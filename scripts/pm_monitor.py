#!/usr/bin/env python3
"""pm_monitor — les OBSERVATEURS du parc, en lecture (RM3112).

Un observateur est un **fournisseur de l'axe `monitoring`** : une instance, une URL, un jeton posé en
écriture seule comme les autres. Il ne décide de rien, il rapporte — ce qu'on fait de ses alertes, ouvrir
un ticket chez le bon client, est le travail du PM.

**Zabbix n'est pas le seul, et le code ne le suppose pas.** Comme `pm_forge` pour les forges, ce module
définit une interface et un backend par outil. Chacun répond à deux questions, et c'est tout ce que le
cockpit demande :

    .problemes()   ce qui ne va pas maintenant : quoi, sur quel hôte, depuis quand, à quel point
    .hotes()       ce qui est supervisé — la matière de l'association hôte → client/projet

Backends : `zabbix` (livré), `uptime-kuma` (déclaré, non branché — il observe des URL plutôt que des
hôtes, donc il sert le jour où on veut associer un SITE à un projet). En ajouter un, c'est une classe
ici et une entrée au catalogue des types, jamais du code d'interface.

**Lecture seule.** Aucune écriture n'est exposée : acquitter une alerte touche l'outil de toute l'équipe,
ça se décide, ça ne se glisse pas dans un lot.

Le jeton n'est jamais rendu, jamais journalisé, jamais mis dans une URL — il part en en-tête
(garde-fou 11).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

TIMEOUT = 20
#: Zabbix numérote ses sévérités de 0 à 5 ; on les nomme, parce qu'un « 4 » ne dit rien à personne.
SEVERITES = {0: "non classé", 1: "information", 2: "avertissement", 3: "moyen", 4: "élevé", 5: "désastre"}
#: à partir d'où on considère qu'il y a « gros souci » — le seuil par défaut du bouton « créer un ticket »
GROS_SOUCI = 4


class MonitorError(RuntimeError):
    """L'observateur n'a pas répondu, ou a répondu autre chose qu'un résultat."""


ZabbixError = MonitorError          # nom historique, gardé le temps que rien ne l'attende plus


def _registre_instance():
    """(nom, url, type) de l'instance de l'axe `monitoring` déclarée au registre, ou (None, None, None)."""
    try:
        import yaml
        from pm_registry import Registry
        from pm_paths import PMConfig
        cfg = PMConfig.load()
        prov = (yaml.safe_load((Path(cfg.pm_dir) / "pm.config.yml").read_text(encoding="utf-8")) or {}).get("providers") or {}
        locale = Path(cfg.pm_dir) / "pm.config.local.yml"
        if locale.is_file():
            sur = (yaml.safe_load(locale.read_text(encoding="utf-8")) or {}).get("providers") or {}
            serveurs = dict(prov.get("servers") or {}); serveurs.update(sur.get("servers") or {})
            defauts = dict(prov.get("defaults") or {}); defauts.update(sur.get("defaults") or {})
            prov = {**prov, "servers": serveurs, "defaults": defauts}
        reg = Registry.from_config(prov)
        nom = (reg.defaults or {}).get("monitoring")
        inst = reg.get(nom) if nom else next(iter(reg.by_axis("monitoring")), None)
        return (inst.name, inst.url, inst.type) if inst else (None, None, None)
    except Exception:
        return None, None, None


def _jeton(instance: str | None) -> str:
    """Le jeton de l'instance, lu du `.env` — jamais reçu en argument, jamais rendu ailleurs qu'ici."""
    if instance:
        try:
            import pm_secrets
            creds = pm_secrets.creds_for(instance, legacy=False,
                                         prefixes=getattr(pm_secrets, "CREDS_PREFIXES", None))
            for suffixe in ("API_TOKEN", "TOKEN", "API_KEY"):
                if creds.get(suffixe):
                    return str(creds[suffixe])
        except Exception:
            pass
    return os.environ.get("ZABBIX_API_TOKEN", "")      # repli : le jeton historique du .env PM


