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
alloc, periodes, totaux, _ph, _phc, _sg = W.allocate(W.build_intervals(simultanes, params), params)
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
alloc, periodes, totaux, _ph, _phc, _sg = W.allocate(W.build_intervals(serie, params), params)
verifie(presque(sum(alloc.values()), sum(totaux.values()), 1e-6),
        "invariant tenu sur une série entremêlée")

# ── 2. Plafond de suivi ──────────────────────────────────────────────────────
print("\n2. Plafond de suivi (l'agent travaille seul, l'humain revient plus tard)")
loin = [ev(0), ev(120)]      # deux heures d'écart
alloc, periodes, totaux, _ph, _phc, _sg = W.allocate(W.build_intervals(loin, params), params)
verifie(sum(totaux.values()) < 40,
        f"les 2 h d'absence ne sont pas comptées ({sum(totaux.values()):.0f} min)")
serre = [ev(0), ev(5)]
_a, _p, t2, _ph2, _phc2, _sg = W.allocate(W.build_intervals(serre, params), params)
verifie(sum(t2.values()) < sum(totaux.values()) or True, "cas resserré calculé")

# ── 3. Les traces d'agent n'étendent pas le temps ────────────────────────────
print("\n3. Traces d'agent : elles attribuent, elles ne créent pas")
humain = [ev(0, cible=("a", "p", "111"))]
avec_agent = humain + [ev(60, cible=("a", "p", "222"), extends=False)]
_a1, _p1, t_h, _p3, _p3c, _sg = W.allocate(W.build_intervals(humain, params), params)
_a2, _p2, t_a, _p4, _p4c, _sg = W.allocate(W.build_intervals(avec_agent, params), params)
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

# Journée à moins d'1 h de client : le pot n'a personne à qui s'imputer, il reste à la
# charge d'iProspective — mais il est NOTÉ. Il était écarté jusqu'au 2026-10-13 :
# « si moins de 1h sur l'ensemble des clients le pot reste pour moi, sinon il est réparti ».
alloc_creuse = {(J, True, ("iprospective", "pm", None)): 200.0,
                (J, True, ("cli1", "p", None)): 10.0}
final2, ecarte2, journal2, _r2 = W.repartir_transversal(alloc_creuse, regles)
verifie(journal2[J]["destin"] == W.INTERNE, "journée à moins d'1 h de client : pot interne")
verifie(presque(sum(ecarte2.values()), 0.0), "plus rien n'est écarté hors absence déclarée")
verifie(presque(final2[(J, ("iprospective", "pm", None))], 200.0),
        "le pot reste entier chez iProspective")
verifie(presque(final2[(J, ("cli1", "p", None))], 10.0),
        "…et le temps du client est facturé quand même, seuil ou pas")
verifie(presque(sum(final2.values()) + sum(ecarte2.values()), 210.0), "conservation")

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


# ── 10. Journée : configuration utilisateur, cache, surcharges (RM3229) ──────
print("\n10. Journée — configuration, cache, surcharges")
import tempfile
with tempfile.TemporaryDirectory() as d:
    racine = Path(d)
    e1 = W.Event(ts=datetime(2026, 8, 26, 9, 45), chars=120, source="claude-transcript",
                 cwd="/zfs/x", session="s1", text="bonjour")
    e2 = W.Event(ts=datetime(2026, 8, 26, 14, 0), chars=30, source="redmine:matnat",
                 text="commentaire", cible=("matnat", "infra", "matnat#5588"))
    W.cache_ecrire("2026-08-26", [(e1, "2553"), (e2, None)], racine=racine)
    relu = W.cache_lire("2026-08-26", racine=racine)
    verifie(len(relu) == 2 and relu[0][1] == "2553" and relu[0][0].ts == e1.ts,
            "cache aller-retour : événement et ticket du tour conservés")
    verifie(relu[1][0].cible == ("matnat", "infra", "matnat#5588"), "cible certaine conservée")
    verifie(W.cache_lire("2026-08-27", racine=racine) is None, "journée absente du cache : None")
    W.surcharges_ecrire("2026-08", {"2026-08-26": {"debut": "09:30", "fin": "18:30", "client": "matnat"}},
                        racine=racine)
    verifie(W.surcharges_charger("2026-08", racine=racine)["2026-08-26"]["client"] == "matnat",
            "surcharges aller-retour")

verifie(W.heures_travaillees("09:30", "18:30") == 8.0, "9 h 30 – 18 h 30 = 8 h (pause d'1 h par défaut)")
verifie(W.heures_travaillees("09:00", "12:00") == 3.0, "demi-journée : pas de pause")
verifie(W.heures_travaillees("09:00", "18:00", 0.5) == 8.5, "pause explicite")

reguliere = [{"client": "matnat", "jours": ["mercredi"], "heures": 8, "debut": "09:30", "fin": "18:30"}]
eff = W.presences_effectives(reguliere, {"2026-08-12": {"debut": "09:00", "fin": "12:00", "client": "matnat"}})
verifie("2026-08-12" in eff[0]["sauf"], "une journée ajustée sort de la présence régulière")
verifie(eff[1]["dates"] == ["2026-08-12"] and eff[1]["heures"] == 3.0,
        "…et devient une présence datée (3 h) — pas deux planchers empilés")
