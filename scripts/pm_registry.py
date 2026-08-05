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
  1. `meta.providers.<axe>.instance`  (config explicite par projet)
  2. bloc legacy du `meta.yml` (`redmine:` pour task, `gitlab:` pour forge)
  3. `providers.defaults.<axe>` du registre
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import _expand_env  # interpolation ${VAR} / ${VAR:-defaut}, comme roots

AXES = ("task", "forge", "doc")


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
    """Instance retenue pour (projet, axe) + params projet + provenance."""
    instance: Instance
    params: dict = field(default_factory=dict)   # project_id, repo, group, default_branch…
    source: str = "default"                       # 'providers' | 'legacy' | 'default'


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
            inst = (registry.get(rm["instance"]) if rm.get("instance")
                    else registry.default_for("task"))
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
            inst = (registry.get(gl["instance"]) if gl.get("instance")
                    else registry.default_for("forge"))
            params = {k: gl[k] for k in ("repo", "group", "default_branch")
                      if k in gl}
            return Resolution(inst, params, source="legacy")
    # axe doc : pas de bloc legacy → on retombe sur le défaut.
    return None


def resolve_instance(project_meta: dict, axis: str, registry: Registry) -> Resolution:
    """Instance retenue pour (projet, axe). Voir priorité en tête de module."""
    if axis not in AXES:
        raise RegistryError(f"axe inconnu : {axis!r} (attendus : {AXES})")
    meta = project_meta or {}

    # 1. Bloc `providers:` explicite du projet.
    prov = (meta.get("providers") or {}).get(axis) or {}
    if prov.get("instance"):
        inst = registry.get(prov["instance"])
        if inst.axis and inst.axis != axis:
            raise RegistryError(
                f"providers.{axis}.instance = {prov['instance']!r} est d'axe "
                f"{inst.axis!r}")
        params = {k: v for k, v in prov.items() if k != "instance"}
        return Resolution(inst, params, source="providers")

    # 2. Rétro-compat (blocs redmine:/gitlab:).
    legacy = _legacy_resolution(meta, axis, registry)
    if legacy:
        return legacy

    # 3. Défaut du registre.
    return Resolution(registry.default_for(axis), {}, source="default")
