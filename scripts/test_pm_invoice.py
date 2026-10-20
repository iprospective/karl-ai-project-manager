#!/usr/bin/env python3
"""Tests de pm_invoice et pm_erp — la proposition de factures (RM2891).

Lancer : python3 scripts/test_pm_invoice.py

Ce qu'ils protègent : aucune heure ne se perd entre les saisies et la facture
(rattachement, éclatement d'un projet mutualisé, regroupement), la note publique
reproduit le modèle des factures existantes, et le tarif vient bien de la
dernière facture — sans jamais prendre un brouillon ou un avoir pour un tarif.
"""
import sys
from datetime import date, datetime
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

print("\n7. Brouillons : marque et idempotence")
m = I.marque("pisceen", "2026-08")
verifie(m == "[invoice:pisceen#2026-08]", "marque d'une facture : client et mois")
verifie(I.deja_facture(m, [{"ref": "FA1", "note_privee": "rien"},
                           {"ref": "FA2", "note_privee": f"posée {m}"}])["ref"] == "FA2",
        "une facture déjà posée est reconnue à sa marque")
verifie(I.deja_facture(m, [{"ref": "FA1", "note_privee": "[invoice:pisceen#2026-07]"}]) is None,
        "un autre mois n'est pas confondu")
appels = []
class FauxErp(pm_erp.DolibarrErpProvider):
    def api(self, methode, chemin, charge=None):
        appels.append((methode, chemin, charge))
        return {"id": 4242} if chemin == "invoices" else None
faux = FauxErp(inst)
fid = faux.creer_brouillon(7, [pm_erp.Ligne(8.5, 43.0, service_id=3),
                               pm_erp.Ligne(2.0, 43.0, libelle="Divers les 07, 13 août")],
                           note_publique="note", note_privee=m, quand=date(2026, 9, 21), projet_id=7)
verifie(fid == 4242 and appels[0][0] == "POST" and appels[0][1] == "invoices", "entête créé")
verifie(appels[0][2]["type"] == 0 and appels[0][2]["note_private"] == m,
        "type facture (0) et marque en note privée")
verifie(len(appels) == 3 and all(a[1] == "invoices/4242/lines" for a in appels[1:]),
        "une requête par ligne")
verifie(all(a[2]["product_type"] == 1 for a in appels[1:]), "lignes de SERVICE (product_type 1)")
verifie(appels[1][2]["fk_product"] == 3 and "fk_product" not in appels[2][2],
        "service du catalogue, ou ligne libre")
verifie(not any("validate" in a[1] for a in appels), "aucune validation : le brouillon reste brouillon")

# ── Projets qu'on ne facture pas (2026-10-20) ──────────────────────────────
print("\nProjets hors facturation")
_s = [I.Saisie(jour="2026-06-01", projet="ultramobile-kamishibai", heures=1.0,
               activite=9, commentaire="migration site"),
      I.Saisie(jour="2026-06-02", projet="calicote", heures=2.0,
               activite=9, commentaire="dev")]
_g, _e = I.ecarter_non_facturables(_s, ["ultramobile-kamishibai"])
verifie(len(_g) == 1 and _g[0].projet == "calicote", "le projet déclaré sort du lot")
verifie(len(_e) == 1 and _e[0].heures == 1.0, "et il est rendu à part, pas perdu en silence")
verifie(I.ecarter_non_facturables(_s, [])[1] == [], "sans liste, rien n'est écarté")
verifie(len(I.ecarter_non_facturables(_s, None)[0]) == 2, "ni avec une liste absente")
_, _orph = I.rattacher(_g, {}, {"calicote"})
verifie(_orph == [], "ce qui reste se rattache normalement")
# ── Ce que la ligne de facture dit du travail (2026-10-20) ─────────────────
print("\nDescription des lignes de facture")
verifie(I._sujet(1915, "Incident — IP failover (srv-prd/srv-mail), OVH Advance")
        == "RM1915 Incident — IP failover, OVH Advance",
        "un marqueur interne entre parenthèses sort, sans laisser sa ponctuation")
