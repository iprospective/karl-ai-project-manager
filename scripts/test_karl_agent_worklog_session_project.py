#!/usr/bin/env python3
"""Tests RM2852 — le worklog dit DE QUEL PROJET est la session.

Le cockpit range les groupes du worklog par proximité (projet de la session, puis
même client, puis le reste) : le tri est une fonction pure côté front, mais il lui
faut ce repère, et le worklog ne le portait pas. Un worklog servi sans `client` /
`project` dégrade vers l'ordre d'avant — c'est le cas « session sans projet résolu »
du ticket, et c'est pourquoi les deux formes (trouvé / pas de worklog) sont testées.

Lancer : python3 scripts/test_karl_agent_worklog_session_project.py
"""
import importlib.util
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def _prep(tmp, *, fiche=True, worklog=True):
    """Neutralise ce qui touche au système ; rend le dossier des worklogs."""
    tasks = tmp / "clients" / "abatik" / "projects" / "infra" / "tasks"
    tasks.mkdir(parents=True)
    if fiche:
        (tasks / "RM2852_x.md").write_text("---\nredmine_id: 2852\n---\n\n## Contexte\n", encoding="utf-8")
    wl = tmp / "worklogs"
    wl.mkdir()
    if worklog:
        (wl / "sess-1.json").write_text(json.dumps(
            {"title": "t", "updated": "2026-09-20", "items": [], "mrs": []}), encoding="utf-8")
    ka.PROJECTS_BASE = tmp / "clients"   # base = le dossier des clients (cf. _TASK_GLOB)
    ka.WORKLOG_DIR = wl
    ka._has_session = lambda rm: True
    ka._key_info = lambda rm: {"session_id": "sess-1"}
    ka._worklog_reconcile_mrs = lambda *a, **k: None
    ka._worklog_live_map = lambda *a, **k: ({}, 0)
    ka._integration_branch = lambda: "dev"
    ka._closed_cache = {"at": 0.0, "ids": frozenset()}


with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    _prep(tmp)
    out = ka.op_worklog("2852")
    check("le worklog porte le client et le projet de la session",
          out.get("client") == "abatik" and out.get("project") == "infra",
          f"{out.get('client')!r}/{out.get('project')!r}")
    check("le reste de la charge est intact", out.get("found") is True and "buckets" in out)

with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    _prep(tmp, worklog=False)
    out = ka.op_worklog("2852")
    check("sans worklog : la charge vide porte quand même le projet (found=False)",
          out.get("found") is False and out.get("client") == "abatik" and out.get("project") == "infra")

with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    _prep(tmp, fiche=False)
    out = ka.op_worklog("2852")
    check("fiche introuvable : champs vides, pas d'exception — le front dégrade vers l'ordre d'avant",
          out.get("client") == "" and out.get("project") == "" and out.get("found") is True)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — le worklog sert le projet de la session (RM2852)")