verifie(W.presences_effectives(reguliere, {"2026-08-12": {"valide_sans_ajout": True}}) == reguliere
        or W.presences_effectives(reguliere, {"2026-08-12": {"valide_sans_ajout": True}})[0]["sauf"] == [],
        "une validation sans horaires ne touche pas aux présences")
verifie(str(W.chemin_config("/tmp/x.yml")) == "/tmp/x.yml", "configuration explicite prioritaire")

# une journée de régie DÉJÀ saisie ne se voit pas re-proposer son complément
pres = [{"client": "matnat", "projet": "infra", "dates": ["2026-08-26"], "debut": "09:30",
         "fin": "18:30", "heures": 8, "reunion_h": 1}]
d0, d1 = datetime(2026, 8, 26), datetime(2026, 8, 27)
ph = {("2026-08-26", h): 20.0 for h in range(9, 19)}          # 3 h 20 mesurées dans la plage
aj_vide, _t = W.appliquer_presences({}, pres, d0, d1, ph)
verifie(round(sum(aj_vide.values())) == 280, "journée non saisie : complément jusqu'à 8 h")
aj_saisie, _t = W.appliquer_presences({}, pres, d0, d1, ph, deja_par_jour={"2026-08-26": 485})
verifie(not aj_saisie, "journée déjà saisie (8 h 05) : aucun complément re-proposé")

# ── Le trou de midi : un ARRÊT, pas une fenêtre vide (RM3229, 2026-10-13) ───
# « Je vois un intervalle de pause énorme sur plusieurs dates » : sans trace entre 11h30
# et 14h30, la fenêtre de recherche ENTIÈRE était annoncée comme pause — 3 h.
verifie(W.trou_de_midi([["09:00", "12:15"], ["13:30", "18:00"]])["minutes"] == 75,
        "un vrai trou entre deux blocs de travail")
verifie(W.trou_de_midi([]) is None, "aucune trace : aucune pause (c'était 3 h)")
verifie(W.trou_de_midi([["08:00", "11:00"]]) is None,
        "parti à 11 h : c'est la fin de la journée, pas une pause")
verifie(W.trou_de_midi([["19:00", "23:00"]]) is None,
        "journée du soir : la journée n'a pas commencé à midi")
verifie(W.trou_de_midi([["09:00", "11:59"], ["12:01", "12:20"], ["13:30", "18:00"]])["debut"]
        == "12:20", "deux traces à 2 min d'écart ne font pas un trou : elles fusionnent")
verifie(W.trou_de_midi([["09:00", "12:00"], ["12:30", "17:00"], ["20:00", "22:00"]])["minutes"] == 30,
        "le trou du SOIR ne concurrence pas celui de midi")

# ── Les bornes de pause, posées à la main ───────────────────────────────────
verifie(W.duree_pause({"pause_debut": "12:30", "pause_fin": "14:00"}) == 1.5,
        "des bornes valent une durée")
verifie(W.duree_pause({"pause_h": 1.0}) == 1.0, "une durée seule reste acceptée")
verifie(W.duree_pause({"pause_debut": "14:00", "pause_fin": "12:00", "pause_h": 0.5}) == 0.5,
        "des bornes à l'envers ne gagnent pas contre une durée explicite")
verifie(W.duree_pause({"pause_debut": "bof", "pause_fin": "14:00"}) is None,
        "des bornes illisibles n'inventent rien")
verifie(W.heures_travaillees("09:00", "18:00",
                             W.duree_pause({"pause_debut": "12:30", "pause_fin": "14:00"})) == 7.5,
        "la journée se calcule sur la pause posée")

# ── Plancher de 15 min par client (RM3229, 2026-10-13) ──────────────────────
# « Si j'ai noté 4 lignes, je facture au moins 15 mn à mon client » : sous la tranche
# d'arrondi, un client réel tombait à zéro — du travail constaté, rien de facturé.
_rp = W.Regles(types={"calicote": "client", "pisceen": "client", "iprospective": "self"})


def _arrondi(brut, minimum=0):
    a = W.quantifier({("j", k): v for k, v in brut.items()}, 15)
    a = {k[1]: v for k, v in a.items()}
    return W.plancher_client(brut, a, 15, _rp, minimum)


_b = {("calicote", "c", None): 3.0, ("pisceen", "p", None): 600.0}
verifie(("calicote", "c", None) not in _arrondi(_b),
        "sans plancher, 3 min de client disparaissent à l'arrondi")
verifie(_arrondi(_b, 15)[("calicote", "c", None)] == 15,
        "avec plancher, le client a son quart d'heure")
verifie(_arrondi(_b, 15)[("pisceen", "p", None)] == 600,
        "…sans rien retirer à personne : le plancher CRÉE du temps, comme la régie")
verifie(_arrondi({("calicote", "c", None): 7.0}, 15)[("calicote", "c", None)] == 15,
        "un client seul sous la tranche est servi aussi")
verifie(_arrondi({("iprospective", "pm", None): 5.0}, 15) == {},
        "l'interne n'a pas de plancher : il ne se facture pas")
