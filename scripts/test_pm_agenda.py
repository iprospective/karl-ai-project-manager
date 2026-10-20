#!/usr/bin/env python3
"""Tests RM3229 — l'agenda pro désigne le client d'une journée.

Sans réseau : seules les fonctions pures sont éprouvées. Ce qui compte ici n'est pas
de savoir lire du CalDAV, c'est de ne JAMAIS désigner un client par erreur : une
suggestion fausse se retrouve sur une facture.

Lancer : python3 scripts/test_pm_agenda.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_agenda as A

ECHECS = []


def verifie(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond:
        ECHECS.append(msg)


def ev(resume, journee=True):
    return {"resume": resume, "journee": journee, "debut": "20261012", "fin": "", "lieu": ""}


CLIENTS = ["matnat", "pisceen", "calicote", "calyclay", "caroline", "hera"]
ALIAS = {"calyprint": "calyclay", "calymix": "calyclay"}

print("\nCe que l'agenda désigne")
verifie(A.client_du_jour([ev("MatNat")], CLIENTS)["client"] == "matnat",
        "un titre qui nomme le client le désigne")
verifie(A.client_du_jour([ev("CalyClay CalyPrint CalyMix")], CLIENTS)["client"] == "calyclay",
        "un titre à plusieurs noms retient celui qu'on connaît")
verifie(A.client_du_jour([ev("CalyPrint")], CLIENTS, ALIAS)["client"] == "calyclay",
        "un alias ramène un nom de produit à son client")
verifie(A.client_du_jour([ev("Pisceen")], CLIENTS)["journee"] is True,
        "une journée entière est signalée comme telle")

print("\nCe qu'il ne désigne pas")
verifie(A.client_du_jour([], CLIENTS) is None, "sans rendez-vous, aucune suggestion")
verifie(A.client_du_jour([ev("Dentiste")], CLIENTS) is None,
        "un rendez-vous qui ne nomme aucun client n'en invente pas")
verifie(A.client_du_jour([ev("matnathalie")], CLIENTS) is None,
        "un nom de client inclus dans un autre mot ne compte pas")
verifie(A.client_du_jour([ev("MatNat"), ev("Pisceen")], CLIENTS) is None,
        "deux clients en journée entière : on ne tranche pas à sa place")
verifie(A.client_du_jour([ev("MatNat")], []) is None,
        "sans liste de clients, rien n'est deviné")

print("\nCe qui pèse le plus")
r = A.client_du_jour([ev("AirCall appel", journee=False), ev("Pisceen")], CLIENTS)
verifie(r and r["client"] == "pisceen",
        "une journée entière l'emporte sur un rendez-vous ponctuel")
r2 = A.client_du_jour([ev("Point Calicote", journee=False)], CLIENTS)
verifie(r2 and r2["client"] == "calicote" and r2["journee"] is False,
        "un rendez-vous ponctuel suffit quand il est seul, et se dit ponctuel")

print("\nNormalisation")
verifie(A._normalise("MatNat") == "matnat", "la casse ne compte pas")
verifie(A._normalise("Caroléne-Yoga") == "carolene yoga", "les accents et tirets non plus")
verifie(A.client_du_jour([ev("CALICOTE")], CLIENTS)["client"] == "calicote",
        "un titre en capitales est reconnu")

print("\nRobustesse")
verifie(A.evenements_periode("pas-une-date", "2026-10-02", {"env_path": "/absent"}) == {},
        "une période illisible ne lève rien")
verifie(A.evenements_periode("2026-10-01", "2026-10-02", {"env_path": "/absent"}) == {},
        "sans identifiants, l'agenda est muet — il ne casse pas la journée")
verifie(A.evenements_periode("2026-10-01", "2026-10-02", {"actif": False}) == {},
        "`actif: false` coupe la lecture sans rien tenter")
verifie(A.client_du_jour([{"resume": None}], CLIENTS) is None,
        "un événement sans titre est ignoré")

print("\n" + ("ÉCHECS : " + " | ".join(ECHECS) if ECHECS else "Tous les tests passent."))
sys.exit(1 if ECHECS else 0)
