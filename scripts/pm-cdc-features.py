#!/usr/bin/env python3
"""pm-cdc-features — le registre des FONCTIONNALITÉS d'un projet (RM3043 ; fusionné par RM3099).

Une fonctionnalité est **ce que le système sait faire**. Elle existe pour elle-même, se dit en
langage d'usage, et **cite 0, 1 ou plusieurs tickets** en référence (RM3099-D001, arbitrage Mathieu :
« les fonctionnalités n'ont pas besoin d'un ticket pour exister ») — le ticket est une trace de
travail, pas la définition. Le registre vit dans `docs/cdc/fonctionnalites.yml` (id `F001…` STABLE,
jamais réattribué) ; le chapitre `docs/cdc-features.md` et la feuille de route `docs/cdc-roadmap.md`
en sont GÉNÉRÉS — plusieurs vues, une donnée.

Le projet a longtemps porté DEUX registres : `cdc/` dérivé des tickets (RM3043) et `cdc-karl/` curé
à la main par capacité (RM3048). Deux `F001` différents pour le même projet, deux roadmaps, deux
taxonomies, un lien déjà faux. RM3099 les a fusionnés : **il n'y en a plus qu'un** (`--absorb`).

**Deux orientations, une seule hiérarchie** (RM3099-D002, « l'usage est prioritaire ») : `domaine`
est le domaine d'**USAGE** — c'est lui qui groupe le chapitre ; `domaine_technique` est posé en
**étiquette**, une colonne, jamais un second niveau de plan.

  --sync                ajoute les tickets nouveaux (tout sauf `nouveau`), met à jour état/date des
                        existants ; ne recrée JAMAIS d'entrée pour un ticket déjà cité
  --build               écrit le chapitre et la feuille de route depuis le registre
  --check               registre, chapitre et roadmap à jour ? (exit 1 sinon) — garde de livraison
  --absorb <yml>        verse un AUTRE registre dans celui-ci : ses entrées y passent à la suite
                        (ids neufs), et toute entrée dérivée dont le ticket est désormais cité
                        disparaît — absorbée, sans perdre la référence (RM3099)
  --init                crée le registre ; `--no-sync` le laisse vide (à remplir à la main)
  --project <client>/<projet>   défaut : le projet du workspace courant (`.mmi-pm`)
  --docs-dir / --tasks-dir      surcharges (tests)

Champs d'une entrée : `libelle`, `domaine` (usage), `domaine_technique` (étiquette), `tickets`
(liste, éventuellement VIDE), `etat`, `date`, `type`, `restants` (tickets encore ouverts),
`version` (RM3060), `parent`, `manuel: true` (libellé et domaine tenus à la main),
`etat_manuel: true` (état posé à la main, `--set-etat` — RM3064).

**L'état** se dérive des tickets cités, et c'est **le plus avancé** qui compte (RM3099-D003) : une
capacité livrée reste livrée quand un ticket d'évolution s'ouvre à côté. Ce qui reste ouvert n'est
pas caché pour autant — `restants` le compte, et le chapitre l'affiche (« livré · 2 en cours »).
Une fonctionnalité SANS ticket garde l'état qu'on lui a posé.

**Versions (RM3060)** — une version est une ÉTAPE DE TRAVAIL, pas une liste de fonctionnalités :
elle porte un rôle (ce qu'elle doit permettre) et un critère de passage. Elles vivent dans
`versions` du même registre, et `cdc-roadmap.md` en est GÉNÉRÉ.

  --add-version V1 --role "…" [--critere "…"] [--etat-version prévu]   crée ou complète une version
  --set-version F001 V1          rattache une fonctionnalité à une version (`-` la détache)
  --drop-version V1              retire la version du registre ET des entrées qui la portaient
  --assign-version V [--etat livré]   la pose en masse sur les entrées qui n'en ont pas

États (dérivés du statut des tickets) : livré (fermé résolu) · en cours (en_cours, tests, MEP,
a_corriger) · prévu (a_faire, étude) · en pause · écarté (fermé autre raison).
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_think   # noqa: E402  RM3053
from pm_think import is_task_sheet  # RM3053 : la fiche, jamais un frère (.log.md, .think.md)
try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

#: Les domaines d'USAGE — la seule hiérarchie du chapitre (RM3099-D002). Les douze premiers viennent
#: du registre curé de RM3048, écrits du point de vue de celui qui se sert du système ; les quatre
#: derniers couvrent ce que ce registre-là n'avait pas à couvrir (il ne parlait que du cockpit) et
#: sans quoi la moitié du projet tomberait dans « Autre ». Premier qui matche : l'ordre compte, du
#: plus spécifique au plus général.
DEFAULT_DOMAINES = [
    ("Voix & accessibilité", r"\bvoix\b|vocal|dict(ée|ee|er)\b|synthèse vocale|\bTTS\b|\bSTT\b|accessibilit"),
    ("Emails & compte-rendu client", r"\bmail|e-mail|email|imap|smtp|newsletter|compte[- ]rendu|relance client|notification client"),
    ("Revue & file de test", r"revue|review|recette|file de test|à tester|a_tester|protocole de test"),
    ("Worklog & travail par lots", r"worklog|par lots?|\bbatch\b|file d'attente|\bqueue\b|reste à faire"),
    ("Jeux de sessions", r"jeu de sessions|multi[- ]sessions?|orchestrat|sous[- ]agent|essaim|fan[- ]?out|en parallèle|parallélis"),
    ("Sessions & terminal", r"session|terminal|tmux|ttyd|transcript|spawn|resume|reprise|compact|claude|opencode|\bagent|outline"),
    ("Navigation, onglets & mobile", r"onglet|navigation|mobile|android|responsive|raccourci|clavier|thème|\bdark\b|layout|panneau|écran|affichage|\bUI\b|ergonomi"),
    ("Réglages, fournisseurs & moteurs", r"réglage|reglage|paramétr|paramètre|setting|fournisseur|provider|moteur|modèle|\bmodel\b|prompt"),
    ("Git, fichiers & livraison", r"\bgit\b|branche|\bMR\b|merge|gitlab|gogs|github|forge|\bMEP\b|worktree|push|commit|submodule|release|déploi|deploy|promotion|fichier|\bdiff\b|patch"),
    ("Tickets & PM", r"ticket|tâche|task|redmine|statut|status|workflow|checklist|description|done_ratio|assign|estim|priorit|fermeture|close|\bCF\b"),
    ("Projets, clients & documentation", r"projet|project|client|contact|aspect|bootstrap|\bdocs?\b|wiki|glossaire|readme|changelog|knowledge|\baide\b|help|dictionnaire|\bCDC\b|arborescence|symlink|logo|charte"),
    ("Supervision & diagnostic", r"supervision|zabbix|monitor|diagnostic|incident|alerte|\blogs?\b|journal|santé|doctor|panne|erreur"),
    ("Coûts, temps & ROI", r"\broi\b|coût|cout|prix|pricing|timesheet|heure|budget|conso|facturation|tarif|métrique|metric"),
    ("Méthode & normes", r"norms|norme|kernel|méthode|tripwire|protocole|règle|governance|gouvernance|précharge"),
    ("Environnements, infra & sécurité", r"\benv\b|environnement|lxc|vhost|zfs|instance|install|provision|systemd|sudo|apache|nginx|serveur|machine|conteneur|opensvc|\bdns\b|backup|snapshot|infra|vault|secret|keepass|1password|nextcloud|\bPAT\b|sécurité|droits|permission|credential|\bclé"),
    ("Socle technique & qualité", r"\bworm\b|\btest|qualit|lint|\bci\b|flaky|régression|refacto|architecture|performance|migration|\bORM\b|\bcache|rendu|innerHTML|découp|bundle|stack|bench|verrou|concurrence"),
]

#: Les domaines TECHNIQUES — une ÉTIQUETTE, pas un plan (RM3099-D002). Ils disent « quelle partie du
#: système est touchée » là où le domaine d'usage dit « à quoi ça sert ». Ils groupaient le chapitre
#: avant RM3099 : gardés parce qu'ils portent une information vraie, rétrogradés parce qu'un lecteur
#: qui cherche une capacité ne cherche pas un répertoire de code.
DEFAULT_TECHNIQUES = [
    ("Cockpit & karl-agent", r"cockpit|onglet|panneau|karl-agent|ttyd|terminal|dashboard|tableau de bord|composer|vibe|mobile|android"),
    ("WORM (ORM)", r"\bworm\b"),
    ("Outillage PM (scripts, CLI, skills)", r"\bpm-|mmi-pm|\bskill|script|\bcli\b|wrapper|porcelain|cheatsheet"),
    ("Sessions & agents", r"session|transcript|orchestrat|sous-agent|worker|tmux|spawn|\bagent|claude|opencode|resume|reprise|outline"),
    ("Communication (mail, SMS, notifications)", r"\bmail|e-mail|email|telegram|\bsms\b|notif|alerte|voix|vocal|imap|dictée"),
    ("Git, forge & MEP", r"\bgit|branche|\bMR\b|merge|gitlab|gogs|github|forge|\bMEP\b|promotion|worktree|push|commit|submodule|release|licence|license"),
    ("Redmine & workflow des tickets", r"redmine|\bCF\b|statut|status|workflow|ticket|tâche|task|sous-tâche|checklist|description|done_ratio|récurr|assign|attribution|fermeture|close"),
    ("Environnements & infra", r"\benv|lxc|vhost|zfs|instance|install|provision|deploy|déploi|systemd|sudo|apache|nginx|serveur|machine|\bhost|conteneur|opensvc|zabbix|\bdns\b|backup|snapshot|infra|prestashop|runtime"),
    ("Secrets & sécurité", r"vault|secret|token|\bPAT\b|sécurité|security|droits|\bauth|permission|confinement|credential|clé|\bkey"),
    ("Métriques, ROI & coûts", r"\broi\b|temps|coût|cout|prix|pricing|\btick|timesheet|heure|usage|budget|bench|conso|métrique|metric|estim|ledger|reporting"),
    ("NORMS & méthode", r"norms|norme|kernel|\bcdc\b|méthode|tripwire|doctor|protocole|règle|governance|gouvernance|précharge|contexte|ergonomi"),
    ("Docs, wiki & knowledge", r"\bdoc|wiki|glossaire|knowledge|readme|\baide|changelog|help|dictionnaire|journal|tags?\b"),
    ("Projets, clients & modèle PM", r"projet|project|client|contact|bootstrap|aspect|overview|meta\.yml|provider|entité|workspace|\.mmi-pm|pm\.config|cascade|modèle|stack"),
    ("Tests & qualité", r"\btest|qualit|lint|\bci\b|flaky|régression"),
]
AUTRE = "À classer"        # RM3099 : un groupe honnête et ACTIONNABLE, pas un fourre-tout sans nom
ETATS_MANUELS = ("prévu", "en cours", "en pause", "écarté", "livré")
#: une version a les mêmes états qu'une fonctionnalité — c'est une étape de travail, elle avance pareil
ETATS_VERSION = ETATS_MANUELS
#: du moins avancé au plus avancé : c'est le PLUS avancé qui donne son état à une fonctionnalité
#: multi-tickets (RM3099-D003). `écarté` ne compte que si tout l'est.
RANG_ETAT = {"écarté": 0, "en pause": 1, "prévu": 2, "en cours": 3, "livré": 4}
_VERSION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,15}$")
ACTIFS = {"en_cours", "a_tester_dev", "a_tester_demandeur", "a_tester_verifier", "a_tester_preprod", "a_mep", "en_mep", "a_corriger"}
PREVUS = {"a_faire", "a_etudier_chiffrer", "etude_chiffrage_en_cours", "etude_chiffrage_a_valider",
          "etude_chiffrage_a_corriger"}
FM_RE = re.compile(r"\A---\n(.*?)\n---", re.S)


def etat_de(fm):
    st = fm.get("status")
    if st == "ferme":
        return "livré" if (fm.get("close_reason") in (None, "resolu")) else f"écarté ({fm.get('close_reason')})"
    if st in ACTIFS:
        return "en cours"
    if st in PREVUS:
        return "prévu"
    if st == "en_pause":
        return "en pause"
    return None   # nouveau (non trié) ou inconnu : hors registre


def _rang(etat):
    return RANG_ETAT.get(str(etat or "").split(" (")[0], -1)


def etat_agrege(etats):
    """L'état d'une fonctionnalité depuis ceux de SES tickets : le plus avancé, et le nombre de
    tickets qui ne sont pas encore livrés. Pure.

    Pourquoi le plus avancé et non « livré seulement si tous le sont » (RM3099-D003) : une
    fonctionnalité utilisable reste utilisable quand un ticket d'évolution s'ouvre à côté d'elle.
    L'inverse ferait retomber en « en cours » une capacité qui marche depuis des mois — un état
    faux, et l'usage prime (D002). Ce qui reste ouvert est compté, pas dissimulé."""
    connus = [e for e in etats if e]
    if not connus:
        return None, 0
    best = max(connus, key=_rang)
    restants = sum(1 for e in connus if _rang(e) < RANG_ETAT["livré"])
    return best, restants


