#!/usr/bin/env python3
"""karl-agent — superviseur de sessions d'agents karl-pm (backend, RM1771).

Daemon HTTP **stdlib-only** (aucune dépendance hors lib standard : le LXC `dev`
est volontairement bare). Il héberge chaque session d'agent (chef de projet sur
un ticket) dans une **session tmux nommée** `karl-RM<id>`, ce qui donne
gratuitement :
  - la persistance (la session survit à la déconnexion du superviseur) ;
  - la **reprise de main humaine** par `tmux attach -t karl-RM<id>` ;
  - l'injection d'entrée (`send-keys`) et la lecture d'écran (`capture-pane`).

Couche 2 de l'archi 3-couches du système PM (cf. RM1803/RM1669/RM1679).
POC validé dans RM1803 (claude piloté de bout en bout dans un tmux).

──────────────────────────────────────────────────────────────────────────────
SÉCURITÉ
  - Le serveur bind **127.0.0.1 EN DUR** (jamais d'écoute publique — invariant
    d'acceptation RM1771). L'exposition vers le conteneur `mmi` passe par un
    tunnel SSH reverse (`karl-agent-tunnel.service`), pas par un bind public.
  - `rm_id` est validé `^[0-9]+$` avant toute interpolation dans un nom de session.
  - `/send` utilise `send-keys -l --` (texte **littéral**, aucune interprétation
    de noms de touches), le « Enter » est envoyé séparément.
  - `cwd` est résolu (realpath) et contraint sous les racines autorisées.
  - Pas de commande shell arbitraire fournie par le client : la commande lancée
    vient d'un **template serveur** (`KARL_AGENT_SPAWN_CMD`), sélectionnable via
    `engine` (claude|shell). Le prompt initial est livré par `send-keys` après
    le spawn (jamais concaténé dans la ligne de commande).
  - Token partagé **optionnel** `X-Karl-Token` (env `KARL_AGENT_TOKEN`) :
    défense en profondeur côté `mmi` où le tunnel expose le port sur localhost.
  - Auth **Basic user/mdp optionnelle** (env `KARL_WEB_USER`/`KARL_WEB_PASS`,
    RM2139) : v1 simple avant le SSO GitLab (RM1845). Configurée ⇒ toutes les
    routes (y compris `/` et `/cockpit-config`) exigent Basic ou token — requis
    dès que le cockpit est exposé au-delà du bridge local (karl.iprospective.fr).

──────────────────────────────────────────────────────────────────────────────
API (JSON, localhost:9876)
  GET  /                        → text/html (cockpit web, RM1873)
  GET  /cockpit-config          → {ttyd_base, auth_required, monitors, layouts, task_types, priorities,
                                   engines, models}  (public en mode token seul ;
                                   gated dès que Basic est configuré, RM2139 ;
                                   models = clés du catalogue par moteur, RM1941)
  GET  /health                  → {status, sessions, tmux}
  GET  /sessions[?engine=&client=&project=]
                                → [{rm_id, tmux, created, attached, engine?,
                                   session_id?, client?, project?}]  (RM1939)
  GET  /resumable[?engine=&client=&project=&status=wip|done&q=&limit=]
                                → sessions REPRENABLES découvertes dans les
                                  stores claude (titre [WIP]/[DONE] de
                                  /session-mark, cwd→projet via .mmi-pm,
                                  tickets liés via l'index local)  (RM1939)
  POST /resume {session_id?, rm_id?, n?, prompt?}
                                → relance `claude --resume <sid>` dans un tmux
                                  karl-RM<id> neuf, au cwd de la session ;
                                  écrit la jonction ticket⇄session  (RM1939)
  GET  /resolve/<rm_id>         → métadonnées riches (type, phase, %, git, envs, docs,
                                   description, log…) depuis le MD local (RM1893 §1)
  GET  /workspace-status/<rm_id>→ git du workspace (branche, dirty, ahead/behind) — intérim RM1883
  GET  /file?path=<rel>         → text/plain (doc .md sous projects/, lecture seule)
  GET  /tickets/search?q=&…     → {results:[…]}  (recherche MD locaux, RM1893 §7)
  GET  /projects                → {projects:[{client, project, value}]}  (RM1893 §8)
  POST /tickets {title, type, priority, project, description?, tags?}
                                → {created, rm_id}  (wrappe pm-task-add, RM1893 §8)
  POST /spawn  {rm_id, cwd?, engine?, model?, prompt?, width?, height?}
                                → {rm_id, tmux, model, model_source, created:true}
                                  model : "" = défaut moteur · "ticket" = frontmatter
                                  ai_model (cascade tâche→projet) · clé du catalogue
                                  serveur (cockpit/models.json, RM1941)
  POST /send   {rm_id, msg, enter?=true}
                                → {rm_id, sent:true}
  GET  /capture/<rm_id>[?lines=N]
                                → text/plain (snapshot du pane, + historique)
  GET  /stream/<rm_id>          → text/event-stream (SSE, tail du pipe-pane)
  POST /monitor   {rm_id, preset, orientation?} → split-window moniteur (RM1893 §3)
  POST /unmonitor {rm_id}                        → ferme le pane moniteur actif/dernier
  POST /layout    {rm_id, layout}                → réarrange les panes (RM1893 §3)
  POST /kill   {rm_id}          → {rm_id, killed:true}

Lancement :
    python3 scripts/karl-agent.py            # bind 127.0.0.1:9876
    KARL_AGENT_PORT=9999 python3 scripts/karl-agent.py
"""
import base64
import hmac
import json
import os
import re
import shlex
import uuid
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# ── Config (env, avec chargement .env léger pour rester stdlib-only) ──────────
REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    """Charge un .env minimal (KEY=VALUE), sans écraser l'env existant."""
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


_load_env_file(REPO_ROOT / ".env")

# Bind localhost EN DUR — ne JAMAIS rendre configurable vers une adresse publique.
HOST = "127.0.0.1"
PORT = int(os.environ.get("KARL_AGENT_PORT", "9876"))

SESSION_PREFIX = "karl-RM"
_RM_ID_RE = re.compile(r"^\d+$")

# Racines autorisées pour le cwd d'une session (anti-évasion de répertoire).
ALLOWED_ROOTS = [
    Path(p).resolve()
    for p in os.environ.get("KARL_AGENT_ALLOWED_ROOTS", "/zfs/workspaces").split(":")
    if p.strip()
]
DEFAULT_CWD = os.environ.get("KARL_AGENT_DEFAULT_CWD", str(REPO_ROOT))

# Templates de moteur. {cwd} déjà validé ; jamais d'entrée client brute ici.
# Chaque moteur : `cmd` (ligne lancée par tmux) + `ready_markers` (sous-chaînes dont
# l'apparition dans le pane signale « TUI prêt à recevoir le prompt » ; vide = pas
# d'attente, simple délai). Le prompt initial est TOUJOURS livré par send-keys APRÈS
# le spawn (jamais concaténé dans la cmd — invariant sécu #4 : pas d'entrée client en
# argv), bien qu'opencode/vibe sachent le prendre à l'invocation.
ENGINES = {
    "claude": {
        "cmd": os.environ.get("KARL_AGENT_SPAWN_CMD", "claude"),
        "ready_markers": ("for shortcuts", "accept edits", "for agents", "❯"),
        "model_flag": "--model",
    },
    "opencode": {
        "cmd": os.environ.get("KARL_AGENT_OPENCODE_CMD", "opencode"),
        "ready_markers": ("Ask anything", "tab agents", "ctrl+p commands"),
        "model_flag": "--model",          # format provider/model
    },
    "vibe": {
        # --trust : confie le cwd (déjà realpath-é sous les racines autorisées) pour
        # cette invocation, sinon le TUI bloque sur l'invite de confiance du dossier.
        "cmd": os.environ.get("KARL_AGENT_VIBE_CMD", "vibe --trust"),
        # « Type /help » n'apparaît que sur le TUI prêt — PAS sur l'écran d'onboarding
        # première-exécution (« Welcome to Mistral Vibe »), qui matcherait un marqueur
        # « Mistral Vibe » trop lâche et ferait injecter le prompt dans le wizard.
        "ready_markers": ("Type /help",),
        # vibe n'a pas de flag modèle : override par env du champ active_model
        # du ~/.vibe/config.toml (le modèle doit y être déclaré dans [[models]]).
        "model_env": "VIBE_ACTIVE_MODEL",
    },
    "shell": {
        "cmd": "bash -l",
        "ready_markers": (),
    },
}
DEFAULT_ENGINE = os.environ.get("KARL_AGENT_DEFAULT_ENGINE", "claude")

