"""pm_mail_routing — de l'expéditeur d'un email au couple client/projet (RM2669).

Lot T2 du chantier RM2666 (CDC `docs/cdc-rm2666-emails-vers-tickets.md`). Répond à
UNE question : « ce mail concerne quel client, quel projet ? » — avec un **indice de
confiance** et la **source** de la réponse, jamais un choix silencieux.

Cascade, du plus sûr au plus incertain (première source qui répond gagne) :

  1. `ticket`   — le sujet porte `[RM<id>]` : le projet du ticket fait foi (1.0).
  2. `mapping`  — table apprise `mail-routing.yml` : adresse exacte (1.0) ou
                  domaine (0.9). C'est elle que nourrit chaque correction humaine.
  3. `redmine`  — l'expéditeur a un compte Redmine : ses projets d'appartenance
                  (0.9 si un seul, 0.6 si plusieurs → projet laissé ouvert).
  4. `contacts` — `contacts[]` du client, **hors adresses maison** : le gabarit de
                  création y met l'adresse du propriétaire, identique chez les 20
                  clients — s'en servir router**ait** tout mail de Mathieu vers un
                  client au hasard. Ces adresses sont donc exclues.
  5. `indice`   — le slug ou le nom du client apparaît dans le domaine, la partie
                  locale ou le nom affiché (0.6) — et **seulement** si un seul
                  client correspond.
  6. rien       — `unresolved` : le mail reste « à classer ». On ne devine pas.

Le **projet** n'est retenu que s'il est certain : client à projet unique, ou projet
désigné explicitement (ticket, mapping, appartenance Redmine unique). Sinon le
client est proposé et le projet laissé à `None` — au demandeur (ou à RM2670) de
trancher. Cf. tripwire NORMS 14 : jamais de résolution par slug nu ni de choix
silencieux entre plusieurs projets.

La table `mail-routing.yml` ne contient QUE des adresses et des couples
client/projet — jamais de contenu d'email. Elle est donc commitable, contrairement
à la file de triage (cf. RM2668).
"""
import os
import re
from pathlib import Path

import yaml

# Adresses/domaines « maison » : ce sont les nôtres, ils n'identifient aucun client.
OWN_DOMAINS_DEFAULT = ["iprospective.fr", "iprospective.net"]

# Domaines de messagerie GRAND PUBLIC : apprendre l'un d'eux comme domaine d'un
# client router**ait** vers ce client tout mail venant de ce fournisseur. Un vrai
# cas : le contact CalyClay écrit depuis gmail.com. On refuse — l'adresse exacte,
# elle, reste apprenable.
PUBLIC_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "outlook.fr", "hotmail.com",
    "hotmail.fr", "live.fr", "live.com", "msn.com", "yahoo.com", "yahoo.fr",
    "free.fr", "orange.fr", "wanadoo.fr", "sfr.fr", "laposte.net", "gmx.fr",
    "gmx.com", "icloud.com", "me.com", "protonmail.com", "proton.me", "aol.com",
}

CONF = {
    "ticket": 1.0,       # le fil dit lui-même de quel ticket il s'agit
    "mapping_addr": 1.0,  # correction humaine sur cette adresse précise
    "mapping_domain": 0.9,
    "redmine_one": 0.9,
    "redmine_many": 0.6,
    "contacts": 0.8,
    "hint": 0.6,
}

_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def own_addresses(cfg=None) -> set:
    """Adresses à ne jamais prendre pour un indice de client (les nôtres).

    Les domaines maison (§ `own_domains`) couvrent déjà le cas courant ; cette
    liste sert aux adresses hors domaine (gmail perso d'un intervenant, alias).
    """
    return {a.strip().lower()
            for a in (os.environ.get("KARL_MAIL_OWN_ADDRESSES") or "").split(",")
            if a.strip()}


def own_domains() -> list:
    raw = os.environ.get("KARL_MAIL_OWN_DOMAINS")
    if raw:
        return [d.strip().lower() for d in raw.split(",") if d.strip()]
    return list(OWN_DOMAINS_DEFAULT)


