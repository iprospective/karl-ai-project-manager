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
    #: Vrai quand la saisie vient d'un projet MUTUALISÉ, réparti entre plusieurs
    #: clients. Sur la facture, son détail ne se dit pas : le ticket parle du commun,
    #: pas de ce client-là.
    partage: bool = False
    projet_nom: str = ""      # nom lisible du projet Redmine (pour le dire au client)


@dataclass
class LigneProposee:
    libelle: str
    heures: float
    service_ref: str = None   # None = ligne libre
    tickets: list = field(default_factory=list)
    jours: list = field(default_factory=list)
    #: Le temps SANS ticket, par projet : {nom du projet : [notes retenues]}. Un
    #: ticket se décrit par son titre ; sans ticket, il ne reste que le projet et ce
    #: qui a été noté à la main — et c'est là que la note vaut (20/10/2026).
    sans_ticket: dict = field(default_factory=dict)
    #: Projets MUTUALISÉS touchés par cette ligne, par leur nom lisible. Leur détail
    #: ne se dit pas au client : c'est du commun, pas son travail à lui.
    partages: list = field(default_factory=list)
    #: Ce que la ligne recouvre, tel que le client le lira sous l'intitulé du service.
    #: Sans elle, une facture ne dit que « Développement 15 h » — exact, et muet.
    description: str = ""


# ── Rattacher une saisie à un client ─────────────────────────────────────────

def ecarter_non_facturables(saisies, exclus):
    """Sépare les saisies des projets qu'on ne facture pas. Rend (gardées, écartées).

    Un projet hors facturation n'est pas un projet « non rattaché » : le signaler
    comme orphelin à chaque mois reviendrait à demander de corriger ce qui est déjà
    correct. On le déclare une fois, et le rapport dit ce qui a été écarté — jamais
    en silence, sinon des heures disparaîtraient sans qu'on sache pourquoi.
    """
    exclus = {str(x) for x in (exclus or [])}
    if not exclus:
        return list(saisies), []
    gardees, ecartees = [], []
    for s in saisies:
        (ecartees if s.projet in exclus else gardees).append(s)
    return gardees, ecartees


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
                sortie.append(Saisie(**{**s.__dict__, "client": c,
                                        "part": s.part * p / total, "partage": True}))
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
        if s.partage:
            nom = s.projet_nom or s.projet
            if nom and nom not in g.partages:
                g.partages.append(nom)
        elif s.ticket and s.ticket not in g.tickets:
            g.tickets.append(s.ticket)
        if s.jour not in g.jours:
            g.jours.append(s.jour)
        if not s.ticket and not s.partage:
            projet = s.projet_nom or s.projet or "divers"
            notes = g.sans_ticket.setdefault(projet, [])
            note = commentaire_utile(s.commentaire, s.projet_nom, notes, s.projet)
            if note and note not in notes:
                notes.append(note)
    for (nature, _cle), g in groupes.items():
        if nature == "libre":
            # la pratique des factures existantes : « Divers les 07, 13, 14, 27 avril »
            mois = MOIS[date.fromisoformat(sorted(g.jours)[0]).month - 1]
            g.libelle = f"Divers les {enumerer(j[8:10] for j in sorted(g.jours))} {mois}"
        g.description = description_ligne(g, titres)
    return [g for g in groupes.values() if g.heures > 0]


#: Au-delà, une ligne de facture devient illisible — on dit « et N autres ».
MAX_SUJETS = 4
#: Un titre de ticket est écrit pour soi : au-delà, il déborde sur la facture.
MAX_TITRE = 70
#: Longueur totale d'une description. Une facture se lit, elle ne se dépouille pas.
MAX_DESCRIPTION = 300

#: Marqueurs internes qu'un titre de ticket traîne parfois — « [À CHIFFRER] »,
#: « [URGENT] », « (bloqué) ». Ils ne regardent pas le client.
_INTERNE_RE = re.compile(r"\s*[\[(](?:[^\])]{0,40})[\])]\s*")


#: Ce que l'outil écrit lui-même dans un commentaire : la marque de déduplication,
#: ses formules passe-partout. Rien de cela n'apprend quoi que ce soit au client.
_MARQUE_RE = re.compile(r"\s*\[timesheet:[^\]]*\]\s*")
#: Le suffixe que l'outil ajoute à ses propres commentaires. Il habille une formule
#: passe-partout sans la rendre parlante — « Travail assisté, dont 20 min d'outillage »
#: n'apprend rien de plus que « Travail assisté ». On le retire AVANT de juger.
_OUTILLAGE_RE = re.compile(r",?\s*dont\s+\d+\s*min\s+d['’]outillage\s*$", re.I)
_GENERIQUES = {"travail assiste", "travail assisté", "divers", "repas midi", "",
               "dev ia", "gestion ia", "divers dev"}

#: Marques d'une note écrite POUR SOI : un calcul d'heures à reprendre, un point
#: d'interrogation, une tâche en suspens. Une facture n'est pas un pense-bête —
#: « Gestion+Réunion IA à détailler : parti 20h57 » ne se lit pas chez un client.
_POUR_SOI_RE = re.compile(
    r"(\bà détailler\b|\bà répartir\b|\bà revoir\b|\bà reprendre\b|\bTODO\b|\bFIXME\b"
    r"|\?\?|=>|\bstopp?é\b|\bparti \d|\bboulot\b)", re.I)