def date_de(fm):
    if fm.get("status") == "ferme":
        for h in reversed(fm.get("status_history") or []):
            if isinstance(h, dict) and h.get("status") == "ferme" and h.get("at"):
                return str(h["at"])[:10]
    return str(fm.get("updated") or fm.get("created") or "")[:10]


def lire_tickets(tasks_dir: Path):
    out = []
    for f in sorted(tasks_dir.glob("RM*.md")):
        if not is_task_sheet(f):
            continue
        m = FM_RE.match(f.read_text(encoding="utf-8"))
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        if not fm.get("redmine_id"):
            continue
        out.append(fm)
    out.sort(key=lambda fm: int(fm["redmine_id"]))
    return out


def domaine_de(titre, domaines):
    for d in domaines or []:
        if d.get("mots") and re.search(d["mots"], titre, re.I):
            return d["nom"]
    return AUTRE


def libelle_de(fm):
    return " ".join(str(fm.get("title") or "").split())


def tickets_de(e) -> list:
    """Les tickets d'une entrée. `rm` était l'ancienne forme (un ticket = une entrée) : lu, jamais
    réécrit — RM3099 a fait de `tickets` la seule (D005)."""
    out = [int(x) for x in (e.get("tickets") or [])]
    if e.get("rm") and int(e["rm"]) not in out:
        out.insert(0, int(e["rm"]))
    return out