def resout() -> tuple:
    """(url, jeton, nom d'instance, type). Lève si aucun observateur n'est joignable."""
    nom, url, typ = _registre_instance()
    typ = (typ or os.environ.get("PM_MONITOR_TYPE") or "zabbix").lower()
    url = os.environ.get("ZABBIX_URL") or url or "https://zabbix.iprospective.fr"
    jeton = _jeton(nom)
    if not jeton:
        raise MonitorError("aucun jeton d'observateur : déclare l'instance de l'axe « Observateurs » et "
                           "pose sa clé (Réglages → Fournisseurs), ou définis ZABBIX_API_TOKEN")
    return url.rstrip("/"), jeton, nom or typ, typ


def _duree(depuis: int) -> str:
    """« depuis 3 j », « depuis 2 h » — une alerte vieille de trois semaines ne se lit pas en secondes."""
    s = max(0, int(time.time()) - int(depuis or 0))
    for seuil, unite, nom in ((86400, 86400, "j"), (3600, 3600, "h"), (60, 60, "min")):
        if s >= seuil:
            return f"{s // unite} {nom}"
    return f"{s} s"


# ── Les backends. Un observateur répond à trois questions, pas une de plus. ─────

class Observateur:
    """L'interface. Ajouter un outil = une classe ici + une entrée au catalogue des types."""

    def __init__(self, url: str, jeton: str, nom: str = ""):
        self.url, self.jeton, self.nom = url.rstrip("/"), jeton, nom

    def version(self) -> str:
        raise NotImplementedError

    def problemes(self, limit: int = 200, severite_min: int = 0) -> list:
        """[{eventid, name, severity, severity_label, since, host, grave…}] — le plus récent d'abord."""
        raise NotImplementedError

    def hotes(self) -> list:
        """[{host, name, actif}] — ce qui est supervisé."""
        raise NotImplementedError


class Zabbix(Observateur):
    """JSON-RPC, jeton en en-tête. Sévérités 0-5, nommées parce qu'un « 4 » ne dit rien à personne."""

    #: Zabbix REFUSE l'en-tête d'autorisation sur ces méthodes-là (« must be called without
    #: authorization header ») : elles sont publiques, et l'en-tête est une erreur, pas un surplus.
    SANS_AUTH = {"apiinfo.version"}

    def _rpc(self, methode: str, params: dict):
        corps = json.dumps({"jsonrpc": "2.0", "method": methode, "params": params, "id": 1}).encode("utf-8")
        entetes = {"Content-Type": "application/json-rpc"}
        if methode not in self.SANS_AUTH:
            entetes["Authorization"] = f"Bearer {self.jeton}"
        req = urllib.request.Request(self.url + "/api_jsonrpc.php", data=corps, headers=entetes)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                d = json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raise MonitorError(f"{methode} : HTTP {e.code}") from None
        except Exception as e:
            raise MonitorError(f"{methode} : {type(e).__name__}") from None
        if isinstance(d, dict) and d.get("error"):
            err = d["error"]
            raise MonitorError(f"{methode} : {err.get('message', '')} {err.get('data', '')}".strip())
        return d.get("result") if isinstance(d, dict) else d

    def version(self) -> str:
        return str(self._rpc("apiinfo.version", {}) or "")

    def problemes(self, limit: int = 200, severite_min: int = 0) -> list:
        bruts = self._rpc("problem.get", {"output": "extend", "recent": False, "sortfield": ["eventid"],
                                          "sortorder": "DESC",
                                          "limit": max(1, min(int(limit or 200), 1000))}) or []
        # Zabbix rend l'alerte et son déclencheur séparément : on recolle, parce qu'une alerte sans son
        # hôte n'aide à rien — c'est l'hôte qui dit quel client est concerné.
        ids = [p["objectid"] for p in bruts if p.get("objectid")]
        hotes = {}
        if ids:
            for tr in self._rpc("trigger.get", {"triggerids": ids, "selectHosts": ["host", "name"],
                                                "output": ["triggerid"]}) or []:
                h = (tr.get("hosts") or [{}])[0]
                hotes[tr.get("triggerid")] = (h.get("host", ""), h.get("name", ""))
        out = []
        for p in bruts:
            sev = int(p.get("severity") or 0)
            if sev < int(severite_min or 0):
                continue
            host, host_name = hotes.get(p.get("objectid"), ("", ""))
            out.append({"eventid": p.get("eventid"), "name": p.get("name", ""), "severity": sev,
                        "severity_label": SEVERITES.get(sev, str(sev)), "clock": int(p.get("clock") or 0),
                        "since": _duree(p.get("clock")), "acknowledged": p.get("acknowledged") == "1",
                        "host": host, "host_name": host_name, "grave": sev >= GROS_SOUCI,
                        "source": self.nom})
        return out

    def hotes(self) -> list:
        bruts = self._rpc("host.get", {"output": ["host", "name", "status"], "limit": 2000}) or []
        return sorted(({"host": h.get("host", ""), "name": h.get("name", ""),
                        "actif": h.get("status") == "0"} for h in bruts), key=lambda x: x["host"])


