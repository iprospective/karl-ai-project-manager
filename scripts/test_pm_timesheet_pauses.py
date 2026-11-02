#!/usr/bin/env python3
"""Test RM3229 — la pause d'une journée HORS période ne s'invite pas dans la proposition.

Les surcharges sont chargées par MOIS entier ; sans bornage, la pause d'une journée
voisine créait une ligne datée d'un autre jour. Combiné au serveur qui rendait la
première journée venue, l'écran affichait alors cette journée-là — ses heures et sa
note (incident du 2026-10-13 : « 08/06 je lis 45 mn proposé… et la note du 04/06 »).

Lancer : python3 scripts/test_pm_timesheet_pauses.py
"""
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("ts_cli", HERE / "pm-timesheet.py")
cli = importlib.util.module_from_spec(spec)
sys.modules["ts_cli"] = cli
spec.loader.exec_module(cli)

ECHECS = []


def verifie(cond, nom):
    print(("  ✓ " if cond else "  ✗ ") + nom)
    if not cond:
        ECHECS.append(nom)


CONF = {"pause": {"client": "iprospective", "project_id": 19, "activity_id": 27,
                  "commentaire": "repas midi", "heures": 1.0}}
SURCHARGES = {
    "2026-06-04": {"client": "calyclay", "pause_h": 0.75},   # hors période
    "2026-06-08": {"client": "calicote", "pause_h": 1.0},    # dans la période
}


def proposition(debut, fin):
    prop = {"lignes": []}
    cli.ajouter_pauses(prop, {"conf": CONF, "surcharges": SURCHARGES, "saisies": [],
                              "debut": debut, "fin": fin})
    return prop["lignes"]


lignes = proposition(datetime(2026, 6, 8), datetime(2026, 6, 10))
verifie([l["jour"] for l in lignes] == ["2026-06-08"],
        "seule la pause de la période proposée (le 04/06 ne s'invite plus)")
verifie(lignes and lignes[0]["minutes"] == 60 and lignes[0]["client"] == "iprospective",
        "…avec sa durée et sa cible")

large = proposition(datetime(2026, 6, 1), datetime(2026, 7, 1))
verifie(sorted(l["jour"] for l in large) == ["2026-06-04", "2026-06-08"],
        "sur le mois entier, les deux pauses sont bien là")

verifie(proposition(datetime(2026, 7, 1), datetime(2026, 8, 1)) == [],
        "un mois sans journée ajustée ne propose aucune pause")

# bornes de pause plutôt que durée : la ligne vaut la différence
SURCHARGES["2026-06-08"] = {"client": "calicote", "pause_debut": "12:30", "pause_fin": "13:15"}
lignes = proposition(datetime(2026, 6, 8), datetime(2026, 6, 10))
verifie(lignes and lignes[0]["minutes"] == 45, "des bornes de pause valent leur durée")

# ── La marque de déduplication distingue ce qui doit l'être (2026-10-20) ────
#
# Deux projets d'un même client, le même jour, sans ticket et avec la même activité
# partageaient une marque : la seconde saisie était prise pour un doublon de la
# première et n'était JAMAIS écrite. Quatre cas sur le seul mois de septembre, dont
# `calicote/infra` et `calicote/prestashop` le 01/09.
_j = "2026-09-01"
_a = {"jour": _j, "client": "calicote", "projet": "infra", "ticket": None, "activite": 9}
_b = {"jour": _j, "client": "calicote", "projet": "prestashop", "ticket": None, "activite": 9}
verifie(cli._marque(_a) != cli._marque(_b),
        "deux projets d'un même client ne partagent plus une marque")
verifie("infra" in cli._marque(_a), "la marque d'une ligne sans ticket nomme son projet")

# Un ticket détermine son projet : sa marque n'a pas à le répéter.
_t = {"jour": _j, "client": "calicote", "projet": "infra", "ticket": 2827, "activite": 9}
verifie(cli._marque(_t) == f"[timesheet:{_j}#calicote/2827]",
        "une ligne à ticket garde sa marque d'avant : rien à migrer")

# Deux morceaux d'une ligne scindée restent discernables.
_m = [dict(_a, cle="calicote/infra#-@9"), dict(_a, cle="calicote/infra#-@9~1")]
cli._poser_rangs(_m)
verifie(cli._marque(_m[0]) != cli._marque(_m[1]),
        "deux morceaux d'une même ligne scindée ont des marques distinctes")