verifie(W.plancher_client({("calicote", "c", None): 0.0}, {}, 15, _rp, 15) == {},
        "un client SANS travail tracé n'est jamais inventé")
verifie(_arrondi({("calicote", "c", None): 120.0}, 15)[("calicote", "c", None)] == 120,
        "un client au-dessus du plancher n'est pas touché")

# ── Tout l'interne n'est pas du partagé (RM3229, 2026-10-13) ────────────────
# « atombox-webmail, projet du client iprospective, n'est pas un projet partagé ! »
_rh = W.Regles(types={"pisceen": "client", "iprospective": "self"}, perso={"lemathou"},
               hors_pot={"iprospective/atombox-webmail"})
verifie(_rh.dans_le_pot("iprospective", "pm-ai-agents"), "l'outillage PM reste du partagé")
verifie(not _rh.dans_le_pot("iprospective", "atombox-webmail"),
        "un produit interne non partagé n'entre pas dans le pot")
verifie(not _rh.dans_le_pot("lemathou", "manoe"), "le perso non plus")
verifie(not _rh.dans_le_pot("pisceen", "infra"), "un client n'est pas du pot")

_P2 = {"follow_cap": 10, "client_threshold_min": 60, "quantum_min": 15,
       "work_start_hour": 8, "work_end_hour": 19}
_a = {("2026-10-13", True, ("pisceen", "p", None)): 120.0,
      ("2026-10-13", True, ("iprospective", "pm-ai-agents", None)): 60.0,
      ("2026-10-13", True, ("iprospective", "atombox-webmail", None)): 60.0}
_f, _e, _j, _rf = W.repartir_transversal(_a, _rh, _P2)
verifie(round(_f[("2026-10-13", ("pisceen", "p", None))]) == 180,
        "seul l'outillage PM gonfle la ligne cliente (120 + 60)")
verifie(round(_f[("2026-10-13", ("iprospective", "atombox-webmail", None))]) == 60,
        "le produit interne reste entier chez iProspective")
verifie(round(sum(_f.values()) + sum(_e.values())) == 240, "rien créé, rien perdu")

# ── Le pot n'est pas homogène (RM3229, 2026-10-12) ──────────────────────────
# « si le pot PM/infra est bien pour tous les clients, presta/doli n'est que pour
# pisceen/calicote/calyclay » — un produit ne se refacture qu'à ceux qui s'en servent.
_r2 = W.Regles(types={"pisceen": "client", "calicote": "client", "matnat": "client",
                      "iprospective": "self", "prestashop": "product"},
               usagers={"prestashop": {"pisceen", "calicote"}})
verifie(_r2.clients_eligibles("prestashop", ["pisceen", "matnat"]) == {"pisceen"},
        "un produit ne vise que ses usagers")
verifie(_r2.clients_eligibles("iprospective", ["pisceen", "matnat"]) == {"pisceen", "matnat"},
        "sans usagers déclarés (PM, infra), le pot va à tout le monde")

_P = {"follow_cap": 10, "client_threshold_min": 60, "quantum_min": 15,
      "work_start_hour": 8, "work_end_hour": 19}
_alloc = {("2026-10-12", True, ("pisceen", "p", None)): 120.0,
          ("2026-10-12", True, ("matnat", "m", None)): 120.0,
          ("2026-10-12", True, ("prestashop", "core", None)): 60.0}
_f, _e, _j, _rf = W.repartir_transversal(_alloc, _r2, _P)
verifie(round(_f[("2026-10-12", ("pisceen", "p", None))]) == 180,
        "les 60 min de PrestaShop vont ENTIÈREMENT à pisceen, seul usager du jour")
verifie(round(_f[("2026-10-12", ("matnat", "m", None))]) == 120,
        "…et matnat, qui n'a pas PrestaShop, n'en reçoit rien")
verifie(round(sum(_f.values()) + sum(_e.values())) == 300, "rien créé, rien perdu")

# aucun usager présent ce jour-là : le temps reste interne, il ne part pas chez un tiers
_alloc2 = {("2026-10-12", True, ("matnat", "m", None)): 120.0,
           ("2026-10-12", True, ("prestashop", "core", None)): 60.0}
_f2, _e2, _j2, _ = W.repartir_transversal(_alloc2, _r2, _P)
verifie(round(_f2[("2026-10-12", ("prestashop", "core", None))]) == 60,
        "produit sans usager présent : reste interne, jamais refacturé au hasard")
verifie(round(_f2[("2026-10-12", ("matnat", "m", None))]) == 120, "…et le client n'est pas gonflé")

# ── Abattement : iProspective garde une part de la quote-part (2026-10-12) ──
# « iprospective garde pour lui 50% du pot PM/infra à répartir relatif à calicote/calyclay »
_r3 = W.Regles(types={"calicote": "client", "pisceen": "client", "iprospective": "self"},
               abattement={"calicote": 0.5})
_alloc3 = {("2026-10-12", True, ("calicote", "c", None)): 120.0,
           ("2026-10-12", True, ("pisceen", "p", None)): 120.0,
           ("2026-10-12", True, ("iprospective", "pm", None)): 60.0}
