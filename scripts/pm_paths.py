"""pm_paths — Résolution de chemins du système PM iprospective.

Lit `pm.config.yml` (+ optionnel `pm.config.local.yml`) à la racine du repo
PM et expose `PMConfig.path(key, **kwargs)` pour résoudre n'importe quel
chemin sans hardcoder la structure dans le code appelant.

Usage typique :

    from pm_paths import PMConfig
    cfg = PMConfig.load()
    cfg.projects_root                              # Path
    cfg.path("entity", entity="lemathou")          # Path
    cfg.path("project", entity="x", project="y")   # Path
    cfg.path("task_file", entity=..., project=..., id=42, slug="foo-bar")
    for ent, proj, p in cfg.iter_projects(): ...
    cfg.find_task(rm_id)                           # Path | None
    cfg.find_project_by_redmine_id(rm_proj_id)     # (Path, Path) | (None, None)

Aucune fonction de cette lib ne doit présupposer la structure interne du
repo projects (présence/nom de "clients/", de "projects/", etc.) — tout
passe par les patterns définis dans pm.config.yml.
"""
import os
import re
import sys
from pathlib import Path
from typing import Iterator, Optional, Tuple

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")


_ENV_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}")
_PATTERN_REF_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def _load_env_file(path: Path) -> None:
    """Charge un fichier .env (KEY=VALUE), sans écraser l'environnement existant."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'\"")
        if k and k not in os.environ:
            os.environ[k] = v


def _expand_env(value: str) -> str:
    """Résout `${VAR}` et `${VAR:-default}` dans une chaîne."""
    if not isinstance(value, str):
        return value

    def repl(m):
        var, default = m.group(1), m.group(2)
        return os.environ.get(var, default if default is not None else "")

    return _ENV_VAR_RE.sub(repl, value)


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class PMConfig:
    """Résolveur de chemins du système PM (lecture seule)."""

    def __init__(self, pm_dir: Path, projects_root: Path, patterns: dict):
        self.pm_dir = pm_dir
        self.projects_root = projects_root
        self._patterns = patterns

    @classmethod
    def load(cls, pm_dir: Optional[Path] = None) -> "PMConfig":
        # 1. Auto-détecte le repo PM si non fourni
        if pm_dir is None:
            pm_dir = Path(__file__).resolve().parent.parent
        pm_dir = Path(pm_dir).resolve()

        # 2. Charge .env (sans écraser l'env existant)
        _load_env_file(pm_dir / ".env")

        # 3. Charge pm.config.yml + pm.config.local.yml (merge)
        cfg_path = pm_dir / "pm.config.yml"
        if not cfg_path.is_file():
            sys.exit(f"ERREUR : {cfg_path} introuvable")
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        local_path = pm_dir / "pm.config.local.yml"
        if local_path.is_file():
            local_cfg = yaml.safe_load(local_path.read_text(encoding="utf-8")) or {}
            cfg = _deep_merge(cfg, local_cfg)

        # 4. Résout les racines
        roots = cfg.get("roots", {})

        pm_dir_raw = _expand_env(roots.get("pm_dir", "auto"))
        if pm_dir_raw == "auto" or not pm_dir_raw:
            pm_dir_final = pm_dir
        else:
            pm_dir_final = Path(pm_dir_raw).resolve()

        projects_root_raw = _expand_env(roots.get("projects_root", ""))
        if not projects_root_raw:
            sys.exit(
                "ERREUR : roots.projects_root non défini "
                "(vérifier $PROJECTS_PATH dans .env ou pm.config.local.yml)"
            )
        projects_root = Path(projects_root_raw).resolve()
        if not projects_root.is_dir():
            sys.exit(f"ERREUR : projects_root introuvable : {projects_root}")

        patterns = cfg.get("paths", {}) or {}
        if not patterns:
            sys.exit("ERREUR : pm.config.yml :: paths est vide")

        return cls(pm_dir_final, projects_root, patterns)

    # ── Résolution de patterns ──────────────────────────────────────────
    def path(self, key: str, **kwargs) -> Path:
        """Résout un pattern de chemin par sa clé.

        Variables disponibles dans le pattern :
          - `{pm_dir}` et `{projects_root}` : racines de la config
          - n'importe quel kwarg passé (ex: `entity="x"`, `project="y"`)
          - n'importe quelle autre clé de `paths.*` (résolue récursivement)
        """
        return Path(self._resolve(key, kwargs, ()))

    def _resolve(self, key: str, kwargs: dict, stack: tuple) -> str:
        if key in stack:
            raise ValueError(
                f"référence circulaire dans paths.{key} : {' -> '.join(stack + (key,))}"
            )
        if key not in self._patterns:
            raise KeyError(f"pattern inconnu : paths.{key}")
        new_stack = stack + (key,)
        template = self._patterns[key]

        def repl(m):
            name = m.group(1)
            if name == "pm_dir":
                return str(self.pm_dir)
            if name == "projects_root":
                return str(self.projects_root)
            # Patterns d'abord (sauf si on est déjà en train de résoudre
            # ce nom — auto-réf → fallback kwargs). Cela permet par exemple
            # à `entity: "{entities_dir}/{entity}"` d'utiliser le kwarg
            # `entity` pour le slug, tout en autorisant `entity_projects_dir:
            # "{entity}/projects"` à référencer le pattern `entity`.
            if name in self._patterns and name not in new_stack:
                return self._resolve(name, kwargs, new_stack)
            if name in kwargs:
                return str(kwargs[name])
            raise KeyError(
                f"variable {{{name}}} non résolue pour paths.{key} "
                f"(kwargs={list(kwargs)})"
            )

        return _PATTERN_REF_RE.sub(repl, template)

    # ── Itérateurs sur l'arborescence ───────────────────────────────────
    def iter_entities(self) -> Iterator[Tuple[str, Path]]:
        """Yield `(slug, Path)` pour chaque entité (client/produit/self) existante.

        Ignore les symlinks (cf. projects_used/) pour ne pas double-compter.
        """
        entities_dir = self.path("entities_dir")
        if not entities_dir.is_dir():
            return
        for p in sorted(entities_dir.iterdir()):
            if p.is_dir() and not p.is_symlink():
                yield p.name, p

    def iter_projects(
        self, entity: Optional[str] = None
    ) -> Iterator[Tuple[str, str, Path]]:
        """Yield `(entity_slug, project_slug, project_path)` pour chaque projet.

        Si `entity` est précisé, ne yield que les projets de cette entité.
        Ignore les symlinks (vues `projects_used/`).
        """
        for ent_slug, _ in self.iter_entities():
            if entity is not None and ent_slug != entity:
                continue
            try:
                proj_dir = self.path("entity_projects_dir", entity=ent_slug)
            except KeyError:
                continue
            if not proj_dir.is_dir():
                continue
            for p in sorted(proj_dir.iterdir()):
                if p.is_dir() and not p.is_symlink():
                    yield ent_slug, p.name, p

    # ── Lookups Redmine ─────────────────────────────────────────────────
    _FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def find_task(self, rm_id: int) -> Optional[Path]:
        """Cherche le fichier `RM{id}_*.md` (hors `.log.md`) parmi tous les
        projets. Retourne le `Path` ou `None`."""
        for ent_slug, proj_slug, _ in self.iter_projects():
            tasks_dir = self.path("tasks_dir", entity=ent_slug, project=proj_slug)
            if not tasks_dir.is_dir():
                continue
            for f in tasks_dir.glob(f"RM{rm_id}_*.md"):
                if f.name.endswith(".log.md"):
                    continue
                return f
        return None

    def find_project_by_redmine_id(
        self, redmine_project_id
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """Cherche le projet PM dont `overview.md` a `redmine.project_id == X`.

        `redmine_project_id` peut être un int (id numérique Redmine) ou un str
        (slug `identifier`). Retourne `(entity_path, project_path)` ou `(None, None)`.
        """
        for ent_slug, proj_slug, proj_path in self.iter_projects():
            overview = (
                self.path("project_dir", entity=ent_slug, project=proj_slug)
                / "overview.md"
            )
            if not overview.is_file():
                continue
            try:
                content = overview.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            m = self._FM_RE.match(content)
            if not m:
                continue
            try:
                fm = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError:
                continue
            rid = (fm.get("redmine") or {}).get("project_id")
            if rid == redmine_project_id:
                ent_path = self.path("entity", entity=ent_slug)
                return ent_path, proj_path
        return None, None

    def detect_project_from_cwd(
        self, start: Optional[Path] = None
    ) -> Optional[Tuple[str, str]]:
        """Détecte (entity, project) depuis le cwd (ou `start`) — source unique.

        Mécanisme **indépendant de la forme de `.mmi-pm`** (symlink hérité OU
        dossier co-localisé, RM1942) : on lit `<.mmi-pm>/project/overview.md` et
        on en extrait `client` + `slug` (présents qu'on suive un symlink ou qu'on
        lise un dossier réel). Fallbacks : chemin cible du symlink, puis position
        du cwd sous `projects_root`.
        """
        cwd = (start or Path.cwd()).resolve()

        # 1. cwd directement sous projects_root/clients/<E>/projects/<P> : le plus
        #    spécifique (passe AVANT la remontée, sinon on capte le `.mmi-pm` de
        #    l'outil PM dans lequel `ai-projects` est imbriqué).
        try:
            rel = cwd.relative_to(self.projects_root).parts
            if len(rel) >= 4 and rel[0] == "clients" and rel[2] == "projects":
                return rel[1], rel[3]
        except ValueError:
            pass

        # 2. Remontée cwd + ancêtres à la recherche d'un `.mmi-pm`
        for d in [cwd] + list(cwd.parents):
            mp = d / ".mmi-pm"
            if not mp.exists():
                continue
            # 2a. Lecture de l'overview (marche pour dossier ET symlink suivi)
            ov = mp / "project" / "overview.md"
            if ov.is_file():
                try:
                    m = self._FM_RE.match(ov.read_text(encoding="utf-8"))
                    fm = (yaml.safe_load(m.group(1)) or {}) if m else {}
                    ent, slug = fm.get("client"), fm.get("slug")
                    if ent and slug:
                        return str(ent), str(slug)
                except (OSError, UnicodeDecodeError, yaml.YAMLError):
                    pass
            # 2b. Fallback : symlink hérité → parse du chemin cible
            if mp.is_symlink():
                try:
                    rel = mp.resolve().relative_to(self.projects_root).parts
                    if len(rel) >= 4 and rel[0] == "clients" and rel[2] == "projects":
                        return rel[1], rel[3]
                except (ValueError, OSError):
                    pass
        return None
