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


# ── Sérialisation liste ↔ texte (deploy_actions / CF 8) ───────────────────────
# Le frontmatter porte une LISTE ordonnée (l'ordre est l'ordre d'exécution) ; le CF
# Redmine est un texte. La conversion doit être symétrique dans les deux sens, et le
# parseur tolérant : un humain qui saisit dans l'UI web tapera des puces ou des
# numéros, pas la forme canonique.
import re as _re

def normalize_text(value) -> str:
    """Texte comparable des deux côtés du miroir.

    Redmine restitue les champs texte en **CRLF** : sans cette normalisation, un
    contenu pourtant identique paraît différer à chaque lecture — faux conflit dans
    le backfill, et diff permanent (donc réécriture en boucle) dans `pm-task-sync`.
    Constaté sur RM2400 : 1077 caractères en local, 1092 côté Redmine, zéro ligne
    de différence.
    """
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


_BULLET_RE = _re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def list_to_text(items) -> str:
    """Liste → texte du CF : une entrée par ligne, puce `- `."""
    return "\n".join(f"- {i}" for i in items)


def text_to_list(text: str):
    """Texte du CF → liste. Tolère `-`, `*`, `•` et la numérotation `1.` / `1)`."""
    out = []
    for line in normalize_text(text).splitlines():
        line = _BULLET_RE.sub("", line).strip()
        if line:
            out.append(line)
    return out


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