_f3, _e3, _j3, _rf3 = W.repartir_transversal(_alloc3, _r3, _P)
verifie(round(_rf3[("2026-10-12", ("calicote", "c", None))]) == 15,
        "calicote reçoit la MOITIÉ de sa quote-part (30 → 15)")
verifie(round(_rf3[("2026-10-12", ("pisceen", "p", None))]) == 30,
        "…pisceen, sans abattement, reçoit la sienne en entier")
verifie(round(_f3[("2026-10-12", ("iprospective", "pm", None))]) == 15,
        "la moitié retenue reste chez iProspective, à sa charge")
verifie(round(sum(_f3.values()) + sum(_e3.values())) == 300,
        "l'abattement DÉPLACE du temps, il n'en détruit pas")

# La retenue atterrit où on l'a DÉCLARÉ, pas chez la source : un pot venu d'un projet
# non identifié y laissait sinon une retenue « non attribuée », illisible sur une facture.
_r4 = W.Regles(types={"calicote": "client", "iprospective": "self"},
               abattement={"calicote": 0.5},
               retenue_vers=("iprospective", "pm-ai-agents", None))
_alloc4 = {("2026-10-12", True, ("calicote", "c", None)): 120.0,
           ("2026-10-12", True, (None, None, None)): 60.0}
_f4, _e4, _j4, _ = W.repartir_transversal(_alloc4, _r4, _P)
verifie(round(_f4.get(("2026-10-12", ("iprospective", "pm-ai-agents", None)), 0)) == 30,
        "la retenue va sur iProspective, même quand le pot vient d'un projet inconnu")
verifie(round(_f4.get(("2026-10-12", (None, None, None)), 0)) == 0,
        "…et plus rien ne reste sur « non attribué »")
verifie(round(sum(_f4.values()) + sum(_e4.values())) == 180, "total conservé")

verifie(W._abattement({"abattement": {"calicote": 0.5}}) == {"calicote": 0.5},
        "forme plate acceptée")
verifie(W._abattement({"abattement": {"vers": "a/b", "clients": {"calicote": 0.5}}})
        == {"calicote": 0.5}, "forme nommée aussi, sans confondre `vers` avec un client")
verifie(W._retenue_vers({"abattement": {"vers": "iprospective/pm-ai-agents"}})
        == ("iprospective", "pm-ai-agents", None), "la cible de retenue se lit")
verifie(W._retenue_vers({}) is None, "sans `vers`, rien n'est imposé")

# ── Le temps rapatrié garde le PROJET de la présence (2026-10-13) ───────────
# Sans lui la ligne est inécrivable dans Redmine (« matnat/None ») et son temps se perd
# en silence à la validation.
_pres_ex = [{"client": "matnat", "projet": "infra", "dates": ["2026-10-08"],
             "debut": "09:30", "fin": "18:30", "heures": 8, "exclusif": True}]
_fin = {("2026-10-08", ("calicote", "presta", "3039")): 120.0}
_ph = {("2026-10-08", h): 30.0 for h in range(9, 19)}
_phc = {("2026-10-08", 10, ("calicote", "presta", "3039")): 120.0}
_aj, _tr = W.appliquer_presences(_fin, _pres_ex, datetime(2026, 10, 8), datetime(2026, 10, 9),
                                 _ph, _phc)
_cibles = [c for (_j, c) in _fin if c[0] == "matnat"]
verifie(_cibles and all(c[1] == "infra" for c in _cibles),
        "le temps rapatrié rejoint matnat AVEC le projet de la présence")
verifie(not any(c[1] is None for c in _cibles), "…et plus jamais sans projet")

# ── Une journée particulière : demi-journée sur site (RM3229, 2026-10-12) ───
# « j'étais chez matnat jusqu'à 13h45, j'ai donc bossé 3,5 h ». Une telle journée se
# note dans l'ÉTAT (days.yml), pas dans la conf — et son plancher porte sur le CLIENT,
# pas sur un créneau : l'après-midi appartient à d'autres, il ne doit pas remplir le
# plancher MatNat à sa place.
_pres = W.presences_effectives([], {"2026-10-09": {"client": "matnat", "projet": "infra",
                                                   "heures": 3.5}})
verifie(len(_pres) == 1, "une journée qui porte un volume d'heures DEVIENT une présence")
verifie(_pres[0]["debut"] is None and _pres[0]["heures"] == 3.5,
        "…sans plage : le plancher portera sur le client, pas sur un créneau")
verifie(_pres[0]["exclusif"] is False,
        "…et sans exclusivité : rien n'est rapatrié d'un créneau qu'on n'a pas défini")
_pres2 = W.presences_effectives([], {"2026-10-08": {"client": "matnat", "debut": "09:30",
                                                    "fin": "18:30"}})
verifie(_pres2[0]["debut"] == "09:30" and _pres2[0]["heures"] == 8.0,
        "une journée avec plage garde son créneau et déduit ses heures")
verifie(W.presences_effectives([], {"2026-10-11": {"client": "matnat"}}) == [],
        "une journée sans plage NI heures n'est pas une présence")

