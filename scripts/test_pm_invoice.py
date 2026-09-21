#!/usr/bin/env python3
"""Tests de pm_invoice et pm_erp — la proposition de factures (RM2891).

Lancer : python3 scripts/test_pm_invoice.py

Ce qu'ils protègent : aucune heure ne se perd entre les saisies et la facture
(rattachement, éclatement d'un projet mutualisé, regroupement), la note publique
reproduit le modèle des factures existantes, et le tarif vient bien de la
dernière facture — sans jamais prendre un brouillon ou un avoir pour un tarif.
"""
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from test_support import hermetic_core
hermetic_core()

import pm_erp
import pm_invoice as I
from pm_registry import Instance

ECHECS = []


def verifie(c, m):
    print(f"  {'✓' if c else '✗'} {m}")
    if not c:
        ECHECS.append(m)


def S(jour, h, projet, ticket=None, act=9, nom="Développement"):
    return I.Saisie(jour=jour, heures=h, projet=projet, ticket=ticket, activite_id=act, activite=nom)


print("\n1. Rattachement à un client")
saisies = [S("2026-08-05", 2, "pisceen-presta", 2680), S("2026-08-05", 1, "sfy-gestion"),
           S("2026-08-06", 1.5, "calicote-dolibarr"), S("2026-08-06", 0.5, "inconnu-xyz")]
table = {"pisceen-presta": "pisceen", "sfy-gestion": "sfy"}
r, orph = I.rattacher(saisies, table, {"pisceen", "calicote", "sfy"},
                      {"sfy": [("pisceen", 70), ("calicote", 30)]})
verifie([s.client for s in r if s.projet == "pisceen-presta"] == ["pisceen"], "table déclarée")
verifie([s.client for s in r if s.projet == "calicote-dolibarr"] == ["calicote"],
        "préfixe d'identifiant qui nomme une entité PM")
verifie(len(orph) == 1 and orph[0].projet == "inconnu-xyz", "l'inconnu est signalé, pas deviné")
r2, _o = I.rattacher([S("2026-08-18", 3, "villa-cactus-yann")], {}, {"villa", "villa-cactus"})
verifie(r2 and r2[0].client == "villa-cactus", "le plus long préfixe d'entité l'emporte")
sfy = [s for s in r if s.projet == "sfy-gestion"]
verifie(abs(sum(s.heures * s.part for s in sfy) - 1.0) < 1e-9, "SFY éclaté sans perte d'heure")
verifie(abs(next(s.part for s in sfy if s.client == "pisceen") - 0.7) < 1e-9, "…à 70/30")

print("\n2. Regroupement en lignes")
lot = [S("2026-08-05", 2, "p", 1, 9, "Développement"), S("2026-08-06", 1, "p", 2, 31, "Developpement/Feature"),
       S("2026-08-06", 0.5, "p", None, 13, "SysAdmin/Conf/Debug"), S("2026-08-07", 0.25, "p", None, 18, "Autre")]
for s in lot:
    s.client = "pisceen"
svc = {9: "SRV000003", 31: "SRV000003", 13: "SRV000025"}
par_act = I.lignes_facture(lot, svc, "activite")
verifie(abs(sum(l.heures for l in par_act) - 3.75) < 1e-9, "mode activité : total conservé")
verifie({l.service_ref for l in par_act} == {"SRV000003", "SRV000025", None},
        "une ligne par service, l'activité sans service en ligne libre")
verifie(next(l for l in par_act if l.service_ref == "SRV000003").heures == 3.0,
        "Développement et Feature réunis sous le même service")
par_tache = I.lignes_facture(lot, svc, "tache", {1: "Prix à partir de", 2: "Filtre"})
verifie(abs(sum(l.heures for l in par_tache) - 3.75) < 1e-9, "mode tâche : total conservé")
verifie(sum(1 for l in par_tache if l.libelle.startswith("RM")) == 2, "une ligne par ticket")
verifie(any(l.libelle == "RM1 — Prix à partir de" for l in par_tache), "libellé = ticket + titre")
verifie(any(l.libelle == "Divers les 07 août" for l in par_act),
        "ligne libre au modèle des factures : « Divers les <jours> »")

