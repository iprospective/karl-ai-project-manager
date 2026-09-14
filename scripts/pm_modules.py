#!/usr/bin/env python3
"""pm_modules — le registre des MODULES de PM (RM3145, lot 0).

PM n'a jamais été monolithique par choix : il porte déjà **sept** mécanismes d'extension, chacun
réinventé dans son coin — le catalogue des fournisseurs, les recettes de moteurs, les backends de
coffres, ceux d'observateurs, les services LLM, les travaux périodiques, les veilles de publication.
Trois sont déclaratifs, quatre sont des tables Python qu'il faut éditer : ajouter un backend y demande
donc de **livrer une version du noyau**.

Ce module est le socle qui les unifie. Il ne déplace rien, et c'est délibéré : le lot 0 **décrit** ce
qui existe pour que le reste se discute sur pièces, plutôt que de déménager d'abord et de constater
ensuite. D'où deux vues, et la distinction entre elles est la seule chose que ce fichier apporte :

  * les modules **décrits** — un dossier sous `modules/`, un `module.yml` qui dit ce qu'il fournit ;
  * les points d'extension **non décrits** — ce que les sept registres contiennent aujourd'hui et que
    personne n'a encore déclaré. Les taire donnerait un inventaire flatteur et faux.

Un manifeste (`modules/<nom>/module.yml`) :

    name: monitoring-zabbix
    version: 1.0.0
    label: "Supervision Zabbix"
    description: "Alertes d'un parc Zabbix, situées chez un client, ticketables."
    requires: ["core >= 3.0"]        # bornes de version, jamais un simple nom nu
    provides:
      - {kind: provider, axis: monitoring, type: zabbix}
      - {kind: job, name: zabbix-poll}
      - {kind: panel, name: monitor}
    enabled: true

Ce que ce module NE fait pas encore (lots suivants) : charger du code, monter des routes, poser des
abonnements. Il lit, valide, ordonne — et dit non avec un motif.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:                     # pragma: no cover — PyYAML est une dépendance du PM
    yaml = None

MANIFESTE = "module.yml"
DOSSIER = "modules"
#: la version du NOYAU, à laquelle un module se compare. Elle bougera avec le contrat, pas avec PM.
CORE_VERSION = "3.0.0"
#: les natures de ce qu'un module peut fournir. Une nature inconnue est refusée : mieux vaut un
#: manifeste rejeté qu'un module qui croit fournir quelque chose que personne ne lira.
KINDS = ("provider", "job", "panel", "route", "hook", "trigger", "skill", "watch", "engine")
_NOM = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_BORNE = re.compile(r"^\s*([a-z0-9][a-z0-9-]*)\s*(==|>=|<=|>|<)?\s*([0-9][0-9.]*)?\s*$")


class ModuleError(Exception):
    """Manifeste invalide, dépendance absente ou incompatible, cycle."""


def version_tuple(v) -> tuple:
    """« 1.10.0 » > « 1.9.0 » — comparer des chaînes dirait le contraire."""
    return tuple(int(n) for n in re.findall(r"\d+", str(v or ""))[:4]) or (0,)


def satisfait(version, operateur, borne) -> bool:
    a, b = version_tuple(version), version_tuple(borne)
    if operateur in (None, ""):
        return True                      # pas de borne = n'importe quelle version
    return {"==": a == b, ">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b}[operateur]


class Module:
    """Un module décrit. Inerte : il ne charge rien, il se lit et se contrôle."""

    def __init__(self, chemin: Path, data: dict):
        self.path = chemin
        self.raw = data or {}
        self.name = str(self.raw.get("name") or chemin.parent.name).strip()
        self.version = str(self.raw.get("version") or "0.0.0").strip()
        self.label = str(self.raw.get("label") or self.name)
        self.description = " ".join(str(self.raw.get("description") or "").split())
        self.requires = [str(x) for x in (self.raw.get("requires") or [])]
        self.provides = list(self.raw.get("provides") or [])
        # Absent = activé : un module qu'on pose est un module qu'on veut. Le désactiver est un geste.
        self.enabled = bool(self.raw.get("enabled", True))
        self.errors = []
        self._valide()

    def _valide(self):
        if not _NOM.match(self.name):
            self.errors.append(f"nom invalide « {self.name} » (minuscules, chiffres et tirets)")
        elif self.name != self.path.parent.name:
            # Deux identités pour un module — celle du disque et celle du manifeste — et on ne sait
            # plus laquelle une dépendance désigne. Le dossier fait foi, le manifeste doit s'y tenir.
            self.errors.append(
                f"le nom déclaré « {self.name} » diffère du dossier « {self.path.parent.name} »")
        if not re.match(r"^\d+\.\d+\.\d+$", self.version):
            self.errors.append(f"version « {self.version} » : attendu X.Y.Z")
        if not self.description:
            # Un module sans description est un module que personne ne saura activer en connaissance
            # de cause : c'est le premier service que rend un manifeste.
            self.errors.append("description manquante")
        for dep in self.requires:
            if not _BORNE.match(dep):
                self.errors.append(f"dépendance illisible « {dep} » (ex. « core >= 3.0 »)")
        for p in self.provides:
            if not isinstance(p, dict) or p.get("kind") not in KINDS:
                self.errors.append(f"« provides » inconnu : {p!r} (natures : {', '.join(KINDS)})")

    @property
    def ok(self) -> bool:
        return not self.errors

    def deps(self) -> list:
        """[(nom, opérateur, borne)] — la forme lue, pas la chaîne."""
        out = []
        for dep in self.requires:
            m = _BORNE.match(dep)
            if m:
                out.append((m.group(1), m.group(2), m.group(3)))
        return out

    def fournit(self) -> list:
        """[(nature, désignation)] — de quoi comparer avec ce que les registres contiennent."""
        out = []
        for p in self.provides:
            if not isinstance(p, dict):
                continue
            k = p.get("kind")
            nom = p.get("type") or p.get("name") or ""
            if k == "provider" and p.get("axis"):
                nom = f"{p['axis']}/{nom}"
            out.append((k, str(nom)))
        return out

    def as_dict(self) -> dict:
        return {"name": self.name, "version": self.version, "label": self.label,
                "description": self.description, "requires": self.requires,
                "provides": self.fournit(), "enabled": self.enabled,
                "ok": self.ok, "errors": list(self.errors),
                "path": str(self.path.parent)}


def racine(root=None) -> Path:
    """Où vivent les modules. `PM_MODULES_DIR` prime — un test ne doit jamais lire ceux de la vraie
    instance, et une instance relocalisée (RM2580) ne range pas forcément son code au même endroit."""
    v = os.environ.get("PM_MODULES_DIR")
    if v:
        return Path(os.path.expanduser(v))
    base = Path(root) if root else Path(__file__).resolve().parent.parent
    return base / DOSSIER


def decouvre(root=None) -> list:
    """Les modules décrits, triés par nom. Un dossier sans manifeste est ignoré en silence (on y met
    des choses), un manifeste illisible devient un module EN ERREUR — jamais un module absent : une
    erreur qu'on ne voit pas est pire qu'un module qui manque."""
    d = racine(root)
    if not d.is_dir():
        return []
    out = []
    for sous in sorted(p for p in d.iterdir() if p.is_dir()):
        f = sous / MANIFESTE
        if not f.is_file():
            continue
        if yaml is None:
            out.append(_casse(f, "PyYAML absent : manifeste illisible"))
            continue
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            out.append(_casse(f, f"YAML illisible — {e}"))
            continue
        if not isinstance(data, dict):
            out.append(_casse(f, "le manifeste doit être un mapping"))
            continue
        out.append(Module(f, data))
    return out


def _casse(f: Path, motif: str) -> Module:
    m = Module.__new__(Module)
    m.path, m.raw = f, {}
    m.name, m.version, m.label = f.parent.name, "0.0.0", f.parent.name
    m.description, m.requires, m.provides, m.enabled = "", [], [], False
    m.errors = [motif]
    return m


def resout(modules, core_version=CORE_VERSION) -> dict:
    """Ordonne les modules pour le chargement, et dit ce qui bloque.

    Rend {ordre, bloques, cycles}. Un module bloqué n'est pas une erreur fatale du système : les
    autres se chargent. Ce qui serait fatal, c'est de le charger QUAND MÊME, ou de le taire.
    """
    par_nom = {m.name: m for m in modules if m.ok}
    bloques, prets = {}, {}

    for m in par_nom.values():
        if not m.enabled:
            continue
        motifs = []
        for nom, op, borne in m.deps():
            if nom == "core":
                if not satisfait(core_version, op, borne):
                    motifs.append(f"noyau {core_version} ne satisfait pas « {nom} {op or ''} {borne or ''} »".replace("  ", " "))
                continue
            dep = par_nom.get(nom)
            if dep is None:
                motifs.append(f"dépendance absente : {nom}")
            elif not dep.enabled:
                motifs.append(f"dépendance désactivée : {nom}")
            elif not satisfait(dep.version, op, borne):
                motifs.append(f"{nom} {dep.version} ne satisfait pas « {op or ''} {borne or ''} »".strip())
        (bloques if motifs else prets)[m.name] = motifs or m

    # Tri topologique — l'ordre de chargement. Un cycle se NOMME : sans ça, on cherche longtemps.
    ordre, vus, cycles = [], {}, []

    def visite(nom, pile):
        if nom in vus:
            return
        if nom in pile:
            boucle = pile[pile.index(nom):] + [nom]
            if boucle not in cycles:
                cycles.append(boucle)
            return
        m = prets.get(nom)
        if m is None:
            return
        pile.append(nom)
        for dep, _, _ in m.deps():
            if dep != "core" and dep in prets:
                visite(dep, pile)
        pile.pop()
        if nom not in vus:
            vus[nom] = True
            ordre.append(nom)

    for nom in sorted(prets):
        visite(nom, [])
    if cycles:
        # Un module pris dans un cycle ne se charge pas : l'ordre n'existe pas, il n'y a pas de
        # « premier ». On le range dans les bloqués plutôt que de deviner.
        dans_cycle = {n for c in cycles for n in c}
        ordre = [n for n in ordre if n not in dans_cycle]
        for n in dans_cycle:
            bloques.setdefault(n, ["dépendance circulaire : " + " → ".join(next(c for c in cycles if n in c))])
    return {"ordre": ordre, "bloques": {k: v for k, v in bloques.items() if isinstance(v, list)},
            "cycles": cycles}


# ── les abonnements : ce à quoi un module RÉAGIT (RM3145, lot 2) ────────────────────────────────
#
# Ils se déclarent dans `modules/<nom>/triggers/*.yml`, pas dans le manifeste : un abonnement est du
# câblage, il change plus souvent que l'identité du module, et le lire à part évite de rouvrir le
# manifeste pour ajouter une réaction.
#
#     event: task.status.changed
#     when: {to: a_tester_demandeur}     # facultatif — sans lui, tout passe
#     run: ["python3", "modules/<nom>/services/prevenir.py"]
#
# ⚠ La clé est `event`, pas `on` : en YAML 1.1, `on` est un BOOLÉEN (comme `yes` et `off`), donc
# `on: task.status.changed` produit une clé `True` et l'abonnement écoute le vide. Le piège est
# silencieux, et il a coûté une heure à GitHub Actions avant nous. `on:` reste accepté — sous ses
# deux formes, la chaîne et le booléen — parce qu'il vient naturellement sous les doigts.

TRIGGERS = "triggers"


class Trigger:
    """Un abonnement : à quel événement, sous quelle condition, et ce qu'il lance."""

    def __init__(self, module: str, fichier: Path, data: dict):
        self.module = module
        self.file = fichier
        d = data or {}
        # `True` est la clé que YAML produit pour `on:` — voir l'avertissement en tête de section.
        self.on = str(d.get("event") or d.get("on") or d.get(True) or "").strip()
        self.when = dict(d.get("when") or {})
        run = d.get("run")
        self.run = [str(x) for x in run] if isinstance(run, list) else []
        self.errors = []
        if not self.on:
            self.errors.append("« event » manquant : un abonnement sans événement n'écoute rien")
        if not self.run:
            self.errors.append("« run » manquant, ou pas une liste d'arguments")
        # Une commande en CHAÎNE passerait par un shell : un abonné ne doit pas pouvoir faire
        # dépendre son exécution d'une interprétation de la ligne de commande.
        if isinstance(run, str):
            self.errors.append("« run » doit être une LISTE d'arguments, jamais une ligne de shell")

    @property
    def ok(self) -> bool:
        return not self.errors

    def concerne(self, evenement: dict) -> bool:
        """Vrai si cet abonnement doit se déclencher pour cet événement. Un filtre absent laisse
        tout passer ; un filtre présent doit être satisfait EN ENTIER."""
        if (evenement or {}).get("name") != self.on:
            return False
        charge = (evenement or {}).get("payload") or {}
        for cle, attendu in self.when.items():
            valeur = charge.get(cle)
            if isinstance(attendu, list):
                if valeur not in attendu:
                    return False
            elif str(valeur) != str(attendu):
                return False
        return True

    def as_dict(self) -> dict:
        return {"module": self.module, "on": self.on, "when": self.when, "run": self.run,
                "ok": self.ok, "errors": list(self.errors), "file": str(self.file)}