def _domaines(defauts):
    return [{"nom": n, "mots": rx} for n, rx in defauts]


def registre_vide(projet):
    return {"projet": projet,
            "domaines": _domaines(DEFAULT_DOMAINES),
            "domaines_techniques": _domaines(DEFAULT_TECHNIQUES),
            "entrees": []}


def sync(reg, tickets):
    """Ajoute les tickets absents, met à jour état/date/libellé/domaines. Retourne (ajoutés, modifiés).

    Un ticket DÉJÀ cité par une entrée (`tickets:`) n'en crée jamais une seconde : c'est ce qui
    permet à une fonctionnalité de couvrir plusieurs tickets sans que l'outil la double."""
    reg.setdefault("domaines", _domaines(DEFAULT_DOMAINES))
    reg.setdefault("domaines_techniques", _domaines(DEFAULT_TECHNIQUES))
    par_fm = {int(fm["redmine_id"]): fm for fm in tickets}
    cites = {t for e in reg["entrees"] for t in tickets_de(e)}
    nxt = 1 + max([int(e["id"][1:]) for e in reg["entrees"]] or [0])
    ajout, modif = [], []
    for fm in tickets:
        rm = int(fm["redmine_id"])
        if rm in cites or etat_de(fm) is None:
            continue
        lib = libelle_de(fm)
        e = {"id": f"F{nxt:03d}", "libelle": lib, "domaine": domaine_de(lib, reg["domaines"]),
             "domaine_technique": domaine_de(lib, reg["domaines_techniques"]),
             "type": fm.get("type") or "feature", "etat": etat_de(fm), "date": date_de(fm),
             "tickets": [rm]}
        if fm.get("parent_task"):
            e["parent"] = int(fm["parent_task"])
        reg["entrees"].append(e); cites.add(rm); nxt += 1; ajout.append(e)
    for e in reg["entrees"]:
        avant = dict(e)
        # normalisation RM3099-D005 : `rm` (un ticket = une entrée) se fond dans `tickets`, la seule
        # forme désormais. Deux champs pour la même chose, c'est deux lecteurs qui divergent.
        tk = tickets_de(e)
        if tk:
            e["tickets"] = tk
        e.pop("rm", None)
        rms = [t for t in tk if t in par_fm]
        if rms:
            etat, restants = etat_agrege([etat_de(par_fm[t]) for t in rms])
            if etat is not None and not e.get("etat_manuel"):
                e["etat"] = etat
            # `restants` n'a de sens que sur une fonctionnalité qui couvre PLUSIEURS tickets : sur
            # une entrée mono-ticket, l'état le dit déjà, et le champ ne serait que du bruit.
            if restants and len(rms) > 1:
                e["restants"] = restants
            else:
                e.pop("restants", None)
            e["date"] = max(date_de(par_fm[t]) for t in rms)
            if len(rms) == 1 and not e.get("manuel"):
                fm = par_fm[rms[0]]
                e["libelle"] = libelle_de(fm); e["type"] = fm.get("type") or e.get("type")
        if not e.get("manuel"):
            e["domaine"] = domaine_de(e.get("libelle") or "", reg["domaines"])
        e["domaine_technique"] = domaine_de(e.get("libelle") or "", reg["domaines_techniques"])
        if e != avant and e not in ajout:
            modif.append(e)
    return ajout, modif


