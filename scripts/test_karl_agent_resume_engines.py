#!/usr/bin/env python3
"""Tests RM2539 — reprise MULTI-MOTEUR (parité resume avec le lancement).

Lancer : python3 scripts/test_karl_agent_resume_engines.py
Aucun tmux, aucun réseau : le démarrage de session est simulé.

La reprise était codée en dur sur claude — `--resume <uuid>` + transcripts
JSONL, et un filtre d'id unique (UUID) qui rejetait toute session opencode bien
avant le routage. Couvre : le contrat de reprise par moteur, la grammaire d'id
propre au moteur, la reprise opencode (commande + métadonnées lues en base), le
refus explicite d'un moteur sans reprise, et la non-régression de claude.
"""
import importlib.util
import pathlib
import sqlite3
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


TMP = pathlib.Path(tempfile.mkdtemp())
UUID_CLAUDE = "aaaa1111-2222-3333-4444-555566667777"
SID_OPENCODE = "ses_14301a3ddffebeMP5Am13rdwG6"

# — contrat de reprise : déclaré, ou explicitement absent —
check("RM2539 : claude déclare son contrat de reprise",
      (ka._resume_support("claude") or {}).get("resume_flag") == "--resume")
check("RM2539 : opencode aussi (--session, vérifié sur v1.18.13)",
      (ka._resume_support("opencode") or {}).get("resume_flag") == "--session")
check("RM2539 : vibe et shell n'en déclarent pas (refus, pas plantage)",
      ka._resume_support("vibe") is None and ka._resume_support("shell") is None)
check("RM2539 : moteur inconnu → pas de contrat", ka._resume_support("zzz") is None)

# — grammaire des identifiants : elle appartient au moteur —
check("RM2539 : un UUID est valide pour claude, pas pour opencode",
      ka._valid_session_id(UUID_CLAUDE, "claude")
      and not ka._valid_session_id(UUID_CLAUDE, "opencode"))
check("RM2539 : un id `ses_…` est valide pour opencode, pas pour claude",
      ka._valid_session_id(SID_OPENCODE, "opencode")
      and not ka._valid_session_id(SID_OPENCODE, "claude"))
check("RM2539 : sans moteur précisé, les deux formes passent (le moteur réel tranchera)",
      ka._valid_session_id(SID_OPENCODE) and ka._valid_session_id(UUID_CLAUDE))
check("RM2539 : une saisie qui n'est d'aucun moteur est refusée",
      not ka._valid_session_id("../etc/passwd") and not ka._valid_session_id(""))

# — métadonnées opencode : lues dans SA base, pas dans un transcript —
DB = TMP / "opencode.db"
con = sqlite3.connect(DB)
con.execute("CREATE TABLE session (id TEXT, project_id TEXT, slug TEXT, directory TEXT,"
            " title TEXT, time_created INTEGER, time_updated INTEGER)")
con.execute("INSERT INTO session (id, directory, title, time_created, time_updated)"
            " VALUES (?,?,?,?,?)",
            (SID_OPENCODE, "/zfs/workspaces/matnat/infra", "[WIP] Migration ERP",
             1781287246883, 1781287247166))
con.commit(); con.close()
ka.OPENCODE_DB = DB

meta = ka._opencode_session_meta(SID_OPENCODE)
check("RM2539 : titre, dossier et date lus en base",
      meta["title"] == "[WIP] Migration ERP"
      and meta["cwd"] == "/zfs/workspaces/matnat/infra"
      and meta["mtime"] == 1781287247)          # ms → s
check("RM2539 : session inconnue de la base → rien (jamais d'invention)",
      ka._opencode_session_meta("ses_inexistante") == {})

ka._DONE_CACHE.update({"at": 0.0, "map": {}})
info = ka._transcript_info(SID_OPENCODE)
check("RM2539 : le marqueur [WIP] est lu comme chez claude",
      info.get("mark") == "wip" and info.get("title") == "Migration ERP")
check("RM2539 : l'âge de la session opencode remonte (tuile datée, pas muette)",
      info.get("mtime") == 1781287247)