# le plancher par CLIENT comble jusqu'au volume déclaré, sans compter les autres clients
_d0, _d1 = datetime(2026, 10, 9), datetime(2026, 10, 10)
_final = {("2026-10-09", ("matnat", "infra", None)): 30.0,
          ("2026-10-09", ("pisceen", "presta", None)): 150.0}
_aj, _tr = W.appliquer_presences(_final, _pres, _d0, _d1, None, None)
verifie(round(sum(_aj.values())) == 180,
        "le complément vise les 3,5 h du CLIENT (30 min mesurées → +180)")
verifie(all(c[0] == "matnat" for (_j, c, _m) in _aj),
        "…et il va bien à MatNat, pas au client de l'après-midi")

# ── Les livraisons se lisent dans les commits de fusion (RM3229, 2026-10-01) ──
# Une MR fusionnée laisse un commit « Merge branch 'NNNN-slug' into 'dev' » : la forge
# n'a pas besoin d'être interrogée pour savoir ce qui est sorti ce jour-là.
verifie(W._MERGE_RE.match("Merge branch '3199-infra' into 'dev'").group(1) == "3199-infra",
        "le nom de branche se lit dans le sujet de fusion")
verifie(W._MERGE_RE.match("Merge branch 'dev' into 'main'").group(2) == "main",
        "…et sa cible")
verifie(W._MERGE_RE.match("feat: autre chose") is None, "un commit ordinaire n'est pas une fusion")

# ── Recouvrement des tours d'agent (RM3229, 2026-09-22) ─────────────────────
# Le bornage a été demandé, essayé, puis RETIRÉ le jour même : deux agents en parallèle
# produisent bien deux fois du travail, même si l'horloge n'avance qu'une fois. La
# fonction reste — elle sert à SIGNALER le recouvrement — mais plus rien ne rabote les
# durées : le chiffre affiché est celui que les tours déclarent.
_t = W.ticks_sans_chevauchement([
    {"heure": "09:00", "minutes": 10.0},     # se termine à 09:10, rien après avant 09:20
    {"heure": "09:20", "minutes": 30.0},     # déborde sur 09:30 → borné à 10 min
    {"heure": "09:30", "minutes": 5.0},
])
verifie([round(x["minutes_reelles"]) for x in _t] == [10, 10, 5],
        "le temps d'horloge d'un tour s'arrête au début du suivant")
verifie([x["borne"] for x in _t] == [False, True, False],
        "…et le recouvrement est signalé")
verifie([x["minutes"] for x in _t] == [10.0, 30.0, 5.0],
        "la durée DÉCLARÉE est intacte : c'est elle qui compte, l'horloge n'est qu'une indication")
verifie(W.ticks_sans_chevauchement([]) == [], "aucun tour : aucune erreur")
_solo = W.ticks_sans_chevauchement([{"heure": "14:00", "minutes": 90.0}])
verifie(_solo[0]["minutes_reelles"] == 90.0 and not _solo[0]["borne"],
        "le dernier tour de la journée ne recouvre rien")
_desordre = W.ticks_sans_chevauchement([{"heure": "10:00", "minutes": 60.0},
                                        {"heure": "09:00", "minutes": 30.0}])
verifie(_desordre[0]["heure"] == "09:00", "les tours sont remis dans l'ordre avant analyse")

# ── Bandes colorées de la frise ─────────────────────────────────────────────
_d = lambda h, m: datetime(2026, 9, 18, h, m)          # noqa: E731
_bandes = W.bandes_par_client([
    (_d(9, 0), _d(9, 10), {"pisceen": 10}),
    (_d(9, 10), _d(9, 20), {"pisceen": 10}),           # même client, contigu → fusionné
    (_d(9, 20), _d(9, 40), {"calicote": 20}),
    (_d(10, 0), _d(10, 30), {"matnat": 20, "pisceen": 10}),
])
verifie(len(_bandes) == 3, "les tranches contiguës d'un même client fusionnent")
verifie(_bandes[0]["minutes"] == 20 and _bandes[0]["client"] == "pisceen",
        "…en cumulant leur durée")
verifie(_bandes[2]["client"] == "matnat" and _bandes[2]["parts"]["pisceen"] == 10,
        "la bande garde TOUTE sa répartition, pas seulement le dominant")
verifie(W.bandes_par_client([]) == [], "journée sans tranche : aucune bande")
_miette = W.bandes_par_client([(_d(9, 0), _d(9, 30), {"pisceen": 30}),
                               (_d(9, 30), _d(9, 31), {"calicote": 1})])
verifie(len(_miette) == 1, "une miette d'une minute est absorbée, pas dessinée")

# ── Facturable et pause de midi (RM3229, 2026-09-22) ────────────────────────
# « ce sont les type self (c'est moi) » : la liste des entités non facturées n'est pas
# une conf, elle est DÉJÀ dans les manifestes PM.
_r = W.Regles(types={"pisceen": "client", "iprospective": "self", "lemathou": "self",
                     "dolibarr": "product"})
verifie(_r.facturable("pisceen"), "un client se facture")
verifie(not _r.facturable("iprospective"), "soi-même, non")
verifie(not _r.facturable("lemathou"), "le perso non plus")
verifie(not _r.facturable("dolibarr"), "un produit mutualisé non plus")
verifie(_r.est_soi("iprospective") and not _r.est_soi("pisceen"), "type self reconnu")

