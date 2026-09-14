#!/usr/bin/env python3
"""Tests RM3059 — pm-wiki-sync : la page index `Wiki` doit exister même quand le projet
n'est synchronisé qu'aspect par aspect (`pm-task-doc --sync` → `--aspect <slug>`).

Lancer : python3 scripts/test_pm_wiki_sync_index.py
"""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_wiki_sync", SCRIPTS / "pm-wiki-sync.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


A = SimpleNamespace(aspect="migration-sf7-cdc", pull_only=False, project_desc_only=False)
check("index régénéré en sync ciblé --aspect", m.index_wanted(True, A))
check("index régénéré en sync complet", m.index_wanted(True, SimpleNamespace(aspect=None, pull_only=False)))
check("pas d'index en pull-only", not m.index_wanted(True, SimpleNamespace(aspect=None, pull_only=True)))
check("pas d'index sans aspects (description projet seule)", not m.index_wanted(False, A))

aspects = [{"wiki_title": "Migration-sf7-cdc", "title": "CDC — Migration", "slug": "migration-sf7-cdc"},
           {"wiki_title": "Orm-fusion-matrice-chaines", "title": "", "slug": "orm-fusion-matrice-chaines"}]
body = m.build_index_body("Matnat ERP old", aspects, "abc1234")
check("index : un lien wiki par aspect", body.count("[[") == 2 and "[[Migration-sf7-cdc|CDC — Migration]]" in body, body)
check("index : slug en libellé quand pas de titre", "[[Orm-fusion-matrice-chaines|orm-fusion-matrice-chaines]]" in body, body)
check("index : nom du projet en H1", "# Matnat ERP old" in body, body)

if fails:
    sys.exit("ÉCHEC — " + ", ".join(fails))
print("\nOK — pm-wiki-sync : index en sync par aspect (RM3059)")
