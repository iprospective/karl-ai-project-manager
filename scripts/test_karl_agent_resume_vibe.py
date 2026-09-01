#!/usr/bin/env python3
"""Tests RM2547 — reprise des sessions Mistral Vibe.

Lancer : python3 scripts/test_karl_agent_resume_vibe.py
Aucun tmux, aucun réseau : arborescence de sessions simulée en tmpdir.

RM2539 avait laissé vibe hors périmètre (moteur non installé). Il l'est depuis
le 2026-08-05 (v2.23.3) et sait reprendre (`vibe --resume <id>`). Particularité
qui justifie ces tests : vibe émet des **UUID, comme claude** — la forme de
l'identifiant ne distingue donc PAS les deux moteurs, et rien ne doit se
confondre. Le dossier de session ne porte que les 8 premiers hexa de l'id : un
filtre, jamais une preuve.
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


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


TMP = pathlib.Path(tempfile.mkdtemp())
SESSIONS = TMP / "vibe-sessions"
SESSIONS.mkdir()
ka.VIBE_SESSIONS = SESSIONS

UUID_VIBE = "f1c6fe5a-2dfc-070c-218d-e999a488b246"
UUID_AUTRE = "f1c6fe5a-9999-0000-1111-222233334444"   # MÊME préfixe, autre session


def _session_dir(name, session_id, title, cwd, end="2026-06-11T18:38:06.944062+00:00"):
    d = SESSIONS / name
    d.mkdir()
    (d / "meta.json").write_text(json.dumps({
        "session_id": session_id, "title": title,
        "start_time": "2026-06-11T18:37:48.953039+00:00", "end_time": end,
        "environment": {"working_directory": cwd},
    }), encoding="utf-8")
    return d


_session_dir("session_20260611_183748_f1c6fe5a", UUID_VIBE,
             "[WIP] Point sur RM1920", "/zfs/workspaces/ai/project-management")

# — contrat —
check("RM2547 : vibe déclare sa reprise (--resume) et son store",
      (ka._resume_support("vibe") or {}).get("resume_flag") == "--resume"
      and ka._resume_support("vibe")["store"] == "vibe_files")

# — métadonnées lues dans meta.json —
meta = ka._vibe_session_meta(UUID_VIBE)
check("RM2547 : titre et dossier lus dans meta.json",
      meta["title"] == "[WIP] Point sur RM1920"
      and meta["cwd"] == "/zfs/workspaces/ai/project-management")
check("RM2547 : date de fin convertie en epoch", isinstance(meta["mtime"], int) and meta["mtime"] > 0)
check("RM2547 : session inconnue → rien", ka._vibe_session_meta("aaaaaaaa-0000-0000-0000-000000000000") == {})

# — le préfixe du dossier ne fait pas foi —
_session_dir("session_20260612_090000_f1c6fe5a", UUID_AUTRE,
             "Autre session, même préfixe", "/zfs/ailleurs")
check("RM2547 : deux sessions de même préfixe restent distinctes",
      ka._vibe_session_meta(UUID_VIBE)["cwd"] == "/zfs/workspaces/ai/project-management"
      and ka._vibe_session_meta(UUID_AUTRE)["cwd"] == "/zfs/ailleurs")
d = _session_dir("session_20260613_090000_deadbeef", "deadbeef-0000-0000-0000-000000000000",
                 "Dossier menteur", "/zfs/x")
(d / "meta.json").write_text(json.dumps({"session_id": "autre-chose"}), encoding="utf-8")
check("RM2547 : un meta.json qui ne confirme pas l'id est écarté",
      ka._vibe_session_meta("deadbeef-0000-0000-0000-000000000000") == {})

# — pas de confusion claude / vibe sur un UUID de même forme —
ka._DONE_CACHE.update({"at": 0.0, "map": {}})
info = ka._transcript_info(UUID_VIBE, "vibe")
check("RM2547 : avec le moteur, les méta viennent du store de vibe",
      info.get("title") == "Point sur RM1920" and info.get("mark") == "wip")
ka._transcript_jsonl = lambda sid: None          # aucun transcript claude
check("RM2547 : le même UUID lu en claude ne rend rien (pas d'emprunt de méta)",
      ka._transcript_info(UUID_VIBE, "claude") == {})
check("RM2547 : et le cache ne confond pas les deux (clé moteur+id)",
      ka._transcript_info(UUID_VIBE, "vibe").get("title") == "Point sur RM1920")

# — reprise réelle : commande vibe, cwd de meta.json —
STARTED = []
ka._has_session = lambda sid: False
ka._start_session_tmux = lambda sid, cmd, cwd, w, h, extra: STARTED.append((sid, cmd, str(cwd)))
ka._record_run = lambda *a, **k: None
ka._record_key = lambda *a, **k: None
ka._auto_join_current_set = lambda sid, ctx=None: None
ka._resolve_cwd = lambda cwd: pathlib.Path(cwd or "/")
ka._runs_by_session = lambda: {}
ka.SESS_DIR = TMP / "sessions"
(ka.SESS_DIR / "vibe").mkdir(parents=True, exist_ok=True)
ka._write_json_atomic(ka.SESS_DIR / "vibe" / f"{UUID_VIBE}.json",
                      {"engine": "vibe", "session_id": UUID_VIBE,
                       "cwd": "/zfs/workspaces/ai/project-management"})

check("RM2547 : le store par session lève l'ambiguïté d'UUID",
      ka._engine_of_session(UUID_VIBE) == "vibe")

r = ka.op_resume({"session_id": UUID_VIBE, "engine": "vibe", "rm_id": "2410"}, {"user": None})
check("RM2547 : une session vibe se reprend", r["resumed"] is True and r["engine"] == "vibe")
check("RM2547 : la commande est celle de vibe, avec l'id (jamais le sélecteur interactif)",
      STARTED and "--resume" in STARTED[-1][1] and UUID_VIBE in STARTED[-1][1]
      and "vibe" in STARTED[-1][1])
check("RM2547 : le dossier vient de meta.json",
      STARTED[-1][2] == "/zfs/workspaces/ai/project-management")

# conversation absente : refus motivé, moteur nommé
try:
    ka.op_resume({"session_id": "bbbbbbbb-1111-2222-3333-444444444444", "engine": "vibe",
                  "rm_id": "2410"}, {"user": None})
    check("RM2547 : session vibe absente → refus motivé", False)
except ka.ApiError as e:
    check("RM2547 : session vibe absente → refus motivé (410, moteur nommé)",
          e.code == 410 and "vibe" in e.msg)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests reprise vibe RM2547 passent")