def is_own(addr: str, cfg=None) -> bool:
    addr = (addr or "").lower()
    if not addr:
        return True
    if addr in own_addresses(cfg):
        return True
    return addr.rsplit("@", 1)[-1] in own_domains()


# ── Table apprise ────────────────────────────────────────────────────────────
def routing_file(cfg) -> Path:
    """Emplacement de la table : `conf_dir` (versionné avec le code)."""
    try:
        return cfg.path("mail_routing_file")
    except KeyError:                     # core pas encore migré : même racine
        return cfg.conf_dir / "mail-routing.yml"


def load_routing(cfg) -> dict:
    f = routing_file(cfg)
    if not f.is_file():
        return {"addresses": {}, "domains": {}}
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {"addresses": {}, "domains": {}}
    data.setdefault("addresses", {})
    data.setdefault("domains", {})
    return data


def save_routing(cfg, data: dict):
    f = routing_file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    header = ("# Routage des emails entrants → client/projet (RM2669).\n"
              "# Alimenté par les corrections humaines ; aucun contenu d'email ici.\n"
              "# Forme : addresses/<email> ou domains/<domaine> → 'client' ou 'client/projet'.\n")
    tmp = f.with_suffix(".yml.tmp")
    tmp.write_text(header + yaml.safe_dump(data, allow_unicode=True, sort_keys=True),
                   encoding="utf-8")
    tmp.replace(f)


def parse_target(value) -> tuple:
    """'client' ou 'client/projet' → (client, projet|None)."""
    if not value:
        return (None, None)
    parts = str(value).split("/", 1)
    return (parts[0].strip() or None, parts[1].strip() if len(parts) > 1 else None)


def learn(cfg, addr: str, target: str, domain: bool = False) -> dict:
    """Enregistre une correction humaine. Retourne la table mise à jour."""
    client, project = parse_target(target)
    if not client:
        raise ValueError("cible attendue : 'client' ou 'client/projet'")
    data = load_routing(cfg)
    key = (addr or "").lower().strip()
    if domain:
        key = key.rsplit("@", 1)[-1]
        if key in PUBLIC_DOMAINS:
            raise ValueError(
                f"{key} est un fournisseur de messagerie grand public : l'apprendre "
                f"comme domaine de « {client} » y router{'ait'} tout le courrier venant "
                f"de {key}. Apprends l'adresse exacte (sans --domain).")
        if key in own_domains():
            raise ValueError(f"{key} est un domaine maison : il n'identifie aucun client")
        data["domains"][key] = target
    else:
        data["addresses"][key] = target
    save_routing(cfg, data)
    return data


# ── Sources ──────────────────────────────────────────────────────────────────
def _project_of_ticket(cfg, rm_id):
    """(client, projet) du ticket, via l'emplacement de son fichier MD."""
    md = cfg.find_task(int(rm_id))
    if not md:
        return (None, None)
    # …/clients/<client>/projects/<projet>/tasks/RM<id>_….md
    try:
        return (md.parents[3].name, md.parents[1].name)
    except IndexError:
        return (None, None)


def _single_project(cfg, client):
    """Projet du client s'il n'en a qu'UN — sinon None (pas de choix silencieux)."""
    projects = [p for e, p, _ in cfg.iter_projects(entity=client)]
    return projects[0] if len(projects) == 1 else None


def _known_clients(cfg) -> list:
    """[(slug, nom, [jetons de reconnaissance])] pour l'heuristique."""
    out = []
    for slug, _ in cfg.iter_entities():
        meta = cfg.client_meta(slug) or {}
        name = str(meta.get("name") or slug)
        tokens = {slug.lower()}
        tokens.add(slug.replace("-", "").lower())
        tokens.add(name.replace(" ", "").replace("-", "").lower())
        out.append((slug, name, {t for t in tokens if len(t) >= 4}))
    return out


def _hint_clients(cfg, addr: str, display_name: str) -> list:
    """Clients dont le slug/nom apparaît dans l'adresse ou le nom affiché."""
    hay = _SPLIT_RE.sub("", f"{addr} {display_name}".lower())
    hits = []
    for slug, name, tokens in _known_clients(cfg):
        if any(t and t in hay for t in tokens):
            hits.append(slug)
    return hits