verifie("[À CHIFFRER]" not in I._sujet(1937, "Calibrer les coefficients [À CHIFFRER] du modèle"),
        "les mentions internes entre crochets ne partent pas chez le client")
verifie(I._sujet(999, "") == "RM999",
        "un ticket sans titre garde son numéro : il renvoie au détail en ligne")
verifie(I._sujet(1, "x" * 200).endswith("…") and len(I._sujet(1, "x" * 200)) <= I.MAX_TITRE + 12,
        "un titre trop long est coupé proprement")
verifie(I._sujet(2, "Analyse : le cas") == "RM2 Analyse : le cas",
        "l'espace avant « : » reste — c'est du français")

_lg = I.LigneProposee(libelle="", heures=3.0, service_ref="SRV1",
                      tickets=[11, 22], jours=["2026-06-03", "2026-06-07"])
_d = I.description_ligne(_lg, {11: "Migration", 22: "Correctif panier"})
verifie("RM11 Migration" in _d and "RM22 Correctif panier" in _d,
        "la description nomme les sujets traités")
verifie("les 03 et 07 juin" in _d, "et les jours concernés")
_un = I.LigneProposee(libelle="", heures=1.0, tickets=[5], jours=["2026-06-03"])
verifie("le 03 juin" in I.description_ligne(_un, {5: "X"}), "un seul jour se dit au singulier")
_bcp = I.LigneProposee(libelle="", heures=9.0, tickets=list(range(1, 10)),
                       jours=["2026-06-03"])
_db = I.description_ligne(_bcp, {})
verifie("et 5 autres" in _db, "au-delà de quatre sujets, on compte le reste")
verifie(len(I.description_ligne(
    I.LigneProposee(libelle="", heures=9.0, tickets=list(range(1, 5)),
                    jours=["2026-06-0%d" % d for d in range(1, 10)]),
    {i: "titre très long " * 5 for i in range(1, 5)})) <= I.MAX_DESCRIPTION + 2,
    "une description ne déborde jamais la longueur tenue")
verifie(I.description_ligne(I.LigneProposee(libelle="", heures=1.0), {}) == "",
        "sans ticket ni jour, pas de description inventée")


print("\nCe qui, dans un commentaire, mérite la facture")
verifie(I.commentaire_utile("Install NC Camille", "calicote") == "Install NC Camille",
        "une note écrite à la main est la meilleure description qui existe")
verifie(I.commentaire_utile("Travail assisté [timesheet:2026-06-01#x/1]", "x") == "",
        "la formule de l'outil et sa marque ne disent rien au client")
verifie(I.commentaire_utile("Travail assisté, dont 20 min d'outillage", "x") == "",
        "l'habillage « dont N min d'outillage » ne la rend pas parlante")
verifie(I.commentaire_utile("pisceen-presta", "pisceen-presta") == "",
        "redire le projet n'apprend rien : c'est déjà l'objet de la ligne")
verifie(I.commentaire_utile("Gestion+Réunion IA à détailler : parti 20h57", "x") == "",
        "une note écrite POUR SOI ne part pas chez le client")
verifie(I.commentaire_utile("opé 9h45 => 10h15 boulot à répartir", "x") == "",
        "un calcul d'heures à reprendre non plus")
verifie(I.commentaire_utile("Relai emails (pourquoi ??)", "x") == "",
        "ni une interrogation qu'on s'adresse")
verifie(I.commentaire_utile("ingestion tarifs", "x", deja=["ingestion tarifs fournisseur"]) == "",
        "un commentaire déjà dit par un titre ne se répète pas")

_lp = I.LigneProposee(libelle="", heures=2.0, jours=["2026-06-02"],
                      partages=["SFY", "Dolibarr"])
