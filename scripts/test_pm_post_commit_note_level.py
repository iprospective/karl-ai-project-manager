#!/usr/bin/env python3
"""Tests du niveau de note par commit dans pm-post-commit (RM2409).

Couvre : classification outillage (TOOLING_RE) et résolution du niveau
`commit_note_level` (override projet > config locale > config core > défaut).

Lancer : python3 scripts/test_pm_post_commit_note_level.py
"""
import importlib.util
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_post_commit", str(_HERE / "pm-post-commit.py"))
ppc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ppc)

FAILS = []


def check(label, got, expected):
    if got != expected:
        FAILS.append(f"{label} : {got!r} != attendu {expected!r}")


# ── TOOLING_RE : outillage vs travail ──────────────────────────────────────
for subject, is_tooling in [
    ("pm(desc): RM2267 description/done_ratio", True),
    ("pm(status): RM2409 nouveau -> en_cours", True),
    ("pm(metrics): RM2267 estimation poussée", True),
    ("pm(tmp): stash de session", True),
    ("chore(pm): sync frontmatter", True),
    ("chore: ménage", True),
    ("RM2362 : hotfix shadowing out", False),
    ("feat: RM1234 nouvelle fonction", False),
    ("docs: guide de déploiement RM1234", False),
    ("pm-task-add : fix régression --porcelain", False),   # nom de script ≠ préfixe pm(…)
]:
    check(f"TOOLING_RE {subject!r}", bool(ppc.TOOLING_RE.match(subject)), is_tooling)

# ── _note_level : cascade projet > local > core > défaut ───────────────────
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    core = tmp / "core"
    core.mkdir()
    ws = tmp / "ws"
    (ws / ".mmi-pm").mkdir(parents=True)
    saved_core = ppc.PM_CORE
    ppc.PM_CORE = str(core)
    try:
        # aucun fichier → défaut
        check("défaut", ppc._note_level(ws), "work")
        # config core
        (core / "pm.config.yml").write_text("traceability:\n  commit_note_level: all\n")
        check("config core", ppc._note_level(ws), "all")
        # config locale prime sur core
        (core / "pm.config.local.yml").write_text("traceability:\n  commit_note_level: none\n")
        check("config locale", ppc._note_level(ws), "none")
        # meta.yml projet prime sur tout
        (ws / ".mmi-pm" / "meta.yml").write_text("traceability:\n  commit_note_level: work\n")
        check("override projet", ppc._note_level(ws), "work")
        # valeur invalide → on passe au niveau suivant de la cascade
        (ws / ".mmi-pm" / "meta.yml").write_text("traceability:\n  commit_note_level: bogus\n")
        check("valeur invalide", ppc._note_level(ws), "none")
        # YAML corrompu → best-effort, cascade poursuivie
        (ws / ".mmi-pm" / "meta.yml").write_text(":: pas du yaml [")
        check("yaml corrompu", ppc._note_level(ws), "none")
    finally:
        ppc.PM_CORE = saved_core

if FAILS:
    print("✗ test_pm_post_commit_note_level :")
    for f in FAILS:
        print(f"  - {f}")
    raise SystemExit(1)
print("✓ test_pm_post_commit_note_level : 16 cas OK")
