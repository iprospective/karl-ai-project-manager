#!/usr/bin/env python3
"""pm_task_md — gabarit d'une fiche de tâche PM (frontmatter + corps + journal).

Source UNIQUE du squelette d'une tâche. Deux producteurs de fiches l'utilisent :
  * `pm-task-add.py`    — création (le ticket est créé côté Redmine dans la foulée) ;
  * `pm-task-import.py` — adoption d'un ticket Redmine qui existe DÉJÀ sans fiche PM
    (rattachement rétroactif, cf. RM2626 / [[Cdc-rm2626-tickets-partenaires]]).

Extrait de `pm-task-add.py` (RM2657), qui reste l'unique producteur de tickets NEUFS :
les deux écrivaient sinon deux squelettes voués à diverger au premier champ ajouté au
schéma. Tables, slug et détection des critères sont repris à l'identique.
"""
import re
import unicodedata
from datetime import datetime

try:
    import yaml
except ImportError:                                            # pragma: no cover
    raise SystemExit("ERREUR : PyYAML requis (pip install pyyaml)")

SCHEMA_VERSION = "1.12.0"

TYPE_TO_TRACKER = {
    "feature": 2,         # Évolution            (worker-dev)
    "bugfix": 1,          # Anomalie             (worker-dev)
    "refactoring": 4,     # Tâche                (worker-dev)
    "security": 4,        # Tâche                (worker-dev)
    "performance": 4,     # Tâche                (worker-dev)
    "infrastructure": 4,  # Tâche                (worker-infra)
    "configuration": 4,   # Tâche — CF20 Config  (worker-infra)
    "database": 4,        # Tâche                (worker-db)
    "maintenance": 4,     # Tâche                (worker-analyst)
    "documentation": 4,   # Tâche                (worker-analyst)
    "research": 4,        # Tâche — Audit/Analyse (worker-analyst)
    "audit": 4,           # Tâche — Audit/Analyse (worker-analyst)
    "design": 4,          # Tâche                (worker-design)
    "assistance": 3,      # Assistance           (worker-analyst)
    "autre": 4,           # Tâche (repli)
}
TYPE_LABELS = {
    "feature": "feature — fonctionnalité",
    "bugfix": "bugfix — anomalie",
    "refactoring": "refactoring — refonte",
    "security": "security — sécurité",
    "performance": "performance — optimisation",
    "infrastructure": "infrastructure — sysadmin/conf",
    "configuration": "configuration — paramétrage applicatif / système",
    "database": "database — schéma / migration / données",
    "maintenance": "maintenance — entretien",
    "documentation": "documentation",
    "research": "research — investigation",
    "audit": "audit — audit / analyse",
    "design": "design — conception",
    "assistance": "assistance — support",
    "autre": "autre",
}
PRIORITY_TO_ID = {"low": 1, "normal": 2, "high": 3, "urgent": 4}


# Inverse du tracker → type NORMS, pour ADOPTER un ticket qui existe déjà. La
# correspondance est ambiguë par construction (le tracker 4 « Tâche » couvre une
# dizaine de types NORMS) : on rend le repli neutre `autre`, à l'appelant de forcer
# `--type` s'il sait mieux.
_TRACKER_TO_TYPE = {2: "feature", 1: "bugfix", 3: "assistance", 4: "autre"}


def tracker_to_type(tracker_id, default="autre"):
    """tracker Redmine → type NORMS (repli neutre, cf. `_TRACKER_TO_TYPE`)."""
    try:
        return _TRACKER_TO_TYPE.get(int(tracker_id), default)
    except (TypeError, ValueError):
        return default


def priority_id_to_name(priority_id, default="normal"):
    """priorité Redmine → priorité NORMS."""
    try:
        return {v: k for k, v in PRIORITY_TO_ID.items()}.get(int(priority_id), default)
    except (TypeError, ValueError):
        return default


def slugify(s: str, maxlen: int = 50) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9-]+", "-", s).strip("-").lower()
    return s[:maxlen].rstrip("-")


# Titre markdown « Critères d'acceptation » : niveau libre, casse et accents
# indifférents, apostrophe droite ou typographique, suffixe toléré (« … (DoD) »).
# Jusqu'à 3 espaces d'indentation — au-delà, markdown y voit un bloc de code.
CRITERIA_HEADING_RE = re.compile(r"^ {0,3}#{1,6}\s*crit[eè]res?\s+d['’]acceptation\b",
                                 re.M | re.I)