# — reprise réelle : commande du moteur, cwd de sa base —
STARTED = []
ka._has_session = lambda sid: False
ka._start_session_tmux = lambda sid, cmd, cwd, w, h, extra: STARTED.append((sid, cmd, str(cwd)))
ka._record_run = lambda *a, **k: None
ka._record_key = lambda *a, **k: None
ka._auto_join_current_set = lambda sid, ctx=None: None
ka._resolve_cwd = lambda cwd: pathlib.Path(cwd or "/")
ka._runs_by_session = lambda: {}
ka.SESS_DIR = TMP / "sessions"
(ka.SESS_DIR / "opencode").mkdir(parents=True, exist_ok=True)
ka._write_json_atomic(ka.SESS_DIR / "opencode" / f"{SID_OPENCODE}.json",
                      {"engine": "opencode", "session_id": SID_OPENCODE,
                       "cwd": "/zfs/workspaces/matnat/infra"})

r = ka.op_resume({"session_id": SID_OPENCODE, "engine": "opencode", "rm_id": "2410"},
                 {"user": None})
check("RM2539 : une session opencode se reprend (plus de 501)",
      r["resumed"] is True and r["engine"] == "opencode")
check("RM2539 : la commande est celle du moteur, pas `claude --resume`",
      STARTED and "--session" in STARTED[-1][1] and SID_OPENCODE in STARTED[-1][1]
      and "claude" not in STARTED[-1][1])
check("RM2539 : le dossier de reprise vient de la base du moteur",
      STARTED[-1][2] == "/zfs/workspaces/matnat/infra")

# — refus explicites —
try:
    # session non mémorisée : sans quoi le recoupement RM2536 refuserait d'abord
    # le moteur (409 incohérent) avant d'arriver au contrat de reprise.
    ka.op_resume({"session_id": "ses_inconnueDeToutStore9", "engine": "vibe",
                  "rm_id": "2410"}, {"user": None})
    check("RM2539 : moteur sans reprise → refus explicite", False)
except ka.ApiError as e:
    check("RM2539 : moteur sans reprise → refus explicite (501 + moteurs capables)",
          e.code == 501 and "claude" in e.msg and "opencode" in e.msg)

try:
    ka.op_resume({"session_id": UUID_CLAUDE, "engine": "opencode"}, {"user": None})
    check("RM2539 : id d'un autre moteur → refus", False)
except ka.ApiError as e:
    check("RM2539 : id d'un autre moteur → refus (400, forme attendue)",
          e.code == 400 and "opencode" in e.msg)

# conversation absente de la base : repli spawn, comme un transcript perdu
try:
    ka.op_resume({"session_id": "ses_disparueXXXXXXXX", "engine": "opencode",
                  "rm_id": "2410"}, {"user": None})
    check("RM2539 : conversation absente → refus motivé", False)
except ka.ApiError as e:
    check("RM2539 : conversation absente → refus motivé (410, moteur nommé)",
          e.code == 410 and "opencode" in e.msg)

# — jeu MIXTE : chaque entrée est relancée avec SON moteur —
CALLS = []
ka.op_resume = lambda payload, ctx=None: (CALLS.append((payload.get("rm_id"),
                                                        payload.get("engine")))
                                          or {"resumed": True})
for entry, want in ((({"sid": "2410", "engine": "opencode",
                       "session_id": SID_OPENCODE, "cwd": "/zfs/a"}), "opencode"),
                    (({"sid": "2536", "engine": "claude",
                       "session_id": UUID_CLAUDE, "cwd": "/zfs/b"}), "claude")):
    r = ka._relaunch_entry(entry, allow_spawn=False)
    check(f"RM2539 : entrée {want} relancée avec son moteur",
          r["action"] == "resumed" and CALLS[-1][1] == want)
check("RM2539 : un jeu mixte n'impose donc aucun moteur unique",
      {c[1] for c in CALLS} == {"claude", "opencode"})


if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests reprise multi-moteur RM2539 passent")
