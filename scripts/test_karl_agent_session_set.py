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

RM2442 — jeux NOMMÉS : découverte (`op_session_sets_list`), libellé humain à
côté du slug immuable, renommage, indépendance des jeux entre eux, et
dédoublonnage des tuiles grises quand une session appartient à deux jeux repris.

RM2445 — jeu COURANT côté serveur : bascule qui change réellement la vue
(fantômes du jeu courant, plus l'union des `autostart`), adhésion automatique
d'une session lancée/reprise au jeu courant (le statut fait ENTRER, jamais
SORTIR), appartenance multiple, et écritures additives non archivées.

RM2446 — VUES (« sessions ouvertes », « tous les jeux ») distinctes du jeu
courant : une vue n'affiche, elle ne reçoit rien — le jeu courant reste la cible
des écritures. Plus la séparation ⊖ (retirer du jeu, la session tourne toujours)
vs ✕ (fermer la session), et le marquage des sessions hors de tout jeu.

RM2447 — création d'un jeu VIDE : verbe `create` distinct de `save`, où
l'absence de `sids` veut dire « rien » (et non « toutes les vivantes », sens que
`save` conserve depuis RM2439) ; 409 sur jeu existant ; compteur de sessions
ouvertes par jeu.

RM2448 — SCINDER un jeu : `create {move_from}` retire les sid retenus du jeu
source dans la même écriture que la création du nouveau (atomicité), avec
archivage puisqu'un split retire quelque chose ; les réglages de l'entrée
suivent la session, et les sid absents du source sont ignorés sans erreur.

RM2449 — DÉPLACER vers un jeu EXISTANT (`move`) : union côté cible, retrait du
source (ou `copy`), une seule écriture, plafond vérifié avant toute modification,
et archivage du seul déplacement.

RM2450 — une seule notion de reprise : le drapeau `autostart` par jeu ne
gouverne plus rien, `_autostart_replay` relance les entrées `auto` du JEU
COURANT ; et l'échec d'adhésion pour cause de jeu plein remonte à l'appelant au
lieu de finir sur stderr.

RM2451 — lisibilité : âge de la SESSION (transcript) et non du jeu, estimation
du coût d'un « tout relancer » (volume de contexte à réhydrater), et retrait
ANNULABLE via le jeton d'archivage rendu par la suppression.

RM2452 — jeux DÉRIVÉS : contenu calculé par une règle (client, projet, marque,
tickets), lecture unifiée par `_set_entries`, écriture refusée sur un dérivé,
matérialisation en jeu manuel, et rétention d'AFFICHAGE optionnelle (masquer les
inactives, jamais supprimer — désactivée par défaut).