verifie(not _m[0].get("rang"), "le premier morceau garde la marque sans rang")

# Le rang suit l'ordre des CLÉS, pas celui de la liste : il est stable au recalcul.
_m2 = list(reversed([dict(x) for x in _m]))
cli._poser_rangs(_m2)
verifie({cli._marque(x) for x in _m} == {cli._marque(x) for x in _m2},
        "l'ordre de la liste ne change pas les marques — sinon : doublons au recalcul")

# Les saisies déjà posées sous l'ancienne forme sont retrouvées, pas recréées.
_ancienne = f"[timesheet:{_j}#calicote/-@9]"
verifie(cli._marque_heritee(cli._marque(_a), {_ancienne}) == _ancienne,
        "une saisie posée avant le projet dans la marque est reconnue")
verifie(cli._marque_heritee(cli._marque(_a), {f"[timesheet:{_j}#calicote/-]"})
        == f"[timesheet:{_j}#calicote/-]",
        "et celle posée avant même l'activité aussi")
verifie(cli._marque_heritee(cli._marque(_a), set()) is None,
        "sans rien en base, aucune forme ancienne n'est inventée")


# ── Une journée sans aucune trace reste traitable (2026-10-20) ─────────────
#
# `calculer` sortait en erreur quand la période ne portait aucune trace : l'écran
# affichait « journée illisible » et la journée devenait inaccessible — alors
# qu'elle gardait souvent l'essentiel (le 02/06/2026 avait 6 saisies Redmine, 9
# tours d'agent, une note et un rendez-vous). Une absence de trace n'est pas une
# erreur : c'est un fait, parfois celui d'un dimanche.
import inspect as _inspect

_src = _inspect.getsource(cli.calculer)
verifie("sys.exit(f\"Aucune trace" not in _src and "sans_trace" in _src,
        "l'absence de trace n'interrompt plus le calcul")
verifie('"jour_demande"' in _src,
        "le résultat porte la journée demandée, pour qu'elle existe même vide")

_vj = _inspect.getsource(cli.vue_json)
verifie("jour_demande" in _vj,
        "la vue rend TOUJOURS la journée demandée — sinon : rien à clore")


# ── Ce qui est déjà posé se défalque, il ne se re-propose pas (22/07/2026) ──
_m_base = "[timesheet:2026-07-22#matnat/-@9/infra]"
_m_rang = "[timesheet:2026-07-22#matnat/-@9/infra+1]"
verifie(cli._marque_heritee(_m_rang, {_m_base}) is None,
        "un RANG est une seconde ligne, pas une autre écriture de la première")
verifie(cli._marque_heritee("[timesheet:2026-07-22#matnat/-@9/infra]",
                            {"[timesheet:2026-07-22#matnat/-@9]"})
        == "[timesheet:2026-07-22#matnat/-@9]",
        "les formes anciennes (sans projet) restent reconnues")

_prop = {"lignes": [{"jour": "2026-07-22", "client": "matnat", "projet": "infra",
                     "ticket": None, "activite": 9, "minutes": 105}]}
_res = {"saisies": [{"jour": "2026-07-22", "minutes": 60,
                     "libelle": "infra [timesheet:2026-07-22#matnat/-@9]"}]}
cli._retirer_deja_posees(_prop, _res)
verifie(len(_prop["lignes"]) == 1 and _prop["lignes"][0]["minutes"] == 45,
        "105 min dont 60 posées : il en reste 45 à écrire, pas 105 ni 0")
verifie(_prop["lignes"][0].get("rang") == 1,
        "et le reste prend un rang, sinon `--apply` le prendrait pour un doublon")

_prop2 = {"lignes": [{"jour": "2026-07-22", "client": "matnat", "projet": "infra",
                      "ticket": None, "activite": 9, "minutes": 60}]}
cli._retirer_deja_posees(_prop2, _res)
verifie(_prop2["lignes"] == [], "tout posé : plus rien à proposer")


print("\n" + ("ÉCHECS : " + " | ".join(ECHECS) if ECHECS else "Tous les tests passent."))
sys.exit(1 if ECHECS else 0)