# Catalogue des modèles par moteur (RM1941). Même modèle de sécurité que les
# moniteurs : le client envoie une CLÉ de ce catalogue, jamais une valeur brute ;
# le serveur mappe vers la valeur réelle (flag ou env selon le moteur). Valeurs
# spéciales côté client : "" = défaut du moteur, "ticket" = prescrit par le
# frontmatter de la tâche (`ai_model`, cascade tâche → overview projet).
# Surchargeable via cockpit/models.json : {"<engine>": {"clé": "valeur", …}}.
_DEFAULT_MODELS = {
    "claude": {
        "opus": "opus",
        "sonnet": "sonnet",
        "haiku": "haiku",
    },
    "opencode": {
        "claude-opus": "anthropic/claude-opus-4-8",
        "claude-sonnet": "anthropic/claude-sonnet-4-6",
        "deepseek": "ollama-cloud/deepseek-v4-pro",
        "deepseek-free": "opencode/deepseek-v4-flash-free",
        "qwen-coder": "ollama-cloud/qwen3-coder-next",
    },
    "vibe": {
        "mistral-medium": "mistral-medium-3.5",
        "vibe-cli": "mistral-vibe-cli-latest",
        "devstral-small": "devstral-small-latest",
        "devstral-local": "devstral",
    },
}

# Garde sur les valeurs de modèle issues du frontmatter (`ai_model`) : ce sont des
# données du repo (pas du client HTTP), mais on refuse quand même tout ce qui ne
# ressemble pas à un identifiant de modèle avant interpolation dans la commande.
_MODEL_VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


def _model_catalog() -> dict:
    """Catalogue effectif des modèles par moteur (cockpit/models.json sinon défauts)."""
    f = COCKPIT_DIR / "models.json"
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and all(
                isinstance(v, dict) and all(isinstance(x, str) for x in v.values())
                for v in data.values()
            ):
                return data
        except (ValueError, OSError):
            pass
    return _DEFAULT_MODELS
DEFAULT_WIDTH = int(os.environ.get("KARL_AGENT_WIDTH", "200"))
DEFAULT_HEIGHT = int(os.environ.get("KARL_AGENT_HEIGHT", "50"))

