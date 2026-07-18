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
                                   session_id?, client?, project?,
                                   registry?{seq, machine, created, branches[],
                                   worktrees[]}, registry_conflicts?[]}]
                                  (RM1939 ; registre pm_session RM2166)
  GET  /session-registry        → {records, rm_map} — registre pm_session brut
                                  (var/sessions/index.json, RM2034/RM2166)
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
  GET  /buffer                  → text/plain — dernier buffer tmux (copies
                                  OSC52 faites dans les sessions, RM2168)
  GET  /pm/commands             → {commands} — catalogue déclaratif des
                                  commandes PM exposables (RM2209/RM2203)
  GET  /pm/test-queue[?client=&project=]
                                → {queue} — tickets a_tester_* enrichis
                                  (branche, env monté, déployabilité) (RM2210)
  POST /pm/run {name, args{}, confirm?}
                                → {rc, ok, stdout, stderr} — exécute une
                                  commande du catalogue (allowlist, args
                                  validés par type, argv sans shell,
                                  runs mutants journalisés pm-runs.jsonl)
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
from pathlib import Path, PurePosixPath
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

# Nommage des sessions (RM2144) : l'ancrage TICKET est l'IDÉAL (karl-RM<id>,
# jonction n-m écrite), mais un SLUG est accepté (karl-<slug>) — cas type : la
# reprise d'une session interactive sans ticket évident. Le sid d'une session
# est donc soit un id numérique de ticket, soit un slug (hors espace rm<n>).
TMUX_PREFIX = "karl-"
SESSION_PREFIX = "karl-RM"   # forme ticket (conservée pour les invariants RM1771)
_RM_ID_RE = re.compile(r"^\d+$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")


def _is_ticket_sid(sid: str) -> bool:
    return bool(_RM_ID_RE.match(sid))


def _valid_sid(sid: str) -> bool:
    if _is_ticket_sid(sid):
        return True
    return bool(_SLUG_RE.match(sid)) and not re.match(r"^rm\d+$", sid)

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
    """sid → nom tmux : karl-RM<id> (ticket) ou karl-<slug> (RM2144)."""
    if _is_ticket_sid(rm_id):
        return f"{SESSION_PREFIX}{rm_id}"
    return f"{TMUX_PREFIX}{rm_id}"


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
        if not name.startswith(TMUX_PREFIX):
            continue
        # karl-RM<id> → sid numérique (ticket) ; karl-<slug> → sid slug (RM2144).
        # `rm_id` porte le sid (nom historique conservé pour les clients).
        key = name[len(TMUX_PREFIX):]
        sid = key[2:] if key.startswith("RM") and key[2:].isdigit() else key
        if not _valid_sid(sid):
            continue  # session tmux étrangère au cockpit
        sessions.append({
            "rm_id": sid,
            "is_ticket": _is_ticket_sid(sid),
            "tmux": name,
            "created": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None,
            "attached": (len(parts) > 2 and parts[2] == "1"),
        })
    return sessions


# ── Registre de sessions PM (pm_session, RM2034) — lecture seule (RM2166) ────
# `var/sessions/index.json` : { "<seq>": { seq, machine, claude_session_id,
# created, branches[], worktrees[] } }, alimenté par pm-branch-start /
# pm-env-session. Machine-local, gitignoré. Lecture directe (stdlib-only,
# pas d'import pm_session) ; fichier minuscule → relu à chaque requête.
# Choix v1 (critère RM2166) : les sessions du registre SANS tmux karl-* ne
# créent pas d'onglet (tmux reste la source des sessions pilotables) mais
# restent exposées via GET /session-registry.
REGISTRY_FILE = REPO_ROOT / "var" / "sessions" / "index.json"
_RM_BRANCH = re.compile(r"^(\d+)-")
_RM_WORKTREE = re.compile(r"-rm(\d+)$")


def _session_registry() -> dict:
    """Registre brut { seq(str) → record }. {} si absent/illisible."""
    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _registry_rm_map(records: dict) -> dict:
    """rm_id(str) → [seq, …] des sessions du registre qui le référencent
    (branche `<id>-…` ou worktree `…-rm<id>`)."""
    rm_map = {}
    for rec in records.values():
        seq, rms = rec.get("seq"), set()
        for b in rec.get("branches") or []:
            m = _RM_BRANCH.match(b)
            if m:
                rms.add(m.group(1))
        for w in rec.get("worktrees") or []:
            m = _RM_WORKTREE.search(w)
            if m:
                rms.add(m.group(1))
        for rm in rms:
            rm_map.setdefault(rm, []).append(seq)
    return rm_map


def _registry_view() -> dict:
    """Payload GET /session-registry : records + carte rm_id → sessions."""
    records = _session_registry()
    return {"records": records, "rm_map": _registry_rm_map(records)}


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
    """sid requis : id de ticket (idéal) OU slug (RM2144)."""
    rm_id = str(payload.get("rm_id", "")).strip()
    if not rm_id or not _valid_sid(rm_id):
        raise ApiError(400, "rm_id requis : id de ticket (^\\d+$) ou slug "
                            "(^[a-z0-9][a-z0-9_-]{1,40}$, hors espace rm<n>)")
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


def _anchor_context(rm_id: str) -> str:
    """RM2284 : préfixe de contexte d'ancrage pour le prompt initial d'une session
    ancrée sur un ticket. Mono-ligne (un \\n littéral via send-keys -l vaudrait
    Enter et soumettrait la ligne seule). Best-effort : si le ticket n'est pas
    résolu en local, le préfixe reste minimal mais l'id transite quand même."""
    tf = _find_task_file(rm_id)
    det = ""
    if tf:
        client, project = _task_client_project(tf)
        meta = _read_task_meta(tf)
        det = f" — client {client}, projet {project}"
        title = str(meta.get("title") or "").strip()
        status = str(meta.get("status") or "").strip()
        if title:
            det += f", « {title} »"
        if status:
            det += f", statut {status}"
    return (f"[Ancrage : cette session concerne le ticket RM{rm_id}{det}. "
            f"Applique le protocole PM correspondant.]")


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
        model_value = _ticket_model(rm_id) if _is_ticket_sid(rm_id) else None
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
        if _is_ticket_sid(rm_id):
            _record_run(rm_id, engine, session_id, str(cwd))
        _record_key(rm_id, engine, session_id, str(cwd))

    # Prompt initial éventuel, livré par send-keys (jamais dans la cmd). On attend
    # que le TUI soit prêt, puis on sépare texte et Enter (claude debounce parfois
    # la soumission si les deux arrivent collés sur un TUI à peine initialisé).
    prompt = payload.get("prompt")
    if prompt:
        # RM2284 : l'ancrage ticket transite TOUJOURS, même en prompt libre —
        # si le texte ne mentionne pas déjà RM<id>, on préfixe le contexte
        # (incident : session lancée pour RM2140 sans que l'agent le sache).
        if _is_ticket_sid(rm_id) and f"rm{rm_id}" not in str(prompt).lower():
            prompt = _anchor_context(rm_id) + " " + str(prompt)
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
    # RM2168 : capture les copies OSC52 émises DANS les sessions (ex. sélection
    # copiée dans Claude Code) vers les buffers tmux → GET /buffer les expose
    # au cockpit (bouton 📥). Validé empiriquement sur tmux 3.4.
    _tmux("set-option", "-g", "set-clipboard", "on")


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