_dp = I.description_ligne(_lp, {})
verifie(_dp.startswith("Outillage commun partagé : SFY et Dolibarr"),
        "le travail mutualisé se dit par son objet, en tête quand il est seul")
verifie("RM" not in _dp, "et SANS ses tickets : ils parlent du commun, pas de ce client")
_mix = I.LigneProposee(libelle="", heures=2.0, jours=["2026-06-02"],
                       tickets=[7], partages=["SFY"])
verifie("RM7" in I.description_ligne(_mix, {7: "Sujet"})
        and "outillage commun partagé : SFY" in I.description_ligne(_mix, {7: "Sujet"}),
        "mêlé au travail du client, il vient après lui, en minuscule")


# ── TVA et suppression d'un brouillon (2026-10-20) ─────────────────────────
print("\nTVA et remplacement d'un brouillon")
import pm_erp as E

_appels = []
def _http(methode, url, cle, charge=None):
    _appels.append((methode, url.split("index.php/")[-1], charge))
    if methode == "GET" and "invoices/900" in url:
        return {"id": 900, "ref": "(PROV900)", "status": "0"}
    if methode == "GET" and "invoices/901" in url:
        return {"id": 901, "ref": "FA-901", "status": "1"}
    return {"id": 42}

_erp = E.DolibarrErpProvider(inst, http=_http)
verifie(_erp.supprimer_brouillon(900) == "(PROV900)", "un brouillon se supprime")
verifie(any(m == "DELETE" for m, _u, _c in _appels), "et c'est bien un DELETE")
_avant = len(_appels)
try:
    _erp.supprimer_brouillon(901)
    _refus = False
except RuntimeError as e:
    _refus = "validée" in str(e)
verifie(_refus, "une facture VALIDÉE ne se supprime pas — c'est ce qu'on ne rattrape pas")
verifie(not any(m == "DELETE" for m, _u, _c in _appels[_avant:]),
        "et aucun DELETE n'est parti pour elle")

# Le taux de TVA voyage jusqu'à la ligne créée.
_appels.clear()
_erp.creer_brouillon(7, [E.Ligne(quantite=2, prix_unitaire=45, tva=20.0)])
_lignes = [c for m, u, c in _appels if m == "POST" and "lines" in u]
verifie(_lignes and _lignes[0].get("tva_tx") == 20.0,
        "la ligne part avec son taux : sans lui, Dolibarr pose 0 %")
_appels.clear()
_erp.creer_brouillon(7, [E.Ligne(quantite=2, prix_unitaire=45)])
_l2 = [c for m, u, c in _appels if m == "POST" and "lines" in u]
verifie(_l2 and "tva_tx" not in _l2[0], "sans taux connu, on ne l'invente pas")

_ft = [F("FA9", 7, date(2026, 6, 1), 100, "payée",
         [E.Ligne(2, 45, tva=20.0), E.Ligne(1, 45, tva=20.0)]),
       F("PROV9", 7, date(2026, 6, 2), 50, "brouillon", [E.Ligne(1, 45, tva=0.0)])]
verifie(_erp.dernier_taux_tva(7, _ft) == 20.0,
        "le taux vient de la dernière facture ÉMISE, pas d'un brouillon")
verifie(_erp.dernier_taux_tva(99, _ft) is None,
        "sans facture antérieure, aucun taux n'est supposé")


# ── Ce qui a du temps facturable et pas de facture (RM3488) ───────────────
print("\nMois clos non facturés")
verifie(I.mois_clos(date(2026, 10, 20), max_mois=3) == ["2026-07", "2026-08", "2026-09"],
        "les mois ENTIÈREMENT écoulés, le mois courant exclu")
verifie(I.mois_clos(date(2026, 1, 5), max_mois=2) == ["2025-11", "2025-12"],
        "le passage d'année ne casse pas le compte")