def absorbe(reg, autre):
    """Verse un AUTRE registre dans celui-ci (RM3099). Retourne (versées, absorbées).

    Deux registres pour un projet, c'était deux `F001` différents, deux roadmaps et deux taxonomies.
    Cette fonction en fait un : les entrées de `autre` passent ici avec des ids NEUFS (ceux d'ici
    sont déjà publiés, ce sont eux qui restent) ; puis toute entrée d'ici dont tous les tickets sont
    désormais cités par une entrée versée disparaît — **absorbée**, pas perdue : son ticket reste
    référencé par l'entrée qui l'a reprise, mieux écrite.

    Les domaines de `autre` (orientés usage) passent EN TÊTE des domaines d'ici : c'est eux qui
    groupent le chapitre. Ceux d'ici, techniques, deviennent la table des étiquettes (D002)."""
    reg.setdefault("entrees", [])
    nxt = 1 + max([int(e["id"][1:]) for e in reg["entrees"]] or [0])
    versees = []
    for src in (autre.get("entrees") or []):
        e = {"id": f"F{nxt:03d}", "libelle": src.get("libelle") or "",
             "domaine": src.get("domaine") or AUTRE,
             "type": src.get("type") or "feature", "etat": src.get("etat") or "prévu",
             "date": src.get("date") or "", "tickets": tickets_de(src), "manuel": True}
        for opt in ("version", "jalon", "parent", "etat_manuel"):
            if src.get(opt) is not None:
                e[opt] = src[opt]
        reg["entrees"].append(e); versees.append(e); nxt += 1
    repris = {t for e in versees for t in tickets_de(e)}
    absorbees = [e for e in reg["entrees"]
                 if e not in versees and tickets_de(e) and set(tickets_de(e)) <= repris]
    reg["entrees"] = [e for e in reg["entrees"] if e not in absorbees]
    # les domaines d'USAGE prennent la tête ; les techniques deviennent la table des étiquettes
    usage = [d for d in (autre.get("domaines") or []) if d.get("nom")]
    connus = {d["nom"] for d in usage}
    reg["domaines_techniques"] = reg.get("domaines_techniques") or reg.get("domaines") or _domaines(DEFAULT_TECHNIQUES)
    reg["domaines"] = usage + [d for d in _domaines(DEFAULT_DOMAINES) if d["nom"] not in connus]
    for d in reg["domaines"]:                      # une table d'usage sans mots-clés ne classerait rien
        if not d.get("mots"):
            d["mots"] = dict(DEFAULT_DOMAINES).get(d["nom"], "")
    for e in reg["entrees"]:
        if not e.get("manuel"):
            e["domaine"] = domaine_de(e.get("libelle") or "", reg["domaines"])
        e["domaine_technique"] = e.get("domaine_technique") or domaine_de(e.get("libelle") or "", reg["domaines_techniques"])
    return versees, absorbees