def triggers(root=None, modules=None) -> list:
    """Les abonnements des modules ACTIFS et résolus, dans l'ordre de chargement.

    Un module bloqué ou désactivé n'écoute pas : réagir sans être chargé serait le pire des deux
    mondes — actif à moitié, et impossible à diagnostiquer."""
    mods = decouvre(root) if modules is None else modules
    r = resout(mods)
    par_nom = {m.name: m for m in mods}
    out = []
    for nom in r["ordre"]:
        m = par_nom.get(nom)
        if m is None:
            continue
        d = m.path.parent / TRIGGERS
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.yml")):
            if yaml is None:
                continue
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as e:
                t = Trigger(nom, f, {})
                t.errors = [f"YAML illisible — {e}"]
                out.append(t)
                continue
            out.append(Trigger(nom, f, data if isinstance(data, dict) else {}))
    return out


# ── l'inventaire de l'EXISTANT — ce que les sept registres contiennent aujourd'hui ──────────────
#
# Un inventaire qui ne montrerait que les modules déclarés serait flatteur et faux : au lot 0, rien
# n'est déclaré. Ces sondes lisent les registres en place, sans rien importer de lourd ni rien
# exécuter, et chacune échoue en silence — l'inventaire ne doit jamais casser à cause d'un registre.

