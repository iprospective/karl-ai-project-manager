#!/usr/bin/env python3
"""pm-workflow-sync — Synchronise le workflow Redmine (transitions de statut) vers une
référence PM, source de vérité des checks, propositions d'étape et formulaires cockpit (RM2920).

Redmine n'expose PAS le workflow via l'API REST. On le capture EMPIRIQUEMENT en
lecture seule : `GET /issues/:id.json?include=allowed_statuses` renvoie, pour un ticket,
les statuts atteignables depuis son statut courant compte tenu du rôle de l'utilisateur
courant et de sa relation (auteur/assigné). Le workflow étant uniforme (mêmes transitions
tous trackers) et à deux colonnes cumulées (assigné + créateur), on agrège l'UNION des
`allowed_statuses` observés sur les tickets où l'utilisateur de service est assigné OU
auteur, groupés par statut source.

Sortie : `workflow.reference.yml` (racine du repo) — `transitions: {statut_norms: [statut_norms…]}`
en noms NORMS (le statut courant lui-même et les statuts hors NORMS — Commentaire,
Récurrent — sont exclus). Les statuts source non couverts sont listés à part.

    pm-workflow-sync.py                 # capture + écrit workflow.reference.yml
    pm-workflow-sync.py --dry-run       # affiche sans écrire
    pm-workflow-sync.py --check         # diffe la référence vs le live (drift), code sortie ≠0 si drift
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis")

REPO_ROOT = Path(__file__).resolve().parent.parent
REF_PATH = REPO_ROOT / "workflow.reference.yml"
SERVICE_USER_ID = int(os.environ.get("REDMINE_SERVICE_USER_ID", "79"))  # karl


def main():
    ap = argparse.ArgumentParser(description="Synchronise le workflow Redmine vers workflow.reference.yml (RM2920).")
    ap.add_argument("--dry-run", action="store_true", help="affiche sans écrire")
    ap.add_argument("--check", action="store_true", help="diffe la référence vs le live (drift)")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from pm_paths import PMConfig      # charge le .env secret canonique (.mmi-pm-core/.env)
    PMConfig.load()
    import redmine_utils               # status_map NORMS↔id + creds + http
    smap = redmine_utils.status_map()               # {norms: id} (inclut alias + variantes ferme:*)
    aliases = set(redmine_utils.status_aliases().keys())
    id2norms = {}                                    # {id: nom NORMS canonique}
    for norms, sid in smap.items():
        if norms in aliases or ":" in norms:        # exclut alias dépréciés + ferme:<raison>
            continue
        id2norms.setdefault(sid, norms)

    creds = redmine_utils.redmine_creds()            # tuple (url, key) + attribut .basic
    c_url, c_key, c_basic = creds[0].rstrip("/"), creds[1], getattr(creds, "basic", None)

    def api(path):
        code, body = redmine_utils.http_json("GET", c_url + path, c_key, basic=c_basic)
        if code != 200:
            raise RuntimeError(f"HTTP {code} sur {path} : {body}")
        return body

    # union des allowed_statuses par statut source, sur tickets assigné OU auteur = service user
    transitions = {}   # {from_id: set(to_id)}
    seen_source = set()
    for rel in ("assigned_to_id", "author_id"):
        for sid in sorted(id2norms):
            lst = api(f"/issues.json?{rel}={SERVICE_USER_ID}&status_id={sid}&limit=1")
            iss = lst.get("issues", [])
            if not iss:
                continue
            seen_source.add(sid)
            d = api(f"/issues/{iss[0]['id']}.json?include=allowed_statuses")["issue"]
            for s in d.get("allowed_statuses", []):
                tid = s["id"]
                if tid == sid or tid not in id2norms:  # exclut self + statuts hors NORMS
                    continue
                transitions.setdefault(sid, set()).add(tid)

    # rendu en noms NORMS
    ref = {id2norms[fid]: sorted((id2norms[t] for t in tos), key=lambda n: n)
           for fid, tos in sorted(transitions.items())}
    uncovered = sorted(id2norms[i] for i in id2norms if i not in seen_source)

    out = {
        "_generated_by": "pm-workflow-sync.py (RM2920)",
        "_note": ("Capture empirique lecture seule du workflow Redmine via allowed_statuses "
                  "(union assigné+créateur). Source de vérité des checks / propositions / formulaires. "
                  "Statuts source non couverts (aucun ticket du service user) listés dans _uncovered."),
        "_uncovered": uncovered,
        "transitions": ref,
    }

    if args.check:
        if not REF_PATH.exists():
            print("drift : workflow.reference.yml absent"); return 1
        cur = yaml.safe_load(REF_PATH.read_text()).get("transitions", {})
        drift = False
        for k in sorted(set(cur) | set(ref)):
            if cur.get(k) != ref.get(k):
                print(f"  drift [{k}] : ref={cur.get(k)} ≠ live={ref.get(k)}"); drift = True
        print("✓ pas de drift" if not drift else "⚠ drift détecté")
        return 1 if drift else 0

    text = yaml.safe_dump(out, allow_unicode=True, sort_keys=False, default_flow_style=False)
    if args.dry_run:
        print(text)
    else:
        REF_PATH.write_text(text, encoding="utf-8")
        print(f"✓ {REF_PATH.name} écrit — {len(ref)} statut(s) source, "
              f"{sum(len(v) for v in ref.values())} transition(s) ; non couverts : {uncovered or '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