def versions_de(reg) -> list:
    """Les versions déclarées, dans l'ordre du registre. Une version absente du registre mais portée par
    une entrée est rendue quand même : mieux vaut une roadmap complète qu'une roadmap juste."""
    decl = [v for v in (reg.get("versions") or []) if isinstance(v, dict) and v.get("id")]
    connus = {v["id"] for v in decl}
    orphelines = sorted({str(e.get("version")) for e in reg.get("entrees", [])
                         if e.get("version") and str(e["version"]) not in connus})
    return decl + [{"id": v, "role": "", "etat": "", "critere": "", "orpheline": True} for v in orphelines]


def ajoute_version(reg, vid, role=None, critere=None, etat=None) -> bool:
    """Crée la version ou complète ce qui est donné. Rend True si elle a été créée."""
    if not _VERSION_RE.match(vid or ""):
        raise ValueError(f"identifiant de version invalide : {vid!r}")
    if etat and etat not in ETATS_VERSION:
        raise ValueError(f"état inconnu « {etat} » — admis : {', '.join(ETATS_VERSION)}")
    reg.setdefault("versions", [])
    v = next((x for x in reg["versions"] if isinstance(x, dict) and x.get("id") == vid), None)
    neuve = v is None
    if neuve:
        v = {"id": vid, "role": "", "etat": "prévu", "critere": ""}
        reg["versions"].append(v)
    if role is not None:
        v["role"] = role
    if critere is not None:
        v["critere"] = critere
    if etat:
        v["etat"] = etat
    return neuve


def rattache(reg, fid, vid) -> dict:
    """Rattache une fonctionnalité à une version (vid `-` ou vide : la détache). Rend l'entrée."""
    e = next((x for x in reg.get("entrees", []) if x.get("id") == fid), None)
    if not e:
        raise KeyError(f"entrée {fid} introuvable")
    if vid in (None, "", "-"):
        e.pop("version", None)
        return e
    if not _VERSION_RE.match(vid):
        raise ValueError(f"identifiant de version invalide : {vid!r}")
    e["version"] = vid
    return e


def retire_version(reg, vid) -> int:
    """Retire la version du registre et de toutes les entrées. Rend le nombre d'entrées détachées."""
    reg["versions"] = [v for v in (reg.get("versions") or []) if not (isinstance(v, dict) and v.get("id") == vid)]
    n = 0
    for e in reg.get("entrees", []):
        if str(e.get("version") or "") == vid:
            e.pop("version", None); n += 1
    return n


