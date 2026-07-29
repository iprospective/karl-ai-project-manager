#!/usr/bin/env python3
"""Tests RM2395/RM2427 — jeux de sessions enregistrés (store, reprise en idle).

Unitaire (sans tmux ni réseau) : résolution user/group (défauts superadmin/
default), op_session_set_save (instantané), op_session_set_get (relecture +
état alive), préservation d'autostart à l'écrasement, coexistence des groupes
nommés, plafond, et correctif RM1941 (_record_key mémorise/préserve le modèle).

RM2427 — reprise « en idle » : `_ghost_sessions` (entrées enregistrées non
vivantes exposées en fantômes), leur intégration dans `_sessions_view`, la
relance UNITAIRE (`op_session_set_relaunch {sid}`) et l'autostart par défaut
d'un jeu neuf.

RM2439 — la sauvegarde ne DÉTRUIT plus : union au lieu du remplacement (une
tuile grise survit au ré-enregistrement), `sids` comme sélecteur additif, refus
atomique au plafond, et titre de session mémorisé dans l'entrée (un sid nu ne
dit pas de quelle session il s'agit).
Lancer : python3 scripts/test_karl_agent_session_set.py
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


# — store en tmpdir, sessions/clés simulées (pas de tmux) —
TMP = pathlib.Path(tempfile.mkdtemp())
ka.SESSION_SET_FILE = TMP / "session-set.json"

LIVE = {}   # sid → key info (engine, session_id, cwd, model)
ka._list_sessions = lambda: [{"rm_id": sid} for sid in LIVE]
ka._key_info = lambda sid: LIVE.get(sid)

LIVE.update({
    "2395": {"engine": "claude", "session_id": "uuid-2395", "cwd": "/zfs/a", "model": "opus"},
    "worm-x": {"engine": "claude", "session_id": "uuid-worm", "cwd": "/zfs/b", "model": None},
})

# — résolution user/group : défauts superadmin / default —
check("user : auth ouverte (user None) → superadmin", ka._session_set_user({"user": None}) == "superadmin")
check("user : ctx None → superadmin", ka._session_set_user(None) == "superadmin")
check("user : compte nommé normalisé (minuscule)", ka._session_set_user({"user": "Alice"}) == "alice")
check("group : défaut → default", ka._session_set_group(None) == "default")
try:
    ka._session_set_group("bad group!")
    check("group : nom invalide refusé", False)
except ka.ApiError as e:
    check("group : nom invalide refusé (400)", e.code == 400)

# — save : instantané des vivantes sous superadmin/default —
r = ka.op_session_set_save({}, {"user": None})
check("save : couple par défaut superadmin/default", r["user"] == "superadmin" and r["group"] == "default")
check("save : 2 entrées instantanées", r["count"] == 2)
e2395 = next(e for e in r["entries"] if e["sid"] == "2395")
check("save : champs capturés (engine/session_id/cwd/model) + politique de reprise",
      e2395 == {"sid": "2395", "engine": "claude", "session_id": "uuid-2395",
                "cwd": "/zfs/a", "model": "opus", "restart": "idle",
                # RM2439 : le nom est capturé aussi ; None ici (aucun transcript
                # réel derrière ces sessions simulées)
                "title": None})

# — persistance disque : schéma users → groups (anticipation multi-user/jeux) —
store = json.loads(ka.SESSION_SET_FILE.read_text())
check("disque : schéma users/superadmin/groups/default",
      "default" in store["users"]["superadmin"]["groups"])
check("disque : version posée", store.get("version") == 1)

# — get : relit + marque alive selon l'état tmux courant —
g = ka.op_session_set_get({}, {"user": None})
check("get : exists + count", g["exists"] and g["count"] == 2)
# RM2427 : un jeu NEUF est repris d'office — la reprise n'ouvre plus rien
check("save : jeu neuf → autostart activé par défaut (RM2427)", g["autostart"] is True)
check("get : toutes vivantes", all(e["alive"] for e in g["entries"]))
del LIVE["worm-x"]   # une session disparaît
g = ka.op_session_set_get({}, {"user": None})
alive = {e["sid"]: e["alive"] for e in g["entries"]}
check("get : session disparue → alive False, entrée conservée",
      alive == {"2395": True, "worm-x": False})

# — écrasement : re-save préserve autostart —
store = ka._session_set_load()
store["users"]["superadmin"]["groups"]["default"]["autostart"] = True
ka._write_json_atomic(ka.SESSION_SET_FILE, store)
r = ka.op_session_set_save({}, {"user": None})
g = ka.op_session_set_get({}, {"user": None})
check("save : autostart préservé à l'écrasement", g["autostart"] is True)

# — RM2439 : le ré-enregistrement n'ÉCRASE plus les entrées non vivantes —
# Avant : l'instantané des seules vivantes REMPLAÇAIT entries[] ⇒ un clic sur
# « 💾 Enregistrer les sessions » effaçait toutes les tuiles grises (sessions
# enregistrées non lancées) sans le moindre geste de retrait de l'opérateur.
# Le retrait reste explicite : ✕ sur la tuile (delete sid) ou éviction [DONE].
check("RM2439 : l'entrée non vivante (worm-x) survit au ré-enregistrement",
      {e["sid"] for e in g["entries"]} == {"2395", "worm-x"})
check("RM2439 : compte-rendu du save (rien de neuf, rien de perdu)",
      r["count"] == 2 and r["added"] == [] and r["kept"] == 2)

# — RM2439 : une nouvelle vivante s'AJOUTE, les entrées en place ne bougent pas —
LIVE["3999"] = {"engine": "claude", "session_id": "uuid-3999", "cwd": "/zfs/c", "model": None}
r = ka.op_session_set_save({}, {"user": None})
check("RM2439 : nouvelle session vivante ajoutée au jeu",
      r["added"] == ["3999"] and r["count"] == 3)

# — RM2439 : `sids` (ce que le cockpit AFFICHE) est un sélecteur ADDITIF —
# jamais un remplacement : un panneau filtré (par client/projet) afficherait un
# sous-ensemble, et un remplacement y viderait le jeu — le bug d'origine déguisé.
LIVE["4000"] = {"engine": "claude", "session_id": "uuid-4000", "cwd": "/zfs/e", "model": None}
r = ka.op_session_set_save({"sids": ["4000"]}, {"user": None})
check("RM2439 : sids n'ajoute que les sid demandés", r["added"] == ["4000"])
check("RM2439 : sids ne retire rien de ce qui était en jeu",
      {e["sid"] for e in r["entries"]} == {"2395", "worm-x", "3999", "4000"})
r = ka.op_session_set_save({"sids": []}, {"user": None})
check("RM2439 : sids vide ⇒ traité comme absent (union), jamais un retrait",
      r["count"] == 4 and r["added"] == [])
r = ka.op_session_set_save({"sids": ["inconnu-9"]}, {"user": None})
check("RM2439 : sid inconnu signalé (ignored), jeu intact",
      r["ignored"] == ["inconnu-9"] and r["count"] == 4)
try:
    ka.op_session_set_save({"sids": "2395"}, {"user": None})
    check("RM2439 : sids non-liste refusé", False)
except ka.ApiError as e:
    check("RM2439 : sids non-liste refusé (400)", e.code == 400)

# — RM2427/RM2439 : un réglage de reprise posé à la main survit au re-save —
ka.op_session_set_restart({"sid": "worm-x", "restart": "auto"}, {"user": None})
r = ka.op_session_set_save({}, {"user": None})
check("RM2439 : politique de reprise explicite préservée au re-save",
      next(e for e in r["entries"] if e["sid"] == "worm-x")["restart"] == "auto")

# — RM2439 : l'entrée porte le NOM de la session (un sid ne dit pas laquelle) —
TITLES = {"uuid-2395": "chantier cockpit", "uuid-worm": "session worm"}
ka._transcript_title = lambda sid: TITLES.get(sid)
r = ka.op_session_set_save({}, {"user": None})
by_sid = {e["sid"]: e for e in r["entries"]}
check("RM2439 : titre de la session vivante mémorisé", by_sid["2395"].get("title") == "chantier cockpit")
check("RM2439 : titre récupéré aussi pour une entrée déjà non vivante",
      by_sid["worm-x"].get("title") == "session worm")
gh = {x["rm_id"]: x for x in ka._ghost_sessions({"user": None})}
check("RM2439 : la tuile grise expose le nom de la session",
      gh["worm-x"].get("title") == "session worm")
TITLES.clear()                     # transcript devenu illisible / effacé
r = ka.op_session_set_save({}, {"user": None})
check("RM2439 : titre mémorisé conservé si le transcript ne répond plus",
      next(e for e in r["entries"] if e["sid"] == "2395").get("title") == "chantier cockpit")
ka._transcript_title = lambda sid: None
LIVE.pop("3999", None); LIVE.pop("4000", None)
for sid in ("3999", "4000"):
    ka.op_session_set_delete({"sid": sid}, {"user": None})
ka.op_session_set_restart({"sid": "worm-x", "restart": "idle"}, {"user": None})

# — anticipation multi-jeux : un groupe nommé coexiste avec default —
ka.op_session_set_save({"group": "nuit"}, {"user": None})
store = ka._session_set_load()
check("save : groupe nommé coexiste avec default",
      set(store["users"]["superadmin"]["groups"]) == {"default", "nuit"})

# — get sur jeu absent —
g = ka.op_session_set_get({"group": "vide"}, {"user": None})
check("get : jeu absent → exists False", g["exists"] is False and g["entries"] == [])

# — relance en lot (op_session_set_relaunch) : idempotence + fallback opt-in —
ka.SESSION_SET_RELAUNCH_DELAY = 0            # pas d'attente en test
ka._model_catalog = lambda: {"claude": {"opus": "claude-opus-4-8"}}

ALIVE = set()
ka._has_session = lambda sid: sid in ALIVE

RESUME = {}   # sid → "ok" | code d'erreur


def fake_resume(payload):
    sid = payload["rm_id"]
    beh = RESUME.get(sid, "ok")
    if beh == "ok":
        ALIVE.add(sid)
        return {"rm_id": sid, "resumed": True}
    raise ka.ApiError(beh, f"resume {sid} → {beh}")


SPAWNED = []


def fake_spawn(payload):
    SPAWNED.append(payload)
    ALIVE.add(payload["rm_id"])
    return {"rm_id": payload["rm_id"], "created": True}


ka.op_resume = fake_resume
ka.op_spawn = fake_spawn

# reverse-map modèle (RM1941) : le store garde la valeur, op_spawn veut la clé
check("model : valeur connue → clé de catalogue", ka._model_key_for_value("claude", "claude-opus-4-8") == "opus")
check("model : valeur inconnue → défaut ''", ka._model_key_for_value("claude", "zzz") == "")
check("model : None → défaut ''", ka._model_key_for_value("claude", None) == "")

# jeu « relance » : 3001 vivante, 3002 reprenable, 3003 transcript perdu (410),
# 3004 transcript perdu + modèle connu (pour le reverse-map au spawn)
store = ka._session_set_load()
ka._session_set_put(store, "superadmin", "relance", {"saved_at": 1, "autostart": False, "entries": [
    {"sid": "3001", "engine": "claude", "session_id": "sa", "cwd": "/x", "model": None},
    {"sid": "3002", "engine": "claude", "session_id": "sb", "cwd": "/x", "model": None},
    {"sid": "3003", "engine": "claude", "session_id": "sc", "cwd": "/x", "model": None},
    {"sid": "3004", "engine": "claude", "session_id": "sd", "cwd": "/zfs/d", "model": "claude-opus-4-8"},
]})
ka._write_json_atomic(ka.SESSION_SET_FILE, store)

# — resume seul (spawn NON demandé) : perdus → failed, pas de spawn —
ALIVE.clear(); ALIVE.add("3001")
RESUME.clear(); RESUME.update({"3003": 410, "3004": 410})
SPAWNED.clear()
r = ka.op_session_set_relaunch({"group": "relance"}, {"user": None})
by = {x["sid"]: x["action"] for x in r["report"]}
check("relance : déjà vivante → skipped (idempotent)", by["3001"] == "skipped")
check("relance : reprenable → resumed", by["3002"] == "resumed")
check("relance : transcript perdu sans opt-in → failed", by["3003"] == "failed" and by["3004"] == "failed")
check("relance : aucun spawn sans opt-in", SPAWNED == [])
check("relance : counts agrégés", r["counts"] == {"skipped": 1, "resumed": 1, "failed": 2})

# — re-jouée : les reprises restent skipped (pas de doublon ni de kill), seuls
#   les cassés (transcript perdu, sans opt-in) refont failed — idempotence —
r2 = ka.op_session_set_relaunch({"group": "relance"}, {"user": None})
check("relance : rejeu → vivantes skipped, cassées re-failed",
      r2["counts"] == {"skipped": 2, "failed": 2})

# — avec opt-in spawn : les perdus sont recréés, modèle reverse-mappé —
ALIVE.clear(); ALIVE.add("3001")
SPAWNED.clear()
r3 = ka.op_session_set_relaunch({"group": "relance", "spawn": True}, {"user": None})
by = {x["sid"]: x["action"] for x in r3["report"]}
check("relance+spawn : perdus recréés", by["3003"] == "spawned" and by["3004"] == "spawned")
spawned_models = {p["rm_id"]: p["model"] for p in SPAWNED}
check("relance+spawn : modèle connu reverse-mappé en clé", spawned_models.get("3004") == "opus")
check("relance+spawn : modèle None → clé vide", spawned_models.get("3003") == "")

# — jeu absent → 404 —
try:
    ka.op_session_set_relaunch({"group": "fantome"}, {"user": None})
    check("relance : jeu absent → 404", False)
except ka.ApiError as e:
    check("relance : jeu absent → 404", e.code == 404)

# — RM2427 : relance UNITAIRE (clic sur une tuile grise) —
ALIVE.clear(); ALIVE.add("3001")
RESUME.clear(); SPAWNED.clear()
r = ka.op_session_set_relaunch({"group": "relance", "sid": "3002"}, {"user": None})
check("relance unitaire : une seule entrée traitée",
      r["counts"] == {"resumed": 1} and [x["sid"] for x in r["report"]] == ["3002"])
check("relance unitaire : les autres entrées restent intouchées", ALIVE == {"3001", "3002"})
r = ka.op_session_set_relaunch({"group": "relance", "sid": "3001"}, {"user": None})
check("relance unitaire : entrée déjà vivante → skipped", r["counts"] == {"skipped": 1})
try:
    ka.op_session_set_relaunch({"group": "relance", "sid": "9999"}, {"user": None})
    check("relance unitaire : sid hors du jeu → 404", False)
except ka.ApiError as e:
    check("relance unitaire : sid hors du jeu → 404", e.code == 404)

# — autostart : drapeau sans re-snapshot ; RM2427 = reprise EN IDLE (aucun TUI) —
ka.op_session_set_autostart({"group": "default", "autostart": False}, {"user": None})  # isole « relance »
ka.op_session_set_autostart({"group": "relance", "autostart": True}, {"user": None})
g = ka.op_session_set_get({"group": "relance"}, {"user": None})
check("autostart : drapeau posé", g["autostart"] is True)
check("autostart : pas de re-snapshot (entrées inchangées)", g["count"] == 4)
# — RM2427 : politique de reprise PAR SESSION (auto = redémarre seule) —
check("restart : défaut idle hors marqueur", ka._default_restart("uuid-x") == "idle")
MARKS = {}
ka._session_mark = lambda sid: MARKS.get(sid)
ka._is_marked_done = lambda sid: MARKS.get(sid) == "done"
MARKS["sb"] = "wip"
check("restart : une session [WIP] redémarre seule par défaut", ka._default_restart("sb") == "auto")

r = ka.op_session_set_restart({"group": "relance", "sid": "3001", "restart": "auto"}, {"user": None})
check("restart : réglage posé sur une session", r["restart"] == "auto")
check("restart : persisté dans le jeu",
      next(e for e in ka.op_session_set_get({"group": "relance"}, {"user": None})["entries"]
           if e["sid"] == "3001").get("restart") == "auto")
for bad, code in (({"sid": "3001", "restart": "zzz"}, 400),
                  ({"sid": "9999", "restart": "auto"}, 404)):
    try:
        ka.op_session_set_restart({"group": "relance", **bad}, {"user": None})
        check(f"restart : payload invalide → {code}", False)
    except ka.ApiError as e:
        check(f"restart : payload invalide → {code}", e.code == code)

# rejeu au démarrage : SEULES les entrées `auto` non vivantes sont relancées
ALIVE.clear(); LIVE.clear()
RESUME.clear(); SPAWNED.clear()
ka.op_session_set_autostart({"group": "default", "autostart": False}, {"user": None})
res = ka._autostart_replay()
check("démarrage : relance la session réglée auto ET la [WIP] (défaut auto)",
      {(x["sid"], x["action"]) for x in res} == {("3001", "resumed"), ("3002", "resumed")})
check("démarrage : les sessions idle restent en tuile grise (aucun TUI)",
      {"3003", "3004"} <= {g["rm_id"] for g in ka._ghost_sessions({"user": None})})
check("démarrage : jamais de spawn (resume seul)", SPAWNED == [])
check("démarrage : rejeu idempotent (sessions déjà vivantes → rien à relancer)",
      ka._autostart_replay() == [])
ka.op_session_set_restart({"group": "relance", "sid": "3001", "restart": "idle"}, {"user": None})
MARKS.clear()                      # 3002 n'est plus [WIP] → repasse en idle
ALIVE.clear(); LIVE.clear()
check("démarrage : repassées en idle → plus rien n'est relancé", ka._autostart_replay() == [])
MARKS.clear()

# — RM2427 : fantômes = entrées enregistrées NON vivantes du jeu autostart —
# « relance » est le seul jeu repris ici (default/nuit désactivés) ; LIVE reste la
# source des sessions tmux simulées (mock posé en tête, jamais remplacé).
ka.op_session_set_autostart({"group": "nuit", "autostart": False}, {"user": None})
ALIVE.clear(); ALIVE.add("3001")
LIVE.clear(); LIVE["3001"] = {"engine": "claude", "session_id": "sa", "cwd": "/x", "model": None}
ka._pm_project_of_cwd = lambda cwd: (("acme", "shop") if cwd == "/zfs/d" else (None, None))
SPAWNED.clear()
ghosts = ka._ghost_sessions({"user": None})
by = {g["rm_id"]: g for g in ghosts}
check("fantômes : les entrées non vivantes du jeu autostart", set(by) == {"3002", "3003", "3004"})
check("fantômes : la session vivante n'en produit pas", "3001" not in by)
check("fantômes : marqués ghost/state pour le cockpit",
      all(g["ghost"] is True and g["state"] == "ghost" for g in ghosts))
check("fantômes : aucun processus démarré", SPAWNED == [] and ALIVE == {"3001"})
check("fantômes : contexte de relance conservé (moteur, transcript, cwd, groupe)",
      by["3004"]["engine"] == "claude" and by["3004"]["session_id"] == "sd"
      and by["3004"]["cwd"] == "/zfs/d" and by["3004"]["group"] == "relance")
check("fantômes : resumable suit la présence d'un transcript", by["3002"]["resumable"] is True)
check("fantômes : client/projet résolus depuis le cwd (groupement cockpit)",
      (by["3004"].get("client"), by["3004"].get("project")) == ("acme", "shop"))

# — RM2427 : les fantômes rejoignent la vue /sessions (et l'opt-out ghosts=0) —
ka._runs_by_session = lambda: {}
ka._session_registry = lambda: {}
ka._session_state = lambda sid, engine: "idle"
view = {s["rm_id"]: s for s in ka._sessions_view({}, {"user": None})}
check("vue : vivantes + fantômes", set(view) == {"3001", "3002", "3003", "3004"})
check("vue : la vivante n'est pas un fantôme", not view["3001"].get("ghost"))
check("vue : ghosts=0 rend la vue historique",
      [s["rm_id"] for s in ka._sessions_view({"ghosts": "0"}, {"user": None})] == ["3001"])
check("vue : filtre projet appliqué aussi aux fantômes",
      [s["rm_id"] for s in ka._sessions_view({"client": "acme", "project": "shop"},
                                             {"user": None})] == ["3004"])
LIVE.clear(); ALIVE.clear()
check("vue : sans aucune session vivante, les fantômes restent servis",
      {s["rm_id"] for s in ka._sessions_view({}, {"user": None})} == {"3001", "3002", "3003", "3004"})

try:
    ka.op_session_set_autostart({"group": "fantome", "autostart": True}, {"user": None})
    check("autostart : jeu absent → 404", False)
except ka.ApiError as e:
    check("autostart : jeu absent → 404", e.code == 404)
try:
    ka.op_session_set_autostart({"group": "relance"}, {"user": None})
    check("autostart : champ requis → 400", False)
except ka.ApiError as e:
    check("autostart : champ requis → 400", e.code == 400)

# — RM2427 : une session TERMINÉE marquée [DONE] sort du jeu toute seule —
DONE = set()                      # session_id marqués [DONE] (transcript simulé)
ka._is_marked_done = lambda sid: sid in DONE
DONE.add("sb")                    # 3002 est [DONE] mais VIVANTE → conservée
ALIVE.clear(); ALIVE.update({"3001", "3002"})
LIVE.clear(); LIVE.update({s: {} for s in ALIVE})
ghosts = {g["rm_id"] for g in ka._ghost_sessions({"user": None})}
check("[DONE] : une session vivante n'est jamais retirée",
      {e["sid"] for e in ka.op_session_set_get({"group": "relance"}, {"user": None})["entries"]}
      == {"3001", "3002", "3003", "3004"})
ALIVE.discard("3002"); LIVE.pop("3002", None)   # /exit sur la session [DONE]
ghosts = {g["rm_id"] for g in ka._ghost_sessions({"user": None})}
check("[DONE] : /exit → entrée retirée du jeu (pas de tuile grise)", "3002" not in ghosts)
g = ka.op_session_set_get({"group": "relance"}, {"user": None})
check("[DONE] : retrait persisté, les autres conservées",
      {e["sid"] for e in g["entries"]} == {"3001", "3003", "3004"})
check("[DONE] : une session close NON marquée reste (fantôme)",
      {"3003", "3004"} <= ghosts)
DONE.clear()

# — RM2427 : retrait d'UNE entrée (session terminée par /exit) sans toucher au reste —
before = ka.op_session_set_get({"group": "relance"}, {"user": None})["count"]
d = ka.op_session_set_delete({"group": "relance", "sid": "3003"}, {"user": None})
check("delete sid : entrée retirée, compte décrémenté",
      d["deleted"] is True and d["count"] == before - 1)
g = ka.op_session_set_get({"group": "relance"}, {"user": None})
check("delete sid : les autres entrées conservées",   # 3002 est partie avec le [DONE]
      {e["sid"] for e in g["entries"]} == {"3001", "3004"})
check("delete sid : le jeu (et ses réglages) survit", g["exists"] and g["autostart"] is True)
check("delete sid : plus de fantôme pour l'entrée retirée",
      "3003" not in {x["rm_id"] for x in ka._ghost_sessions({"user": None})})
try:
    ka.op_session_set_delete({"group": "relance", "sid": "3003"}, {"user": None})
    check("delete sid : entrée déjà retirée → 404", False)
except ka.ApiError as e:
    check("delete sid : entrée déjà retirée → 404", e.code == 404)

# — delete : efface le groupe, 404 si déjà absent —
check("delete : groupe effacé", ka.op_session_set_delete({"group": "nuit"}, {"user": None})["deleted"] is True)
check("delete : groupe retiré du store",
      "nuit" not in ka._session_set_load()["users"]["superadmin"]["groups"])
try:
    ka.op_session_set_delete({"group": "nuit"}, {"user": None})
    check("delete : déjà absent → 404", False)
except ka.ApiError as e:
    check("delete : déjà absent → 404", e.code == 404)

# — plafond : un instantané trop gros est refusé —
LIVE.clear()
LIVE.update({str(i): {"engine": "claude", "session_id": f"u{i}", "cwd": "/x", "model": None}
             for i in range(ka.SESSION_SET_MAX + 1)})
try:
    ka.op_session_set_save({}, {"user": None})
    check("save : plafond dépassé refusé", False)
except ka.ApiError as e:
    check("save : plafond dépassé refusé (409)", e.code == 409)
# RM2439 : le refus est ATOMIQUE — l'union qui déborde ne doit rien réécrire
check("RM2439 : plafond franchi ⇒ jeu inchangé sur disque",
      {e["sid"] for e in ka.op_session_set_get({}, {"user": None})["entries"]} == {"2395", "worm-x"})

# — correctif RM1941 : _record_key mémorise le modèle et le préserve à la reprise —
LIVE.clear()
KLOG = TMP / "state"
ka.LOG_DIR = KLOG
ka.STATE_DIR = KLOG            # RM2385 : keys/ suit STATE_DIR (défaut = LOG_DIR)
ka.SESS_DIR = KLOG / "sessions"
ka._record_key("2395", "claude", "uuid-z", "/zfs/z", model="sonnet")
key = json.loads((KLOG / "keys" / "RM2395.json").read_text())
check("record_key : modèle mémorisé au spawn", key.get("model") == "sonnet")
ka._record_key("2395", "claude", "uuid-z", "/zfs/z")   # reprise, sans model
key = json.loads((KLOG / "keys" / "RM2395.json").read_text())
check("record_key : modèle préservé à la reprise", key.get("model") == "sonnet")

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests jeux de sessions RM2395/RM2427 passent")
