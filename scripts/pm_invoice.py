#!/usr/bin/env python3
"""pm_invoice — proposer les factures d'un mois depuis les saisies de temps Redmine (RM2891).

Le temps facturable est dans Redmine : ce sont les saisies de l'utilisateur, qu'elles
viennent de `mmi-pm timesheet` ou de la main. Ce module les regroupe par CLIENT, puis
par ACTIVITÉ (→ un service du catalogue ERP) ou par TÂCHE, applique le tarif de la
dernière facture du client, et rédige la note publique au modèle habituel :

    Correspondant à mon Travail du 01/08/2026 au 31/08/2026.
    Principalement les 05, 12, 19 et 26 août.
    Détail de mon travail accessible sur https://tasks.iprospective.fr/.

Fonctions pures, testables sans réseau ; l'accès à Redmine et à l'ERP est injecté.
Une proposition ne crée rien : elle se relit, s'amende, puis s'applique.
"""
import collections
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


@dataclass
class Saisie:
    jour: str                 # AAAA-MM-JJ
    heures: float
    projet: str               # identifiant du projet Redmine
    ticket: int = None
    activite_id: int = None
    activite: str = ""
    commentaire: str = ""
    client: str = None        # rempli par rattacher()
    part: float = 1.0         # < 1 quand un projet mutualisé est éclaté (SFY 70/30)


@dataclass
class LigneProposee:
    libelle: str
    heures: float
    service_ref: str = None   # None = ligne libre
    tickets: list = field(default_factory=list)
    jours: list = field(default_factory=list)


# ── Rattacher une saisie à un client ─────────────────────────────────────────

def rattacher(saisies, projet_vers_client, entites, cles_multi=None):
    """Donne un client à chaque saisie ; éclate les projets mutualisés.

    Ordre : table déclarée / PM (`projet_vers_client`) → préfixe d'identifiant qui
    nomme une entité PM (`pisceen-dercya` → pisceen). Un projet mutualisé (clé
    multi-clients, ex. SFY) produit une saisie par client, au prorata : le total
    d'heures est conservé.
    """
    cles_multi = cles_multi or {}
    sortie, orphelins = [], []
    for s in saisies:
        client = projet_vers_client.get(s.projet)
        if client is None:
            # le plus long préfixe qui nomme une entité : `villa-cactus-yann` → villa-cactus
            candidats = [e for e in entites if s.projet == e or s.projet.startswith(e + "-")]
            client = max(candidats, key=len) if candidats else None
        if client is None:
            orphelins.append(s)
            continue
        cle = cles_multi.get(client)
        if cle:
            total = sum(p for _c, p in cle) or 1
            for c, p in cle:
                sortie.append(Saisie(**{**s.__dict__, "client": c, "part": s.part * p / total}))
        else:
            sortie.append(Saisie(**{**s.__dict__, "client": client}))
    return sortie, orphelins


# ── Regrouper en lignes de facture ───────────────────────────────────────────

def lignes_facture(saisies, services_par_activite, groupement="activite", titres=None):
    """Lignes d'une facture pour UN client.

    - `activite` (pratique historique) : une ligne par service du catalogue ; ce qui
      n'a pas de service devient une ligne libre « Divers ».
    - `tache` : une ligne par ticket ; le temps sans ticket, une ligne par activité.
    Le total d'heures est conservé à la minute près, quel que soit le mode.
    """
    titres = titres or {}
    groupes = collections.OrderedDict()
    for s in sorted(saisies, key=lambda x: (x.jour, x.ticket or 0)):
        service = (services_par_activite.get(s.activite_id)
                   or services_par_activite.get(s.activite))
        if groupement == "tache" and s.ticket:
            cle = ("tache", s.ticket)
            libelle = f"RM{s.ticket} — {titres.get(s.ticket, '')}".rstrip(" —")
        elif service:
            cle, libelle = ("service", service), None
        else:
            cle, libelle = ("libre", s.activite or "Divers"), s.activite or "Divers"
        g = groupes.setdefault(cle, LigneProposee(libelle=libelle or "", heures=0.0,
                                                  service_ref=service if cle[0] != "libre" else None))
        g.heures += s.heures * s.part
        if s.ticket and s.ticket not in g.tickets:
            g.tickets.append(s.ticket)
        if s.jour not in g.jours:
            g.jours.append(s.jour)
    for (nature, _cle), g in groupes.items():
        if nature == "libre":
            # la pratique des factures existantes : « Divers les 07, 13, 14, 27 avril »
            mois = MOIS[date.fromisoformat(sorted(g.jours)[0]).month - 1]
            g.libelle = f"Divers les {enumerer(j[8:10] for j in sorted(g.jours))} {mois}"
    return [g for g in groupes.values() if g.heures > 0]


def arrondir_heures(h, pas=0.01):
    """Dolibarr porte des heures décimales (8.58 = 8 h 35) : on garde le centième."""
    return round(round(h / pas) * pas, 2)


# ── Note publique ────────────────────────────────────────────────────────────

