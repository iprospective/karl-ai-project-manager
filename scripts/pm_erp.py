#!/usr/bin/env python3
"""pm_erp — interface ErpProvider (facturation) + backend Dolibarr (RM2891).

Axe **erp** du registre des providers (`pm.config.yml` → `providers`) : l'ERP où
vivent les tiers, les services, les tarifs et les factures. Même patron que
`pm_doc` pour la documentation : un contrat générique, un backend par type, une
résolution par le registre — un client qui a son propre Dolibarr se branche en
déclarant une instance, sans toucher au code.

Le secret suit la convention des providers (`<PRÉFIXE>__<INSTANCE>__API_KEY`),
posé par `pm-provider-secret` et jamais relu ailleurs qu'ici. Le nom de la
variable est calculé par CE script-là : une seule règle de nommage.
"""
import collections
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_registry import resolve_instance


class ErpProviderError(Exception):
    """Backend ERP non supporté, secret absent, ou réponse d'erreur de l'ERP."""


def _nommage():
    """`pm-provider-secret` est la seule source de la règle de nommage des secrets."""
    spec = importlib.util.spec_from_file_location(
        "pm_provider_secret", str(Path(__file__).resolve().parent / "pm-provider-secret.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def variable_secret(instance, cle="API_KEY"):
    """`DOLIBARR__DOLIBARR_IPRO__API_KEY` pour l'instance `dolibarr-ipro`."""
    m = _nommage()
    prefixe = m.TYPE_PREFIXES.get(instance.type) or m.PREFIXES.get(instance.axis) or "ERP"
    return m.nom_variable(instance.name, cle, prefixe)


@dataclass
class Ligne:
    """Une ligne de facture, telle que l'ERP la porte."""
    quantite: float
    prix_unitaire: float
    service_id: int = None
    libelle: str = ""
    #: Taux de TVA en pourcentage. `None` laisse Dolibarr décider — et il décide 0,
    #: ce qui donne une facture FAUSSE (constaté le 20/10/2026 sur cinq brouillons).
    tva: float = None


@dataclass
class Facture:
    ref: str
    tiers_id: int
    date: date
    total_ht: float
    statut: str
    lignes: list
    note_publique: str = ""
    projet_id: int = None
    #: Conditions de règlement (délai de paiement). 0 ou None = aucune posée, et
    #: Dolibarr n'en met pas de lui-même : la facture part sans échéance.
    reglement_id: int = None
    #: Identifiant ERP. Sans lui, une facture lue ne peut pas être modifiée : on ne
    #: savait que créer et supprimer, donc « corriger » voulait dire recréer — ce qui
    #: perd le numéro et les retouches faites à la main (RM3529).
    id: int = None


class ErpProvider:
    """Contrat générique d'un ERP de facturation."""
    name = "base"

    def __init__(self, instance=None, http=None):
        self.instance = instance
        self._http = http
        self._terms = None          # dictionnaire des conditions de règlement, lu une fois

    def tiers(self):
        """{id: {"nom", "alias"}} — les clients facturables."""
        raise NotImplementedError

    def factures(self, limite=200):
        """[Facture], des plus récentes aux plus anciennes."""
        raise NotImplementedError

    def services(self):
        """{id: {"ref", "libelle"}} — le catalogue des prestations."""
        raise NotImplementedError

    def creer_brouillon(self, tiers_id, lignes, note_publique="", note_privee="",
                        quand=None, projet_id=None, reglement_id=None):
        """Crée une facture BROUILLON. Ne valide jamais : la validation reste humaine."""
        raise NotImplementedError

    def maj_note_publique(self, facture_id, texte):
        """Réécrit la note publique d'une facture existante, sans rien toucher d'autre.

        Corriger une facture ne doit pas passer par une recréation : cela perdrait son
        numéro et les retouches faites à la main (RM3529).
        """
        raise NotImplementedError

    def ajouter_ligne(self, facture_id, ligne):
        """Ajoute une ligne à une facture existante, sans rien supprimer (RM3529)."""
        raise NotImplementedError

    def dernier_taux_tva(self, tiers_id, factures=None):
        """Taux de TVA de la DERNIÈRE facture de ce tiers, ou None.

        Même règle que le tarif : la facture précédente fait foi. Un tiers exonéré
        garde son 0 % parce que ses factures le portent, pas parce qu'on l'a oublié.
        """
        for f in (factures if factures is not None else self.factures()):
            if f.tiers_id != tiers_id or f.statut == "brouillon":
                continue
            taux = collections.Counter(round(l.tva, 3) for l in f.lignes
                                       if l.quantite > 0 and l.tva is not None)
            if taux:
                return taux.most_common(1)[0][0]
        return None

    def dernier_reglement(self, tiers_id, factures=None):
        """Conditions de règlement de la DERNIÈRE facture de ce tiers, ou None.

        Même règle que le tarif et la TVA. Les valeurs nulles sont ignorées : une
        facture partie SANS délai ne fait pas jurisprudence, elle témoigne d'un oubli.
        """
        for f in (factures if factures is not None else self.factures()):
            if f.tiers_id != tiers_id or f.statut == "brouillon":
                continue
            if f.reglement_id:
                return f.reglement_id
        return None

    def dernier_tarif(self, tiers_id, factures=None):
        """Prix horaire de la DERNIÈRE facture de ce tiers, ou None s'il n'en a pas.

        C'est la règle voulue (RM2891) : pas de table de tarifs à tenir en double,
        la facture précédente fait foi. Le prix retenu est le plus fréquent de ses
        lignes à prix positif — une remise ou un avoir n'est pas un tarif.
        """
        for f in (factures if factures is not None else self.factures()):
            if f.tiers_id != tiers_id or f.statut == "brouillon":
                continue
            prix = collections.Counter(round(l.prix_unitaire, 2) for l in f.lignes
                                       if l.quantite > 0 and l.prix_unitaire > 0)
            if prix:
                return prix.most_common(1)[0][0]
        return None


_STATUTS = {"0": "brouillon", "1": "validée", "2": "payée", "3": "abandonnée"}


class DolibarrErpProvider(ErpProvider):
    """Backend Dolibarr — API REST (`/api/index.php`, en-tête DOLAPIKEY)."""
    name = "dolibarr"

    def _creds(self):
        url = (getattr(self.instance, "url", "") or "").rstrip("/")
        if not url:
            raise ErpProviderError(f"instance {self.instance.name!r} : url absente du registre")
        var = variable_secret(self.instance)
        cle = os.environ.get(var)
        if not cle:
            raise ErpProviderError(
                f"secret {var} absent — le poser : pm-provider-secret --instance "
                f"{self.instance.name} --key API_KEY < clé")
        return url, cle

    def api(self, methode, chemin, charge=None):
        url, cle = self._creds()
        if self._http is not None:                       # tests : transport injecté
            return self._http(methode, f"{url}/api/index.php/{chemin}", cle, charge)
        req = urllib.request.Request(
            f"{url}/api/index.php/{chemin}", method=methode,
            data=json.dumps(charge).encode() if charge is not None else None,
            headers={"DOLAPIKEY": cle, "Accept": "application/json",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                corps = r.read()
                return json.loads(corps) if corps else None
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read())["error"]["message"]
            except Exception:
                msg = ""
            if e.code == 404 and methode == "GET":
                return []                                 # liste vide : Dolibarr répond 404
            raise ErpProviderError(f"Dolibarr {methode} {chemin} → HTTP {e.code} {msg}")

    def _liste(self, chemin, par_page=100):
        sortie, page = [], 0
        while True:
            sep = "&" if "?" in chemin else "?"
            lot = self.api("GET", f"{chemin}{sep}limit={par_page}&page={page}") or []
            sortie += lot
            if len(lot) < par_page:
                return sortie
            page += 1

    def tiers(self):
        return {int(t["id"]): {"nom": t.get("name") or "", "alias": t.get("name_alias") or ""}
                for t in self._liste("thirdparties")}

    def services(self):
        return {int(p["id"]): {"ref": p.get("ref") or "", "libelle": p.get("label") or ""}
                for p in self._liste("products?mode=2")}

    def factures(self, limite=200):
        brut = self.api("GET", f"invoices?limit={limite}&sortfield=t.datef&sortorder=DESC") or []
        sortie = []
        for f in brut:
            lignes = [Ligne(tva=float(l.get("tva_tx") or 0),
                            quantite=float(l.get("qty") or 0),
                            prix_unitaire=float(l.get("subprice") or 0),
                            service_id=int(l["fk_product"]) if l.get("fk_product") else None,
                            libelle=(l.get("desc") or "").strip())
                      for l in (f.get("lines") or [])]
            quand = date.fromtimestamp(int(f["date"])) if f.get("date") else None
            sortie.append(Facture(
                ref=f.get("ref") or "", tiers_id=int(f["socid"]), date=quand,
                total_ht=float(f.get("total_ht") or 0),
                statut=_STATUTS.get(str(f.get("statut", f.get("status"))), "?"),
                lignes=lignes, note_publique=(f.get("note_public") or "").strip(),
                projet_id=int(f["fk_project"]) if f.get("fk_project") else None,
                reglement_id=int(f["cond_reglement_id"]) if f.get("cond_reglement_id") else None,
                id=int(f["id"]) if f.get("id") else None))
        return sortie

    def maj_note_publique(self, facture_id, texte):
        """Réécrit la note publique d'une facture, sans rien toucher d'autre.

        Modifier, pas recréer : une facture validée porte un numéro définitif et des
        retouches faites à la main dans Dolibarr. `supprimer_brouillon` + recréation
        perdait les deux — d'où cette voie, qui n'envoie que `note_public` (RM3529).

        Fonctionne aussi sur une facture validée : la note publique n'est pas un
        élément comptable. Attention cependant, le PDF déjà envoyé au client n'en est
        pas changé ; seule une regénération le reflète.
        """
        self.api("PUT", f"invoices/{int(facture_id)}", {"note_public": texte})
        return True

    def ajouter_ligne(self, facture_id, ligne):
        """Ajoute une ligne à une facture existante, sans rien supprimer.

        Corriger une facture ne doit pas passer par une recréation : `--replace`
        supprimait le brouillon et le refaisait, ce qui perd les retouches faites à la
        main et, sur une validée, serait impossible. Quand une facture est juste
        incomplète — un projet rattaché après coup, des heures oubliées — il suffit
        d'ajouter ce qui manque (RM3529).

        Relit le nombre de lignes avant et après : Dolibarr peut répondre sans écrire,
        et un POST silencieux ne prouve rien.
        """
        fid = int(facture_id)
        avant = len((self.api("GET", f"invoices/{fid}") or {}).get("lines") or [])
        self.api("POST", f"invoices/{fid}/lines", self._charge_ligne(ligne))
        apres = len((self.api("GET", f"invoices/{fid}") or {}).get("lines") or [])
        if apres != avant + 1:
            raise ErpProviderError(
                f"ligne non ajoutée à la facture {fid} : {avant} ligne(s) avant, "
                f"{apres} après — Dolibarr n'a rien écrit")
        return True

    def utilisateur_par_login(self, login, limite=100):
        """L'id Dolibarr d'un utilisateur, par son login. None s'il n'existe pas.

        Résoudre par login plutôt que coder un id : `karl` vaut 3 sur cette instance,
        et rien ne garantit la même valeur ailleurs.
        """
        for u in (self.api("GET", f"users?limit={int(limite)}") or []):
            if (u.get("login") or "") == login:
                return int(u["id"])
        return None

    def maj_auteur(self, facture_id, user_id):
        """Pose l'auteur (« créé par ») d'une facture. Rend True seulement si c'est pris.

        Vérifié le 25/10/2026 : Dolibarr accepte ce champ sur un brouillon **comme** sur
        une facture validée — 15 factures reprises, 15 posées. Mais un PUT qui répond
        sans broncher ne prouve rien : lors d'un premier essai manuel, le champ n'avait
        pas été pris alors que l'appel n'avait rien signalé. D'où la relecture, qui seule
        tranche (RM3529).
        """
        fid = int(facture_id)
        self.api("PUT", f"invoices/{fid}", {"user_author": int(user_id)})
        relu = self.api("GET", f"invoices/{fid}") or {}
        pose = relu.get("user_author") or relu.get("fk_user_author")
        return str(pose) == str(int(user_id))


    @staticmethod
    def _charge_ligne(l):
        """Une `Ligne` au format attendu par Dolibarr.

        Partagée par la création et l'ajout : une ligne ajoutée après coup doit avoir
        exactement la même forme que ses voisines, TVA et service compris (RM3529).
        """
        ligne = {"qty": round(float(l.quantite), 2), "subprice": float(l.prix_unitaire),
                 "product_type": 1, "desc": l.libelle or ""}
        # Sans `tva_tx`, Dolibarr pose 0 % : la facture part sans TVA.
        if l.tva is not None:
            ligne["tva_tx"] = float(l.tva)
        if l.service_id:
            ligne["fk_product"] = int(l.service_id)
        return ligne

    def creer_brouillon(self, tiers_id, lignes, note_publique="", note_privee="",
                        quand=None, projet_id=None, reglement_id=None):
        """Facture brouillon Dolibarr : l'entête, puis ses lignes. Jamais `validate`.

        Une facture émise ne se rattrape pas : l'outil s'arrête au brouillon, que
        l'humain relit dans Dolibarr avant de valider. Le `product_type` 1 (service)
        est imposé — une prestation de temps n'est pas une marchandise.
        """
        entete = {"socid": int(tiers_id), "type": 0,
                  "note_public": note_publique, "note_private": note_privee}
        if quand:
            entete["date"] = quand.isoformat() if hasattr(quand, "isoformat") else quand
        if projet_id:
            entete["fk_project"] = int(projet_id)
        # Sans conditions de règlement, Dolibarr n'en pose aucune : la facture part
        # sans échéance de paiement (constaté le 20/10/2026 sur les cinq de juin).
        #
        # Et on pose l'ÉCHÉANCE nous-mêmes : laissée à Dolibarr, elle tombait une
        # fois sur deux en 1970 — il la calcule à partir d'une date qu'il n'a pas
        # encore enregistrée, donc depuis zéro, et le délai seul fait « 15/01/1970 ».
        # Une facture est partie validée avec cette échéance (FA2610-0190).
        if reglement_id:
            entete["cond_reglement_id"] = int(reglement_id)
            echeance = self._echeance(quand, reglement_id)
            if echeance is not None:
                entete["date_lim_reglement"] = echeance
        fid = self.api("POST", "invoices", entete)
        if isinstance(fid, dict):
            fid = fid.get("id") or fid.get("rowid")
        if not fid:
            raise ErpProviderError(f"Dolibarr n'a pas rendu d'identifiant de facture (tiers {tiers_id})")
        for l in lignes:
            ligne = self._charge_ligne(l)
            self.api("POST", f"invoices/{fid}/lines", ligne)
        return int(fid)

    def factures_du_tiers(self, tiers_id, limite=100):
        brut = self.api("GET", f"invoices?thirdparty_ids={int(tiers_id)}&limit={limite}"
                               f"&sortfield=t.rowid&sortorder=DESC") or []
        return [{"id": int(f["id"]), "ref": f.get("ref") or "",
                 "statut": _STATUTS.get(str(f.get("statut", f.get("status"))), "?"),
                 "note_privee": (f.get("note_private") or ""),
                 # Nécessaire pour ne réécrire que ce qui change (RM3529).
                 "note_publique": (f.get("note_public") or "")} for f in brut]

    def _jours_reglement(self, reglement_id):
        """Nombre de jours d'une condition de règlement, depuis le dictionnaire."""
        if self._terms is None:
            self._terms = {}
            for d in (self.api("GET", "setup/dictionary/payment_terms?limit=100") or []):
                try:
                    self._terms[int(d["id"])] = int(d.get("nbjour") or 0)
                except (KeyError, TypeError, ValueError):
                    continue
        return self._terms.get(int(reglement_id))

    def _echeance(self, quand, reglement_id):
        """Date d'échéance = date de facture + délai, en timestamp. None si inconnue."""
        jours = self._jours_reglement(reglement_id)
        if not jours:
            return None
        base = quand or date.today()
        if not hasattr(base, "toordinal"):
            try:
                base = date.fromisoformat(str(base))
            except (TypeError, ValueError):
                return None
        cible = base + timedelta(days=int(jours))
        return int(datetime(cible.year, cible.month, cible.day).timestamp())

    #: Marge entre création et modification en deçà de laquelle on considère que
    #: personne n'y a touché : Dolibarr écrit les deux dates à quelques secondes.
    TOLERANCE_RETOUCHE_S = 90

    def supprimer_brouillon(self, facture_id, force=False):
        """Supprime une facture — brouillon, et non retouchée à la main.

        Deux relectures sur le serveur avant d'effacer, parce que c'est l'opération
        qu'on ne rattrape pas :

        - le STATUT : une facture validée, voire envoyée, ne se supprime pas ;
        - la date de MODIFICATION : un brouillon retouché depuis sa création porte
          du travail humain. L'écraser a déjà coûté des corrections en cours
          (20/10/2026 : « tu as supprimé les autres factures sur lesquelles je
          faisais des modifs »). `force` passe outre, en connaissance de cause.
        """
        f = self.api("GET", f"invoices/{int(facture_id)}") or {}
        ref = f.get("ref") or str(facture_id)
        statut = _STATUTS.get(str(f.get("statut", f.get("status"))), "?")
        if statut != "brouillon":
            raise RuntimeError(
                f"facture {ref} au statut « {statut} » : "
                f"seul un brouillon peut être supprimé")
        if not force and self._retouchee(f):
            raise RuntimeError(
                f"brouillon {ref} modifié à la main depuis sa création : "
                f"il porte peut-être un travail en cours. Le supprimer dans l'ERP, "
                f"ou relancer avec --force si c'est bien ce qu'on veut.")
        self.api("DELETE", f"invoices/{int(facture_id)}")
        return ref

    def _retouchee(self, facture):
        """Vrai si la facture a été modifiée nettement après sa création."""
        try:
            cree = int(facture.get("date_creation") or 0)
            modif = int(facture.get("date_modification") or facture.get("datem") or 0)
        except (TypeError, ValueError):
            return False
        if not cree or not modif:
            return False
        return (modif - cree) > self.TOLERANCE_RETOUCHE_S


_BACKENDS = {"dolibarr": DolibarrErpProvider}


def get_erp_provider(project_meta=None, registry=None, instance=None, http=None):
    """L'ERP d'un projet : instance explicite > registre (projet, client, défaut)."""
    if instance is None:
        if registry is None:
            raise ErpProviderError("ni instance ni registre : impossible de résoudre l'ERP")
        instance = resolve_instance(project_meta or {}, "erp", registry).instance
    backend = _BACKENDS.get(instance.type)
    if backend is None:
        raise ErpProviderError(f"backend erp {instance.type!r} non supporté (seul : dolibarr)")
    return backend(instance, http=http)