verifie(I.mois_clos(date(2026, 10, 20), depuis="2026-09", max_mois=12) == ["2026-09"],
        "`depuis` borne au démarrage de l'outil : avant, on facturait à la main")

_h = {("2026-07", "pisceen"): 15.75, ("2026-07", "matnat"): 11.25,
      ("2026-08", "pisceen"): 35.5, ("2026-06", "pisceen"): 26.75}
_m = {"pisceen": {"2026-06", "2026-07"}}
_r = I.a_facturer(_h, _m, ["2026-07", "2026-08"])
verifie([(x["mois"], x["client"]) for x in _r] == [("2026-07", "matnat"), ("2026-08", "pisceen")],
        "ce qui est déjà facturé sort, le reste est rendu du plus ancien au plus récent")
verifie(all(x["heures"] > 0 for x in _r), "et chaque manque dit ce qu'il pèse")
verifie(I.a_facturer(_h, _m, []) == [], "aucun mois à voir : rien à dire")
verifie(I.a_facturer({("2026-07", "x"): 0.0}, {}, ["2026-07"]) == [],
        "un mois sans temps facturable n'est pas un manque")
verifie(I.a_facturer({}, {}, ["2026-07"]) == [], "ni un mois sans aucune saisie")


print("\nCe qui a été écrit pour le client passe devant (RM3489)")
_sd = [I.Saisie(jour="2026-10-15", projet="matnat-infra", projet_nom="MatNat Infra",
                heures=2.0, ticket=42, activite_id=9,
                commentaire="Mise en place de la validation des journées [timesheet:x]")]
_ld = I.lignes_facture(_sd, {}, titres={42: "Refonte interne du suivi"})
_dd = _ld[0].description
verifie(_dd.startswith("Mise en place de la validation des journées"),
        "la phrase écrite pour le client ouvre la description")
verifie("RM42 Refonte interne du suivi" in _dd,
        "le titre du ticket suit, il ne disparaît pas")

_sf = [I.Saisie(jour="2026-10-15", projet="matnat-infra", projet_nom="MatNat Infra",
                heures=2.0, ticket=42, activite_id=9,
                commentaire="Travail assisté [timesheet:x]")]
_lf = I.lignes_facture(_sf, {}, titres={42: "Refonte"})
verifie(not _lf[0].dites, "une formule de l'outil ne devient pas une phrase client")


# ── Parler la langue du client (RM3490) ───────────────────────────────────
print("\nReformulation par glossaire")
_g = {"*": {"reappro": "réapprovisionnement", "sysadmin": "administration système"},
      "calicote": {"antigaspi": "anti-gaspillage"}}
verifie(I.reformuler("Réappro étape 3", _g, "calicote") == "Réapprovisionnement étape 3",
        "le terme est remplacé, et la MAJUSCULE d'origine conservée")
verifie(I.reformuler("badge ANTIGASPI", _g, "calicote") == "badge ANTI-GASPILLAGE",
        "un mot tout en capitales le reste")
verifie(I.reformuler("badge antigaspi", _g, "pisceen") == "badge antigaspi",
        "le glossaire d'un client ne déborde pas sur un autre")
verifie(I.reformuler("du sysadmin", _g, "pisceen") == "du administration système",
        "le glossaire commun vaut pour tous — à charge du rédacteur que ça s'insère")
verifie(I.reformuler("reapprovisionnement fait", _g, None) == "reapprovisionnement fait",
        "un mot déjà clair n'est pas retouché")
verifie(I.reformuler("stock-reappro", _g, None) == "stock-réapprovisionnement",
        "un terme composé par un tiret est reconnu")
verifie(I.reformuler("Réapprochement", _g, None) == "Réapprochement",
        "pas de remplacement au milieu d'un mot : « réappro » n'est pas « réapprochement »")