print("\n3. Note publique — le modèle des factures existantes")
jours = I.jours_principaux({"2026-08-05": 8, "2026-08-12": 3, "2026-08-19": 0.5, "2026-08-26": 7.6})
verifie(jours == ["2026-08-05", "2026-08-12", "2026-08-26"], "jours d'au moins 1 h, dans l'ordre")
n = I.note_publique(date(2026, 8, 1), date(2026, 8, 31), jours)
verifie(n == ("Correspondant à mon Travail du 01/08/2026 au 31/08/2026.\n"
              "Principalement les 05, 12 et 26 août.\n"
              "Détail de mon travail accessible sur https://tasks.iprospective.fr/."),
        "texte identique au modèle")
n2 = I.note_publique(date(2026, 8, 1), date(2026, 8, 31), jours,
                     [{"ticket": 2576, "titre": "Nettoyage cins", "jour": "2026-08-28"}])
verifie("Mises en production :\n- RM2576 — Nettoyage cins (28/08)" in n2, "section mises en production")

print("\n4. Proposition complète")
p = I.proposer(lot, date(2026, 8, 1), date(2026, 8, 31), tiers_par_client={"pisceen": 7},
               tarifs={"pisceen": 43.0}, services_par_activite=svc)
verifie(p[0]["total_ht"] == round(3.75 * 43, 2), "total HT = heures × tarif")
verifie(p[0]["valide"] and not p[0]["alertes"], "tiers et tarif connus : proposition valide")
p2 = I.proposer(lot, date(2026, 8, 1), date(2026, 8, 31), tiers_par_client={},
                tarifs={}, services_par_activite=svc)
verifie(not p2[0]["valide"] and len(p2[0]["alertes"]) == 2, "tiers et tarif inconnus : signalés")

print("\n5. Provider ERP (transport simulé)")
inst = Instance(name="dolibarr-ipro", axis="erp", type="dolibarr", url="https://erp.test", options={})
verifie(pm_erp.variable_secret(inst) == "DOLIBARR__DOLIBARR_IPRO__API_KEY",
        "nom du secret = convention pm-provider-secret")
F = pm_erp.Facture
L = pm_erp.Ligne
factures = [F("PROV1", 7, date(2026, 6, 11), -405, "brouillon", [L(1, 999)]),
            F("FA2", 7, date(2026, 6, 1), 1297, "payée", [L(8, 43), L(2, 43), L(1, -50)]),
            F("FA1", 7, date(2026, 4, 1), 900, "payée", [L(20, 40)])]
erp = pm_erp.DolibarrErpProvider(inst)
verifie(erp.dernier_tarif(7, factures) == 43, "tarif de la dernière facture, brouillon ignoré")
verifie(erp.dernier_tarif(99, factures) is None, "aucun tarif sans facture antérieure")
try:
    pm_erp.get_erp_provider(instance=Instance(name="x", axis="erp", type="sage", url="u", options={}))
    verifie(False, "type non supporté refusé")
except pm_erp.ErpProviderError:
    verifie(True, "type non supporté refusé")
import os
os.environ.pop("DOLIBARR__DOLIBARR_IPRO__API_KEY", None)
try:
    erp.factures()
    verifie(False, "secret absent : erreur explicite")
except pm_erp.ErpProviderError as e:
    verifie("pm-provider-secret" in str(e), "secret absent : erreur qui dit quoi faire")
os.environ["DOLIBARR__DOLIBARR_IPRO__API_KEY"] = "test"
brut = [{"ref": "FA9", "socid": "7", "date": "1780000000", "total_ht": "86", "statut": "2",
         "fk_project": "7", "note_public": "n", "lines": [{"qty": "2", "subprice": "43", "fk_product": "3"}]}]
erp2 = pm_erp.DolibarrErpProvider(inst, http=lambda m, u, k, c: brut)
f = erp2.factures()
verifie(f[0].statut == "payée" and f[0].lignes[0].service_id == 3, "facture Dolibarr décodée")

print("\n6. Table des projets")
import importlib.util
_spec = importlib.util.spec_from_file_location("pm_invoice_cli", str(_HERE / "pm-invoice.py"))
cli = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(cli)
verifie(cli.normaliser_entite("/zfs/x/projects/clients/matnat") == "matnat",
        "un chemin de dossier client redevient son identifiant (piège du résolveur)")
verifie(cli.normaliser_entite("pisceen") == "pisceen", "un identifiant reste tel quel")

print("\n" + ("ÉCHECS : " + " | ".join(ECHECS) if ECHECS else "Tous les tests passent."))
sys.exit(1 if ECHECS else 0)
