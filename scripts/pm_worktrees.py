"""pm_worktrees — d'où partent les worktrees, où vont les envs (RM3209).

Le PM ne connaissait qu'un modèle : un dépôt bare partagé `<ws>/repos/<repo>.git`, des worktrees
`<ws>/envs/<repo>-rm<id>`. Chez certains clients, chaque dev a SON dépôt ; le chemin du bare était écrit en dur à
cinq endroits. Ce module est désormais le seul à décider :

    git.worktree_source  (instance, admin)   central   → <ws>/repos/<repo>.git
                                             per_user  → <dossier des dépôts du dev>/<repo>
    dossier des dépôts   (par utilisateur)   PM_REPOS_DIR de son ~/.config/mmi-pm/.env, défaut ~/repos
    git.envs_layout      (instance, admin)   project   → <ws>/envs/<env>
                                             user      → <ws>/envs/<user>/<env>

Les deux réglages d'instance se lisent dans `pm.config.yml` puis `pm.config.local.yml` (qui prime), et
dans ces fichiers SEULEMENT : une variable d'environnement permettrait à n'importe quel dev de contourner
un réglage réservé à l'admin. Une valeur inconnue est refusée, jamais rabattue sur le défaut.
"""
import os
import pwd
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

SOURCES = ("central", "per_user")
LAYOUTS = ("project", "user")
DEFAULT_REPOS_DIR = "~/repos"
CORE_DIR = Path(__file__).resolve().parent.parent


class LayoutError(ValueError):
    """Réglage invalide ou information manquante pour résoudre un chemin."""


@dataclass(frozen=True)
class Layout:
    source: str = "central"
    envs_layout: str = "project"


def read_layout(core_dir: Path = CORE_DIR) -> Layout:
    merged: dict = {}
    for name in ("pm.config.yml", "pm.config.local.yml"):
        p = Path(core_dir) / name
        if not p.is_file():
            continue
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        section = data.get("git") if isinstance(data, dict) else None
        if section is None:
            continue
        if not isinstance(section, dict):
            raise LayoutError(f"{p} : la section `git:` doit être un dictionnaire")
        merged.update({k: v for k, v in section.items() if k in ("worktree_source", "envs_layout")})
    source = merged.get("worktree_source") or "central"
    layout = merged.get("envs_layout") or "project"
    if source not in SOURCES:
        raise LayoutError(f"git.worktree_source : « {source} » inconnu (attendu : {' | '.join(SOURCES)})")
    if layout not in LAYOUTS:
        raise LayoutError(f"git.envs_layout : « {layout} » inconnu (attendu : {' | '.join(LAYOUTS)})")
    return Layout(source, layout)


def _read_env_value(env_file: Path, key: str) -> Optional[str]:
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith(f"{key}="):
                return s.split("=", 1)[1].strip().strip("'\"") or None
    except OSError:
        pass
    return None


def user_repos_dir(user: Optional[str] = None, home: Optional[Path] = None, environ=os.environ,
                   current: Optional[bool] = None) -> Path:
    """Dossier des dépôts d'un utilisateur. L'environnement n'est consulté que pour l'utilisateur COURANT :
    pour un autre, sa valeur vient de son propre `~/.config/mmi-pm/.env`."""
    if home is None:
        entry = pwd.getpwnam(user) if user else pwd.getpwuid(os.geteuid())
        home = Path(entry.pw_dir)
        if current is None:
            current = entry.pw_uid == os.geteuid()
    home = Path(home)
    raw = None
    if environ is not None and current is not False:
        raw = environ.get("PM_REPOS_DIR")
    if raw is None:
        raw = _read_env_value(home / ".config" / "mmi-pm" / ".env", "PM_REPOS_DIR")
    raw = raw or DEFAULT_REPOS_DIR
    if raw == "~" or raw.startswith("~/"):
        return home / raw[2:] if raw != "~" else home
    p = Path(raw)
    return p if p.is_absolute() else home / p


