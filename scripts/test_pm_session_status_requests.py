#!/usr/bin/env python3
"""Tests RM2635 — le registre des demandes ne doit capturer que des demandes.

Le rattrapage de RM2621 avait avalé un résumé de compaction de 17 000 signes et
cinq collages de console : 41 lignes « à traiter » dont la moitié n'appelait
aucune décision. Un registre censé garantir qu'aucune demande ne se perd devient
inutile dès qu'il faut le relire en entier pour y trouver les vraies.

Les deux directions d'erreur ne se valent pas et les tests le disent :
laisser passer du bruit coûte une ligne à trier ; écarter une vraie demande la
fait disparaître. Le second cas est celui qu'on verrouille le plus.

Lancer : python3 scripts/test_pm_session_status_requests.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pss", HERE / "pm-session-status.py")
pss = importlib.util.module_from_spec(spec)
sys.modules["pss"] = pss
spec.loader.exec_module(pss)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# ── ce qui doit être écarté ──────────────────────────────────────────────────
COMPACT = ("This session is being continued from a previous conversation that ran out "
           "of context. The summary below covers the earlier portion. " + "x" * 9000)
check("un résumé de compaction n'est pas une demande",
      pss.request_is_noise(COMPACT) == "paste")
check("un collage de console l'est encore moins",
      pss.request_is_noise('keydown {"key":"Process","keyCode":229,"isComposing":false}')
      == "paste")
check("même mêlé à du texte libre",
      pss.request_is_noise("TEXTAREA: xterm-helper-textarea SOURCE SERVEUR: sans garde "
                           "11235 o debugger eval code:3:11 keydown "
                           '{"key":"Control","keyCode":17}') == "paste")
check("une trace Python est un collage",
      pss.request_is_noise("Traceback (most recent call last): File x line 3 "
                           "at run (app.py:12:3)") == "paste")

for ack in ("ok", "go", "enchaine", "core update fait", "core update fait, enchaine",
            "Core update + reload faits", "ca a l'air bien !!",
            "ça a l'air bon ! tous les accents passent même en changeant de session.",
            "/compact"):
    check("accusé reconnu : %r" % ack[:38], pss.request_is_noise(ack) == "ack")

# ── ce qui doit passer coûte que coûte ───────────────────────────────────────
# La mesure qui avait tranché sur RM2621 : la longueur ne sépare pas les
# demandes des accusés. « fais un sous-tâche » fait 18 signes.
for demande in ("fais un sous-tâche",
                "je teste ou ?",
                "teste. ensuite MR, et je core update la prod",
                "ok merge sur main, je met en prod",
                "coche les critres et merge",
                "go. L'état c'est un super début, on amliorera au fur et à mesure.",
                "les actions sur les dépôt pm ne m'intéressent pas, je veux les worktrees !",
                "ajouter info rapide + lien détaillé vers client et projet depuis ticket"):
    check("demande préservée : %r" % demande[:40], pss.request_is_noise(demande) is None)

# Le piège du filtre à collages : une demande QUI CITE une erreur en porte tous
# les marqueurs. C'est la forme la plus courante d'un signalement de bug.
check("« corrige ce TypeError at boot (app.js:12:3) » reste une demande",
      pss.request_is_noise("corrige ce TypeError at boot (app.js:12:3), "
                           "console.error( ) part en boucle") is None)
check("un verdict suivi d'une consigne reste une demande",
      pss.request_is_noise("c'est bon, maintenant ajoute le filtre par client") is None)
check("une question posée après un accusé reste une demande",
      pss.request_is_noise("ok mais pourquoi le worklog ne montre rien ?") is None)

# ── l'état « non_demande » ───────────────────────────────────────────────────
check("l'état existe", "non_demande" in pss.REQUEST_STATES)
check("il a son icône, distincte des autres",
      pss.REQUEST_ICON["non_demande"] not in
      (pss.REQUEST_ICON["annulee"], pss.REQUEST_ICON["repondu"]))
reqs = [{"text": "a", "status": "nouveau"}, {"text": "b", "status": "non_demande"},
        {"text": "c", "status": "annulee"}]
check("une non-demande sort du « à traiter »",
      [r["text"] for r in pss.request_open(reqs)] == ["a"])
check("mais elle reste comptée pour ce qu'elle est",
      pss.request_count_by_state(reqs)["non_demande"] == 1
      and pss.request_count_by_state(reqs)["annulee"] == 1)
check("elle n'est pas confondue avec « annulée » — personne n'a rien annulé",
      pss.request_count_by_state(reqs).get("annulee") == 1)

# ── audit et import doivent s'accorder ───────────────────────────────────────
# Sinon l'audit réclame indéfiniment l'enregistrement de ce que l'import refuse.
MSGS = ["fais un sous-tâche", "ok", COMPACT, "ajoute un filtre par client",
        'keydown {"keyCode":229,"isComposing":false}', "core update fait"]
rep = pss.request_audit(MSGS, [])
check("l'audit n'attend que les vraies demandes", rep["expected"] == 2)
check("et dit combien il a écarté, par nature",
      rep["acks"] == 2 and rep["pastes"] == 2)
importables = [m for m in MSGS if not pss.request_is_noise(m)]
check("l'import capturerait exactement ce que l'audit attend",
      len(importables) == rep["expected"])
check("l'écart se calcule sur cette base",
      pss.request_audit(MSGS, [{"text": "fais un sous-tâche"}])["gap"] == 1)
check("registre complet ⇒ aucun écart",
      pss.request_audit(MSGS, [{"text": "a"}, {"text": "b"}])["gap"] == 0)

# ── robustesse : ces fonctions lisent des données de session, pas du labo ────
for vide in ("", None, "   "):
    check("entrée vide tolérée : %r" % vide, pss.request_is_noise(vide) == "ack")
check("audit sans message ne divise pas par zéro",
      pss.request_audit([], [])["expected"] == 0)

# ── le cockpit et le script doivent classer pareil ───────────────────────────
# karl-agent recopie la liste des statuts « traités » (il ne peut pas importer
# un module au nom tireté). Sans ce test, ajouter un statut ici ferait
# réapparaître dans le cockpit des demandes déjà classées — et il n'y a aucune
# raison pour que quelqu'un pense à aller corriger l'autre fichier.
kspec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(kspec)
sys.modules["karl_agent"] = ka
kspec.loader.exec_module(ka)
check("cockpit et pm-session-status s'accordent sur ce qui est « traité »",
      ka.REQUEST_DONE_STATES == set(pss.REQUEST_DONE))

# Et le cockpit sert bien la liste : sans ça, le registre reste un fichier que
# le demandeur ne voit jamais — donc, de son point de vue, pas livré.
import json
import tempfile

tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / "sess-1.json").write_text(json.dumps({
    "session_id": "sess-1", "title": "t", "items": [],
    "requests": [{"text": "à traiter", "status": "nouveau", "ts": "2026-08-11"},
                 {"text": "déjà ticketée", "status": "ticketee", "ticket": "RM1"},
                 {"text": "collage", "status": "non_demande"}],
}), encoding="utf-8")
ka.WORKLOG_DIR = tmp
ka._has_session = lambda rm_id: True
ka._key_info = lambda sid: {"session_id": "sess-1"}
ka._worklog_live_map = lambda sid, items, force=False: ({}, 0)
wl = ka.op_worklog("2635")
check("le cockpit sert les demandes ouvertes",
      [r["text"] for r in wl["requests_open"]] == ["à traiter"])
check("avec leur numéro d'ordre, celui que `request --set` attend",
      wl["requests_open"][0]["n"] == 1)
check("ni les ticketées ni les non-demandes ne reviennent hanter le panneau",
      len(wl["requests_open"]) == 1)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests registre des demandes RM2635 passent")
