#!/usr/bin/env python3
"""Tests RM2578 — le hook env de session ne sort plus en silence.

Le hook renonçait à créer l'env sans rien dire, et annonçait ses succès avec
`out.info`, qui n'émet QU'EN --verbose. Impossible, dès lors, de distinguer
« le hook n'a pas tourné » de « il a tourné sans rien faire » : un ticket a
conclu au premier alors que rien ne le prouvait.

Lancer : python3 scripts/test_pm_env_session_hook_visible.py
"""
import importlib.util
import io
import contextlib
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("psu", HERE / "pm-task-status-update.py")
psu = importlib.util.module_from_spec(spec)
sys.modules["psu"] = psu
try:
    spec.loader.exec_module(psu)
except SystemExit:
    pass

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def run_hook(meta_yml, make_bare=False):
    """Lance le hook sur un workspace jetable, rend ce qui a été DIT (stdout+stderr)."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = pathlib.Path(tmp) / "ws"
        (ws / ".mmi-pm" / "tasks").mkdir(parents=True)
        (ws / ".mmi-pm" / "meta.yml").write_text(meta_yml, encoding="utf-8")
        if make_bare:
            (ws / "repos" / "demo.git").mkdir(parents=True)
        md = ws / ".mmi-pm" / "tasks" / "RM9999_x.md"
        md.write_text("---\n---\n", encoding="utf-8")
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            psu.env_session_hook(md, "9999", "en_cours", "a_faire")
        return buf_out.getvalue() + buf_err.getvalue()


sans_repos = run_hook("slug: x\n")
check("aucun `repos:` au manifeste → le hook le DIT", "aucun `repos:`" in sans_repos)
check("le message nomme le fichier fautif", "meta.yml" in sans_repos)

sans_bare = run_hook("repos:\n  - name: demo\n")
check("bare absent → le hook le DIT", "bare absent" in sans_bare)
check("le message donne le chemin attendu", "repos/demo.git" in sans_bare)
check("et suggère la piste (layout)", "RM1993" in sans_bare)

sans_name = run_hook("repos:\n  - url: x\n")
check("un `repos:` sans `name` est signalé", "n'a pas de `name`" in sans_name)

multi = run_hook("repos:\n  - name: a\n  - name: b\n")
check("multi-repo : le hook dit quoi lancer à la main",
      "pm-env-session.py create" in multi and "--repo" in multi)

# aucun de ces messages ne doit dépendre de --verbose : ils passent tous par
# `warn`, jamais par `info` (qui n'émet qu'en verbose).
src = (HERE / "pm-task-status-update.py").read_text(encoding="utf-8")
debut = src.index("def env_session_hook")
fin = src.index("def fetch_issue_basic")
corps = src[debut:fin]
check("le hook n'annonce plus rien via `out.info` (invisible par défaut)",
      "out.info(" not in corps)
check("le résultat d'un create/teardown est une ligne d'opération visible",
      'out.op("env-session"' in corps)

# l'opt-out global reste silencieux : c'est un choix assumé, pas une panne
check("opt-out `auto_session: false` : silence assumé, commenté comme tel",
      "opt-out global assumé" in corps)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests visibilité du hook RM2578 passent")
