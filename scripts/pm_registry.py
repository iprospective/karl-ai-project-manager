#!/usr/bin/env python3
"""pm_registry — registre de serveurs (instances) + résolution d'instance par projet.

Fondation P0 (RM2542) de la généralisation forge → 3 axes providers
(**task** / **forge** / **doc**) — cf. CDC RM2530 [[Cdc-rm2530-providers-par-projet]].

Trois entrées :
  * `Registry.from_config(providers_cfg)` — construit le registre depuis la section
    `providers:` de `pm.config.yml` (exposée par `PMConfig.providers`).
  * `resolve_instances(project_meta, axis, registry)` — **liste ordonnée** des providers
    d'un axe pour ce projet : le **primaire** en tête, puis les **secondaires**
    (RM2653/L0, CDC RM2626 § 5.1).
  * `resolve_instance(project_meta, axis, registry)` — le **primaire** seul (= premier
    élément) : signature et sémantique inchangées pour tous les appelants historiques.

Une `Resolution` = instance retenue + params projet (project_id, repo, …) + `role`
(`primary` | `secondary`) + `link`/`sync` (règles portées par un secondaire) + `source`
(traçabilité).

**Primaire vs secondaire** (CDC RM2626) : le primaire est la **source de vérité PM**
(états NORMS, reporting temps/tokens, cascade, tag IA) ; un secondaire est un
gestionnaire **partenaire** avec lequel on se synchronise, jamais une source de vérité —
d'où l'interdiction de porter `link:`/`sync:` sur le primaire.

**INERTE par défaut / zéro régression.** Les défauts du registre reproduisent
l'état actuel (Redmine global + GitLab) ; la rétro-compat lit les blocs historiques
`redmine:` / `gitlab:` d'un `meta.yml` qui n'a pas (encore) de bloc `providers:`.
Aucun script existant ne consomme ce module en P0 — le câblage est en P1+.

Priorité de résolution, par axe :
  1. `meta.providers.<axe>`  (config explicite par projet — **dict** (1 provider) ou
     **liste** (primaire + secondaires))
  2. bloc legacy du `meta.yml` (`redmine:` pour task, `gitlab:` pour forge)
  3. `providers.defaults.<axe>` du registre

Formes acceptées de `meta.providers.<axe>` (toutes rétro-compatibles) :

```yaml
providers:
  task: {instance: redmine-ipro, project_id: pm-ai-agents}    # dict → 1 primaire
  task:                                                        # liste → primaire + N
    - {instance: redmine-ipro, role: primary, project_id: pm-ai-agents}
    - instance: redmine-matnat
      role: secondary
      project_id: 12
      link: {policy: required}
      sync: {pull: {notes: true}, push: {on: [ferme]}}
```
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import _expand_env  # interpolation ${VAR} / ${VAR:-defaut}, comme roots

AXES = ("task", "forge", "doc")
ROLES = ("primary", "secondary")
# Clés d'une entrée de provider qui ne sont PAS des params projet.
_ENTRY_KEYS = ("instance", "role", "link", "sync")


class RegistryError(Exception):
    """Config de registre incohérente (instance/axe inconnus, défaut manquant)."""


@dataclass(frozen=True)
class Instance:
    """Une instance déclarée dans `providers.servers` (sans secret)."""
    name: str
    axis: str
    type: str
    url: str = ""
    options: dict = field(default_factory=dict)  # ssh_port, etc.


@dataclass(frozen=True)
class Resolution:
    """Instance retenue pour (projet, axe) + params projet + rôle + provenance."""
    instance: Instance
    params: dict = field(default_factory=dict)   # project_id, repo, group, default_branch…
    source: str = "default"                       # 'providers' | 'legacy' | 'default'
    role: str = "primary"                         # 'primary' | 'secondary' (RM2653)
    link: dict = field(default_factory=dict)      # règles de rattachement (secondaire)
    sync: dict = field(default_factory=dict)      # règles de synchro pull/push (secondaire)

    @property
    def is_primary(self) -> bool:
        return self.role == "primary"


class Registry:
    def __init__(self, servers: dict, defaults: dict):
        self._servers = servers      # name -> Instance
        self._defaults = defaults     # axis -> instance name

    # ── construction ──────────────────────────────────────────────────────
    @classmethod
    def from_config(cls, providers_cfg: dict) -> "Registry":
        cfg = providers_cfg or {}
        servers: dict = {}
        for name, spec in (cfg.get("servers") or {}).items():
            spec = spec or {}
            axis = spec.get("axis", "")
            if axis and axis not in AXES:
                raise RegistryError(
                    f"instance {name!r} : axis {axis!r} inconnu (attendus : {AXES})")
            servers[name] = Instance(
                name=name,
                axis=axis,
                type=spec.get("type", ""),
                url=_expand_env(spec.get("url") or "").rstrip("/"),
                options={k: v for k, v in spec.items()
                         if k not in ("axis", "type", "url")},
            )
        defaults = dict(cfg.get("defaults") or {})
        # Cohérence : chaque défaut pointe une instance existante du bon axe.
        for axis, name in defaults.items():
            if axis not in AXES:
                raise RegistryError(f"defaults.{axis} : axe inconnu (attendus : {AXES})")
            if name not in servers:
                raise RegistryError(
                    f"defaults.{axis} = {name!r} : instance absente du registre")
            declared = servers[name].axis
            if declared and declared != axis:
                raise RegistryError(
                    f"defaults.{axis} = {name!r} mais cette instance est d'axe "
                    f"{declared!r}")
        return cls(servers, defaults)

    # ── accès ─────────────────────────────────────────────────────────────
    def get(self, name: str) -> Instance:
        if name not in self._servers:
            raise RegistryError(f"instance inconnue dans le registre : {name!r}")
        return self._servers[name]

    def default_for(self, axis: str) -> Instance:
        name = self._defaults.get(axis)
        if not name:
            raise RegistryError(f"aucun défaut providers.defaults.{axis} configuré")
        return self.get(name)

    def by_axis(self, axis: str):
        """Instances déclarées pour un axe donné (diagnostic/listing)."""
        return [i for i in self._servers.values() if i.axis == axis]

    def by_url(self, url: str, axis: str = ""):
        """Instance déclarée servant cette URL, ou None (comparaison sans slash final)."""
        target = (url or "").rstrip("/")
        if not target:
            return None
        for i in self._servers.values():
            if i.url and i.url.rstrip("/") == target and (not axis or not i.axis
                                                          or i.axis == axis):
                return i
        return None

    def resolve_name_or_url(self, value: str, axis: str = "") -> Instance:
        """Résout une instance depuis un **nom** de registre ou une **URL**.

        Les blocs `meta.yml` historiques (`redmine.instance`) ont été remplis avant que
        le champ ait une sémantique arrêtée : on y trouve aussi bien un nom d'instance
        qu'une URL (constaté sur `lemathou/mathematicians-db`). Refuser l'URL ferait
        échouer la résolution sur de la donnée légitime — on la rattache donc à
        l'instance déclarée qui sert cette URL.
        """
        if value in self._servers:
            return self._servers[value]
        if "://" in str(value):
            inst = self.by_url(value, axis)
            if inst is not None:
                return inst
            raise RegistryError(
                f"instance {value!r} : aucune instance déclarée ne sert cette URL "
                f"(déclarer le serveur dans pm.config.yml :: providers.servers, "
                f"puis référencer son NOM)")
        raise RegistryError(f"instance inconnue dans le registre : {value!r}")

    @property
    def servers(self):
        return dict(self._servers)

    @property
    def defaults(self):
        return dict(self._defaults)


# ── Rétro-compatibilité des blocs `meta.yml` historiques ────────────────────
# Un projet non migré n'a pas de bloc `providers:` ; on lit ses blocs d'origine
# pour ne rien changer à l'usage actuel.
def _legacy_resolution(meta: dict, axis: str, registry: Registry):
    if axis == "task":
        rm = meta.get("redmine") or {}
        if rm:
            inst = (registry.resolve_name_or_url(rm["instance"], "task")
                    if rm.get("instance") else registry.default_for("task"))
            params = {}
            if rm.get("project_id") is not None:
                params["project_id"] = rm["project_id"]
            if rm.get("subprojects"):
                params["subprojects"] = rm["subprojects"]
            return Resolution(inst, params, source="legacy")
    elif axis == "forge":
        gl = meta.get("gitlab") or {}
        if gl:
            # bloc `gitlab:` historique → instance forge par défaut (GitLab),
            # params repo/group/default_branch conservés.
            inst = (registry.resolve_name_or_url(gl["instance"], "forge")
                    if gl.get("instance") else registry.default_for("forge"))
            params = {k: gl[k] for k in ("repo", "group", "default_branch")
                      if k in gl}
            return Resolution(inst, params, source="legacy")
    # axe doc : pas de bloc legacy → on retombe sur le défaut.
    return None


def _entry_resolution(entry: dict, axis: str, registry: Registry, where: str) -> Resolution:
    """Une entrée de `providers.<axe>` (dict) → `Resolution` validée."""
    inst = registry.get(entry["instance"])
    if inst.axis and inst.axis != axis:
        raise RegistryError(
            f"{where}.instance = {entry['instance']!r} est d'axe {inst.axis!r}")
    role = entry.get("role") or "primary"
    if role not in ROLES:
        raise RegistryError(f"{where}.role = {role!r} inconnu (attendus : {ROLES})")
    link = entry.get("link") or {}
    sync = entry.get("sync") or {}
    # Les règles de rattachement/synchro n'ont de sens que pour un partenaire :
    # les poser sur le primaire (la source de vérité) est une erreur de conf.
    if role == "primary" and (link or sync):
        raise RegistryError(
            f"{where} : 'link'/'sync' sur le provider PRIMAIRE — ces règles ne "
            f"valent que pour un secondaire (le primaire est la source de vérité)")
    params = {k: v for k, v in entry.items() if k not in _ENTRY_KEYS}
    return Resolution(inst, params, source="providers", role=role, link=link, sync=sync)


def resolve_instances(project_meta: dict, axis: str, registry: Registry) -> list:
    """Providers d'un axe pour ce projet : **primaire en tête**, puis secondaires.

    Retourne toujours au moins un élément (le primaire) — via le bloc `providers:`,
    le bloc legacy, ou le défaut du registre. Voir priorité en tête de module.
    """
    if axis not in AXES:
        raise RegistryError(f"axe inconnu : {axis!r} (attendus : {AXES})")
    meta = project_meta or {}

    # 1. Bloc `providers:` explicite du projet — dict (1 provider) ou liste (N).
    prov = (meta.get("providers") or {}).get(axis)
    entries = []
    if isinstance(prov, dict) and prov.get("instance"):
        entries = [prov]
    elif isinstance(prov, (list, tuple)):
        entries = [e for e in prov if isinstance(e, dict)]
        for i, e in enumerate(entries):
            if not e.get("instance"):
                raise RegistryError(
                    f"providers.{axis}[{i}] : champ 'instance' obligatoire")
    if entries:
        out = [_entry_resolution(e, axis, registry, f"providers.{axis}[{i}]")
               for i, e in enumerate(entries)]
        primaries = [r for r in out if r.is_primary]
        if len(primaries) != 1:
            raise RegistryError(
                f"providers.{axis} : {len(primaries)} provider(s) 'primary' — il en "
                f"faut exactement un (les autres en role: secondary)")
        seen = set()
        for r in out:
            if r.instance.name in seen:
                raise RegistryError(
                    f"providers.{axis} : instance {r.instance.name!r} déclarée deux fois")
            seen.add(r.instance.name)
        # Primaire en tête, ordre de déclaration préservé pour les secondaires.
        return primaries + [r for r in out if not r.is_primary]

    # 2. Rétro-compat (blocs redmine:/gitlab:).
    legacy = _legacy_resolution(meta, axis, registry)
    if legacy:
        return [legacy]

    # 3. Défaut du registre.
    return [Resolution(registry.default_for(axis), {}, source="default")]


def resolve_instance(project_meta: dict, axis: str, registry: Registry) -> Resolution:
    """Provider **primaire** pour (projet, axe) — source de vérité PM.

    Sémantique historique conservée : un projet sans bloc `providers:` (ou avec la
    forme dict) résout exactement comme avant l'introduction des secondaires.
    """
    return resolve_instances(project_meta, axis, registry)[0]


def secondaries(project_meta: dict, axis: str, registry: Registry) -> list:
    """Providers secondaires (partenaires) de cet axe — liste éventuellement vide."""
    return [r for r in resolve_instances(project_meta, axis, registry) if not r.is_primary]
