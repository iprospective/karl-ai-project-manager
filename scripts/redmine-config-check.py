#!/usr/bin/env python3
"""redmine-config-check — Diffe la config Redmine live contre la référence locale.

Les IDs Redmine (custom fields, statuts, trackers, priorités, activités de saisie
de temps) sont propres à l'instance et mutables. Un ID périmé fait échouer
*silencieusement* un POST/PUT (cf. knowledge/redmine/gotchas.md). Ce script
revalide périodiquement le binding du système PM (NORMS § « Synchronisation de la
configuration Redmine »).

Référence : `redmine.reference.yml` à la racine du repo PM — source unique de
vérité des IDs sur lesquels le code se lie. Seuls les éléments réellement bindés
y figurent (pas l'intégralité des énumérations de l'instance).

Modes :
    redmine-config-check.py            # rapport humain, exit≠0 si drift
    redmine-config-check.py --json     # rapport machine (CI / pré-vol)
    redmine-config-check.py --dump     # squelette de référence depuis le live (YAML)
    redmine-config-check.py --quiet    # n'affiche que les drifts (silencieux si OK)

Exit code : 0 si aucun drift bloquant, 1 si drift détecté, 2 si erreur d'accès.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import _load_env_file
from redmine_utils import redmine_creds, http_json

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")


PM_DIR = Path(__file__).resolve().parent.parent
REFERENCE_FILE = PM_DIR / "redmine.reference.yml"

# Endpoint live → clé de réponse JSON.
ENDPOINTS = {
    "custom_fields":        ("/custom_fields.json",                       "custom_fields"),
    "issue_statuses":       ("/issue_statuses.json",                      "issue_statuses"),
    "trackers":             ("/trackers.json",                            "trackers"),
    "issue_priorities":     ("/enumerations/issue_priorities.json",       "issue_priorities"),
    "time_entry_activities":("/enumerations/time_entry_activities.json",  "time_entry_activities"),
}


def fetch_live():
    """Récupère la config live. Retourne dict {section: {id: item}} ou sys.exit(2)."""
    url, key = redmine_creds()
    live = {}
    for section, (ep, resp_key) in ENDPOINTS.items():
        code, body = http_json("GET", f"{url}{ep}", key)
        if code != 200:
            print(f"ERREUR : GET {ep} → HTTP {code} : {body.get('_error', '')[:200]}",
                  file=sys.stderr)
            sys.exit(2)
        live[section] = {item["id"]: item for item in body.get(resp_key, [])}
    return live


def load_reference():
    """Charge redmine.reference.yml. Sys.exit(2) si absent/illisible."""
    if not REFERENCE_FILE.is_file():
        print(f"ERREUR : référence introuvable : {REFERENCE_FILE}", file=sys.stderr)
        sys.exit(2)
    try:
        return yaml.safe_load(REFERENCE_FILE.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        print(f"ERREUR : YAML invalide dans {REFERENCE_FILE} : {e}", file=sys.stderr)
        sys.exit(2)


# ── Diff ─────────────────────────────────────────────────────────────────────

def _drift(section, ref_id, expected, found, kind, detail):
    return {"section": section, "id": ref_id, "expected": expected,
            "found": found, "kind": kind, "detail": detail}


def check_custom_fields(ref, live, drifts):
    live_cf = live["custom_fields"]
    for cf_id, spec in (ref.get("custom_fields") or {}).items():
        exp_name = spec.get("name")
        item = live_cf.get(cf_id)
        if item is None:
            drifts.append(_drift("custom_fields", cf_id, exp_name, None,
                                 "missing", f"CF {cf_id} ({exp_name!r}) absent du live"))
            continue
        if item.get("name") != exp_name:
            drifts.append(_drift("custom_fields", cf_id, exp_name, item.get("name"),
                                 "renamed", f"CF {cf_id} : nom {exp_name!r} → {item.get('name')!r}"))
        if spec.get("format") and item.get("field_format") != spec["format"]:
            drifts.append(_drift("custom_fields", cf_id, spec["format"], item.get("field_format"),
                                 "format_changed",
                                 f"CF {cf_id} ({exp_name!r}) : format {spec['format']} → {item.get('field_format')}"))
        if spec.get("on") and item.get("customized_type") != spec["on"]:
            drifts.append(_drift("custom_fields", cf_id, spec["on"], item.get("customized_type"),
                                 "type_changed",
                                 f"CF {cf_id} ({exp_name!r}) : customized_type {spec['on']} → {item.get('customized_type')}"))


def check_id_name_map(section, ref_map, live, drifts, *, name_check=True):
    """Vérifie qu'un mapping {clé_norms: id} ou {id: nom} pointe vers un id live.

    `ref_map` peut être {label: id} (statuses/trackers/priorities) ou {id: name}
    (activities). On détecte le sens par le type de la valeur.
    """
    live_items = live[section]
    for k, v in (ref_map or {}).items():
        if isinstance(v, int):           # {label_norms: id}
            ref_id, exp_name = v, None
            label = k
        else:                            # {id: name}
            ref_id, exp_name = k, v
            label = v
        item = live_items.get(ref_id)
        if item is None:
            drifts.append(_drift(section, ref_id, label, None,
                                 "missing", f"{section} id={ref_id} ({label!r}) absent du live"))
            continue
        if name_check and exp_name is not None and item.get("name") != exp_name:
            drifts.append(_drift(section, ref_id, exp_name, item.get("name"),
                                 "renamed",
                                 f"{section} id={ref_id} : nom {exp_name!r} → {item.get('name')!r}"))


def check_env_consistency(ref, live, drifts):
    """Vérifie que REDMINE_CF_IA_ID (.env) == id du CF 'IA' dans la référence."""
    import os
    env_ia = (os.environ.get("REDMINE_CF_IA_ID") or "").strip()
    ref_cfs = ref.get("custom_fields") or {}
    ia_ids = [cid for cid, spec in ref_cfs.items() if spec.get("name") == "IA"]
    if env_ia.isdigit() and ia_ids and int(env_ia) != ia_ids[0]:
        drifts.append(_drift("env", "REDMINE_CF_IA_ID", ia_ids[0], int(env_ia),
                             "env_mismatch",
                             f".env REDMINE_CF_IA_ID={env_ia} ≠ référence CF IA id={ia_ids[0]}"))


def run_diff(ref, live):
    drifts = []
    check_custom_fields(ref, live, drifts)
    check_id_name_map("issue_statuses", ref.get("statuses"), live, drifts, name_check=False)
    check_id_name_map("trackers", ref.get("trackers"), live, drifts, name_check=False)
    check_id_name_map("issue_priorities", ref.get("priorities"), live, drifts, name_check=False)
    check_id_name_map("time_entry_activities", ref.get("activities"), live, drifts)
    check_env_consistency(ref, live, drifts)
    return drifts


# ── Dump (squelette de référence depuis le live) ─────────────────────────────

def dump_live(live):
    """Émet un squelette YAML de toute la config live (aide à régénérer la réf)."""
    lines = ["# Squelette généré depuis le live par redmine-config-check.py --dump",
             "# À filtrer : ne garder que les éléments réellement bindés.", ""]
    cf = live["custom_fields"]
    lines.append("custom_fields:")
    for cid in sorted(cf):
        it = cf[cid]
        lines.append(f"  {cid}: {{name: {it.get('name')!r}, format: {it.get('field_format')}, "
                     f"on: {it.get('customized_type')}}}")
    for section, header in [("issue_statuses", "statuses_live"),
                            ("trackers", "trackers_live"),
                            ("issue_priorities", "priorities_live"),
                            ("time_entry_activities", "activities_live")]:
        items = live[section]
        lines.append(f"{header}:")
        for iid in sorted(items):
            lines.append(f"  {iid}: {items[iid].get('name')!r}")
    return "\n".join(lines) + "\n"


# ── Rapport ──────────────────────────────────────────────────────────────────

def print_report(drifts, quiet=False):
    if not drifts:
        if not quiet:
            print("✓ Config Redmine conforme à redmine.reference.yml (aucun drift).")
        return
    print(f"✗ {len(drifts)} drift(s) détecté(s) vs redmine.reference.yml :\n")
    by_section = {}
    for d in drifts:
        by_section.setdefault(d["section"], []).append(d)
    for section, items in by_section.items():
        print(f"  [{section}]")
        for d in items:
            print(f"    · {d['kind']:<14} {d['detail']}")
        print()
    print("→ Corriger redmine.reference.yml et les constantes liées "
          "(redmine-post-note.py, pm-task-add.py, knowledge/redmine/api.md).")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="Sortie machine (liste de drifts)")
    ap.add_argument("--dump", action="store_true",
                    help="Émet un squelette de référence depuis le live, puis sort")
    ap.add_argument("--quiet", action="store_true",
                    help="N'affiche rien si conforme (utile en pré-vol)")
    args = ap.parse_args()

    _load_env_file(PM_DIR / ".env")
    live = fetch_live()

    if args.dump:
        sys.stdout.write(dump_live(live))
        return

    ref = load_reference()
    drifts = run_diff(ref, live)

    if args.json:
        print(json.dumps({"drift_count": len(drifts), "drifts": drifts},
                         ensure_ascii=False, indent=2))
    else:
        print_report(drifts, quiet=args.quiet)

    sys.exit(1 if drifts else 0)


if __name__ == "__main__":
    main()
