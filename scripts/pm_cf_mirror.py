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

**Mais il ne doit pas non plus être MUET** (RM3366). Le PUT partait sans délai
d'attente : quand l'API traînait, il restait pendant jusqu'au délai système. Or
les appelants écrivent le miroir local AVANT de pousser ; un script interrompu
entre les deux (un `timeout` de shell, un Ctrl-C, un cron tué) laissait le
frontmatter affirmer « coché » et le champ dire « non coché », sans que personne
ne soit prévenu. L'écart ne se voyait qu'au prochain garde-fou de statut, sous
une forme incompréhensible : « aucun critère coché » sur un ticket complet
(constaté sur RM3330 et RM3346, chantier RM3217).

D'où trois garde-fous ici : un délai explicite, une RELECTURE après écriture, et
une divergence qui se dit à voix haute avec la commande pour la réparer.
"""
import json
import os
import sys
import urllib.error
import urllib.request

# Délai d'attente des appels API, en secondes. Un PUT sans délai peut rester
# pendant plusieurs minutes sur une instance lente : le script paraît figé, et
# l'appelant finit par le tuer — au pire moment, entre l'écriture locale et le
# push. Surchargeable par PM_HTTP_TIMEOUT pour les instances lentes.
HTTP_TIMEOUT = int(os.environ.get("PM_HTTP_TIMEOUT", "20"))
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import redmine_utils


# ── Sérialisation liste ↔ texte (deploy_actions / CF 8) ───────────────────────
# Le frontmatter porte une LISTE ordonnée (l'ordre est l'ordre d'exécution) ; le CF
# Redmine est un texte. La conversion doit être symétrique dans les deux sens, et le
# parseur tolérant : un humain qui saisit dans l'UI web tapera des puces ou des
# numéros, pas la forme canonique.
import re as _re

_H_RE = _re.compile(r"^(#{1,6})\s*(.*)$")
_IMPL_RE = _re.compile(r"(?i)^impl[ée]mentations?\b")


def extract_implementation_section(body: str):
    """Corps de la section `## Implémentation` d'un MD, ou None.

    La section court jusqu'au prochain titre de niveau **inférieur ou égal** au sien,
    pas jusqu'au prochain titre tout court : une esquisse structurée en sous-parties
    (`### Modèle de données`, `### Composants`…) serait sinon tronquée à sa phrase
    d'introduction. Constaté sur RM2560 — 160 caractères repris sur 6057.
    """
    lines = (body or "").splitlines()
    start = level = None
    for i, line in enumerate(lines):
        m = _H_RE.match(line)
        if m and _IMPL_RE.match(m.group(2).strip()):
            start, level = i, len(m.group(1))
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = _H_RE.match(lines[j])
        if m and len(m.group(1)) <= level:
            end = j
            break
    return "\n".join(lines[start + 1:end]).strip() or None


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


def push_text_cf(rm_id: int, text: str, *, env_var: str, cf_name: str, verify: bool = True) -> bool:
    """PUT du CF texte. True si poussé ET relu conforme ; False sinon (non fatal).

    La relecture n'est pas un luxe : sans elle, une écriture perdue ne se découvre
    qu'au prochain garde-fou de statut, des heures plus tard et sous une forme
    trompeuse (RM3366). Elle coûte une requête GET ; l'écart coûtait une enquête.
    """
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
        urllib.request.urlopen(req, timeout=HTTP_TIMEOUT)
    except urllib.error.HTTPError as e:
        print(f"⚠ PUT CF {cid} « {cf_name} » → HTTP {e.code} (non fatal)", file=sys.stderr)
        return False
    except urllib.error.URLError as e:
        print(f"⚠ PUT CF {cid} « {cf_name} » → {e.reason} (non fatal)", file=sys.stderr)
        return False
    except OSError as e:  # délai dépassé, socket coupée…
        print(f"⚠ PUT CF {cid} « {cf_name} » → {e} (non fatal)", file=sys.stderr)
        return False

    if not verify:
        return True

    # Relecture : le champ doit maintenant porter ce qu'on vient d'écrire.
    relu = pull_text_cf(rm_id, env_var=env_var, cf_name=cf_name, verbose=False)
    if normalize_text(relu) == normalize_text(text):
        return True

    print(f"⚠ CF {cid} « {cf_name} » : l'écriture n'a pas pris côté Redmine — le miroir "
          f"local et le champ DIVERGENT.\n"
          f"  → Réparer : pm-task-cf-resync.py {rm_id}", file=sys.stderr)

    return False


def pull_text_cf(rm_id: int, *, env_var: str, cf_name: str, verbose: bool = True):
    """Valeur actuelle du CF côté Redmine, ou None (CF non résolu, ticket illisible).

    Sert au sens REDMINE → PM : un humain peut saisir le champ directement dans
    l'UI web, et le miroir local doit pouvoir le rattraper. Sert aussi à VÉRIFIER
    ce qu'on vient d'écrire (RM3366) — d'où `verbose`, pour ne pas crier deux fois
    sur la même panne.
    """
    cid = resolve_cf_id(env_var, cf_name)
    if cid is None:
        return None
    try:
        issue = redmine_utils.fetch_issue(rm_id)
    except Exception as e:  # noqa: BLE001 — lecture d'appoint, jamais fatale
        if verbose:
            print(f"⚠ lecture RM{rm_id} impossible ({e}) — CF non relu.", file=sys.stderr)
        return None
    for cf in (issue or {}).get("custom_fields", []):
        if cf.get("id") == cid:
            return (cf.get("value") or "").strip() or None
    return None
