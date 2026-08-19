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
    """Charge un fichier .env (KEY=VALUE), sans écraser l'environnement existant.

    Tolère un fichier illisible (`PermissionError`) : un dev NON-admin n'a pas le droit
    de lire le `.env` secret (fallback karl, admin-only) → on l'ignore silencieusement,
    ses propres clés (`~/.config/mmi-pm/.env`) et le `pm.env` d'instance suffisent."""
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except PermissionError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'\"")
        if k and k not in os.environ:
            os.environ[k] = v


def _secrets_env(pm_dir: Path) -> Optional[Path]:
    """`.env` portant secrets + chemins. Celui de `pm_dir` s'il existe (cas runtime
    canonique : pm_dir == `.mmi-pm-core`). Sinon, le `.env` du core pointé par
    `PM_CORE_DIR` (cas d'un CLONE de dev, qui ne porte PAS de secrets — symétrique de
    `PM_DEV_DIR`). `None` si aucun n'est trouvable → erreur explicite dans `load()`."""
    here = pm_dir / ".env"
    if here.is_file():
        return here
    core = os.environ.get("PM_CORE_DIR")
    if core:
        cand = Path(core).expanduser().resolve() / ".env"
        if cand.is_file():
            return cand
    return None


def _user_env() -> Optional[Path]:
    """`.env` de secrets PROPRE à l'utilisateur courant — identité par dev (T1/RM2497).

    Porte la clé API Redmine perso (`REDMINE_API_KEY`) et les tokens forge du dev.
    Il est chargé AVANT le `.env` d'instance et le prime donc (car `_load_env_file`
    n'écrase pas l'existant → priorité : env de session > user > instance).
    Résolution : override `PM_USER_ENV`, sinon `$XDG_CONFIG_HOME/mmi-pm/.env`,
    sinon `~/.config/mmi-pm/.env`. `None` si absent (→ fallback karl, rétrocompat)."""
    override = os.environ.get("PM_USER_ENV")
    if override:
        cand = Path(override).expanduser()
        return cand if cand.is_file() else None
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    cand = base / "mmi-pm" / ".env"
    return cand if cand.is_file() else None