def build_roadmap(reg) -> str:
    """La feuille de route : une ligne par version, son rôle, son état, son critère de passage, et
    COMBIEN de fonctionnalités s'y rattachent — le lien entre les deux vues, sans les recopier."""
    vers = versions_de(reg)
    ents = reg.get("entrees", [])
    par_v = {}
    for e in ents:
        v = str(e.get("version") or (f"V{e['jalon']}" if e.get("jalon") is not None else ""))
        if v:
            par_v.setdefault(v, []).append(e)
    L = [f"# Feuille de route — {reg.get('titre') or ('projet `' + reg['projet'] + '`')}", "",
         "> **Généré** par `pm-cdc-features --build` depuis [`cdc/fonctionnalites.yml`](cdc/fonctionnalites.yml) — ne pas éditer ici.",
         "> Une version est une **étape de travail** : ce qu'elle doit permettre, et à quoi on sait qu'elle est passée.",
         "> La liste des fonctionnalités, elle, vit dans [cdc-features.md](cdc-features.md) : la version y est une **colonne**.", ""]
    if not vers:
        L += ["_Aucune version déclarée._ En ajouter une : `pm-cdc-features --add-version V1 --role \"…\" --build`,",
              "ou depuis le cockpit, onglet CDC → Feuille de route.", ""]
        return "\n".join(L)
    L += ["| Version | Rôle | État | Fonctionnalités | Critère de passage |", "|---|---|---|---|---|"]
    for v in vers:
        rows = par_v.get(v["id"], [])
        livres = sum(1 for e in rows if e.get("etat") == "livré")
        compte = f"{livres}/{len(rows)}" if rows else "—"
        role = (v.get("role") or "").replace("|", "/") or ("_(version portée par des fonctionnalités, non déclarée)_" if v.get("orpheline") else "_(à définir)_")
        L.append(f"| {v['id']} | {role} | {v.get('etat') or '—'} | {compte} | {(v.get('critere') or '').replace('|', '/')} |")
    L.append("")
    for v in vers:
        rows = par_v.get(v["id"], [])
        if not rows:
            continue
        L += [f"## {v['id']} — {(v.get('role') or 'sans rôle défini')} ({len(rows)})", ""]
        for e in sorted(rows, key=lambda x: x.get("id") or ""):
            tk = "".join(f" · RM{t}" for t in tickets_de(e)[:1])
            L.append(f"- **{e['id']}** {e['libelle'].replace('|', '/')}{tk} — {e.get('etat') or ''}")
        L.append("")
    sans = [e for e in ents if not e.get("version") and e.get("jalon") is None and e.get("etat") in ("prévu", "en cours")]
    if sans:
        L += [f"## Sans version ({len(sans)})", "",
              "_Ces fonctionnalités sont en cours ou prévues et ne sont rattachées à aucune étape._", ""]
        for e in sorted(sans, key=lambda x: x.get("id") or ""):
            L.append(f"- {e['id']} {e['libelle'].replace('|', '/')} — {e.get('etat') or ''}")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def dump(reg):
    head = ("# FONCTIONNALITÉS du projet — registre tenu par pm-cdc-features (RM3043, fusionné RM3099).\n"
            "# UNE fonctionnalité = ce que le système sait faire ; elle cite 0, 1 ou PLUSIEURS tickets (`tickets:`),\n"
            "# et peut n'en citer aucun (RM3099-D001). `id` F001… STABLE, jamais réattribué.\n"
            "# `domaine` = domaine d'USAGE (il groupe le chapitre) ; `domaine_technique` = étiquette (D002).\n"
            "# `etat` dérivé des tickets, le plus avancé l'emporte (D003) ; `restants` compte ceux encore ouverts.\n"
            "# Pour corriger libellé/domaine à la main : les éditer ET poser `manuel: true`, sinon `--sync` les réécrit.\n"
            "# Le chapitre `cdc-features.md` et `cdc-roadmap.md` sont GÉNÉRÉS d'ici (`--build`) : ne pas les éditer.\n")
    return head + yaml.safe_dump(reg, allow_unicode=True, sort_keys=False, width=160)


def compose(reg, chap: Path) -> str:
    """Le chapitre : partie générée + bloc `think-merge` existant conservé (RM3053)."""
    block = ""
    if chap.is_file():
        old = chap.read_text(encoding="utf-8")
        if pm_think.MERGE_BEGIN in old and pm_think.MERGE_END in old:
            block = old[old.index(pm_think.MERGE_BEGIN): old.index(pm_think.MERGE_END) + len(pm_think.MERGE_END)]
    return build(reg) + ("\n## Détail par ticket (depuis les `.think.md`)\n\n" + block + "\n" if block else "")


def etat_affiche(e):
    """« livré », ou « livré · 2 en cours » quand la fonctionnalité porte encore du travail ouvert."""
    etat = e.get("etat") or ""
    n = int(e.get("restants") or 0)
    return f"{etat} · {n} en cours" if n and not etat.startswith(("en cours", "prévu")) else etat