def _send_approval(rm_id: str, source: str = "manuel") -> str | None:
    """RM2302/RM2327 : re-capture le pane et répond « oui » si une question y est
    visible. Retourne la réponse envoyée ("1" menu / "y" prompt) ou None (pas de
    question). Lève ApiError sur échec tmux. Journalise chaque réponse dans
    answers.jsonl avec sa provenance (manuel / tout / auto) — socle RM2305."""
    name = _session_name(rm_id)
    rc, out, err = _tmux("capture-pane", "-p", "-t", name)
    if rc != 0:
        raise ApiError(500, f"capture-pane a échoué : {err.strip()}")
    tail = "\n".join(out.rstrip().splitlines()[-15:])
    answer = _approve_answer(tail)
    if answer is None:
        return None
    rc, _, err = _tmux("send-keys", "-t", name, "-l", "--", answer)
    if rc != 0:
        raise ApiError(500, f"send-keys a échoué : {err.strip()}")
    if answer == "y":
        _tmux("send-keys", "-t", name, "Enter")
    try:  # journal best-effort, ne bloque jamais la réponse
        ANSWERS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ANSWERS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "rm_id": rm_id,
                                "sent": answer, "source": source,
                                "question": tail}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return answer


def op_approve(payload: dict) -> dict:
    """RM2302 : répond « Oui » à une session qui pose une question Oui/Non.
    Refuse (409) si aucune question n'est visible — l'état a pu changer entre
    l'affichage UI et le clic."""
    rm_id = _require_rm_id(payload)
    if not _has_session(rm_id):
        raise ApiError(404, f"session absente : {_session_name(rm_id)}")
    answer = _send_approval(rm_id, source="manuel")
    if answer is None:
        raise ApiError(409, "la session ne pose pas (ou plus) de question — rien envoyé")
    return {"rm_id": rm_id, "approved": True, "sent": answer}


def op_approve_all(payload: dict) -> dict:
    """RM2327 : répond « Oui » d'un coup à TOUTES les sessions qui posent une
    question. Best-effort par session (une session en échec tmux n'empêche pas
    les autres) ; celles sans question sont simplement ignorées."""
    sent, skipped = [], []
    for s in _list_sessions():
        rm_id = s["rm_id"]
        try:
            answer = _send_approval(rm_id, source="tout")
        except ApiError:
            answer = None
        if answer:
            sent.append({"rm_id": rm_id, "sent": answer})
        else:
            skipped.append(rm_id)
    return {"approved": sent, "skipped": skipped}


# ── Auto-oui par session (RM2327) ────────────────────────────────────────────
# La session répond « oui » seule à ses questions, pour une durée limitée
# (timeout obligatoire — pas d'auto-approbation permanente). Boucle de fond
# côté serveur : fonctionne même navigateur fermé. _AUTO_YES : rm_id → epoch
# d'expiration (dict, opérations atomiques sous GIL).
_AUTO_YES: dict = {}
AUTO_YES_POLL_SECONDS = int(os.environ.get("KARL_AGENT_AUTO_YES_POLL", "3"))
AUTO_YES_MAX_MINUTES = 240


def op_auto_yes(payload: dict) -> dict:
    """Arme (minutes > 0) ou désarme (minutes = 0) l'auto-oui d'une session."""
    rm_id = _require_rm_id(payload)
    try:
        minutes = float(payload.get("minutes"))
    except (TypeError, ValueError):
        raise ApiError(400, "minutes requis (nombre ; 0 = désactiver)")
    if minutes <= 0:
        _AUTO_YES.pop(rm_id, None)
        return {"rm_id": rm_id, "auto_yes_until": None}
    if minutes > AUTO_YES_MAX_MINUTES:
        raise ApiError(400, f"minutes > {AUTO_YES_MAX_MINUTES} — l'auto-oui est "
                            f"volontairement borné (timeout obligatoire)")
    if not _has_session(rm_id):
        raise ApiError(404, f"session absente : {_session_name(rm_id)}")
    until = time.time() + minutes * 60
    _AUTO_YES[rm_id] = until
    return {"rm_id": rm_id, "auto_yes_until": until}


def _auto_yes_tick(now=None) -> list:
    """Une passe de la boucle auto-oui : purge les entrées expirées ou dont la
    session a disparu, répond aux questions des autres. Retourne [(rm_id, réponse)].
    Séparée de la boucle pour être testable sans thread ni horloge."""
    now = time.time() if now is None else now
    sent = []
    for rm_id, until in list(_AUTO_YES.items()):
        if until <= now or not _has_session(rm_id):
            _AUTO_YES.pop(rm_id, None)
            continue
        try:
            answer = _send_approval(rm_id, source="auto")
        except ApiError:
            continue        # tmux grognon : on retentera à la prochaine passe
        if answer:
            sent.append((rm_id, answer))
    return sent


def _auto_yes_loop():
    while True:
        time.sleep(AUTO_YES_POLL_SECONDS)
        try:
            _auto_yes_tick()
        except Exception as e:  # noqa: BLE001 — la boucle ne meurt jamais
            sys.stderr.write(f"auto-oui: passe en échec (non fatal) : {e}\n")


def op_buffer() -> str:
    """Dernier buffer tmux (RM2168) — reçoit les copies OSC52 faites dans les
    sessions (set-clipboard on, posé au spawn). Les buffers sont globaux au
    serveur tmux : on renvoie le plus récent, peu importe la session."""
    rc, out, _ = _tmux("show-buffer")
    if rc != 0 or not out:
        raise ApiError(404, "aucune copie en attente dans tmux (buffer vide)")
    return out


def op_capture(rm_id: str, lines: int | None) -> str:
    if not _valid_sid(rm_id):
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


def _record_key(sid: str, engine: str, session_id: str, cwd: str) -> None:
    """Index clé-tmux → (engine, session_id, cwd) — RM2144. Couvre AUSSI les
    sessions slug (sans jonction ticket) : sert à l'enrichissement /sessions
    (moteur, projet via cwd) et à la reprise. Touche l'entité session au passage."""
    now = int(time.time())
    key = f"RM{sid}" if _is_ticket_sid(sid) else sid
    _write_json_atomic(LOG_DIR / "keys" / f"{key}.json",
                       {"sid": sid, "engine": engine, "session_id": session_id,
                        "cwd": cwd, "last_seen": now})
    sf = SESS_DIR / engine / f"{session_id}.json"
    meta = _read_json_file(sf) or {"engine": engine, "session_id": session_id, "created": now}
    meta.update({"cwd": cwd, "last_seen": now})
    _write_json_atomic(sf, meta)