def commentaire_utile(texte, projet=None, deja=(), projet_id=None):
    """Le commentaire d'une saisie, s'il dit quelque chose. Sinon : rien.

    Mathieu note souvent à la main ce que le ticket ne dit pas (« Install NC Camille »,
    « config redir vacances »). C'est la description la plus juste qui existe — mais
    seulement quand elle est écrite : les formules de l'outil (« Travail assisté ») et
    les reprises du nom de projet n'apprennent rien et encombrent la facture.
    """
    t = _MARQUE_RE.sub(" ", texte or "").strip(" -—·,;")
    t = _OUTILLAGE_RE.sub("", t).strip(" -—·,;")
    t = re.sub(r"\s+", " ", t)
    if not t or t.lower() in _GENERIQUES:
        return ""
    if _POUR_SOI_RE.search(t):
        return ""
    # Un fragment d'un ou deux caractères (« IA », « ok ») ne décrit rien : c'est
    # souvent ce qui reste d'une note qu'on vient d'élaguer.
    if len(t) < 6 and len(t.split()) < 2:
        return ""
    # Un commentaire qui ne fait que redire le projet (« pisceen-presta ») n'apprend
    # rien : le client sait pour quel projet il paie, c'est l'objet de la ligne.
    plat = lambda x: re.sub(r"[^a-z0-9]+", " ", str(x or "").lower()).strip()
    pt = plat(t)
    # Égal au projet, ou simple morceau de son nom (« site_sf7 » dans « MatNat site
    # SF7 ») : le client sait déjà pour quel projet il paie.
    if pt and any(pt == p or (p and pt in p) for p in (plat(projet), plat(projet_id)) if p):
        return ""
    # Le commentaire qui redit un titre déjà cité ne l'enrichit pas.
    norme = t.lower()
    if any(norme in str(d).lower() for d in deja):
        return ""
    if len(t) > MAX_TITRE:
        t = t[:MAX_TITRE].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return t


def _sujet(ticket, titre):
    """Un sujet présentable : le titre nettoyé, coupé, ou le numéro à défaut."""
    t = _INTERNE_RE.sub(" ", titre or "").strip(" -—:·")
    t = re.sub(r"\s+", " ", t)
    # Retirer un morceau laisse sa ponctuation orpheline (« injoignables , OVH »).
    # Seules la virgule et le point perdent leur espace : en français, « : », « ; »,
    # « ! » et « ? » la gardent.
    t = re.sub(r"\s+([,.])", r"\1", t)
    t = re.sub(r"([,;:])\s*(?=[,;:])", "", t).strip(" ,;:-—")
    if len(t) > MAX_TITRE:
        t = t[:MAX_TITRE].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return f"RM{ticket} {t}".strip() if t else f"RM{ticket}"


def description_ligne(ligne, titres=None, max_sujets=MAX_SUJETS):
    """Ce que la ligne recouvre : les sujets traités, puis les jours.

    Une facture qui ne porte que « Développement — 15 h » est exacte et illisible :
    le client ne peut ni la vérifier ni s'en souvenir. On lui donne les SUJETS, pris
    des titres de tickets — ce que le ticket dit de lui-même, pas un résumé inventé.

    Les tickets sans titre connu restent nommés par leur numéro plutôt que tus : un
    numéro renvoie au détail en ligne, une absence ne renvoie à rien.
    """
    titres = titres or {}
    sujets = [_sujet(t, titres.get(t) or titres.get(str(t)) or "")
              for t in (ligne.tickets or [])]
    tete = sujets[:max_sujets]
    reste = len(sujets) - len(tete)
    morceaux = []
    if tete:
        morceaux.append(" · ".join(tete) + (f" · et {reste} autre{'s' if reste > 1 else ''}"
                                            if reste > 0 else ""))
    # Le travail MUTUALISÉ se dit par son objet, jamais par ses tickets : ceux-ci
    # parlent du commun — d'autres clients, d'autres besoins — et n'ont pas à figurer
    # sur la facture de celui-ci (arbitrage du 20/10/2026).
    if ligne.partages:
        quoi = enumerer(ligne.partages[:max_sujets])
        tete_mot = "outillage commun partagé" if morceaux else "Outillage commun partagé"
        morceaux.append(f"{tete_mot} : {quoi}")
    # Le temps sans ticket se dit par son PROJET, suivi de ce qui a été noté à la
    # main : c'est là, et seulement là, que la note apporte quelque chose.
    for projet, notes in (ligne.sans_ticket or {}).items():
        utiles = [n for n in notes if n][:max_sujets]
        if utiles:
            morceaux.append(f"{projet} : {' · '.join(utiles)}")
        elif not sujets:
            # Un projet sans note ne vaut d'être nommé que si rien d'autre ne parle.
            morceaux.append(str(projet))
    jours = sorted(set(ligne.jours or []))
    if jours:
        mois = MOIS[date.fromisoformat(jours[0]).month - 1]
        morceaux.append(f"les {enumerer(j[8:10] for j in jours)} {mois}"
                        if len(jours) > 1 else
                        f"le {jours[0][8:10]} {mois}")
    texte = " — ".join(morceaux)
    if len(texte) > MAX_DESCRIPTION:
        texte = texte[:MAX_DESCRIPTION].rsplit(" · ", 1)[0].rstrip(" ·—,") + " …"
    return texte


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
                        "heures": arrondir_heures(l.heures), "tickets": l.tickets,
                        # Amendable à la main dans le `.yml` avant `--apply` : c'est le
                        # texte que le client lira, il doit pouvoir être corrigé.
                        "description": l.description} for l in lignes],
            "note_publique": note_publique(debut, fin, jours_principaux(heures_jour),
                                           (meps or {}).get(client)),
            "alertes": ([] if tiers else ["tiers ERP inconnu pour ce client"])
                       + ([] if tarif else ["aucune facture antérieure : tarif à saisir"]),
            "valide": bool(tiers and tarif),
        })
    return propositions
