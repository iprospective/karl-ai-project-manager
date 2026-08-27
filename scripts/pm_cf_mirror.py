#!/usr/bin/env python3
"""pm_cf_mirror — miroir « champ frontmatter ↔ custom field Redmine » (RM2563).

Trois champs de tâche suivent aujourd'hui le même contrat, né avec le protocole
de test (RM2229) :

| frontmatter      | CF Redmine                     | écrit par                  |
|------------------|--------------------------------|----------------------------|
| `test_protocol`  | 30 « Protocole de test »       | `pm-task-protocol.py`      |
| `implementation` | 31 « Proposition d'implém. »   | `pm-task-implementation.py`|
| `deploy_actions` | 8  « Actions au déploiement »  | `pm-task-deploy.py`        |

Contrat commun :
- **le CF Redmine est le champ canonique** (visible sur la fiche web, requêtable) ;
- **le frontmatter est le miroir local** — c'est LUI que lit la fiche de revue du
  cockpit (karl-agent ne lit que le local, jamais l'API) ;
- l'id du CF se résout par `.env` (override explicite) puis par
  `redmine.reference.yml` (source canonique) ; **absent ⇒ miroir seul + warning,
  jamais d'échec** : le cockpit continue de fonctionner, Redmine n'affiche
  simplement pas le champ.

Le PUT du CF n'est JAMAIS fatal : une écriture locale réussie ne doit pas être
perdue parce que Redmine est injoignable.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import redmine_utils


def resolve_cf_id(env_var: str, cf_name: str):
    """Id du CF : override `.env` (entier), sinon `redmine.reference.yml`, sinon None."""
    v = os.environ.get(env_var, "").strip()
    if v.isdigit():
        return int(v)
    try:
        return redmine_utils.cf_id_by_name(cf_name)
    except Exception:  # noqa: BLE001 — référence absente ou champ inconnu : miroir seul
        return None


def push_text_cf(rm_id: int, text: str, *, env_var: str, cf_name: str) -> bool:
    """PUT du CF texte. True si poussé ; False si non configuré / échec (non fatal)."""
    cid = resolve_cf_id(env_var, cf_name)
    if cid is None:
        print(f"⚠ CF « {cf_name} » non résolu ({env_var} absent du .env et nom absent de "
              f"redmine.reference.yml) — miroir frontmatter seul.", file=sys.stderr)
        return False
    base = os.environ.get("REDMINE_URL", "").rstrip("/")
    key = os.environ.get("REDMINE_API_KEY") or os.environ.get("REDMINE_USER_MAIN_API_KEY")
    if not base or not key:
        print("⚠ REDMINE_URL / clé API absents — CF non poussé.", file=sys.stderr)
        return False
    body = json.dumps({"issue": {"custom_fields": [{"id": cid, "value": text}]}}).encode()
    req = urllib.request.Request(f"{base}/issues/{rm_id}.json", data=body, method="PUT",
                                 headers={"X-Redmine-API-Key": key,
                                          "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
        return True
    except urllib.error.HTTPError as e:
        print(f"⚠ PUT CF {cid} « {cf_name} » → HTTP {e.code} (non fatal)", file=sys.stderr)
        return False
    except urllib.error.URLError as e:
        print(f"⚠ PUT CF {cid} « {cf_name} » → {e.reason} (non fatal)", file=sys.stderr)
        return False


def pull_text_cf(rm_id: int, *, env_var: str, cf_name: str):
    """Valeur actuelle du CF côté Redmine, ou None (CF non résolu, ticket illisible).

    Sert au sens REDMINE → PM : un humain peut saisir le champ directement dans
    l'UI web, et le miroir local doit pouvoir le rattraper.
    """
    cid = resolve_cf_id(env_var, cf_name)
    if cid is None:
        return None
    try:
        issue = redmine_utils.fetch_issue(rm_id)
    except Exception as e:  # noqa: BLE001 — lecture d'appoint, jamais fatale
        print(f"⚠ lecture RM{rm_id} impossible ({e}) — CF non relu.", file=sys.stderr)
        return None
    for cf in (issue or {}).get("custom_fields", []):
        if cf.get("id") == cid:
            return (cf.get("value") or "").strip() or None
    return None