def _key_info(sid: str) -> dict | None:
    key = f"RM{sid}" if _is_ticket_sid(sid) else sid
    return _read_json_file(LOG_DIR / "keys" / f"{key}.json")


def _auto_slug(title: str | None, session_id: str) -> str:
    """Slug d'ancrage automatique pour une reprise sans ticket (RM2144) :
    dérivé du titre de la session (marqueur [WIP]/[DONE] retiré), unique parmi
    les tmux vivants, jamais dans l'espace rm<n>."""
    base = _MARK_RE.sub("", title or "").lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:32].strip("-") or session_id[:8]
    if re.match(r"^rm\d+$", base):
        base = f"s-{base}"
    slug, i = base, 2
    while _has_session(slug):
        slug, i = f"{base}-{i}", i + 1
    return slug


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
        # status=not-done : tout sauf les [DONE] (défaut du panneau de reprise)
        if f_status == "not-done":
            if e["mark"] == "done":
                return False
        elif f_status and e["mark"] != f_status:
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
    if rm_id and not _valid_sid(rm_id):
        raise ApiError(400, "rm_id invalide (id de ticket ou slug)")

    if not session_id:
        if not rm_id or not _is_ticket_sid(rm_id):
            raise ApiError(400, "session_id ou rm_id (ticket) requis")
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

    jf = next((p for root in CLAUDE_STORES for p in root.glob(f"*/{session_id}.jsonl")), None)
    if not rm_id:
        # Ancrage automatique (RM2144) : ticket idéal (dernière jonction), sinon
        # SLUG dérivé du titre de la session — plus d'obligation de fournir un
        # ticket à la reprise.
        runs = _runs_by_session().get(session_id, [])
        if runs:
            rm_id = max(runs, key=lambda r: r.get("last_seen", r.get("created", 0)))["rm_id"]
        else:
            title = _jsonl_tail_meta(jf)["title"] if jf else None
            rm_id = _auto_slug(title, session_id)

    if _has_session(rm_id):
        raise ApiError(409, f"session déjà active : {_session_name(rm_id)}")

    # Garde-fous : transcript présent ? cwd toujours valide ?
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
    if _is_ticket_sid(rm_id):
        _record_run(rm_id, "claude", session_id, str(cwd))
    _record_key(rm_id, "claude", session_id, str(cwd))

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
# RM2302/RM2327 : marqueurs d'un menu numéroté dont l'option 1 est bien un OUI
# (la touche chiffre sélectionne et valide seule, sans Enter). Un menu numéroté
# SANS « 1. Yes/Oui » est un choix multiple → état "choice", jamais auto-répondu.
_YES_MENU_MARKERS = ("1. Yes", "1. Oui")
_MENU_MARKERS = ("❯ 1.", "│ 1.")


def _approve_answer(tail: str) -> str | None:
    """RM2302 : réponse affirmative à envoyer au pane qui pose une question.
    "1" = menu numéroté dont l'option 1 est Yes/Oui (chiffre seul) ; "y" =
    prompt texte y/n ou question sans menu (Enter derrière) ; None = pas de
    question OU choix multiple non Oui/Non (RM2327 — on ne choisit pas à
    l'aveugle dans un menu)."""
    if any(m in tail for m in _YES_MENU_MARKERS):
        return "1"
    if any(m in tail for m in _MENU_MARKERS):
        return None     # menu numéroté ≠ oui/non → décision humaine
    if any(m in tail for m in _ATTENTION_MARKERS):
        return "y"
    return None


def _session_state(rm_id: str, engine) -> str:
    rc, out, _ = _tmux("capture-pane", "-p", "-t", _session_name(rm_id))
    if rc != 0:
        return "idle"
    tail = "\n".join(out.rstrip().splitlines()[-15:])
    if any(m in tail for m in _ATTENTION_MARKERS):
        # RM2327 : question OUI/NON auto-répondable → "attention" ; menu à choix
        # multiple (ou forme inconnue de réponse) → "choice" (en attente aussi,
        # mais réponse humaine requise — icône distincte, hors auto-oui/✔ tout).
        return "attention" if _approve_answer(tail) else "choice"
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
    # Registre pm_session (RM2166) : jointure par claude_session_id + carte
    # rm_id → sessions pour signaler les travaux concurrents sur un même ticket.
    registry = _session_registry()
    reg_by_csid = {r.get("claude_session_id"): r for r in registry.values()
                   if r.get("claude_session_id")}
    rm_map = _registry_rm_map(registry)
    for s in sessions:
        # Enrichissement : index clé-tmux (couvre tickets ET slugs, RM2144),
        # complété par la jonction (client/projet des tickets).
        k = _key_info(s["rm_id"])
        if k:
            s["engine"] = k.get("engine")
            s["session_id"] = k.get("session_id")
        r = latest.get(s["rm_id"]) if s.get("is_ticket") else None
        if r:
            s.setdefault("engine", r.get("engine"))
            s.setdefault("session_id", r.get("session_id"))
            if r.get("client") != "_":
                s["client"], s["project"] = r.get("client"), r.get("project")
        if not s.get("client") and k and k.get("cwd"):
            c, p = _pm_project_of_cwd(k["cwd"])
            if c:
                s["client"], s["project"] = c, p
        s["state"] = _session_state(s["rm_id"], s.get("engine"))
        # RM2327 : auto-oui armé → l'UI affiche le badge + compte à rebours
        au = _AUTO_YES.get(s["rm_id"])
        if au and au > time.time():
            s["auto_yes_until"] = au
        # RM2166 — encart session : branches/worktrees de la session (registre
        # pm_session) + conflits (un rm_id référencé par PLUSIEURS sessions).
        rec = reg_by_csid.get(s.get("session_id"))
        own_seq = rec.get("seq") if rec else None
        own_rms = set()
        if rec:
            own_rms = {m.group(1) for b in rec.get("branches") or []
                       if (m := _RM_BRANCH.match(b))}
            own_rms |= {m.group(1) for w in rec.get("worktrees") or []
                        if (m := _RM_WORKTREE.search(w))}
            s["registry"] = {
                "seq": own_seq, "machine": rec.get("machine"),
                "created": rec.get("created"),
                "branches": rec.get("branches") or [],
                "worktrees": rec.get("worktrees") or [],
            }
        if s.get("is_ticket"):
            own_rms.add(s["rm_id"])  # ticket de l'onglet, même sans registre
        conflicts = [{"rm_id": rm, "seqs": sorted(x for x in rm_map.get(rm, [])
                                                  if x != own_seq)}
                     for rm in sorted(own_rms)
                     if [x for x in rm_map.get(rm, []) if x != own_seq]]
        if conflicts:
            s["registry_conflicts"] = conflicts

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
    """Workspace de code du projet PM. Voie canonique : le symlink
    `paths.workspace_link` (= `<projet PM>/workspace`, cf. structure-reference) —
    couvre les workspaces imbriqués (ex. perso/maths) que le scan superficiel
    ratait (RM2210). Repli : scan des `.mmi-pm` des racines autorisées."""
    wl = project_dir / "workspace"
    try:
        if wl.is_symlink() and wl.resolve().is_dir():
            ws = wl.resolve()
            # Invariant bidirectionnel : on ne fait confiance au lien que si le
            # `.mmi-pm` du workspace (symlink OU dossier co-localisé RM1949)
            # repointe bien ce projet — un lien `workspace` périmé (ancien
            # emplacement pré-migration) est ainsi ignoré → repli sur le scan.
            back = ws / ".mmi-pm"
            if back.exists() and back.resolve() == project_dir.resolve():
                return ws
    except OSError:
        pass
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


