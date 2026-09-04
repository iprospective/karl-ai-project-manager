#!/usr/bin/env python3
"""Tests RM2949 — les tuiles grises ne promettent plus une session introuvable.

Le panneau « ▶ en cours », vue par client, affichait des dizaines de sessions
éteintes annoncées « conversation mémorisée » : le clic partait en /resume et
finissait en « relance impossible ». Deux causes, deux garanties ici :

  - `resumable` ne valait que « un identifiant de conversation est mémorisé »,
    jamais « la conversation EXISTE encore ». Un transcript purgé laissait la
    tuile promettre une reprise que le serveur refuse (410). On protège donc
    l'ÉQUIVALENCE : `_is_resumable` est vrai si et seulement si `op_resume`
    accepterait de reprendre ;
  - une session dont le TICKET est fermé restait listée indéfiniment (seul le
    marqueur `[DONE]`, posé à la main, l'écartait) — d'où le volume. Elle sort
    de la vue, sauf si elle TOURNE : on n'escamote jamais un processus vivant.

Lancer : python3 scripts/test_karl_agent_ghosts.py
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


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


TMP = pathlib.Path(tempfile.mkdtemp())

# — un vrai store de transcripts claude : c'est LA source que /resume consulte —
STORE = TMP / "claude" / "projet"
STORE.mkdir(parents=True)
ka.CLAUDE_STORES = [TMP / "claude"]

SID = {n: f"aaaa1111-2222-3333-4444-55556666{n}" for n in
       ("9401", "9402", "9403", "9404", "9405")}
for n in ("9401", "9403", "9405"):          # 9402 et 9404 : conversation purgée
    (STORE / f"{SID[n]}.jsonl").write_text(
        '{"type":"user","cwd":"/zfs/ws/pm","timestamp":"2026-09-01T10:00:00Z"}\n',
        encoding="utf-8")

# — un vrai arbre PM : deux fiches fermées, deux ouvertes —
ka.PROJECTS_BASE = TMP / "projects" / "clients"
TASKS = ka.PROJECTS_BASE / "iprospective" / "projects" / "pm-ai-agents" / "tasks"
TASKS.mkdir(parents=True)
for rm, status in (("9401", "en_cours"), ("9402", "a_faire"),
                   ("9403", "ferme"), ("9405", "ferme")):
    (TASKS / f"RM{rm}_x.md").write_text(
        f"---\ntitle: tâche {rm}\nstatus: {status}\n---\n\ncorps\n", encoding="utf-8")
    (TASKS / f"RM{rm}_x.log.md").write_text("# Journal\n", encoding="utf-8")

CWD_OK = str(TMP)                 # dossier qui existe : un spawn neuf reste possible
KEYS = {
    "9401": {"engine": "claude", "session_id": SID["9401"], "cwd": CWD_OK, "model": None},
    "9402": {"engine": "claude", "session_id": SID["9402"], "cwd": CWD_OK, "model": None},
    "9403": {"engine": "claude", "session_id": SID["9403"], "cwd": CWD_OK, "model": None},
    "9404": {"engine": "claude", "session_id": SID["9404"], "cwd": None, "model": None},
    "9405": {"engine": "claude", "session_id": SID["9405"], "cwd": CWD_OK, "model": None},
}
LIVE = {}
ka._all_keys = lambda: list(KEYS.items())
ka._list_sessions = lambda: [{"rm_id": sid} for sid in LIVE]
ka._key_info = lambda sid: KEYS.get(sid)
ka._pm_project_of_cwd = lambda cwd: (("iprospective", "pm-ai-agents")
                                     if cwd and cwd.startswith(str(TMP)) else (None, None))


def frais():
    """Vide les caches à TTL — le test crée et supprime des fichiers."""
    ka._DONE_CACHE.update({"at": 0.0, "map": {}})
    ka._tail_cache.clear()
    ka._closed_cache.update({"at": 0.0, "ids": frozenset()})


# ── 1. `resumable` dit la VÉRITÉ (et la même que /resume) ────────────────────
frais()
check("conversation présente → relançable", ka._is_resumable("claude", SID["9401"]) is True)
check("conversation purgée → NON relançable (le bug : un sid mémorisé suffisait)",
      ka._is_resumable("claude", SID["9402"]) is False)
check("aucun identifiant de conversation → non relançable",
      ka._is_resumable("claude", None) is False)
check("moteur sans reprise (shell) → non relançable",
      ka._is_resumable("shell", SID["9401"]) is False)

# l'équivalence avec /resume : ce que la tuile promet, le serveur le tient
ka._has_session = lambda sid: False
try:
    ka.op_resume({"session_id": SID["9402"], "rm_id": "9402"}, {"user": None})
    check("op_resume refuse ce que `_is_resumable` dit perdu (410)", False)
except ka.ApiError as e:
    check("op_resume refuse ce que `_is_resumable` dit perdu (410)",
          e.code == 410 and "introuvable" in e.msg, f"{e.code} {e.msg}")

# ── 2. le contenu d'une vue client : ce qu'on peut encore faire ──────────────
frais()
vue = {e["sid"] for e in ka._derived_entries({"client": "iprospective"})}
check("le ticket FERMÉ sort de la vue (le volume vient de là)", "9403" not in vue, sorted(vue))
check("une session sans conversation NI dossier mémorisé n'a plus de tuile",
      "9404" not in vue, sorted(vue))
check("la session d'un ticket ouvert reste listée", "9401" in vue)
check("conversation perdue mais dossier connu : on la garde (session neuve possible)",
      "9402" in vue)

LIVE["9403"] = KEYS["9403"]        # le ticket est clos, mais la session TOURNE
frais()
vue = {e["sid"] for e in ka._derived_entries({"client": "iprospective"})}
check("une session VIVANTE reste listée même ticket fermé (on n'escamote pas un processus)",
      "9403" in vue)
LIVE.clear()

# ── 3. ce que la tuile grise annonce ─────────────────────────────────────────
frais()
ka.SESSION_SET_FILE = TMP / "session-set.json"
ka._session_set_load = lambda: {"version": 1, "users": {}}
ka._current_view = lambda user, store=None: "client:iprospective"
gh = {g["rm_id"]: g for g in ka._ghost_sessions({"user": None})}
check("vue client : les tuiles grises sont celles de la vue", set(gh) == {"9401", "9402"},
      sorted(gh))
check("tuile d'une conversation vivante : « conversation mémorisée »",
      gh["9401"]["resumable"] is True)
check("tuile d'une conversation purgée : annoncée PERDUE",
      gh["9402"]["resumable"] is False)

# ── 4. le coût annoncé d'un « tout relancer » compte les mêmes perdues ───────
frais()
rec = {"saved_at": 1, "entries": [
    {"sid": "9401", "engine": "claude", "session_id": SID["9401"], "cwd": CWD_OK},
    {"sid": "9402", "engine": "claude", "session_id": SID["9402"], "cwd": CWD_OK},
]}
ka._session_set_get = lambda store, user, group: rec
est = ka.op_session_set_estimate({"group": "default"}, {"user": None})
check("estimation : une seule est relançable, l'autre est comptée perdue",
      est["relaunchable"] == 1 and est["lost"] == 1, est)

# les entrées rendues à l'UI portent le même verdict (panneau 🚀 sessions)
g = ka.op_session_set_get({"group": "default"}, {"user": None})
byid = {e["sid"]: e for e in g["entries"]}
check("chaque entrée d'un jeu porte `resumable` (🟡 reprenable vs 🔴 perdue)",
      byid["9401"].get("resumable") is True and byid["9402"].get("resumable") is False,
      byid)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests fantômes RM2949 passent")
