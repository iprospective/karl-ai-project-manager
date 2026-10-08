"""pm_privsep — qui possède quoi dans une instance PM : UNE seule source (RM3379, A1).

Deux outils posaient la propriété des mêmes fichiers avec deux modèles différents : `core-lock` (rejoué à
chaque `mmi-pm core update`) et `pm-perms --var`. `pm-perms` « corrigeait » ce que la mise à jour suivante
défaisait. Tant qu'il n'y avait qu'un humain, personne ne le voyait : `mathieu-pm` appartenait au groupe
`mathieu`. À plusieurs devs, un `<dev>-pm` hors de ce groupe ne lit plus `.env` et n'écrit plus `var/`.

Le modèle vit ici, et il est **piloté par la configuration de l'instance** (décision Mathieu 2026-10-08 :
une instance cliente ne se configure pas comme celle d'iProspective) :

    privsep:
      group:       pm         # données partagées : les devs y écrivent (var/, projects/, workspaces)
      admin_group: pm-admin   # tâches d'administration ET lecture des secrets communs (.env)

Les deux comptes viennent du `.env` : `KARL_SUDO_USER` (service PM, propriétaire de `var/`) et `KARL_USER`
(agent runtime). Décisions appliquées :
- **les secrets de service ne sont pas lisibles par les devs** : `.env` (et ses dérivés `.env.*`) en
  `root:<admin_group>` 640 — un dev n'a que sa conf personnelle (`<core>/var/users/<login>/.env`, RM3318) ;
- `pm.env`, non secret, en `root:<group>` 640 — il était en 644 ;
- `var/` reste au service PM, groupe `<group>`, setgid : les devs y écrivent l'état partagé ;
- le code reste `root:root` : sa mise à jour est le seul geste privilégié.

**Jamais de panne de déploiement** : si `admin_group` n'existe pas sur le système, on retombe sur `group`
(et sur le groupe du compte runtime si `group` manque aussi) en le DISANT. Un `core update` ne doit pas
échouer parce qu'un groupe n'a pas encore été créé ; `install-mmi-pm` les crée.
"""
import grp
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

DEFAULT_GROUP = "pm"
DEFAULT_ADMIN_GROUP = "pm-admin"
SECRET_MODE = 0o640          # .env et dérivés : root:<admin_group>
CONF_MODE = 0o640            # pm.env : root:<group>
STATE_MODE = 0o2775          # var/ : setgid, group-writable
#: Fichiers de secrets à la racine du cœur. Le motif couvre les DÉRIVÉS (`.env.bak-…`, `.env.sav`) :
#: c'est par là qu'une sauvegarde s'est retrouvée lisible par tous (RM3378).
SECRET_GLOBS = (".env", ".env.*", ".env-*")
CONF_FILES = ("pm.env",)


@dataclass(frozen=True)
class Model:
    group: str                      # groupe des données partagées
    admin_group: str                # groupe d'administration (secrets communs)
    service_user: str               # KARL_SUDO_USER — propriétaire de var/
    runtime_user: str               # KARL_USER — agent/cockpit
    fallbacks: tuple = ()           # messages à DIRE quand un groupe demandé n'existe pas

    def describe(self) -> str:
        return (f"code=root ; secrets=root:{self.admin_group} {SECRET_MODE:04o} ; "
                f"pm.env=root:{self.group} {CONF_MODE:04o} ; "
                f"var/={self.service_user}:{self.group} {STATE_MODE:04o} ; "
                f"projects/={self.service_user}:{self.group}")


def _group_exists(name: str) -> bool:
    try:
        grp.getgrnam(name)
        return True
    except KeyError:
        return False


def read_config(core_dir: Path) -> dict:
    """Section `privsep:` de `pm.config.yml`, surchargée par `pm.config.local.yml`."""
    out: dict = {}
    for name in ("pm.config.yml", "pm.config.local.yml"):
        p = Path(core_dir) / name
        if not p.is_file():
            continue
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        section = data.get("privsep") if isinstance(data, dict) else None
        if isinstance(section, dict):
            out.update({k: v for k, v in section.items() if k in ("group", "admin_group")})
    return out