# Répertoire des logs pipe-pane (alimente /stream et /capture étendu).
LOG_DIR = Path(
    os.environ.get("KARL_AGENT_LOG_DIR")
    or (Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")) / "karl-agent")
)

# ── Store sessions ⇄ tickets (RM1939) — instance-local, JAMAIS committé ──────
# Modèle n-m : une session traverse plusieurs tickets, un ticket est repris dans
# plusieurs sessions. Deux dimensions + jonction :
#   sessions/<engine>/<session_id>.json      entité SESSION (projet-agnostique)
#   tasks/<client>/<projet>/RM<id>-<n>.json  jonction (n = occurrence, max+1)
# Un session-id n'a de sens que sur CETTE machine (fédération : jamais en git).
SESS_DIR = LOG_DIR / "sessions"
RUNS_DIR = LOG_DIR / "tasks"
# Stores claude scannés pour la DÉCOUVERTE des sessions reprenables (l'historique
# reste chez le moteur ; karl-agent n'en garde qu'un index). Multi-racines ':' —
# permet de monter le store d'une autre machine en lecture (listing seulement :
# le resume natif exige le transcript dans le store du user qui lance claude).
CLAUDE_STORES = [
    Path(p).expanduser()
    for p in os.environ.get(
        "KARL_AGENT_CLAUDE_STORES", str(Path.home() / ".claude" / "projects")
    ).split(":")
    if p.strip()
]

AUTH_TOKEN = os.environ.get("KARL_AGENT_TOKEN") or None  # optionnel
# Auth Basic user/mdp (RM2139) — v1 simple avant le SSO GitLab (RM1845).
# Posés dans le .env du core. Dès que le couple est configuré, TOUTES les routes
# exigent une auth (y compris / et /cockpit-config) : le cockpit est joignable
# au-delà du bridge local via le tunnel mmi + vhost karl.iprospective.fr, donc
# plus aucune route « publique ». X-Karl-Token reste accepté en alternative
# pour les clients API non-navigateur.
BASIC_USER = os.environ.get("KARL_WEB_USER") or None
BASIC_PASS = os.environ.get("KARL_WEB_PASS") or None

# Cockpit web v0 (RM1873) — UI servie en MÊME ORIGINE que l'API (pas de CORS).
COCKPIT_DIR = REPO_ROOT / "deploy" / "karl-agent" / "cockpit"
# Base URL du terminal web ttyd. Vide → le client la calcule (location.hostname:7681).
TTYD_URL = os.environ.get("KARL_AGENT_TTYD_URL", "")


# ── Helpers tmux ─────────────────────────────────────────────────────────────
def _tmux(*args, timeout=10):
    """Exécute tmux et renvoie (rc, stdout, stderr)."""
    p = subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def _session_name(rm_id: str) -> str:
    return f"{SESSION_PREFIX}{rm_id}"


def _has_session(rm_id: str) -> bool:
    rc, _, _ = _tmux("has-session", "-t", _session_name(rm_id))
    return rc == 0


def _log_path(rm_id: str) -> Path:
    return LOG_DIR / f"{_session_name(rm_id)}.log"


def _list_sessions():
    rc, out, _ = _tmux(
        "list-sessions", "-F",
        "#{session_name}\t#{session_created}\t#{session_attached}",
    )
    if rc != 0:
        return []  # pas de serveur tmux = aucune session
    sessions = []
    for line in out.splitlines():
        parts = line.split("\t")
        name = parts[0]
        if not name.startswith(SESSION_PREFIX):
            continue
        sessions.append({
            "rm_id": name[len(SESSION_PREFIX):],
            "tmux": name,
            "created": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None,
            "attached": (len(parts) > 2 and parts[2] == "1"),
        })
    return sessions


def _resolve_cwd(cwd: str | None) -> Path:
    """Résout et contraint le cwd sous une racine autorisée."""
    target = Path(cwd).resolve() if cwd else Path(DEFAULT_CWD).resolve()
    if not target.is_dir():
        raise ValueError(f"cwd inexistant ou non répertoire : {target}")
    if not any(target == r or r in target.parents for r in ALLOWED_ROOTS):
        raise ValueError(f"cwd hors des racines autorisées ({ALLOWED_ROOTS}) : {target}")
    return target


# ── Opérations métier ────────────────────────────────────────────────────────
class ApiError(Exception):
    def __init__(self, code: int, msg: str):
        self.code, self.msg = code, msg
        super().__init__(msg)


def _require_rm_id(payload: dict) -> str:
    rm_id = str(payload.get("rm_id", "")).strip()
    if not _RM_ID_RE.match(rm_id):
        raise ApiError(400, "rm_id requis, entier (^\\d+$)")
    return rm_id


def _wait_engine_ready(rm_id: str, engine: str, timeout: float = 8.0) -> None:
    """Attend que le TUI du moteur soit prêt à recevoir une entrée, avant
    d'injecter le prompt initial. Sans ça, les touches envoyées trop tôt partent
    dans le vide pendant le splash de démarrage (course observée sur claude, RM1873).
    Best-effort : rend la main dès qu'un marqueur d'invite apparaît, ou au timeout."""
    # Marqueurs propres au moteur (cf. ENGINES). Vide (ex. shell) → pas d'attente.
    markers = ENGINES.get(engine, {}).get("ready_markers", ())
    if not markers:
        time.sleep(0.3)
        return
    name = _session_name(rm_id)
    deadline = time.time() + timeout
    while time.time() < deadline:
        rc, out, _ = _tmux("capture-pane", "-p", "-t", name)
        if rc == 0 and any(m in out for m in markers):
            return
        time.sleep(0.3)


def _ticket_model(rm_id: str) -> str | None:
    """Modèle prescrit par le ticket (RM1941) : frontmatter `ai_model` de la tâche,
    sinon celui de l'overview du projet (cascade projet → tâche, le plus précis
    gagne). None si rien de prescrit → défaut du moteur. La valeur est la valeur
    NATIVE du moteur visé (alias claude, provider/model opencode, nom [[models]]
    vibe) — c'est l'auteur du ticket qui la choisit en connaissant le moteur."""
    tf = _find_task_file(rm_id)
    if not tf:
        return None
    mmi = tf.parent.parent  # dossier .mmi-pm
    try:
        import yaml as _yaml
    except ImportError:
        _yaml = None
    # Cascade (le plus précis gagne) : tâche (frontmatter) → manifeste projet
    # meta.yml (RM1994, YAML pur) → overview.md (fallback frontmatter pendant la migration).
    candidates = [(tf, "fm"), (mmi / "meta.yml", "yaml"),
                  (mmi / "project" / "overview.md", "fm")]
    for f, kind in candidates:
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if kind == "yaml":
            fm = (_yaml.safe_load(text) or {}) if _yaml else {}
        else:
            fm = _parse_frontmatter(text)
        v = fm.get("ai_model")
        if isinstance(v, str) and v.strip():
            v = v.strip()
            if not _MODEL_VALUE_RE.match(v):
                raise ApiError(400, f"ai_model invalide dans {f.name} : {v!r}")
            return v
    return None


def op_spawn(payload: dict) -> dict:
    rm_id = _require_rm_id(payload)
    if _has_session(rm_id):
        raise ApiError(409, f"session déjà active : {_session_name(rm_id)}")

    engine = payload.get("engine", DEFAULT_ENGINE)
    if engine not in ENGINES:
        raise ApiError(400, f"engine inconnu : {engine} (connus : {list(ENGINES)})")
    cmd = ENGINES[engine]["cmd"]

    # Modèle (RM1941) : "" = défaut moteur ; "ticket" = frontmatter `ai_model` ;
    # sinon une CLÉ du catalogue serveur (jamais une valeur brute client).
    model_key = str(payload.get("model") or "").strip()
    model_value, model_source = None, "default"
    if model_key == "ticket":
        model_value = _ticket_model(rm_id)
        model_source = "ticket" if model_value else "default"
    elif model_key:
        cat = _model_catalog().get(engine, {})
        if model_key not in cat:
            raise ApiError(400, f"modèle inconnu pour {engine} : {model_key} (connus : {list(cat)})")
        model_value, model_source = cat[model_key], "catalogue"
    env_extra = []
    if model_value:
        if "model_flag" in ENGINES[engine]:
            cmd = f"{cmd} {ENGINES[engine]['model_flag']} {shlex.quote(model_value)}"
        elif "model_env" in ENGINES[engine]:
            env_extra = ["-e", f"{ENGINES[engine]['model_env']}={model_value}"]
        elif model_key == "ticket":
            # moteur sans choix de modèle (shell…) : la prescription du ticket est
            # ignorée silencieusement — la sentinelle doit rester un choix sûr.
            model_value, model_source = None, "default"
        else:
            raise ApiError(400, f"le moteur {engine} ne supporte pas le choix de modèle")

    try:
        cwd = _resolve_cwd(payload.get("cwd"))
    except ValueError as e:
        raise ApiError(400, str(e))

    # RM1939 : pour claude, on FIXE le session-id au lancement → index de reprise
    # écrit immédiatement, sans découverte. Autres moteurs : itération suivante
    # (pas de set-at-launch → capture différée du session-id).
    session_id = None
    if engine == "claude":
        session_id = str(uuid.uuid4())
        cmd = f"{cmd} --session-id {session_id}"

    width = int(payload.get("width", DEFAULT_WIDTH))
    height = int(payload.get("height", DEFAULT_HEIGHT))
    name = _session_name(rm_id)

    _start_session_tmux(rm_id, cmd, cwd, width, height, env_extra)
    if session_id:
        _record_run(rm_id, engine, session_id, str(cwd))

    # Prompt initial éventuel, livré par send-keys (jamais dans la cmd). On attend
    # que le TUI soit prêt, puis on sépare texte et Enter (claude debounce parfois
    # la soumission si les deux arrivent collés sur un TUI à peine initialisé).
    prompt = payload.get("prompt")
    if prompt:
        _wait_engine_ready(rm_id, engine)
        op_send({"rm_id": rm_id, "msg": prompt, "enter": False})
        time.sleep(0.3)
        _tmux("send-keys", "-t", name, "Enter")

    return {"rm_id": rm_id, "tmux": name, "engine": engine, "cwd": str(cwd),
            "model": model_value, "model_source": model_source,
            "session_id": session_id, "created": True}


def _start_session_tmux(rm_id: str, cmd: str, cwd, width: int, height: int,
                        env_extra: list) -> None:
    """Démarre la session tmux karl-RM<id> + plomberie commune (spawn ET resume)."""
    name = _session_name(rm_id)
    rc, _, err = _tmux(
        "new-session", "-d", "-s", name,
        "-x", str(width), "-y", str(height),
        *env_extra,
        "-c", str(cwd), cmd,
    )
    if rc != 0:
        raise ApiError(500, f"tmux new-session a échoué : {err.strip()}")

    # pipe-pane : capture continue du pane vers un log (alimente /stream).
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logf = _log_path(rm_id)
    _tmux("pipe-pane", "-o", "-t", name, f"cat >> {shlex.quote(str(logf))}")

    # Marque le pane de l'agent (seul pane à ce stade) → /unmonitor le protège.
    _tmux("set-option", "-p", "-t", name, "@karl_agent", "1")

    # Cockpit (RM1873) : rendre le terminal web scrollable. Sans `mouse on`, la
    # molette ne scrolle pas l'historique du pane une fois attaché via ttyd.
    # Options globales du serveur tmux (dédié aux sessions karl-*). `history-limit`
    # ne s'applique qu'aux panes créés APRÈS (donc aux prochaines sessions) ;
    # `mouse on` prend effet immédiatement pour toutes.
    _tmux("set-option", "-g", "mouse", "on")
    _tmux("set-option", "-g", "history-limit", "50000")


def op_send(payload: dict) -> dict:
    rm_id = _require_rm_id(payload)
    if not _has_session(rm_id):
        raise ApiError(404, f"session absente : {_session_name(rm_id)}")
    msg = payload.get("msg")
    if msg is None:
        raise ApiError(400, "msg requis")
    name = _session_name(rm_id)
    # -l : littéral (pas d'interprétation des noms de touches) ; -- : fin d'options.
    rc, _, err = _tmux("send-keys", "-t", name, "-l", "--", str(msg))
    if rc != 0:
        raise ApiError(500, f"send-keys a échoué : {err.strip()}")
    if payload.get("enter", True):
        _tmux("send-keys", "-t", name, "Enter")
    return {"rm_id": rm_id, "sent": True}


def op_capture(rm_id: str, lines: int | None) -> str:
    if not _RM_ID_RE.match(rm_id):
        raise ApiError(400, "rm_id invalide")
    if not _has_session(rm_id):
        raise ApiError(404, f"session absente : {_session_name(rm_id)}")
    name = _session_name(rm_id)
    args = ["capture-pane", "-p", "-t", name]
    if lines:
        args += ["-S", f"-{int(lines)}"]
    rc, out, err = _tmux(*args)
    if rc != 0:
        raise ApiError(500, f"capture-pane a échoué : {err.strip()}")
    return out


def op_kill(payload: dict) -> dict:
    rm_id = _require_rm_id(payload)
    if not _has_session(rm_id):
        raise ApiError(404, f"session absente : {_session_name(rm_id)}")
    rc, _, err = _tmux("kill-session", "-t", _session_name(rm_id))
    if rc != 0:
        raise ApiError(500, f"kill-session a échoué : {err.strip()}")
    return {"rm_id": rm_id, "killed": True}


# ── Sessions ⇄ tickets : store, découverte, reprise (RM1939, itér.1 claude) ──
_SID_RE = re.compile(r"^[0-9a-fA-F][0-9a-fA-F-]{7,63}$")
_MARK_RE = re.compile(r"^\[(WIP|DONE)\]\s*", re.I)


def _write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _read_json_file(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _runs_for_ticket(rm_id: str) -> list:
    """Jonctions RM<id>-<n> du ticket, tous projets, triées par n. Chaque entrée
    porte client/project/_file (déduits du chemin — retirés avant écriture)."""
    runs = []
    for f in RUNS_DIR.glob(f"*/*/RM{rm_id}-*.json"):
        d = _read_json_file(f)
        if d and str(d.get("rm_id")) == rm_id:
            d["client"], d["project"], d["_file"] = f.parent.parent.name, f.parent.name, str(f)
            runs.append(d)
    return sorted(runs, key=lambda d: d.get("n", 0))


def _runs_by_session() -> dict:
    """Index session_id → [jonctions] (scan complet du store, petit par nature)."""
    idx = {}
    for f in RUNS_DIR.glob("*/*/RM*-*.json"):
        d = _read_json_file(f)
        if d and d.get("session_id"):
            d["client"], d["project"], d["_file"] = f.parent.parent.name, f.parent.name, str(f)
            idx.setdefault(d["session_id"], []).append(d)
    return idx


def _record_run(rm_id: str, engine: str, session_id: str, cwd: str) -> dict:
    """Écrit/rafraîchit l'entité session + la jonction. Même couple (ticket,
    session) → jonction réutilisée (un resume ne crée pas d'occurrence) ;
    nouveau couple → n = max existant + 1."""
    now = int(time.time())
    sf = SESS_DIR / engine / f"{session_id}.json"
    meta = _read_json_file(sf) or {"engine": engine, "session_id": session_id, "created": now}
    meta.update({"cwd": cwd, "last_seen": now})
    _write_json_atomic(sf, meta)

    runs = _runs_for_ticket(rm_id)
    same = [r for r in runs if r.get("session_id") == session_id]
    if same:
        run = same[-1]
        run["last_seen"] = now
        rf = Path(run["_file"])
    else:
        run = {"rm_id": rm_id, "n": (max((r.get("n", 0) for r in runs), default=0) + 1),
               "session_id": session_id, "engine": engine, "created": now, "last_seen": now}
        tf = _find_task_file(rm_id)
        client, project = _task_client_project(tf) if tf else ("_", "_")
        rf = RUNS_DIR / client / project / f"RM{rm_id}-{run['n']}.json"
    _write_json_atomic(rf, {k: v for k, v in run.items()
                            if k not in ("client", "project", "_file")})
    return run


# Cache mtime → méta extraite (le scan du store relit seulement ce qui a changé).
_tail_cache: dict = {}


def _jsonl_tail_meta(path: Path, max_bytes: int = 131072) -> dict:
    """Méta d'un transcript claude, extraite de son DERNIER segment (lecture
    bornée : les fichiers font parfois des centaines de Mo) : titre (dernier
    `custom-title`, sinon dernier `ai-title` — même logique que /session-mark),
    cwd et mtime. Le CLI ré-émet son custom-title à chaque tour → il est
    toujours dans la fenêtre de fin."""
    st = path.stat()
    key = str(path)
    hit = _tail_cache.get(key)
    if hit and hit[0] == st.st_mtime:
        return hit[1]
    with path.open("rb") as fh:
        if st.st_size > max_bytes:
            fh.seek(st.st_size - max_bytes)
            fh.readline()  # saute la ligne probablement tronquée
        data = fh.read().decode("utf-8", "replace")
    title = ai_title = cwd = None
    for line in data.splitlines():
        if '"custom-title"' not in line and '"ai-title"' not in line and '"cwd"' not in line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        t = obj.get("type")
        if t == "custom-title" and obj.get("customTitle"):
            title = obj["customTitle"]
        elif t == "ai-title" and obj.get("aiTitle"):
            ai_title = obj["aiTitle"]
        if obj.get("cwd"):
            cwd = obj["cwd"]
    meta = {"title": title or ai_title, "cwd": cwd, "mtime": int(st.st_mtime)}
    _tail_cache[key] = (st.st_mtime, meta)
    return meta


# Index {realpath du dossier .mmi-pm co-localisé → (client, projet)}, reconstruit
# depuis l'arbre PM (dont les entrées clients/<C>/projects/<P> sont des SYMLINKS
# vers les .mmi-pm co-localisés depuis RM1949 — le .mmi-pm d'un workspace est un
# vrai dossier, pas un lien vers l'arbre). Cache 60 s (l'arbre bouge rarement).
_pm_index_cache = {"at": 0.0, "map": {}}


def _pm_projects_index() -> dict:
    now = time.time()
    if now - _pm_index_cache["at"] > 60:
        m = {}
        for pd in PROJECTS_BASE.glob("*/projects/*"):
            try:
                m[str(pd.resolve())] = (pd.parent.parent.name, pd.name)
            except OSError:
                continue
        _pm_index_cache["at"], _pm_index_cache["map"] = now, m
    return _pm_index_cache["map"]


def _pm_project_of_cwd(cwd: str | None):
    """cwd → (client, projet) PM via son `.mmi-pm` (cwd puis parents proches —
    convention : à la racine du workspace ou du dépôt). Gère les deux layouts :
    .mmi-pm co-localisé (canonique RM1949, lookup par l'index inversé) et
    .mmi-pm symlink vers l'arbre PM (pré-bascule, ex. pm-ai-agents)."""
    if not cwd:
        return None, None
    p = Path(cwd)
    for cand in [p, *list(p.parents)[:3]]:
        link = cand / ".mmi-pm"
        try:
            if not (link.is_symlink() or link.is_dir()):
                continue
            target = link.resolve()
            hit = _pm_projects_index().get(str(target))
            if hit:
                return hit
            parts = target.parts
            if "clients" in parts:
                i = parts.index("clients")
                if len(parts) > i + 3 and parts[i + 2] == "projects":
                    return parts[i + 1], parts[i + 3]
        except OSError:
            continue
    return None, None


def op_resumable(qs: dict) -> list:
    """Sessions REPRENABLES découvertes dans les stores claude (+ index local
    pour les tickets liés). Filtres : engine, client, project,
    status (wip|done — marqueurs [WIP]/[DONE] posés par /session-mark), q."""
    f_engine = qs.get("engine") or None
    f_client = qs.get("client") or None
    f_project = qs.get("project") or None
    f_status = (qs.get("status") or "").lower() or None
    f_q = (qs.get("q") or "").lower() or None
    limit = max(1, min(int(qs.get("limit") or 100), 500))

    if f_engine not in (None, "claude"):
        return []  # itération 1 : découverte claude uniquement
    runs_idx = _runs_by_session()
    live_rm = {s["rm_id"] for s in _list_sessions()}
    out, seen = [], set()
    for root in CLAUDE_STORES:
        if not root.is_dir():
            continue
        for jf in root.glob("*/*.jsonl"):
            sid = jf.stem
            if sid in seen or not _SID_RE.match(sid):
                continue
            seen.add(sid)
            try:
                meta = _jsonl_tail_meta(jf)
            except OSError:
                continue
            raw_title = meta["title"] or ""
            m = _MARK_RE.match(raw_title)
            runs = runs_idx.get(sid, [])
            client, project = _pm_project_of_cwd(meta["cwd"])
            if not client and runs:
                client, project = runs[-1]["client"], runs[-1]["project"]
            out.append({
                "engine": "claude", "session_id": sid,
                "title": _MARK_RE.sub("", raw_title) or None,
                "mark": m.group(1).lower() if m else None,
                "cwd": meta["cwd"], "mtime": meta["mtime"],
                "client": client, "project": project,
                "tickets": [{"rm_id": r["rm_id"], "n": r.get("n")} for r in runs],
                "live": any(r["rm_id"] in live_rm for r in runs),
            })

    def keep(e):
        if f_status and e["mark"] != f_status:
            return False
        if f_client and e["client"] != f_client:
            return False
        if f_project and e["project"] != f_project:
            return False
        if f_q and f_q not in (e["title"] or "").lower():
            return False
        return True

    out = [e for e in out if keep(e)]
    out.sort(key=lambda e: e["mtime"], reverse=True)
    return out[:limit]


def op_resume(payload: dict) -> dict:
    """Reprend une conversation TERMINÉE côté process (tmux mort) via le resume
    natif du moteur, dans une session tmux karl-RM<id> neuve. Cible : session_id
    direct, ou rm_id (+ n) → jonction la plus récente. Itération 1 : claude."""
    engine = payload.get("engine", "claude")
    session_id = str(payload.get("session_id") or "").strip() or None
    rm_id = str(payload.get("rm_id") or "").strip() or None
    n = payload.get("n")
    if session_id and not _SID_RE.match(session_id):
        raise ApiError(400, "session_id invalide")
    if rm_id and not _RM_ID_RE.match(rm_id):
        raise ApiError(400, "rm_id invalide")

    if not session_id:
        if not rm_id:
            raise ApiError(400, "session_id ou rm_id requis")
        runs = _runs_for_ticket(rm_id)
        if n is not None:
            runs = [r for r in runs if r.get("n") == int(n)]
        if not runs:
            raise ApiError(404, f"aucune session connue pour RM{rm_id}"
                                + (f" (n={n})" if n is not None else "")
                                + " — lancer un spawn neuf")
        last = max(runs, key=lambda r: r.get("last_seen", r.get("created", 0)))
        session_id, engine = last["session_id"], last.get("engine", engine)
    if engine != "claude":
        raise ApiError(501, f"resume : itération 1 = claude uniquement (session {engine})")

    if not rm_id:
        # Le tmux est nommé karl-RM<id> (mono-session vivante, invariant RM1771) :
        # une session jamais liée à un ticket doit être reprise AVEC un rm_id.
        runs = _runs_by_session().get(session_id, [])
        if not runs:
            raise ApiError(400, "rm_id requis : session encore liée à aucun ticket "
                                "(le tmux de reprise est nommé karl-RM<id>)")
        rm_id = max(runs, key=lambda r: r.get("last_seen", r.get("created", 0)))["rm_id"]

    if _has_session(rm_id):
        raise ApiError(409, f"session déjà active : {_session_name(rm_id)}")

    # Garde-fous : transcript présent ? cwd toujours valide ?
    jf = next((p for root in CLAUDE_STORES for p in root.glob(f"*/{session_id}.jsonl")), None)
    if jf is None:
        raise ApiError(410, f"transcript introuvable pour {session_id} "
                            "(session purgée ou store non monté) — lancer un spawn neuf")
    smeta = _read_json_file(SESS_DIR / engine / f"{session_id}.json") or {}
    try:
        cwd = _resolve_cwd(smeta.get("cwd") or _jsonl_tail_meta(jf)["cwd"])
    except (ValueError, TypeError) as e:
        raise ApiError(410, f"cwd de la session invalide ({e}) — lancer un spawn neuf")

    cmd = f"{ENGINES['claude']['cmd']} --resume {shlex.quote(session_id)}"
    width = int(payload.get("width", DEFAULT_WIDTH))
    height = int(payload.get("height", DEFAULT_HEIGHT))
    _start_session_tmux(rm_id, cmd, cwd, width, height, [])
    _record_run(rm_id, "claude", session_id, str(cwd))

    prompt = payload.get("prompt")
    if prompt:
        _wait_engine_ready(rm_id, "claude")
        op_send({"rm_id": rm_id, "msg": prompt, "enter": False})
        time.sleep(0.3)
        _tmux("send-keys", "-t", _session_name(rm_id), "Enter")

    return {"rm_id": rm_id, "tmux": _session_name(rm_id), "engine": "claude",
            "session_id": session_id, "cwd": str(cwd), "resumed": True}


# État heuristique d'une session (RM2140) — INTÉRIM avant le bus de hooks
# (RM1874) qui donnera les états exacts working/blocked/idle. Lecture du tail
# du pane :
#   attention : dialogue de permission / question qui BLOQUE l'agent ;
#   working   : le moteur produit (claude affiche « esc to interrupt ») ;
#   idle      : invite au repos (tour fini, ou en attente d'une consigne).
_ATTENTION_MARKERS = ("Do you want", "Would you like", "(y/n)", "❯ 1.", "│ 1. Yes")
_WORKING_MARKERS = ("esc to interrupt", "ctrl+b to run in background", "Compacting")


def _session_state(rm_id: str, engine) -> str:
    rc, out, _ = _tmux("capture-pane", "-p", "-t", _session_name(rm_id))
    if rc != 0:
        return "idle"
    tail = "\n".join(out.rstrip().splitlines()[-15:])
    if any(m in tail for m in _ATTENTION_MARKERS):
        return "attention"
    if any(m in tail for m in _WORKING_MARKERS):
        return "working"
    if engine not in (None, "claude"):
        # moteurs sans marqueurs fiables : âge de la dernière sortie (pipe-pane)
        try:
            if time.time() - _log_path(rm_id).stat().st_mtime < 15:
                return "working"
        except OSError:
            pass
    return "idle"


def _sessions_view(qs: dict) -> list:
    """Sessions tmux vivantes, enrichies (moteur, session_id, client/projet via
    la jonction la plus récente, état heuristique RM2140) + filtres
    engine/client/project (RM1939)."""
    sessions = _list_sessions()
    if not sessions:
        return []
    latest = {}
    for runs in _runs_by_session().values():
        for r in runs:
            cur = latest.get(r["rm_id"])
            if not cur or r.get("last_seen", 0) > cur.get("last_seen", 0):
                latest[r["rm_id"]] = r
    for s in sessions:
        r = latest.get(s["rm_id"])
        if r:
            s["engine"] = r.get("engine")
            s["session_id"] = r.get("session_id")
            if r.get("client") != "_":
                s["client"], s["project"] = r.get("client"), r.get("project")
        s["state"] = _session_state(s["rm_id"], s.get("engine"))

    f_engine, f_client, f_project = qs.get("engine"), qs.get("client"), qs.get("project")

    def keep(s):
        if f_engine and s.get("engine") != f_engine:
            return False
        if f_client and s.get("client") != f_client:
            return False
        if f_project and s.get("project") != f_project:
            return False
        return True

    return [s for s in sessions if keep(s)]


# ── Tickets PM locaux : résolution + recherche (RM1893 §1, §7) ────────────────
# Lecture des MD de tâches synchronisés en local. Stdlib-only (pas d'import des
# modules du repo, pour rester runnable sur un dev bare). Aucun credential : tout
# vient du filesystem. Arbo : projects/clients/<C>/projects/<P>/tasks/RM<id>_*.md
PROJECTS_BASE = REPO_ROOT / "projects" / "clients"
_TASK_GLOB = "*/projects/*/tasks/RM{}_*.md"
LAYOUTS = {"even-horizontal", "even-vertical", "main-vertical", "main-horizontal", "tiled"}


_NULLISH = {"null", "~", "", "None"}


def _scalar(line: str) -> str:
    v = line.split(":", 1)[1].strip().strip("'\"")
    return "" if v in _NULLISH else v


def _read_task_meta(path: Path) -> dict:
    """Lecture minimale du frontmatter d'un fichier de tâche (sans dépendance YAML).
    Retourne {title, status, priority, type, test_url, target_env, tags:[...]}."""
    meta = {"title": "", "status": "", "priority": "", "type": "",
            "test_url": "", "target_env": "", "tags": []}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return meta
    if not text.startswith("---"):
        return meta
    end = text.find("\n---", 3)
    fm = text[3:end] if end != -1 else text
    in_tags = False
    for line in fm.splitlines():
        if in_tags:
            s = line.strip()
            if s.startswith("- "):
                meta["tags"].append(s[2:].strip().strip("'\""))
                continue
            in_tags = False
        if line.startswith("title:"):
            meta["title"] = _scalar(line)
        elif line.startswith("status:"):
            meta["status"] = _scalar(line)
        elif line.startswith("priority:"):
            meta["priority"] = _scalar(line)
        elif line.startswith("type:"):
            meta["type"] = _scalar(line)
        elif line.startswith("test_url:"):
            meta["test_url"] = _scalar(line)
        elif line.startswith("target_env:"):
            meta["target_env"] = _scalar(line)
        elif line.startswith("tags:"):
            in_tags = True
    return meta


def _read_project_envs(project_dir: Path) -> list:
    """Liste [{name, url}] des environnements d'un projet, lue depuis
    `<project>/project/environments.md` (bloc `environments:` du frontmatter).
    Parse ciblé (pas de dépendance YAML), borné au bloc pour ne pas attraper
    `env_vars:`."""
    f = project_dir / "project" / "environments.md"
    try:
        text = f.read_text(encoding="utf-8")
    except OSError:
        return []
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    fm = text[3:end] if end != -1 else text
    envs, cur, in_block = [], None, False
    for line in fm.splitlines():
        if re.match(r"^environments:\s*$", line):
            in_block = True
            continue
        if in_block and re.match(r"^\S", line):   # autre clé top-level → fin du bloc
            break
        if not in_block:
            continue
        s = line.strip()
        m = re.match(r"-\s+name:\s*(.+)", s)
        if m:
            if cur:
                envs.append(cur)
            cur = {"name": m.group(1).strip().strip("'\""), "url": ""}
            continue
        if cur is not None:
            mu = re.match(r"url:\s*(.+)", s)
            if mu:
                u = mu.group(1).strip().strip("'\"")
                cur["url"] = "" if u in _NULLISH else u
    if cur:
        envs.append(cur)
    return envs


# Phase (statut NORMS) → rôle d'environnement, pour proposer le « lien env actif ».
_STATUS_ENV_ROLE = {
    "a_tester_demandeur": "staging", "a_mep": "staging", "en_mep": "staging",
    "ferme": "prod",
}
_ENV_ROLE_KEYS = {
    "dev": ["dev"],
    "staging": ["staging", "preprod", "recette", "test"],
    "prod": ["prod", "production", "live"],
}


def _env_for_status(status: str, envs: list):
    """Choisit l'env pertinent pour la phase courante (heuristique). None si vide."""
    if not envs:
        return None
    role = _STATUS_ENV_ROLE.get(status, "dev")
    keys = _ENV_ROLE_KEYS.get(role, [role])
    for e in envs:
        if any(k in e["name"].lower() for k in keys):
            return e
    return envs[-1] if role == "prod" else envs[0]


def _task_client_project(tf: Path):
    """De .../clients/<C>/projects/<P>/tasks/RMx_*.md → (client, project)."""
    return tf.parent.parent.parent.parent.name, tf.parent.parent.name


def _find_task_file(rm_id: str):
    # Exclure les .log.md (même préfixe RM<id>_, mais pas de frontmatter).
    matches = sorted(p for p in PROJECTS_BASE.glob(_TASK_GLOB.format(rm_id))
                     if not p.name.endswith(".log.md"))
    return matches[0] if matches else None


def _resolve_workspace(project_dir: Path):
    """Trouve le workspace de code dont le symlink `.mmi-pm` pointe vers ce projet
    PM (scan superficiel des racines autorisées). None si aucun → cwd = repo PM."""
    target = project_dir.resolve()
    for root in ALLOWED_ROOTS:
        if not root.is_dir():
            continue
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            link = entry / ".mmi-pm"
            try:
                if link.is_symlink() and link.resolve() == target:
                    return entry
            except OSError:
                continue
    return None


def _parse_frontmatter(text: str) -> dict:
    """Frontmatter complet en dict via PyYAML si dispo (présent sur dev car requis
    par les scripts PM), sinon {} → on retombe sur le mini-parser scalaire."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        import yaml
        d = yaml.safe_load(text[3:end])
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _task_body(text: str) -> str:
    """Corps Markdown (description) après le frontmatter."""
    if not text.startswith("---"):
        return text.strip()
    end = text.find("\n---", 3)
    return text[end + 4:].strip() if end != -1 else ""


def _log_tail(tf: Path, n: int = 18) -> str:
    logf = tf.with_name(tf.stem + ".log.md")
    try:
        lines = [l for l in logf.read_text(encoding="utf-8").splitlines() if l.strip()]
    except OSError:
        return ""
    return "\n".join(lines[-n:])


def _project_docs(project_dir: Path) -> list:
    """Fichiers de doc du projet (overview, environments, CDC, specs…).

    Deux emplacements depuis RM2043 (privsep) : `project/` (canoniques overview +
    environments) et `docs/` (aspects libres wiki-syncés). On surface les deux.
    """
    docs = []
    for sub in ("project", "docs"):
        pdir = project_dir / sub
        if pdir.is_dir():
            for f in sorted(pdir.glob("*.md")):
                docs.append({"name": f.name, "path": str(f.relative_to(REPO_ROOT))})
    return docs


def op_resolve(rm_id: str) -> dict:
    """Résout un rm_id en métadonnées riches depuis le MD local (RM1893 §1) — pour
    pré-remplir le lanceur ET alimenter le panneau de pilotage du cockpit. Pas de
    fetch Redmine ; tout vient du frontmatter/corps/log/projet locaux."""
    if not _RM_ID_RE.match(rm_id):
        raise ApiError(400, "rm_id invalide")
    tf = _find_task_file(rm_id)
    if not tf:
        return {"found": False, "rm_id": rm_id, "cwd": DEFAULT_CWD,
                "prompt": f"traite la tâche RM{rm_id}"}
    client, project = _task_client_project(tf)
    project_dir = tf.parent.parent
    try:
        text = tf.read_text(encoding="utf-8")
    except OSError:
        text = ""
    fm = _parse_frontmatter(text)
    meta = _read_task_meta(tf)            # repli scalaire si yaml indispo

    def pick(key, default=""):
        v = fm.get(key) if isinstance(fm, dict) else None
        if v in (None, "", "null"):
            v = meta.get(key, default)
        return v if v not in (None, "null") else default

    status = pick("status")
    envs = _read_project_envs(project_dir)
    git = fm.get("git") if isinstance(fm.get("git"), dict) else {}
    redmine = os.environ.get("REDMINE_URL", "").rstrip("/")
    ws = _resolve_workspace(project_dir)

    return {
        "found": True, "rm_id": rm_id, "client": client, "project": project,
        "title": pick("title"), "type": pick("type"), "status": status,
        "priority": pick("priority"), "completion_pct": fm.get("completion_pct"),
        "due": pick("due"), "assigned_to": fm.get("assigned_to"),
        "description": _task_body(text)[:6000],
        "task_file": str(tf.relative_to(REPO_ROOT)),
        "cwd": str(ws) if ws else DEFAULT_CWD,
        "prompt": f"traite la tâche RM{rm_id} du client {client} projet {project}",
        "test_url": pick("test_url"), "target_env": pick("target_env"),
        "environments": envs, "active_env": _env_for_status(status, envs),
        "git": {"repo": git.get("repo"), "branch": git.get("branch"), "mr_url": git.get("mr_url")},
        "redmine_url": f"{redmine}/issues/{rm_id}" if redmine else "",
        "parent_task": fm.get("parent_task"), "sub_tasks": fm.get("sub_tasks") or [],
        "depends_on": fm.get("depends_on") or [], "blocks": fm.get("blocks") or [],
        "relates": fm.get("relates") or [], "outputs": fm.get("outputs") or [],
        "project_docs": _project_docs(project_dir),
        "log_tail": _log_tail(tf),
        # Modèle prescrit (RM1941) : frontmatter ai_model (cascade tâche → projet).
        "ai_model": _safe_ticket_model(rm_id),
    }


def _safe_ticket_model(rm_id: str):
    """_ticket_model sans lever : /resolve ne doit pas échouer pour un ai_model
    malformé (le spawn, lui, refuse). Renvoie la valeur ou None."""
    try:
        return _ticket_model(rm_id)
    except ApiError:
        return None


def op_search(q="", status=None, client=None, project=None, tag=None, limit=60) -> list:
    """Recherche sur les MD de tâches locaux (RM1893 §7). Match q sur id/titre/tags ;
    filtres status/client/project/tag. Trié par rm_id décroissant."""
    q_low = (q or "").lower().strip()
    out = []
    for tf in PROJECTS_BASE.glob("*/projects/*/tasks/RM*_*.md"):
        if tf.name.endswith(".log.md"):
            continue
        m = re.match(r"RM(\d+)_", tf.name)
        if not m:
            continue
        rid = m.group(1)
        cl, pr = _task_client_project(tf)
        if client and cl != client:
            continue
        if project and pr != project:
            continue
        meta = _read_task_meta(tf)
        if status and meta["status"] != status:
            continue
        if tag and tag not in meta["tags"]:
            continue
        if q_low:
            hay = f"{rid} {meta['title']} {' '.join(meta['tags'])}".lower()
            if q_low not in hay:
                continue
        out.append({
            "rm_id": rid, "title": meta["title"], "status": meta["status"],
            "priority": meta["priority"], "client": cl, "project": pr,
            "tags": meta["tags"],
        })
    out.sort(key=lambda r: -int(r["rm_id"]))
    return out[:limit]


# ── Statut du workspace de la tâche (intérim ; outil dédié = RM1883) ─────────
def _git(cwd, *args, timeout=8):
    try:
        p = subprocess.run(["git", "-C", str(cwd), *args],
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, "", "git indisponible"


def op_workspace_status(rm_id: str) -> dict:
    """État git du workspace de code de la tâche (branche, dirty, untracked,
    ahead/behind). Vue *intérim* : l'outil complet (submodules, prod, nettoyage)
    est RM1883 — karl-agent l'appellera quand il existera."""
    if not _RM_ID_RE.match(rm_id):
        raise ApiError(400, "rm_id invalide")
    tf = _find_task_file(rm_id)
    cwd = Path(DEFAULT_CWD)
    if tf:
        ws = _resolve_workspace(tf.parent.parent)
        if ws:
            cwd = ws
    rc, _, _ = _git(cwd, "rev-parse", "--is-inside-work-tree")
    if rc != 0:
        return {"rm_id": rm_id, "cwd": str(cwd), "is_git": False}
    _, branch, _ = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    _, porcelain, _ = _git(cwd, "status", "--porcelain")
    lines = [l for l in porcelain.splitlines() if l]
    dirty = sum(1 for l in lines if not l.startswith("??"))
    untracked = sum(1 for l in lines if l.startswith("??"))
    ahead = behind = 0
    rc, ab, _ = _git(cwd, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    if rc == 0 and ab:
        parts = ab.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            behind, ahead = int(parts[0]), int(parts[1])
    return {
        "rm_id": rm_id, "cwd": str(cwd), "is_git": True, "branch": branch,
        "dirty": dirty, "untracked": untracked, "ahead": ahead, "behind": behind,
        "clean": dirty == 0 and untracked == 0,
        "interim": True,  # remplacé par l'outil RM1883
    }


def op_file(relpath: str) -> str:
    """Sert un fichier .md sous projects/ (lecture seule, anti-évasion) — pour
    afficher les docs projet (CDC, overview…) dans le panneau du cockpit."""
    if not relpath:
        raise ApiError(400, "path requis")
    target = (REPO_ROOT / relpath).resolve()
    base = (REPO_ROOT / "projects").resolve()
    if not (target == base or base in target.parents):
        raise ApiError(403, "chemin hors de projects/")
    if target.suffix != ".md" or not target.is_file():
        raise ApiError(404, "fichier .md introuvable")
    try:
        return target.read_text(encoding="utf-8")
    except OSError as e:
        raise ApiError(500, f"lecture impossible : {e}")


# ── Création de ticket depuis le cockpit (RM1893 §8) ─────────────────────────
# Wrappe scripts/pm-task-add.py. Les credentials Redmine viennent du .env chargé
# par le daemon (REDMINE_URL/REDMINE_USER_MAIN_API_KEY) et sont hérités par le
# sous-processus. Les entrées client sont passées en argv (liste, jamais via un
# shell) → aucune injection possible ; type/priorité validés contre une liste.
PRIORITIES = ["low", "normal", "high", "urgent"]
_TASK_TYPES_CACHE = None


def _task_types() -> list:
    """Taxonomie canonique des types, lue DYNAMIQUEMENT depuis pm-task-add
    (`--list-types`) → source de vérité unique, jamais redupliquée ici (NORMS).
    Cachée pour la durée de vie du process. Repli si l'appel échoue."""
    global _TASK_TYPES_CACHE
    if _TASK_TYPES_CACHE is not None:
        return _TASK_TYPES_CACHE
    fallback = [{"value": v, "label": v} for v in (
        "feature", "bugfix", "assistance", "infrastructure",
        "maintenance", "documentation", "research", "autre")]
    try:
        p = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "pm-task-add.py"), "--list-types"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=20, env=os.environ)
        data = json.loads(p.stdout) if p.returncode == 0 else None
        _TASK_TYPES_CACHE = data if isinstance(data, list) and data else fallback
    except (OSError, ValueError, subprocess.TimeoutExpired):
        _TASK_TYPES_CACHE = fallback
    return _TASK_TYPES_CACHE


def op_list_projects() -> list:
    out = []
    for cl in sorted(PROJECTS_BASE.glob("*")):
        pdir = cl / "projects"
        if not pdir.is_dir():
            continue
        for pr in sorted(pdir.glob("*")):
            if pr.is_dir():
                out.append({"client": cl.name, "project": pr.name, "value": f"{cl.name}/{pr.name}"})
    return out


def op_create_ticket(payload: dict) -> dict:
    title = (payload.get("title") or "").strip()
    if not title:
        raise ApiError(400, "title requis")
    ttype = payload.get("type", "autre")
    valid = {t["value"] for t in _task_types()}
    if ttype not in valid:
        raise ApiError(400, f"type invalide (connus : {sorted(valid)})")
    prio = payload.get("priority", "normal")
    if prio not in PRIORITIES:
        raise ApiError(400, f"priority invalide (connus : {PRIORITIES})")
    project = (payload.get("project") or "").strip()
    if not project or "/" not in project:
        raise ApiError(400, "project requis (forme entity/project)")
    args = [sys.executable, str(REPO_ROOT / "scripts" / "pm-task-add.py"),
            "--title", title, "--type", ttype, "--priority", prio, "--project", project]
    desc = (payload.get("description") or "").strip()
    if desc:
        args += ["--description", desc]
    tags = (payload.get("tags") or "").strip()
    if tags:
        args += ["--tags", tags]
    try:
        p = subprocess.run(args, cwd=str(REPO_ROOT), capture_output=True,
                           text=True, timeout=90, env=os.environ)
    except subprocess.TimeoutExpired:
        raise ApiError(504, "pm-task-add : timeout")
    blob = (p.stdout or "") + "\n" + (p.stderr or "")
    m = re.search(r"RM(\d+) créé", blob) or re.search(r"#(\d+) créé", blob)
    if not m:
        raise ApiError(500, "pm-task-add a échoué : " + blob.strip()[-400:])
    return {"created": True, "rm_id": m.group(1), "output": blob.strip()[-600:]}


# ── Moniteurs multi-panes (RM1893 §3) ────────────────────────────────────────
# Catalogue serveur de commandes de monitoring (jamais de commande brute client,
# même modèle de sécurité que les moteurs). Surchargeable via cockpit/monitors.json.
_DEFAULT_MONITORS = {
    "opensvc": "watch -n2 om mon",
    "journal": "journalctl -fn80 --no-pager",
    "htop": "htop",
    "dmesg": "dmesg -w",
    "sessions": "watch -n2 tmux list-sessions",
}


def _monitor_presets() -> dict:
    f = COCKPIT_DIR / "monitors.json"
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and all(isinstance(v, str) for v in data.values()):
                return data
        except (ValueError, OSError):
            pass
    return _DEFAULT_MONITORS


def op_monitor(payload: dict) -> dict:
    """Ajoute un pane moniteur (split-window) à la session de l'agent."""
    rm_id = _require_rm_id(payload)
    if not _has_session(rm_id):
        raise ApiError(404, f"session absente : {_session_name(rm_id)}")
    preset = payload.get("preset")
    presets = _monitor_presets()
    if preset not in presets:
        raise ApiError(400, f"preset inconnu : {preset} (connus : {list(presets)})")
    name = _session_name(rm_id)
    orient = "-v" if payload.get("orientation") == "v" else "-h"
    rc, _, err = _tmux("split-window", orient, "-t", name,
                       "-c", "#{pane_current_path}", presets[preset])
    if rc != 0:
        raise ApiError(500, f"split-window a échoué : {err.strip()}")
    # Marque le nouveau pane (actif après split) comme moniteur → permet de le
    # retirer sans jamais toucher au pane de l'agent (qui n'a pas ce flag).
    _tmux("set-option", "-p", "-t", name, "@karl_mon", "1")
    _tmux("select-layout", "-t", name, "tiled")
    return {"rm_id": rm_id, "preset": preset, "added": True}


def op_unmonitor(payload: dict) -> dict:
    """Ferme un pane moniteur (RM1893 §3). Cible le moniteur actif (celui que
    l'utilisateur a cliqué dans le terminal) ou, à défaut, le dernier. Identifie
    le pane de l'AGENT (marqué @karl_agent au spawn, sinon pane index 0) et le
    protège ; tout autre pane est considéré comme moniteur — robuste même pour
    les moniteurs ajoutés avant le marquage @karl_mon."""
    rm_id = _require_rm_id(payload)
    if not _has_session(rm_id):
        raise ApiError(404, f"session absente : {_session_name(rm_id)}")
    name = _session_name(rm_id)
    # Délimiteur '|' : les champs d'options vides ne sont pas avalés (contrairement
    # à un split sur espaces). pane_id (%N) ne contient jamais de '|'.
    rc, out, err = _tmux("list-panes", "-t", name, "-F",
                         "#{pane_id}|#{pane_index}|#{pane_active}|#{@karl_agent}")
    if rc != 0:
        raise ApiError(500, f"list-panes a échoué : {err.strip()}")
    panes = []
    for line in out.splitlines():
        f = line.split("|")
        if len(f) < 4:
            continue
        panes.append({"id": f[0], "index": f[1], "active": f[2] == "1", "agent": f[3] == "1"})
    if len(panes) <= 1:
        raise ApiError(400, "aucun moniteur à fermer")
    agent = next((p for p in panes if p["agent"]), None) \
        or next((p for p in panes if p["index"] == "0"), panes[0])
    monitors = [p for p in panes if p["id"] != agent["id"]]
    if not monitors:
        raise ApiError(400, "aucun moniteur à fermer")
    active = next((p for p in monitors if p["active"]), None)
    target = (active or monitors[-1])["id"]
    rc, _, err = _tmux("kill-pane", "-t", target)
    if rc != 0:
        raise ApiError(500, f"kill-pane a échoué : {err.strip()}")
    _tmux("select-layout", "-t", name, "tiled")
    return {"rm_id": rm_id, "closed": target, "remaining": len(monitors) - 1}


def op_layout(payload: dict) -> dict:
    """Réarrange les panes de la session (RM1893 §3)."""
    rm_id = _require_rm_id(payload)
    if not _has_session(rm_id):
        raise ApiError(404, f"session absente : {_session_name(rm_id)}")
    layout = payload.get("layout", "tiled")
    if layout not in LAYOUTS:
        raise ApiError(400, f"layout inconnu : {layout} (connus : {sorted(LAYOUTS)})")
    rc, _, err = _tmux("select-layout", "-t", _session_name(rm_id), layout)
    if rc != 0:
        raise ApiError(500, f"select-layout a échoué : {err.strip()}")
    return {"rm_id": rm_id, "layout": layout}


# ── Serveur HTTP ─────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = "karl-agent/1.0"

    def log_message(self, fmt, *args):  # journald capte stderr ; format compact
        sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

    # -- utilitaires de réponse --
    def _send_json(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, code: int, text: str):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, code: int, html: str):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self) -> bool:
        """Vraie si le client présente le token partagé OU des credentials Basic
        valides (RM2139). Sans aucune auth configurée → ouvert (usage local)."""
        if AUTH_TOKEN is not None:
            if hmac.compare_digest(self.headers.get("X-Karl-Token") or "", AUTH_TOKEN):
                return True
        if BASIC_USER is not None and BASIC_PASS is not None:
            auth = self.headers.get("Authorization") or ""
            if not auth.startswith("Basic "):
                return False
            try:
                user, _, pwd = base64.b64decode(
                    auth[6:], validate=True).decode("utf-8").partition(":")
            except (ValueError, UnicodeDecodeError):
                return False
            return (hmac.compare_digest(user, BASIC_USER)
                    and hmac.compare_digest(pwd, BASIC_PASS))
        return AUTH_TOKEN is None

    def _send_auth_required(self):
        """401 ; le challenge Basic n'est émis que si le mode user/mdp est
        configuré (en mode token seul, pas de prompt navigateur parasite)."""
        body = json.dumps(
            {"error": "authentification requise (Basic ou X-Karl-Token)"},
            ensure_ascii=False).encode("utf-8")
        self.send_response(401)
        if BASIC_USER is not None and BASIC_PASS is not None:
            self.send_header("WWW-Authenticate", 'Basic realm="karl-agent", charset="UTF-8"')
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "corps JSON invalide")
        if not isinstance(obj, dict):
            raise ApiError(400, "corps JSON doit être un objet")
        return obj

    # -- routage --
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        # Basic configuré ⇒ AUCUNE route publique : la page cockpit elle-même est
        # gated, le navigateur prompte nativement puis rejoue les credentials sur
        # tous les fetch same-origin (RM2139).
        if BASIC_USER is not None and not self._check_auth():
            return self._send_auth_required()
        # Routes publiques du cockpit (RM1873) — SANS auth en mode token : la page
        # doit pouvoir se charger pour qu'on y saisisse le token, et elle ne
        # divulgue rien de sensible (le ttyd_base est déjà déductible côté client).
        if path in ("/", "/cockpit"):
            try:
                return self._send_html(200, (COCKPIT_DIR / "index.html").read_text(encoding="utf-8"))
            except FileNotFoundError:
                return self._send_json(404, {"error": "cockpit/index.html absent"})
        if path == "/cockpit-config":
            return self._send_json(200, {
                "ttyd_base": TTYD_URL,
                # En mode Basic, le navigateur a déjà été authentifié pour charger
                # la page : le champ token du cockpit n'a pas lieu d'être.
                "auth_required": AUTH_TOKEN is not None and BASIC_USER is None,
                "monitors": list(_monitor_presets().keys()),
                "layouts": sorted(LAYOUTS),
                "task_types": _task_types(),
                "priorities": PRIORITIES,
                "engines": list(ENGINES),
                # clés du catalogue par moteur (RM1941) — le client ne voit que les
                # clés, le mapping vers les valeurs réelles reste côté serveur.
                "models": {e: sorted(m) for e, m in _model_catalog().items()},
            })
        if not self._check_auth():
            return self._send_auth_required()
        try:
            if path == "/health":
                return self._send_json(200, {
                    "status": "ok",
                    "sessions": len(_list_sessions()),
                    "tmux": _tmux("-V")[0] == 0,
                })
            if path == "/sessions":
                qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                return self._send_json(200, {"sessions": _sessions_view(qs)})
            if path == "/resumable":
                qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                return self._send_json(200, {"resumable": op_resumable(qs)})
            if path.startswith("/capture/"):
                rm_id = path[len("/capture/"):]
                qs = parse_qs(parsed.query)
                lines = int(qs["lines"][0]) if "lines" in qs else None
                return self._send_text(200, op_capture(rm_id, lines))
            if path.startswith("/stream/"):
                return self._stream(path[len("/stream/"):])
            if path.startswith("/resolve/"):
                return self._send_json(200, op_resolve(path[len("/resolve/"):]))
            if path == "/tickets/search":
                qs = parse_qs(parsed.query)
                g = lambda k: qs[k][0] if k in qs else None  # noqa: E731
                return self._send_json(200, {"results": op_search(
                    g("q") or "", g("status"), g("client"), g("project"), g("tag"))})
            if path == "/projects":
                return self._send_json(200, {"projects": op_list_projects()})
            if path.startswith("/workspace-status/"):
                return self._send_json(200, op_workspace_status(path[len("/workspace-status/"):]))
            if path == "/file":
                qs = parse_qs(parsed.query)
                return self._send_text(200, op_file(qs["path"][0] if "path" in qs else ""))
            return self._send_json(404, {"error": f"route inconnue : {path}"})
        except ApiError as e:
            return self._send_json(e.code, {"error": e.msg})
        except Exception as e:  # noqa: BLE001
            return self._send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        if not self._check_auth():
            return self._send_auth_required()
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/spawn":
                return self._send_json(201, op_spawn(payload))
            if path == "/resume":
                return self._send_json(201, op_resume(payload))
            if path == "/tickets":
                return self._send_json(201, op_create_ticket(payload))
            if path == "/send":
                return self._send_json(200, op_send(payload))
            if path == "/kill":
                return self._send_json(200, op_kill(payload))
            if path == "/monitor":
                return self._send_json(201, op_monitor(payload))
            if path == "/unmonitor":
                return self._send_json(200, op_unmonitor(payload))
            if path == "/layout":
                return self._send_json(200, op_layout(payload))
            return self._send_json(404, {"error": f"route inconnue : {path}"})
        except ApiError as e:
            return self._send_json(e.code, {"error": e.msg})
        except Exception as e:  # noqa: BLE001
            return self._send_json(500, {"error": f"{type(e).__name__}: {e}"})

    # -- SSE : tail du log pipe-pane (octets de terminal bruts) --
    def _stream(self, rm_id: str):
        if not _RM_ID_RE.match(rm_id):
            return self._send_json(400, {"error": "rm_id invalide"})
        logf = _log_path(rm_id)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            with open(logf, "r", encoding="utf-8", errors="replace") as fh:
                fh.seek(0, os.SEEK_END)
                last_beat = time.time()
                while True:
                    line = fh.readline()
                    if line:
                        self.wfile.write(f"data: {line.rstrip(chr(10))}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    else:
                        if not _has_session(rm_id):
                            self.wfile.write(b"event: end\ndata: session terminee\n\n")
                            self.wfile.flush()
                            return
                        if time.time() - last_beat > 15:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                            last_beat = time.time()
                        time.sleep(0.4)
        except FileNotFoundError:
            self.wfile.write(b"event: error\ndata: pas de log pour cette session\n\n")
        except (BrokenPipeError, ConnectionResetError):
            return  # client parti


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True

    def _shutdown(*_):
        # NB : ne PAS appeler server.shutdown() ici — le handler tourne dans le
        # thread de serve_forever() et shutdown() s'y bloquerait (deadlock).
        # sys.exit() lève SystemExit dans le thread principal, ce qui déroule
        # serve_forever ; daemon_threads=True laisse les workers mourir avec.
        sys.stderr.write("karl-agent: arrêt\n")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    sys.stderr.write(
        f"karl-agent en écoute sur http://{HOST}:{PORT} "
        f"(prefix={SESSION_PREFIX}, engine={DEFAULT_ENGINE}, "
        f"auth={'on' if AUTH_TOKEN else 'off'})\n"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