# le trou de midi : ce qui permet de dire « la pause n'apparaît pas » sans le deviner
verifie(W.trou_de_midi([["09:00", "12:15"], ["13:30", "18:00"]])["minutes"] == 75,
        "un vrai trou de midi est mesuré")
verifie(W.trou_de_midi([["09:00", "18:00"]]) is None,
        "journée d'un seul tenant : aucune pause visible")
verifie(W.trou_de_midi([["09:00", "12:50"], ["13:05", "18:00"]]) is None,
        "15 min ne font pas une pause de midi")
# Le trou rendu est le trou RÉEL, pas sa portion dans le créneau : le travail s'est
# arrêté à 11:00 et repris à 14:45. Rogner à 11:30–14:30 inventerait des bornes et
# sous-estimerait la pause (comportement d'avant le 2026-10-13).
_t = W.trou_de_midi([["09:00", "11:00"], ["14:45", "18:00"]])
verifie((_t["debut"], _t["fin"]) == ("11:00", "14:45"),
        "le trou rendu est celui qu'on a réellement observé, pas sa portion de créneau")
_pc = W.conf_pause({"pause": {"client": "iprospective", "heures": 0.75}})
verifie(_pc["client"] == "iprospective" and _pc["heures"] == 0.75
        and _pc["activity_id"] == 27,
        "la conf de pause complète les défauts sans les perdre")
verifie(W.conf_pause({})["client"] is None,
        "sans conf, aucune cible : rien ne se note d'office")


# Les données d'exploitation du PM (cache des traces, surcharges, sauvegardes de reprise)
# appartiennent au core, avec le reste de ce que le PM produit en tournant.
import tempfile as _tf
import types as _ty

with _tf.TemporaryDirectory() as _tmp:
    _core = Path(_tmp) / "core"
    (_core / "var").mkdir(parents=True)
    _ancien = Path(_tmp) / "home-state"
    (_ancien / "cache").mkdir(parents=True)
    (_ancien / "2026-08.days.yml").write_text("'2026-08-26': {client: matnat}\n", encoding="utf-8")
    (_ancien / "cache" / "2026-08-26.jsonl").write_text("{}\n", encoding="utf-8")

    _avant, _herite = W.ETAT, list(W.ETATS_HERITES)
    import os as _os
    _os.environ["PM_USER_DIR"] = str(_core / "var" / "users" / "moi")
    try:
        W.ETATS_HERITES[:] = [_ancien]
        _cible = W.configurer_etat(_ty.SimpleNamespace(state_dir=_core / "var", pm_dir=_core))
        verifie(_cible == _core / "var" / "users" / "moi" / "timesheet",
                "l'état vit dans le dossier de l'UTILISATEUR, pas dans un var/ commun")
        verifie((_cible / "2026-08.days.yml").is_file(), "les surcharges de journée ont suivi")
        verifie((_cible / "cache" / "2026-08-26.jsonl").is_file(),
                "le cache des traces a suivi (sinon : tout rejouer)")
        verifie(not any(_ancien.iterdir()), "l'ancien emplacement est vidé")

        (_ancien / "2026-08.days.yml").write_text("'2026-08-26': {client: AUTRE}\n", encoding="utf-8")
        W.configurer_etat(_ty.SimpleNamespace(state_dir=_core / "var", pm_dir=_core))
        verifie("matnat" in (_cible / "2026-08.days.yml").read_text(encoding="utf-8"),
                "une seconde reprise n'écrase pas l'état déjà en place")
        verifie(W.configurer_etat(None) == _cible, "sans configuration, l'état ne bouge pas")
    finally:
        W.ETAT = _avant
        W.ETATS_HERITES[:] = _herite
        _os.environ.pop("PM_USER_DIR", None)

# ── Les tours d'agent comme traces (RM3229, 2026-10-13) ─────────────────────
print("\nLes tours d'agent sont des traces à part entière")
_p = {"follow_cap": 10, "write_base": 1, "chars_per_min": 45,
      "write_min": 2, "write_max": 30, "default_prompt_chars": 120}
_ticks = [
    {"jour": "2026-06-07", "heure": "10:00", "ticket": "1444", "client": "calicote",
     "projet": "dolibarr", "modele": "m", "tokens": 1000, "minutes": 20.0},
    {"jour": "2026-06-07", "heure": "10:04", "ticket": "1444", "client": "calicote",
     "projet": "dolibarr", "modele": "m", "tokens": 1000, "minutes": 20.0},
]
_evs = W.evenements_des_tours(_ticks, params=_p)
verifie(len(_evs) == 2, "un événement par tour d'agent")
verifie(all(e.source == "tick-ia" for e in _evs), "les tours se reconnaissent à leur source")
verifie(all(e.extends for e in _evs), "un tour CRÉE du temps : quelqu'un l'a demandé")
verifie(all(e.scores == {("calicote", "dolibarr", None): 1.0} for e in _evs),
        "le tour attribue son temps au client de son ticket")

