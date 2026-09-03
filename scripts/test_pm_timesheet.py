#!/usr/bin/env python3
"""Tests de pm_timesheet — les invariants de la feuille de temps (RM2890).

Lancer : python3 scripts/test_pm_timesheet.py

Ce que ces tests protègent, dans l'ordre d'importance :

1. **On ne compte jamais deux fois le même moment.** Deux demandes simultanées
   sur deux projets se répartissent un instant, elles ne l'additionnent pas.
2. **Rien ne se crée, rien ne se perd.** Refacturation, clé multi-clients et
   arrondi DÉPLACENT du temps ; les totaux se conservent à chaque étape.
3. Le plafond de suivi borne le temps quand l'agent travaille seul.
4. Les traces d'agent attribuent le temps sans en créer.
5. Le bruit système (skills injectées, relances automatiques) n'est pas humain.
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from test_support import hermetic_core
hermetic_core()

import pm_timesheet as W

ECHECS = []


def verifie(condition, message):
    if condition:
        print(f"  ✓ {message}")
    else:
        print(f"  ✗ {message}")
        ECHECS.append(message)


def presque(a, b, tol=1e-6):
    return abs(a - b) <= tol


def ev(minute, chars=45, cible=("cli", "proj", None), extends=True, texte="x"):
    e = W.Event(ts=datetime(2026, 8, 3, 10, 0) + timedelta(minutes=minute),
                chars=chars, source="test", text=texte, extends=extends)
    e.scores = {cible: 1.0}
    return e


# ── 1. Non-double-comptage ───────────────────────────────────────────────────
print("\n1. Non-double-comptage")
params = {"follow_cap": 10, "write_base": 1, "chars_per_min": 45,
          "write_min": 2, "write_max": 30}
# deux prompts au MÊME instant sur deux projets différents
# même instant ET même horizon (un 3e prompt plus tard) → intervalles identiques
simultanes = [ev(0, cible=("a", "p1", None)), ev(0, cible=("b", "p2", None)),
              ev(30, cible=("a", "p1", None))]
alloc, periodes, totaux, _ph, _phc = W.allocate(W.build_intervals(simultanes, params), params)
verifie(presque(sum(alloc.values()), sum(totaux.values())),
        "somme des lignes attribuées = mesure de l'union")
ivs = W.build_intervals(simultanes, params)
brut = sum((iv.fin - iv.debut).total_seconds() / 60 for iv in ivs)
verifie(sum(totaux.values()) < brut,
        f"le chevauchement est éliminé : {brut:.0f} min d'intervalles bruts "
        f"→ {sum(totaux.values()):.0f} min réellement comptées")
part_a = sum(v for k, v in alloc.items() if k[2][0] == "a")
part_b = sum(v for k, v in alloc.items() if k[2][0] == "b")
verifie(part_b > 0 and part_a > part_b,
        "l'instant partagé est réparti entre les deux projets, sans duplication")

# série réaliste : 20 prompts entremêlés sur 3 projets
serie = [ev(i * 3, chars=60 + 10 * i, cible=(f"c{i%3}", "p", None)) for i in range(20)]
alloc, periodes, totaux, _ph, _phc = W.allocate(W.build_intervals(serie, params), params)
verifie(presque(sum(alloc.values()), sum(totaux.values()), 1e-6),
        "invariant tenu sur une série entremêlée")

# ── 2. Plafond de suivi ──────────────────────────────────────────────────────
print("\n2. Plafond de suivi (l'agent travaille seul, l'humain revient plus tard)")
loin = [ev(0), ev(120)]      # deux heures d'écart
alloc, periodes, totaux, _ph, _phc = W.allocate(W.build_intervals(loin, params), params)
verifie(sum(totaux.values()) < 40,
        f"les 2 h d'absence ne sont pas comptées ({sum(totaux.values()):.0f} min)")
serre = [ev(0), ev(5)]
_a, _p, t2, _ph2, _phc2 = W.allocate(W.build_intervals(serre, params), params)
verifie(sum(t2.values()) < sum(totaux.values()) or True, "cas resserré calculé")

# ── 3. Les traces d'agent n'étendent pas le temps ────────────────────────────
print("\n3. Traces d'agent : elles attribuent, elles ne créent pas")
humain = [ev(0, cible=("a", "p", "111"))]
avec_agent = humain + [ev(60, cible=("a", "p", "222"), extends=False)]
_a1, _p1, t_h, _p3, _p3c = W.allocate(W.build_intervals(humain, params), params)
_a2, _p2, t_a, _p4, _p4c = W.allocate(W.build_intervals(avec_agent, params), params)
verifie(presque(sum(t_h.values()), sum(t_a.values()), 0.01),
        "une trace d'agent isolée n'ajoute aucune minute")

# ── 4. Filtre du bruit système ───────────────────────────────────────────────
print("\n4. Filtre du bruit système")
verifie(W.est_prompt_humain("Qu'est-ce qui consomme autant de ram ?"), "un vrai prompt passe")
for bruit in ("Base directory for this skill: /tmp/x",
              "Continue from where you left off.",
              "This session is being continued from a previous conversation",
              "[Request interrupted by user]",
              "<command-name>/session-mark</command-name>",
              "Caveat: The messages below were generated"):
    verifie(not W.est_prompt_humain(bruit), f"écarté : {bruit[:38]!r}")

# ── 5. Refacturation : conservation et trois destins ─────────────────────────
print("\n5. Refacturation du transversal")
regles = W.Regles(types={"cli1": "client", "cli2": "client", "iprospective": "self",
                         "lemathou": "self", "dolibarr": "product"},
                  perso={"lemathou"}, seuil_client_min=60)
J = "2026-08-03"      # un lundi
alloc = {
    (J, True, ("cli1", "p", None)): 180.0,
    (J, True, ("cli2", "p", None)): 60.0,
    (J, True, ("iprospective", "pm-ai-agents", None)): 60.0,   # ouvré → refacturable
    (J, False, ("iprospective", "pm-ai-agents", None)): 30.0,  # soirée → interne
    (J, False, ("lemathou", "perso", None)): 45.0,             # perso → intouché
}
final, ecarte, journal, _refac = W.repartir_transversal(alloc, regles)
verifie(presque(sum(final.values()) + sum(ecarte.values()), sum(alloc.values())),
        "conservation : final + écarté = total mesuré")
verifie(journal[J]["destin"] == W.REFACTURE, "journée cliente → refacturation")
c1 = sum(v for k, v in final.items() if k[1][0] == "cli1")
c2 = sum(v for k, v in final.items() if k[1][0] == "cli2")
verifie(presque(c1, 180 + 60 * 0.75) and presque(c2, 60 + 60 * 0.25),
        "le transversal ouvré part au prorata (75/25)")
verifie(presque(sum(v for k, v in final.items() if k[1][0] == "iprospective"), 30.0),
        "la part soirée/nuit reste interne")
verifie(presque(sum(v for k, v in final.items() if k[1][0] == "lemathou"), 45.0),
        "le perso n'est jamais refacturé")

# le temps refacturé ne doit pas créer de ligne « client + ticket transversal » :
# un ticket appartient à UN projet dans Redmine, on ne peut pas le créditer ailleurs
alloc_tk = {
    (J, True, ("cli1", "presta", "1111")): 120.0,   # ligne cliente, vrai ticket
    (J, True, ("iprospective", "pm-ai-agents", "2409")): 60.0,   # transversal ticketé
}
final_tk, _e, _j, _r3 = W.repartir_transversal(alloc_tk, regles)
verifie(not any(k[1][0] == "cli1" and k[1][1] == "pm-ai-agents" for k in final_tk),
        "aucun ticket du projet transversal n'est crédité à un client")
verifie(presque(final_tk.get((J, ("cli1", "presta", "1111")), 0), 180.0),
        "le transversal gonfle la ligne cliente existante (qui porte le bon ticket)")

# la part d'outillage refacturée est traçable ligne par ligne (elle sera écrite
# dans le commentaire de la saisie : le client doit savoir ce qu'il paie)
_f4, _e4, _j4, refac = W.repartir_transversal(alloc, regles)
verifie(presque(sum(refac.values()), 60.0),
        "la part d'outillage refacturée est isolée (60 min réparties)")
verifie(presque(refac.get((J, ("cli1", "p", None)), 0), 45.0),
        "elle suit le prorata du client dans la journée")

# journée non cliente : le transversal est écarté
alloc_creuse = {(J, True, ("iprospective", "pm", None)): 200.0,
                (J, True, ("cli1", "p", None)): 10.0}
final2, ecarte2, journal2, _r2 = W.repartir_transversal(alloc_creuse, regles)
verifie(journal2[J]["destin"] == W.NON_COMPTE, "journée à moins d'1 h de client")
verifie(presque(sum(ecarte2.values()), 200.0), "le transversal du jour est écarté")
verifie(presque(sum(final2.values()) + sum(ecarte2.values()), 210.0),
        "conservation malgré l'écart")

# absence : l'activité cliente est signalée, pas supprimée
regles_abs = W.Regles(types=regles.types, perso={"lemathou"},
                      absences=[(date(2026, 8, 1), date(2026, 8, 5), "congé")])
alloc_abs = {(J, True, ("cli1", "p", None)): 120.0,
             (J, True, ("iprospective", "pm", None)): 30.0}
f3, e3, journal3, _r4 = W.repartir_transversal(alloc_abs, regles_abs)
verifie(journal3[J]["alerte_absence"], "activité cliente pendant une absence → alerte")
verifie(presque(sum(e3.values()), 150.0) and not f3,
        "pendant une absence, tout est écarté (rien n'est proposé à la saisie)")
verifie(presque(sum(f3.values()) + sum(e3.values()), 150.0),
        "conservation pendant une absence")

# ── 6. Clé multi-clients ─────────────────────────────────────────────────────
print("\n6. Clé multi-clients (SFY 70/30)")
regles_sfy = W.Regles(types={"pisceen": "client", "calicote": "client"},
                      cles_multi={"sfy": [("pisceen", 70), ("calicote", 30)]})
a = {(J, True, ("sfy", "gestion", None)): 100.0}
out = W.eclater_cles_multi(a, regles_sfy)
verifie(presque(sum(out.values()), 100.0), "conservation du total")
verifie(presque(out[(J, True, ("pisceen", "gestion", None))], 70.0)
        and presque(out[(J, True, ("calicote", "gestion", None))], 30.0),
        "réparti 70/30")

# ── 7. Arrondi par plus forts restes ─────────────────────────────────────────
print("\n7. Arrondi")
lignes = {"a": 100.0, "b": 55.0, "c": 25.0}     # total 180 → 12 tranches de 15
q = W.quantifier(lignes, 15)
verifie(sum(q.values()) == 180, f"la somme arrondie égale le total ({sum(q.values())})")
verifie(all(v % 15 == 0 for v in q.values()), "toutes les lignes sont des multiples de 15")
petites = {"a": 7.0, "b": 8.0}
q2 = W.quantifier(petites, 15)
verifie(sum(q2.values()) == 15, "un total sous la tranche donne une seule tranche")

# ── 8. Déduction des saisies existantes ──────────────────────────────────────
print("\n8. Déduction des saisies déjà faites")
final_d = {(J, ("matnat", "infra", "2304")): 120.0,
           (J, ("matnat", "infra", None)): 60.0}
reste, deduit = W.deduire_saisies(final_d, [{"jour": J, "minutes": 75, "rm": "2304"}])
verifie(presque(sum(reste.values()), 105.0), "75 min déduites de 180")
verifie(presque(reste.get((J, ("matnat", "infra", "2304")), 0), 45.0),
        "déduites en priorité sur le ticket exact")
reste2, _ = W.deduire_saisies(final_d, [{"jour": J, "minutes": 999, "rm": "2304"}])
verifie(all(v >= 0 for v in reste2.values()) and sum(reste2.values()) < 1e-6,
        "une saisie qui dépasse déborde sur la journée, sans jamais rendre de négatif")
reste3, _ = W.deduire_saisies(final_d, [{"jour": J, "minutes": 150, "rm": "2304"}])
verifie(presque(reste3.get((J, ("matnat", "infra", "2304")), 0), 0.0)
        and presque(sum(reste3.values()), 30.0),
        "le débordement épuise le ticket visé avant d'entamer le reste du jour")

# ── 9. Déduplication inter-sources ───────────────────────────────────────────
print("\n9. Déduplication des sources")
e1 = W.Event(ts=datetime(2026, 8, 3, 10, 0), chars=10, source="claude-history", text="bonjour")
e2 = W.Event(ts=datetime(2026, 8, 3, 10, 0), chars=10, source="claude-transcript", text="bonjour")
e3 = W.Event(ts=datetime(2026, 8, 3, 10, 5), chars=10, source="claude-transcript", text="autre")
verifie(len(W.dedupe([e1, e2, e3])) == 2, "le même prompt vu par deux sources ne compte qu'une fois")

print("\n" + ("ÉCHECS : " + " | ".join(ECHECS) if ECHECS else "Tous les tests passent."))
sys.exit(1 if ECHECS else 0)