def _contacts_clients(cfg, addr: str) -> list:
    """Clients dont `contacts[]` porte cette adresse (adresses maison exclues)."""
    if is_own(addr, cfg):
        return []
    hits = []
    for slug, _ in cfg.iter_entities():
        meta = cfg.client_meta(slug) or {}
        for c in meta.get("contacts") or []:
            if isinstance(c, dict) and (c.get("email") or "").lower() == addr:
                hits.append(slug)
                break
    return hits


def _result(source, client, project, confidence, reason, candidates=None):
    return {"client": client, "project": project, "source": source,
            "confidence": round(confidence, 2) if client else 0.0,
            "reason": reason, "candidates": candidates or []}


def route(entry: dict, cfg, redmine_lookup=None) -> dict:
    """Route UNE entrée de file. `redmine_lookup(addr) -> [(client, projet), …]`
    est injecté (None = source Redmine désactivée, mode hors-ligne)."""
    addr = (entry.get("from") or "").lower().strip()
    display = entry.get("from_name") or ""

    # 1. le fil désigne son ticket
    if entry.get("rm_id"):
        client, project = _project_of_ticket(cfg, entry["rm_id"])
        if client:
            return _result("ticket", client, project, CONF["ticket"],
                           f"sujet [RM{entry['rm_id']}] → projet du ticket")

    # 2. table apprise : adresse exacte, puis domaine
    table = load_routing(cfg)
    if addr in (table.get("addresses") or {}):
        client, project = parse_target(table["addresses"][addr])
        return _result("mapping", client, project or _single_project(cfg, client),
                       CONF["mapping_addr"], "adresse connue de mail-routing.yml")
    domain = addr.rsplit("@", 1)[-1] if "@" in addr else ""
    if domain and domain in (table.get("domains") or {}):
        client, project = parse_target(table["domains"][domain])
        return _result("mapping", client, project or _single_project(cfg, client),
                       CONF["mapping_domain"], f"domaine {domain} connu de mail-routing.yml")

    # 3. compte Redmine de l'expéditeur → ses projets
    if redmine_lookup and addr and not is_own(addr, cfg):
        pairs = redmine_lookup(addr) or []
        clients = sorted({c for c, _ in pairs if c})
        if len(clients) == 1:
            projects = sorted({p for c, p in pairs if p})
            if len(projects) == 1:
                return _result("redmine", clients[0], projects[0], CONF["redmine_one"],
                               "compte Redmine de l'expéditeur, projet unique")
            return _result("redmine", clients[0], _single_project(cfg, clients[0]),
                           CONF["redmine_many"],
                           f"compte Redmine, {len(projects)} projets — projet à confirmer",
                           candidates=[f"{clients[0]}/{p}" for p in projects])
        if len(clients) > 1:
            return _result("redmine", None, None, 0.0,
                           "compte Redmine rattaché à plusieurs clients — à trancher",
                           candidates=clients)

    # 4. contacts[] du client (hors adresses maison)
    hits = _contacts_clients(cfg, addr)
    if len(hits) == 1:
        return _result("contacts", hits[0], _single_project(cfg, hits[0]),
                       CONF["contacts"], "adresse trouvée dans contacts[] du client")
    if len(hits) > 1:
        return _result("contacts", None, None, 0.0,
                       "adresse présente chez plusieurs clients — à trancher",
                       candidates=hits)

    # 5. indice textuel (slug/nom du client dans l'adresse ou le nom affiché)
    hits = _hint_clients(cfg, addr, display)
    if len(hits) == 1:
        return _result("indice", hits[0], _single_project(cfg, hits[0]), CONF["hint"],
                       f"« {hits[0]} » reconnu dans l'expéditeur — à confirmer")
    if len(hits) > 1:
        return _result("indice", None, None, 0.0,
                       "plusieurs clients reconnus dans l'expéditeur — à trancher",
                       candidates=hits)

    # 6. rien de fiable : on ne devine pas
    return _result("unresolved", None, None, 0.0,
                   "expéditeur inconnu — à classer à la main (la correction sera apprise)")
