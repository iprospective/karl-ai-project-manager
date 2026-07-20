#!/usr/bin/env python3
"""Validateur de fichiers de tâches.

Vérifie qu'un fichier MD respecte le schéma défini dans norms/NORMS.md.
Utilisable en pre-commit hook ou en CI.

Usage :
    ./scripts/validate-task.py <fichier.md> [<fichier2.md> ...]
"""

import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERREUR : PyYAML requis. Installer avec : pip install pyyaml", file=sys.stderr)
    sys.exit(2)


REQUIRED_FIELDS = [
    "schema_version", "redmine_id", "title", "type",
    "creator", "status", "priority", "created",
]

VALID_TYPES = {
    "audit", "feature", "bugfix", "refactoring", "documentation",
    "security", "performance", "infrastructure", "configuration", "database",
    "design", "research", "maintenance", "assistance",
}

VALID_STATUSES = {
    "nouveau",  # statut d'entrée : ticket créé non encore trié (défaut pm-task-add)
    "a_etudier_chiffrer", "etude_chiffrage_en_cours", "etude_chiffrage_a_valider", "a_faire",
    "en_cours", "a_tester_dev", "a_tester_demandeur", "a_mep", "en_mep",
    "en_pause", "a_corriger", "ferme",
    "a_tester_verifier",  # déprécié — alias de a_tester_demandeur (rétrocompat)
}

VALID_PRIORITIES = {"low", "normal", "high", "urgent"}

VALID_CLOSE_REASONS = {
    "resolu", "abandonne", "doublon", "wont_fix", "invalide", "hors_perimetre",
}

VALID_REPRODUCIBILITIES = {"always", "often", "sometimes", "rarely", "never"}
VALID_DIFFICULTIES = {"low", "medium", "high", "critical"}
VALID_PISTE_TYPES = {"automation", "amélioration", "sécurité", "performance", "intégration", "documentation"}
VALID_PISTE_EFFORTS = {"low", "medium", "high"}