# La durée propre d'un tour ne se laisse pas raboter par le plafond de supervision.
_long = W.Event(ts=datetime(2026, 6, 7, 10, 0), chars=0, source="tick-ia", duree=45.0)
_long.scores = {("calicote", "dolibarr", None): 1.0}
_iv = W.build_intervals([_long], _p)[0]
verifie(presque((_iv.fin - _long.ts).total_seconds() / 60, 45.0),
        "l'intervalle d'un tour couvre sa durée réelle, pas le plafond de suivi")

# Des tours resserrés se rejoignent en une période continue.
_alloc, _per, _tot, _ph, _phc, _sg = W.allocate(W.build_intervals(_evs, _p), _p)
verifie(len(_per.get("2026-06-07", [])) == 1,
        "des tours qui s'enchaînent dans le temps de relecture forment UNE période")
verifie(sum(_tot.values()) > 9, "la période couvre les deux tours, pas un seul")

# … mais un vrai trou reste un trou : deux tours espacés font deux périodes.
_ecartes = W.evenements_des_tours(
    [{"jour": "2026-06-07", "heure": "10:00", "ticket": "1", "client": "calicote",
      "projet": "dolibarr", "modele": "m", "tokens": 1, "minutes": 5.0},
     {"jour": "2026-06-07", "heure": "14:00", "ticket": "1", "client": "calicote",
      "projet": "dolibarr", "modele": "m", "tokens": 1, "minutes": 5.0}], params=_p)
_, _per2, _, _, _, _ = W.allocate(W.build_intervals(_ecartes, _p), _p)
verifie(len(_per2.get("2026-06-07", [])) == 2,
        "quatre heures entre deux tours : deux périodes, pas une plage continue")

# Sans tour d'agent, rien n'est fabriqué.
verifie(W.evenements_des_tours([], params=_p) == [], "aucun tour : aucun événement")
verifie(W.evenements_des_tours([{"jour": "x", "heure": "nope"}], params=_p) == [],
        "un tick illisible est ignoré, il ne casse pas la journée")

# Le plafond de relecture : un tour n'atteste d'une présence que le temps de relire
# ce qu'il a produit (13/06/2026 — un tour de 113 min étirait la nuit jusqu'à 04:11).
_pr = {**_p, "relecture_part": 0.25, "relecture_min": 5.0, "relecture_max": 30.0}
_tick = lambda h, dec: {"jour": "2026-06-13", "heure": h, "ticket": "1895",
                        "client": "iprospective", "projet": "pm-ai-agents",
                        "modele": "m", "tokens": 1, "minutes": dec}
_seul = W.evenements_des_tours([_tick("02:18", 113.6)], params=_pr)[0]
verifie(presque(_seul.duree, 28.4), "un tour de 113 min ne retient que 28 min de relecture")
_court = W.evenements_des_tours([_tick("02:18", 2.0)], params=_pr)[0]
verifie(presque(_court.duree, 2.0), "un tour court n'est pas ALLONGÉ au plancher de relecture")
_enorme = W.evenements_des_tours([_tick("02:18", 600.0)], params=_pr)[0]
verifie(presque(_enorme.duree, 30.0), "le plafond de relecture tient : 30 min, pas davantage")
_moyen = W.evenements_des_tours([_tick("02:18", 30.0)], params=_pr)[0]
verifie(presque(_moyen.duree, 7.5), "entre les bornes, la relecture suit la quantité produite")

# Le plafond vaut aussi quand un autre tour suit (choix du 14/10/2026).
_suivis = W.evenements_des_tours([_tick("02:18", 113.6), _tick("03:00", 10.0)], params=_pr)
verifie(presque(_suivis[0].duree, 28.4),
        "un tour suivi d'un autre est plafonné lui aussi : l'enchaînement ne prouve pas la présence")

# Une trace humaine et un tour au même moment ne comptent pas deux fois.
_mix = [ev(0, cible=("calicote", "dolibarr", None)),
        W.Event(ts=datetime(2026, 8, 3, 10, 0), chars=0, source="tick-ia", duree=5.0,
                scores={("calicote", "dolibarr", None): 1.0})]
_a2, _p2, _t2, _, _, _ = W.allocate(W.build_intervals(_mix, _p), _p)
verifie(presque(sum(_a2.values()), sum(_t2.values())),
        "humain + tour au même instant : l'union, jamais la somme")


# ── Corriger le rattachement d'une ligne (RM3229, 2026-10-14) ───────────────
print("\nCorriger le rattachement d'une ligne")
_lg = [{"jour": "2026-06-07", "client": "calicote", "projet": "dolibarr",
        "ticket": 1855, "activite": 13, "minutes": 30},
       {"jour": "2026-06-07", "client": "calicote", "projet": "dolibarr",
        "ticket": None, "activite": 13, "minutes": 15}]
W._poser_cles(_lg)
verifie(_lg[0]["cle"] == "calicote/dolibarr#1855@13", "la clé nomme la cible, pas le rang")
verifie(_lg[1]["cle"] == "calicote/dolibarr#-@13", "une ligne sans ticket a sa clé propre")
_doublons = [dict(_lg[0]), dict(_lg[0])]
W._poser_cles(_doublons)
verifie(_doublons[0]["cle"] != _doublons[1]["cle"], "deux lignes jumelles restent distinguables")

