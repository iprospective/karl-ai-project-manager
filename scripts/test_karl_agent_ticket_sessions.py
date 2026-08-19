#!/usr/bin/env python3
"""Tests RM2726 — « qui traite ce ticket, et où le lancer » (fiche du ticket).

Ce qu'on protège :
  - les TROIS sources de « cette session traite ce ticket » (ancrage, registre
    pm_session, worklog) — la troisième est la seule qui voie une session lancée
    sur un slug, cas le plus courant chez le demandeur ;
  - une session ÉTEINTE qui a traité le ticket reste visible (« existe mais ne
    tourne plus » ≠ « personne ne s'en occupe ») mais n'est jamais proposée
    comme destination : on n'envoie pas un prompt à un fantôme ;
  - les destinations sont triées avec les sessions DU MÊME PROJET d'abord ;
  - une session qui traite déjà le ticket n'est pas re-proposée comme cible ;
  - `own_alive` dit que la session d'ancrage tourne — c'est ce qui empêche de
    proposer un /spawn que le serveur refuserait (409) ;
  - le tri des sids est numérique pour les tickets (999 avant 1000).

Lancer : python3 scripts/test_karl_agent_ticket_sessions.py
"""
import importlib.util
import pathlib
import sys

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


def raises(code, fn):
    try:
        fn()
        return False
    except ka.ApiError as e:
        return e.code == code


CP = {"client": "iprospective", "project": "pm-ai-agents"}
SESSIONS = [
    # la session d'ancrage du ticket
    dict(rm_id="2726", is_ticket=True, state="idle", title="[WIP] fiche ticket", **CP),
    # une session slug du même projet : elle a le ticket dans son WORKLOG seulement
    dict(rm_id="cockpit", is_ticket=False, state="idle", title="cockpit", **CP),
    # une session slug d'un autre projet, libre
    {"rm_id": "presta", "is_ticket": False, "state": "idle", "title": "presta",
     "client": "acme", "project": "boutique"},
    # une session qui porte la BRANCHE du ticket (registre pm_session)
    dict(rm_id="2700", is_ticket=True, state="idle", title="autre ticket",
         registry={"branches": ["2726-fiche-ticket", "2700-x"], "worktrees": []}, **CP),
    # une session éteinte (fantôme) qui a traité le ticket
    dict(rm_id="vieille", is_ticket=False, ghost=True, state="ghost", title="hier",
         registry={"branches": [], "worktrees": ["/w/envs/ai-pm-rm2726"]}, **CP),
]
WL = {"cockpit": ["RM2726", "RM2700"], "presta": ["RM2600"]}

v = ka.ticket_sessions_view("2726", SESSIONS, WL, "iprospective", "pm-ai-agents")
by_sid = {r["sid"]: r for r in v["handled"]}

check("les trois sources sont reconnues",
      set(by_sid) == {"2726", "cockpit", "2700", "vieille"}, sorted(by_sid))
check("ancrage : le sid EST l'id du ticket", by_sid["2726"]["reasons"] == ["ancrage"])
check("registre : branche <id>-… de la session d'un AUTRE ticket",
      by_sid["2700"]["reasons"] == ["registre"]
      and by_sid["2700"]["branch"] == "2726-fiche-ticket")
check("worklog : session sur slug, sans branche ni ancrage",
      by_sid["cockpit"]["reasons"] == ["worklog"])
check("worktree …-rm<id> compte comme registre",
      by_sid["vieille"]["reasons"] == ["registre"])
check("une session éteinte est rendue, marquée non vivante",
      by_sid["vieille"]["alive"] is False and by_sid["2726"]["alive"] is True)
check("les vivantes passent devant les éteintes",
      [r["sid"] for r in v["handled"]] == ["2726", "2700", "cockpit", "vieille"],
      [r["sid"] for r in v["handled"]])

check("destinations : seules les sessions qui NE traitent PAS déjà le ticket",
      [r["sid"] for r in v["candidates"]] == ["presta"],
      [r["sid"] for r in v["candidates"]])
check("un fantôme n'est jamais une destination",
      all(r["alive"] for r in v["candidates"]))
check("live : une session vivante traite le ticket", v["live"] is True)
check("own_alive : la session d'ancrage tourne (un /spawn ferait 409)",
      v["own_alive"] is True)

# — même projet d'abord —
MANY = [
    {"rm_id": "zeta", "client": "iprospective", "project": "pm-ai-agents"},
    {"rm_id": "alpha", "client": "acme", "project": "boutique"},
    {"rm_id": "999", "client": "iprospective", "project": "pm-ai-agents"},
    {"rm_id": "1000", "client": "iprospective", "project": "pm-ai-agents"},
]
v2 = ka.ticket_sessions_view("2726", MANY, {}, "iprospective", "pm-ai-agents")
check("destinations : même projet d'abord, tickets par numéro puis slugs",
      [r["sid"] for r in v2["candidates"]] == ["999", "1000", "zeta", "alpha"],
      [r["sid"] for r in v2["candidates"]])
check("same_project est porté par chaque destination",
      [r["same_project"] for r in v2["candidates"]] == [True, True, True, False])
check("aucune session ne traite le ticket → handled vide, sans live",
      v2["handled"] == [] and v2["live"] is False and v2["own_alive"] is False)

# — le ticket dont on ne connaît ni client ni projet : pas de « même projet » inventé —
v3 = ka.ticket_sessions_view("2726", MANY, {}, None, None)
check("sans client/projet du ticket, aucune destination n'est dite du bon projet",
      not any(r["same_project"] for r in v3["candidates"]))

# — session vivante ET éteinte du même ticket : la vivante gagne la tête —
v4 = ka.ticket_sessions_view("42", [
    {"rm_id": "42", "ghost": True, "state": "ghost"},
    {"rm_id": "b", "registry": {"branches": ["42-x"]}},
], {})
check("une session d'ancrage ÉTEINTE ne rend pas own_alive",
      v4["own_alive"] is False and v4["live"] is True)
check("l'éteinte passe derrière la vivante, quelle que soit la source",
      [r["sid"] for r in v4["handled"]] == ["b", "42"])

# — l'entrée : un id de ticket, pas un slug —
check("un slug est refusé (400) : la fiche est celle d'un TICKET",
      raises(400, lambda: ka.op_ticket_sessions("cockpit")))
check("une entrée vide est refusée (400)",
      raises(400, lambda: ka.op_ticket_sessions("")))

# — bout en bout, sources stubbées : l'op assemble sans rien inventer —
ka._sessions_view = lambda qs, ctx=None: [
    {"rm_id": "2726", "session_id": "s1", "client": "iprospective",
     "project": "pm-ai-agents", "title": None},
    {"rm_id": "libre", "session_id": "s2", "client": "iprospective",
     "project": "pm-ai-agents", "title": None},
]
ka._transcript_title = lambda sid: {"s1": "session du ticket", "s2": "session libre"}.get(sid)
ka._overview_worklog = lambda sid: {"items": [{"ref": "RM2726"}]} if sid == "s2" else None
ka._find_task_file = lambda rm: None
out = ka.op_ticket_sessions("2726")
check("op : le titre du transcript nomme les sessions sans titre",
      {r["sid"]: r["title"] for r in out["handled"]}
      == {"2726": "session du ticket", "libre": "session libre"})
check("op : le worklog d'une session slug la range dans handled",
      {r["sid"] for r in out["handled"]} == {"2726", "libre"} and out["candidates"] == [])

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests sessions du ticket RM2726 passent")