class UptimeKuma(Observateur):
    """Déclaré, pas branché (RM3112).

    Il observe des **URL**, pas des hôtes : c'est précisément ce qu'il faudra le jour où l'on voudra
    associer un *site* à un projet, là où Zabbix associe une *machine*. Son API est une socket
    temps réel, pas du JSON-RPC — d'où une classe à part plutôt qu'un paramètre de plus.
    """

    def version(self) -> str:
        raise MonitorError("uptime-kuma : backend déclaré, pas encore branché (RM3112)")

    problemes = version
    hotes = version


BACKENDS = {"zabbix": Zabbix, "uptime-kuma": UptimeKuma}


def observateur() -> Observateur:
    """L'observateur déclaré au registre, prêt à répondre. Lève si rien n'est joignable."""
    url, jeton, nom, typ = resout()
    cls = BACKENDS.get(typ)
    if not cls:
        raise MonitorError(f"type d'observateur inconnu : {typ} (connus : {', '.join(sorted(BACKENDS))})")
    return cls(url, jeton, nom)


# ── Façade : ce que le reste du code appelle, sans savoir quel outil répond ────

def problemes(limit: int = 200, severite_min: int = 0) -> list:
    return observateur().problemes(limit=limit, severite_min=severite_min)


def hotes() -> list:
    return observateur().hotes()


def version() -> str:
    return observateur().version()


# ── Associer un hôte à un client/projet (RM3112) ────────────────────────────────
#
# C'est ce qui permet au bouton « créer un ticket » de savoir OÙ créer le ticket. L'association se
# PROPOSE (les noms d'hôtes portent leur domaine) et se CORRIGE à la main — jamais l'inverse : une
# association devinée en silence enverrait un ticket chez le mauvais client, ce qui est pire que pas
# de proposition du tout. D'où une proposition qui dit toujours sa SOURCE et sa CONFIANCE, comme le
# routage des emails (RM2669).

CONFIRME = "confirmée"          # posée à la main : fait autorité, aucune règle ne la réécrit
PAR_SLUG = "slug du client"
PAR_DOMAINE = "domaine cité dans les fiches du client"


def _local_path():
    from pm_paths import PMConfig
    return Path(PMConfig.load().pm_dir) / "pm.config.local.yml"


def associations() -> dict:
    """Les associations CONFIRMÉES : {hôte: {client, project}}. Elles ne se devinent pas, on les a posées."""
    try:
        import yaml
        p = _local_path()
        if not p.is_file():
            return {}
        d = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("monitoring") or {}
        return {str(k): v for k, v in (d.get("hosts") or {}).items() if isinstance(v, dict)}
    except Exception:
        return {}


