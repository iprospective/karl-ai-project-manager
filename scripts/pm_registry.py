#!/usr/bin/env python3
"""pm_registry — registre de serveurs (instances) + résolution d'instance par projet.

Fondation P0 (RM2542) de la généralisation forge → 3 axes providers
(**task** / **forge** / **doc**) — cf. CDC RM2530 [[Cdc-rm2530-providers-par-projet]].

Deux entrées :
  * `Registry.from_config(providers_cfg)` — construit le registre depuis la section
    `providers:` de `pm.config.yml` (exposée par `PMConfig.providers`).
  * `resolve_instance(project_meta, axis, registry)` — pour un projet (son `meta.yml`)
    et un axe, retourne la **`Resolution`** = instance retenue + params projet
    (project_id, repo, …) + `source` (traçabilité).

**INERTE par défaut / zéro régression.** Les défauts du registre reproduisent
l'état actuel (Redmine global + GitLab) ; la rétro-compat lit les blocs historiques
`redmine:` / `gitlab:` d'un `meta.yml` qui n'a pas (encore) de bloc `providers:`.
Aucun script existant ne consomme ce module en P0 — le câblage est en P1+.

Priorité de résolution, par axe :
  1. `meta.providers.<axe>`  (config explicite du PROJET)
  2. bloc legacy du `meta.yml` projet (`redmine:` pour task, `gitlab:` pour forge)
  3. `providers.<axe>` du CLIENT — vaut pour tous ses projets (RM2682)
  4. `providers.defaults.<axe>` du registre

Un axe porte **un primaire et N secondaires** (RM2653). Le primaire est la source
de vérité PM ; un secondaire est un gestionnaire PARTENAIRE, qui porte ses propres
règles de rattachement (`link:`) et de synchro (`sync:`) — cf. CDC RM2626. Formes
acceptées à tous les niveaux (projet comme client), toutes rétro-compatibles :

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

Le legacy projet (2) passe **avant** le client (3) : c'est une configuration du
projet, donc plus spécifique. Conséquence pratique : sur les axes `task`/`forge`,
un projet portant un bloc `redmine:`/`gitlab:` (le cas de presque tous) n'hérite
pas du client — le niveau client joue pleinement sur les axes sans legacy, dont
`secret`, et sur les projets migrés au bloc `providers:`.

Axes : `DEFAULT_AXES` (task/forge/doc/secret) + tout axe déclaré dans
`providers.axes`. Ajouter un axe (monitoring…) ne demande aucune modification ici.
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import _expand_env  # interpolation ${VAR} / ${VAR:-defaut}, comme roots

# Axes livrés d'office. `secret` (vaults) arrive avec RM2682/L1 — cf. CDC RM2662.
# La liste est un DÉFAUT, pas une limite : `providers.axes` peut l'étendre (un axe
# `monitoring` ne doit coûter qu'une ligne de conf, pas une modification d'ici).
DEFAULT_AXES = ("task", "forge", "doc", "secret")

# Rétro-compat : plusieurs appelants importent `AXES`. Le registre, lui, raisonne
# sur `Registry.axes` (qui tient compte de `providers.axes`).
AXES = DEFAULT_AXES

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
    source: str = "default"                       # 'providers' | 'legacy' | 'client' | 'default'
    role: str = "primary"                         # 'primary' | 'secondary' (RM2653)
    link: dict = field(default_factory=dict)      # règles de rattachement (secondaire)
    sync: dict = field(default_factory=dict)      # règles de synchro pull/push (secondaire)

    @property
    def is_primary(self) -> bool:
        return self.role == "primary"


class Registry:
    def __init__(self, servers: dict, defaults: dict, axes=None):
        self._servers = servers      # name -> Instance
        self._defaults = defaults     # axis -> instance name
        self._axes = tuple(axes) if axes else DEFAULT_AXES

    # ── construction ──────────────────────────────────────────────────────
    @classmethod
    def from_config(cls, providers_cfg: dict) -> "Registry":
        cfg = providers_cfg or {}
        # `providers.axes` étend (ou restreint) la liste d'axes. Les axes livrés
        # restent toujours valides : les retirer casserait des appelants en place.
        declared_axes = cfg.get("axes") or []
        if not isinstance(declared_axes, (list, tuple)):
            raise RegistryError("providers.axes doit être une liste d'axes")
        axes = tuple(DEFAULT_AXES) + tuple(a for a in declared_axes
                                           if a not in DEFAULT_AXES)
        servers: dict = {}
        for name, spec in (cfg.get("servers") or {}).items():
            spec = spec or {}
            axis = spec.get("axis", "")
            if axis and axis not in axes:
                raise RegistryError(
                    f"instance {name!r} : axis {axis!r} inconnu (attendus : {axes} "
                    f"— déclare-le dans providers.axes)")
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
            if axis not in axes:
                raise RegistryError(f"defaults.{axis} : axe inconnu (attendus : {axes})")
            if name not in servers:
                raise RegistryError(
                    f"defaults.{axis} = {name!r} : instance absente du registre")
            declared = servers[name].axis
            if declared and declared != axis:
                raise RegistryError(
                    f"defaults.{axis} = {name!r} mais cette instance est d'axe "
                    f"{declared!r}")
        return cls(servers, defaults, axes=axes)

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

    @property
    def axes(self):
        """Axes valides pour CE registre (défauts + `providers.axes`)."""
        return self._axes


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


def _entry_resolution(entry: dict, axis: str, registry: Registry, source: str,
                      where: str) -> Resolution:
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
    return Resolution(inst, params, source=source, role=role, link=link, sync=sync)


def _providers_resolutions(meta: dict, axis: str, registry: Registry, source: str):
    """Bloc `providers.<axe>` d'un meta (projet ou client) → liste de `Resolution`.

    Accepte la forme **dict** (un seul provider, historique) comme la forme
    **liste** (primaire + secondaires). Retourne [] si le bloc est absent.
    """
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
    if not entries:
        return []
    out = [_entry_resolution(e, axis, registry, source, f"providers.{axis}[{i}]")
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


def resolve_instances(project_meta: dict, axis: str, registry: Registry,
                      client_meta: dict = None) -> list:
    """Providers d'un axe pour ce projet : **primaire en tête**, puis secondaires.

    Retourne toujours au moins un élément (le primaire) — via le bloc `providers:`
    du projet, son bloc legacy, celui du CLIENT, ou le défaut du registre. Voir la
    priorité en tête de module.

    `client_meta` (optionnel) ajoute le **niveau client** entre le projet et le
    défaut d'instance (RM2682) : « tous les projets de ce client passent par tel
    vault / telle forge » — et, depuis RM2653, « …et sont rattachés à tel
    gestionnaire partenaire ». Omis ⇒ comportement d'avant, à l'identique.
    """
    if axis not in registry.axes:
        raise RegistryError(f"axe inconnu : {axis!r} (attendus : {registry.axes})")
    meta = project_meta or {}

    # 1. Bloc `providers:` explicite du projet.
    res = _providers_resolutions(meta, axis, registry, "providers")
    if res:
        return res

    # 2. Bloc legacy du projet (`redmine:` / `gitlab:`) — un seul provider, primaire.
    legacy = _legacy_resolution(meta, axis, registry)
    if legacy:
        return [legacy]

    # 3. Bloc `providers:` du client — vaut pour tous ses projets.
    res = _providers_resolutions(client_meta or {}, axis, registry, "client")
    if res:
        return res

    # 4. Défaut du registre.
    return [Resolution(registry.default_for(axis), {}, source="default")]


def resolve_instance(project_meta: dict, axis: str, registry: Registry,
                     client_meta: dict = None) -> Resolution:
    """Provider **primaire** pour (projet, axe) — source de vérité PM.

    Sémantique historique conservée : un projet sans bloc `providers:` (ou avec la
    forme dict) résout exactement comme avant l'introduction des secondaires.
    """
    return resolve_instances(project_meta, axis, registry, client_meta)[0]


def secondaries(project_meta: dict, axis: str, registry: Registry,
                client_meta: dict = None) -> list:
    """Providers secondaires (partenaires) de cet axe — liste éventuellement vide."""
    return [r for r in resolve_instances(project_meta, axis, registry, client_meta)
            if not r.is_primary]