verifie(I.reformuler("Réappro", None, "x") == "Réappro", "sans glossaire, rien ne bouge")
verifie(I.reformuler("", _g, "x") == "", "ni sur un texte vide")
verifie(I.reformuler("Réappro", {"*": {"reappro": ""}}, None) == "Réappro",
        "un remplacement vide est ignoré : on n'efface pas un mot par accident")

_lg = I.LigneProposee(libelle="", heures=1.0, tickets=[7], jours=["2026-06-03"])
_d = I.description_ligne(_lg, {7: "Réappro des stocks"}, glossaire=_g, client="calicote")
verifie("Réapprovisionnement des stocks" in _d,
        "la description d'une ligne passe par le glossaire")


print("\nÉchéance de paiement (RM2891, 20/10/2026)")
_ap = []
def _h2(methode, url, cle, charge=None):
    _ap.append((methode, url.split("index.php/")[-1], charge))
    if "payment_terms" in url:
        return [{"id": 9, "code": "10D", "nbjour": 10}, {"id": 11, "code": "14D", "nbjour": 14}]
    return 77
_e2 = E.DolibarrErpProvider(inst, http=_h2)
_e2.creer_brouillon(7, [E.Ligne(quantite=1, prix_unitaire=45, tva=20.0)],
                    quand=date(2026, 10, 20), reglement_id=11)
_entete = next(c for m2, u, c in _ap if m2 == "POST" and u == "invoices")
verifie(_entete.get("cond_reglement_id") == 11, "la condition de règlement part avec la facture")
_att = int(datetime(2026, 11, 3).timestamp())
verifie(_entete.get("date_lim_reglement") == _att,
        "et l'ÉCHÉANCE est calculée ICI : 20/10 + 14 jours = 03/11")

_ap.clear()
_e2.creer_brouillon(7, [E.Ligne(quantite=1, prix_unitaire=45)], quand=date(2026, 10, 20))
_e3 = next(c for m2, u, c in _ap if m2 == "POST" and u == "invoices")
verifie("date_lim_reglement" not in _e3,
        "sans condition de règlement, aucune échéance inventée")

verifie(_e2._echeance(date(2026, 10, 20), 9) == int(datetime(2026, 10, 30).timestamp()),
        "10 jours donnent le 30/10")
verifie(_e2._echeance(date(2026, 10, 20), 999) is None,
        "une condition inconnue ne produit pas une date absurde — surtout pas 1970")
verifie(_e2._echeance(None, 9) is not None, "sans date fournie, on part d'aujourd'hui")


print("\nUn brouillon retouché ne s'écrase pas (20/10/2026)")
_a3 = []
def _h3(methode, url, cle, charge=None):
    _a3.append((methode, url.split("index.php/")[-1]))
    if methode == "GET" and "invoices/300" in url:      # intact
        return {"id": 300, "ref": "(PROV300)", "status": "0",
                "date_creation": 1000, "date_modification": 1010}
    if methode == "GET" and "invoices/301" in url:      # retouché
        return {"id": 301, "ref": "(PROV301)", "status": "0",
                "date_creation": 1000, "date_modification": 9000}
    return {}
_e4 = E.DolibarrErpProvider(inst, http=_h3)
verifie(_e4.supprimer_brouillon(300) == "(PROV300)",
        "un brouillon que personne n'a touché se remplace")
_avant3 = len(_a3)
try:
    _e4.supprimer_brouillon(301)
    _refus3 = False
except RuntimeError as e:
    _refus3 = "modifié à la main" in str(e)
verifie(_refus3, "un brouillon RETOUCHÉ est refusé : il porte un travail en cours")
verifie(not any(m2 == "DELETE" for m2, _u in _a3[_avant3:]),
        "et aucun DELETE n'est parti pour lui")
verifie(_e4.supprimer_brouillon(301, force=True) == "(PROV301)",
        "`force` passe outre, en connaissance de cause")


print("\n" + ("ÉCHECS : " + " | ".join(ECHECS) if ECHECS else "Tous les tests passent."))
sys.exit(1 if ECHECS else 0)
