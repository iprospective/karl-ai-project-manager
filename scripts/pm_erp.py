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
from datetime import date
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


class ErpProvider:
    """Contrat générique d'un ERP de facturation."""
    name = "base"

    def __init__(self, instance=None, http=None):
        self.instance = instance
        self._http = http

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
                        quand=None, projet_id=None):
        """Crée une facture BROUILLON. Ne valide jamais : la validation reste humaine."""
        raise NotImplementedError

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
            lignes = [Ligne(quantite=float(l.get("qty") or 0),
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
                projet_id=int(f["fk_project"]) if f.get("fk_project") else None))
        return sortie


    def creer_brouillon(self, tiers_id, lignes, note_publique="", note_privee="",
                        quand=None, projet_id=None):
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
        fid = self.api("POST", "invoices", entete)
        if isinstance(fid, dict):
            fid = fid.get("id") or fid.get("rowid")
        if not fid:
            raise ErpProviderError(f"Dolibarr n'a pas rendu d'identifiant de facture (tiers {tiers_id})")
        for l in lignes:
            ligne = {"qty": round(float(l.quantite), 2), "subprice": float(l.prix_unitaire),
                     "product_type": 1, "desc": l.libelle or ""}
            if l.service_id:
                ligne["fk_product"] = int(l.service_id)
            self.api("POST", f"invoices/{fid}/lines", ligne)
        return int(fid)

    def factures_du_tiers(self, tiers_id, limite=100):
        brut = self.api("GET", f"invoices?thirdparty_ids={int(tiers_id)}&limit={limite}"
                               f"&sortfield=t.rowid&sortorder=DESC") or []
        return [{"id": int(f["id"]), "ref": f.get("ref") or "",
                 "note_privee": (f.get("note_private") or "")} for f in brut]


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
