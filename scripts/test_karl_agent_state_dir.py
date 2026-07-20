#!/usr/bin/env python3
"""Tests RM2385 — séparation état de session (STATE_DIR) vs logs (LOG_DIR).

Unitaire (sans réseau) : les clés/entités session s'écrivent et se relisent
sous STATE_DIR, indépendamment de LOG_DIR, pour qu'une instance de test partage
l'état de session prod sans mélanger ses logs.
Lancer : python3 scripts/test_karl_agent_state_dir.py
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


# — défaut : STATE_DIR = LOG_DIR (invariant I1, prod inchangée) —
check("défaut STATE_DIR = LOG_DIR", str(ka.STATE_DIR) == str(ka.LOG_DIR))

# — STATE_DIR ≠ LOG_DIR : keys/sessions/tasks suivent STATE_DIR, pas LOG_DIR —
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2385-"))
state, log = tmp / "state", tmp / "log"
ka.STATE_DIR = state
ka.LOG_DIR = log
ka.SESS_DIR = state / "sessions"
ka.RUNS_DIR = state / "tasks"

ka._record_key("42", "claude", "sid-abc", "/w/cwd")
check("clé écrite sous STATE_DIR/keys", (state / "keys" / "RM42.json").is_file())
check("clé PAS sous LOG_DIR/keys (logs isolés)", not (log / "keys" / "RM42.json").exists())
check("entité session écrite sous STATE_DIR/sessions",
      (state / "sessions" / "claude" / "sid-abc.json").is_file())

info = ka._key_info("42")
check("_key_info relit depuis STATE_DIR", info and info["session_id"] == "sid-abc")

# — un slug non-ticket passe aussi par STATE_DIR —
ka._record_key("mon-slug", "shell", "sid-shell", "/w")
check("slug non-ticket sous STATE_DIR/keys", (state / "keys" / "mon-slug.json").is_file())
check("_key_info slug", ka._key_info("mon-slug")["engine"] == "shell")

# — LOG_DIR reste le foyer des logs d'instance (inchangé) —
check("session log file sous LOG_DIR", str(ka._log_path("42")).startswith(str(log)))

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests STATE_DIR RM2385 passent")