def central_bare(ws: Path, repo: str) -> Path:
    """Dépôt partagé du layout RM1993. Seul endroit où ce chemin s'écrit."""
    return Path(ws) / "repos" / f"{repo}.git"


def source_repo(ws: Path, repo: str, layout: Layout, repos_dir: Optional[Path] = None) -> Path:
    if layout.source == "central":
        return central_bare(ws, repo)
    if repos_dir is None:
        raise LayoutError("worktree_source per_user : dossier des dépôts de l'utilisateur requis")
    return Path(repos_dir) / repo


def envs_root(ws: Path, layout: Layout, user: Optional[str] = None) -> Path:
    if layout.envs_layout == "project":
        return Path(ws) / "envs"
    if not user:
        raise LayoutError("envs_layout user : nom d'utilisateur requis")
    return Path(ws) / "envs" / user


def env_dir(ws: Path, env_name: str, layout: Layout, user: Optional[str] = None) -> Path:
    return envs_root(ws, layout, user) / env_name


def bare_creation_allowed(layout: Layout) -> bool:
    """En `per_user`, il n'y a pas de dépôt partagé à créer : chaque dev clone le sien."""
    return layout.source == "central"


def same_repo(a: Path, b: Path) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return False


def current_user() -> str:
    return pwd.getpwuid(os.geteuid()).pw_name


def workspace_for_task(md_path: Path, projects_root: Path) -> Optional[Path]:
    """Workspace de code d'une tâche. Par le lien du projet dans l'index (`…/projects/<p>` → `<ws>/.mmi-pm`),
    lu SANS suivre le `.mmi-pm` jusqu'aux données (qui peuvent vivre ailleurs, ex. /opt/mmi-pm/data) ;
    à défaut, le parent du `.mmi-pm` qui contient la fiche (co-localisation)."""
    md_path = Path(md_path)
    for anc in md_path.parents:
        if anc.is_symlink():
            target = Path(os.readlink(anc))
            if not target.is_absolute():
                target = anc.parent / target
            if target.name == ".mmi-pm":
                return target.parent
        if anc.name == ".mmi-pm":
            return anc.parent
        if Path(projects_root) in (anc,):
            break
    return None


def main_repo_dir(root: Path, git_common_dir: str) -> Path:
    """Dépôt principal d'où part `root` — le dépôt lui-même, ou celui d'un worktree lié (`--git-common-dir`)."""
    if not git_common_dir:
        return Path(root)
    p = Path(git_common_dir)
    if not p.is_absolute():
        p = Path(root) / p
    return p.parent if p.name == ".git" else p


def per_user_source_error(root: Path, git_common_dir: str, expected: Path) -> Optional[str]:
    """En `per_user`, une branche de ticket part du dépôt de l'utilisateur COURANT, jamais de celui d'un autre
    (ni d'un clone quelconque). Rend le message d'erreur, ou None si la source est la bonne."""
    src = main_repo_dir(root, git_common_dir)
    if same_repo(src, expected):
        return None
    return (f"git.worktree_source=per_user — la branche part de TON dépôt {expected}, pas de {src}. "
            "Place-toi dedans, ou règle PM_REPOS_DIR dans ~/.config/mmi-pm/.env.")


def resolve_source(ws: Path, repo: str, core_dir: Path = CORE_DIR) -> Path:
    """Dépôt source pour l'utilisateur COURANT, selon les réglages de l'instance."""
    layout = read_layout(core_dir)
    return source_repo(ws, repo, layout, repos_dir=user_repos_dir() if layout.source == "per_user" else None)


def resolve_env_dir(ws: Path, env_name: str, core_dir: Path = CORE_DIR) -> Path:
    """Dossier d'un env pour l'utilisateur COURANT, selon les réglages de l'instance."""
    return env_dir(ws, env_name, read_layout(core_dir), current_user())