def _instance_env(pm_dir: Path) -> Optional[Path]:
    """`pm.env` d'INSTANCE, NON-secret (URLs Redmine/forge, ids de CF, chemins) —
    group-readable (`640 root:pm`), lisible par tout le groupe `pm` SANS exposer les
    secrets karl (RM2438 T1, scission du `.env` monolithique). Résolution symétrique de
    `_secrets_env` : `pm_dir` sinon `PM_CORE_DIR`. Chargé ENTRE le `.env` user (prime)
    et le `.env` secret (fallback). Absent → no-op : rétrocompat, tout reste dans le
    `.env` monolithique tant qu'on ne l'a pas scindé."""
    here = pm_dir / "pm.env"
    if here.is_file():
        return here
    core = os.environ.get("PM_CORE_DIR")
    if core:
        cand = Path(core).expanduser().resolve() / "pm.env"
        if cand.is_file():
            return cand
    return None


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

    def __init__(self, pm_dir: Path, projects_root: Path, patterns: dict,
                 providers: Optional[dict] = None,
                 conf_dir: Optional[Path] = None,
                 state_dir: Optional[Path] = None,
                 log_dir: Optional[Path] = None):
        self.pm_dir = pm_dir
        self.projects_root = projects_root
        self._patterns = patterns
        # Racines FHS (RM2580) — séparent config / état / logs du code. Défauts
        # = layout actuel si non fournies (conf avec le code, var sous pm_dir) →
        # 0 régression ; un install packagé les surcharge (roots / env).
        self.state_dir = state_dir or (pm_dir / "var")
        self.conf_dir = conf_dir or pm_dir
        self.log_dir = log_dir or (self.state_dir / "log")
        # Registre de providers (RM2542/P0) — section `providers:` de pm.config.yml
        # (servers + defaults). Vide si absente. Consommé par pm_registry.
        self.providers = providers or {}

    @classmethod
    def load(cls, pm_dir: Optional[Path] = None) -> "PMConfig":
        # 1. Auto-détecte le repo PM si non fourni
        if pm_dir is None:
            pm_dir = Path(__file__).resolve().parent.parent
        pm_dir = Path(pm_dir).resolve()

        # 2. Charge la config/secrets, priorité décroissante (premier-écrit-gagne ;
        #    `_load_env_file` n'écrase pas l'existant, os.environ de session prime) :
        #      user  ~/.config/mmi-pm/.env  (identité par dev, RM2497)
        #      inst  pm.env                 (instance, NON-secret, group-readable, RM2438 T1)
        #      secr  .env                   (fallback karl, admin-only, peut être illisible)
        #    Sans user ni pm.env, `.env` monolithique seul → comportement karl inchangé.
        user_env = _user_env()
        if user_env:
            _load_env_file(user_env)
        inst_env = _instance_env(pm_dir)
        if inst_env:
            _load_env_file(inst_env)
        env_file = _secrets_env(pm_dir)
        if env_file:
            _load_env_file(env_file)

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
            if env_file is None:
                sys.exit(
                    f"ERREUR : aucun .env trouvé pour {pm_dir}.\n"
                    "  Normal pour un CLONE de dev : il ne porte pas les secrets "
                    "(ils vivent dans le .env canonique de .mmi-pm-core). Pour exécuter\n"
                    "  un script du système PM, au choix :\n"
                    "    • le lancer depuis le RUNTIME via le symlink "
                    "(ai/project-management/scripts/…) — le .env canonique est résolu ;\n"
                    "    • exporter PM_CORE_DIR=<chemin .mmi-pm-core> (pointe le .env canonique) ;\n"
                    "    • sourcer le .env canonique avant l'appel.\n"
                    "  (cf. NORMS git-mep : split clone-dev / runtime canonique)"
                )
            sys.exit(
                "ERREUR : roots.projects_root non défini "
                "(vérifier $PROJECTS_PATH dans .env ou pm.config.local.yml)"
            )
        projects_root = Path(projects_root_raw).resolve()
        if not projects_root.is_dir():
            sys.exit(f"ERREUR : projects_root introuvable : {projects_root}")

        # Racines FHS (RM2580) — "auto"/absent → défaut relatif au layout actuel
        # (0 régression). Un install packagé surcharge par env (PM_CONF_DIR, …).
        # Ces racines sont des SORTIES (créées à la demande) → pas de is_dir()
        # bloquant, contrairement à projects_root.
        def _root(key: str, default: Path) -> Path:
            raw = _expand_env(roots.get(key, "auto"))
            if not raw or raw == "auto":
                return default
            return Path(raw).expanduser().resolve()
        conf_dir = _root("conf_dir", pm_dir_final)
        state_dir = _root("state_dir", pm_dir_final / "var")
        log_dir = _root("log_dir", state_dir / "log")

        patterns = cfg.get("paths", {}) or {}
        if not patterns:
            sys.exit("ERREUR : pm.config.yml :: paths est vide")

        return cls(pm_dir_final, projects_root, patterns, cfg.get("providers", {}),
                   conf_dir=conf_dir, state_dir=state_dir, log_dir=log_dir)

    # ── Résolution de patterns ──────────────────────────────────────────
    def path(self, key: str, **kwargs) -> Path:
        """Résout un pattern de chemin par sa clé.

        Variables disponibles dans le pattern :
          - `{pm_dir}` `{projects_root}` `{conf_dir}` `{state_dir}` `{log_dir}` : racines
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
            if name == "conf_dir":
                return str(self.conf_dir)
            if name == "state_dir":
                return str(self.state_dir)
            if name == "log_dir":
                return str(self.log_dir)
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

        **Suit les symlinks-vers-dossier** (bascule du résolveur, RM1949) : un
        projet basculé est un symlink `clients/<E>/projects/<P>` → son `.mmi-pm`
        co-localisé ; il doit être yieldé comme un projet réel. Un projet non
        basculé reste un dossier réel. Les deux formes coexistent (bascule
        client par client). **Dédup par cible résolue** : anti double-comptage si
        deux entrées (réelle + symlink, ou deux symlinks) pointent la même cible.
        """
        seen_targets: set = set()
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
                # `is_dir()` suit les symlinks → True pour un symlink→dossier
                if not p.is_dir():
                    continue
                try:
                    target = p.resolve()
                except OSError:
                    continue
                if target in seen_targets:
                    continue
                seen_targets.add(target)
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
            # RM1994 : lecteur central (meta.yml, sinon frontmatter overview)
            fm = self.project_meta(ent_slug, proj_slug)
            rid = (fm.get("redmine") or {}).get("project_id")
            if rid == redmine_project_id:
                ent_path = self.path("entity", entity=ent_slug)
                return ent_path, proj_path
        return None, None

    def resolve_project_ref(
        self, ref, *, require_redmine: bool = False
    ) -> Tuple[str, str, Path]:
        """Résout une référence de projet **non ambiguë** → `(entity, project, path)`.

        RM2430 — fin du match de slug silencieux (plusieurs clients partagent un
        même slug, ex. `infra`). Formes acceptées :
          - `client/slug` (ex. `matnat/infra`) — désambiguïsation explicite ;
          - un `redmine.project_id` unique (ex. `matnat-infra`) ;
          - un slug **non ambigu** (présent chez un seul client).

        Lève `ValueError` si : référence introuvable ; slug nu **ambigu** (message
        listant les candidats) ; ou `require_redmine=True` alors que le projet
        résolu n'a pas de `redmine.project_id` (« pas de projet Redmine précis en
        conf → on n'avance pas »).
        """
        ref = str(ref).strip()

        # 1. Forme explicite « client/slug »
        if "/" in ref:
            ent, slug = ref.split("/", 1)
            for e, p, path in self.iter_projects():
                if e == ent and p == slug:
                    return self._finalize_project_ref(e, p, path, require_redmine)
            raise ValueError(f"projet '{ref}' introuvable (forme client/slug)")

        # 2. redmine.project_id (unique par construction)
        for e, p, path in self.iter_projects():
            rid = (self.project_meta(e, p).get("redmine") or {}).get("project_id")
            if rid and rid == ref:
                return self._finalize_project_ref(e, p, path, require_redmine)

        # 3. slug nu → doit être NON ambigu
        matches = [(e, p, path) for e, p, path in self.iter_projects() if p == ref]
        if len(matches) == 1:
            return self._finalize_project_ref(*matches[0], require_redmine)
        if len(matches) > 1:
            cands = []
            for e, p, _ in matches:
                rid = (self.project_meta(e, p).get("redmine") or {}).get("project_id")
                cands.append(f"{e}/{p}" + (f" ({rid})" if rid else ""))
            raise ValueError(
                f"référence de projet ambiguë : le slug '{ref}' existe chez "
                f"plusieurs clients. Précise `client/slug` ou le `redmine.project_id`. "
                f"Candidats : {', '.join(sorted(cands))}"
            )
        raise ValueError(f"projet '{ref}' introuvable")

    def _finalize_project_ref(
        self, ent: str, proj: str, path: Path, require_redmine: bool
    ) -> Tuple[str, str, Path]:
        if require_redmine:
            rid = (self.project_meta(ent, proj).get("redmine") or {}).get("project_id")
            if not rid:
                raise ValueError(
                    f"projet '{ent}/{proj}' sans `redmine.project_id` en conf "
                    f"(meta.yml) — opération Redmine bloquée (RM2430 : pas de "
                    f"projet Redmine précis → on n'avance pas)."
                )
        return ent, proj, path

    def detect_project_from_cwd(
        self, start: Optional[Path] = None
    ) -> Optional[Tuple[str, str]]:
        """Détecte (entity, project) depuis le cwd (ou `start`) — source unique.

        Mécanisme **indépendant de la forme de `.mmi-pm`** (symlink hérité OU
        dossier co-localisé, RM1942) : on lit le manifeste du projet — `meta.yml`
        (RM1994), sinon frontmatter d'`overview.md` (shim pré-migration) — et on
        en extrait `client` + `slug`. Fallbacks : chemin cible du symlink, puis
        position du cwd sous `projects_root`.
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
            # 2a. Manifeste du projet (meta.yml RM1994, sinon frontmatter overview —
            #     marche pour dossier co-localisé ET symlink suivi). Ne PAS lire le
            #     frontmatter directement : les projets migrés RM1994 n'en ont plus.
            meta = self._read_meta(mp / "meta.yml", mp / "project" / "overview.md")
            ent, slug = meta.get("client"), meta.get("slug")
            if ent and slug:
                return str(ent), str(slug)
            # 2b. Fallback : symlink hérité → parse du chemin cible
            if mp.is_symlink():
                try:
                    rel = mp.resolve().relative_to(self.projects_root).parts
                    if len(rel) >= 4 and rel[0] == "clients" and rel[2] == "projects":
                        return rel[1], rel[3]
                except (ValueError, OSError):
                    pass
        return None

    # --- Manifeste d'entité (RM1994) : meta.yml séparé, fin du frontmatter-dans-MD ---

    def _read_meta(self, meta_path: Path, overview_path: Path) -> dict:
        """Lit le manifeste machine d'une entité (projet/client).

        Source unique de vérité = `meta.yml` (RM1994). **Shim de migration** : tant que
        `meta.yml` est absent, on retombe sur le frontmatter d'`overview.md` (l'ancienne
        convention). Une fois la migration faite, le frontmatter disparaît et seul
        `meta.yml` subsiste.
        """
        if meta_path.is_file():
            try:
                return yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                return {}
        if overview_path.is_file():
            try:
                m = self._FM_RE.match(overview_path.read_text(encoding="utf-8"))
                return (yaml.safe_load(m.group(1)) or {}) if m else {}
            except (OSError, UnicodeDecodeError, yaml.YAMLError):
                return {}
        return {}

    def project_meta(self, entity, project) -> dict:
        """Métadonnées machine d'un projet (`.mmi-pm/meta.yml`, sinon overview frontmatter)."""
        proj = self.path("project", entity=entity, project=project)
        return self._read_meta(proj / "meta.yml", proj / "project" / "overview.md")

    def client_meta(self, entity) -> dict:
        """Métadonnées machine d'un client (`.mmi-pm-client/meta.yml`, sinon overview frontmatter)."""
        client_dir = self.path("entity_client_dir", entity=entity)  # …/.mmi-pm-client/client (symlink)
        try:
            mmi_client = client_dir.resolve().parent                # …/.mmi-pm-client
        except OSError:
            mmi_client = client_dir.parent
        return self._read_meta(mmi_client / "meta.yml", client_dir / "overview.md")
