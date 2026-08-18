#!/usr/bin/env python3
"""Tests RM2696 (T2 de RM2694) — agrégat /overview par projet.

Ce qu'on protège :
  - l'agrégat ne rend QUE des données déjà connues (index des tâches, index des
    clés, worklogs sur disque) — aucune saisie nouvelle ;
  - un ticket actif dont plus AUCUNE session ne parle reste visible et signalé :
    c'est le cas qu'on perd de vue, et la raison d'être de cette vue ;
  - la garde de fraîcheur (60 s) évite de rejouer le calcul à chaque poll ;
  - le filtre client/projet ne laisse pas fuiter un autre projet.

Tout est monté en tmpdir : ni tmux, ni réseau, ni état du poste.
Lancer : python3 scripts/test_karl_agent_overview.py
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


TMP = pathlib.Path(tempfile.mkdtemp(prefix="rm2696-"))


def task(client, project, rm_id, status, title, body=""):
    d = TMP / "clients" / client / "projects" / project / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"RM{rm_id}_t.md").write_text(
        f"---\nredmine_id: {rm_id}\ntitle: {title}\nstatus: {status}\npriority: normal\ntype: feature\n---\n\n{body}\n",
        encoding="utf-8")


# projet A : un ticket suivi par une session vivante, un ticket ORPHELIN, un en attente
task("acme", "shop", "10", "en_cours", "suivi", "## Critères\n\n- [x] a\n- [ ] b\n")
task("acme", "shop", "11", "en_cours", "orphelin", "- [ ] rien de fait\n")
task("acme", "shop", "12", "a_tester_demandeur", "en attente")
task("acme", "shop", "13", "ferme", "fermé — ne doit pas apparaître")
# projet B : ne doit jamais apparaître quand on filtre sur A
task("beta", "api", "20", "en_cours", "autre projet")

ka.PROJECTS_BASE = TMP / "clients"

# index des clés : deux sessions sur acme/shop (une vivante, une éteinte)
KEYS = [("70", {"cwd": "/w/acme/shop", "session_id": "sid-live"}),
        ("71", {"cwd": "/w/acme/shop", "session_id": "sid-dead"}),
        ("80", {"cwd": "/w/beta/api", "session_id": "sid-beta"})]
ka._all_keys = lambda: KEYS
ka._list_sessions = lambda: [{"rm_id": "70"}]          # seule 70 tourne
ka._pm_project_of_cwd = lambda cwd: (("acme", "shop") if cwd and "acme" in cwd
                                     else ("beta", "api") if cwd else (None, None))
ka._transcript_title = lambda sid: "titre " + str(sid)

WL = {
    "sid-live": {"items": [{"ref": "RM10", "status": "en_cours"}],
                 "mrs": [{"iid": "1", "repo": "r", "ref": "RM10", "target": "dev", "state": "opened"},
                         {"iid": "2", "repo": "r", "ref": "RM10", "state": "merged"}],
                 "requests": [{"text": "une demande", "status": "nouveau"},
                              {"text": "déjà ticketée", "status": "ticketee"}]},
    "sid-dead": {"items": [{"ref": "RM12", "status": "a_tester_demandeur"}],
                 "mrs": [{"iid": "9", "repo": "r", "ref": "RM12", "state": "opened"}]},
    "sid-beta": {"items": [{"ref": "RM20", "status": "en_cours"}], "mrs": []},
}
ka._overview_worklog = lambda sid: WL.get(sid)

ka._overview_cache.clear()
d = ka.op_overview({"client": "acme", "project": "shop"})
check("un seul projet rendu (filtre respecté)", d["count"] == 1, str(d["count"]))
g = d["projects"][0]
check("le projet filtré est le bon", g["key"] == "acme/shop")
check("aucun ticket d'un autre projet", all(t["client"] == "acme" for t in g["tickets"]))
check("un ticket fermé n'est pas repris", all(t["rm_id"] != "13" for t in g["tickets"]))

rows = {t["rm_id"]: t for t in g["tickets"]}
check("ticket actif suivi par une session vivante", rows["10"]["has_live_session"] is True)
check("…et la session est nommée", rows["10"]["sessions"] == ["70"])
check("ticket ORPHELIN visible (aucune session n'en parle)", "11" in rows)
check("…et signalé comme tel",
      rows["11"]["has_live_session"] is False and rows["11"]["sessions"] == [])
check("ticket vu par une session ÉTEINTE : pas de session vivante",
      rows["12"]["sessions"] == ["71"] and rows["12"]["has_live_session"] is False)
check("l'avancement (checklist RM2695) est joint", rows["10"]["checklist"]["done"] == 1
      and rows["10"]["checklist"]["total"] == 2)
check("un ticket sans checklist n'en invente pas", "checklist" not in rows["12"])
check("les tickets actifs SANS session vivante passent en tête",
      [t["rm_id"] for t in g["tickets"]][:2] == ["11", "10"],
      str([t["rm_id"] for t in g["tickets"]]))

check("MR ouvertes seulement", [m["iid"] for m in g["mrs"]] == ["1", "9"], str(g["mrs"]))
check("une MR laissée par une session éteinte est signalée",
      next(m for m in g["mrs"] if m["iid"] == "9")["alive"] is False)
check("demandes : les traitées sont exclues",
      [r["text"] for r in g["requests"]] == ["une demande"])
check("sessions du projet : vivantes ET éteintes, vivantes d'abord",
      [(s["sid"], s["alive"]) for s in g["sessions"]] == [("70", True), ("71", False)])

c = g["counts"]
check("compteurs cohérents",
      (c["active"], c["waiting"], c["orphans"], c["mrs"], c["sessions_live"], c["requests"])
      == (2, 1, 1, 2, 1, 1), str(c))

# — garde de fraîcheur : le second appel ne recalcule pas —
d2 = ka.op_overview({"client": "acme", "project": "shop"})
check("second appel servi par le cache", d2["cached"] is True)
task("acme", "shop", "14", "en_cours", "ajouté après le cache")
d3 = ka.op_overview({"client": "acme", "project": "shop"})
check("le cache masque bien le recalcul (60 s)", len(d3["projects"][0]["tickets"]) == 3)
d4 = ka.op_overview({"client": "acme", "project": "shop", "force": "1"})
check("`force` contourne la garde", len(d4["projects"][0]["tickets"]) == 4 and d4["cached"] is False)

# — sans filtre : tous les projets, triés par activité —
ka._overview_cache.clear()
allp = ka.op_overview({})
check("sans filtre, tous les projets sont rendus", allp["count"] == 2, str(allp["count"]))
check("le plus actif d'abord", allp["projects"][0]["key"] == "acme/shop")
check("filtered dit si un filtre s'applique",
      allp["filtered"] is False and d["filtered"] is True)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests agrégat /overview RM2696 passent")