def build(reg):
    ents = reg["entrees"]
    declares = [d["nom"] for d in reg.get("domaines") or []]
    ordre = declares + sorted({e.get("domaine") for e in ents if e.get("domaine") and e.get("domaine") not in declares and e.get("domaine") != AUTRE}) + [AUTRE]
    par_dom = {}
    for e in ents:
        par_dom.setdefault(e.get("domaine") or AUTRE, []).append(e)
    cnt = {}
    for e in ents:
        k = "écarté" if str(e["etat"]).startswith("écarté") else e["etat"]; cnt[k] = cnt.get(k, 0) + 1
    L = [f"# {reg.get('titre') or ('Fonctionnalités du projet `' + reg['projet'] + '`')}", "",
         "> **Généré** par `pm-cdc-features --build` depuis [`cdc/fonctionnalites.yml`](cdc/fonctionnalites.yml) — ne pas éditer ici.",
         "> Une ligne par **fonctionnalité** — ce que le système sait faire. Elle cite les tickets qui l'ont",
         "> construite, s'il y en a : une fonctionnalité n'a pas besoin d'un ticket pour exister (RM3099).",
         "> Le plan suit l'**usage** ; la colonne *Technique* dit quelle partie du système est touchée.", "",
         "| État | Nombre |", "|---|---|"]
    for k in ("livré", "en cours", "prévu", "en pause", "écarté"):
        if k in cnt:
            L.append(f"| {k} | {cnt[k]} |")
    L.append("")
    for dom in ordre:
        rows = par_dom.get(dom)
        if not rows:
            continue
        feats = [e for e in rows if e.get("type") != "bugfix"]; bugs = [e for e in rows if e.get("type") == "bugfix"]
        ver = lambda e: str(e.get("version") or (f"V{e['jalon']}" if e.get("jalon") is not None else ""))
        jal = any(ver(e) for e in ents)
        L += [f"## {dom} ({len(rows)})", ""]
        if feats:
            L += ["| # | Fonctionnalité | Ticket(s) | Technique | Type | " + ("Version | " if jal else "") + "État | Date |",
                  "|---|---|---|---|---|" + ("---|" if jal else "") + "---|---|"]
            for e in feats:
                lib = e["libelle"].replace("|", "/")
                if e.get("parent"):
                    lib += f" *(sous-tâche de RM{e['parent']})*"
                tk = ", ".join(f"RM{t}" for t in tickets_de(e)) or "—"
                jc = (f" {ver(e)} |" if ver(e) else " — |") if jal else ""
                L.append(f"| {e['id']} | {lib} | {tk} | {e.get('domaine_technique') or ''} | {e.get('type') or ''} |{jc} {etat_affiche(e)} | {e.get('date') or ''} |")
            L.append("")
        if bugs:
            L += [f"**Corrections ({len(bugs)})** :", ""]
            for e in bugs:
                tk = ", ".join(f"RM{t}" for t in tickets_de(e)) or "sans ticket"
                L.append(f"- {e['id']} · {tk} · {e['libelle'].replace('|', '/')} — {etat_affiche(e)} {e.get('date') or ''}")
            L.append("")
    return "\n".join(L).rstrip() + "\n"


