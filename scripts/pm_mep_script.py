"""pm_mep_script — le script de MEP d'un ticket (RM3225).

Quand une mise en production demande plus que le workflow générique, sa procédure
s'automatise dans un script **conservé à côté de la fiche du ticket** :

    tasks/RM<id>_<slug>.script-mep.sh

Frère de la fiche au même titre que `.log.md`, `.think.md`, `.reporting.yml` : versionné
avec les données du projet, jamais supprimé (c'est l'historique exécutable des MEP).
Décision de Mathieu du 2026-09-18, premier cas réel : RM3219 (pisceen/presta).

Ce module est la SEULE lecture de ces scripts : le cockpit (fiche du ticket),
`pm-task-status-update` (rappel à l'entrée en a_mep) et `pm-task-deploy` passent par lui.

Contrat minimal d'un script (norme `git-mep-pratique` § Actions au déploiement) :
`set -euo pipefail` ; mode CONTRÔLE par défaut (lecture seule) ; `--apply` pour
exécuter ; idempotent ; gardes avant le point de non-retour ; vérification finale ;
rollback en en-tête ; aucun secret. `lint()` en vérifie ce qui se voit dans le texte —
un signalement, jamais un refus.
"""
import re
from pathlib import Path

SUFFIX = ".script-mep.sh"
MAX_CHARS = 20000

# alias ssh employé par l'en-tête (`ssh pisceen-presta 'bash -s' < …`)
_ALIAS_RE = re.compile(r"ssh\s+(?:-\S+\s+)*([A-Za-z0-9][\w.@-]*)\s+'bash -s")


def script_path(task_file) -> Path:
    """Le chemin du script de MEP d'une fiche (`RM12_x.md` → `RM12_x.script-mep.sh`), qu'il existe ou non."""
    p = Path(task_file)
    stem = p.name[:-3] if p.name.endswith(".md") else p.stem
    return p.with_name(stem + SUFFIX)


def find(task_file):
    """Le script de MEP de la fiche s'il existe, sinon None."""
    s = script_path(task_file)
    return s if s.is_file() else None


def alias_from_text(text: str):
    """Premier alias ssh cité dans le script (`ssh <alias> 'bash -s' …`), sinon None."""
    m = _ALIAS_RE.search(text or "")
    return m.group(1) if m else None


def launch_commands(name: str, alias=None, prefix: str = ".mmi-pm/tasks") -> dict:
    """Les deux commandes de lancement, depuis la racine du workspace de code.

    Le script s'exécute SUR la cible et se lance depuis le poste de l'opérateur : il est
    passé sur l'entrée standard, rien n'est copié sur le serveur."""
    a = alias or "<alias-ssh>"
    path = f"{prefix.rstrip('/')}/{name}" if prefix else name
    return {"check": f"ssh {a} 'bash -s' < {path}",
            "apply": f"ssh {a} 'bash -s -- --apply' < {path}"}


def lint(text: str) -> list:
    """Ce que le contrat minimal attend et que le texte ne montre pas (liste de libellés)."""
    t = text or ""
    manques = []
    if not re.search(r"(?m)^\s*set\s+-euo\s+pipefail\b", t):
        manques.append("set -euo pipefail")
    if "--apply" not in t:
        manques.append("mode --apply (contrôle par défaut)")
    if not re.search(r"(?i)rollback|retour arri[eè]re", t):
        manques.append("procédure de rollback")
    return manques


def describe(task_file, alias=None, prefix: str = ".mmi-pm/tasks", max_chars: int = MAX_CHARS):
    """{file, text, truncated, lines, launch, alias, lint} — ou None s'il n'y a pas de script.

    `alias` : alias ssh de la cible (environnement de prod du projet) ; à défaut, celui
    que cite l'en-tête du script. Lecture bornée : la fiche s'ouvre souvent."""
    s = find(task_file)
    if s is None:
        return None
    try:
        text = s.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    al = alias or alias_from_text(text)
    return {"file": s.name, "text": text[:max_chars], "truncated": len(text) > max_chars,
            "lines": text.count("\n") + (0 if text.endswith("\n") or not text else 1),
            "alias": al, "launch": launch_commands(s.name, al, prefix), "lint": lint(text)}