def load(core_dir: Path, environ=None, group_exists=_group_exists) -> Model:
    """Modèle effectif : configuration de l'instance + comptes du `.env`, replis DITS."""
    environ = os.environ if environ is None else environ
    cfg = read_config(core_dir)
    group = str(cfg.get("group") or DEFAULT_GROUP)
    admin = str(cfg.get("admin_group") or DEFAULT_ADMIN_GROUP)
    runtime = environ.get("KARL_USER") or ""
    service = environ.get("KARL_SUDO_USER") or ""
    fallbacks = []
    if not group_exists(group):
        legacy = runtime or group
        fallbacks.append(f"groupe « {group} » inexistant → repli sur « {legacy} » "
                         f"(créer : sudo groupadd {group})")
        group = legacy
    if not group_exists(admin):
        fallbacks.append(f"groupe d'administration « {admin} » inexistant → les secrets communs restent "
                         f"lisibles par « {group} » (créer : sudo groupadd {admin})")
        admin = group
    return Model(group=group, admin_group=admin, service_user=service, runtime_user=runtime,
                 fallbacks=tuple(fallbacks))


@dataclass(frozen=True)
class Target:
    path: Path
    owner: Optional[str]            # None = inchangé
    group: str
    mode: int
    recurse: bool = False           # dossiers : appliquer récursivement (+ setgid)
    label: str = ""


def secret_files(core_dir: Path) -> list:
    """`.env` et ses DÉRIVÉS présents à la racine du cœur (sauvegardes incluses)."""
    core = Path(core_dir)
    out = []
    for pattern in SECRET_GLOBS:
        for p in sorted(core.glob(pattern)):
            if p.is_file() and not p.is_symlink() and p.name != ".env.example" and p not in out:
                out.append(p)
    return out


def core_targets(core_dir: Path, state_dir: Path, model: Model) -> list:
    """Cibles du cœur, dans l'ordre d'application. Les chemins absents sont écartés par l'appelant."""
    core = Path(core_dir)
    t = [Target(p, "root", model.admin_group, SECRET_MODE, label="secrets communs")
         for p in secret_files(core)]
    t += [Target(core / f, "root", model.group, CONF_MODE, label="conf d'instance (non secrète)")
          for f in CONF_FILES]
    t.append(Target(Path(state_dir), model.service_user or None, model.group, STATE_MODE,
                    recurse=True, label="état runtime"))
    t.append(Target(core / "projects", model.service_user or None, model.group, STATE_MODE,
                    recurse=True, label="index résolveur"))
    return t


def sh_exports(core_dir: Path, state_dir: Path, model: Model) -> str:
    """Modèle consommable par `core-lock` (shell) — même source, aucune règle dupliquée en bash.

    Tout ce qui peut contenir un espace, une apostrophe ou un caractère accentué passe par `shlex.quote` :
    les messages de repli en portent (« groupe d'administration »), et un `eval` naïf cassait dessus."""
    q = shlex.quote
    lines = [f"PRIVSEP_GROUP={q(model.group)}", f"PRIVSEP_ADMIN_GROUP={q(model.admin_group)}",
             f"PRIVSEP_SERVICE_USER={q(model.service_user)}", f"PRIVSEP_RUNTIME_USER={q(model.runtime_user)}",
             f"PRIVSEP_SUMMARY={q(model.describe())}"]
    for i, w in enumerate(model.fallbacks, 1):
        lines.append(f"PRIVSEP_WARN_{i}={q(w)}")
    lines.append("PRIVSEP_SECRET_FILES=" + q(" ".join(str(p) for p in secret_files(core_dir))))
    lines.append(f"PRIVSEP_SECRET_MODE={SECRET_MODE:04o}")
    lines.append("PRIVSEP_CONF_FILES=" + q(" ".join(str(Path(core_dir) / f) for f in CONF_FILES)))
    lines.append(f"PRIVSEP_CONF_MODE={CONF_MODE:04o}")
    lines.append(f"PRIVSEP_STATE_DIR={q(str(state_dir))}")
    lines.append(f"PRIVSEP_PROJECTS_DIR={q(str(Path(core_dir) / 'projects'))}")
    return "\n".join(lines) + "\n"