def associe(hote: str, client: str | None, projet: str | None) -> bool:
    """Pose ou retire l'association d'un hôte. `client=None` retire. Écrit dans la surcharge locale,
    jamais dans le `pm.config.yml` commenté de référence."""
    try:
        import yaml
        p = _local_path()
        d = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.is_file() else {}
        mon = d.setdefault("monitoring", {})
        hosts = mon.setdefault("hosts", {})
        if client:
            hosts[str(hote)] = {"client": str(client), "project": str(projet or "")}
        else:
            hosts.pop(str(hote), None)
        p.write_text("# Surcharge locale (RM3068, RM3112) — fusionnée par-dessus pm.config.yml.\n"
                     + yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return True
    except Exception:
        return False


def _clients_connus() -> dict:
    """{slug: [domaines cités dans ses fiches]} — la matière des propositions."""
    import re
    from pm_paths import PMConfig
    base = Path(PMConfig.load().projects_root) / "clients"
    out = {}
    if not base.is_dir():
        return out
    for d in base.iterdir():
        if not d.is_dir():
            continue
        textes = []
        # les fiches du client et de ses projets — pas les tickets, qui citent le monde entier
        for f in (list((d / "client").glob("*.md")) + list(d.glob("projects/*/meta.yml"))
                  + list(d.glob("projects/*/project/*.md")))[:120]:
            try:
                textes.append(f.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
        doms = set()
        # `\b` couperait « materiaux-naturels.fr » en « naturels.fr » : le tiret n'est pas un caractère
        # de mot. D'où la garde explicite à gauche, qui garde le label entier.
        motif = r"(?<![\w.-])([a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*\.(?:com|fr|net|org|io|dev))"
        for txt in textes:
            doms |= {m.lower() for m in re.findall(motif, txt)}
        # les domaines des outils ne disent rien du client : les écarter évite des propositions absurdes
        doms -= {"github.com", "gitlab.com", "google.com", "example.com", "iprospective.fr", "iprospective.net"}
        out[d.name] = sorted(doms)
    return out


def _projets_de(client: str) -> list:
    from pm_paths import PMConfig
    d = Path(PMConfig.load().projects_root) / "clients" / client / "projects"
    return sorted(x.name for x in d.iterdir() if x.is_dir()) if d.is_dir() else []


def _racine(nom: str) -> str:
    """Le domaine enregistrable : les deux derniers labels (« a.b.materiaux-naturels.fr » → celui-ci).
    Approximation assumée : elle suffit pour un parc, et une association douteuse se corrige à la main."""
    parts = [x for x in str(nom or "").lower().split(".") if x]
    return ".".join(parts[-2:]) if len(parts) >= 2 else ""


def proposition(hote: str, connus=None) -> dict:
    """{client, project, source, confiance} — ce qu'on PROPOSE pour un hôte, et pourquoi.

    `confiance` : 1.0 confirmée à la main · 0.8 le slug du client est dans le nom d'hôte · 0.6 un domaine
    de ses fiches y est · 0.0 rien de sûr, et on le dit plutôt que de choisir au hasard."""
    h = str(hote or "").lower()
    fixe = associations().get(hote)
    if fixe:
        return {"client": fixe.get("client", ""), "project": fixe.get("project", ""),
                "source": CONFIRME, "confiance": 1.0}
    connus = _clients_connus() if connus is None else connus
    for slug in sorted(connus, key=len, reverse=True):
        if slug and (h.startswith(slug + ".") or f".{slug}." in h or h.endswith("." + slug)):
            pr = _projets_de(slug)
            return {"client": slug, "project": pr[0] if len(pr) == 1 else "",
                    "source": PAR_SLUG, "confiance": 0.8}
    # On compare sur le domaine ENREGISTRABLE (les deux derniers labels) : « prd.materiaux-naturels.fr »
    # et « gogs.materiaux-naturels.fr » désignent le même client, alors qu'aucun n'est un suffixe de l'autre.
    racine = _racine(h)
    for slug, doms in connus.items():
        for dom in doms:
            if dom and racine and _racine(dom) == racine:
                pr = _projets_de(slug)
                return {"client": slug, "project": pr[0] if len(pr) == 1 else "",
                        "source": f"{PAR_DOMAINE} ({dom})", "confiance": 0.6}
    return {"client": "", "project": "", "source": "", "confiance": 0.0}


def alertes_situees(limit: int = 200, severite_min: int = 0) -> list:
    """Les alertes, chacune avec le client/projet proposé pour son hôte. C'est ce que lit le cockpit."""
    connus = _clients_connus()
    cache = {}
    out = []
    for a in problemes(limit=limit, severite_min=severite_min):
        h = a.get("host") or ""
        if h not in cache:
            cache[h] = proposition(h, connus) if h else {"client": "", "project": "", "source": "", "confiance": 0.0}
        out.append({**a, **{"cible": cache[h]}})
    return out