FILENAME_PATTERN = re.compile(r"^RM\d+_[a-z0-9-]+\.md$")
LOG_FILENAME_PATTERN = re.compile(r"^RM\d+_[a-z0-9-]+\.log\.md$")
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class Validator:
    def __init__(self):
        self.errors = []

    def err(self, file, msg):
        self.errors.append(f"{file}: {msg}")

    def parse_frontmatter(self, file_path):
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            self.err(file_path, f"Lecture impossible : {e}")
            return None

        m = FRONTMATTER_PATTERN.match(content)
        if not m:
            self.err(file_path, "Frontmatter YAML manquant ou mal formaté (doit commencer par ---)")
            return None

        try:
            return yaml.safe_load(m.group(1))
        except yaml.YAMLError as e:
            self.err(file_path, f"YAML invalide : {e}")
            return None

    def validate_filename(self, file_path):
        name = os.path.basename(file_path)
        # Ignorer le template
        if name == "task.md":
            return True
        if name.endswith(".log.md"):
            if not LOG_FILENAME_PATTERN.match(name):
                self.err(file_path, f"Nom de log non conforme (attendu : RM{{id}}_{{kebab}}.log.md)")
            return False  # ne pas valider le contenu d'un log
        if not FILENAME_PATTERN.match(name):
            self.err(file_path, f"Nom de fichier non conforme (attendu : RM{{id}}_{{kebab}}.md)")
        return True

    def validate_redmine_coherence(self, file_path, fm):
        """Le RM{id} du nom de fichier doit correspondre au redmine_id du frontmatter."""
        name = os.path.basename(file_path)
        m = re.match(r"^RM(\d+)_", name)
        if not m:
            return  # filename invalide déjà signalé par validate_filename
        filename_id = int(m.group(1))
        rid = fm.get("redmine_id")
        try:
            rid_int = int(rid) if rid is not None else None
        except (TypeError, ValueError):
            self.err(file_path, f"redmine_id doit être un entier (reçu : {rid!r})")
            return
        if rid_int is None:
            return  # déjà signalé par validate_required
        if rid_int != filename_id:
            self.err(file_path, f"Incohérence : nom de fichier RM{filename_id}_ ≠ redmine_id du frontmatter ({rid_int})")

    def validate_required(self, file, fm):
        for field in REQUIRED_FIELDS:
            if field not in fm or fm[field] in (None, ""):
                self.err(file, f"Champ obligatoire manquant ou vide : {field}")

    def validate_enums(self, file, fm):
        if fm.get("type") and fm["type"] not in VALID_TYPES:
            self.err(file, f"type invalide : {fm['type']} (attendu parmi {sorted(VALID_TYPES)})")
        if fm.get("status") and fm["status"] not in VALID_STATUSES:
            self.err(file, f"status invalide : {fm['status']}")
        if fm.get("priority") and fm["priority"] not in VALID_PRIORITIES:
            self.err(file, f"priority invalide : {fm['priority']}")
        if fm.get("close_reason") and fm["close_reason"] not in VALID_CLOSE_REASONS:
            self.err(file, f"close_reason invalide : {fm['close_reason']}")

    def validate_conditional(self, file, fm):
        # close_reason obligatoire si status = ferme
        if fm.get("status") == "ferme" and not fm.get("close_reason"):
            self.err(file, "close_reason obligatoire quand status = ferme")
        # bug.* obligatoire si type = bugfix
        if fm.get("type") == "bugfix":
            bug = fm.get("bug") or {}
            if not bug.get("reproducibility"):
                self.err(file, "bug.reproducibility obligatoire pour type=bugfix")
            elif bug["reproducibility"] not in VALID_REPRODUCIBILITIES:
                self.err(file, f"bug.reproducibility invalide : {bug['reproducibility']}")
            if not bug.get("reproduce_steps"):
                self.err(file, "bug.reproduce_steps obligatoire pour type=bugfix")

    def validate_estimate(self, file, fm):
        est = fm.get("estimate") or {}
        if est.get("difficulty") and est["difficulty"] not in VALID_DIFFICULTIES:
            self.err(file, f"estimate.difficulty invalide : {est['difficulty']}")
        if est.get("confidence") is not None:
            try:
                c = float(est["confidence"])
                if not 0 <= c <= 1:
                    self.err(file, f"estimate.confidence doit être entre 0 et 1 (reçu {c})")
            except (TypeError, ValueError):
                self.err(file, f"estimate.confidence doit être numérique")

    def validate_status_history(self, file, fm):
        sh = fm.get("status_history")
        if not isinstance(sh, list) or not sh:
            self.err(file, "status_history doit être une liste non vide")
            return
        last = sh[-1]
        if not isinstance(last, dict) or last.get("status") != fm.get("status"):
            self.err(file, "Le dernier status_history doit correspondre au status courant")
        for i, entry in enumerate(sh):
            if not isinstance(entry, dict):
                self.err(file, f"status_history[{i}] doit être un objet")
                continue
            if entry.get("status") not in VALID_STATUSES:
                self.err(file, f"status_history[{i}].status invalide : {entry.get('status')}")

    def validate_pistes(self, file, fm):
        for i, p in enumerate(fm.get("pistes") or []):
            if not isinstance(p, dict):
                continue
            if p.get("type") and p["type"] not in VALID_PISTE_TYPES:
                self.err(file, f"pistes[{i}].type invalide : {p['type']}")
            if p.get("effort") and p["effort"] not in VALID_PISTE_EFFORTS:
                self.err(file, f"pistes[{i}].effort invalide : {p['effort']}")

    def validate_completion_pct(self, file, fm):
        pct = fm.get("completion_pct")
        if pct is not None:
            try:
                p = int(pct)
                if not 0 <= p <= 100:
                    self.err(file, f"completion_pct doit être entre 0 et 100 (reçu {p})")
            except (TypeError, ValueError):
                self.err(file, "completion_pct doit être un entier")

    def validate(self, file_path):
        name = os.path.basename(file_path)
        # Le template skeleton n'est pas validé pour son contenu (champs vides volontaires)
        if name == "task.md":
            fm = self.parse_frontmatter(file_path)
            if fm is None:
                return
            return
        if not self.validate_filename(file_path):
            return
        fm = self.parse_frontmatter(file_path)
        if fm is None:
            return
        self.validate_required(file_path, fm)
        self.validate_enums(file_path, fm)
        self.validate_conditional(file_path, fm)
        self.validate_estimate(file_path, fm)
        self.validate_status_history(file_path, fm)
        self.validate_pistes(file_path, fm)
        self.validate_completion_pct(file_path, fm)
        self.validate_redmine_coherence(file_path, fm)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    files = sys.argv[1:]
    v = Validator()
    for f in files:
        v.validate(f)

    if v.errors:
        for e in v.errors:
            print(f"✗ {e}", file=sys.stderr)
        print(f"\n{len(v.errors)} erreur(s) sur {len(files)} fichier(s)", file=sys.stderr)
        sys.exit(1)

    print(f"✓ {len(files)} fichier(s) validé(s)")


if __name__ == "__main__":
    main()