def resoudre(args):
    if args.docs_dir and args.tasks_dir:
        return Path(args.docs_dir), Path(args.tasks_dir), args.project or "?"
    from pm_paths import PMConfig
    cfg = PMConfig.load()
    ref = args.project
    if not ref:
        mm = Path.cwd() / ".mmi-pm"
        if mm.exists():
            p = mm.resolve(); ref = f"{p.parent.parent.name}/{p.name}"
    if not ref or "/" not in ref:
        sys.exit("--project <client>/<projet> requis (ou un workspace avec .mmi-pm)")
    c, p = ref.split("/", 1)
    return cfg.path("docs_dir", entity=c, project=p), cfg.path("tasks_dir", entity=c, project=p), ref


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project"); ap.add_argument("--docs-dir"); ap.add_argument("--tasks-dir")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--sync", action="store_true"); ap.add_argument("--build", action="store_true"); ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-sync", action="store_true", help="avec --init : registre vide (à remplir à la main)")
    ap.add_argument("--absorb", metavar="YML", help="verse un autre registre dans celui-ci (RM3099)")
    ap.add_argument("--assign-version", metavar="V", help="pose cette version sur les entrées qui n'en ont pas (filtre --etat)")
    ap.add_argument("--set-etat", nargs=2, metavar=("ID", "ETAT"), help="pose l'état d'une entrée (prévu · en cours · en pause · écarté · livré) et le fige (RM3064)")
    ap.add_argument("--etat", help="avec --assign-version : seulement les entrées de cet état (ex. livré)")
    ap.add_argument("--add-version", metavar="V", help="crée ou complète une version (RM3060)")
    ap.add_argument("--role", help="avec --add-version : ce que la version doit permettre")
    ap.add_argument("--critere", help="avec --add-version : à quoi on sait qu'elle est passée")
    ap.add_argument("--etat-version", help="avec --add-version : " + " · ".join(ETATS_VERSION))
    ap.add_argument("--set-version", nargs=2, metavar=("ID", "V"), help="rattache une fonctionnalité à une version (« - » : détache)")
    ap.add_argument("--drop-version", metavar="V", help="retire une version du registre et des entrées")
    a = ap.parse_args()
    docs, tasks, projet = resoudre(a)
    reg_path = docs / "cdc" / "fonctionnalites.yml"
    if a.init:
        if reg_path.exists():
            sys.exit(f"registre déjà présent : {reg_path}")
        reg = registre_vide(projet)
    elif reg_path.is_file():
        reg = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
        reg.setdefault("entrees", [])
        reg.setdefault("domaines", _domaines(DEFAULT_DOMAINES))
        reg.setdefault("domaines_techniques", _domaines(DEFAULT_TECHNIQUES))
        reg.pop("prefix", None); reg.pop("cure", None)   # RM3099 : un seul registre, plus de préfixe
    else:
        sys.exit(f"aucun registre {reg_path} — `pm-cdc-features --init`")
    chap = docs / "cdc-features.md"
    road = docs / "cdc-roadmap.md"
    if a.check:
        avant = dump(reg)
        sync(reg, lire_tickets(tasks))
        apres = dump(reg)
        ok_reg = avant == apres; ok_chap = chap.exists() and chap.read_text(encoding="utf-8") == compose(reg, chap)
        ok_road = road.exists() and road.read_text(encoding="utf-8") == build_roadmap(reg)
        print(f"{'✓' if ok_reg else '✗'} registre à jour ({reg_path.name}, {len(reg['entrees'])} entrées)")
        print(f"{'✓' if ok_chap else '✗'} chapitre à jour ({chap.name})")
        print(f"{'✓' if ok_road else '✗'} feuille de route à jour ({road.name}, {len(versions_de(reg))} version(s))")
        if not (ok_reg and ok_chap and ok_road):
            print("  → pm-cdc-features --sync --build"); sys.exit(1)
        return
    if a.absorb:
        src = Path(a.absorb)
        if not src.is_file():
            sys.exit(f"registre à absorber introuvable : {src}")
        autre = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
        versees, absorbees = absorbe(reg, autre)
        reg_path.parent.mkdir(parents=True, exist_ok=True); reg_path.write_text(dump(reg), encoding="utf-8")
        print(f"✓ {len(versees)} entrée(s) versée(s) depuis {src.name}, "
              f"{len(absorbees)} entrée(s) dérivée(s) absorbée(s) — {len(reg['entrees'])} au total")
        if not (a.sync or a.build):
            return
    if a.set_etat:
        fid, etat = a.set_etat
        if etat not in ETATS_MANUELS:
            sys.exit(f"état inconnu « {etat} » — admis : {', '.join(ETATS_MANUELS)}")
        e = next((x for x in reg["entrees"] if x.get("id") == fid), None)
        if not e:
            sys.exit(f"entrée {fid} introuvable dans {reg_path}")
        e["etat"] = etat; e["etat_manuel"] = True
        reg_path.write_text(dump(reg), encoding="utf-8"); print(f"✓ {fid} → {etat} (état figé : etat_manuel)")
        if not a.build:
            return
    if a.add_version:
        try:
            neuve = ajoute_version(reg, a.add_version, a.role, a.critere, a.etat_version)
        except ValueError as e:
            sys.exit(f"ERREUR : {e}")
        reg_path.write_text(dump(reg), encoding="utf-8")
        print(f"✓ version {a.add_version} {'créée' if neuve else 'mise à jour'}")
        if not a.build:
            return
    if a.set_version:
        fid, vid = a.set_version
        try:
            e = rattache(reg, fid, vid)
        except (KeyError, ValueError) as err:
            sys.exit(f"ERREUR : {err}")
        if vid not in (None, "", "-") and not any(v.get("id") == vid for v in (reg.get("versions") or [])):
            ajoute_version(reg, vid)          # rattacher à une version inconnue la déclare : sinon elle serait invisible
            print(f"  · version {vid} déclarée au passage")
        reg_path.write_text(dump(reg), encoding="utf-8")
        print(f"✓ {fid} → " + (f"version {vid}" if vid not in (None, "", "-") else "sans version"))
        if not a.build:
            return
    if a.drop_version:
        n = retire_version(reg, a.drop_version)
        reg_path.write_text(dump(reg), encoding="utf-8")
        print(f"✓ version {a.drop_version} retirée ({n} entrée(s) détachée(s))")
        if not a.build:
            return
    if a.assign_version:
        n = 0
        for e in reg["entrees"]:
            if not e.get("version") and e.get("jalon") is None and (not a.etat or e.get("etat") == a.etat):
                e["version"] = a.assign_version; n += 1
        reg_path.write_text(dump(reg), encoding="utf-8"); print(f"✓ version {a.assign_version} posée sur {n} entrée(s)" + (f" ({a.etat})" if a.etat else ""))
        if not a.build:
            return
    if a.init or a.sync:
        ajout, modif = ([], []) if (a.init and a.no_sync) else sync(reg, lire_tickets(tasks))
        reg_path.parent.mkdir(parents=True, exist_ok=True); reg_path.write_text(dump(reg), encoding="utf-8")
        print(f"✓ registre {reg_path.relative_to(docs)} : +{len(ajout)} ajoutée(s), {len(modif)} mise(s) à jour, {len(reg['entrees'])} au total")
    if a.build:
        chap.write_text(compose(reg, chap), encoding="utf-8")
        print(f"✓ chapitre {chap.name} régénéré ({len(reg['entrees'])} lignes)")
        road.write_text(build_roadmap(reg), encoding="utf-8")
        print(f"✓ feuille de route {road.name} régénérée ({len(versions_de(reg))} version(s))")
    if not (a.init or a.sync or a.build or a.absorb or a.add_version or a.set_version or a.drop_version):
        ap.print_help()


if __name__ == "__main__":
    main()
