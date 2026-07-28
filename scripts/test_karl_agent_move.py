#!/usr/bin/env python3
"""Tests RM2418 — déplacer une session vers un autre projet + robustesse resume.

Unitaire (sans tmux ni réseau) : _slug_of, op_move_session (3 ancrages, garde
session vivante, résolution {client,project}→workspace, 404) et _resume_cwd
(préférence à l'emplacement RÉEL du transcript). Le module se configure via des
variables d'env (HOME/stores/racines) AVANT import.

Lancer : python3 scripts/test_karl_agent_move.py
"""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SB = pathlib.Path(tempfile.mkdtemp())
os.environ["HOME"] = str(SB)
PROJ = SB / ".claude" / "projects"
PROJ.mkdir(parents=True)
os.environ["KARL_AGENT_ALLOWED_ROOTS"] = str(SB)
os.environ["KARL_AGENT_CLAUDE_STORES"] = str(PROJ)
os.environ["KARL_AGENT_STATE_DIR"] = str(SB / ".local/state/karl-agent")

spec = importlib.util.spec_from_file_location("karl_agent_move", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent_move"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def mkdir(p):
    pathlib.Path(p).mkdir(parents=True, exist_ok=True)
    return str(p)


def seed_transcript(sid, cwd):
    d = PROJ / ka._slug_of(cwd)
    d.mkdir(parents=True, exist_ok=True)
    jf = d / f"{sid}.jsonl"
    jf.write_text("\n".join([
        json.dumps({"type": "summary", "cwd": cwd}),
        json.dumps({"type": "custom-title", "customTitle": "[WIP] démo"}),
        json.dumps({"type": "user", "cwd": cwd}),
    ]) + "\n")
    return jf


def seed_store(sid, cwd, engine="claude"):
    sf = ka.SESS_DIR / engine / f"{sid}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps({"engine": engine, "session_id": sid, "cwd": cwd}))
    return sf


# — _slug_of —
check("_slug_of : '/' et '.' → '-'",
      ka._slug_of("/zfs/workspaces/calicote/prestashop")
      == "-zfs-workspaces-calicote-prestashop")

# — op_move_session : 3 ancrages via to_cwd explicite —
ka._session_live = lambda sid, eng="claude": False
ka._runs_by_session = lambda: {}
SID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
old = mkdir(SB / "pisceen" / "dolibarr")
new = mkdir(SB / "calicote" / "prestashop")
jf = seed_transcript(SID, old)
sf = seed_store(SID, old)
res = ka.op_move_session({"session_id": SID, "to_cwd": new})
new_jf = PROJ / ka._slug_of(new) / f"{SID}.jsonl"
check("move : moved=True + cwd cible", res.get("moved") and res["cwd"] == new)
check("move : transcript déplacé (ancien retiré)", new_jf.exists() and not jf.exists())
check("move : pas de doublon du sid", list(PROJ.glob(f"*/{SID}.jsonl")) == [new_jf])
txt = new_jf.read_text()
check("move : cwd internes réécrits", old not in txt and new in txt)
check("move : store per-session réécrit", json.loads(sf.read_text())["cwd"] == new)

# — _resume_cwd : store périmé, transcript à jour → préfère le transcript —
seed_store(SID, old)  # store repointe l'ancien projet (bug RM2391)
check("_resume_cwd préfère l'emplacement réel du transcript",
      ka._resume_cwd(new_jf, "claude", SID) == new)

# — garde session vivante → 409 —
ka._session_live = lambda sid, eng="claude": True
try:
    ka.op_move_session({"session_id": SID, "to_cwd": old})
    check("garde session vivante → 409", False)
except ka.ApiError as e:
    check("garde session vivante → 409", e.code == 409)
ka._session_live = lambda sid, eng="claude": False

# — résolution {client, project} → workspace —
SID2 = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
seed_transcript(SID2, mkdir(SB / "x" / "old2"))
ka.PROJECTS_BASE = SB / "pm"
pdir = SB / "pm" / "calicote" / "projects" / "prestashop"
pdir.mkdir(parents=True)
ka._resolve_workspace = lambda d: pathlib.Path(new) if d == pdir else None
r2 = ka.op_move_session({"session_id": SID2, "client": "calicote", "project": "prestashop"})
check("résolution {client,project} → workspace", r2["cwd"] == new)
try:
    ka.op_move_session({"session_id": SID2, "client": "nope", "project": "nope"})
    check("projet inconnu → 404", False)
except ka.ApiError as e:
    check("projet inconnu → 404", e.code == 404)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests déplacement de session RM2418 passent")
