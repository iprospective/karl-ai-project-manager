#!/usr/bin/env python3
"""pm_reporting — ledger annexe des données de reporting d'un ticket (RM2366, CDC RM2316 § S5).

Problème : `reporting.time_entries[]`, `reporting.notes[]` et `status_history[]`
croissent sans borne dans le frontmatter (1 entrée/commit) et sont relus à
CHAQUE lecture du MD. Solution : un fichier annexe par ticket,
`<stem>.reporting.yml` (à côté du MD, mêmes commits), qui porte l'historique ;
le frontmatter garde les cumuls + la QUEUE de `status_history` (le validateur
exige que la dernière entrée corresponde au statut courant).

Rétrocompat (2 formats, lecture fusionnée) :
- lecture : `load()` fusionne ledger + blocs frontmatter résiduels (writers non
  migrés continuent d'appender au frontmatter ; `pm-reporting-migrate` re-balaye) ;
- dédup : les clés (`key` des time_entries/notes) restent la référence.
"""
import re
from pathlib import Path

try:
    import yaml
except ImportError:  # laissé au script appelant
    yaml = None

SCHEMA_VERSION = 1
KEYS = ("time_entries", "notes", "status_history")


def ledger_path(md_path):
    md_path = Path(md_path)
    return md_path.parent / (md_path.name[:-3] + ".reporting.yml")


def load_ledger(md_path):
    p = ledger_path(md_path)
    if not p.is_file():
        return {"schema_version": SCHEMA_VERSION, **{k: [] for k in KEYS}}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    for k in KEYS:
        data.setdefault(k, [])
    data.setdefault("schema_version", SCHEMA_VERSION)
    return data


def save_ledger(md_path, data):
    p = ledger_path(md_path)
    p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False,
                                default_flow_style=False), encoding="utf-8")
    return p


def merged(fm, md_path):
    """Vue fusionnée ledger + frontmatter (lecture rétrocompatible).

    Retourne {key: liste} — ledger d'abord, puis les entrées frontmatter dont la
    clé n'y est pas déjà (time_entries/notes : champ `key` ; status_history :
    tuple (status, at))."""
    led = load_ledger(md_path)
    rep = fm.get("reporting") or {}
    res = {}
    for k in ("time_entries", "notes"):
        seen = {e.get("key") for e in led[k] if isinstance(e, dict)}
        res[k] = led[k] + [e for e in (rep.get(k) or [])
                           if isinstance(e, dict) and e.get("key") not in seen]
    seen_sh = {(e.get("status"), str(e.get("at"))) for e in led["status_history"]
               if isinstance(e, dict)}
    res["status_history"] = led["status_history"] + [
        e for e in (fm.get("status_history") or [])
        if isinstance(e, dict) and (e.get("status"), str(e.get("at"))) not in seen_sh]
    return res


def sweep(fm, md_path, keep_history_tail=1):
    """Migre les blocs frontmatter vers le ledger (idempotent).

    Modifie `fm` EN PLACE (le MD reste à écrire par l'appelant) et écrit le
    ledger. Retourne (n_moved, ledger_file) — n_moved = entrées déplacées."""
    led = load_ledger(md_path)
    rep = fm.get("reporting") or {}
    moved = 0
    for k in ("time_entries", "notes"):
        seen = {e.get("key") for e in led[k] if isinstance(e, dict)}
        for e in (rep.get(k) or []):
            if isinstance(e, dict) and e.get("key") not in seen:
                led[k].append(e)
                seen.add(e.get("key"))
                moved += 1
        rep[k] = []
    seen_sh = {(e.get("status"), str(e.get("at"))) for e in led["status_history"]
               if isinstance(e, dict)}
    hist = fm.get("status_history") or []
    for e in hist:
        if isinstance(e, dict) and (e.get("status"), str(e.get("at"))) not in seen_sh:
            led["status_history"].append(e)
            seen_sh.add((e.get("status"), str(e.get("at"))))
            moved += 1
    if hist:
        fm["status_history"] = hist[-keep_history_tail:]
    rep["ledger"] = ledger_path(md_path).name
    fm["reporting"] = rep
    p = save_ledger(md_path, led)
    return moved, p