def jours_principaux(heures_par_jour, max_jours=8, seuil=1.0):
    """Les jours qui comptent : au moins `seuil` heures, les plus chargés d'abord,
    restitués dans l'ordre du calendrier."""
    retenus = [j for j, h in heures_par_jour.items() if h >= seuil] or list(heures_par_jour)
    retenus = sorted(retenus, key=lambda j: -heures_par_jour[j])[:max_jours]
    return sorted(retenus)


def enumerer(elements):
    elements = list(elements)
    if len(elements) <= 1:
        return "".join(elements)
    return ", ".join(elements[:-1]) + " et " + elements[-1]


def note_publique(debut, fin, jours, meps=None, url_detail="https://tasks.iprospective.fr/"):
    """Le modèle des factures existantes, à l'identique ; plus les mises en production."""
    lignes = [f"Correspondant à mon Travail du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}."]
    if jours:
        mois = MOIS[date.fromisoformat(jours[0]).month - 1]
        lignes.append(f"Principalement les {enumerer(j[8:10] for j in jours)} {mois}.")
    lignes.append(f"Détail de mon travail accessible sur {url_detail}.")
    if meps:
        lignes.append("")
        lignes.append("Mises en production :")
        lignes += [f"- RM{m['ticket']} — {m['titre']} ({m['jour'][8:10]}/{m['jour'][5:7]})"
                   for m in meps]
    return "\n".join(lignes)


# ── Mises en production du mois ──────────────────────────────────────────────

_TRANSITION = re.compile(r"status: (en_mep|a_mep)\s*\n\s*at: '?(\d{4}-\d{2}-\d{2})")


def mises_en_production(cfg, client, debut, fin):
    """Tickets du client passés en production pendant la période (status_history).

    Date retenue : le passage en `en_mep` (MEP effectuée), à défaut `a_mep`.
    """
    sortie = []
    for ent, proj, _ in cfg.iter_projects():
        if ent != client:
            continue
        try:
            dossier = cfg.path("tasks_dir", entity=ent, project=proj)
        except Exception:
            continue
        if not dossier.is_dir():
            continue
        for f in dossier.glob("RM*_*.md"):
            if f.name.endswith((".log.md", ".think.md")):
                continue
            texte = f.read_text(encoding="utf-8", errors="replace")
            led = f.parent / (f.name[:-3] + ".reporting.yml")
            if led.is_file():
                texte += "\n" + led.read_text(encoding="utf-8", errors="replace")
            dates = {}
            for statut, jour in _TRANSITION.findall(texte):
                if debut.isoformat() <= jour <= fin.isoformat():
                    dates.setdefault(statut, jour)
            if not dates:
                continue
            m = re.search(r"^title: (.+)$", texte, re.M)
            titre = (m.group(1).strip().strip("'\"").replace("''", "'") if m else "")
            sortie.append({"ticket": int(f.name[2:].split("_")[0]),
                           "titre": titre[:80], "jour": dates.get("en_mep") or dates["a_mep"]})
    return sorted(sortie, key=lambda m: m["jour"])


def marque(client, periode):
    """Clé de déduplication d'une facture : un client, un mois, une facture.

    Portée par la note PRIVÉE du brouillon : Dolibarr n'a aucun lien natif vers les
    saisies Redmine, et refacturer un mois déjà facturé est la faute qu'on ne peut
    pas rattraper après envoi.
    """
    return f"[invoice:{client}#{periode}]"


def deja_facture(marque_attendue, factures_du_tiers):
    """La facture existante qui porte cette marque, ou None."""
    for f in factures_du_tiers:
        if marque_attendue in (f.get("note_privee") or ""):
            return f
    return None


# ── Assemblage ───────────────────────────────────────────────────────────────

def proposer(saisies, debut, fin, *, tiers_par_client, tarifs, services_par_activite,
             groupement=None, titres=None, meps=None):
    """Une proposition de facture par client. Pure : tout arrive en paramètre."""
    groupement = groupement or {}
    par_client = collections.defaultdict(list)
    for s in saisies:
        par_client[s.client].append(s)
    propositions = []
    for client, liste in sorted(par_client.items()):
        tiers = tiers_par_client.get(client)
        lignes = lignes_facture(liste, services_par_activite,
                                groupement.get(client, "activite"), titres)
        heures_jour = collections.Counter()
        for s in liste:
            heures_jour[s.jour] += s.heures * s.part
        tarif = tarifs.get(client)
        total_h = sum(l.heures for l in lignes)
        propositions.append({
            "client": client, "tiers": tiers, "tarif": tarif,
            "heures": round(total_h, 2),
            "total_ht": round(sum(arrondir_heures(l.heures) for l in lignes) * tarif, 2) if tarif else None,
            "lignes": [{"libelle": l.libelle, "service": l.service_ref,
                        "heures": arrondir_heures(l.heures), "tickets": l.tickets} for l in lignes],
            "note_publique": note_publique(debut, fin, jours_principaux(heures_jour),
                                           (meps or {}).get(client)),
            "alertes": ([] if tiers else ["tiers ERP inconnu pour ce client"])
                       + ([] if tarif else ["aucune facture antérieure : tarif à saisir"]),
            "valide": bool(tiers and tarif),
        })
    return propositions
