"""pm_hierarchy — Helpers partagés pour la hiérarchie parent/enfant des tâches PM.

La hiérarchie `parent_task` / `sub_tasks` est un **attribut natif d'issue Redmine**
(`parent_issue_id`), pas une relation (cf. NORMS § « Liens entre tâches »). Ce module
centralise la réflexion de cet attribut dans le frontmatter MD local :

- côté enfant  : champ `parent_task` (int | null, unique)
- côté parent  : liste `sub_tasks` (enfants directs)

Utilisé par `pm-task-add` (création avec --parent), `pm-task-sync` (réconciliation
depuis Redmine) et `pm-task-link` (sous-commande `parent`).

Aucun appel Redmine ici — uniquement la couche MD locale. Le PUT `parent_issue_id`
vit dans `redmine_utils.set_issue_parent`.
"""
import re
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    import sys
    sys.exit("PyYAML requis : pip install PyYAML")


FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def load_md(cfg, rm_id):
    """Retourne (path, fm, body) pour RMid, ou (None, None, None) si introuvable."""
    p = cfg.find_task(rm_id)
    if not p:
        return None, None, None
    content = p.read_text(encoding="utf-8")
    m = FM_RE.match(content)
    if not m:
        return None, None, None
    fm = yaml.safe_load(m.group(1)) or {}
    body = content[m.end():]
    return p, fm, body


def write_md(path, fm, body):
    fm_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                             default_flow_style=False).rstrip()
    path.write_text(f"---\n{fm_yaml}\n---\n{body}", encoding="utf-8")


def append_log(path, source, message):
    log_path = path.parent / path.name.replace(".md", ".log.md")
    entry = (f"\n## {_now()} — Hiérarchie ({source})\nTokens : 0 | Durée : 0 min\n\n"
             f"{message}\n")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry)


def child_set_parent_field(cfg, child_id, parent_id, source):
    """Pose `parent_task = parent_id` (None pour détacher) sur le MD de l'enfant.

    Retourne (old_parent, changed: bool). N'écrit/logue que si la valeur change.
    Si le MD enfant est introuvable, retourne (None, False) sans erreur.
    """
    path, fm, body = load_md(cfg, child_id)
    if path is None:
        return None, False
    old = fm.get("parent_task")
    if old == parent_id:
        return old, False
    fm["parent_task"] = parent_id
    fm["updated"] = _now()
    write_md(path, fm, body)
    if parent_id is None:
        append_log(path, source, f"`parent_task` : RM{old} → ∅ (détaché).")
    else:
        prev = f"RM{old}" if old else "∅"
        append_log(path, source, f"`parent_task` : {prev} → RM{parent_id}.")
    return old, True


def _parent_subtasks_op(cfg, parent_id, child_id, add, source):
    """Ajoute (add=True) ou retire (add=False) child_id des `sub_tasks` du parent.

    Retourne True si le MD parent existe et a été modifié. Silencieux si le parent
    n'est pas tracké localement (peut être un ticket Redmine hors-PM).
    """
    if parent_id is None:
        return False
    path, fm, body = load_md(cfg, parent_id)
    if path is None:
        return False
    subs = fm.get("sub_tasks") or []
    if not isinstance(subs, list):
        subs = []
    if add:
        if child_id in subs:
            return False
        subs.append(child_id)
        msg = f"`sub_tasks` += RM{child_id}."
    else:
        if child_id not in subs:
            return False
        subs.remove(child_id)
        msg = f"`sub_tasks` -= RM{child_id}."
    fm["sub_tasks"] = subs
    fm["updated"] = _now()
    write_md(path, fm, body)
    append_log(path, source, msg)
    return True


def maintain_parent_subtasks(cfg, child_id, old_parent, new_parent, source):
    """Maintient les `sub_tasks` des parents après changement de parent de l'enfant.

    - retire child_id de l'ancien parent (si différent du nouveau)
    - ajoute child_id au nouveau parent
    Opère uniquement sur les MD parents (jamais l'enfant). Retourne dict de résumé.
    """
    res = {"removed_from": None, "added_to": None}
    if old_parent is not None and old_parent != new_parent:
        if _parent_subtasks_op(cfg, old_parent, child_id, add=False, source=source):
            res["removed_from"] = old_parent
    if new_parent is not None:
        if _parent_subtasks_op(cfg, new_parent, child_id, add=True, source=source):
            res["added_to"] = new_parent
    return res


def set_parent(cfg, child_id, parent_id, source):
    """Opération complète côté MD : (re)pose le parent d'un enfant existant.

    Met à jour `parent_task` de l'enfant ET les `sub_tasks` de l'ancien et du
    nouveau parent. NE TOUCHE PAS Redmine (le caller fait le PUT via
    redmine_utils.set_issue_parent). Retourne dict de résumé.
    """
    old_parent, changed = child_set_parent_field(cfg, child_id, parent_id, source)
    sub = maintain_parent_subtasks(cfg, child_id, old_parent, parent_id, source)
    return {"child_changed": changed, "old_parent": old_parent,
            "new_parent": parent_id, **sub}