def _registres(root=None) -> dict:
    base = Path(root) if root else Path(__file__).resolve().parent.parent
    sc = base / "scripts"
    if str(sc) not in sys.path:
        sys.path.insert(0, str(sc))
    out = {}

    def sonde(cle, fn):
        try:
            v = fn()
            if v:
                out[cle] = sorted(v)
        except Exception:      # noqa: BLE001 — un registre absent ou cassé n'empêche pas l'inventaire
            pass

    def providers():
        import pm_provider_types as PT
        return [f"{v['axis']}/{k}" for k, v in PT.CATALOGUE.items()]

    def jobs():
        if yaml is None:
            return []
        data = yaml.safe_load((base / "jobs.reference.yml").read_text(encoding="utf-8")) or {}
        return list((data.get("jobs") or {}).keys())

    def veilles():
        if yaml is None:
            return []
        f = base / "releases.watch.yml"
        if not f.is_file():
            return []
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        return list((data.get("watches") or {}).keys())

    sonde("provider", providers)
    sonde("engine", lambda: list(__import__("pm_engine_recipes").RECETTES))
    sonde("job", jobs)
    sonde("watch", veilles)
    sonde("secret-backend", lambda: list(__import__("pm_secrets").BACKENDS))
    sonde("monitoring-backend", lambda: list(__import__("pm_monitor").BACKENDS))
    sonde("llm-service", lambda: list(__import__("pm_llm_services").SERVICES))
    return out


def inventaire(root=None, modules=None) -> dict:
    """Ce que les registres contiennent, et ce qui n'est décrit par aucun module.

    C'est la mesure de l'écart entre l'architecture visée et l'existant — et donc l'avancement réel
    du chantier, plutôt qu'une impression."""
    mods = decouvre(root) if modules is None else modules
    decrits = set()
    for m in mods:
        for kind, nom in m.fournit():
            decrits.add((kind, nom))
            if kind == "provider":
                decrits.add(("provider", nom.split("/")[-1]))
    regs = _registres(root)
    out, total, couverts = {}, 0, 0
    for cle, items in regs.items():
        kind = "provider" if cle == "provider" else cle
        lignes = []
        for it in items:
            vu = (kind, it) in decrits or (cle, it) in decrits
            lignes.append({"item": it, "decrit": vu})
            total += 1
            couverts += 1 if vu else 0
        out[cle] = lignes
    return {"registres": out, "total": total, "decrits": couverts,
            "non_decrits": total - couverts}