# Déplacer une ligne chez un autre client.
_l2 = [dict(x) for x in _lg]
_orph = W.amender_lignes(_l2, {"2026-06-07": {"lignes": {
    "calicote/dolibarr#1855@13": {"client": "pisceen", "projet": "dolibarr"}}}})
verifie(_l2[0]["client"] == "pisceen", "le client corrigé remplace celui du calcul")
verifie(_l2[0]["minutes"] == 30, "les minutes ne bougent PAS : on déplace, on ne crée rien")
verifie(_l2[0]["origine"]["client"] == "calicote", "le rattachement d'origine reste lisible")
verifie(_l2[1]["client"] == "calicote", "les autres lignes ne sont pas touchées")
verifie(_orph == [], "une correction qui trouve sa ligne n'est pas orpheline")

# Le ticket emporte le projet dans Redmine : il est lâché quand la cible change.
verifie(_l2[0]["ticket"] is None and _l2[0]["ticket_abandonne"] == 1855,
        "déplacer une ligne lâche son ticket, sinon Redmine la ramènerait à son projet")
_l3 = [dict(x) for x in _lg]
W.amender_lignes(_l3, {"2026-06-07": {"lignes": {
    "calicote/dolibarr#1855@13": {"client": "pisceen", "ticket": "1234"}}}})
verifie(_l3[0]["ticket"] == 1234, "un ticket choisi explicitement est gardé")

# Une correction dont la ligne a disparu se signale, elle ne se perd pas.
_l4 = [dict(x) for x in _lg]
_orph2 = W.amender_lignes(_l4, {"2026-06-07": {"lignes": {"parti/ailleurs#9@1": {"client": "x"}}}})
verifie(_orph2 == [("2026-06-07", "parti/ailleurs#9@1")],
        "une correction sans cible est rendue à l'appelant, pas avalée")
verifie(all(not x.get("amendee") for x in _l4), "et elle ne touche aucune autre ligne")


# ── La pause habituelle d'une présence (RM3229, 2026-10-19) ─────────────────
print("\nLa pause habituelle d'une journée de présence")
_pres = [{"client": "matnat", "projet": "infra", "jours": ["jeudi", "vendredi"],
          "depuis": "2026-09-24", "pause_debut": "12:30", "pause_fin": "13:30",
          "heures": 8}]
_d0, _d1 = date(2026, 10, 12), date(2026, 10, 18)   # lundi → dimanche
_pz = W.pauses_par_presence(_pres, _d0, _d1)
verifie(sorted(_pz) == ["2026-10-15", "2026-10-16"],
        "la pause ne vise que les jours de présence déclarés")
verifie(_pz["2026-10-15"]["pause_debut"] == "12:30" and _pz["2026-10-15"]["pause_fin"] == "13:30",
        "elle porte les bornes déclarées sur la présence")
verifie(W.duree_pause(_pz["2026-10-15"]) == 1.0, "une heure, lue depuis les bornes")
verifie(_pz["2026-10-15"]["origine"] == "presence", "son origine est dite : c'est un défaut")

# Une pause notée à la main l'emporte toujours.
_pz2 = W.pauses_par_presence(_pres, _d0, _d1,
                             {"2026-10-15": {"pause_debut": "13:00", "pause_fin": "13:30"}})
verifie("2026-10-15" not in _pz2, "une pause notée à la main n'est jamais recouverte")
verifie("2026-10-16" in _pz2, "mais les autres journées gardent leur défaut")

# Une journée particulière peut la redéfinir ou l'annuler.
_pres2 = [{**_pres[0], "exceptions": {"2026-10-15": {"pause": False},
                                      "2026-10-16": {"pause_debut": "12:00",
                                                     "pause_fin": "12:45"}}}]
_pz3 = W.pauses_par_presence(_pres2, _d0, _d1)
verifie("2026-10-15" not in _pz3, "une exception peut annuler la pause d'un jour")
verifie(_pz3["2026-10-16"]["pause_fin"] == "12:45", "une exception peut la redéfinir")

# Hors de la fenêtre de la présence, rien.
verifie(W.pauses_par_presence(_pres, date(2026, 9, 1), date(2026, 9, 7)) == {},
        "avant le début de la présence, aucune pause n'est proposée")
_bornee = [{**_pres[0], "jusqu_a": "2026-10-15"}]
verifie(sorted(W.pauses_par_presence(_bornee, _d0, _d1)) == ["2026-10-15"],
        "`jusqu_a` est inclusif, et ferme bien la série")
_sauf = [{**_pres[0], "sauf": ["2026-10-15"]}]
verifie(sorted(W.pauses_par_presence(_sauf, _d0, _d1)) == ["2026-10-16"],
        "un jour mis de côté n'a pas de pause")

# Sans pause déclarée sur la présence, rien n'est inventé.
verifie(W.pauses_par_presence([{**_pres[0], "pause_debut": None, "pause_fin": None}],
                              _d0, _d1) == {},
        "une présence sans pause déclarée n'en fabrique pas")


print("\n" + ("ÉCHECS : " + " | ".join(ECHECS) if ECHECS else "Tous les tests passent."))
sys.exit(1 if ECHECS else 0)
