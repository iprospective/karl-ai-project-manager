#!/usr/bin/env python3
"""pm-task-blockers — pourquoi un ticket ne peut pas changer de statut / être fermé.

Redmine refuse de fermer un ticket tant qu'il a des **relations bloquantes** dont la
source est encore OUVERTE (« blocked by » / « precedes »). Ce script explicite la cause
au lieu de laisser un « statut PAS changé » opaque.

Affiche :
  - les **tickets bloquants encore ouverts** (relations blocks/blocked, precedes/follows) ;
  - les **sous-tâches ouvertes** (info : selon config Redmine, peuvent gêner la clôture) ;
  - un verdict : fermable ou non, et quoi débloquer.

    pm-task-blockers.py 1813
    pm-task-blockers.py 1813 --json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import redmine_utils  # noqa: E402


def _blocker_of(rel, me):
    """Retourne l'id du ticket qui BLOQUE `me` dans cette relation, sinon None.

    Redmine stocke 'blocks' (issue_id bloque issue_to_id) et 'precedes' (issue_id
    précède issue_to_id) ; on gère aussi les formes inverses par prudence.
    """
    a, b, t = rel.get("issue_id"), rel.get("issue_to_id"), rel.get("relation_type")
    if t in ("blocks", "precedes") and b == me:
        return a          # a bloque/précède me
    if t in ("blocked", "follows") and a == me:
        return b          # me est bloqué/suit b
    return None


def main():
    ap = argparse.ArgumentParser(description="Pourquoi un ticket ne peut pas être fermé")
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    me = args.rm_id

    issue = redmine_utils.fetch_issue(me, include="relations,children")
    subj = issue.get("subject", "")
    st = (issue.get("status") or {})

    # Tickets bloquants (relations) encore ouverts.
    blockers = []
    seen = set()
    for rel in issue.get("relations", []):
        bid = _blocker_of(rel, me)
        if not bid or bid in seen:
            continue
        seen.add(bid)
        b = redmine_utils.fetch_issue(bid)
        bst = (b.get("status") or {})
        if not bst.get("is_closed"):
            blockers.append({"id": bid, "type": rel.get("relation_type"),
                             "status": bst.get("name"), "subject": b.get("subject", "")})

    # Sous-tâches ouvertes (info).
    open_children = []
    for c in issue.get("children", []):
        cst = (c.get("status") or {})
        name = cst.get("name")
        if name is None:                       # children sans statut → fetch
            cc = redmine_utils.fetch_issue(c.get("id"))
            cst = cc.get("status") or {}
            name = cst.get("name")
        if not cst.get("is_closed"):
            open_children.append({"id": c.get("id"), "status": name,
                                  "subject": c.get("subject", "")})

    blocked = bool(blockers)
    if args.json:
        print(json.dumps({"id": me, "status": st.get("name"), "blocked": blocked,
                          "blockers": blockers, "open_children": open_children},
                         ensure_ascii=False, indent=2))
        return

    print(f"#{me} — {subj}  [{st.get('name')}]")
    if blockers:
        print("\n⛔ BLOQUÉ par (relation + ticket ouvert) :")
        for b in blockers:
            print(f"   • #{b['id']} [{b['status']}] ({b['type']}) — {b['subject']}")
    else:
        print("\n✅ Aucune relation bloquante ouverte — la clôture n'est pas bloquée par une dépendance.")
    if open_children:
        print("\n↳ Sous-tâches ouvertes (peuvent gêner selon la config Redmine) :")
        for c in open_children:
            print(f"   • #{c['id']} [{c['status']}] — {c['subject']}")
    print()
    if blocked:
        ids = ", ".join(f"#{b['id']}" for b in blockers)
        print(f"→ Pour fermer #{me}, clôture d'abord : {ids}")
    elif open_children:
        print("→ Pas de relation bloquante ; si la clôture est refusée, c'est probablement "
              "une sous-tâche ouverte ou le workflow/rôle.")
    else:
        print("→ Rien ne bloque côté dépendances : si la clôture est refusée, vérifier "
              "workflow/rôle (ex. Évolution fermée par un humain) ou checklist.")
    sys.exit(2 if blocked else 0)


if __name__ == "__main__":
    main()