RM2443 — historique : archivage de l'état courant avant chaque écriture (avec
dédoublonnage et rotation `keep`), et restauration CHIRURGICALE d'un seul jeu
depuis une version — les autres jeux ne bougent pas. Dégradations couvertes :
archive corrompue ignorée, historique en échec non bloquant pour le store.
Lancer : python3 scripts/test_karl_agent_session_set.py
"""
import importlib.util
import json
import pathlib
import sys
import tempfile
import time

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

# RM2536 : les vraies op_resume/op_spawn, avant que le harnais ne les remplace
# par des doublures (les tests RM2536 exercent la VRAIE relance, en bas de fichier)
REAL_OP_RESUME, REAL_OP_SPAWN = ka.op_resume, ka.op_spawn

ALIVE = set()
ka._has_session = lambda sid: sid in ALIVE
# RM2951 : /spawn et /resume vérifient que la session a SURVÉCU avant de
# répondre « créée ». Point de mesure distinct de la garde « déjà active »,
# que ce harnais fige à False pour pouvoir enchaîner les lancements.
ka._session_started = lambda sid: True

RESUME = {}   # sid → "ok" | code d'erreur


def fake_resume(payload, auth_ctx=None):   # RM2445 : op_resume porte le contexte d'auth
    sid = payload["rm_id"]
    beh = RESUME.get(sid, "ok")
    if beh == "ok":
        ALIVE.add(sid)
        return {"rm_id": sid, "resumed": True}
    raise ka.ApiError(beh, f"resume {sid} → {beh}")


SPAWNED = []


def fake_spawn(payload, auth_ctx=None):     # RM2445 : idem pour op_spawn
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

# rejeu au démarrage : SEULES les entrées `auto` non vivantes du JEU COURANT
# (RM2450 : le drapeau `autostart` par jeu ne gouverne plus rien — la politique
# par entrée suffit, et le périmètre est le jeu courant comme partout ailleurs)
ALIVE.clear(); LIVE.clear()
RESUME.clear(); SPAWNED.clear()
ka.op_session_set_current({"group": "relance"}, {"user": None})   # le jeu observé
res = ka._autostart_replay()
check("démarrage : relance la session réglée auto ET la [WIP] (défaut auto)",
      {(x["sid"], x["action"]) for x in res} == {("3001", "resumed"), ("3002", "resumed")})
# RM2450 : une entrée `auto` d'un AUTRE jeu ne doit pas rouvrir le chantier d'à côté
ka.op_session_set_current({"group": "default"}, {"user": None})
ALIVE.clear(); RESUME.clear()
check("RM2450 : les entrées `auto` d'un autre jeu ne sont pas relancées",
      ka._autostart_replay() == [])
ka.op_session_set_current({"group": "relance"}, {"user": None})
ALIVE.clear(); RESUME.clear()
ka._autostart_replay()   # remet 3001/3002 vivantes pour la suite du scénario
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

# — RM2427/RM2445 : fantômes = entrées enregistrées NON vivantes du JEU COURANT —
# « relance » est le jeu courant ici ; LIVE reste la source des sessions tmux
# simulées (mock posé en tête, jamais remplacé). Depuis RM2445 le périmètre des
# fantômes est le jeu courant, plus l'union des jeux `autostart`.
ka.op_session_set_autostart({"group": "nuit", "autostart": False}, {"user": None})
ALIVE.clear(); ALIVE.add("3001")
LIVE.clear(); LIVE["3001"] = {"engine": "claude", "session_id": "sa", "cwd": "/x", "model": None}
ka._pm_project_of_cwd = lambda cwd: (("acme", "shop") if cwd == "/zfs/d" else (None, None))
SPAWNED.clear()
ghosts = ka._ghost_sessions({"user": None})
by = {g["rm_id"]: g for g in ghosts}
check("fantômes : les entrées non vivantes du jeu courant", set(by) == {"3002", "3003", "3004"})
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
REAL_RUNS_BY_SESSION = ka._runs_by_session   # RM2536 : réutilisée en bas de fichier
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

# ── RM2442 : jeux NOMMÉS, multiples et indépendants ──────────────────────────
# Le store portait déjà le multi-groupes (RM2395) sans qu'aucun endpoint ne
# permette de les DÉCOUVRIR, ni de leur donner un intitulé lisible.
LIVE.clear()
LIVE.update({
    "5001": {"engine": "claude", "session_id": "uuid-5001", "cwd": "/zfs/cal", "model": None},
    "5002": {"engine": "claude", "session_id": "uuid-5002", "cwd": "/zfs/inf", "model": None},
})
ka.op_session_set_save({"group": "calicote", "label": "Chantier Calicote",
                        "sids": ["5001"]}, {"user": None})
ka.op_session_set_save({"group": "infra", "sids": ["5002"]}, {"user": None})

lst = ka.op_session_sets_list({}, {"user": None})
names = [s["name"] for s in lst["sets"]]
check("RM2442 : les jeux sont listables (endpoint de découverte)",
      set(names) == {"default", "calicote", "infra", "relance"})
check("RM2442 : `default` en tête, le reste alphabétique",
      names == ["default", "calicote", "infra", "relance"])
by_name = {s["name"]: s for s in lst["sets"]}
check("RM2442 : libellé humain rendu quand il existe",
      by_name["calicote"]["label"] == "Chantier Calicote")
check("RM2442 : à défaut de libellé, le slug fait office",
      by_name["infra"]["label"] == "infra")
check("RM2442 : compte et vivantes par jeu",
      by_name["calicote"]["count"] == 1 and by_name["calicote"]["alive"] == 1)

# le libellé survit à un ré-enregistrement (il n'est pas dans l'instantané)
ka.op_session_set_save({"group": "calicote"}, {"user": None})
check("RM2442 : libellé conservé au ré-enregistrement",
      ka.op_session_set_get({"group": "calicote"}, {"user": None})["label"] == "Chantier Calicote")

# renommage : le LIBELLÉ change, le slug (clé du store) est immuable
ka.op_session_set_rename({"group": "infra", "label": "Infra iProspective"}, {"user": None})
store = ka._session_set_load()
check("RM2442 : renommage = libellé seul, slug intact",
      "infra" in store["users"]["superadmin"]["groups"]
      and ka.op_session_set_get({"group": "infra"}, {"user": None})["label"] == "Infra iProspective")
for bad, why in ((""," vide"), ("x" * (ka.SET_LABEL_MAX + 1), " trop long")):
    try:
        ka.op_session_set_rename({"group": "infra", "label": bad}, {"user": None})
        check(f"RM2442 : libellé{why} refusé", False)
    except ka.ApiError as e:
        check(f"RM2442 : libellé{why} refusé (400)", e.code == 400)
try:
    ka.op_session_set_rename({"group": "fantome", "label": "X"}, {"user": None})
    check("RM2442 : renommage d'un jeu absent → 404", False)
except ka.ApiError as e:
    check("RM2442 : renommage d'un jeu absent → 404", e.code == 404)

# indépendance : agir sur un jeu ne touche pas les autres
ka.op_session_set_delete({"group": "calicote"}, {"user": None})
check("RM2442 : supprimer un jeu laisse les autres intacts",
      {s["name"] for s in ka.op_session_sets_list({}, {"user": None})["sets"]}
      == {"default", "infra", "relance"})
check("RM2442 : le jeu voisin garde ses entrées",
      ka.op_session_set_get({"group": "infra"}, {"user": None})["count"] == 1)

# une MÊME session dans DEUX jeux repris ⇒ UNE seule tuile grise (dédoublonnage)
ka.op_session_set_save({"group": "infra", "sids": ["5001", "5002"]}, {"user": None})
ka.op_session_set_autostart({"group": "infra", "autostart": True}, {"user": None})
ka.op_session_set_autostart({"group": "default", "autostart": True}, {"user": None})
ka.op_session_set_save({"sids": ["5001"]}, {"user": None})       # 5001 aussi dans default
LIVE.clear()                                                     # toutes éteintes
ka.op_session_set_current({"group": "infra"}, {"user": None})     # RM2445 : jeu observé
ghosts = ka._ghost_sessions({"user": None})
sids = [g["rm_id"] for g in ghosts]
check("RM2442 : session appartenant à deux jeux ⇒ une seule tuile grise",
      sids.count("5001") == 1 and sorted(sids) == ["5001", "5002"])
check("RM2442 : la tuile grise dit de quel jeu elle vient",
      all(g.get("group") and g.get("group_label") for g in ghosts))
ka.op_session_set_autostart({"group": "infra", "autostart": False}, {"user": None})
ka.op_session_set_autostart({"group": "default", "autostart": False}, {"user": None})

# ── RM2443 : historique du store + restauration PAR JEU ──────────────────────
# On historise le FICHIER (point d'écriture unique, sûr) mais on restaure un JEU :
# rembobiner le fichier entier rendrait AUSSI les jeux qu'on n'a pas demandés.
HIST = ka._history_dir()
check("RM2443 : l'historique s'est rempli au fil des écritures",
      len(ka._history_versions()) > 0)

# dédoublonnage : deux écritures de contenu IDENTIQUE n'empilent rien
n0 = len(ka._history_versions())
store = ka._session_set_load()
ka._write_session_set(store)
ka._write_session_set(store)
check("RM2443 : une écriture sans changement n'empile aucune version",
      len(ka._history_versions()) == n0)

# rotation : au-delà de `keep`, les plus anciennes sont purgées
ka.SESSION_SET_KEEP = 3
for i in range(6):
    ka.op_session_set_rename({"group": "infra", "label": f"Infra v{i}"}, {"user": None})
vers = ka._history_versions()
check("RM2443 : rotation — jamais plus de `keep` versions", len(vers) == 3)
check("RM2443 : ce sont les plus RÉCENTES qui restent",
      [s for s, _ in vers] == sorted([s for s, _ in vers], reverse=True))

# le point dur : restaurer UN jeu laisse les autres intacts
ka.SESSION_SET_KEEP = 10
ka.op_session_set_rename({"group": "infra", "label": "AVANT"}, {"user": None})
avant_infra = {e["sid"] for e in ka.op_session_set_get({"group": "infra"}, {"user": None})["entries"]}
h = ka.op_session_set_history({}, {"user": None})
check("RM2443 : l'historique liste les jeux de chaque version",
      h["count"] > 0 and all({"id", "at", "sets"} <= set(v) for v in h["versions"]))
ka.op_session_set_rename({"group": "infra", "label": "APRÈS"}, {"user": None})   # nouvel état
vid = ka.op_session_set_history({}, {"user": None})["versions"][0]["id"]          # = l'état AVANT

# on abîme les DEUX jeux, puis on ne restaure QUE `infra`
ka.op_session_set_delete({"group": "infra", "sid": sorted(avant_infra)[0]}, {"user": None})
ka.op_session_set_rename({"group": "default", "label": "témoin default"}, {"user": None})
temoin = ka.op_session_set_get({}, {"user": None})
r = ka.op_session_set_restore({"group": "infra", "id": vid}, {"user": None})
infra = ka.op_session_set_get({"group": "infra"}, {"user": None})
check("RM2443 : le jeu visé est rétabli (entrées ET libellé)",
      {e["sid"] for e in infra["entries"]} == avant_infra
      and infra["label"] == "AVANT" and r["count"] == len(avant_infra))
apres = ka.op_session_set_get({}, {"user": None})
check("RM2443 : les AUTRES jeux ne bougent pas (restauration chirurgicale)",
      apres["label"] == temoin["label"]
      and {e["sid"] for e in apres["entries"]} == {e["sid"] for e in temoin["entries"]})

# la restauration est elle-même annulable : elle a archivé ce qu'elle a remplacé
h2 = ka.op_session_set_history({}, {"user": None})
check("RM2443 : la restauration archive l'état qu'elle remplace (annulable)",
      h2["versions"][0]["id"] != vid)

for payload, code, why in (({"group": "jamais-vu", "id": vid}, 404, "jeu absent de la version"),
                           ({"group": "infra", "id": "1"}, 404, "version inconnue"),
                           ({"group": "infra"}, 400, "identifiant de version manquant")):
    try:
        ka.op_session_set_restore(payload, {"user": None})
        check(f"RM2443 : {why} → {code}", False)
    except ka.ApiError as e:
        check(f"RM2443 : {why} → {code}", e.code == code)
check("RM2443 : après un refus, le jeu reste tel quel",
      {e["sid"] for e in ka.op_session_set_get({"group": "infra"}, {"user": None})["entries"]} == avant_infra)

# archive corrompue : ignorée en lecture, jamais fatale
(HIST / "session-set-1.json").write_text("{ pas du json", encoding="utf-8")
check("RM2443 : une archive corrompue est ignorée, pas remontée en erreur",
      all(v["id"] != "1" for v in ka.op_session_set_history({}, {"user": None})["versions"]))
# et le store reste écrivable même si l'historique devient inutilisable
HIST.chmod(0o500)
try:
    ka.op_session_set_rename({"group": "infra", "label": "malgré tout"}, {"user": None})
    check("RM2443 : historique en échec ⇒ l'écriture du store passe quand même",
          ka.op_session_set_get({"group": "infra"}, {"user": None})["label"] == "malgré tout")
finally:
    HIST.chmod(0o700)

# ── RM2445 : jeu COURANT côté serveur — bascule réelle, adhésion automatique ──
# Le jeu courant vivait dans le localStorage du cockpit : le serveur l'ignorait,
# donc basculer ne changeait rien à l'affichage (les fantômes venaient de l'union
# des jeux `autostart`). Il devient un état serveur, et tout en découle.
LIVE.clear()
LIVE.update({
    "6001": {"engine": "claude", "session_id": "uuid-6001", "cwd": "/zfs/x", "model": None},
    "6002": {"engine": "claude", "session_id": "uuid-6002", "cwd": "/zfs/y", "model": None},
})
ka.op_session_set_save({"group": "chantier-a", "label": "Chantier A", "sids": ["6001"]}, {"user": None})
ka.op_session_set_save({"group": "chantier-b", "label": "Chantier B", "sids": ["6002"]}, {"user": None})

check("RM2445 : jeu courant par défaut pour qui n'en a jamais choisi",
      ka._current_set("utilisateur-vierge") == "default")
ka.op_session_set_current({"group": "chantier-a"}, {"user": None})
check("RM2445 : le jeu courant est un état SERVEUR (persisté)",
      ka._current_set("superadmin") == "chantier-a"
      and ka.op_session_sets_list({}, {"user": None})["current"] == "chantier-a")
try:
    ka.op_session_set_current({"group": "jamais-vu"}, {"user": None})
    check("RM2445 : jeu courant inconnu → 404", False)
except ka.ApiError as e:
    check("RM2445 : jeu courant inconnu → 404", e.code == 404)
try:
    ka.op_session_set_current({"group": "PAS UN SLUG"}, {"user": None})
    check("RM2445 : slug invalide → 400", False)
except ka.ApiError as e:
    check("RM2445 : slug invalide → 400", e.code == 400)

# les fantômes SUIVENT le jeu courant (c'est tout l'objet de la bascule)
LIVE.clear()                                   # les deux sessions s'arrêtent
check("RM2445 : fantômes du jeu courant (A)",
      {g["rm_id"] for g in ka._ghost_sessions({"user": None})} == {"6001"})
ka.op_session_set_current({"group": "chantier-b"}, {"user": None})
check("RM2445 : bascule ⇒ les fantômes changent (B)",
      {g["rm_id"] for g in ka._ghost_sessions({"user": None})} == {"6002"})

# une bascule ne touche AUCUN tmux : rien n'est tué, rien n'est lancé
SPAWNED.clear(); ALIVE.clear(); ALIVE.update({"6001"})
LIVE.update({"6001": {"engine": "claude", "session_id": "uuid-6001", "cwd": "/zfs/x", "model": None}})
ka.op_session_set_current({"group": "chantier-a"}, {"user": None})
ka.op_session_set_current({"group": "chantier-b"}, {"user": None})
check("RM2445 : basculer ne tue ni ne lance aucune session",
      SPAWNED == [] and ALIVE == {"6001"} and set(LIVE) == {"6001"})

# une session VIVANTE d'un autre jeu reste visible, marquée de son appartenance
view = {s["rm_id"]: s for s in ka._sessions_view({}, {"user": None})}
check("RM2445 : la vivante d'un autre jeu n'est pas masquée", "6001" in view)
check("RM2445 : elle porte ses jeux et le fait qu'elle est hors du courant",
      view["6001"]["sets"] == ["chantier-a"]
      and view["6001"]["set_labels"] == ["Chantier A"]
      and view["6001"]["in_current"] is False)

# une session peut appartenir à PLUSIEURS jeux ; la retirer d'un jeu la laisse dans l'autre
ka.op_session_set_save({"group": "chantier-b", "sids": ["6001"]}, {"user": None})
check("RM2445 : une session peut être dans deux jeux",
      set(ka._sessions_view({}, {"user": None})[0]["sets"]) == {"chantier-a", "chantier-b"})
ka.op_session_set_delete({"group": "chantier-b", "sid": "6001"}, {"user": None})
check("RM2445 : retirée d'un jeu, elle reste dans l'autre",
      ka._sessions_view({}, {"user": None})[0]["sets"] == ["chantier-a"])

# adhésion automatique : le statut fait ENTRER, jamais SORTIR (invariant RM2439)
ka.op_session_set_current({"group": "chantier-b"}, {"user": None})
avant_b = {e["sid"] for e in ka.op_session_set_get({"group": "chantier-b"}, {"user": None})["entries"]}
LIVE["6003"] = {"engine": "claude", "session_id": "uuid-6003", "cwd": "/zfs/z", "model": None}
ka._auto_join_current_set("6003", {"user": None})
apres_b = {e["sid"] for e in ka.op_session_set_get({"group": "chantier-b"}, {"user": None})["entries"]}
check("RM2445 : une session lancée rejoint le jeu courant", apres_b == avant_b | {"6003"})
ka._auto_join_current_set("6003", {"user": None})
check("RM2445 : adhésion idempotente (pas de doublon)",
      len(ka.op_session_set_get({"group": "chantier-b"}, {"user": None})["entries"]) == len(apres_b))
del LIVE["6003"]                                   # la session s'arrête
check("RM2445 : une session arrêtée RESTE dans le jeu (tuile grise, RM2439)",
      "6003" in {e["sid"] for e in ka.op_session_set_get({"group": "chantier-b"}, {"user": None})["entries"]})
check("RM2445 : le jeu voisin n'a pas bougé",
      {e["sid"] for e in ka.op_session_set_get({"group": "chantier-a"}, {"user": None})["entries"]} == {"6001"})

# une écriture ADDITIVE n'archive pas (sinon lancer 10 sessions viderait l'historique)
def _derniere_version():
    v = ka._history_versions()
    return v[0][0] if v else None

avant = _derniere_version()
LIVE["6004"] = {"engine": "claude", "session_id": "uuid-6004", "cwd": "/zfs/w", "model": None}
ka._auto_join_current_set("6004", {"user": None})
ka.op_session_set_current({"group": "chantier-a"}, {"user": None})
check("RM2445 : adhésion et bascule n'entament pas l'historique",
      _derniere_version() == avant)
ka.op_session_set_current({"group": "chantier-b"}, {"user": None})
ka.op_session_set_delete({"group": "chantier-b", "sid": "6004"}, {"user": None})
check("RM2445 : une écriture DESTRUCTRICE archive toujours",
      _derniere_version() != avant)

# jeu courant effacé ⇒ retombée sur `default`, jamais de contexte orphelin
ka.op_session_set_current({"group": "chantier-b"}, {"user": None})
ka.op_session_set_delete({"group": "chantier-b"}, {"user": None})
check("RM2445 : jeu courant effacé → retour à `default`",
      ka._current_set("superadmin") == "default")

# ── RM2446 : vues (« sessions ouvertes », « tous les jeux ») + hors jeu ───────
# Une VUE n'est pas un jeu : elle ne reçoit rien. Le jeu courant reste la cible
# des écritures, la vue ne décide que de l'affichage.
LIVE.clear()
LIVE.update({
    "7001": {"engine": "claude", "session_id": "uuid-7001", "cwd": "/zfs/p", "model": None},
    "7002": {"engine": "claude", "session_id": "uuid-7002", "cwd": "/zfs/q", "model": None},
    "7003": {"engine": "claude", "session_id": "uuid-7003", "cwd": "/zfs/r", "model": None},
})
ka.op_session_set_save({"group": "vue-a", "label": "Vue A", "sids": ["7001"]}, {"user": None})
ka.op_session_set_save({"group": "vue-b", "label": "Vue B", "sids": ["7002"]}, {"user": None})
ka.op_session_set_current({"group": "vue-a"}, {"user": None})
LIVE.clear()                                    # tout s'arrête → que des fantômes

check("RM2446 : vue par défaut = le jeu courant", ka._current_view("superadmin") == "set")
check("RM2446 : vue `set` — fantômes du seul jeu courant",
      {g["rm_id"] for g in ka._ghost_sessions({"user": None})} == {"7001"})
ka.op_session_set_current({"view": "live"}, {"user": None})
check("RM2446 : vue `live` — aucune tuile grise (on ne voit que ce qui tourne)",
      ka._ghost_sessions({"user": None}) == [])
ka.op_session_set_current({"view": "all"}, {"user": None})
tous = {g["rm_id"]: g for g in ka._ghost_sessions({"user": None})}
check("RM2446 : vue `all` — fantômes de TOUS les jeux",
      {"7001", "7002"} <= set(tous))
check("RM2446 : vue `all` — chaque fantôme dit son jeu",
      tous["7001"]["group"] == "vue-a" and tous["7002"]["group"] == "vue-b")
check("RM2446 : vue `all` — aucun doublon",
      len(tous) == len({g["rm_id"] for g in ka._ghost_sessions({"user": None})}))

# le jeu courant NE CHANGE PAS quand on change de vue : une vue n'est pas une cible
check("RM2446 : changer de vue ne déplace pas le jeu courant",
      ka._current_set("superadmin") == "vue-a")
LIVE["7003"] = {"engine": "claude", "session_id": "uuid-7003", "cwd": "/zfs/r", "model": None}
ka._auto_join_current_set("7003", {"user": None})
check("RM2446 : une session lancée depuis une vue rejoint le JEU courant",
      "7003" in {e["sid"] for e in ka.op_session_set_get({"group": "vue-a"}, {"user": None})["entries"]})

# choisir un jeu, c'est vouloir le regarder → retour en vue `set`
ka.op_session_set_current({"group": "vue-b"}, {"user": None})
check("RM2446 : choisir un jeu rebascule en vue `set`",
      ka._current_view("superadmin") == "set" and ka._current_set("superadmin") == "vue-b")

for bad in ("perspective", ""):
    try:
        ka.op_session_set_current({"view": bad}, {"user": None})
        check(f"RM2446 : vue invalide ({bad!r}) → 400", False)
    except ka.ApiError as e:
        check(f"RM2446 : vue invalide ({bad!r}) → 400", e.code == 400)
try:
    ka.op_session_set_current({}, {"user": None})
    check("RM2446 : ni group ni view → 400", False)
except ka.ApiError as e:
    check("RM2446 : ni group ni view → 400", e.code == 400)

# ⊖ retirer du jeu ≠ ✕ fermer : la session RESTE vivante après un retrait
LIVE.clear(); LIVE.update({"7002": {"engine": "claude", "session_id": "uuid-7002",
                                    "cwd": "/zfs/q", "model": None}})
ka.op_session_set_delete({"group": "vue-b", "sid": "7002"}, {"user": None})
check("RM2446 : retirer du jeu ne ferme pas la session (elle tourne toujours)",
      "7002" in LIVE and "7002" in {s["rm_id"] for s in ka._sessions_view({}, {"user": None})})
check("RM2446 : retirée de tout jeu, elle est signalée « hors jeu » (sets vide)",
      next(s for s in ka._sessions_view({}, {"user": None}) if s["rm_id"] == "7002")["sets"] == [])

# en vue `live` / `all`, tout ce qui est affiché appartient à la vue
ka.op_session_set_current({"view": "live"}, {"user": None})
check("RM2446 : en vue `live`, aucune vivante n'est reléguée « hors du jeu courant »",
      all(s["in_current"] for s in ka._sessions_view({}, {"user": None}) if not s.get("ghost")))
ka.op_session_set_current({"view": "set"}, {"user": None})

# ── RM2447 : créer un jeu VIDE par défaut (verbe distinct de `save`) ──────────
# `save` traite `sids` vide comme « toutes les vivantes » (garde-fou RM2439) :
# aucun chemin ne permettait donc de créer un jeu vide. Le verbe `create` donne à
# l'absence de `sids` le sens INVERSE — rien — sans toucher à celui de `save`.
LIVE.clear()
LIVE.update({
    "8001": {"engine": "claude", "session_id": "uuid-8001", "cwd": "/zfs/m", "model": None},
    "8002": {"engine": "claude", "session_id": "uuid-8002", "cwd": "/zfs/n", "model": None},
})
r = ka.op_session_set_create({"group": "neuf-vide", "label": "Jeu neuf"}, {"user": None})
check("RM2447 : sans `sids`, le jeu naît VIDE", r["count"] == 0 and r["entries"] == [])
check("RM2447 : le jeu créé devient courant, en vue `jeu`",
      ka._current_set("superadmin") == "neuf-vide" and ka._current_view("superadmin") == "set")
check("RM2447 : il est bien listé, à zéro entrée",
      next(s for s in ka.op_session_sets_list({}, {"user": None})["sets"]
           if s["name"] == "neuf-vide")["count"] == 0)
check("RM2447 : un jeu vide n'expose aucune tuile grise",
      ka._ghost_sessions({"user": None}) == [])

r = ka.op_session_set_create({"group": "neuf-plein", "sids": ["8001"]}, {"user": None})
check("RM2447 : avec `sids`, le jeu naît avec exactement ces sessions",
      [e["sid"] for e in r["entries"]] == ["8001"])
check("RM2447 : à défaut de libellé, le slug fait office", r["label"] == "neuf-plein")

try:
    ka.op_session_set_create({"group": "neuf-plein", "sids": ["8002"]}, {"user": None})
    check("RM2447 : jeu déjà existant → 409", False)
except ka.ApiError as e:
    check("RM2447 : jeu déjà existant → 409", e.code == 409)
check("RM2447 : et l'existant n'a pas bougé",
      [e["sid"] for e in ka.op_session_set_get({"group": "neuf-plein"}, {"user": None})["entries"]] == ["8001"])
for bad, code, why in (({"group": "PAS UN SLUG"}, 400, "slug invalide"),
                       ({"group": "libelle-long", "label": "x" * (ka.SET_LABEL_MAX + 1)}, 400, "libellé trop long"),
                       ({"group": "sids-pas-liste", "sids": "8001"}, 400, "sids non-liste")):
    try:
        ka.op_session_set_create(bad, {"user": None})
        check(f"RM2447 : {why} → {code}", False)
    except ka.ApiError as e:
        check(f"RM2447 : {why} → {code}", e.code == code)

# non-régression RM2439 : `save` garde le sens INVERSE pour un `sids` vide
ka.op_session_set_current({"group": "neuf-vide"}, {"user": None})
r = ka.op_session_set_save({"group": "neuf-vide", "sids": []}, {"user": None})
check("RM2447 : `save` avec sids vide enregistre toujours toutes les vivantes (RM2439)",
      {e["sid"] for e in r["entries"]} == {"8001", "8002"})

# RM2447 : la liste dit, par jeu, combien de sessions sont OUVERTES
del LIVE["8002"]
s = next(x for x in ka.op_session_sets_list({}, {"user": None})["sets"] if x["name"] == "neuf-vide")
check("RM2447 : le jeu expose ses sessions ouvertes et son total",
      s["alive"] == 1 and s["count"] == 2)

# ── RM2448 : SCINDER un jeu (create + move_from), atomique ───────────────────
LIVE.clear()
LIVE.update({s: {"engine": "claude", "session_id": "uuid-" + s, "cwd": "/zfs/s", "model": None}
             for s in ("9001", "9002", "9003")})
ka.op_session_set_create({"group": "fourre-tout", "label": "Fourre-tout",
                          "sids": ["9001", "9002", "9003"]}, {"user": None})
ka.op_session_set_restart({"group": "fourre-tout", "sid": "9002", "restart": "auto"}, {"user": None})
avant = ka._derniere_version() if hasattr(ka, "_derniere_version") else None
v_avant = ka._history_versions()[0][0] if ka._history_versions() else None

r = ka.op_session_set_create({"group": "scission", "label": "Scission",
                              "sids": ["9002", "9003"], "move_from": "fourre-tout"},
                             {"user": None})
check("RM2448 : le nouveau jeu contient exactement la sélection",
      {e["sid"] for e in r["entries"]} == {"9002", "9003"} and sorted(r["moved"]) == ["9002", "9003"])
check("RM2448 : le jeu source ne les a plus, et garde le reste",
      {e["sid"] for e in ka.op_session_set_get({"group": "fourre-tout"}, {"user": None})["entries"]} == {"9001"})
check("RM2448 : les réglages de l'entrée suivent la session (pas un instantané neuf)",
      next(e for e in r["entries"] if e["sid"] == "9002")["restart"] == "auto")
check("RM2448 : un split ARCHIVE (il retire quelque chose)",
      ka._history_versions() and ka._history_versions()[0][0] != v_avant)
check("RM2448 : les sessions scindées tournent toujours",
      {"9002", "9003"} <= set(LIVE))

# création simple : n'archive pas
v = ka._history_versions()[0][0]
ka.op_session_set_create({"group": "sans-split", "sids": ["9001"]}, {"user": None})
check("RM2448 : une création SANS split n'archive pas",
      ka._history_versions()[0][0] == v)

for bad, code, why in (
        ({"group": "x1", "sids": ["9001"], "move_from": "jamais-vu"}, 404, "source inconnue"),
        ({"group": "x2", "sids": ["9001"], "move_from": "x2"}, 400, "source == jeu créé")):
    try:
        ka.op_session_set_create(bad, {"user": None})
        check(f"RM2448 : {why} → {code}", False)
    except ka.ApiError as e:
        check(f"RM2448 : {why} → {code}", e.code == code)

# un sid absent du jeu source est ignoré (il peut être vivant hors jeu)
r = ka.op_session_set_create({"group": "tolerant", "sids": ["9001", "9002"],
                              "move_from": "fourre-tout"}, {"user": None})
check("RM2448 : sid absent du source ignoré sans erreur",
      r["moved"] == ["9001"] and {e["sid"] for e in r["entries"]} == {"9001", "9002"})
check("RM2448 : le jeu source vidé de sa part, sans casse",
      ka.op_session_set_get({"group": "fourre-tout"}, {"user": None})["count"] == 0)

# ── RM2449 : DÉPLACER vers un jeu EXISTANT ───────────────────────────────────
LIVE.clear()
LIVE.update({s: {"engine": "claude", "session_id": "uuid-" + s, "cwd": "/zfs/t", "model": None}
             for s in ("9101", "9102", "9103")})
ka.op_session_set_create({"group": "src-jeu", "label": "Source",
                          "sids": ["9101", "9102", "9103"]}, {"user": None})
ka.op_session_set_create({"group": "dst-jeu", "label": "Cible", "sids": ["9103"]}, {"user": None})
ka.op_session_set_restart({"group": "src-jeu", "sid": "9101", "restart": "auto"}, {"user": None})
ka.op_session_set_current({"group": "src-jeu"}, {"user": None})
v0 = ka._history_versions()[0][0] if ka._history_versions() else None

r = ka.op_session_set_move({"sids": ["9101", "9103"], "to": "dst-jeu"}, {"user": None})
dst = ka.op_session_set_get({"group": "dst-jeu"}, {"user": None})
src = ka.op_session_set_get({"group": "src-jeu"}, {"user": None})
check("RM2449 : la cible gagne la sélection, sans doublon (9103 y était déjà)",
      [e["sid"] for e in dst["entries"]] == ["9103", "9101"])
check("RM2449 : le source perd la sélection et garde le reste",
      {e["sid"] for e in src["entries"]} == {"9102"})
check("RM2449 : `from` vaut le jeu courant par défaut", r["from"] == "src-jeu")
check("RM2449 : les réglages suivent la session (entrée reprise du source)",
      next(e for e in dst["entries"] if e["sid"] == "9101")["restart"] == "auto")
check("RM2449 : un déplacement archive", ka._history_versions()[0][0] != v0)
check("RM2449 : les sessions déplacées tournent toujours", {"9101", "9103"} <= set(LIVE))

# copie : la cible gagne, le source garde
v1 = ka._history_versions()[0][0]
r = ka.op_session_set_move({"sids": ["9102"], "to": "dst-jeu", "copy": True}, {"user": None})
check("RM2449 : `copy` ajoute à la cible sans retirer du source",
      r["copied"] is True
      and "9102" in {e["sid"] for e in ka.op_session_set_get({"group": "dst-jeu"}, {"user": None})["entries"]}
      and "9102" in {e["sid"] for e in ka.op_session_set_get({"group": "src-jeu"}, {"user": None})["entries"]})
check("RM2449 : une copie n'archive pas", ka._history_versions()[0][0] == v1)

for bad, code, why in (
        ({"sids": ["9102"], "to": "jamais-vu"}, 404, "cible inexistante"),
        ({"sids": ["9102"], "to": "src-jeu"}, 400, "cible == source"),
        ({"sids": [], "to": "dst-jeu"}, 400, "sélection vide"),
        ({"sids": ["9999"], "to": "dst-jeu"}, 404, "aucun sid présent dans le source")):
    try:
        ka.op_session_set_move(bad, {"user": None})
        check(f"RM2449 : {why} → {code}", False)
    except ka.ApiError as e:
        check(f"RM2449 : {why} → {code}", e.code == code)

# plafond de la cible : refus AVANT écriture, ni source ni cible touchés
ka.SESSION_SET_MAX_SAVE = ka.SESSION_SET_MAX
ka.SESSION_SET_MAX = 2
src_avant = {e["sid"] for e in ka.op_session_set_get({"group": "src-jeu"}, {"user": None})["entries"]}
dst_avant = {e["sid"] for e in ka.op_session_set_get({"group": "dst-jeu"}, {"user": None})["entries"]}
try:
    ka.op_session_set_move({"sids": ["9102"], "to": "dst-jeu"}, {"user": None})
    check("RM2449 : plafond de la cible → 409", False)
except ka.ApiError as e:
    check("RM2449 : plafond de la cible → 409", e.code == 409)
check("RM2449 : après le refus, source ET cible sont intacts",
      {e["sid"] for e in ka.op_session_set_get({"group": "src-jeu"}, {"user": None})["entries"]} == src_avant
      and {e["sid"] for e in ka.op_session_set_get({"group": "dst-jeu"}, {"user": None})["entries"]} == dst_avant)
ka.SESSION_SET_MAX = ka.SESSION_SET_MAX_SAVE

# ── RM2450 : le jeu PLEIN remonte à l'appelant (il finissait sur stderr) ──────
LIVE.clear()
ka.op_session_set_create({"group": "plein", "label": "Plein"}, {"user": None})
ka.SESSION_SET_MAX_KEEP = ka.SESSION_SET_MAX
ka.SESSION_SET_MAX = 2
LIVE.update({s: {"engine": "claude", "session_id": "uuid-" + s, "cwd": "/zfs/u", "model": None}
             for s in ("9201", "9202", "9203")})
for s in ("9201", "9202"):
    check(f"RM2450 : {s} rejoint le jeu courant", ka._auto_join_current_set(s, {"user": None})["joined"] is True)
r = ka._auto_join_current_set("9203", {"user": None})
check("RM2450 : jeu plein ⇒ refus EXPLICITE remonté (plus de stderr muet)",
      r["joined"] is False and r["reason"] == "plein" and r["max"] == 2)
check("RM2450 : et la session n'est pas entrée dans le jeu",
      "9203" not in {e["sid"] for e in ka.op_session_set_get({"group": "plein"}, {"user": None})["entries"]})
r = ka._auto_join_current_set("9201", {"user": None})
check("RM2450 : une session déjà présente est signalée comme telle",
      r["joined"] is False and r["reason"] == "deja")
ka.SESSION_SET_MAX = ka.SESSION_SET_MAX_KEEP

# ── RM2451 : âge, coût annoncé, retrait annulable ────────────────────────────
LIVE.clear()
TR = {}          # session_id → méta de transcript simulée
ka._transcript_info = lambda sid: TR.get(sid, {})
LIVE.update({s: {"engine": "claude", "session_id": "uuid-" + s, "cwd": "/zfs/v", "model": None}
             for s in ("9301", "9302", "9303")})
TR["uuid-9301"] = {"mark": None, "title": "vieille", "mtime": 1_000_000, "bytes": 400_000}
TR["uuid-9302"] = {"mark": None, "title": "récente", "mtime": 2_000_000, "bytes": 200_000}
# 9303 : aucun transcript → relance vouée à l'échec, ne doit rien coûter
ka.op_session_set_create({"group": "cout", "label": "Coût",
                          "sids": ["9301", "9302", "9303"]}, {"user": None})

g = ka.op_session_set_get({"group": "cout"}, {"user": None})
check("RM2451 : l'âge rendu est celui de la SESSION, pas du jeu",
      {e["sid"]: e["last_active"] for e in g["entries"]}
      == {"9301": 1_000_000, "9302": 2_000_000, "9303": None})

LIVE.pop("9301"); LIVE.pop("9303")          # deux se sont arrêtées
est = ka.op_session_set_estimate({"group": "cout"}, {"user": None})
check("RM2451 : l'estimation ne compte que les entrées RELANÇABLES",
      est["relaunchable"] == 1 and est["already_live"] == 1 and est["lost"] == 1)
check("RM2451 : volume estimé depuis la taille du transcript",
      est["bytes"] == 400_000 and est["tokens_est"] == 400_000 // ka.BYTES_PER_TOKEN)
try:
    ka.op_session_set_estimate({"group": "jamais-vu"}, {"user": None})
    check("RM2451 : estimation d'un jeu absent → 404", False)
except ka.ApiError as e:
    check("RM2451 : estimation d'un jeu absent → 404", e.code == 404)

# retrait annulable : le jeton désigne l'état d'avant
r = ka.op_session_set_delete({"group": "cout", "sid": "9302"}, {"user": None})
check("RM2451 : le retrait rend un jeton d'annulation", bool(r.get("undo")))
check("RM2451 : l'entrée est bien partie",
      "9302" not in {e["sid"] for e in ka.op_session_set_get({"group": "cout"}, {"user": None})["entries"]})
ka.op_session_set_restore({"group": "cout", "id": r["undo"]}, {"user": None})
check("RM2451 : annuler rétablit exactement l'entrée",
      {e["sid"] for e in ka.op_session_set_get({"group": "cout"}, {"user": None})["entries"]}
      == {"9301", "9302", "9303"})
ka._transcript_info = lambda sid: {}

# ── RM2452 : jeux DÉRIVÉS (règle) + rétention optionnelle ────────────────────
# Le contenu se CALCULE : rien à curer, et une session neuve qui satisfait la
# règle y entre sans geste.
LIVE.clear()
KEYS = {}        # sid → info de clé (simule l'index keys/)
ka._all_keys = lambda: list(KEYS.items())
MARKS2 = {}
ka._session_mark = lambda sid: MARKS2.get(sid)
ka._transcript_title = lambda sid: None
ka._transcript_age = lambda sid: AGES.get(sid)
AGES = {}
ka._pm_project_of_cwd = lambda cwd: {"/zfs/cal": ("calicote", "prestashop"),
                                     "/zfs/inf": ("iprospective", "infra")}.get(cwd, (None, None))
KEYS.update({
    "7101": {"engine": "claude", "session_id": "u7101", "cwd": "/zfs/cal", "model": None},
    "7102": {"engine": "claude", "session_id": "u7102", "cwd": "/zfs/cal", "model": None},
    "7103": {"engine": "claude", "session_id": "u7103", "cwd": "/zfs/inf", "model": None},
})
MARKS2["u7102"] = "wip"

r = ka.op_session_set_create({"group": "der-cal", "label": "Calicote (dérivé)",
                              "rule": {"client": "calicote"}}, {"user": None})
check("RM2452 : un jeu dérivé rend le contenu de sa RÈGLE",
      r["derived"] is True and {e["sid"] for e in r["entries"]} == {"7101", "7102"})
check("RM2452 : le contenu n'est PAS stocké (seule la règle l'est)",
      "entries" not in ka._session_set_get(ka._session_set_load(), "superadmin", "der-cal"))

# une session neuve qui satisfait la règle entre sans geste
KEYS["7104"] = {"engine": "claude", "session_id": "u7104", "cwd": "/zfs/cal", "model": None}
check("RM2452 : une session neuve satisfaisant la règle y entre d'elle-même",
      {e["sid"] for e in ka.op_session_set_get({"group": "der-cal"}, {"user": None})["entries"]}
      == {"7101", "7102", "7104"})

ka.op_session_set_create({"group": "der-wip", "rule": {"mark": "wip"}}, {"user": None})
check("RM2452 : règle sur la marque [WIP]",
      {e["sid"] for e in ka.op_session_set_get({"group": "der-wip"}, {"user": None})["entries"]} == {"7102"})
ka.op_session_set_create({"group": "der-tick", "rule": {"tickets": ["7103"]}}, {"user": None})
check("RM2452 : règle sur une liste de tickets",
      {e["sid"] for e in ka.op_session_set_get({"group": "der-tick"}, {"user": None})["entries"]} == {"7103"})

for bad, why in (({}, "règle vide"), ({"client": ""}, "critères tous vides"),
                 ({"mark": "peut-etre"}, "marque inconnue"), ({"inconnu": "x"}, "critère inconnu"),
                 ({"tickets": "7103"}, "tickets non-liste")):
    try:
        ka.op_session_set_create({"group": "der-bad", "rule": bad}, {"user": None})
        check(f"RM2452 : {why} → 400", False)
    except ka.ApiError as e:
        check(f"RM2452 : {why} → 400", e.code == 400)
try:
    ka.op_session_set_create({"group": "der-mix", "rule": {"client": "calicote"},
                              "sids": ["7101"]}, {"user": None})
    check("RM2452 : règle ET liste ⇒ 400", False)
except ka.ApiError as e:
    check("RM2452 : règle ET liste ⇒ 400", e.code == 400)

# on ne modifie pas à la main un ensemble CALCULÉ
ka.op_session_set_current({"group": "der-cal"}, {"user": None})
for call, why in (
        (lambda: ka.op_session_set_save({"group": "der-cal"}, {"user": None}), "enregistrer"),
        (lambda: ka.op_session_set_delete({"group": "der-cal", "sid": "7101"}, {"user": None}), "retirer"),
        (lambda: ka.op_session_set_move({"sids": ["7101"], "to": "der-cal", "from": "der-wip"}, {"user": None}), "déplacer vers"),
        (lambda: ka.op_session_set_create({"group": "issu", "sids": ["7101"], "move_from": "der-cal"}, {"user": None}), "scinder depuis")):
    try:
        call()
        check(f"RM2452 : {why} sur un jeu dérivé → 400", False)
    except ka.ApiError as e:
        check(f"RM2452 : {why} sur un jeu dérivé → 400", e.code == 400)
check("RM2452 : l'adhésion automatique ne touche pas un jeu dérivé",
      ka._auto_join_current_set("7103", {"user": None})["reason"] == "derive")

# matérialiser : le meilleur des deux
m = ka.op_session_set_materialize({"group": "der-cal"}, {"user": None})
check("RM2452 : matérialiser fige le contenu en jeu manuel",
      m["derived"] is False and {e["sid"] for e in m["entries"]} == {"7101", "7102", "7104"})
KEYS["7105"] = {"engine": "claude", "session_id": "u7105", "cwd": "/zfs/cal", "model": None}
check("RM2452 : une fois figé, il n'absorbe plus les nouvelles venues",
      "7105" not in {e["sid"] for e in ka.op_session_set_get({"group": "der-cal"}, {"user": None})["entries"]})
try:
    ka.op_session_set_materialize({"group": "der-cal"}, {"user": None})
    check("RM2452 : matérialiser un jeu déjà manuel → 400", False)
except ka.ApiError as e:
    check("RM2452 : matérialiser un jeu déjà manuel → 400", e.code == 400)

# rétention : OPTION, jamais par défaut, et masque sans supprimer
LIVE.clear()
AGES.update({"u7101": time.time() - 40 * 86400, "u7102": time.time() - 1 * 86400,
             "u7104": time.time() - 60 * 86400})
g = ka.op_session_set_get({"group": "der-cal"}, {"user": None})
check("RM2452 : par défaut, aucune rétention", g["hide_idle_days"] == 0)
check("RM2452 : par défaut, rien n'est masqué",
      len(ka._ghost_sessions({"user": None})) == 3)
ka.op_session_set_retention({"group": "der-cal", "days": 30}, {"user": None})
check("RM2452 : rétention activée ⇒ les inactives sortent de l'AFFICHAGE",
      {x["rm_id"] for x in ka._ghost_sessions({"user": None})} == {"7102"})
check("RM2452 : mais elles RESTENT dans le jeu (masquer ≠ supprimer)",
      len(ka.op_session_set_get({"group": "der-cal"}, {"user": None})["entries"]) == 3)
check("RM2452 : on les revoit à la demande",
      len(ka._ghost_sessions({"user": None}, show_old=True)) == 3)
ka.op_session_set_retention({"group": "der-cal", "days": 0}, {"user": None})
check("RM2452 : rétention désactivable",
      len(ka._ghost_sessions({"user": None})) == 3)
for bad in (-1, "beaucoup", None):
    try:
        ka.op_session_set_retention({"group": "der-cal", "days": bad}, {"user": None})
        check(f"RM2452 : rétention invalide ({bad!r}) → 400", False)
    except ka.ApiError as e:
        check(f"RM2452 : rétention invalide ({bad!r}) → 400", e.code == 400)

# RM2452 : une sélection de tuiles GRISES doit produire un vrai jeu (l'instantané
# tmux ne connaît que les vivantes — un jeu vide aurait été le résultat)
LIVE.clear()
ka._all_keys = lambda: []
ka._transcript_title = lambda sid: None
ka._key_info = lambda sid: LIVE.get(sid) or KEYS.get(sid)
ka.op_session_set_create({"group": "src-gris", "sids": []}, {"user": None})
ka.op_session_set_current({"group": "src-gris"}, {"user": None})
store = ka._session_set_load()
rec = ka._session_set_get(store, "superadmin", "src-gris")
rec["entries"] = [{"sid": "7301", "engine": "claude", "session_id": "u7301",
                   "cwd": "/zfs/g", "model": None, "title": "éteinte", "restart": "idle"}]
ka._write_session_set(store, archive=False)
r = ka.op_session_set_create({"group": "depuis-gris", "sids": ["7301"]}, {"user": None})
check("RM2452 : un jeu créé depuis une session ÉTEINTE n'est pas vide",
      [e["sid"] for e in r["entries"]] == ["7301"] and r["entries"][0]["title"] == "éteinte")

# ── RM2452 (suite) : méta-jeux par client, édition de règle ──────────────────
KEYS.clear()
KEYS.update({
    "7401": {"engine": "claude", "session_id": "u7401", "cwd": "/zfs/cal", "model": None},
    "7402": {"engine": "claude", "session_id": "u7402", "cwd": "/zfs/cal", "model": None},
    "7403": {"engine": "claude", "session_id": "u7403", "cwd": "/zfs/inf", "model": None},
})
ka._all_keys = lambda: list(KEYS.items())
LIVE.clear()
l = ka.op_session_sets_list({}, {"user": None})
cv = {c["view"]: c for c in l["client_views"]}
check("RM2452 : un méta-jeu par client AYANT des sessions",
      set(cv) == {"client:calicote", "client:iprospective"})
check("RM2452 : le méta-jeu porte son compte", cv["client:calicote"]["count"] == 2)
check("RM2452 : les facettes listent clients et projets",
      [c["slug"] for c in l["facets"]["clients"]] == ["calicote", "iprospective"]
      and l["facets"]["clients"][0]["projects"] == ["prestashop"])

ka.op_session_set_current({"view": "client:calicote"}, {"user": None})
check("RM2452 : la vue par client se résout sans rien créer",
      {g["rm_id"] for g in ka._ghost_sessions({"user": None})} == {"7401", "7402"})
check("RM2452 : la tuile dit de quel méta-jeu elle vient",
      all(g["group_label"] == "calicote" for g in ka._ghost_sessions({"user": None})))
check("RM2452 : aucun jeu n'a été créé au passage",
      "client:calicote" not in {s["name"] for s in ka.op_session_sets_list({}, {"user": None})["sets"]})
try:
    ka.op_session_set_current({"view": "client:PAS UN SLUG"}, {"user": None})
    check("RM2452 : vue client invalide → 400", False)
except ka.ApiError as e:
    check("RM2452 : vue client invalide → 400", e.code == 400)
ka.op_session_set_current({"view": "set"}, {"user": None})

# éditer la règle d'un jeu dérivé
ka.op_session_set_create({"group": "edit-der", "rule": {"client": "calicote"}}, {"user": None})
r = ka.op_session_set_rule({"group": "edit-der", "rule": {"client": "iprospective"}}, {"user": None})
check("RM2452 : la règle se modifie, le contenu suit",
      r["rule"] == {"client": "iprospective"} and {e["sid"] for e in r["entries"]} == {"7403"})
try:
    ka.op_session_set_rule({"group": "edit-der", "rule": {}}, {"user": None})
    check("RM2452 : règle vide au remplacement → 400", False)
except ka.ApiError as e:
    check("RM2452 : règle vide au remplacement → 400", e.code == 400)
ka.op_session_set_create({"group": "manuel-x", "sids": []}, {"user": None})
try:
    ka.op_session_set_rule({"group": "manuel-x", "rule": {"client": "calicote"}}, {"user": None})
    check("RM2452 : poser une règle sur un jeu MANUEL → 400", False)
except ka.ApiError as e:
    check("RM2452 : poser une règle sur un jeu MANUEL → 400", e.code == 400)

# ── RM2452 : hygiène des dérivés — [DONE] écartées, troncature annoncée ──────
# Une vue client affichait 12 sessions CLOSES sur 25 : les jeux manuels les
# évincent depuis RM2427, le chemin dérivé contournait la règle.
KEYS.clear()
KEYS.update({s: {"engine": "claude", "session_id": "u" + s, "cwd": "/zfs/cal", "model": None}
             for s in ("7501", "7502", "7503")})
ka._all_keys = lambda: list(KEYS.items())
MARKS2.clear(); MARKS2["u7502"] = "done"
# `_is_marked_done` a été doublé plus haut par le scénario [DONE] : on le
# raccorde à la même source que `_session_mark` pour ce bloc
ka._is_marked_done = lambda sid: MARKS2.get(sid) == "done"
LIVE.clear()
check("RM2452 : une session [DONE] et éteinte est écartée d'un dérivé",
      {e["sid"] for e in ka._derived_entries({"client": "calicote"})} == {"7501", "7503"})
LIVE["7502"] = KEYS["7502"]            # la [DONE] se remet à tourner
check("RM2452 : mais une [DONE] VIVANTE reste listée (on n'escamote pas un processus)",
      "7502" in {e["sid"] for e in ka._derived_entries({"client": "calicote"})})
LIVE.clear()

# le plafond ne tronque plus en silence
KEYS.update({str(7600 + i): {"engine": "claude", "session_id": f"u{7600+i}",
                             "cwd": "/zfs/cal", "model": None} for i in range(30)})
ents, total = ka._derived_entries({"client": "calicote"}, with_total=True)
check("RM2452 : le plafond s'applique toujours", len(ents) == ka.SESSION_SET_MAX)
check("RM2452 : mais le total RÉEL est rendu (plus de troncature muette)", total > len(ents))
ka.op_session_set_create({"group": "gros-der", "rule": {"client": "calicote"}}, {"user": None})
g = ka.op_session_set_get({"group": "gros-der"}, {"user": None})
check("RM2452 : le jeu annonce sa troncature",
      g["truncated"] is True and g["total"] == total and len(g["entries"]) == ka.SESSION_SET_MAX)
l = ka.op_session_sets_list({}, {"user": None})
cv = {c["view"]: c["count"] for c in l["client_views"]}
check("RM2452 : le compteur du méta-jeu compte ce qu'on VERRA (hors [DONE])",
      cv["client:calicote"] == len(ents))

# RM2452 : une vue par CLIENT ne s'approprie pas les vivantes des autres clients
KEYS.clear()
KEYS.update({"7701": {"engine": "claude", "session_id": "u7701", "cwd": "/zfs/cal", "model": None},
             "7702": {"engine": "claude", "session_id": "u7702", "cwd": "/zfs/inf", "model": None}})
ka._all_keys = lambda: list(KEYS.items())
MARKS2.clear()
LIVE.clear(); LIVE.update(KEYS)          # les deux tournent
ka.op_session_set_current({"view": "client:iprospective"}, {"user": None})
vue = {s["rm_id"]: s for s in ka._sessions_view({}, {"user": None}) if not s.get("ghost")}
check("RM2452 : la vivante du client regardé appartient à la vue",
      vue["7702"]["in_current"] is True)
check("RM2452 : celle d'un AUTRE client est rangée hors de la vue (et badgée)",
      vue["7701"]["in_current"] is False)
check("RM2452 : mais elle reste VISIBLE (jamais de processus escamoté)",
      set(vue) == {"7701", "7702"})
ka.op_session_set_current({"view": "all"}, {"user": None})
check("RM2452 : en vue « tous les jeux », tout ce qui est affiché appartient à la vue",
      all(s["in_current"] for s in ka._sessions_view({}, {"user": None}) if not s.get("ghost")))
ka.op_session_set_current({"view": "set"}, {"user": None})

# ── RM2537 : un jeu DÉRIVÉ courant ne relègue pas ses propres sessions ────────
# L'appartenance aux jeux était lue sur `rec["entries"]` en dur : vide pour un
# jeu à règle, donc `in_current: False` pour ses propres sessions — le cockpit
# les rangeait dans « hors du jeu courant », sans en-tête client/projet.
KEYS.clear()
KEYS.update({"7901": {"engine": "claude", "session_id": "u7901", "cwd": "/zfs/inf", "model": None},
             "7902": {"engine": "claude", "session_id": "u7902", "cwd": "/zfs/cal", "model": None}})
ka._all_keys = lambda: list(KEYS.items())
LIVE.clear(); LIVE.update(KEYS)
MARKS2.clear()
ka.op_session_set_create({"group": "der-courant", "rule": {"client": "iprospective"}}, {"user": None})
ka.op_session_set_current({"group": "der-courant"}, {"user": None})
vue = {s["rm_id"]: s for s in ka._sessions_view({}, {"user": None}) if not s.get("ghost")}
check("RM2537 : une session du jeu dérivé COURANT lui appartient",
      vue["7901"]["in_current"] is True)
check("RM2537 : et elle porte le badge de son jeu (plus de tuile orpheline)",
      "der-courant" in vue["7901"]["sets"])
check("RM2537 : une session hors de la règle reste hors du jeu",
      vue["7902"]["in_current"] is False and "der-courant" not in vue["7902"]["sets"])
# non-régression : un jeu MANUEL courant se comporte comme avant
ka.op_session_set_create({"group": "manuel-courant", "sids": ["7902"]}, {"user": None})
ka.op_session_set_current({"group": "manuel-courant"}, {"user": None})
vue = {s["rm_id"]: s for s in ka._sessions_view({}, {"user": None}) if not s.get("ghost")}
check("RM2537 : jeu manuel courant — comportement inchangé",
      vue["7902"]["in_current"] is True and vue["7901"]["in_current"] is False)
ka.op_session_set_current({"group": "default"}, {"user": None})
# ── RM2536 : la relance ne dépend plus du contexte d'affichage ────────────────
# Le clic sur une tuile envoyait le `group` de son contexte ; dans une vue par
# client, ce champ vaut la clé de VUE (« client:matnat »), refusée comme nom de
# jeu (400 « nom de groupe invalide ») — rien ne démarrait. La relance passe
# désormais par l'IDENTITÉ de la session : le couple (engine, session_id).

# la clé de vue n'est toujours PAS un nom de jeu (on ne relâche pas la grammaire
# des jeux persistés — c'est l'appelant qui n'a plus à parler de jeu)
try:
    ka._session_set_group("client:matnat")
    check("RM2536 : la clé de vue reste un nom de jeu invalide", False)
except ka.ApiError as e:
    check("RM2536 : la clé de vue reste un nom de jeu invalide (400)", e.code == 400)

ka.op_resume, ka.op_spawn = REAL_OP_RESUME, REAL_OP_SPAWN   # fin des doublures
ka._runs_by_session = REAL_RUNS_BY_SESSION                   # vraies jonctions sur disque
SESS = TMP / "sessions"; RUNS = TMP / "tasks"; STORE = TMP / "claude-store"
ka.SESS_DIR, ka.RUNS_DIR, ka.CLAUDE_STORES = SESS, RUNS, [STORE]
(SESS / "claude").mkdir(parents=True, exist_ok=True)
(SESS / "opencode").mkdir(parents=True, exist_ok=True)
ka._write_json_atomic(SESS / "claude" / "aaaa1111-2222-3333-4444-555566667777.json",
                      {"engine": "claude", "session_id": "aaaa1111-2222-3333-4444-555566667777", "cwd": "/zfs/matnat/infra"})
ka._write_json_atomic(SESS / "opencode" / "bbbb1111-2222-3333-4444-555566667777.json",
                      {"engine": "opencode", "session_id": "bbbb1111-2222-3333-4444-555566667777", "cwd": "/zfs/x"})

# — moteur : l'index fait foi, jamais le client —
check("RM2536 : moteur retrouvé depuis le store par session",
      ka._engine_of_session("aaaa1111-2222-3333-4444-555566667777") == "claude" and ka._engine_of_session("bbbb1111-2222-3333-4444-555566667777") == "opencode")
check("RM2536 : session inconnue de l'index → moteur inconnu (pas de défaut inventé)",
      ka._engine_of_session("eeee1111-2222-3333-4444-555566667777") is None)
try:
    ka.op_resume({"session_id": "bbbb1111-2222-3333-4444-555566667777", "engine": "claude"}, {"user": None})
    check("RM2536 : moteur du client contredisant l'index → refus", False)
except ka.ApiError as e:
    check("RM2536 : moteur du client contredisant l'index → refus (409)", e.code == 409)

# — ancrage rm_id : le PROJET du cwd prime sur la récence (modèle n-m) —
for client, project, rid, n, seen in (("matnat", "infra", "2410", 1, 100),
                                      ("matnat", "infra", "2411", 2, 200),
                                      ("iprospective", "pm-ai-agents", "2536", 3, 900)):
    d = RUNS / client / project
    d.mkdir(parents=True, exist_ok=True)
    ka._write_json_atomic(d / f"RM{rid}-{n}.json",
                          {"rm_id": rid, "n": n, "session_id": "aaaa1111-2222-3333-4444-555566667777",
                           "engine": "claude", "created": seen, "last_seen": seen})
_PROJ = {"/zfs/matnat/infra": ("matnat", "infra"),
         "/zfs/iprospective/pm": ("iprospective", "pm-ai-agents")}
ka._pm_project_of_cwd = lambda cwd: _PROJ.get(cwd or "", (None, None))
check("RM2536 : ancrage sur le ticket du projet du cwd, pas sur le plus récent d'un autre projet",
      ka._anchor_rm_id("aaaa1111-2222-3333-4444-555566667777", "/zfs/matnat/infra") == "2411")
check("RM2536 : cwd d'un autre projet → jonction la plus récente (comportement historique)",
      ka._anchor_rm_id("aaaa1111-2222-3333-4444-555566667777", "/zfs/iprospective/pm") == "2536")
check("RM2536 : cwd inconnu du PM → comportement historique",
      ka._anchor_rm_id("aaaa1111-2222-3333-4444-555566667777", "/zfs/ailleurs") == "2536")
check("RM2536 : aucune jonction → pas d'ancrage (le slug prendra le relais)",
      ka._anchor_rm_id("uuid-inconnue", "/zfs/matnat/infra") is None)
# jonctions du bon projet SANS récence connue → l'initiale (n minimal)
d = RUNS / "calyclay" / "site"; d.mkdir(parents=True, exist_ok=True)
for rid, n in (("7801", 1), ("7802", 2)):
    ka._write_json_atomic(d / f"RM{rid}-{n}.json",
                          {"rm_id": rid, "n": n, "session_id": "cccc1111-2222-3333-4444-555566667777", "engine": "claude"})
_PROJ["/zfs/calyclay/site"] = ("calyclay", "site")
check("RM2536 : sans récence, on retient la jonction INITIALE du projet",
      ka._anchor_rm_id("cccc1111-2222-3333-4444-555566667777", "/zfs/calyclay/site") == "7801")

# — relance NUE : ni jeu, ni vue, ni cwd fourni ; le serveur retrouve le reste —
STARTED = []
ka._has_session = lambda sid: False
ka._start_session_tmux = lambda sid, cmd, cwd, w, h, extra: STARTED.append((sid, cmd, str(cwd)))
ka._record_run = lambda *a, **k: None
ka._record_key = lambda *a, **k: None
ka._auto_join_current_set = lambda sid, ctx=None: None
ka._resolve_cwd = lambda cwd: pathlib.Path(cwd or "/")
(STORE / "slug").mkdir(parents=True, exist_ok=True)
(STORE / "slug" / "aaaa1111-2222-3333-4444-555566667777.jsonl").write_text('{"cwd":"/zfs/matnat/infra"}\n', encoding="utf-8")
ka.op_session_set_current({"view": "client:matnat"}, {"user": None})
r = ka.op_resume({"session_id": "aaaa1111-2222-3333-4444-555566667777", "engine": "claude"}, {"user": None})
check("RM2536 : relance depuis une vue client, sans aucun contexte de jeu",
      r["resumed"] is True and r["session_id"] == "aaaa1111-2222-3333-4444-555566667777")
check("RM2536 : elle s'ancre sur le ticket du projet de la session",
      r["rm_id"] == "2411" and STARTED and STARTED[-1][0] == "2411")
check("RM2536 : le resume natif porte bien le session_id",
      "--resume" in STARTED[-1][1] and "aaaa1111-2222-3333-4444-555566667777" in STARTED[-1][1])
ka.op_session_set_current({"view": "set"}, {"user": None})

# — repli « session neuve » : opt-in, et alimenté par l'index des clés —
LIVE["2410"] = {"engine": "claude", "session_id": "dd001111-2222-3333-4444-555566667777",
                "cwd": "/zfs/matnat/infra", "model": None}
ka._write_json_atomic(SESS / "claude" / "dd001111-2222-3333-4444-555566667777.json",
                      {"engine": "claude", "session_id": "dd001111-2222-3333-4444-555566667777", "cwd": "/zfs/matnat/infra"})
try:
    ka.op_resume({"session_id": "dd001111-2222-3333-4444-555566667777", "rm_id": "2410"}, {"user": None})
    check("RM2536 : transcript perdu sans opt-in → refus motivé", False)
except ka.ApiError as e:
    # RM2539 : le libellé nomme la CONVERSATION et son moteur (« transcript »
    # ne veut rien dire pour un moteur qui range ses sessions en base).
    check("RM2536 : transcript perdu sans opt-in → refus motivé (410)",
          e.code == 410 and "introuvable côté claude" in e.msg)
SPAWNED_2536 = []
ka.op_spawn = lambda payload, ctx=None: (SPAWNED_2536.append(payload) or {"rm_id": payload["rm_id"]})
r = ka.op_resume({"session_id": "dd001111-2222-3333-4444-555566667777", "rm_id": "2410", "spawn": True}, {"user": None})
check("RM2536 : avec l'opt-in, session neuve annoncée comme telle",
      r.get("spawned") is True and r.get("resumed") is False)
check("RM2536 : son dossier vient de l'index des clés, pas du client",
      SPAWNED_2536 and SPAWNED_2536[-1]["cwd"] == "/zfs/matnat/infra")
LIVE["sans-cwd"] = {"engine": "claude", "session_id": "dd002222-2222-3333-4444-555566667777", "cwd": None, "model": None}
try:
    ka.op_resume({"session_id": "dd002222-2222-3333-4444-555566667777", "rm_id": "sans-cwd", "spawn": True}, {"user": None})
    check("RM2536 : rien de mémorisé à rouvrir → refus explicite", False)
except ka.ApiError as e:
    check("RM2536 : rien de mémorisé à rouvrir → refus explicite (410)", e.code == 410)


if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests jeux de sessions RM2395/RM2427 passent")