_PROTO_HEAD_RE = re.compile(
    r"(?im)^#{1,4}\s*(?:📋\s*)?(?:à tester|a tester|protocole de test|"
    r"tests? à effectuer|quoi tester)\b.*$")


def _test_protocol(tf: Path, body: str):
    """Protocole de test du ticket (RM2229) : la DERNIÈRE section « À tester » /
    « Protocole de test » trouvée dans le `.log.md` (notes de livraison — la
    plus récente prime, une re-livraison remplace le protocole), sinon dans la
    description. Renvoie {source, heading, text} ou None. Convention associée :
    toute livraison en a_tester_* inclut une note avec un titre `## À tester`."""
    logf = tf.with_name(tf.stem + ".log.md")
    try:
        log_text = logf.read_text(encoding="utf-8")
    except OSError:
        log_text = ""
    for source, text in (("note", log_text), ("description", body or "")):
        if not text:
            continue
        matches = list(_PROTO_HEAD_RE.finditer(text))
        if not matches:
            continue
        m = matches[-1]
        after = text[m.end():]
        # coupe à la prochaine section `#`/`##` (nouvelle rubrique de la note
        # ou entrée horodatée suivante du log)
        stop = re.search(r"(?m)^#{1,2}\s", after)
        section = (after[:stop.start()] if stop else after).strip()
        if section:
            return {"source": source,
                    "heading": m.group(0).lstrip("# ").strip(),
                    "text": section[:4000]}
    return None


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
        # Protocole de test (RM2229) : champ canonique = frontmatter
        # `test_protocol` (miroir du CF Redmine, rédigé au fil de l'eau via
        # pm-task-protocol) ; repli : section « À tester » de la dernière note
        # de livraison (log), sinon de la description.
        "test_protocol": (
            {"source": "cf", "heading": "Protocole de test",
             "text": str(pick("test_protocol"))[:4000]}
            if str(pick("test_protocol") or "").strip() not in ("", "None")
            else _test_protocol(tf, _task_body(text))),
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
        # Métriques worklog (RM2173) : ce que le PM enregistre via pm-task-tick.
        "metrics": {
            "tokens_total": fm.get("tokens_total"),
            "tokens_breakdown": fm.get("tokens_breakdown")
                if isinstance(fm.get("tokens_breakdown"), dict) else {},
            "cost_total_usd": fm.get("cost_total_usd"),
            "ai_time_total_minutes": fm.get("ai_time_total_minutes"),
            "human_time_total_minutes": fm.get("human_time_total_minutes"),
            "time_total_minutes": fm.get("time_total_minutes"),
            "updated": str(pick("updated")),
        },
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
    afficher les docs projet (CDC, overview…) dans le panneau du cockpit.

    RM2303 : garde LEXICALE sur le chemin demandé (absolu, segments «..», hors
    projects/), sans résoudre les symlinks de la cible — le tree projects/
    contient des liens légitimes vers les dossiers PM des workspaces (projets
    relocalisés, pm-sync-links) que l'ancien resolve() faisait rejeter en 403.
    Les symlinks sont posés par le provisioning serveur, jamais par le client :
    l'évasion à bloquer est celle de l'URL, pas celle du tree."""
    if not relpath:
        raise ApiError(400, "path requis")
    parts = PurePosixPath(relpath).parts
    if (PurePosixPath(relpath).is_absolute() or ".." in parts
            or not parts or parts[0] != "projects"):
        raise ApiError(403, "chemin hors de projects/")
    target = REPO_ROOT / relpath
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


# ── Chips d'actions en un clic (RM1893 §2) ───────────────────────────────────
# Rangée de raccourcis sous le terminal : chaque chip INJECTE du texte dans la
# session attachée via /send (langage naturel — l'agent appelle le bon skill).
# Catalogue config-driven, surchargeable via cockpit/actions.json (liste de
# {key, group, label, text, enter?, ticket_only?}). `{id}` est substitué par le
# sid de la session côté client ; `enter: false` = texte injecté sans Enter
# (l'utilisateur complète) ; `ticket_only` = masqué pour les sessions slug.
_DEFAULT_ACTIONS = [
    {"key": "encours", "group": "PM", "label": "▶ en cours",
     "text": "passe la tâche RM{id} en cours", "ticket_only": True},
    {"key": "atester", "group": "PM", "label": "✔ à tester",
     "text": "le travail de RM{id} est livré : passe-la au statut à tester approprié "
             "(a_tester_dev ou a_tester_demandeur selon requires_agent_test)",
     "ticket_only": True},
    {"key": "commenter", "group": "PM", "label": "💬 commenter",
     "text": "commente RM{id} : ", "enter": False, "ticket_only": True},
    {"key": "majdesc", "group": "PM", "label": "📝 MAJ desc",
     "text": "mets à jour la description du ticket RM{id} pour refléter l'état réel "
             "(checklist, contexte, critères)", "ticket_only": True},
    {"key": "tests", "group": "Dev", "label": "🧪 tests",
     "text": "lance les tests du projet et donne-moi le résultat"},
    {"key": "commit", "group": "Dev", "label": "💾 commit+push",
     "text": "committe et pushe tes modifications en cours (chemins explicites, "
             "jamais git add -A)"},
    {"key": "gitstatus", "group": "Dev", "label": "🔍 git status",
     "text": "fais un git status du workspace et résume l'état (modifs, untracked, "
             "ahead/behind)"},
    {"key": "point", "group": "Session", "label": "📊 point",
     "text": "fais un point synthétique : avancement, reste à faire, blocages, "
             "prochaine étape — sans rien modifier"},
    {"key": "done", "group": "Session", "label": "🏁 done",
     "text": "marque la session terminée (/session-mark done)"},
]


def _actions_catalog() -> list:
    f = COCKPIT_DIR / "actions.json"
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, list) and all(
                    isinstance(a, dict) and a.get("label") and a.get("text")
                    for a in data):
                return data
        except (ValueError, OSError):
            pass
    return _DEFAULT_ACTIONS


# ── Command-catalog PM (RM2209, chapeau RM2203) ──────────────────────────────
# Exposer la surface CLI PM au cockpit SANS écrire un endpoint par script :
# un catalogue DÉCLARATIF des commandes exposables (le catalogue EST l'allowlist),
# un runner générique qui valide les args par type et exécute en argv (jamais de
# shell). Défauts en code, surchargeables via cockpit/pm-commands.json (même
# pattern que monitors.json / actions.json). Les scripts restent la seule
# implémentation (single-writer RM1669) — l'UI ne fait qu'appeler.
#
# Spec d'une commande : {name, label, category, script, mutate, confirm?, args[]}
# Spec d'un arg : {name, label?, type: rm_id|int|enum|text|bool, required?,
#                  positional?, flag?, choices?, max_len?}
_PM_STATUSES = ["nouveau", "a_etudier_chiffrer", "etude_chiffrage_en_cours",
                "etude_chiffrage_a_valider", "a_faire", "en_cours", "a_tester_dev",
                "a_tester_demandeur", "a_tester_verifier", "a_mep", "en_mep",
                "en_pause", "a_corriger", "ferme"]
_PM_CLOSE_REASONS = ["resolu", "abandonne", "wont_fix", "hors_perimetre",
                     "invalide", "doublon"]
_PM_COMMANDS_DEFAULT = [
    {"name": "task-status", "label": "Changer le statut d'un ticket",
     "category": "ticket", "script": "pm-task-status-update.py",
     "mutate": True, "confirm": True, "args": [
         {"name": "rm_id", "label": "Ticket", "type": "rm_id", "required": True, "positional": True},
         {"name": "status", "label": "Nouveau statut", "type": "enum", "required": True,
          "positional": True, "choices": _PM_STATUSES},
         {"name": "note", "label": "Note (compte-rendu)", "type": "text", "flag": "--note"},
         {"name": "close_reason", "label": "Motif de fermeture", "type": "enum",
          "flag": "--close-reason", "choices": _PM_CLOSE_REASONS},
         {"name": "allow_unchecked", "label": "Forcer malgré checklist non cochée",
          "type": "bool", "flag": "--allow-unchecked"},
         {"name": "allow_unmerged", "label": "Forcer malgré branche non mergée (RM2319)",
          "type": "bool", "flag": "--allow-unmerged"},
     ]},
    {"name": "task-comment", "label": "Commenter un ticket",
     "category": "ticket", "script": "pm-task-comment.py",
     "mutate": True, "args": [
         {"name": "rm_id", "label": "Ticket", "type": "rm_id", "required": True, "positional": True},
         {"name": "note", "label": "Note", "type": "text", "required": True, "flag": "--note"},
     ]},
    {"name": "task-link", "label": "Lier deux tickets",
     "category": "ticket", "script": "pm-task-link.py",
     "mutate": True, "args": [
         {"name": "action", "type": "enum", "required": True, "positional": True,
          "choices": ["add"]},
         {"name": "rm_id", "label": "Ticket", "type": "rm_id", "required": True, "positional": True},
         {"name": "target", "label": "Ticket cible", "type": "rm_id", "required": True, "positional": True},
         {"name": "type", "label": "Type de lien", "type": "enum", "flag": "--type",
          "choices": ["relates", "depends_on", "blocks"]},
     ]},
    {"name": "conso-report", "label": "Rapport de consommation tokens/coût",
     "category": "reporting", "script": "pm-conso-report.py",
     "mutate": False, "args": [
         {"name": "by", "label": "Grouper par", "type": "enum", "flag": "--by",
          "choices": ["project", "client", "type", "status", "day", "week", "month"]},
         {"name": "entity", "label": "Entité", "type": "text", "flag": "--entity", "max_len": 64},
         {"name": "project", "label": "Projet", "type": "text", "flag": "--project", "max_len": 64},
         {"name": "top", "label": "Top N", "type": "int", "flag": "--top"},
         {"name": "json", "label": "Sortie JSON", "type": "bool", "flag": "--json"},
     ]},
    # Menu Nouveau projet / client (RM2212) — mutations structurantes : confirm,
    # timeouts larges (Redmine + GitLab + arbo + symlinks). Slugs validés par les
    # scripts eux-mêmes ; ici on borne juste la longueur.
    {"name": "client-new", "label": "Créer un client / produit / self",
     "category": "projet", "script": "pm-client-new.py", "mutate": True,
     "confirm": True, "timeout": 300, "args": [
         {"name": "slug", "label": "Slug", "type": "text", "required": True,
          "flag": "--slug", "max_len": 48},
         {"name": "name", "label": "Nom affiché", "type": "text", "required": True,
          "flag": "--name", "max_len": 96},
         {"name": "type", "label": "Type d'entité", "type": "enum", "flag": "--type",
          "choices": ["client", "product", "self"]},
         {"name": "gitlab_group", "label": "Groupe GitLab (ex. iprospective/nextcloud)",
          "type": "text", "flag": "--gitlab-group", "max_len": 96},
         {"name": "contact_name", "label": "Contact (nom)", "type": "text",
          "flag": "--contact-name", "max_len": 96},
         {"name": "contact_email", "label": "Contact (email)", "type": "text",
          "flag": "--contact-email", "max_len": 96},
     ]},
    {"name": "project-new", "label": "Créer un projet PM (Redmine + arbo + liens + bootstrap)",
     "category": "projet", "script": "pm-project-new.py", "mutate": True,
     "confirm": True, "timeout": 600, "args": [
         {"name": "client", "label": "Client (slug existant)", "type": "text",
          "required": True, "flag": "--client", "max_len": 48},
         {"name": "slug", "label": "Slug du projet", "type": "text", "required": True,
          "flag": "--slug", "max_len": 48},
         {"name": "name", "label": "Nom affiché", "type": "text", "required": True,
          "flag": "--name", "max_len": 96},
         {"name": "workspace", "label": "Workspace de code (chemin /zfs/workspaces/…)",
          "type": "path", "required": True, "flag": "--workspace"},
         # l'un des deux est requis (XOR contrôlé par le script) :
         {"name": "redmine_parent", "label": "Projet Redmine parent (slug) — OU id existant ci-dessous",
          "type": "text", "flag": "--redmine-parent", "max_len": 64},
         {"name": "existing_redmine_id", "label": "Id projet Redmine existant (si déjà créé)",
          "type": "text", "flag": "--existing-redmine-id", "max_len": 16},
         {"name": "description", "label": "Description", "type": "text",
          "flag": "--description"},
         {"name": "with_environments", "label": "Créer environments.md",
          "type": "bool", "flag": "--with-environments"},
         {"name": "no_bootstrap", "label": "Sans bootstrap", "type": "bool",
          "flag": "--no-bootstrap"},
         {"name": "dry_run", "label": "Dry-run (prévisualiser)", "type": "bool",
          "flag": "--dry-run"},
     ]},
    # Console de test (RM2210) : déploiement/démontage de l'env de session d'un
    # ticket. Le workspace est résolu CÔTÉ SERVEUR depuis le ticket (spec
    # `server: workspace_of_rm`) — jamais un chemin fourni par le client.
    {"name": "env-deploy", "label": "Déployer la branche du ticket dans l'env PARTAGÉ",
     "category": "env", "script": "pm-env-deploy.py", "mutate": True, "confirm": True,
     "timeout": 300, "args": [
         {"name": "action", "type": "enum", "required": True, "positional": True,
          "choices": ["deploy", "restore"]},
         {"name": "rm_id", "label": "Ticket", "type": "rm_id", "required": True, "positional": True},
         {"name": "workspace", "server": "workspace_of_rm", "positional": True},
         {"name": "env", "label": "Env partagé (défaut test)", "type": "text",
          "flag": "--env", "max_len": 32},
         {"name": "force", "label": "Forcer (worktree sale)", "type": "bool", "flag": "--force"},
     ]},
    {"name": "env-session-create", "label": "Déployer la branche du ticket en env de test",
     "category": "env", "script": "pm-env-session.py", "mutate": True, "confirm": True,
     "timeout": 600, "args": [
         {"name": "action", "type": "enum", "required": True, "positional": True,
          "choices": ["create"]},
         {"name": "rm_id", "label": "Ticket", "type": "rm_id", "required": True, "positional": True},
         {"name": "workspace", "server": "workspace_of_rm", "positional": True},
         {"name": "db_clone", "label": "Cloner la BDD", "type": "bool", "flag": "--db-clone"},
         {"name": "no_db_clone", "label": "BDD partagée", "type": "bool", "flag": "--no-db-clone"},
     ]},
    {"name": "env-session-teardown", "label": "Démonter l'env de test du ticket",
     "category": "env", "script": "pm-env-session.py", "mutate": True, "confirm": True,
     "timeout": 600, "args": [
         {"name": "action", "type": "enum", "required": True, "positional": True,
          "choices": ["teardown"]},
         {"name": "rm_id", "label": "Ticket", "type": "rm_id", "required": True, "positional": True},
         {"name": "workspace", "server": "workspace_of_rm", "positional": True},
         {"name": "keep_db", "label": "Conserver le clone BDD", "type": "bool", "flag": "--keep-db"},
         {"name": "force", "label": "Forcer (modifs non commitées)", "type": "bool", "flag": "--force"},
     ]},
]
_PM_SCRIPT_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.py$")
PM_RUNS_LOG = LOG_DIR / "pm-runs.jsonl"
ANSWERS_LOG = LOG_DIR / "answers.jsonl"   # RM2302 : réponses « Oui » envoyées (socle RM2305)


def _probe_env(host: str, env: str) -> tuple:
    """Vivacité d'un env de session (RM2229) → (live: bool, reason: str).

    L'existence du worktree `envs/*-rm<id>` ne prouve PAS que l'env est servi :
    un vhost absent retombe sur le site Apache par défaut (200 trompeur), un
    env sans setup appli répond 500. Deux étages :
      1. GET /pm-env.txt == nom d'env — canari statique posé par
         pm-env-session dans le docroot : prouve « ce vhost sert CE worktree » ;
      2. GET / < 500 — l'appli elle-même répond.
    Connexion sur 127.0.0.1 + en-tête Host (surchargable KARL_PROBE_ADDR) :
    karl-agent tourne DANS le conteneur dev, où Apache est local et où les
    noms `*.lxc` ne résolvent pas (dnsmasq est côté hôte).
    Timeout court : appelé en parallèle sur la file de test."""
    import http.client
    addr = os.environ.get("KARL_PROBE_ADDR", "127.0.0.1")
    try:
        c = http.client.HTTPConnection(addr, 80, timeout=1.5)
        c.request("GET", "/pm-env.txt", headers={"Host": host})
        r = c.getresponse()
        body = r.read(256).decode("utf-8", "replace").strip()
        r.read()  # draine avant de réutiliser la connexion
        if r.status != 200 or body != env:
            c.close()
            if r.status == 200:
                return False, "vhost absent (site par défaut servi)"
            return False, (f"canari absent (HTTP {r.status}) — "
                           "env non initialisé, re-déployer")
        c.request("GET", "/", headers={"Host": host})
        r2 = c.getresponse()
        r2.read()
        c.close()
        if r2.status >= 500:
            return False, (f"env servi mais appli en erreur (HTTP {r2.status})"
                           " — re-déployer")
        return True, ""
    except OSError as exc:
        return False, f"injoignable ({exc.__class__.__name__})"


def op_test_queue(qs: dict) -> list:
    """File de test (RM2210) : tickets a_tester_dev / a_tester_demandeur enrichis
    (branche du ticket, env de session monté ET vivant, déployabilité)."""
    out = []
    for st in ("a_tester_demandeur", "a_tester_dev"):
        out += op_search(status=st, client=qs.get("client"),
                         project=qs.get("project"), limit=100)
    for e in out:
        tf = _find_task_file(str(e["rm_id"]))
        if not tf:
            continue
        try:
            fm = _parse_frontmatter(tf.read_text(encoding="utf-8"))
        except OSError:
            fm = {}
        git = fm.get("git") if isinstance(fm.get("git"), dict) else {}
        e["branch"] = git.get("branch")
        e["updated"] = str(fm.get("updated") or "")
        ws = _resolve_workspace(tf.parent.parent)
        # déployable = workspace au layout RM1993 (repos/ présent) ; l'existence
        # d'un bloc runtime: décide vhost/BDD mais un env code seul reste utile
        e["deployable"] = bool(ws and (ws / "repos").is_dir())
        env = None
        if ws:
            hits = sorted((ws / "envs").glob(f"*-rm{e['rm_id']}")) if (ws / "envs").is_dir() else []
            env = hits[0].name if hits else None
        e["env"] = env
        e["test_host"] = f"{env}.lxc" if env else None
    # Sonde de vivacité en parallèle (RM2229) : un worktree présent n'est un
    # env de test QUE si son vhost sert bien ce worktree et que l'appli répond.
    to_probe = [e for e in out if e.get("env")]
    if to_probe:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futs = {pool.submit(_probe_env, e["test_host"], e["env"]): e
                    for e in to_probe}
            for fut in concurrent.futures.as_completed(futs):
                e = futs[fut]
                try:
                    e["env_live"], e["env_reason"] = fut.result()
                except Exception as exc:  # défensif : la file doit toujours rendre
                    e["env_live"], e["env_reason"] = False, f"sonde en erreur ({exc})"
    out.sort(key=lambda r: (r["status"] != "a_tester_demandeur", r.get("updated") or ""),
             )
    return out


# ── Réglages contrôlés (RM2213) ──────────────────────────────────────────────
# Whitelist déclarative de clés éditables depuis le cockpit. Deux cibles :
#  - conf   → écrit dans pm.config.local.yml (surcharge gitignorée, NORMS) —
#             le fichier canonique commenté n'est JAMAIS réécrit ;
#  - tarifs → édition CIBLÉE de la ligne dans pm.pricing.yml (commentaires
#             et structure intacts ; refus si la ligne n'existe pas).
_PM_SETTINGS_CONF = [
    {"key": "conf:notifications.email_enabled", "label": "Notifs mail à chaque changement de statut",
     "group": "Conf PM", "type": "bool", "path": ["notifications", "email_enabled"]},
    {"key": "conf:git.autocommit", "label": "Auto-commit des écritures PM",
     "group": "Conf PM", "type": "bool", "path": ["git", "autocommit"]},
    {"key": "conf:git.autopush", "label": "Auto-push après commit PM",
     "group": "Conf PM", "type": "bool", "path": ["git", "autopush"]},
    {"key": "conf:env_runtime.auto_session", "label": "Env de session auto à la prise de ticket",
     "group": "Conf PM", "type": "bool", "path": ["env_runtime", "auto_session"]},
]
_PRICE_FIELDS = ("input_per_mtok_usd", "output_per_mtok_usd",
                 "cache_read_per_mtok_usd", "cache_creation_per_mtok_usd")


def _pricing_file() -> Path:
    return REPO_ROOT / "pm.pricing.yml"


def _conf_merged() -> dict:
    out = {}
    for name in ("pm.config.yml", "pm.config.local.yml"):
        try:
            cfg = yaml_safe_load((REPO_ROOT / name).read_text(encoding="utf-8")) or {}
        except OSError:
            continue
        for k, v in cfg.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k].update(v)
            else:
                out[k] = v
    return out


def yaml_safe_load(text):
    import yaml
    return yaml.safe_load(text)


def _pm_settings() -> list:
    """Spec + valeurs courantes. Tarifs générés dynamiquement depuis le fichier."""
    out = []
    conf = _conf_merged()
    for e in _PM_SETTINGS_CONF:
        cur = conf
        for part in e["path"]:
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                break
        out.append({**e, "value": bool(cur)})
    try:
        pricing = yaml_safe_load(_pricing_file().read_text(encoding="utf-8")) or {}
    except OSError:
        pricing = {}
    h = pricing.get("human_hourly_rate_eur")
    out.append({"key": "pricing:human_hourly_rate_eur", "label": "Taux horaire humain (€)",
                "group": "Tarifs", "type": "number", "min": 10, "max": 500, "value": h})
    for model, fields in sorted((pricing.get("models") or {}).items()):
        for f in _PRICE_FIELDS:
            if isinstance(fields, dict) and f in fields:
                out.append({"key": f"pricing:models.{model}.{f}",
                            "label": f"{model} · {f.replace('_per_mtok_usd', '')} ($/MTok)",
                            "group": "Tarifs modèles", "type": "number",
                            "min": 0, "max": 1000, "value": fields[f]})
    return out


def op_pm_settings_set(payload: dict) -> dict:
    key = str(payload.get("key") or "")
    spec = next((e for e in _pm_settings() if e["key"] == key), None)
    if not spec:
        raise ApiError(400, f"clé inconnue/hors whitelist : {key!r}")
    if payload.get("confirm") is not True:
        raise ApiError(400, "confirmation requise (confirm: true)")
    raw = payload.get("value")
    if spec["type"] == "bool":
        val = raw in (True, "1", "true", "on")
    else:
        try:
            val = float(raw)
        except (TypeError, ValueError):
            raise ApiError(400, f"{key} : nombre attendu")
        if not (spec.get("min", 0) <= val <= spec.get("max", 1e9)):
            raise ApiError(400, f"{key} : hors bornes [{spec.get('min')}..{spec.get('max')}]")

    if key.startswith("conf:"):
        import yaml
        lp = REPO_ROOT / "pm.config.local.yml"
        try:
            local = yaml_safe_load(lp.read_text(encoding="utf-8")) or {}
        except OSError:
            local = {}
        cur = local
        for part in spec["path"][:-1]:
            cur = cur.setdefault(part, {})
        cur[spec["path"][-1]] = val
        lp.write_text("# Surcharge locale (gitignorée) — clés posées via le cockpit (RM2213).\n"
                      + yaml.safe_dump(local, allow_unicode=True, sort_keys=False),
                      encoding="utf-8")
    else:  # pricing: édition ciblée de la ligne existante
        pf = _pricing_file()
        text = pf.read_text(encoding="utf-8")
        if key == "pricing:human_hourly_rate_eur":
            pat = re.compile(r"^(human_hourly_rate_eur:\s*)[0-9.]+\s*$", re.M)
        else:
            m = re.match(r"pricing:models\.(.+)\.([a-z_]+)$", key)
            model, field = m.group(1), m.group(2)
            block = re.search(rf"^  {re.escape(model)}:\n((?:    .*\n)+)", text, re.M)
            if not block:
                raise ApiError(400, f"modèle {model} introuvable dans pm.pricing.yml")
            pat = re.compile(rf"^(    {re.escape(field)}:\s*)[0-9.]+\s*$", re.M)
            seg = block.group(0)
            if not pat.search(seg):
                raise ApiError(400, f"champ {field} introuvable pour {model}")
            new_seg = pat.sub(lambda mm: f"{mm.group(1)}{val:.2f}", seg, count=1)
            pf.write_text(text.replace(seg, new_seg, 1), encoding="utf-8")
            _journal_setting(key, val)
            return {"key": key, "value": val, "ok": True}
        if not pat.search(text):
            raise ApiError(400, "ligne human_hourly_rate_eur introuvable")
        pf.write_text(pat.sub(lambda mm: f"{mm.group(1)}{val:g}", text, count=1), encoding="utf-8")
    _journal_setting(key, val)
    return {"key": key, "value": val, "ok": True}


def _journal_setting(key, val):
    try:
        PM_RUNS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with PM_RUNS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "name": "settings", "args": {"key": key, "value": val},
                                "rc": 0}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _pm_commands() -> list:
    f = COCKPIT_DIR / "pm-commands.json"
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, list) and all(
                    isinstance(c, dict) and c.get("name") and c.get("script")
                    for c in data):
                return data
        except (ValueError, OSError):
            pass
    return _PM_COMMANDS_DEFAULT


def _pm_validate_arg(spec: dict, value) -> str:
    """Valide/normalise UNE valeur selon sa spec. ApiError 400 si invalide."""
    name, typ = spec["name"], spec.get("type", "text")
    if typ == "bool":
        return "1" if value in (True, "1", "true", "on") else ""
    s = str(value).strip()
    if s.startswith("-"):
        raise ApiError(400, f"arg {name} : valeur commençant par '-' refusée")
    if typ == "rm_id":
        if not re.fullmatch(r"\d{1,8}", s):
            raise ApiError(400, f"arg {name} : RM-id numérique attendu")
    elif typ == "int":
        if not re.fullmatch(r"\d{1,9}", s):
            raise ApiError(400, f"arg {name} : entier attendu")
    elif typ == "enum":
        if s not in (spec.get("choices") or []):
            raise ApiError(400, f"arg {name} : valeur hors choix {spec.get('choices')}")
    elif typ == "path":
        # chemin borné aux workspaces — jamais de chemin arbitraire depuis le web
        if ".." in s or not s.startswith("/zfs/workspaces/"):
            raise ApiError(400, f"arg {name} : chemin sous /zfs/workspaces/ attendu")
        if len(s) > 200:
            raise ApiError(400, f"arg {name} : chemin trop long")
    elif typ == "text":
        if len(s) > int(spec.get("max_len") or 4000):
            raise ApiError(400, f"arg {name} : trop long (max {spec.get('max_len', 4000)})")
        if "\x00" in s:
            raise ApiError(400, f"arg {name} : caractère nul refusé")
    else:
        raise ApiError(400, f"arg {name} : type de spec inconnu {typ!r}")
    return s


def op_pm_run(payload: dict) -> dict:
    """Exécute une commande du catalogue (allowlist) — argv strict, sans shell."""
    name = str(payload.get("name") or "")
    cmd = next((c for c in _pm_commands() if c.get("name") == name), None)
    if not cmd:
        raise ApiError(400, f"commande inconnue : {name!r} (voir GET /pm/commands)")
    if cmd.get("confirm") and payload.get("confirm") is not True:
        raise ApiError(400, f"commande {name} : confirmation requise (confirm: true)")
    script_name = cmd["script"]
    if not _PM_SCRIPT_RE.match(script_name):
        raise ApiError(500, f"catalogue invalide : script {script_name!r}")
    script = (REPO_ROOT / "scripts" / script_name).resolve()
    if not str(script).startswith(str(REPO_ROOT / "scripts")) or not script.is_file():
        raise ApiError(500, f"script introuvable : {script_name}")

    given = payload.get("args") or {}
    if not isinstance(given, dict):
        raise ApiError(400, "args : objet {nom: valeur} attendu")
    # les args `server:` sont calculés ici — un client qui les fournit est rejeté
    known = {a["name"] for a in cmd.get("args") or [] if not a.get("server")}
    unknown = set(given) - known
    if unknown:
        raise ApiError(400, f"args inconnus pour {name} : {sorted(unknown)}")
    positionals, flags = [], []
    for spec in cmd.get("args") or []:
        aname = spec["name"]
        if spec.get("server") == "workspace_of_rm":
            # workspace du projet du ticket, résolu depuis le MD local
            rmv = str(given.get("rm_id") or "")
            tf = _find_task_file(rmv) if rmv.isdigit() else None
            ws = _resolve_workspace(tf.parent.parent) if tf else None
            if not ws:
                raise ApiError(400, f"workspace introuvable pour RM{rmv or '?'} "
                                    "(ticket inconnu en local ou projet sans workspace)")
            positionals.append(str(ws))
            continue
        if aname not in given or given[aname] in (None, ""):
            if spec.get("required"):
                raise ApiError(400, f"arg requis manquant : {aname}")
            continue
        val = _pm_validate_arg(spec, given[aname])
        if spec.get("type") == "bool":
            if val:
                flags.append(spec["flag"])
            continue
        if spec.get("positional"):
            positionals.append(val)
        else:
            flags += [spec["flag"], val]
    argv = [sys.executable, str(script)] + positionals + flags

    timeout_s = int(cmd.get("timeout") or 300)
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s,
                           cwd=str(REPO_ROOT))
    except subprocess.TimeoutExpired:
        raise ApiError(500, f"{name} : timeout ({timeout_s} s)")
    if cmd.get("mutate"):
        try:
            PM_RUNS_LOG.parent.mkdir(parents=True, exist_ok=True)
            with PM_RUNS_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "name": name, "args": given, "rc": r.returncode,
                }, ensure_ascii=False) + "\n")
        except OSError:
            pass  # le journal ne doit jamais faire échouer le run
    return {"name": name, "rc": r.returncode, "ok": r.returncode == 0,
            "stdout": r.stdout[-30000:], "stderr": r.stderr[-10000:]}


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
                # chips d'actions (RM1893 §2) — texte en langage naturel injecté
                # via /send ; rien de sensible (le client peut déjà /send librement).
                "actions": _actions_catalog(),
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
            if path == "/session-registry":
                return self._send_json(200, _registry_view())
            if path == "/pm/commands":
                return self._send_json(200, {"commands": _pm_commands()})
            if path == "/pm/settings":
                return self._send_json(200, {"settings": _pm_settings()})
            if path == "/pm/test-queue":
                qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                return self._send_json(200, {"queue": op_test_queue(qs)})
            if path == "/resumable":
                qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                return self._send_json(200, {"resumable": op_resumable(qs)})
            if path.startswith("/capture/"):
                rm_id = path[len("/capture/"):]
                qs = parse_qs(parsed.query)
                lines = int(qs["lines"][0]) if "lines" in qs else None
                return self._send_text(200, op_capture(rm_id, lines))
            if path == "/buffer":
                return self._send_text(200, op_buffer())
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
            if path == "/approve":
                return self._send_json(200, op_approve(payload))
            if path == "/approve-all":
                return self._send_json(200, op_approve_all(payload))
            if path == "/auto-yes":
                return self._send_json(200, op_auto_yes(payload))
            if path == "/kill":
                return self._send_json(200, op_kill(payload))
            if path == "/monitor":
                return self._send_json(201, op_monitor(payload))
            if path == "/unmonitor":
                return self._send_json(200, op_unmonitor(payload))
            if path == "/layout":
                return self._send_json(200, op_layout(payload))
            if path == "/pm/run":
                return self._send_json(200, op_pm_run(payload))
            if path == "/pm/settings":
                return self._send_json(200, op_pm_settings_set(payload))
            return self._send_json(404, {"error": f"route inconnue : {path}"})
        except ApiError as e:
            return self._send_json(e.code, {"error": e.msg})
        except Exception as e:  # noqa: BLE001
            return self._send_json(500, {"error": f"{type(e).__name__}: {e}"})

    # -- SSE : tail du log pipe-pane (octets de terminal bruts) --
    def _stream(self, rm_id: str):
        if not _valid_sid(rm_id):
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

    # RM2327 : boucle auto-oui (daemon — meurt avec le serveur)
    threading.Thread(target=_auto_yes_loop, name="auto-yes", daemon=True).start()

    sys.stderr.write(
        f"karl-agent en écoute sur http://{HOST}:{PORT} "
        f"(prefix={SESSION_PREFIX}, engine={DEFAULT_ENGINE}, "
        f"auth={'on' if AUTH_TOKEN else 'off'})\n"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