CODE_FENCE_RE = re.compile(r"^ {0,3}(```|~~~).*?^ {0,3}\1", re.M | re.S)


def has_acceptance_criteria(desc: str) -> bool:
    """La description fournit-elle déjà sa section de critères ?

    Les blocs de code sont retirés d'abord : un titre qui s'y trouve est un
    exemple cité, pas une section du ticket.
    """
    return bool(CRITERIA_HEADING_RE.search(CODE_FENCE_RE.sub("", desc or "")))

def build_frontmatter(rm_id, title, *, type="feature", priority="normal",
                      status="nouveau", parent=None, tags=None, target_env=None,
                      agent_test="default", recurrence=None, created=None, now=None,
                      estimate=None, creator="iprospective",
                      team=None, estimated_by="pm-task-add"):
    """Frontmatter d'une fiche neuve. `estimate` : dict partiel des champs d'estimation.

    `created` permet de dater la fiche du jour de création du ticket DISTANT lors
    d'une adoption — une fiche importée ne doit pas prétendre être née aujourd'hui.
    """
    now = now or datetime.now().strftime("%Y-%m-%dT%H:%M")
    est = dict(difficulty="medium", human_time_minutes=30, ai_time_minutes=30,
               tokens=None, cost_usd=None, estimated_model=None, confidence=0.5)
    est.update({k: v for k, v in (estimate or {}).items() if v is not None})
    est["time_minutes"] = (est["human_time_minutes"] or 0) + (est["ai_time_minutes"] or 0)
    est["estimated_by"], est["estimated_at"] = estimated_by, now
    return {
        "schema_version": SCHEMA_VERSION,
        "redmine_id": rm_id,
        "redmine_last_journal_id": None,
        "redmine_last_checked_at": None,
        "title": title,
        "type": type,
        "bootstrap_template": None,
        "parent_task": parent,
        "sub_tasks": [],
        "creator": creator,
        "team": team if team is not None else [
            {"username": "iprospective", "email": "mathieu@iprospective.fr",
             "role": "owner"}],
        "status": status,
        "close_reason": None,
        "requires_agent_test": agent_test,
        "recurrence": recurrence,
        "completion_pct": 0,
        "priority": priority,
        "roi": {"immediate_benefit": 3, "monthly_benefit": 3,
                "immediate_gain_eur": None, "monthly_gain_eur": None},
        "estimate": est,
        "depends_on": [], "blocks": [], "relates": [], "refs": [],
        "target_env": target_env,
        "test_url": None,
        "git": {"repo": None, "branch": None, "mr_url": None},
        "deploy_actions": [],
        "tokens_total": 0,
        "tokens_breakdown": {"input": 0, "output": 0, "cache_read": 0,
                             "cache_creation": 0},
        "cost_total_usd": 0.0,
        "human_time_total_minutes": 0,
        "ai_time_total_minutes": 0,
        "time_total_minutes": 0,  # conservé pour compat (= human + ai cumul)
        "created": created or datetime.now().strftime("%Y-%m-%d"),
        "due": None, "updated": now,
        "status_history": [{"status": status, "at": now, "by": creator,
                            "model": None, "tokens": None, "duration_minutes": None}],
        "pistes": [],
        "tags": list(tags or []),
    }


def render_md(fm, description=""):
    """Fiche complète (frontmatter + corps). Le gabarit de critères n'est ajouté que
    si la description n'en porte pas déjà (RM2540)."""
    fm_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                             default_flow_style=False).rstrip()
    desc = description or "_(pas de description fournie au moment de la création)_"
    md = f"---\n{fm_yaml}\n---\n\n## Contexte\n\n{desc}\n"
    if not has_acceptance_criteria(desc):
        md += "\n## Critères d'acceptation\n\n- [ ] (à compléter)\n"
    return md


def render_log(rm_id, now=None, title="Création (pm-task-add)",
               body="Tâche créée via pm-task-add.py."):
    now = now or datetime.now().strftime("%Y-%m-%dT%H:%M")
    return (f"# Journal RM{rm_id}\n\n## {now} — {title}\n"
            f"Tokens : 0 | Durée : 0 min\n\n{body}\n")
