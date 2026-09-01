#!/usr/bin/env python3
"""Tests RM2396 — le badge « tmux vivant » du panneau de reprise (op_resumable).

Reproduction du bug : une session reprise/ancrée sur un SLUG (sans jonction
ticket) tourne bien dans un tmux karl-<slug>, mais op_resumable calculait `live`
uniquement via les jonctions ticket → la session n'était jamais marquée vivante,
poussant l'humain à la reprendre une seconde fois. Correctif : match direct par
session_id via l'index clé-tmux (RM2144), écrit à chaque spawn ET resume.

Unitaire (sans tmux ni réseau) : op_resumable sur un store claude fabriqué, avec
_list_sessions / _key_info / _runs_by_session monkeypatchés.
Lancer : python3 scripts/test_karl_agent_resumable_live.py
"""
import importlib.util
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# — Store claude fabriqué : un transcript par session, avec un cwd hors PM —
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2396-"))
store = tmp / "projstore"
store.mkdir(parents=True)
SID_SLUG = "aaaaaaaa-1111-2222-3333-444444444444"   # session ancrée sur slug
SID_TICK = "bbbbbbbb-1111-2222-3333-555555555555"   # session d'un ticket
SID_DEAD = "cccccccc-1111-2222-3333-666666666666"   # session sans tmux vivant
for sid in (SID_SLUG, SID_TICK, SID_DEAD):
    (store / f"{sid}.jsonl").write_text(
        '{"type":"user","cwd":"/tmp","message":{"content":"go"}}\n', encoding="utf-8")
ka.CLAUDE_STORES = [tmp]
# RM2539 : la découverte n'est plus claude-only — `op_resumable` énumère aussi
# les conversations opencode et vibe. Ce test porte sur le marquage « tmux
# vivant » ; on isole donc les stores tiers, sinon les VRAIES sessions de la
# machine entreraient dans le résultat et le rendraient non reproductible.
ka.OPENCODE_DB = tmp / "aucune-base-opencode.db"
ka.VIBE_SESSIONS = tmp / "aucun-dossier-vibe"

# tmux vivants : un slug (karl-ma-session) + un ticket (karl-RM4242). Pas de tmux
# pour SID_DEAD.
ka._list_sessions = lambda: [
    {"rm_id": "ma-session", "is_ticket": False, "tmux": "karl-ma-session"},
    {"rm_id": "4242", "is_ticket": True, "tmux": "karl-RM4242"},
]
# Index clé-tmux : rm_id (clé de nommage tmux) → session_id réellement servi.
_KEYS = {"ma-session": SID_SLUG, "4242": SID_TICK}
ka._key_info = lambda rm_id: ({"engine": "claude", "session_id": _KEYS[rm_id]}
                              if rm_id in _KEYS else None)
# Jonctions ticket : SEULEMENT le ticket (le slug n'en a pas — c'est le cœur du bug).
ka._runs_by_session = lambda: {
    SID_TICK: [{"rm_id": "4242", "n": 1, "client": "iprospective", "project": "pm-ai-agents",
                "session_id": SID_TICK, "_file": "x"}],
}
ka._pm_project_of_cwd = lambda cwd: (None, None)

res = {e["session_id"]: e for e in ka.op_resumable({})}

check("les 3 sessions sont listées", set(res) == {SID_SLUG, SID_TICK, SID_DEAD})
# Le bug RM2396 : cette assertion échouait (live=False) avant le correctif.
check("session ancrée sur slug + tmux vivant → live=True (RM2396)",
      res[SID_SLUG]["live"] is True)
check("session ticket + tmux vivant → live=True (non-régression jonction)",
      res[SID_TICK]["live"] is True)
check("session sans tmux vivant → live=False",
      res[SID_DEAD]["live"] is False)

# — Non-régression : une jonction ticket dont le tmux est vivant marque live même
#   si l'index clé-tmux pointe un AUTRE session_id (re-spawn) — via live_rm/runs.
ka._key_info = lambda rm_id: ({"engine": "claude", "session_id": "zzzzzzzz-0000-0000-0000-000000000000"}
                              if rm_id == "4242" else None)
res2 = {e["session_id"]: e for e in ka.op_resumable({})}
check("jonction ticket vivante marque live même si clé-tmux pointe un autre sid",
      res2[SID_TICK]["live"] is True)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests badge « tmux vivant » du panneau de reprise RM2396 passent")
