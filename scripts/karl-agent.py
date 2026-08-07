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
                                   engines, resume_engines, models}  (public en mode token seul ;
                                   gated dès que Basic est configuré, RM2139 ;
                                   models = clés du catalogue par moteur, RM1941)
  POST /auth/login {user, pass, device_name?}
                                → {token, device_id, user, admin} — identifiants
                                  (superadmin .env OU compte var/karl-users.json)
                                  → token d'appareil 256 bits, mémorisé côté
                                  serveur en SHA-256 (RM2334). Sans auth préalable.
  GET  /auth/whoami             → {user, admin, mode, device_id?}
  GET  /auth/devices            → {devices:[…]} (les siens ; admin : tous)
  DELETE /auth/devices/<id>     → révocation (soi-même ; admin : tous)
  GET  /auth/users              → {users:[…]} (admin)
  POST /auth/users {user, pass} → création compte normal (admin)
  PUT  /auth/users/<name> {pass?, disabled?}
                                → maj mdp / activation ; disabled révoque les
                                  appareils du compte (admin)
  DELETE /auth/users/<name>     → suppression + révocation appareils (admin)
  GET  /health                  → {status, sessions, tmux}
  GET  /sessions[?engine=&client=&project=&ghosts=0]
                                → [{rm_id, tmux, created, attached, engine?,
                                   session_id?, client?, project?,
                                   registry?{seq, machine, created, branches[],
                                   worktrees[]}, registry_conflicts?[]}]
                                  (RM1939 ; registre pm_session RM2166)
                                  + entrées « fantômes » des jeux enregistrés
                                  (ghost:true, state:"ghost", resumable,
                                  restart:auto|idle) : des sessions reprises EN
                                  IDLE, sans processus — `ghosts=0` les exclut.
                                  Les sessions réglées `restart:auto` (défaut des
                                  [WIP]) sont, elles, relancées au démarrage ; une
                                  session [DONE] terminée sort du jeu  (RM2427)
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
  GET  /usage/<rm_id>           → {usage:{input,output,cache_read,cache_creation,
                                  total,turns,context_last}} conso tokens live de
                                  la session, entrée/sortie séparées (RM2373)
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
  POST /mr/deliver {rm_id, confirm}
                                → {rc, ok, branch, target, stdout, stderr} —
                                  livre la branche du ticket (MR + merge → dev)
                                  pour débloquer un verdict bloqué par la merge
                                  gate RM2319 (RM2355)
  GET  /stream/<rm_id>          → text/event-stream (SSE, tail du pipe-pane)
  POST /monitor   {rm_id, preset, orientation?} → split-window moniteur (RM1893 §3)
  POST /unmonitor {rm_id}                        → ferme le pane moniteur actif/dernier
  POST /layout    {rm_id, layout}                → réarrange les panes (RM1893 §3)
  POST /kill   {rm_id}          → {rm_id, killed:true}
  POST /disposition {rm_id, disposition}
                                → {rm_id, disposition} — marque manuelle d'une
                                  session (a_traiter|parke|termine ; vide = efface).
                                  Raffine `idle` côté UI, persistée keys/ (RM2515)

Lancement :
    python3 scripts/karl-agent.py            # bind 127.0.0.1:9876
    KARL_AGENT_PORT=9999 python3 scripts/karl-agent.py
"""
import base64
import hashlib
import hmac
import json
import secrets
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
HOST = os.environ.get("KARL_AGENT_HOST", "127.0.0.1")   # RM2356 : instances de test liées ailleurs
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
# RM2539 — CONTRAT DE REPRISE, par moteur. La reprise était codée en dur sur
# claude (`--resume <uuid>` + transcripts JSONL) ; un moteur la déclare ici ou
# n'en a pas (refus explicite, jamais un 501 opaque) :
#   resume_flag : drapeau qui reprend une conversation existante
#   sid_re      : grammaire des identifiants de CE moteur — claude émet des UUID,
#                 opencode des `ses_…` que la regex UUID rejetait en amont
#   store       : d'où viennent la conversation et ses méta ("claude_jsonl" =
#                 transcripts ; "opencode_db" = base SQLite du moteur)
ENGINES = {
    "claude": {
        "cmd": os.environ.get("KARL_AGENT_SPAWN_CMD", "claude"),
        "ready_markers": ("for shortcuts", "accept edits", "for agents", "❯"),
        "model_flag": "--model",
        "resume_flag": "--resume",
        "sid_re": r"^[0-9a-fA-F][0-9a-fA-F-]{7,63}$",
        "store": "claude_jsonl",
    },
    "opencode": {
        "cmd": os.environ.get("KARL_AGENT_OPENCODE_CMD", "opencode"),
        "ready_markers": ("Ask anything", "tab agents", "ctrl+p commands"),
        "model_flag": "--model",          # format provider/model
        # `opencode --session <id>` reprend la conversation (vérifié v1.18.13) ;
        # `--continue` reprend la dernière — sans intérêt ici, on vise un id précis.
        "resume_flag": "--session",
        "sid_re": r"^ses_[A-Za-z0-9]{6,64}$",
        "store": "opencode_db",
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
        # RM2547 : `vibe --resume <id>` reprend (vérifié v2.23.3) — SANS id, il
        # ouvre un sélecteur interactif, que le cockpit ne doit jamais déclencher
        # (il vise toujours une session précise). ⚠ vibe émet des UUID, comme
        # claude : la forme de l'id NE distingue pas les deux moteurs — c'est le
        # store par session (`_engine_of_session`, RM2536) qui tranche.
        "resume_flag": "--resume",
        "sid_re": r"^[0-9a-fA-F][0-9a-fA-F-]{7,63}$",
        "store": "vibe_files",
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

# État de session partageable (RM2385) — distinct des logs d'instance. Le store
# sessions⇄tickets (keys/, sessions/, tasks/) est une donnée d'ÉTAT que plusieurs
# instances karl-agent du même utilisateur peuvent vouloir partager (p. ex. une
# instance de test de branche qui doit résoudre les sessions live pour /usage et
# /outline — cf. pm-cockpit-test-env). Les LOGS d'instance (pipe-pane, pm-runs,
# answers) restent, eux, sous LOG_DIR. Défaut : STATE_DIR = LOG_DIR ⇒ comportement
# prod strictement inchangé.
STATE_DIR = Path(os.environ.get("KARL_AGENT_STATE_DIR") or LOG_DIR)

# ── Store sessions ⇄ tickets (RM1939) — instance-local, JAMAIS committé ──────
# Modèle n-m : une session traverse plusieurs tickets, un ticket est repris dans
# plusieurs sessions. Deux dimensions + jonction :
#   sessions/<engine>/<session_id>.json      entité SESSION (projet-agnostique)
#   tasks/<client>/<projet>/RM<id>-<n>.json  jonction (n = occurrence, max+1)
# Un session-id n'a de sens que sur CETTE machine (fédération : jamais en git).
SESS_DIR = STATE_DIR / "sessions"
RUNS_DIR = STATE_DIR / "tasks"
# RM2532 (vocal V2 L1) : TTS serveur Piper. Détecté via un venv runtime + modèles
# (installés par scripts/karl-voice-setup.sh). Absent → /voice/caps annonce tts:false
# et le cockpit reste sur la synthèse navigateur (repli, aucune régression).
VOICE_DIR = Path(os.environ.get("KARL_VOICE_DIR") or (
    Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "karl-agent" / "voice"))
PIPER_BIN = Path(os.environ.get("KARL_PIPER_BIN") or (VOICE_DIR / "venv" / "bin" / "piper"))
PIPER_MODELS = Path(os.environ.get("KARL_PIPER_MODELS") or (VOICE_DIR / "models"))
_TTS_PREFIX = {"fr": "fr_", "en": "en_"}   # préfixe de nom de modèle Piper par langue
# RM2533 (vocal V2 L2) : STT via le sidecar karl-whisper (faster-whisper chaud,
# service systemd user dédié — cf. scripts/karl-whisper-sidecar.py). Injoignable →
# /voice/caps annonce stt:false et le cockpit reste sur la Web Speech API (repli).
WHISPER_URL = (os.environ.get("KARL_WHISPER_URL") or "http://127.0.0.1:9877").rstrip("/")
STT_MAX_BYTES = int(float(os.environ.get("KARL_STT_MAX_MB") or 25) * 1024 * 1024)
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

# ── Comptes utilisateurs + tokens d'appareil (RM2334) ────────────────────────
# Modèle : le SUPERADMIN reste dans la conf (.env, couple KARL_WEB_USER/PASS
# ci-dessus) — amorçage garanti, insupprimable via l'API. Les comptes normaux
# vivent côté serveur (var/karl-users.json, hash PBKDF2 salé). Un login réussi
# émet un token d'appareil aléatoire dont SEUL le SHA-256 est mémorisé serveur
# (var/karl-devices.json) : le client garde le token, jamais le mot de passe.
# Les deux fichiers sont instance-locaux (var/ gitignoré), écrits en 0600.
AUTH_VAR_DIR = Path(os.environ.get("KARL_AGENT_AUTH_DIR") or (REPO_ROOT / "var"))
USERS_FILE = AUTH_VAR_DIR / "karl-users.json"
DEVICES_FILE = AUTH_VAR_DIR / "karl-devices.json"
PBKDF2_ITERATIONS = 310_000  # recommandation OWASP pour PBKDF2-HMAC-SHA256
_AUTH_LOCK = threading.Lock()          # ThreadingHTTPServer → sérialiser les I/O
_LOGIN_FAILS: dict = {}                # ip → {"count": n, "until": ts} (mémoire)
_LOGIN_LOCK_BASE_S = 2                 # 3 échecs → 2 s, puis ×2, plafonné
_LOGIN_LOCK_MAX_S = 300


def _auth_load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _auth_save(path: Path, data: dict) -> None:
    """Écriture atomique (tmp + rename) en 0600 — jamais de secret en clair
    dedans (hashes uniquement), mais autant restreindre quand même."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _pbkdf2(password: str, salt_hex=None, iterations: int = PBKDF2_ITERATIONS) -> dict:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {"salt": salt.hex(), "iterations": iterations, "hash": dk.hex()}


def _password_ok(password: str, rec: dict) -> bool:
    try:
        ref = _pbkdf2(password, rec["salt"], int(rec["iterations"]))
        return hmac.compare_digest(ref["hash"], rec["hash"])
    except (KeyError, TypeError, ValueError):
        return False


_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")


def _issue_device(user: str, admin: bool, device_name: str) -> dict:
    """Émet un token d'appareil ; seul son SHA-256 est mémorisé serveur."""
    token = secrets.token_urlsafe(32)  # 256 bits
    device_id = uuid.uuid4().hex[:12]
    with _AUTH_LOCK:
        devices = _auth_load(DEVICES_FILE)
        devices[device_id] = {
            "user": user, "admin": bool(admin),
            "device_name": (device_name or "appareil")[:80],
            "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "last_seen": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        _auth_save(DEVICES_FILE, devices)
    return {"token": token, "device_id": device_id, "user": user, "admin": bool(admin)}


def _device_auth(token: str):
    """(device_id, record) si le token correspond à un appareil enregistré."""
    if not token:
        return None
    want = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with _AUTH_LOCK:
        devices = _auth_load(DEVICES_FILE)
        for did, rec in devices.items():
            if hmac.compare_digest(rec.get("token_sha256", ""), want):
                # last_seen : maj throttlée (≤ 1 écriture / 5 min / appareil)
                now = time.strftime("%Y-%m-%dT%H:%M:%S")
                if rec.get("last_seen", "")[:15] != now[:15]:
                    rec["last_seen"] = now
                    _auth_save(DEVICES_FILE, devices)
                return did, rec
    return None


def _revoke_devices(device_ids=None, user=None) -> int:
    with _AUTH_LOCK:
        devices = _auth_load(DEVICES_FILE)
        doomed = [d for d, r in devices.items()
                  if (device_ids and d in device_ids) or (user and r.get("user") == user)]
        for d in doomed:
            devices.pop(d, None)
        if doomed:
            _auth_save(DEVICES_FILE, devices)
    return len(doomed)


def _login_throttled(ip: str):
    """Anti-bruteforce minimal : verrou progressif par IP. Renvoie le nombre de
    secondes restantes si l'IP est verrouillée, sinon 0."""
    rec = _LOGIN_FAILS.get(ip)
    if rec and rec["until"] > time.time():
        return int(rec["until"] - time.time()) + 1
    return 0


def _login_failed(ip: str) -> None:
    rec = _LOGIN_FAILS.setdefault(ip, {"count": 0, "until": 0.0})
    rec["count"] += 1
    if rec["count"] >= 3:
        lock = min(_LOGIN_LOCK_BASE_S * (2 ** (rec["count"] - 3)), _LOGIN_LOCK_MAX_S)
        rec["until"] = time.time() + lock
    # journalisation SANS le mot de passe (tripwire secrets)
    sys.stderr.write(f"auth: échec login depuis {ip} (#{rec['count']})\n")


def _login_succeeded(ip: str) -> None:
    _LOGIN_FAILS.pop(ip, None)


def op_auth_login(payload: dict, ip: str) -> dict:
    wait = _login_throttled(ip)
    if wait:
        raise ApiError(429, f"trop d'échecs — réessayer dans {wait} s")
    user = str(payload.get("user") or "").strip()
    password = str(payload.get("pass") or "")
    device_name = str(payload.get("device_name") or "")
    if not user or not password:
        raise ApiError(400, "user et pass requis")
    if BASIC_USER is None and not _auth_load(USERS_FILE):
        raise ApiError(400, "auth par identifiants non configurée "
                            "(ni KARL_WEB_USER/PASS ni compte serveur)")
    # 1) superadmin de la conf (.env) — toujours valide, insupprimable
    if (BASIC_USER is not None and BASIC_PASS is not None
            and hmac.compare_digest(user, BASIC_USER)
            and hmac.compare_digest(password, BASIC_PASS)):
        _login_succeeded(ip)
        return _issue_device(user, admin=True, device_name=device_name)
    # 2) comptes normaux (store serveur)
    with _AUTH_LOCK:
        rec = _auth_load(USERS_FILE).get(user)
    if rec and not rec.get("disabled") and _password_ok(password, rec):
        _login_succeeded(ip)
        return _issue_device(user, admin=False, device_name=device_name)
    _login_failed(ip)
    raise ApiError(401, "identifiants invalides")


def op_auth_users_list() -> dict:
    with _AUTH_LOCK:
        users = _auth_load(USERS_FILE)
        devices = _auth_load(DEVICES_FILE)
    per_user: dict = {}
    for rec in devices.values():
        per_user[rec.get("user")] = per_user.get(rec.get("user"), 0) + 1
    out = [{"user": name, "disabled": bool(rec.get("disabled")),
            "created": rec.get("created"), "devices": per_user.get(name, 0)}
           for name, rec in sorted(users.items())]
    return {"users": out, "superadmin": BASIC_USER}


def op_auth_user_create(payload: dict) -> dict:
    user = str(payload.get("user") or "").strip().lower()
    password = str(payload.get("pass") or "")
    if not _USERNAME_RE.match(user):
        raise ApiError(400, "user : 2-32 car., [a-z0-9._-], commence par [a-z0-9]")
    if BASIC_USER is not None and user == BASIC_USER.lower():
        raise ApiError(400, "ce nom est réservé au superadmin (.env)")
    if len(password) < 8:
        raise ApiError(400, "pass : 8 caractères minimum")
    with _AUTH_LOCK:
        users = _auth_load(USERS_FILE)
        if user in users:
            raise ApiError(409, f"compte existant : {user}")
        users[user] = {**_pbkdf2(password),
                       "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
        _auth_save(USERS_FILE, users)
    return {"user": user, "created": True}


def op_auth_user_update(user: str, payload: dict) -> dict:
    with _AUTH_LOCK:
        users = _auth_load(USERS_FILE)
        rec = users.get(user)
        if not rec:
            raise ApiError(404, f"compte inconnu : {user}")
        changed = {}
        if payload.get("pass"):
            password = str(payload["pass"])
            if len(password) < 8:
                raise ApiError(400, "pass : 8 caractères minimum")
            rec.update(_pbkdf2(password))
            changed["pass"] = True
        if "disabled" in payload:
            rec["disabled"] = bool(payload["disabled"])
            changed["disabled"] = rec["disabled"]
        users[user] = rec
        _auth_save(USERS_FILE, users)
    # mdp changé ou compte désactivé ⇒ les appareils existants sont révoqués
    if changed.get("disabled") or changed.get("pass"):
        changed["devices_revoked"] = _revoke_devices(user=user)
    if not changed:
        raise ApiError(400, "rien à changer (pass et/ou disabled attendus)")
    return {"user": user, **changed}


def op_auth_user_delete(user: str) -> dict:
    with _AUTH_LOCK:
        users = _auth_load(USERS_FILE)
        if user not in users:
            raise ApiError(404, f"compte inconnu : {user}")
        users.pop(user)
        _auth_save(USERS_FILE, users)
    return {"user": user, "deleted": True, "devices_revoked": _revoke_devices(user=user)}


def op_auth_devices_list(ctx: dict) -> dict:
    with _AUTH_LOCK:
        devices = _auth_load(DEVICES_FILE)
    out = []
    for did, rec in sorted(devices.items(), key=lambda kv: kv[1].get("created", "")):
        if ctx.get("admin") or rec.get("user") == ctx.get("user"):
            out.append({"device_id": did, "user": rec.get("user"),
                        "device_name": rec.get("device_name"),
                        "admin": bool(rec.get("admin")),
                        "created": rec.get("created"),
                        "last_seen": rec.get("last_seen"),
                        "current": did == ctx.get("device_id")})
    return {"devices": out}

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


def op_spawn(payload: dict, auth_ctx: dict | None = None) -> dict:
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
        _record_key(rm_id, engine, session_id, str(cwd), model=model_value)
        joined = _auto_join_current_set(rm_id, auth_ctx)   # RM2445 : rejoint le jeu courant

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
            "session_id": session_id, "created": True,
            "set": joined}          # RM2450 : dit si la session a rejoint le jeu


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


# ── Vocal V2 L1 : TTS serveur Piper (RM2532) ─────────────────────────────────
def _piper_models() -> dict:
    """{lang: chemin_onnx} des modèles Piper présents (paire .onnx + .onnx.json).
    Langue déduite du préfixe de nom (`fr_FR-…` → fr, `en_US-…` → en)."""
    out = {}
    if PIPER_MODELS.is_dir():
        for onnx in sorted(PIPER_MODELS.glob("*.onnx")):
            if not onnx.with_suffix(".onnx.json").is_file():
                continue
            lang = onnx.name[:2].lower()
            out.setdefault(lang, onnx)
    return out


def _piper_ready() -> bool:
    return PIPER_BIN.is_file() and bool(_piper_models())


def op_voice_caps() -> dict:
    """Capacités vocales SERVEUR, pour la bascule navigateur↔serveur du cockpit.
    tts=Piper si installé (RM2532) ; stt=sidecar karl-whisper joignable (RM2533)."""
    langs = sorted(_piper_models().keys())
    ready = _piper_ready()
    stt = _whisper_ready()
    return {"tts": ready, "stt": stt, "engine": "piper" if ready else None,
            "stt_engine": "whisper" if stt else None, "tts_langs": langs}


def op_tts_wav(payload: dict) -> bytes:
    """RM2532 : synthèse Piper d'un texte → octets WAV. Sous-process sans état
    (`piper -m <modèle>` lit stdin, écrit le WAV sur stdout). ApiError sinon."""
    text = str(payload.get("text") or "").strip()
    if not text:
        raise ApiError(400, "texte vide")
    if len(text) > 4000:
        raise ApiError(400, "texte trop long (max 4000 caractères)")
    models = _piper_models()
    if not PIPER_BIN.is_file() or not models:
        raise ApiError(503, "TTS serveur indisponible (Piper non installé) — "
                            "cockpit sur synthèse navigateur")
    lang = str(payload.get("lang") or "fr")[:2].lower()
    model = models.get(lang) or next(iter(models.values()))
    # Piper écrit le WAV via `-f <fichier>` (le stdout n'est pas fiable selon la
    # version : sans -f il tente ffplay puis retombe sur output.wav). Fichier temp.
    import tempfile
    tf = tempfile.NamedTemporaryFile(prefix="karl-tts-", suffix=".wav", delete=False)
    tmp = tf.name
    tf.close()
    try:
        r = subprocess.run([str(PIPER_BIN), "-m", str(model), "-f", tmp],
                           input=text.encode("utf-8"), capture_output=True, timeout=30)
        if r.returncode != 0:
            raise ApiError(500, "TTS : échec Piper — "
                                + (r.stderr.decode("utf-8", "replace")[:200] or "?"))
        wav = Path(tmp).read_bytes()
        if not wav:
            raise ApiError(500, "TTS : WAV vide")
        return wav
    except subprocess.TimeoutExpired:
        raise ApiError(500, "TTS : timeout Piper (30 s)")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ── Vocal V2 L2 : STT sidecar karl-whisper (RM2533) ──────────────────────────
def _whisper_health(timeout: float = 0.4):
    """État du sidecar STT, ou None s'il est injoignable / froid. Timeout court :
    op_voice_caps est appelé au chargement du cockpit — on ne bloque pas l'UI si
    le sidecar est absent (cas nominal tant que L2 n'est pas activé en prod)."""
    import urllib.request
    try:
        with urllib.request.urlopen(WHISPER_URL + "/health", timeout=timeout) as r:
            if r.status != 200:
                return None
            data = json.loads(r.read().decode("utf-8"))
            return data if (data.get("ok") and data.get("warm")) else None
    except Exception:  # noqa: BLE001
        return None


def _whisper_ready() -> bool:
    return _whisper_health() is not None


def op_stt(payload: dict) -> dict:
    """RM2533 : transcrit un clip audio (base64) via le sidecar karl-whisper. Le
    cockpit envoie {audio_b64, lang} (blob MediaRecorder, webm/opus). ApiError si
    audio absent/trop gros/sidecar injoignable → le cockpit retombe sur la Web
    Speech API du navigateur (repli, aucune régression V1)."""
    import urllib.error
    import urllib.request
    b64 = str(payload.get("audio_b64") or "")
    if not b64:
        raise ApiError(400, "audio vide")
    try:
        audio = base64.b64decode(b64, validate=True)
    except Exception:
        raise ApiError(400, "audio_b64 invalide")
    if not audio:
        raise ApiError(400, "audio vide")
    if len(audio) > STT_MAX_BYTES:
        raise ApiError(413, f"audio trop volumineux (> {STT_MAX_BYTES // (1024 * 1024)} Mo)")
    lang = str(payload.get("lang") or "fr")[:2].lower()
    req = urllib.request.Request(
        WHISPER_URL + "/stt?lang=" + lang, data=audio, method="POST",
        headers={"Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        raise ApiError(502, "STT sidecar : " + (body or str(e.code)))
    except Exception:  # noqa: BLE001
        raise ApiError(503, "STT serveur indisponible (sidecar karl-whisper absent) — "
                            "cockpit sur reconnaissance navigateur")
    return {"text": out.get("text") or "", "lang": out.get("lang"),
            "duration": out.get("duration")}


# RM2515 : disposition manuelle d'une session — raffine l'état heuristique `idle`
# (l'humain sait ce que la machine ne peut pas déduire : « j'en ai fini » vs « j'y
# reviens »). Défaut « à traiter » = pas de marque stockée. Ne s'affiche que sur
# `idle` côté UI : elle CÈDE aux évènements live (working/attention/choice).
_DISPOSITIONS = ("a_traiter", "parke", "termine")


def op_disposition(payload: dict, auth_ctx=None) -> dict:
    """Pose/efface la disposition d'une session (à traiter / parké / terminé).
    Persistée dans keys/<sid>.json (STATE_DIR, RM2385) → survit au reload et
    cohérente entre fenêtres attachées. « a_traiter » (ou vide) efface la marque."""
    rm_id = _require_rm_id(payload)
    disp = str(payload.get("disposition") or "").strip()
    if disp and disp not in _DISPOSITIONS:
        raise ApiError(400, f"disposition invalide : {disp!r} "
                            f"(attendu {'/'.join(_DISPOSITIONS)} ou vide)")
    key = f"RM{rm_id}" if _is_ticket_sid(rm_id) else rm_id
    keyf = STATE_DIR / "keys" / f"{key}.json"
    rec = _read_json_file(keyf)
    if rec is None:
        raise ApiError(404, f"session inconnue : {rm_id} (pas d'entrée keys/ — jamais ancrée)")
    if disp and disp != "a_traiter":
        rec["disposition"] = disp
    else:
        rec.pop("disposition", None)   # défaut → pas de marque stockée
    _write_json_atomic(keyf, rec)
    return {"rm_id": rm_id, "disposition": disp or "a_traiter"}


# ── Sessions ⇄ tickets : store, découverte, reprise (RM1939, itér.1 claude) ──
_SID_RE = re.compile(r"^[0-9a-fA-F][0-9a-fA-F-]{7,63}$")   # claude (historique)

# RM2539 — la grammaire d'un identifiant de conversation appartient au MOTEUR.
# `_SID_RE` (UUID) restait le seul filtre : un id opencode `ses_14301a3ddff…`
# était rejeté en `400 session_id invalide` bien avant d'atteindre le routage.
_ENGINE_SID_RES = {name: re.compile(e["sid_re"])
                   for name, e in ENGINES.items() if e.get("sid_re")}


def _valid_session_id(session_id: str | None, engine: str | None = None) -> bool:
    """Un id de conversation est valide pour SON moteur. `engine` inconnu ou
    absent : on accepte ce qu'accepte au moins un moteur (l'appelant recoupera
    le moteur réel via `_engine_of_session`)."""
    if not session_id:
        return False
    rx = _ENGINE_SID_RES.get(engine or "")
    if rx:
        return bool(rx.match(session_id))
    return any(r.match(session_id) for r in _ENGINE_SID_RES.values())


def _resume_support(engine: str | None) -> dict | None:
    """Contrat de reprise du moteur, ou None s'il n'en déclare pas (vibe, shell).
    Un moteur sans contrat n'est pas une anomalie : c'est un refus à formuler
    clairement, pas un plantage."""
    e = ENGINES.get(engine or "", {})
    return e if e.get("resume_flag") and e.get("store") else None


# Base SQLite d'opencode : une ligne `session` porte id, titre, dossier et dates —
# soit, déjà structuré, ce que karl-agent extrait des transcripts claude en les
# parsant. Lecture SEULE (uri mode=ro) : le moteur en est propriétaire.
OPENCODE_DB = Path(os.environ.get("KARL_AGENT_OPENCODE_DB") or (
    Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    / "opencode" / "opencode.db"))


# Sessions vibe : un dossier par session sous ~/.vibe/logs/session/, nommé
# `session_<date>_<8 premiers hexa de l'id>`, contenant meta.json (id complet,
# titre déjà extrait par le moteur, working_directory, dates) et messages.jsonl.
VIBE_SESSIONS = Path(os.environ.get("KARL_AGENT_VIBE_SESSIONS") or (
    Path.home() / ".vibe" / "logs" / "session"))


def _vibe_session_meta(session_id: str) -> dict:
    """{title, mtime, cwd} d'une conversation vibe, ou {} si introuvable.

    Le suffixe du dossier ne porte que les 8 premiers hexa de l'id : il sert de
    filtre, jamais de preuve — c'est le `session_id` de meta.json qui fait foi
    (deux sessions peuvent partager un préfixe, et un dossier renommé mentirait)."""
    if not VIBE_SESSIONS.is_dir() or "-" not in session_id:
        return {}
    prefix = session_id.split("-")[0]
    for d in sorted(VIBE_SESSIONS.glob(f"session_*_{prefix}"), reverse=True):
        try:
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if meta.get("session_id") != session_id:
            continue        # préfixe partagé : ce n'est pas la bonne session
        end = meta.get("end_time") or meta.get("start_time")
        mtime = None
        if end:
            try:
                from datetime import datetime as _dt
                mtime = int(_dt.fromisoformat(end).timestamp())
            except ValueError:
                mtime = None
        if mtime is None:
            try:
                mtime = int((d / "meta.json").stat().st_mtime)
            except OSError:
                mtime = None
        return {"title": (meta.get("title") or None),
                "cwd": (meta.get("environment") or {}).get("working_directory"),
                "mtime": mtime}
    return {}


def _opencode_session_meta(session_id: str) -> dict:
    """{title, mtime, cwd} d'une conversation opencode, ou {} si introuvable."""
    if not OPENCODE_DB.is_file():
        return {}
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True, timeout=2)
        try:
            row = con.execute("SELECT title, directory, time_updated, time_created "
                              "FROM session WHERE id = ?", (session_id,)).fetchone()
        finally:
            con.close()
    except Exception:            # base absente, verrouillée, schéma changé…
        return {}
    if not row:
        return {}
    title, directory, updated, created = row
    ms = updated or created or 0
    return {"title": (title or None), "cwd": (directory or None),
            "mtime": (int(ms) // 1000 if ms else None)}   # epoch ms → s
_MARK_RE = re.compile(r"^\[(WIP|DONE)\]\s*", re.I)


def _write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _slug_of(cwd) -> str:
    """Nom du dossier projet claude pour un cwd — schéma observé du CLI :
    '/' et '.' → '-'. Sert à recouper le cwd d'un store avec l'emplacement RÉEL
    du transcript (RM2418)."""
    return re.sub(r"[/.]", "-", str(cwd).rstrip("/")) or str(cwd)


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


def _record_key(sid: str, engine: str, session_id: str, cwd: str,
                model: str | None = None) -> None:
    """Index clé-tmux → (engine, session_id, cwd) — RM2144. Couvre AUSSI les
    sessions slug (sans jonction ticket) : sert à l'enrichissement /sessions
    (moteur, projet via cwd) et à la reprise. Touche l'entité session au passage.

    `model` (RM1941/RM2395) : la valeur de modèle résolue au spawn, mémorisée
    pour qu'un instantané de jeu (RM2395) puisse relancer avec le bon modèle
    (None = défaut moteur). Préservée sur une reprise (qui appelle sans model)."""
    now = int(time.time())
    key = f"RM{sid}" if _is_ticket_sid(sid) else sid
    keyf = STATE_DIR / "keys" / f"{key}.json"   # RM2385 : état partagé, pas LOG_DIR
    prev = _read_json_file(keyf) or {}
    if model is None:  # reprise / enrichissement : ne pas perdre le modèle déjà connu
        model = prev.get("model")
    rec = {"sid": sid, "engine": engine, "session_id": session_id,
           "cwd": cwd, "last_seen": now}
    if model:
        rec["model"] = model
    if prev.get("disposition"):  # RM2515 : préserver la disposition manuelle (idem model)
        rec["disposition"] = prev["disposition"]
    _write_json_atomic(keyf, rec)
    sf = SESS_DIR / engine / f"{session_id}.json"
    meta = _read_json_file(sf) or {"engine": engine, "session_id": session_id, "created": now}
    meta.update({"cwd": cwd, "last_seen": now})
    if model:
        meta["model"] = model
    _write_json_atomic(sf, meta)


# ── Jeux DÉRIVÉS (RM2452) ────────────────────────────────────────────────────
# Les jeux manuels dupliquent une connaissance que le système possède déjà :
# chaque session porte son cwd → client/projet (.mmi-pm), souvent un RM-id, son
# titre et sa marque [WIP]/[DONE]. Cette duplication se paie en gestes — créer,
# verser, scinder, retirer — et le jeu dérive dès qu'on oublie.
#
# Un jeu DÉRIVÉ est défini par une RÈGLE, pas par une liste : il ne dérive jamais,
# rien à curer, et une session neuve qui satisfait la règle y entre sans geste.
# La résolution se fait à la LECTURE : rien n'est stocké, donc rien à synchroniser.
RULE_KEYS = ("client", "project", "mark", "tickets")


def _rule_norm(rule) -> dict:
    """Valide et normalise une règle. Une règle vide n'a pas de sens (elle
    désignerait tout) : 400 plutôt qu'un jeu fourre-tout silencieux."""
    if not isinstance(rule, dict):
        raise ApiError(400, "rule doit être un objet")
    out = {}
    for k in RULE_KEYS:
        v = rule.get(k)
        if v in (None, "", []):
            continue
        if k == "tickets":
            if not isinstance(v, list):
                raise ApiError(400, "rule.tickets doit être une liste d'id")
            out[k] = [str(x) for x in v]
        elif k == "mark":
            m = str(v).lower()
            if m not in ("wip", "done", "none"):
                raise ApiError(400, "rule.mark doit valoir wip, done ou none")
            out[k] = m
        else:
            out[k] = str(v)
    if not out:
        raise ApiError(400, "règle vide : elle désignerait toutes les sessions")
    unknown = set(rule) - set(RULE_KEYS)
    if unknown:
        raise ApiError(400, f"critère(s) inconnu(s) : {', '.join(sorted(unknown))}")
    return out


def _all_keys() -> list:
    """Toutes les sessions que karl-agent a ancrées un jour (index `keys/`) :
    la seule source qui donne à la fois un `sid` (nom tmux, donc relançable) et
    le contexte de la session. `op_resumable` part des transcripts et n'a pas
    toujours de sid — un jeu dérivé doit pouvoir produire des tuiles grises."""
    out = []
    d = STATE_DIR / "keys"
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        k = _read_json_file(f) or {}
        stem = f.stem
        sid = stem[2:] if stem.startswith("RM") and stem[2:].isdigit() else stem
        if _valid_sid(sid):
            out.append((sid, k))
    return out


def _rule_matches(rule: dict, sid: str, k: dict) -> bool:
    client, project = _pm_project_of_cwd(k.get("cwd"))
    if "client" in rule and client != rule["client"]:
        return False
    if "project" in rule and project != rule["project"]:
        return False
    if "tickets" in rule and sid not in rule["tickets"]:
        return False
    if "mark" in rule:
        mark = _session_mark(k.get("session_id"))
        if rule["mark"] == "none":
            if mark:
                return False
        elif mark != rule["mark"]:
            return False
    return True


def _derived_entries(rule: dict, with_total: bool = False):
    """Contenu d'un jeu dérivé, au format d'une entrée manuelle — pour que tout
    l'aval (fantômes, relance, estimation) l'ignore et le traite pareil.

    Deux règles d'hygiène, alignées sur les jeux manuels :

    - une session TERMINÉE marquée `[DONE]` et qui ne tourne plus est écartée,
      exactement comme `_forget_done_entries` l'évince d'un jeu manuel (RM2427) :
      un travail fini n'a pas de tuile grise. Sans cela une vue client affichait
      12 sessions closes sur 25 — d'où l'impression, justifiée, d'en voir
      « beaucoup plus » ;
    - le plafond `SESSION_SET_MAX` ne tronque plus en SILENCE : le total réel est
      rendu à l'appelant, qui le dit (`truncated`).

    Une session `[DONE]` mais VIVANTE reste listée : on n'escamote jamais un
    processus qui tourne."""
    live = {s["rm_id"] for s in _list_sessions()}
    out = []
    for sid, k in _all_keys():
        if not _rule_matches(rule, sid, k):
            continue
        if sid not in live and _is_marked_done(k.get("session_id")):
            continue
        out.append({
            "sid": sid, "engine": k.get("engine"), "session_id": k.get("session_id"),
            "cwd": k.get("cwd"), "model": k.get("model"),
            "title": _transcript_title(k.get("session_id")),
            "restart": _default_restart(k.get("session_id")),
        })
    return (out[:SESSION_SET_MAX], len(out)) if with_total else out[:SESSION_SET_MAX]


def _entries_for_sids(wanted: set, user: str, store: dict) -> list:
    """RM2452 — entrées correspondant à des sid, qu'ils soient VIVANTS ou non.
    L'instantané tmux ne connaît que les sessions qui tournent : une sélection de
    tuiles grises aurait produit un jeu vide. On résout donc dans l'ordre :
    l'instantané (état frais), puis le jeu courant (titre et politique déjà
    réglés), puis l'index des clés (toute session jamais ancrée)."""
    out, seen = [], set()
    for e in _snapshot_live_sessions():
        if e["sid"] in wanted:
            out.append(e); seen.add(e["sid"])
    cur = _session_set_get(store, user, _current_set(user, store)) or {}
    for e in _set_entries(cur):
        if e.get("sid") in wanted and e["sid"] not in seen:
            out.append(dict(e)); seen.add(e["sid"])
    for sid in wanted - seen:
        k = _key_info(sid)
        if not k:
            continue
        out.append({"sid": sid, "engine": k.get("engine"),
                    "session_id": k.get("session_id"), "cwd": k.get("cwd"),
                    "model": k.get("model"),
                    "title": _transcript_title(k.get("session_id")),
                    "restart": _default_restart(k.get("session_id"))})
    return out


def _session_facets() -> dict:
    """RM2452 — ce que l'index des clés sait déjà, agrégé : clients ayant au moins
    une session, leurs projets, et les marques présentes. Sert à DEUX choses —
    proposer des vues par client sans que l'opérateur ait rien à créer, et
    peupler les listes du formulaire de règle (on ne saisit pas un slug à la
    main quand le système connaît la liste)."""
    clients: dict = {}
    marks = set()
    for sid, k in _all_keys():
        client, project = _pm_project_of_cwd(k.get("cwd"))
        if client:
            c = clients.setdefault(client, {"slug": client, "count": 0, "projects": set()})
            c["count"] += 1
            if project:
                c["projects"].add(project)
        m = _session_mark(k.get("session_id"))
        if m:
            marks.add(m)
    out = [{"slug": c["slug"], "count": c["count"], "projects": sorted(c["projects"])}
           for c in clients.values()]
    out.sort(key=lambda c: (-c["count"], c["slug"]))
    return {"clients": out, "marks": sorted(marks)}


def _set_entries(rec: dict) -> list:
    """Contenu d'un jeu, dérivé ou manuel. Point de passage unique : l'aval n'a
    pas à savoir de quelle nature est le jeu qu'il lit."""
    rule = rec.get("rule")
    return _derived_entries(rule) if rule else (rec.get("entries") or [])


def _set_total(rec: dict) -> int:
    """Nombre RÉEL de sessions désignées, avant plafonnement — pour que l'UI
    puisse dire « 24 affichées sur 31 » au lieu de mentir par omission."""
    rule = rec.get("rule")
    if not rule:
        return len(rec.get("entries") or [])
    return _derived_entries(rule, with_total=True)[1]


def _reject_if_derived(rec: dict, what: str) -> None:
    """On ne retire pas à la main d'un ensemble CALCULÉ : la règle décide. Le
    geste existe quand même — « matérialiser » fige le jeu dérivé en jeu manuel."""
    if rec.get("rule"):
        raise ApiError(400, f"{what} : ce jeu est dérivé (défini par une règle). "
                            f"Matérialise-le d'abord pour le modifier à la main.")


def _key_info(sid: str) -> dict | None:
    key = f"RM{sid}" if _is_ticket_sid(sid) else sid
    return _read_json_file(STATE_DIR / "keys" / f"{key}.json")


# ── Jeux de sessions enregistrés (RM2395) — instance-local, JAMAIS committé ───
# Un « jeu » = un instantané des sessions vivantes qu'on veut pouvoir relancer
# d'un clic après un reboot. Rangé sous LOG_DIR (à côté de keys/sessions/tasks) :
# instance-local, hors git — un session_id n'a de sens que sur cette machine.
#
# Le schéma anticipe DÉLIBÉRÉMENT le multi-utilisateur et les groupes NOMMÉS :
#   {"version":1, "users": {"<user>": {"groups": {"<group>": {saved_at, autostart,
#                                                              entries:[…]}}}}}
# Cette première étape (RM2395) n'exerce que le couple par défaut — user
# « superadmin » (l'utilisateur amorcé par la conf, cf. RM2334), groupe
# « default » — mais la clé user+groupe est portée de bout en bout pour que le
# multi-jeux et le multi-utilisateur soient une simple extension, sans migration.
SESSION_SET_FILE = LOG_DIR / "session-set.json"
DEFAULT_SET_USER = "superadmin"    # auth ouverte / secret partagé → superadmin
DEFAULT_SET_GROUP = "default"
SESSION_SET_MAX = 24               # garde-fou : un instantané ne dépasse pas ça
_SET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")  # user ET group


def _session_set_user(auth_ctx: dict | None) -> str:
    """Utilisateur porteur du jeu. En auth ouverte ou via secret partagé,
    auth_ctx['user'] vaut None → on retombe sur le superadmin par défaut. Le nom
    est normalisé/validé (c'est une clé de dict) ; à défaut, superadmin."""
    user = str((auth_ctx or {}).get("user") or DEFAULT_SET_USER).lower()
    return user if _SET_NAME_RE.match(user) else DEFAULT_SET_USER


def _session_set_group(name) -> str:
    name = str(name or DEFAULT_SET_GROUP).lower()
    if not _SET_NAME_RE.match(name):
        raise ApiError(400, f"nom de groupe invalide : {name!r}")
    return name


def _session_set_load() -> dict:
    store = _read_json_file(SESSION_SET_FILE)
    if not isinstance(store, dict) or not isinstance(store.get("users"), dict):
        return {"version": 1, "users": {}}
    return store


def _session_set_get(store: dict, user: str, group: str) -> dict | None:
    return (store.get("users", {}).get(user, {}).get("groups") or {}).get(group)


def _session_set_put(store: dict, user: str, group: str, rec: dict) -> None:
    store.setdefault("version", 1)
    (store.setdefault("users", {}).setdefault(user, {})
        .setdefault("groups", {}))[group] = rec


# ── Historique du store des jeux (RM2443) ────────────────────────────────────
# Le store est réécrit à chaque geste (enregistrement, réglage de reprise, retrait
# d'une entrée, éviction [DONE]) — ~9 écritures/semaine mesurées, pour 1,6 Ko :
# en garder les N derniers états ne coûte rien et rend réversible le seul chemin
# de suppression SILENCIEUX qui subsiste (l'éviction [DONE] automatique).
#
# Nuance de conception : on historise le FICHIER (point d'écriture unique, donc
# sûr et complet) mais on restaure un JEU. Le store contient tous les users et
# tous les groupes : rétablir « calicote d'hier » en rembobinant le fichier
# entier rendrait AUSSI les autres jeux dans leur état d'hier — rendre ce qu'on
# ne demande pas est un piège, pas un filet.
SESSION_SET_KEEP = max(1, int(os.environ.get("KARL_AGENT_SET_HISTORY_KEEP", "10")))


def _history_dir() -> Path:
    """Dossier d'archives, DÉRIVÉ du store courant (et non d'un LOG_DIR figé à
    l'import) : une instance de test qui rebind `SESSION_SET_FILE` obtient un
    historique isolé, sans jamais toucher celui de la prod."""
    return SESSION_SET_FILE.with_name(SESSION_SET_FILE.name + ".history")


def _history_versions() -> list:
    """(stamp, chemin) des versions archivées, de la plus RÉCENTE à la plus
    ancienne. Le stamp est un `time.time_ns()` — unique même si deux écritures
    tombent dans la même seconde."""
    d = _history_dir()
    if not d.is_dir():
        return []
    out = []
    for p in d.glob("session-set-*.json"):
        stamp = p.stem[len("session-set-"):]
        if stamp.isdigit():
            out.append((int(stamp), p))
    out.sort(reverse=True)
    return out


def _archive_session_set(payload: str):
    """Archive l'état COURANT — celui que l'écriture qui suit va écraser — puis
    purge au-delà de `SESSION_SET_KEEP`. Si le nouveau contenu est identique,
    il n'y a rien à perdre : rien n'est empilé (deux gestes sans effet ne
    consomment pas l'historique). Best-effort : un historique en échec ne doit
    JAMAIS empêcher d'écrire le store."""
    try:
        current = SESSION_SET_FILE.read_text(encoding="utf-8")
    except OSError:
        return None                 # pas encore de store : rien à sauvegarder
    if current == payload:
        return None
    try:
        d = _history_dir()
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.time_ns()      # RM2451 : rendu à l'appelant → « annuler »
        (d / f"session-set-{stamp}.json").write_text(current, encoding="utf-8")
        for _, old in _history_versions()[SESSION_SET_KEEP:]:
            old.unlink(missing_ok=True)
        return str(stamp)
    except OSError as e:
        sys.stderr.write(f"historique du jeu de sessions ignoré : {e}\n")
        return None


def _write_session_set(store: dict, archive: bool = True):
    """Seul point d'écriture du store des jeux : archive l'état courant, puis
    écrit. La sérialisation doit être IDENTIQUE à celle de `_write_json_atomic`,
    sans quoi la comparaison de dédoublonnage serait toujours fausse.

    RM2445 — `archive=False` pour une écriture strictement ADDITIVE (adhésion
    d'une session au jeu courant, changement de jeu courant) : l'historique
    existe pour rattraper une PERTE, et rien n'est perdu ici. Sans ce garde-fou,
    lancer dix sessions chasserait les dix versions conservées, c'est-à-dire
    l'historique tout entier au moment où il servirait le plus."""
    stamp = _archive_session_set(json.dumps(store, ensure_ascii=False, indent=1)) \
        if archive else None
    _write_json_atomic(SESSION_SET_FILE, store)
    return stamp                    # RM2451 : identifiant de l'état d'AVANT


def _current_set(user: str, store: dict | None = None) -> str:
    """RM2445 — jeu COURANT de l'utilisateur, état SERVEUR. Il vivait dans le
    localStorage du cockpit : le serveur l'ignorait, donc ni les fantômes ni
    l'adhésion automatique ne pouvaient en tenir compte, et basculer de jeu
    n'avait aucun effet. Un jeu courant effacé entre-temps retombe sur `default`
    (jamais de contexte orphelin)."""
    store = _session_set_load() if store is None else store
    u = (store.get("users") or {}).get(user) or {}
    name = u.get("current") or DEFAULT_SET_GROUP
    return name if name in (u.get("groups") or {}) else DEFAULT_SET_GROUP


# RM2446 — VUES. Un pseudo-jeu (« sessions ouvertes », « tous les jeux ») n'est pas
# un jeu : on n'y enregistre rien, on ne le renomme pas, on ne l'efface pas. D'où
# deux états distincts : le JEU COURANT (`current`, toujours un vrai jeu) reste la
# cible de toutes les écritures — adhésion automatique, bouton « Enregistrer », ⊖ —,
# tandis que la VUE (`view`) décide seulement de ce qu'on affiche. Une vue ne peut
# donc jamais devenir une destination par accident.
SESSION_SET_VIEWS = ("set", "live", "all")
_VIEW_CLIENT_RE = re.compile(r"^client:([a-z0-9][a-z0-9._-]{0,31})$")


def _view_valid(v: str) -> bool:
    return v in SESSION_SET_VIEWS or bool(_VIEW_CLIENT_RE.match(v or ""))


def _current_view(user: str, store: dict | None = None) -> str:
    store = _session_set_load() if store is None else store
    v = ((store.get("users") or {}).get(user) or {}).get("view")
    return v if _view_valid(v or "") else "set"


def op_session_set_current(payload: dict, auth_ctx: dict | None = None) -> dict:
    """RM2445/RM2446 — change le jeu courant et/ou la vue. C'est une bascule de
    CONTEXTE : aucun tmux n'est tué ni lancé, une session peut appartenir à
    plusieurs jeux. `group` fixe le jeu courant (et rebascule en `view=set`) ;
    `view` seul ne change que l'affichage, le jeu courant restant la cible des
    écritures."""
    user = _session_set_user(auth_ctx)
    store = _session_set_load()
    u = store.setdefault("users", {}).setdefault(user, {})
    groups = u.get("groups") or {}
    if payload.get("group") is not None:
        group = _session_set_group(payload.get("group"))
        if group not in groups and group != DEFAULT_SET_GROUP:
            raise ApiError(404, f"aucun jeu enregistré ({user}/{group})")
        u["current"] = group
        u["view"] = "set"          # choisir un jeu, c'est vouloir le regarder
    if payload.get("view") is not None:
        view = str(payload.get("view") or "").strip().lower()
        if not _view_valid(view):
            raise ApiError(400, f"view doit valoir {' ou '.join(SESSION_SET_VIEWS)} "
                                f"ou client:<slug>")
        u["view"] = view
    if payload.get("group") is None and payload.get("view") is None:
        raise ApiError(400, "group ou view requis")
    _write_session_set(store, archive=False)
    return {"user": user, "current": _current_set(user, store),
            "view": _current_view(user, store)}


def _auto_join_current_set(sid: str, auth_ctx: dict | None = None) -> dict | None:
    """RM2445 — une session qui démarre (spawn) ou qui est reprise (resume)
    REJOINT le jeu courant, sans geste manuel. Union stricte : le statut fait
    ENTRER, jamais SORTIR (invariant RM2439 — une session qui s'arrête devient
    une tuile grise, elle ne quitte pas le jeu). Best-effort : l'échec de
    l'adhésion ne doit jamais faire échouer le lancement d'une session."""
    try:
        user = _session_set_user(auth_ctx)
        store = _session_set_load()
        group = _current_set(user, store)
        rec = _session_set_get(store, user, group)
        if rec is not None and rec.get("rule"):
            # RM2452 : dans un jeu dérivé, c'est la RÈGLE qui décide — la session
            # y figurera si elle la satisfait, sans qu'on l'y « ajoute ».
            return {"group": group, "joined": False, "reason": "derive"}
        if rec is None:
            rec = {"saved_at": int(time.time()), "saved_by": (auth_ctx or {}).get("user"),
                   "autostart": True, "entries": []}
        entries = rec.setdefault("entries", [])
        if any(e.get("sid") == sid for e in entries):
            return {"group": group, "joined": False, "reason": "deja"}
        if len(entries) >= SESSION_SET_MAX:
            # RM2450 : ce refus finissait sur stderr — invisible pour l'opérateur,
            # qui croyait sa session enregistrée. Il remonte à l'appelant, qui le
            # renvoie dans la réponse de /spawn et /resume.
            sys.stderr.write(f"jeu {user}/{group} plein ({SESSION_SET_MAX}) : "
                             f"{sid} n'y a pas été ajoutée\n")
            return {"group": group, "joined": False, "reason": "plein",
                    "max": SESSION_SET_MAX}
        k = _key_info(sid) or {}
        entries.append({
            "sid": sid, "engine": k.get("engine"), "session_id": k.get("session_id"),
            "cwd": k.get("cwd"), "model": k.get("model"),
            "title": _transcript_title(k.get("session_id")),
            "restart": _default_restart(k.get("session_id")),
        })
        rec["saved_at"] = int(time.time())
        _session_set_put(store, user, group, rec)
        _write_session_set(store, archive=False)
        return {"group": group, "joined": True}
    except (OSError, ValueError) as e:
        sys.stderr.write(f"adhésion au jeu courant ignorée pour {sid} : {e}\n")
        return {"group": None, "joined": False, "reason": "erreur"}


def _snapshot_live_sessions() -> list:
    """Instantané des sessions tmux vivantes, réduit aux champs nécessaires à une
    relance ultérieure (sid, engine, session_id, cwd, model). Les champs manquants
    (session non indexée en clé) restent à None — l'entrée est enregistrée mais
    sera signalée non reprenable au moment de la relance (étape suivante)."""
    entries = []
    for s in _list_sessions():
        sid = s["rm_id"]
        k = _key_info(sid) or {}
        entries.append({
            "sid": sid,
            "engine": k.get("engine"),
            "session_id": k.get("session_id"),
            "cwd": k.get("cwd"),
            "model": k.get("model"),
            # RM2439 : nom de la session, pour que l'entrée soit identifiable
            # autrement que par son sid (cf. `_transcript_title`)
            "title": _transcript_title(k.get("session_id")),
            # RM2427 : politique de reprise par session — `[WIP]` ⇒ redémarre
            # seule, sinon tuile grise (réglable ensuite, cf. RESTART_POLICIES)
            "restart": _default_restart(k.get("session_id")),
        })
    return entries


def op_session_set_save(payload: dict, auth_ctx: dict | None = None) -> dict:
    """RM2395/RM2439 — enregistre les sessions dans le jeu (user, group) par
    UNION, jamais par remplacement. v1 : couple par défaut superadmin/default ;
    `group` peut déjà être passé (anticipation multi-jeux). L'écrasement préserve
    le drapeau `autostart` du jeu précédent ; un jeu NEUF naît `autostart=True`
    (RM2427 : la reprise ne coûte plus rien — elle n'affiche que des tuiles
    grises).

    RM2439 — la sauvegarde ne DÉTRUIT rien. Elle rafraîchit les entrées dont la
    session tourne, ajoute les vivantes qui manquaient, et **conserve les autres
    telles quelles**. Avant, l'instantané des seules sessions vivantes remplaçait
    `entries[]` : un clic sur « Enregistrer les sessions » effaçait toutes les
    tuiles grises (sessions enregistrées non lancées) que l'opérateur croyait
    justement enregistrer. Le retrait d'une entrée reste un geste explicite :
    `DELETE /session-set?sid=…` (✕ sur la tuile) ou l'éviction automatique des
    sessions terminées marquées `[DONE]` (`_forget_done_entries`).

    `sids` (optionnel) = les sid que le cockpit AFFICHE. C'est un sélecteur
    **additif** : il restreint les sessions vivantes à enregistrer, il ne retire
    jamais une entrée en place. Un remplacement piloté par le client rejouerait
    le bug sous une autre forme, le panneau pouvant être filtré (client/projet)
    et donc n'afficher qu'un sous-ensemble du jeu. Vide ou absent ⇒ toutes les
    vivantes."""
    user = _session_set_user(auth_ctx)
    group = _session_set_group(payload.get("group"))
    only = payload.get("sids")
    if only is not None and not isinstance(only, list):
        raise ApiError(400, "sids doit être une liste de sid")
    live = _snapshot_live_sessions()
    wanted = {str(s) for s in only} if only else set()
    if wanted:
        live = [e for e in live if e["sid"] in wanted]
    live_by_sid = {e["sid"]: e for e in live}

    store = _session_set_load()
    prev = _session_set_get(store, user, group) or {}
    _reject_if_derived(prev, "enregistrement impossible")     # RM2452
    prev_entries = list(prev.get("entries") or [])

    entries = []
    for old in prev_entries:
        fresh = live_by_sid.pop(old.get("sid"), None)
        e = dict(fresh) if fresh else dict(old)
        # RM2427 : un réglage de reprise posé à la main sur une session survit au
        # ré-enregistrement du jeu (sinon il serait réécrit par le défaut
        # [WIP]/idle).
        if old.get("restart") in RESTART_POLICIES:
            e["restart"] = old["restart"]
        # RM2439 : le nom mémorisé ne se perd pas si le transcript a disparu ;
        # et une entrée ancienne (enregistrée avant ce correctif, ou déjà éteinte)
        # se fait nommer au passage — c'est le seul moment où on la relit.
        if not e.get("title"):
            e["title"] = old.get("title") or _transcript_title(e.get("session_id"))
        entries.append(e)
    added = list(live_by_sid)                    # vivantes encore jamais vues
    entries.extend(live_by_sid.values())

    # Le plafond porte désormais sur l'UNION : refus AVANT toute écriture, pour
    # que le jeu déjà en place survive intact au dépassement.
    if len(entries) > SESSION_SET_MAX:
        raise ApiError(409, f"le jeu dépasserait {SESSION_SET_MAX} entrées "
                            f"({len(entries)}) — retire des tuiles (✕) avant "
                            f"d'enregistrer")
    # RM2442 : le libellé humain se pose à la création du jeu (« enregistrer ces
    # sessions sous “Chantier Calicote” ») et survit aux ré-enregistrements.
    label = str(payload.get("label") or prev.get("label") or "").strip()
    rec = {
        "saved_at": int(time.time()),
        "saved_by": (auth_ctx or {}).get("user"),   # user réel (None si auth ouverte)
        "autostart": bool(prev.get("autostart", True)),
        "entries": entries,
    }
    if label:
        rec["label"] = label[:SET_LABEL_MAX]
    _session_set_put(store, user, group, rec)
    _write_session_set(store)
    known = {e["sid"] for e in entries}
    return {"user": user, "group": group, "count": len(entries),
            "saved_at": rec["saved_at"], "added": added,
            "kept": len(prev_entries),
            "ignored": [s for s in sorted(wanted) if s not in known],
            "entries": entries}


SET_LABEL_MAX = 64


def op_session_sets_list(qs: dict, auth_ctx: dict | None = None) -> dict:
    """RM2442 — liste les jeux de l'utilisateur. Sans cet endpoint, on ne pouvait
    interroger qu'un groupe dont on connaissait DÉJÀ le nom : le multi-jeux vivait
    dans le store (RM2395) sans être découvrable. `default` en tête, le reste par
    ordre alphabétique — l'UI affiche la liste telle quelle."""
    user = _session_set_user(auth_ctx)
    groups = ((_session_set_load().get("users") or {}).get(user, {}).get("groups") or {})
    live = {s["rm_id"] for s in _list_sessions()}
    sets = [{
        "name": name,
        "label": rec.get("label") or name,
        "derived": bool(rec.get("rule")), "rule": rec.get("rule"),
        "count": len(_set_entries(rec)),
        "total": _set_total(rec),          # RM2452 : réel, même si tronqué
        "alive": sum(1 for e in _set_entries(rec) if e.get("sid") in live),
        "saved_at": rec.get("saved_at"),
        "autostart": bool(rec.get("autostart", False)),
    } for name, rec in groups.items()]
    sets.sort(key=lambda s: (s["name"] != DEFAULT_SET_GROUP, s["name"]))
    store = _session_set_load()
    # RM2446 : de quoi libeller les pseudo-jeux sans un second aller-retour
    known = {e.get("sid") for rec in groups.values() for e in (rec.get("entries") or [])}
    facets = _session_facets()
    return {"user": user, "sets": sets, "count": len(sets),
            "current": _current_set(user, store), "view": _current_view(user, store),
            "live_count": len(live), "all_count": len(known | live),
            # RM2452 : vues par client, offertes d'office pour les clients qui ONT
            # des sessions — rien à créer, rien à curer
            "facets": facets,
            "client_views": [{"view": f"client:{c['slug']}", "label": c["slug"],
                              "count": len(_derived_entries({"client": c["slug"]}))}
                             for c in facets["clients"]]}


def op_session_set_rename(payload: dict, auth_ctx: dict | None = None) -> dict:
    """RM2442 — pose le LIBELLÉ humain d'un jeu (« Chantier Calicote »). Le slug
    reste immuable : c'est la clé du store, le renommer casserait les références
    (réglages par entrée, jeux repris au démarrage, historique à venir). Slug =
    clé stable, label = affichage."""
    user = _session_set_user(auth_ctx)
    group = _session_set_group(payload.get("group"))
    label = str(payload.get("label") or "").strip()
    if not label:
        raise ApiError(400, "label requis")
    if len(label) > SET_LABEL_MAX:
        raise ApiError(400, f"label trop long ({len(label)} > {SET_LABEL_MAX})")
    store = _session_set_load()
    rec = _session_set_get(store, user, group)
    if not rec:
        raise ApiError(404, f"aucun jeu enregistré ({user}/{group})")
    rec["label"] = label
    _write_session_set(store)
    return {"user": user, "group": group, "label": label}


def op_session_set_history(qs: dict, auth_ctx: dict | None = None) -> dict:
    """RM2443 — versions archivées du store, de la plus récente à la plus
    ancienne, réduites aux jeux de CET utilisateur (on n'expose pas ceux des
    autres). Une version illisible est ignorée, jamais remontée en erreur :
    l'historique est un confort, il ne doit pas casser la lecture."""
    user = _session_set_user(auth_ctx)
    versions = []
    for stamp, path in _history_versions():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            groups = ((data.get("users") or {}).get(user, {}).get("groups") or {})
        except (OSError, ValueError):
            continue
        versions.append({
            "id": str(stamp), "at": stamp // 1_000_000_000,
            "sets": [{"name": g, "label": r.get("label") or g,
                      "count": len(r.get("entries") or [])}
                     for g, r in sorted(groups.items())],
        })
    return {"user": user, "versions": versions, "count": len(versions),
            "keep": SESSION_SET_KEEP}


def op_session_set_restore(payload: dict, auth_ctx: dict | None = None) -> dict:
    """RM2443 — rétablit UN jeu depuis une version archivée. La restauration est
    chirurgicale : les autres jeux ne bougent pas (cf. § historique — le fichier
    porte tous les jeux, le geste n'en vise qu'un). L'état courant est archivé au
    passage par `_write_session_set`, donc la restauration est elle-même
    annulable. Un jeu supprimé depuis est recréé tel quel."""
    user = _session_set_user(auth_ctx)
    group = _session_set_group(payload.get("group"))
    vid = str(payload.get("id") or payload.get("at") or "").strip()
    if not vid.isdigit():
        raise ApiError(400, "id de version requis (cf. GET /session-set/history)")
    path = next((p for stamp, p in _history_versions() if str(stamp) == vid), None)
    if not path:
        raise ApiError(404, f"version inconnue : {vid}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ApiError(422, f"version illisible : {e}")
    rec = ((data.get("users") or {}).get(user, {}).get("groups") or {}).get(group)
    if not rec:
        raise ApiError(404, f"le jeu « {group} » n'existe pas dans cette version")
    store = _session_set_load()
    _session_set_put(store, user, group, rec)
    _write_session_set(store)
    return {"user": user, "group": group, "restored_from": vid,
            "at": int(vid) // 1_000_000_000,
            "count": len(rec.get("entries") or [])}


def op_session_set_create(payload: dict, auth_ctx: dict | None = None) -> dict:
    """RM2447 — CRÉE un jeu et le rend courant. Verbe distinct de `save`, et à
    dessein : dans `save`, un `sids` vide signifie « toutes les vivantes » (le
    garde-fou anti-écrasement de RM2439, qu'un client ancien ne doit pas
    contourner) ; ici l'absence de `sids` veut dire **VIDE**. Un même champ ne
    pouvait pas porter les deux sens sans rendre les deux illisibles — d'où deux
    verbes plutôt qu'un drapeau.

    Créer n'est pas écraser : un jeu déjà présent ⇒ 409, l'existant intact.

    RM2448 — `move_from` SCINDE : les `sids` retenus quittent le jeu source dans
    la MÊME écriture que la création du nouveau. Un split à mi-chemin (nouveau
    jeu créé mais source pas nettoyée, ou l'inverse) laisserait un état
    incohérent. Un split retire quelque chose : il ARCHIVE (RM2443), là où une
    création simple ne le fait pas."""
    user = _session_set_user(auth_ctx)
    group = _session_set_group(payload.get("group"))
    label = str(payload.get("label") or "").strip()
    if len(label) > SET_LABEL_MAX:
        raise ApiError(400, f"label trop long ({len(label)} > {SET_LABEL_MAX})")
    store = _session_set_load()
    if _session_set_get(store, user, group):
        raise ApiError(409, f"le jeu « {group} » existe déjà")
    rule = payload.get("rule")
    if rule is not None:                       # RM2452 : jeu DÉRIVÉ
        rule = _rule_norm(rule)
    sids = payload.get("sids")
    if sids is not None and not isinstance(sids, list):
        raise ApiError(400, "sids doit être une liste de sid")
    if rule and sids:
        raise ApiError(400, "un jeu dérivé n'a pas de liste : sa règle la produit")
    wanted = {str(s) for s in (sids or [])}
    entries = _entries_for_sids(wanted, user, store) if wanted else []
    if len(entries) > SESSION_SET_MAX:
        raise ApiError(409, f"le jeu dépasserait {SESSION_SET_MAX} entrées "
                            f"({len(entries)})")
    # RM2448 — split : retrait des sid retenus du jeu source, dans cette écriture
    src = payload.get("move_from")
    moved = []
    if src is not None:
        src = _session_set_group(src)
        if src == group:
            raise ApiError(400, "move_from ne peut pas être le jeu créé lui-même")
        src_rec = _session_set_get(store, user, src)
        if not src_rec:
            raise ApiError(404, f"aucun jeu enregistré ({user}/{src})")
        _reject_if_derived(src_rec, "scission impossible depuis un jeu dérivé")
        kept = [e for e in (src_rec.get("entries") or []) if e.get("sid") not in wanted]
        moved = [e.get("sid") for e in (src_rec.get("entries") or []) if e.get("sid") in wanted]
        # les entrées du SOURCE font foi : elles portent titre et politique de
        # reprise déjà réglés, que l'instantané des vivantes ne connaît pas
        by_sid = {e["sid"]: e for e in entries}
        entries = [dict(e) for e in (src_rec.get("entries") or []) if e.get("sid") in wanted]
        entries += [e for sid, e in by_sid.items() if sid not in set(moved)]
        src_rec["entries"] = kept
    rec = {"saved_at": int(time.time()), "saved_by": (auth_ctx or {}).get("user"),
           "autostart": True, "entries": entries}
    if rule:
        rec["rule"] = rule
        rec.pop("entries")                     # le contenu se calcule, il ne se stocke pas
    if label:
        rec["label"] = label
    _session_set_put(store, user, group, rec)
    # on vient de le créer pour y travailler : il devient courant, et l'on
    # rebascule en vue « jeu » (une vue ne reçoit rien — RM2446)
    u = store.setdefault("users", {}).setdefault(user, {})
    u["current"], u["view"] = group, "set"
    # une création n'ôte rien (archive=False) ; un split, si (RM2443)
    _write_session_set(store, archive=bool(moved))
    resolved = _set_entries(rec)
    return {"user": user, "group": group, "label": rec.get("label") or group,
            "derived": bool(rule), "rule": rule,
            "count": len(resolved), "current": group, "entries": resolved,
            "moved_from": src if moved else None, "moved": moved}


def op_session_set_rule(payload: dict, auth_ctx: dict | None = None) -> dict:
    """RM2452 — remplace la RÈGLE d'un jeu dérivé. Créer une règle sans pouvoir la
    corriger obligeait à supprimer puis recréer le jeu. Refusé sur un jeu manuel :
    lui poser une règle jetterait silencieusement ses entrées — qu'il le devienne
    est une décision à part entière, pas un effet de bord d'une édition."""
    user = _session_set_user(auth_ctx)
    group = _session_set_group(payload.get("group"))
    rule = _rule_norm(payload.get("rule"))
    store = _session_set_load()
    rec = _session_set_get(store, user, group)
    if not rec:
        raise ApiError(404, f"aucun jeu enregistré ({user}/{group})")
    if not rec.get("rule"):
        raise ApiError(400, f"le jeu « {group} » est manuel : une règle jetterait "
                            f"ses {len(rec.get('entries') or [])} entrée(s)")
    rec["rule"] = rule
    rec["saved_at"] = int(time.time())
    _write_session_set(store, archive=False)   # la règle change, rien n'est perdu
    entries = _set_entries(rec)
    return {"user": user, "group": group, "rule": rule, "derived": True,
            "count": len(entries), "entries": entries}


def op_session_set_materialize(payload: dict, auth_ctx: dict | None = None) -> dict:
    """RM2452 — FIGE un jeu dérivé en jeu manuel, avec son contenu du moment. Le
    meilleur des deux : on part d'une règle pour constituer l'ensemble sans
    effort, puis on le fige pour l'amender à la main."""
    user = _session_set_user(auth_ctx)
    group = _session_set_group(payload.get("group"))
    store = _session_set_load()
    rec = _session_set_get(store, user, group)
    if not rec:
        raise ApiError(404, f"aucun jeu enregistré ({user}/{group})")
    if not rec.get("rule"):
        raise ApiError(400, f"le jeu « {group} » est déjà manuel")
    rec["entries"] = _set_entries(rec)
    rec.pop("rule")
    rec["saved_at"] = int(time.time())
    _session_set_put(store, user, group, rec)
    _write_session_set(store, archive=False)   # rien n'est perdu : on fige
    return {"user": user, "group": group, "derived": False,
            "count": len(rec["entries"]), "entries": rec["entries"]}


def op_session_set_retention(payload: dict, auth_ctx: dict | None = None) -> dict:
    """RM2452 — rétention d'affichage d'un jeu : masquer les entrées inactives
    depuis N jours. `0` (défaut) = rien n'est masqué. MASQUER, jamais supprimer :
    l'entrée reste dans le jeu et revient d'un clic. Aucun nettoyage automatique
    — décision explicite : un jeu ne doit pas perdre de session tout seul."""
    user = _session_set_user(auth_ctx)
    group = _session_set_group(payload.get("group"))
    try:
        days = int(payload.get("days"))
    except (TypeError, ValueError):
        raise ApiError(400, "days (entier de jours, 0 = désactivé) requis")
    if days < 0 or days > 3650:
        raise ApiError(400, "days doit être compris entre 0 et 3650")
    store = _session_set_load()
    rec = _session_set_get(store, user, group)
    if not rec:
        raise ApiError(404, f"aucun jeu enregistré ({user}/{group})")
    rec["hide_idle_days"] = days
    _write_session_set(store, archive=False)   # réglage d'affichage : rien perdu
    return {"user": user, "group": group, "hide_idle_days": days}


def op_session_set_move(payload: dict, auth_ctx: dict | None = None) -> dict:
    """RM2449 — DÉPLACE des sessions vers un jeu EXISTANT. `create {move_from}`
    (RM2448) fabrique un jeu neuf et refuse un nom déjà pris : verser dans un jeu
    existant n'avait donc aucun chemin.

    Verbe dédié plutôt qu'une extension de `save` : `save` est une UNION, elle
    n'ôte jamais rien (garde-fou RM2439), tandis qu'un déplacement retire du jeu
    source. Les mélanger rendrait `save` destructeur selon un paramètre.

    `from` vaut le jeu courant ; `copy` ajoute sans retirer (une session peut
    appartenir à plusieurs jeux, RM2445). Source et cible changent dans la MÊME
    écriture — jamais l'une sans l'autre. Un déplacement retire : il archive
    (RM2443) ; une copie, non."""
    user = _session_set_user(auth_ctx)
    store = _session_set_load()
    to = _session_set_group(payload.get("to"))
    src = _session_set_group(payload.get("from") or _current_set(user, store))
    if to == src:
        raise ApiError(400, "le jeu de destination est le jeu d'origine")
    sids = payload.get("sids")
    if not isinstance(sids, list) or not sids:
        raise ApiError(400, "sids (liste non vide) requis")
    wanted = {str(s) for s in sids}
    dst_rec = _session_set_get(store, user, to)
    if not dst_rec:                       # créer est le travail de `create`
        raise ApiError(404, f"aucun jeu enregistré ({user}/{to})")
    src_rec = _session_set_get(store, user, src)
    if not src_rec:
        raise ApiError(404, f"aucun jeu enregistré ({user}/{src})")
    _reject_if_derived(dst_rec, "déplacement impossible vers un jeu dérivé")
    _reject_if_derived(src_rec, "déplacement impossible depuis un jeu dérivé")
    src_entries = src_rec.get("entries") or []
    taken = [e for e in src_entries if e.get("sid") in wanted]
    if not taken:
        raise ApiError(404, f"aucune des sessions demandées n'est dans « {src} »")
    dst_entries = list(dst_rec.get("entries") or [])
    present = {e.get("sid") for e in dst_entries}
    # union côté cible : une session déjà là n'y entre pas deux fois
    dst_entries += [dict(e) for e in taken if e.get("sid") not in present]
    if len(dst_entries) > SESSION_SET_MAX:
        raise ApiError(409, f"le jeu « {to} » dépasserait {SESSION_SET_MAX} entrées "
                            f"({len(dst_entries)}) — rien n'a été déplacé")
    copy = bool(payload.get("copy"))
    dst_rec["entries"] = dst_entries
    dst_rec["saved_at"] = int(time.time())
    if not copy:
        src_rec["entries"] = [e for e in src_entries if e.get("sid") not in wanted]
    _session_set_put(store, user, to, dst_rec)
    _session_set_put(store, user, src, src_rec)
    _write_session_set(store, archive=not copy)
    return {"user": user, "to": to, "from": src, "copied": copy,
            "moved": [e.get("sid") for e in taken],
            "to_count": len(dst_entries), "from_count": len(src_rec.get("entries") or [])}


# Réhydrater un transcript, c'est le relire dans le contexte. On estime le volume
# par la taille du fichier (~4 octets par token, ordre de grandeur assumé) et on
# le valorise au tarif de lecture de cache du modèle — la moins chère des entrées,
# donc un plancher honnête plutôt qu'un chiffre flatteur.
BYTES_PER_TOKEN = 4


def _cache_read_usd_per_mtok() -> float | None:
    try:
        pricing = yaml_safe_load(_pricing_file().read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return None
    vals = [f.get("cache_read_per_mtok_usd") for f in (pricing.get("models") or {}).values()
            if isinstance(f, dict) and f.get("cache_read_per_mtok_usd")]
    return min(vals) if vals else None


def op_session_set_estimate(qs: dict, auth_ctx: dict | None = None) -> dict:
    """RM2451 — ce que coûterait un « Tout relancer » : nombre d'entrées
    réellement relançables et volume de contexte à réhydrater. Douze sessions
    relancées, ce sont douze réhydratations — le bouton doit l'annoncer AVANT,
    pas le facturer après. Ordre de grandeur assumé (taille du transcript /
    ~4 octets par token, tarif de lecture de cache le plus bas)."""
    user = _session_set_user(auth_ctx)
    group = _session_set_group(qs.get("group") or _current_set(user))
    rec = _session_set_get(_session_set_load(), user, group)
    if not rec:
        raise ApiError(404, f"aucun jeu enregistré ({user}/{group})")
    live = {s["rm_id"] for s in _list_sessions()}
    relaunchable, already, lost, total = 0, 0, 0, 0
    for e in _set_entries(rec):
        if e.get("sid") in live:
            already += 1
            continue
        info = _transcript_info(e.get("session_id"))
        if not info.get("bytes"):
            lost += 1                      # transcript perdu : la relance échouera
            continue
        relaunchable += 1
        total += info["bytes"]
    tokens = total // BYTES_PER_TOKEN
    rate = _cache_read_usd_per_mtok()
    return {"user": user, "group": group, "relaunchable": relaunchable,
            "already_live": already, "lost": lost, "bytes": total,
            "tokens_est": tokens,
            "usd_est": round(tokens / 1_000_000 * rate, 2) if rate else None}


def op_session_set_get(qs: dict, auth_ctx: dict | None = None) -> dict:
    """RM2395 — relit le jeu (user, group) et marque chaque entrée `alive` selon
    l'état tmux courant. `exists=False` si aucun jeu enregistré."""
    user = _session_set_user(auth_ctx)
    group = _session_set_group(qs.get("group"))
    rec = _session_set_get(_session_set_load(), user, group)
    if not rec:
        return {"user": user, "group": group, "label": group,
                "exists": False, "entries": [], "count": 0}
    total = _set_total(rec)
    live = {s["rm_id"] for s in _list_sessions()}
    # RM2427 : `restart` EFFECTIF (réglage explicite, sinon défaut [WIP]/idle) —
    # l'UI affiche et bascule cette valeur sans avoir à rejouer la règle.
    entries = [dict(e, alive=(e.get("sid") in live),
                    last_active=_transcript_age(e.get("session_id")),   # RM2451
                    restart=(e.get("restart") if e.get("restart") in RESTART_POLICIES
                             else _default_restart(e.get("session_id"))))
               for e in _set_entries(rec)]
    return {"user": user, "group": group, "label": rec.get("label") or group,
            "derived": bool(rec.get("rule")), "rule": rec.get("rule"),
            "hide_idle_days": rec.get("hide_idle_days") or 0,
            "total": total, "truncated": total > len(entries),
            "exists": True,
            "saved_at": rec.get("saved_at"), "saved_by": rec.get("saved_by"),
            "autostart": bool(rec.get("autostart", False)),
            "count": len(entries), "entries": entries}


# Temporisation entre deux démarrages d'une relance en lot : chaque entrée ouvre
# un TUI complet ; on espace les tmux new-session pour ne pas les bousculer.
SESSION_SET_RELAUNCH_DELAY = float(os.environ.get("KARL_AGENT_RELAUNCH_DELAY", "0.6"))


def _model_key_for_value(engine: str, value: str | None) -> str:
    """Le store garde la VALEUR de modèle résolue (RM1941), mais op_spawn attend
    une CLÉ de catalogue. Reverse-map value → key pour le fallback spawn ; clé
    inconnue du catalogue courant → "" (défaut moteur, jamais une valeur brute)."""
    if not value:
        return ""
    for k, v in _model_catalog().get(engine, {}).items():
        if v == value:
            return k
    return ""


def _relaunch_entry(e: dict, allow_spawn: bool, auth_ctx: dict | None = None) -> dict:
    """RM2427 — relance RÉELLE d'UNE entrée de jeu ; renvoie sa ligne de rapport
    ({sid, action, error?}). Cœur partagé par la relance unitaire (clic sur une
    tuile grise) et la relance en lot. Idempotent : entrée déjà vivante =
    `skipped` (jamais dupliquée ni tuée)."""
    sid = e.get("sid")
    if not sid or not _valid_sid(sid):
        return {"sid": sid, "action": "failed", "error": "sid invalide"}
    if _has_session(sid):
        return {"sid": sid, "action": "skipped"}
    engine = e.get("engine") or "claude"
    try:
        op_resume({"session_id": e.get("session_id"), "rm_id": sid, "engine": engine}, auth_ctx)
        return {"sid": sid, "action": "resumed"}
    except ApiError as ex:
        if ex.code == 409:   # course : devenue vivante entre le check et le resume
            return {"sid": sid, "action": "skipped"}
        if ex.code in (404, 410) and allow_spawn and e.get("cwd"):
            try:
                op_spawn({"rm_id": sid, "engine": engine, "cwd": e.get("cwd"),
                          "model": _model_key_for_value(engine, e.get("model"))}, auth_ctx)
                return {"sid": sid, "action": "spawned"}
            except ApiError as ex2:
                return {"sid": sid, "action": "failed", "error": ex2.msg}
        return {"sid": sid, "action": "failed", "error": ex.msg}


def op_session_set_relaunch(payload: dict, auth_ctx: dict | None = None) -> dict:
    """RM2395/RM2427 — relance RÉELLE des entrées du jeu (user, group).

    `sid` fourni ⇒ relance UNITAIRE de cette seule entrée (c'est le chemin normal
    depuis RM2427 : la reprise n'ouvre plus rien, l'opérateur clique la tuile
    grise qu'il veut réveiller). Sans `sid` ⇒ lot complet (bouton « tout
    relancer », séquentiel + temporisé : chaque entrée ouvre un TUI).

    Dans les deux cas : resume natif du moteur (`resumed`) ; si le transcript ou
    le cwd a disparu (410/404), spawn neuf UNIQUEMENT si `spawn` est demandé
    (opt-in, défaut off) et SANS prompt initial — sinon `failed` avec le motif."""
    user = _session_set_user(auth_ctx)
    group = _session_set_group(payload.get("group"))
    allow_spawn = bool(payload.get("spawn"))
    rec = _session_set_get(_session_set_load(), user, group)
    if not rec:
        raise ApiError(404, f"aucun jeu enregistré ({user}/{group})")
    entries = _set_entries(rec)[:SESSION_SET_MAX]
    sid = str(payload.get("sid") or "").strip()
    if sid:
        entries = [e for e in entries if e.get("sid") == sid]
        if not entries:
            raise ApiError(404, f"sid absent du jeu {user}/{group} : {sid}")
    report, started = [], 0
    for e in entries:
        # temporisation entre deux DÉMARRAGES seulement (une entrée déjà vivante
        # n'ouvre rien : elle ne doit pas ralentir le lot)
        if started and not _has_session(e.get("sid") or ""):
            time.sleep(SESSION_SET_RELAUNCH_DELAY)
        r = _relaunch_entry(e, allow_spawn, auth_ctx)
        if r["action"] != "skipped":
            started += 1
        report.append(r)
    counts = {}
    for r in report:
        counts[r["action"]] = counts.get(r["action"], 0) + 1
    return {"user": user, "group": group, "counts": counts, "report": report}


def op_session_set_autostart(payload: dict, auth_ctx: dict | None = None) -> dict:
    """DÉPRÉCIÉ (RM2450) — le drapeau `autostart` ne gouverne plus rien : la
    reprise au démarrage suit la politique `restart` PAR ENTRÉE, sur le jeu
    courant (`_autostart_replay`). L'endpoint est conservé pour ne pas casser un
    client ancien, et le drapeau reste stocké, sans effet.

    RM2395/RM2427 — (dé)marque le jeu (user, group) pour reprise automatique.
    Depuis RM2427 la reprise est « en idle » : le jeu marqué est exposé en tuiles
    grises (cf. `_ghost_sessions`), aucun TUI n'est ouvert. Ne re-snapshote pas :
    ne touche que le drapeau `autostart`."""
    user = _session_set_user(auth_ctx)
    group = _session_set_group(payload.get("group"))
    if "autostart" not in payload:
        raise ApiError(400, "autostart (booléen) requis")
    store = _session_set_load()
    rec = _session_set_get(store, user, group)
    if not rec:
        raise ApiError(404, f"aucun jeu enregistré ({user}/{group})")
    rec["autostart"] = bool(payload["autostart"])
    _session_set_put(store, user, group, rec)
    _write_session_set(store)
    return {"user": user, "group": group, "autostart": rec["autostart"]}


def op_session_set_restart(payload: dict, auth_ctx: dict | None = None) -> dict:
    """RM2427 — règle la politique de reprise d'UNE session du jeu :
    `auto` (relancée pour de bon au démarrage) ou `idle` (tuile grise, relance au
    clic). Le défaut vient du marqueur `[WIP]` à l'enregistrement ; ce réglage-ci
    est explicite et survit aux ré-enregistrements du jeu."""
    user = _session_set_user(auth_ctx)
    group = _session_set_group(payload.get("group"))
    sid = str(payload.get("sid") or "").strip()
    policy = str(payload.get("restart") or "").strip().lower()
    if policy not in RESTART_POLICIES:
        raise ApiError(400, f"restart doit valoir {' ou '.join(RESTART_POLICIES)}")
    store = _session_set_load()
    rec = _session_set_get(store, user, group)
    if not rec:
        raise ApiError(404, f"aucun jeu enregistré ({user}/{group})")
    entry = next((e for e in (rec.get("entries") or []) if e.get("sid") == sid), None)
    if not entry:
        raise ApiError(404, f"sid absent du jeu {user}/{group} : {sid}")
    entry["restart"] = policy
    _write_session_set(store)
    return {"user": user, "group": group, "sid": sid, "restart": policy}


def op_session_set_delete(qs: dict, auth_ctx: dict | None = None) -> dict:
    """RM2395 — efface le jeu (user, group). RM2427 : avec `sid`, n'efface QUE
    cette entrée — une session terminée volontairement (`/exit`) doit pouvoir
    sortir du jeu sans effacer les 14 autres. Le jeu vidé de ses entrées est
    conservé (ses réglages aussi) ; c'est `sid` absent qui le supprime."""
    user = _session_set_user(auth_ctx)
    group = _session_set_group(qs.get("group"))
    store = _session_set_load()
    groups = store.get("users", {}).get(user, {}).get("groups", {})
    if group not in groups:
        raise ApiError(404, f"aucun jeu enregistré ({user}/{group})")
    sid = str(qs.get("sid") or "").strip()
    if not sid:
        del groups[group]
        _write_session_set(store)
        return {"user": user, "group": group, "deleted": True}
    rec = groups[group]
    _reject_if_derived(rec, "retrait impossible")             # RM2452
    entries = rec.get("entries") or []
    kept = [e for e in entries if e.get("sid") != sid]
    if len(kept) == len(entries):
        raise ApiError(404, f"sid absent du jeu {user}/{group} : {sid}")
    rec["entries"] = kept
    undo = _write_session_set(store)
    # RM2451 : de quoi proposer « annuler » plutôt qu'une confirmation préalable —
    # l'état d'avant vient d'être archivé, il suffit de le désigner (RM2443).
    return {"user": user, "group": group, "sid": sid, "deleted": True,
            "count": len(kept), "undo": undo}


# ── Reprise « en idle » des jeux enregistrés (RM2427, ex-autostart RM2395) ────
# Un jeu marqué `autostart` n'ouvre PLUS de tmux au démarrage (RM2395 rejouait un
# `resume` par entrée : N TUI, N réhydratations de contexte, pour une ou deux
# sessions réellement pilotées derrière). Ses entrées non vivantes sont exposées
# telles quelles dans GET /sessions — des « fantômes » : mêmes tuiles, pastille
# grise, aucun processus. Un clic sur l'une d'elles déclenche la relance réelle
# (POST /session-set/relaunch {sid}). Le lot d'un coup reste possible (bouton
# « tout relancer »), mais il n'est plus le comportement par défaut.


# Marqueur [DONE] d'une session close : le calcul passe par un glob des stores
# claude, or /sessions est polled en continu → résultat mémorisé 30 s (les
# transcripts d'une session TERMINÉE ne bougent plus, le cache ne ment pas).
_DONE_CACHE: dict = {"at": 0.0, "map": {}}
_DONE_CACHE_TTL = 30.0


# RM2539/RM2547 — lecteur de métadonnées par STORE déclaré dans ENGINES. Ajouter
# un moteur, c'est déclarer son contrat et poser sa fonction ici : le reste du
# code (cache, marqueurs, tuiles, reprise) ne bouge pas.
_ENGINE_META = {
    "opencode_db": _opencode_session_meta,
    "vibe_files": _vibe_session_meta,
}


def _transcript_jsonl(session_id: str | None):
    """Transcript d'une session dans les stores claude, ou None (id invalide,
    session inconnue, store absent). Point d'entrée unique de la recherche —
    partagé par le marqueur `[WIP]`/`[DONE]` et le titre (RM2439)."""
    if not session_id or not _SID_RE.match(session_id):
        return None
    return next((p for root in CLAUDE_STORES if root.is_dir()
                 for p in root.glob(f"*/{session_id}.jsonl")), None)


def _transcript_info(session_id: str | None, engine: str | None = None) -> dict:
    """RM2451 — méta du transcript, MÉMORISÉE : {mark, title, mtime, bytes}.
    `/sessions` est polled en continu et chaque entrée de jeu demandait déjà son
    marqueur puis son titre — soit deux globs par session et par appel. Une
    lecture unique, mise en cache 30 s, sert les trois usages (marqueur, nom,
    âge). Un transcript absent ou illisible rend un dict vide : dans le doute,
    rien de marqué, rien de daté.

    RM2539 — la SOURCE dépend du moteur : transcripts JSONL pour claude, base
    du moteur pour opencode. Le cache et le contrat de sortie sont communs."""
    if not session_id or not _valid_session_id(session_id, engine):
        return {}
    now = time.time()
    if now - _DONE_CACHE["at"] > _DONE_CACHE_TTL:
        _DONE_CACHE.update({"at": now, "map": {}})
    ckey = f"{engine or ''}:{session_id}"      # RM2547 : même UUID, moteurs distincts
    if ckey in _DONE_CACHE["map"]:
        return _DONE_CACHE["map"][ckey]
    if not _SID_RE.match(session_id) or engine:
        # Moteur tiers (ou moteur imposé par l'appelant) : les méta viennent de
        # SON store. Le marqueur [WIP]/[DONE] y est porté par le titre, comme
        # côté claude : même extraction.
        # ⚠ vibe émet des UUID comme claude (RM2547) : sans `engine`, une telle
        # session est traitée en claude — c'est l'appelant qui lève l'ambiguïté,
        # via `_engine_of_session` ou l'`engine` transmis (RM2536).
        store = (ENGINES.get(engine or "", {}) or {}).get("store")
        reader = _ENGINE_META.get(store or "")
        if reader is None and not _SID_RE.match(session_id):
            reader = next((_ENGINE_META[ENGINES[n]["store"]] for n in ENGINES
                           if ENGINES.get(n, {}).get("store") in _ENGINE_META
                           and _ENGINE_SID_RES.get(n, _SID_RE).match(session_id)), None)
        meta = reader(session_id) if reader else {}
        raw = meta.get("title") or ""
        m = _MARK_RE.match(raw)
        info = {"mark": m.group(1).lower() if m else None,
                "title": _MARK_RE.sub("", raw).strip() or None,
                "mtime": meta.get("mtime"), "cwd": meta.get("cwd")} if meta else {}
        _DONE_CACHE["map"][ckey] = info
        return info
    info: dict = {}
    jf = _transcript_jsonl(session_id)
    if jf:
        try:
            meta = _jsonl_tail_meta(jf)
            raw = meta.get("title") or ""
            m = _MARK_RE.match(raw)
            info = {"mark": m.group(1).lower() if m else None,
                    "title": _MARK_RE.sub("", raw).strip() or None,
                    "mtime": meta.get("mtime"), "bytes": jf.stat().st_size}
        except OSError:
            info = {}
    _DONE_CACHE["map"][ckey] = info
    return info


def _transcript_title(session_id: str | None) -> str | None:
    """RM2439 — titre du transcript, marqueur `[WIP]`/`[DONE]` ôté. Sert à NOMMER
    une entrée de jeu : un sid nu ne dit pas de quelle session il s'agit, et le
    sujet Redmine du ticket (seul libellé qu'affichait la tuile grise) n'existe
    pas pour une session ancrée sur un slug."""
    return _transcript_info(session_id).get("title")


def _transcript_age(session_id: str | None):
    """RM2451 — dernier mouvement du transcript (epoch), ou None. Une tuile grise
    d'il y a une heure et une du mois dernier étaient indiscernables, alors que
    reprendre l'une ou l'autre n'a pas le même sens : contexte périmé, et
    réhydratation à payer."""
    return _transcript_info(session_id).get("mtime")


def _session_mark(session_id: str | None) -> str | None:
    """RM2427 — marqueur `[WIP]` / `[DONE]` posé par /session-mark, en minuscules
    (None si absent, introuvable ou illisible)."""
    return _transcript_info(session_id).get("mark")


def _is_marked_done(session_id: str | None) -> bool:
    return _session_mark(session_id) == "done"


# Politique de reprise, PAR ENTRÉE de jeu (RM2427) : `auto` = la session est
# vraiment relancée au démarrage (défaut des sessions marquées `[WIP]` — un
# travail en cours reprend tout seul) ; `idle` = tuile grise, relance au clic
# (défaut de tout le reste). Réglable par session (POST /session-set/restart).
RESTART_POLICIES = ("auto", "idle")


def _default_restart(session_id: str | None) -> str:
    return "auto" if _session_mark(session_id) == "wip" else "idle"


def _forget_done_entries(user: str, groups: dict) -> bool:
    """RM2427 — une session TERMINÉE (`/exit`, plus aucun tmux) dont le
    transcript est marqué `[DONE]` sort du jeu toute seule : elle a fini son
    travail, sa tuile grise n'a plus lieu d'être. Les sessions vivantes et les
    non marquées sont conservées. Renvoie True si le store a changé."""
    live = {s["rm_id"] for s in _list_sessions()}
    changed = False
    for group, rec in groups.items():
        if rec.get("rule"):
            continue                      # RM2452 : rien à curer dans un dérivé
        entries = rec.get("entries") or []
        kept = [e for e in entries
                if e.get("sid") in live or not _is_marked_done(e.get("session_id"))]
        if len(kept) != len(entries):
            dropped = [e.get("sid") for e in entries if e not in kept]
            rec["entries"] = kept
            changed = True
            sys.stderr.write(f"jeu {user}/{group} : {len(dropped)} session(s) "
                             f"[DONE] terminée(s) retirée(s) — {', '.join(map(str, dropped))}\n")
    return changed


def _ghost_sessions(auth_ctx: dict | None = None, show_old: bool = False) -> list:
    """Entrées ENREGISTRÉES et non vivantes du JEU COURANT de l'utilisateur,
    au format d'une entrée /sessions (`ghost: True`, `state: "ghost"`). Un sid déjà
    vivant n'en produit jamais (le fantôme disparaît dès que la session existe) ;
    `resumable` dit si un transcript est mémorisé (sinon la relance exigera le
    fallback spawn). client/projet sont résolus depuis le cwd enregistré pour que
    la tuile se range dans le bon groupe.

    RM2445 — le périmètre est le **jeu courant**, plus l'union des jeux
    `autostart` : sélectionner un jeu doit CHANGER ce qu'on voit, sinon la
    bascule n'a aucun effet observable. `autostart` garde son rôle propre — le
    rejeu des entrées `restart:auto` au démarrage de karl-agent
    (`_autostart_replay`), qui n'a rien à voir avec l'affichage.

    Passe d'entretien au vol : les sessions TERMINÉES marquées `[DONE]` sortent
    du jeu (cf. `_forget_done_entries`) — pas de tuile grise pour un travail
    fini."""
    user = _session_set_user(auth_ctx)
    live = {s["rm_id"] for s in _list_sessions()}
    out, seen = [], set()
    store = _session_set_load()
    groups = ((store.get("users") or {}).get(user, {}).get("groups") or {})
    if _forget_done_entries(user, groups):
        _write_session_set(store)
    # RM2446 : le périmètre suit la VUE — le jeu courant (`set`), aucun fantôme
    # (`live` : on ne regarde que ce qui tourne), ou tous les jeux (`all`).
    view = _current_view(user, store)
    if view == "live":
        return []
    m = _VIEW_CLIENT_RE.match(view)
    if m:
        # RM2452 : vue par client — un jeu dérivé qu'on n'a même pas eu à créer.
        for e in _derived_entries({"client": m.group(1)}):
            sid = e.get("sid")
            if not sid or sid in live or sid in seen:
                continue
            seen.add(sid)
            g = dict(e, rm_id=sid, is_ticket=_is_ticket_sid(sid), ghost=True,
                     state="ghost", group=view, group_label=m.group(1),
                     attached=False, created=None,
                     last_active=_transcript_age(e.get("session_id")),
                     resumable=bool(e.get("session_id")), saved_at=None)
            client, project = _pm_project_of_cwd(e.get("cwd"))
            if client:
                g["client"], g["project"] = client, project
            out.append(g)
        return out
    group = _current_set(user, store)
    picked = groups.items() if view == "all" else \
        ([(group, groups[group])] if group in groups else [])
    for group, rec in picked:
        # RM2452 : rétention OPTIONNELLE — masquer (jamais supprimer) les entrées
        # inactives depuis N jours. Désactivée par défaut : aucun nettoyage
        # automatique, aucune perte ; l'entrée reste dans le jeu et revient d'un
        # clic (`show_old=1`).
        hide_days = 0 if show_old else int(rec.get("hide_idle_days") or 0)
        for e in _set_entries(rec)[:SESSION_SET_MAX]:
            sid = e.get("sid")
            if not sid or sid in live or sid in seen or not _valid_sid(sid):
                continue
            if hide_days:
                seen_at = _transcript_age(e.get("session_id"))
                if seen_at and (time.time() - seen_at) > hide_days * 86400:
                    continue
            seen.add(sid)
            g = {
                "rm_id": sid, "is_ticket": _is_ticket_sid(sid), "ghost": True,
                # RM2442 : le libellé suit le groupe — quand plusieurs jeux sont
                # repris, la tuile doit dire de QUEL jeu elle vient
                "state": "ghost", "group": group,
                "group_label": rec.get("label") or group,
                "attached": False, "created": None,
                "engine": e.get("engine"), "session_id": e.get("session_id"),
                "cwd": e.get("cwd"), "model": e.get("model"),
                # RM2439 : nom mémorisé de la session — la tuile grise d'une
                # session ancrée sur un slug n'a aucun sujet Redmine à afficher
                "title": e.get("title"),
                # RM2451 : âge de la SESSION (dernier mouvement du transcript),
                # à ne pas confondre avec `saved_at` qui date le JEU
                "last_active": _transcript_age(e.get("session_id")),
                "resumable": bool(e.get("session_id")), "saved_at": rec.get("saved_at"),
            }
            g["restart"] = e.get("restart") if e.get("restart") in RESTART_POLICIES \
                else _default_restart(e.get("session_id"))
            client, project = _pm_project_of_cwd(e.get("cwd"))
            if client:
                g["client"], g["project"] = client, project
            out.append(g)
    return out


# ── Redémarrage au lancement des sessions réglées `auto` (RM2427) ─────────────
# Seules les entrées `restart:auto` (défaut des `[WIP]`) sont VRAIMENT relancées
# au démarrage — resume seul, jamais spawn, jamais de prompt (arbitrage RM2395 :
# pas d'agent lancé sans opérateur devant). Tout le reste attend en tuile grise.
AUTOSTART_DELAY = float(os.environ.get("KARL_AGENT_AUTOSTART_DELAY", "4"))


def _autostart_replay() -> list:
    """Une passe : relance les entrées `auto` du JEU COURANT de chaque
    utilisateur. Best-effort (un jeu en échec n'empêche pas les autres). Séparée
    du thread pour être testable sans horloge.

    RM2450 — le drapeau `autostart` PAR JEU est abandonné : il ne servait plus
    qu'à autoriser la politique `restart:auto` par entrée, soit deux réglages
    pour une seule question — d'où la case dont le libellé promettait des tuiles
    grises alors qu'elle ouvrait de vrais TUI. Le périmètre devient le jeu
    courant, cohérent avec tout le reste depuis RM2445 (fantômes, adhésion, ⊖).
    Conséquence assumée : une entrée `auto` d'un autre jeu n'est plus relancée —
    on ne rouvre pas le chantier d'à côté."""
    out = []
    store = _session_set_load()
    for user, u in (store.get("users") or {}).items():
        group = _current_set(user, store)
        rec = (u.get("groups") or {}).get(group)
        if rec:
            for e in _set_entries(rec)[:SESSION_SET_MAX]:
                policy = e.get("restart") if e.get("restart") in RESTART_POLICIES \
                    else _default_restart(e.get("session_id"))
                if policy != "auto" or _has_session(e.get("sid") or ""):
                    continue
                r = _relaunch_entry(e, allow_spawn=False)
                out.append({"user": user, "group": group, **r})
                if r["action"] != "skipped":
                    time.sleep(SESSION_SET_RELAUNCH_DELAY)
    return out


def _autostart_thread() -> None:
    time.sleep(AUTOSTART_DELAY)   # laisse tmux / le daemon se stabiliser après un boot
    try:
        for r in _autostart_replay():
            sys.stderr.write(f"reprise auto {r.get('user')}/{r.get('group')} "
                             f"{r.get('sid')} : {r.get('action')}"
                             f"{' — ' + r['error'] if r.get('error') else ''}\n")
    except Exception as e:  # noqa: BLE001 — best-effort, ne tue jamais le démarrage
        sys.stderr.write(f"reprise auto : passe en échec (non fatal) : {e}\n")


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


def _list_opencode_sessions() -> list:
    """RM2539 (correctif) — conversations opencode connues : (session_id, méta).
    Source : la base du moteur, en lecture seule."""
    if not OPENCODE_DB.is_file():
        return []
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True, timeout=2)
        try:
            rows = con.execute("SELECT id, title, directory, time_updated, time_created "
                               "FROM session").fetchall()
        finally:
            con.close()
    except Exception:
        return []
    out = []
    for sid, title, directory, updated, created in rows:
        ms = updated or created or 0
        out.append((sid, {"title": title or None, "cwd": directory or None,
                          "mtime": int(ms) // 1000 if ms else None}))
    return out


def _list_vibe_sessions() -> list:
    """RM2547 (correctif) — conversations vibe connues : (session_id, méta).
    Source : les meta.json des dossiers de session (l'id du meta fait foi)."""
    if not VIBE_SESSIONS.is_dir():
        return []
    out = []
    for d in VIBE_SESSIONS.glob("session_*"):
        try:
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sid = meta.get("session_id")
        if not sid:
            continue
        m = _vibe_session_meta(sid)
        if m:
            out.append((sid, m))
    return out


# Énumération par moteur — pendant « découverte » de `_ENGINE_META` (lecture
# d'UNE session). Un moteur absent d'ici n'apparaît pas au panneau de reprise.
_ENGINE_LIST = {
    "opencode": _list_opencode_sessions,
    "vibe": _list_vibe_sessions,
}


def resume_engines() -> list:
    """Moteurs dont on sait ET reprendre ET découvrir les conversations — c'est
    la liste que le cockpit doit proposer, plutôt qu'un « claude » codé en dur
    (RM2539 : la reprise multi-moteur était livrée sans que le panneau ne
    permette d'en choisir un autre)."""
    return [n for n in ENGINES
            if _resume_support(n) and (n == "claude" or n in _ENGINE_LIST)]


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

    if f_engine and f_engine not in resume_engines():
        return []      # moteur inconnu, ou sans découverte : rien à proposer
    runs_idx = _runs_by_session()
    sessions = _list_sessions()
    live_rm = {s["rm_id"] for s in sessions}
    # RM2396 : une session reprise doit passer « tmux vivant » DE SUITE, y compris
    # ancrée sur un slug (sans jonction ticket, donc absente de runs_idx). L'index
    # clé-tmux (RM2144, écrit à chaque spawn ET resume) donne le session_id
    # réellement servi par chaque tmux vivant → match direct par session_id, sans
    # dépendre d'une jonction. La jonction reste un repli (ticket re-spawné sur un
    # autre session_id).
    live_sids = {ki["session_id"] for s in sessions
                 if (ki := _key_info(s["rm_id"])) and ki.get("session_id")}
    def _entry(engine, sid, title_raw, cwd, mtime):
        """Ligne du panneau de reprise, commune à tous les moteurs."""
        m = _MARK_RE.match(title_raw or "")
        runs = runs_idx.get(sid, [])
        client, project = _pm_project_of_cwd(cwd)
        if not client and runs:
            client, project = runs[-1]["client"], runs[-1]["project"]
        return {
            "engine": engine, "session_id": sid,
            "title": _MARK_RE.sub("", title_raw or "") or None,
            "mark": m.group(1).lower() if m else None,
            "cwd": cwd, "mtime": mtime,
            "client": client, "project": project,
            "tickets": [{"rm_id": r["rm_id"], "n": r.get("n")} for r in runs],
            "live": sid in live_sids or any(r["rm_id"] in live_rm for r in runs),
        }

    out, seen = [], set()
    # RM2539 (correctif) : les moteurs tiers énumèrent leurs conversations par
    # leur propre store — la découverte était restée claude-only alors que la
    # reprise, elle, était déjà multi-moteur : le panneau ne montrait donc
    # jamais une session opencode ou vibe.
    for engine_name, lister in _ENGINE_LIST.items():
        if f_engine and f_engine != engine_name:
            continue
        for sid, meta in lister():
            if sid in seen:
                continue
            seen.add(sid)
            out.append(_entry(engine_name, sid, meta.get("title"),
                              meta.get("cwd"), meta.get("mtime")))
    for root in (CLAUDE_STORES if f_engine in (None, "claude") else []):
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
            out.append(_entry("claude", sid, meta["title"], meta["cwd"], meta["mtime"]))

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
    out.sort(key=lambda e: e["mtime"] or 0, reverse=True)
    return out[:limit]


def _resume_cwd(jf: Path, engine: str, session_id: str) -> str | None:
    """cwd de relance pour `claude --resume` (RM2418). Le store per-session
    (figé au spawn) pouvait pointer un ANCIEN projet après un déplacement manuel
    du transcript → relance au mauvais cwd et « No conversation found ».
    Correctif : on retient le premier candidat — store per-session, puis cwd
    interne du transcript — dont le slug == dossier où vit RÉELLEMENT le .jsonl.
    Aucun ne colle → comportement historique (store, sinon transcript)."""
    smeta = _read_json_file(SESS_DIR / engine / f"{session_id}.json") or {}
    try:
        tail = _jsonl_tail_meta(jf)["cwd"]
    except OSError:
        tail = None
    slug = jf.parent.name
    for c in (smeta.get("cwd"), tail):
        if c and _slug_of(c) == slug:
            return c
    return smeta.get("cwd") or tail


def _engine_of_session(session_id: str) -> str | None:
    """RM2536 — moteur MÉMORISÉ d'une conversation, depuis les sources du
    serveur : store par session (`sessions/<engine>/<sid>.json`, dont le
    répertoire EST le moteur) puis jonctions. `None` = inconnu de l'index.

    C'est cette valeur qui fait foi face à un `engine` reçu du client : le
    moteur ne discrimine pas seulement deux conversations, il décide du binaire
    à lancer et du store où chercher le transcript."""
    if not session_id:
        return None
    try:
        for d in SESS_DIR.iterdir():
            if d.is_dir() and (d / f"{session_id}.json").is_file():
                return d.name
    except OSError:
        pass
    runs = _runs_by_session().get(session_id, [])
    return runs[0].get("engine") if runs else None


def _anchor_rm_id(session_id: str, cwd: str | None) -> str | None:
    """RM2536 — ticket d'ancrage d'une conversation reprise (nom du tmux).

    Le modèle jonction est n-m PAR CONCEPTION (`tasks/<client>/<projet>/RM<id>-<n>`
    : « une session traverse plusieurs tickets ») : une session ouverte sur le
    projet A peut porter des jonctions vers des tickets du projet B. Prendre la
    plus récente TOUS PROJETS confondus (comportement ≤ RM2144) nommait alors le
    tmux d'après un ticket étranger au projet de la session.

    Ordre de préférence : jonctions du projet du `cwd` — la plus récente, à
    défaut de récence connue l'INITIALE (`n` minimal, le ticket qui a ouvert la
    session) — puis, si le projet ne dit rien, le comportement historique."""
    runs = _runs_by_session().get(session_id, [])
    if not runs:
        return None
    client, project = _pm_project_of_cwd(cwd)
    same = [r for r in runs if client and r.get("client") == client
            and r.get("project") == project]
    pool = same or runs
    if same and not any(r.get("last_seen") or r.get("created") for r in same):
        return min(pool, key=lambda r: r.get("n", 0))["rm_id"]
    return max(pool, key=lambda r: r.get("last_seen", r.get("created", 0)))["rm_id"]


def _spawn_fallback(rm_id: str, engine: str, payload: dict,
                    auth_ctx: dict | None, why: str) -> dict:
    """RM2536 — repli « session neuve » d'une relance dont le transcript ou le
    cwd a disparu. Opt-in strict (`spawn: true`) : sans lui, on refuse en 410
    avec le motif, jamais de session muette à la place de la conversation
    attendue.

    `cwd` et `model` viennent de l'INDEX DES CLÉS (`_key_info`), pas du client :
    c'est le serveur qui sait où vivait la session, et le navigateur n'a plus à
    dicter un chemin. Sans cwd mémorisé, il n'y a rien à rouvrir → 410."""
    if not payload.get("spawn"):
        raise ApiError(410, f"{why} — relancer une session neuve ?")
    k = _key_info(rm_id) or {}
    if not k.get("cwd"):
        raise ApiError(410, f"{why}, et aucun dossier mémorisé pour {rm_id} "
                            "— lancer un spawn explicite")
    out = op_spawn({"rm_id": rm_id, "engine": engine, "cwd": k["cwd"],
                    "model": _model_key_for_value(engine, k.get("model"))}, auth_ctx)
    out["resumed"], out["spawned"], out["reason"] = False, True, why
    return out


def op_resume(payload: dict, auth_ctx: dict | None = None) -> dict:
    """Reprend une conversation TERMINÉE côté process (tmux mort) via le resume
    natif du moteur, dans une session tmux karl-RM<id> neuve. Cible : session_id
    direct, ou rm_id (+ n) → jonction la plus récente. Itération 1 : claude.

    RM2536 — c'est le chemin de relance du cockpit : une tuile envoie l'IDENTITÉ
    de sa session — le couple (`engine`, `session_id`) — et rien du contexte
    d'affichage (jeu, vue). Tout le reste (`rm_id`, `cwd`, `model`) est retrouvé
    ici, à partir des sources du serveur. `spawn: true` autorise le repli en
    session neuve quand le transcript a disparu (opt-in, ex-`_relaunch_entry`)."""
    session_id = str(payload.get("session_id") or "").strip() or None
    rm_id = str(payload.get("rm_id") or "").strip() or None
    n = payload.get("n")
    # RM2539 : la grammaire de l'id suit le MOTEUR (claude : UUID ; opencode :
    # `ses_…`). L'ancien filtre UUID unique rejetait toute session opencode ici.
    if session_id and not _valid_session_id(session_id):
        raise ApiError(400, "session_id invalide")
    if rm_id and not _valid_sid(rm_id):
        raise ApiError(400, "rm_id invalide (id de ticket ou slug)")

    # RM2536 : moteur EXPLICITE, recoupé avec l'index — un `engine` absent ne
    # retombe plus silencieusement sur claude quand le serveur sait faire mieux,
    # et un `engine` contredisant l'index est refusé (jamais de reprise tentée
    # avec le mauvais binaire, qui échouerait en « transcript introuvable »).
    engine_in = str(payload.get("engine") or "").strip() or None
    known = _engine_of_session(session_id) if session_id else None
    if engine_in and known and engine_in != known:
        raise ApiError(409, f"moteur incohérent pour {session_id} : "
                            f"reçu {engine_in!r}, mémorisé {known!r}")
    engine = engine_in or known or "claude"

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
    # RM2539 : le moteur déclare (ou non) son contrat de reprise. Un moteur sans
    # contrat n'est pas un bug du serveur : c'est un refus à formuler, avec la
    # sortie de secours (spawn neuf) plutôt qu'un 501 sec.
    support = _resume_support(engine)
    if not support:
        capables = ", ".join(sorted(n for n in ENGINES if _resume_support(n)))
        raise ApiError(501, f"le moteur {engine} ne sait pas reprendre une conversation "
                            f"(moteurs capables : {capables}) — lancer une session neuve.")
    if not _valid_session_id(session_id, engine):
        raise ApiError(400, f"session_id {session_id!r} n'a pas la forme attendue "
                            f"par le moteur {engine}")

    # Conversation présente ? La SOURCE dépend du moteur : transcript JSONL
    # (claude) ou base du moteur (opencode). `conv` porte le cwd de reprise.
    jf = None
    if support["store"] == "claude_jsonl":
        jf = next((p for root in CLAUDE_STORES for p in root.glob(f"*/{session_id}.jsonl")), None)
        conv = {"cwd": _resume_cwd(jf, engine, session_id)} if jf else None
    else:
        meta = _ENGINE_META[support["store"]](session_id)
        conv = {"cwd": meta.get("cwd")} if meta else None

    if not rm_id:
        # Ancrage automatique (RM2144, affiné RM2536 : le projet du cwd prime
        # sur la récence) ; à défaut de jonction, SLUG dérivé du titre de la
        # session — plus d'obligation de fournir un ticket à la reprise.
        smeta = _read_json_file(SESS_DIR / engine / f"{session_id}.json") or {}
        rm_id = _anchor_rm_id(session_id, smeta.get("cwd") or (conv or {}).get("cwd"))
        if not rm_id:
            rm_id = _auto_slug(_transcript_info(session_id).get("title"), session_id)

    if _has_session(rm_id):
        raise ApiError(409, f"session déjà active : {_session_name(rm_id)}")

    # Garde-fous : conversation présente ? cwd toujours valide ? RM2536 : `spawn`
    # autorise le repli en session NEUVE (cwd/model repris de l'index des clés,
    # jamais du client) — l'appelant n'a donc plus à porter ces valeurs.
    if conv is None:
        return _spawn_fallback(rm_id, engine, payload, auth_ctx,
                               f"conversation {session_id} introuvable côté {engine} "
                               "(purgée ou store non monté)")
    try:
        cwd = _resolve_cwd(conv.get("cwd"))
    except (ValueError, TypeError) as e:
        return _spawn_fallback(rm_id, engine, payload, auth_ctx,
                               f"cwd de la session invalide ({e})")

    cmd = f"{support['cmd']} {support['resume_flag']} {shlex.quote(session_id)}"
    width = int(payload.get("width", DEFAULT_WIDTH))
    height = int(payload.get("height", DEFAULT_HEIGHT))
    _start_session_tmux(rm_id, cmd, cwd, width, height, [])
    if _is_ticket_sid(rm_id):
        _record_run(rm_id, engine, session_id, str(cwd))
    _record_key(rm_id, engine, session_id, str(cwd))
    joined = _auto_join_current_set(rm_id, auth_ctx)   # RM2445 : rejoint le jeu courant

    prompt = payload.get("prompt")
    if prompt:
        _wait_engine_ready(rm_id, engine)
        op_send({"rm_id": rm_id, "msg": prompt, "enter": False})
        time.sleep(0.3)
        _tmux("send-keys", "-t", _session_name(rm_id), "Enter")

    return {"rm_id": rm_id, "tmux": _session_name(rm_id), "engine": engine,
            "session_id": session_id, "cwd": str(cwd), "resumed": True,
            "set": joined}          # RM2450 : dit si la session a rejoint le jeu


def _session_live(session_id: str, engine: str = "claude") -> bool:
    """Vrai si un tmux karl-* ancré à cette session tourne, ou si un process
    `<engine> --resume <session_id>` vit encore. Garde de op_move_session : ne
    jamais déplacer une session vivante (elle ré-estampille sa queue / peut
    recréer le transcript — RM2418)."""
    for r in _runs_by_session().get(session_id, []):
        if _has_session(r["rm_id"]):
            return True
    try:
        out = subprocess.run(["pgrep", "-af", engine],
                             capture_output=True, text=True, timeout=5).stdout
        # RM2539 : `--resume` (claude) ou `--session` (opencode) selon le moteur
        flag = (_resume_support(engine) or {}).get("resume_flag", "--resume")
        if any(session_id in ln and flag in ln for ln in out.splitlines()):
            return True
    except (OSError, subprocess.SubprocessError):
        pass
    return False


def op_move_session(payload: dict) -> dict:
    """Déplace une session claude d'un projet vers un autre (RM2418). Corrige les
    TROIS ancrages qui, ensemble, lient une session à un projet :
      1. le transcript  ~/.claude/projects/<slug>/<sid>.jsonl        → déplacé
      2. ses `cwd` internes (pilotent le regroupement d'affichage)    → réécrits
      3. le store per-session SESS_DIR/<engine>/<sid>.json (`cwd`)    → réécrit
    (+ les jonctions ticket éventuelles). N'en corriger qu'un ou deux ne suffit
    pas : la session repart au mauvais projet ou disparaît de la liste.

    ⚠ karl-agent tourne DANS le conteneur dev : ~/.claude/projects est partagé
    hôte↔conteneur, mais SESS_DIR (~/.local/state) NON — l'endpoint agit sur le
    store local au conteneur, ce qui est le bon (celui que lit op_resume)."""
    engine = payload.get("engine", "claude")
    session_id = str(payload.get("session_id") or "").strip()
    if not _SID_RE.match(session_id):
        raise ApiError(400, "session_id invalide")
    if engine != "claude":
        raise ApiError(501, "move-session : itération 1 = claude uniquement")
    # Destination : cwd explicite, ou (client, projet) → workspace résolu via le
    # `.mmi-pm` (voie canonique, plus sûre qu'un chemin fourni par le client).
    to_cwd = str(payload.get("to_cwd") or "").strip() or None
    client_in, project_in = payload.get("client"), payload.get("project")
    if not to_cwd and client_in and project_in:
        pdir = PROJECTS_BASE / client_in / "projects" / project_in
        ws = _resolve_workspace(pdir) if pdir.is_dir() else None
        if not ws:
            raise ApiError(404, f"pas de workspace de code pour {client_in}/{project_in}")
        to_cwd = str(ws)
    target = _resolve_cwd(to_cwd)

    if _session_live(session_id, engine) and not payload.get("force"):
        raise ApiError(409, "session vivante (tmux ou claude --resume) — "
                            "ferme-la avant de la déplacer")

    jf = next((p for root in CLAUDE_STORES
               for p in root.glob(f"*/{session_id}.jsonl")), None)
    if jf is None:
        raise ApiError(404, f"transcript introuvable pour {session_id}")

    old_slug = jf.parent.name
    new_slug = _slug_of(str(target))
    new_jf = jf.parent.parent / new_slug / f"{session_id}.jsonl"

    # 1+2. déplacer le transcript et réécrire ses cwd internes
    text = jf.read_text(encoding="utf-8", errors="replace")
    cwds = re.findall(r'"cwd"\s*:\s*"([^"]*)"', text)  # transcripts claude = compacts
    old_cwd = max(set(cwds), key=cwds.count) if cwds else None
    if old_cwd:
        text = re.sub(r'("cwd"\s*:\s*")' + re.escape(old_cwd) + r'(")',
                      lambda m: m.group(1) + str(target) + m.group(2), text)
    new_jf.parent.mkdir(parents=True, exist_ok=True)
    new_jf.write_text(text, encoding="utf-8")
    if new_jf != jf:
        jf.unlink()
    # purge d'éventuels doublons du sid restés dans d'autres dossiers projet
    for root in CLAUDE_STORES:
        for dup in root.glob(f"*/{session_id}.jsonl"):
            if dup != new_jf:
                dup.unlink()
    _tail_cache.pop(str(jf), None)
    _tail_cache.pop(str(new_jf), None)

    # 3. store per-session (le cwd que lit op_resume)
    sf = SESS_DIR / engine / f"{session_id}.json"
    smeta = _read_json_file(sf) or {"engine": engine, "session_id": session_id}
    smeta["cwd"] = str(target)
    _write_json_atomic(sf, smeta)
    # jonctions ticket éventuelles (cwd conservé pour l'affichage /sessions)
    for run in _runs_by_session().get(session_id, []):
        rf = Path(run.pop("_file"))
        run.pop("client", None), run.pop("project", None)
        run["cwd"] = str(target)
        _write_json_atomic(rf, run)

    client, project = _pm_project_of_cwd(str(target))
    return {"session_id": session_id, "engine": engine,
            "old_slug": old_slug, "new_slug": new_slug, "cwd": str(target),
            "client": client, "project": project, "moved": True}


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


# ── Outline de conversation + navigation dans l'historique (RM2330) ─────────
# Le terminal est un tmux (servi par ttyd) : la « position de lecture » est donc
# pilotée par le copy-mode tmux — history-top puis scroll-down N, déterministe
# et visible par tous les clients attachés. L'outline est parsé du scrollback :
# dans le TUI claude, un message utilisateur commence par « > », une réponse de
# l'assistant par « ⏺ » (les lignes de suite sont indentées, sans marqueur).


def _conversation_outline(text: str, max_items: int = 800) -> list:
    """RM2330 : parse un scrollback en items [{line, kind, text}] — kind
    user|assistant. Les lignes « > » consécutives forment UN item (message
    multi-ligne). Pure (testable sans tmux) ; texte tronqué à 120 caractères."""
    items = []
    prev_user = False
    for i, ln in enumerate(text.splitlines()):
        s = ln.strip()
        if s.startswith("> "):
            body = s[2:].strip()
            if prev_user and items and body:            # suite d'un message multi-ligne
                cur = items[-1]
                cur["text"] = (cur["text"] + " " + body)[:120]
            elif body:
                items.append({"line": i, "kind": "user", "text": body[:120]})
            prev_user = True
            continue
        prev_user = False
        if s.startswith("⏺"):
            body = s.lstrip("⏺").strip()
            if body:
                items.append({"line": i, "kind": "assistant", "text": body[:120]})
    if len(items) > max_items:                          # garde le plus récent
        items = items[-max_items:]
    return items


# RM2549 : outils par lesquels l'agent interpelle EXPLICITEMENT l'utilisateur.
# Liste fermée, volontairement : une question est un fait déclaré par l'agent,
# jamais une devinette sur de la prose (« on dirait qu'il demande un avis »).
_QUESTION_TOOLS = ("AskUserQuestion", "ExitPlanMode")
# Un tool_result existe, mais il ne porte AUCUN choix : la question est restée
# sans réponse (interruption, refus). À distinguer d'une question répondue.
_NO_ANSWER_MARKERS = ("[Request interrupted by user",
                      "The user doesn't want to proceed",
                      "The user doesn't want to take this action")
# « "Quelle option ?"="Barre permanente" selected preview:… » → le choix retenu.
_ANSWER_PAIR_RE = re.compile(r'"[^"]*"="([^"]*)"')


def _content_text(content) -> str:
    """Texte d'un `content` (message ou tool_result) : chaîne, ou blocs texte."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _question_parts(name: str, inp) -> tuple:
    """RM2549 : (aperçu, détail) d'une question posée à l'utilisateur."""
    inp = inp if isinstance(inp, dict) else {}
    if name == "ExitPlanMode":
        return "Plan proposé — validation demandée", str(inp.get("plan") or "")
    questions = [q for q in (inp.get("questions") or []) if isinstance(q, dict)]
    apercu = " / ".join(str(q.get("question") or "").strip() for q in questions)
    detail = []
    for q in questions:
        detail.append(str(q.get("question") or "").strip())
        for opt in (q.get("options") or []):
            if isinstance(opt, dict):
                detail.append("  - " + str(opt.get("label") or "").strip())
    return apercu, "\n".join(detail)


def _answer_parts(text: str):
    """RM2549 : (aperçu de la réponse retenue, détail), ou None si la question
    est restée sans réponse — l'utilisateur a interrompu ou refusé."""
    if not text or any(m in text for m in _NO_ANSWER_MARKERS):
        return None
    choix = [c.strip() for c in _ANSWER_PAIR_RE.findall(text) if c.strip()]
    apercu = " / ".join(choix) if choix else " ".join(text.split())
    return apercu, text


def _transcript_outline(lines, max_items: int = 400) -> list:
    """RM2330 : items de conversation depuis un transcript claude (JSONL).
    Source de référence pour les sessions claude : leur TUI tourne en écran
    alterné (history tmux VIDE — vérifié : alternate_on=1, history_size=0),
    le scrollback ne contient donc PAS la conversation.

    Un item = un message user|assistant, ou (RM2549) une `question` posée à
    l'utilisateur / la `answer` retenue — jusqu'ici jetées avec le reste des
    tool_use/tool_result alors que c'est là que se joue « où en est-on ».
    Une question sans tool_result, ou dont le résultat ne porte aucun choix,
    reste `resolved: False`.
    {n, kind, text (aperçu), full (lecture), resolved, answer} — pure."""
    items = []
    pending = {}                    # tool_use_id → item question sans réponse
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = obj.get("type")
        if kind not in ("user", "assistant") or obj.get("isMeta"):
            continue
        content = (obj.get("message") or {}).get("content")
        if not isinstance(content, (str, list)):
            continue
        # enveloppes techniques (<command-name>, <local-command-stdout>,
        # <system-reminder>…) : pas des messages de conversation
        text = _content_text(content).strip()
        if text and not text.startswith("<"):
            items.append({"n": len(items), "kind": kind, "resolved": None, "answer": None,
                          "text": " ".join(text.split())[:120], "full": text[:4000]})
        # le texte d'un message précède toujours ses appels d'outil : l'ordre
        # chronologique de l'outline est conservé en traitant les blocs après.
        for b in (content if isinstance(content, list) else []):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") in _QUESTION_TOOLS:
                apercu, detail = _question_parts(b.get("name"), b.get("input"))
                item = {"n": len(items), "kind": "question", "resolved": False,
                        "answer": None, "text": " ".join(apercu.split())[:120] or "(question)",
                        "full": detail[:4000]}
                pending[b.get("id")] = item
                items.append(item)
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                question = pending.pop(b.get("tool_use_id"))
                reponse = _answer_parts(_content_text(b.get("content")))
                if reponse is None:
                    continue                # question laissée sans réponse
                apercu, detail = reponse
                question["resolved"] = True
                question["answer"] = apercu[:120]
                items.append({"n": len(items), "kind": "answer", "resolved": True,
                              "answer": None, "text": apercu[:120] or "(réponse)",
                              "full": detail[:4000]})
    if len(items) > max_items:
        items = items[-max_items:]
    return items


def _transcript_usage(lines) -> dict:
    """RM2373 : consommation tokens d'une session claude depuis son transcript
    (JSONL), différenciée ENTRÉE / SORTIE. Somme les `message.usage` des tours
    assistant — mêmes champs que pm-task-tick (input/output/cache_read/
    cache_creation). `total` = entrée + sortie (RM2519 : le cache est
    complémentaire, hors total). Le dernier tour donne l'occupation de contexte
    courante (input non-caché + cache lu + cache écrit). Pure (testable sans fichier)."""
    agg = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    turns = 0
    context_last = 0
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict) or obj.get("type") != "assistant":
            continue
        usage = (obj.get("message") or {}).get("usage")
        if not isinstance(usage, dict):
            continue
        i = usage.get("input_tokens", 0) or 0
        o = usage.get("output_tokens", 0) or 0
        cr = usage.get("cache_read_input_tokens", 0) or 0
        cc = usage.get("cache_creation_input_tokens", 0) or 0
        agg["input"] += i
        agg["output"] += o
        agg["cache_read"] += cr
        agg["cache_creation"] += cc
        ctx = i + cr + cc                   # occupation de contexte de ce tour
        if ctx:                             # ignore les tours à contexte nul (sortie seule / synthétiques)
            context_last = ctx              # → dernier tour significatif = contexte courant
        turns += 1
    # RM2519 : total = entrée + sortie. Le cache (lu/écrit) est une info
    # complémentaire, HORS total : le sommer donnerait un nombre écrasé par la
    # relecture de contexte (souvent >90 %) et mélangerait des catégories aux
    # taux distincts. `context_last` reste, lui, entrée+cache (occupation réelle).
    agg["total"] = agg["input"] + agg["output"]
    agg["turns"] = turns
    agg["context_last"] = context_last
    return agg


def op_usage(rm_id: str) -> dict:
    """RM2373 : consommation tokens EN DIRECT d'une session (entrée/sortie/cache),
    lue du transcript claude (JSONL) — même résolution de session_id que /outline.
    404 si session absente ; usage à zéro si moteur non-claude ou transcript
    encore introuvable (session tout juste lancée)."""
    if not _valid_sid(rm_id):
        raise ApiError(400, "rm_id invalide")
    if not _has_session(rm_id):
        raise ApiError(404, f"session absente : {_session_name(rm_id)}")
    k = _key_info(rm_id) or {}
    session_id = k.get("session_id")
    empty = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0,
             "total": 0, "turns": 0, "context_last": 0}
    if k.get("engine") == "claude" and session_id:
        jf = next((p for root in CLAUDE_STORES
                   for p in root.glob(f"*/{session_id}.jsonl")), None)
        if jf:
            try:
                with jf.open(encoding="utf-8", errors="replace") as fh:
                    return {"rm_id": rm_id, "source": "transcript",
                            "engine": "claude", "usage": _transcript_usage(fh)}
            except OSError as e:
                raise ApiError(500, f"transcript illisible : {e}")
    return {"rm_id": rm_id, "source": "none",
            "engine": k.get("engine"), "usage": empty}


def op_outline(rm_id: str) -> dict:
    """RM2330 : outline de la conversation d'une session. Source primaire :
    transcript claude (JSONL) résolu par le session_id de la clé tmux ; repli :
    parse du scrollback tmux (moteurs shell/autres, où l'historique existe —
    items alors positionnés par `line`, navigables via /scroll)."""
    if not _valid_sid(rm_id):
        raise ApiError(400, "rm_id invalide")
    if not _has_session(rm_id):
        raise ApiError(404, f"session absente : {_session_name(rm_id)}")
    k = _key_info(rm_id) or {}
    session_id = k.get("session_id")
    if k.get("engine") == "claude" and session_id:
        jf = next((p for root in CLAUDE_STORES
                   for p in root.glob(f"*/{session_id}.jsonl")), None)
        if jf:
            try:
                with jf.open(encoding="utf-8", errors="replace") as fh:
                    items = _transcript_outline(fh)
                return {"rm_id": rm_id, "source": "transcript", "items": items}
            except OSError as e:
                raise ApiError(500, f"transcript illisible : {e}")
    rc, out, err = _tmux("capture-pane", "-p", "-t", _session_name(rm_id),
                         "-S", "-", timeout=30)
    if rc != 0:
        raise ApiError(500, f"capture-pane a échoué : {err.strip()}")
    return {"rm_id": rm_id, "source": "tmux",
            "total_lines": len(out.splitlines()),
            "items": _conversation_outline(out)}


def op_scroll(payload: dict) -> dict:
    """RM2330 : positionne le pane sur une ligne du scrollback (copy-mode :
    history-top + scroll-down N) ou revient au direct (bottom → cancel)."""
    rm_id = _require_rm_id(payload)
    if not _has_session(rm_id):
        raise ApiError(404, f"session absente : {_session_name(rm_id)}")
    name = _session_name(rm_id)
    if payload.get("bottom"):
        _tmux("send-keys", "-t", name, "-X", "cancel")   # hors copy-mode : sans effet
        return {"rm_id": rm_id, "position": "live"}
    try:
        line = int(payload.get("line"))
    except (TypeError, ValueError):
        raise ApiError(400, "line requis (entier) ou bottom: true")
    if line < 0:
        raise ApiError(400, "line ≥ 0 requis")
    rc, _, err = _tmux("copy-mode", "-t", name)
    if rc != 0:
        raise ApiError(500, f"copy-mode a échoué : {err.strip()}")
    _tmux("send-keys", "-t", name, "-X", "history-top")
    if line > 0:
        _tmux("send-keys", "-t", name, "-N", str(line), "-X", "scroll-down")
    return {"rm_id": rm_id, "position": line}


# RM2329 : caractères de décor TUI (bordures de boîtes claude) à ôter d'une
# question avant lecture vocale — une ligne qui n'est QUE du décor est jetée.
_TUI_DECOR = set("─│╭╮╰╯┌┐└┘├┤═║╔╗╚╝• ")


def _extract_question(tail: str) -> str | None:
    """RM2329 : texte lisible de la question posée dans un pane (pour la synthèse
    vocale). Prend le bloc depuis la première ligne porteuse d'un marqueur
    d'attention, nettoie bordures/curseur TUI, aplati en une phrase. None si
    aucune question visible. Pure (testable sans tmux)."""
    lines = tail.rstrip().splitlines()[-15:]
    start = next((i for i, ln in enumerate(lines)
                  if any(m in ln for m in _ATTENTION_MARKERS)), None)
    if start is None:
        return None
    out = []
    for ln in lines[start:start + 10]:
        ln = ln.replace("❯", " ").strip()
        ln = ln.strip("│║").strip()
        if not ln or set(ln) <= _TUI_DECOR:
            continue
        out.append(ln)
    text = " ".join(out).strip()
    return text[:500] or None


def op_question(rm_id: str) -> dict:
    """RM2329 : question actuellement posée par une session (texte nettoyé,
    prêt pour la synthèse vocale) — null si la session ne demande rien."""
    if not _valid_sid(rm_id):
        raise ApiError(400, "rm_id invalide")
    if not _has_session(rm_id):
        raise ApiError(404, f"session absente : {_session_name(rm_id)}")
    rc, out, err = _tmux("capture-pane", "-p", "-t", _session_name(rm_id))
    if rc != 0:
        raise ApiError(500, f"capture-pane a échoué : {err.strip()}")
    tail = "\n".join(out.rstrip().splitlines()[-15:])
    return {"rm_id": rm_id, "question": _extract_question(tail)}


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


def _sessions_view(qs: dict, auth_ctx: dict | None = None) -> list:
    """Sessions tmux vivantes, enrichies (moteur, session_id, client/projet via
    la jonction la plus récente, état heuristique RM2140) + filtres
    engine/client/project (RM1939).

    RM2427 : s'y ajoutent les « fantômes » — sessions enregistrées d'un jeu
    `autostart` qui ne tournent pas (aucun processus). `ghosts=0` les exclut."""
    sessions = _list_sessions()
    if not sessions:
        return _keep_sessions(_ghosts_for(qs, auth_ctx), qs)
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
            s["disposition"] = k.get("disposition")   # RM2515 : marque manuelle (idle uniquement, côté UI)
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

    # RM2445 : appartenance aux jeux. Une session VIVANTE n'est jamais masquée,
    # même quand elle relève d'un autre jeu que le courant — un agent qui attend
    # une réponse (⚠) doit rester visible ; l'UI la range à part et la badge de
    # son jeu (`sets`/`set_labels`), au lieu de la faire disparaître.
    _store = _session_set_load()
    _groups = ((_store.get("users") or {}).get(_session_set_user(auth_ctx), {})
               .get("groups") or {})
    _cur = _current_set(_session_set_user(auth_ctx), _store)
    # RM2446 : en vue `live` ou `all`, tout ce qui est affiché fait partie de la
    # vue — `in_current` ne doit pas y reléguer des sessions dans « hors du jeu ».
    _view = _current_view(_session_set_user(auth_ctx), _store)
    # RM2537 : appartenance lue par `_set_entries` — le point de passage unique
    # qui sait CALCULER le contenu d'un jeu dérivé (RM2452). Lire `entries` en
    # dur rendait vide tout jeu à règle : ses propres sessions se voyaient
    # `in_current: False` et le cockpit les reléguait dans « hors du jeu
    # courant », sans en-tête client/projet ni badge de jeu.
    _member: dict = {}
    for _g, _rec in _groups.items():
        for _e in _set_entries(_rec):
            _member.setdefault(_e.get("sid"), []).append(_g)
    for s in sessions:
        names = _member.get(s["rm_id"], [])
        s["sets"] = names
        s["set_labels"] = [(_groups[n].get("label") or n) for n in names if n in _groups]
        # RM2452 : dans une vue par CLIENT, une vivante n'appartient à la vue que
        # si elle est de ce client — sinon elle s'y rangeait sans badge, et en
        # tête par ordre alphabétique (des sessions calicote ouvraient la vue
        # pisceen). Les vues `live`/`all` embrassent tout, elles.
        _mv = _VIEW_CLIENT_RE.match(_view)
        if _mv:
            s["in_current"] = s.get("client") == _mv.group(1)
        else:
            s["in_current"] = True if _view != "set" else (_cur in names)
    return _keep_sessions(sessions + _ghosts_for(qs, auth_ctx), qs)


def _ghosts_for(qs: dict, auth_ctx: dict | None) -> list:
    """RM2427 — fantômes à joindre à la vue, sauf opt-out explicite `ghosts=0`."""
    return [] if str(qs.get("ghosts", "")) == "0" else _ghost_sessions(auth_ctx)


def _keep_sessions(sessions: list, qs: dict) -> list:
    """Filtres engine/client/project (RM1939) — vivantes comme fantômes."""
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
# RM2452 : surchargeable. Une instance lancée sur un WORKTREE de code n'a pas
# d'arbre `projects/` (les données PM vivent dans l'autre dépôt) : sans override,
# client/projet ne se résolvent pas — le panneau retombe sur « divers » et une
# règle de jeu dérivé ne désigne plus rien.
PROJECTS_BASE = Path(os.environ.get("KARL_AGENT_PROJECTS_BASE")
                     or (REPO_ROOT / "projects" / "clients"))
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


# ── Vue projet (RM2353) ──────────────────────────────────────────────────────
_PART_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


def _project_tickets_summary(tasks: list) -> dict:
    """RM2353 : agrège une liste de tickets [{rm_id, title, status, type, mtime}]
    → derniers traités (fermés, plus récents d'abord), ouverts récents, compte
    par statut. Pure (testable sans filesystem)."""
    closed = sorted([t for t in tasks if t.get("status") == "ferme"],
                    key=lambda t: -t.get("mtime", 0))
    open_ = sorted([t for t in tasks if t.get("status") != "ferme"],
                   key=lambda t: -t.get("mtime", 0))
    by_status = {}
    for t in open_:
        st = t.get("status") or "?"
        by_status[st] = by_status.get(st, 0) + 1
    return {"closed_recent": closed[:12], "open_recent": open_[:15],
            "open_by_status": by_status, "total": len(tasks)}


def _client_conf(client: str) -> dict:
    """RM2531 — conf structurée du client pour préremplir le formulaire d'édition :
    name + redmine.default_project_id, lus à plat depuis .mmi-pm-client/meta.yml
    (parent du symlink `client`). Vide si absent."""
    cdir = PROJECTS_BASE / client / "client"
    try:
        meta = cdir.resolve().parent / "meta.yml"
    except OSError:
        return {}
    if not meta.is_file():
        return {}
    name = rid = None
    block = None
    for line in meta.read_text(encoding="utf-8", errors="replace").splitlines():
        if line and not line[0].isspace():
            block = line.split(":", 1)[0].strip() if ":" in line else None
            if line.startswith("name:") and not name:
                name = _scalar(line)
            continue
        s = line.strip()
        if block == "redmine" and s.startswith("default_project_id:") and not rid:
            rid = s.split(":", 1)[1].strip().strip("'\"")
    if rid in ("null", "~", ""):
        rid = None
    return {"client_name": name, "client_redmine_project_id": rid}


def op_project(client: str, project: str) -> dict:
    """RM2353 : fiche projet pour le panneau principal du cockpit — conf
    pertinente (overview : redmine.project_id, repo gitlab), docs, environnements,
    liens Redmine (projet + liste des tickets), derniers tickets traités et
    ouverts par statut (MD locaux, récence = mtime des fichiers)."""
    if not (_PART_RE.match(client or "") and _PART_RE.match(project or "")):
        raise ApiError(400, "client/projet invalide")
    pdir = PROJECTS_BASE / client / "projects" / project
    if not pdir.is_dir():
        raise ApiError(404, f"projet inconnu en local : {client}/{project}")
    # conf : name + redmine.project_id + gitlab.repo — depuis meta.yml (layout
    # co-localisé) ET le frontmatter de project/overview.md (l'un ou l'autre
    # peut manquer selon le projet ; parse à plat, blocs à 1 niveau).
    name = slug = repo = default_branch = None

    def _flat(text):
        nonlocal name, slug, repo, default_branch
        block = None
        for line in text.splitlines():
            if line and not line[0].isspace():
                block = line.split(":", 1)[0].strip() if ":" in line else None
                if line.startswith("name:") and not name:
                    name = _scalar(line)
                continue
            s = line.strip()
            if block == "redmine" and s.startswith("project_id:") and not slug:
                slug = s.split(":", 1)[1].strip().strip("'\"")
            elif block == "gitlab" and s.startswith("repo:") and not repo:
                repo = s.split(":", 1)[1].strip().strip("'\"")
            elif block == "gitlab" and s.startswith("default_branch:") and not default_branch:
                default_branch = s.split(":", 1)[1].strip().strip("'\"")

    meta_yml = pdir / "meta.yml"
    if meta_yml.is_file():
        _flat(meta_yml.read_text(encoding="utf-8", errors="replace"))
    ov = pdir / "project" / "overview.md"
    if ov.is_file():
        text = ov.read_text(encoding="utf-8", errors="replace")
        if text.startswith("---"):
            end = text.find("\n---", 3)
            _flat(text[3:end] if end != -1 else text)
    tasks = []
    tdir = pdir / "tasks"
    if tdir.is_dir():
        for tf in tdir.glob("RM*_*.md"):
            if tf.name.endswith(".log.md"):
                continue
            m = re.match(r"RM(\d+)_", tf.name)
            if not m:
                continue
            meta = _read_task_meta(tf)
            try:
                mtime = int(tf.stat().st_mtime)
            except OSError:
                mtime = 0
            tasks.append({"rm_id": m.group(1), "title": meta["title"],
                          "status": meta["status"], "type": meta["type"],
                          "mtime": mtime})
    redmine = os.environ.get("REDMINE_URL", "").rstrip("/")
    return {
        "client": client, "project": project, "name": name,
        "redmine_project_id": slug,          # RM2531 : préremplissage du formulaire de conf
        "redmine_project_url": f"{redmine}/projects/{slug}" if redmine and slug else "",
        "redmine_issues_url": f"{redmine}/projects/{slug}/issues" if redmine and slug else "",
        "gitlab_repo": repo, "default_branch": default_branch,
        "docs": _project_docs(pdir),
        "environments": _read_project_envs(pdir),
        **_client_conf(client),
        **_project_tickets_summary(tasks),
    }


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
            "--title", title, "--type", ttype, "--priority", prio, "--project", project,
            "--porcelain"]
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
    # --porcelain (RM2362) : l'id seul sur stdout ; repli sur les anciens formats
    # de sortie pour un core pas encore migré.
    m = re.match(r"\s*(\d+)\s*$", (p.stdout or "").strip().splitlines()[0] if (p.stdout or "").strip() else "") \
        or re.search(r"RM(\d+) créé", blob) or re.search(r"#(\d+) créé", blob) \
        or re.search(r"✓ add RM(\d+)", blob)
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
    {"name": "cockpit-test-env", "label": "Instance cockpit de test (RM2356)",
     "category": "ticket", "script": "pm-cockpit-test-env.py",
     "mutate": True, "args": [
         {"name": "action", "type": "enum", "required": True, "positional": True,
          "choices": ["create", "teardown"]},
         {"name": "rm_id", "label": "Ticket", "type": "rm_id", "required": True, "positional": True},
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
    # Conf structurée projet/client (RM2531) — édition CIBLÉE de meta.yml via le
    # single-writer pm-project-config.py (les champs vides ne touchent rien).
    {"name": "project-config", "label": "Modifier la conf d'un projet", "category": "projet",
     "script": "pm-project-config.py", "mutate": True, "confirm": True, "args": [
         {"name": "client", "label": "Client", "type": "text", "required": True,
          "flag": "--client", "max_len": 48},
         {"name": "project", "label": "Projet", "type": "text", "required": True,
          "flag": "--project", "max_len": 48},
         {"name": "name", "label": "Nom affiché", "type": "text", "flag": "--name", "max_len": 96},
         {"name": "redmine_project_id", "label": "Projet Redmine (id/slug)", "type": "text",
          "flag": "--redmine-project-id", "max_len": 64},
         {"name": "gitlab_repo", "label": "Repo GitLab (groupe/nom)", "type": "text",
          "flag": "--gitlab-repo", "max_len": 128},
         {"name": "default_branch", "label": "Branche par défaut", "type": "text",
          "flag": "--default-branch", "max_len": 64},
     ]},
    {"name": "client-config", "label": "Modifier la conf d'un client", "category": "projet",
     "script": "pm-project-config.py", "mutate": True, "confirm": True, "args": [
         {"name": "client", "label": "Client", "type": "text", "required": True,
          "flag": "--client", "max_len": 48},
         {"name": "name", "label": "Nom affiché", "type": "text", "flag": "--name", "max_len": 96},
         {"name": "redmine_project_id", "label": "Projet Redmine parent (id/slug)", "type": "text",
          "flag": "--redmine-project-id", "max_len": 64},
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
        # RM2356 : ticket cockpit-testable = son worktree embarque karl-agent
        e["cockpit_testable"] = bool(
            ws and env and (ws / "envs" / env / "scripts" / "karl-agent.py").is_file())
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
    # RM2386 — rubrique « Design front » : apparence du cockpit web. Le type
    # `enum` est générique (options[] + défaut), pas ad hoc au thème : les
    # prochains réglages de mise en page s'ajoutent ici sans toucher au rendu.
    {"key": "conf:ui.theme", "label": "Thème",
     "group": "Design front", "type": "enum", "path": ["ui", "theme"],
     "options": ["dark", "light", "auto"], "default": "auto"},
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
        if e["type"] == "enum":
            # valeur hors options (conf éditée à la main) → on retombe sur le défaut
            val = cur if cur in e["options"] else e.get("default", e["options"][0])
        else:
            val = bool(cur)
        out.append({**e, "value": val})
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


def _ui_theme() -> str:
    """Défaut d'apparence de l'instance (RM2386), lu depuis la whitelist."""
    spec = next((e for e in _pm_settings() if e["key"] == "conf:ui.theme"), None)
    return spec["value"] if spec else "auto"


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
    elif spec["type"] == "enum":
        val = str(raw)
        if val not in spec["options"]:
            raise ApiError(400, f"{key} : valeur hors options {spec['options']}")
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


def _mr_deliver_context(rm_id: str):
    """Résout (bare_code, branche_source, intégration) d'un ticket pour livrer sa
    MR SANS dépendre d'un worktree (RM2355) : projet de code depuis le bare
    `repos/<name>.git` du workspace, branche depuis le frontmatter `git.branch`,
    cible depuis `integration_branch` du manifeste (défaut dev). Pur API : la
    branche est déjà sur origin (poussée pendant le travail), aucun checkout requis."""
    if not rm_id.isdigit():
        raise ApiError(400, "rm_id invalide")
    tf = _find_task_file(rm_id)
    if not tf:
        raise ApiError(404, f"RM{rm_id} : ticket inconnu en local")
    ws = _resolve_workspace(tf.parent.parent)
    if not ws:
        raise ApiError(400, f"RM{rm_id} : workspace de code introuvable")
    fm = _parse_frontmatter(tf.read_text(encoding="utf-8"))
    git = fm.get("git") if isinstance(fm.get("git"), dict) else {}
    branch = git.get("branch")
    if not branch:
        raise ApiError(400, f"RM{rm_id} : aucune branche au frontmatter (git.branch) — "
                            "ticket jamais démarré (pm-branch-start) ?")
    try:
        meta = yaml_safe_load((ws / ".mmi-pm" / "meta.yml").read_text(encoding="utf-8")) or {}
    except OSError:
        meta = {}
    repos = meta.get("repos") or []
    if len(repos) != 1:
        raise ApiError(400, f"RM{rm_id} : livraison auto réservée au mono-repo "
                            f"({len(repos)} repo(s) au manifeste)")
    name = repos[0].get("name")
    integration = repos[0].get("integration_branch") or "dev"
    bare = ws / "repos" / f"{name}.git"
    if not bare.is_dir():
        raise ApiError(400, f"RM{rm_id} : bare de code introuvable ({bare})")
    return bare, str(branch), str(integration)


def op_mr_deliver(payload: dict) -> dict:
    """RM2355 : livre la branche d'un ticket — crée la MR <branche>→intégration et
    la merge — pour débloquer un verdict « testé OK » que la merge gate RM2319
    refuse (branche non mergée dans dev). Enchaîne `pm-mr create --merge` en pur
    API (aucun checkout de la branche) ; la transition de statut du verdict reste
    au JS appelant, qui la rejoue une fois la branche mergée (RM2319 la laisse
    alors passer). single-writer : sous-process pm-mr, jamais de shell."""
    if payload.get("confirm") is not True:
        raise ApiError(400, "confirmation requise (confirm: true)")
    rm_id = str(payload.get("rm_id") or "")
    bare, branch, integration = _mr_deliver_context(rm_id)
    script = (REPO_ROOT / "scripts" / "pm-mr.py").resolve()
    argv = [sys.executable, str(script), "create", rm_id,
            "--repo", str(bare), "--source", branch, "--target", integration, "--merge"]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=180,
                           cwd=str(REPO_ROOT))
    except subprocess.TimeoutExpired:
        raise ApiError(500, "mr-deliver : timeout (180 s)")
    try:
        PM_RUNS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with PM_RUNS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "name": "mr-deliver",
                                "args": {"rm_id": rm_id, "branch": branch, "target": integration},
                                "rc": r.returncode}, ensure_ascii=False) + "\n")
    except OSError:
        pass  # le journal ne doit jamais faire échouer le run
    return {"name": "mr-deliver", "rc": r.returncode, "ok": r.returncode == 0,
            "branch": branch, "target": integration,
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


# ── Détection des mises à jour du core (RM2571) ──────────────────────────────
# NON privilégié, par construction. `git fetch` est IMPOSSIBLE ici : le `.git`
# du core est root-owned (verrou 3-couches RM2032) et le fetch veut écrire
# FETCH_HEAD — il échoue en « Permission denied ». En revanche `git ls-remote`
# ne fait que lire la conf et interroger le remote, sans écrire un octet dans
# `.git` : il passe en KARL_USER. C'est ce qui permet de sonder les MAJ sans le
# moindre privilège. Seule l'APPLICATION de la mise à jour est privilégiée.
_CORE_UPD_TTL = 600          # s — le cockpit sonde souvent, ls-remote sort sur le réseau
_core_upd_cache: dict = {}   # dernier état connu, servi tant qu'il est frais


def _core_branch() -> str:
    p = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
                       capture_output=True, text=True, timeout=10)
    return (p.stdout.strip() or "main") if p.returncode == 0 else "main"


def op_core_update_status(qs: dict | None = None) -> dict:
    """État de mise à jour du core : HEAD local vs tête du remote.

    Ne fait JAMAIS échouer la route : un remote injoignable (réseau, auth) rend
    `error` et le dernier état connu, marqué périmé. Un cockpit ne doit pas
    s'allumer en rouge parce que le réseau a hoqueté.
    """
    force = str((qs or {}).get("force", "")).lower() in ("1", "true", "oui")
    now = time.time()
    cached = _core_upd_cache.get("data")
    if cached and not force and (now - _core_upd_cache.get("at", 0)) < _CORE_UPD_TTL:
        return {**cached, "cached": True}

    branch = _core_branch()
    out = {"branch": branch, "local": None, "remote": None,
           "available": False, "error": None, "cached": False, "stale": False}
    try:
        p = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        if p.returncode == 0:
            out["local"] = p.stdout.strip()
        # ls-remote : lecture seule, aucun octet écrit dans .git (cf. en-tête).
        p = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-remote", "origin",
                            f"refs/heads/{branch}"],
                           capture_output=True, text=True, timeout=45)
        if p.returncode != 0:
            out["error"] = (p.stderr or "").strip()[:400] or "ls-remote a échoué"
        else:
            line = (p.stdout or "").strip().split("\n")[0]
            out["remote"] = line.split("\t")[0].strip() if line else None
    except subprocess.TimeoutExpired:
        out["error"] = "remote injoignable (délai dépassé)"
    except Exception as e:  # noqa: BLE001 — la route doit toujours rendre
        out["error"] = f"{type(e).__name__}: {e}"

    out["available"] = bool(out["local"] and out["remote"] and out["local"] != out["remote"])
    out["checked_at"] = (time.strftime("%Y-%m-%dT%H:%M:%S") if out["error"] is None
                         else (cached or {}).get("checked_at"))
    if out["error"] and cached:
        # Échec transitoire : on garde l'état connu, en le marquant périmé.
        return {**cached, "cached": True, "stale": True, "error": out["error"]}
    _core_upd_cache["data"], _core_upd_cache["at"] = out, now
    return out


# ── Serveur HTTP ─────────────────────────────────────────────────────────────
# ── Assets statiques du cockpit (RM2522) ────────────────────────────────────
# Jusqu'ici le serveur ne servait QUE index.html ; le client terminal maison
# (xterm.js vendoré + karl-term.js) a besoin de fichiers séparés. Liste blanche
# d'extensions et confinement strict sous COCKPIT_DIR.
ASSET_TYPES = {
    ".js":  "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}


def _resolve_asset(rel: str):
    """Chemin absolu d'un asset servable du cockpit, ou None. Refuse un type
    hors liste blanche ET toute évasion hors de COCKPIT_DIR (`..`, chemin
    absolu, symlink sortant) — le chemin est résolu AVANT d'être comparé.
    Pure et testable (test_karl_agent_asset.py)."""
    if not rel or os.path.splitext(rel)[1] not in ASSET_TYPES:
        return None
    try:
        root = COCKPIT_DIR.resolve()
        target = (root / rel).resolve()
        target.relative_to(root)
    except (ValueError, OSError):
        return None
    return target


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

    def _send_bytes(self, code: int, ctype: str, body: bytes):
        # RM2532 : réponse binaire (WAV du TTS) — pas de charset.
        self.send_response(code)
        self.send_header("Content-Type", ctype)
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

    def _send_asset(self, rel: str):
        target = _resolve_asset(rel)
        if target is None:
            return self._send_json(404, {"error": "asset non servi"})
        try:
            st = target.stat()
            body = target.read_bytes()
        except OSError:
            return self._send_json(404, {"error": f"asset absent : {rel}"})
        # Revalidation systématique plutôt que cache long : ces fichiers sont
        # ÉDITÉS pendant le développement du cockpit, et un cache d'un jour
        # oblige à des rechargements forcés pour voir ses propres correctifs.
        # L'ETag garde le coût réseau nul quand rien n'a changé (304).
        etag = f'"{int(st.st_mtime)}-{st.st_size}"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ASSET_TYPES[target.suffix])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self) -> bool:
        """Vraie si le client présente le token partagé, un TOKEN D'APPAREIL
        (RM2334) ou des credentials Basic valides (RM2139). Sans aucune auth
        configurée → ouvert (usage local). Pose self.auth_ctx {mode, user,
        admin, device_id} pour les routes qui distinguent les rôles."""
        self.auth_ctx = {"mode": "open", "user": None, "admin": True, "device_id": None}
        presented = self.headers.get("X-Karl-Token") or ""
        if AUTH_TOKEN is not None and presented:
            if hmac.compare_digest(presented, AUTH_TOKEN):
                # secret partagé historique = accès complet (rétrocompat)
                self.auth_ctx = {"mode": "shared-token", "user": None,
                                 "admin": True, "device_id": None}
                return True
        if presented:
            hit = _device_auth(presented)
            if hit:
                did, rec = hit
                self.auth_ctx = {"mode": "device", "user": rec.get("user"),
                                 "admin": bool(rec.get("admin")), "device_id": did}
                return True
        if BASIC_USER is not None and BASIC_PASS is not None:
            auth = self.headers.get("Authorization") or ""
            if auth.startswith("Basic "):
                try:
                    user, _, pwd = base64.b64decode(
                        auth[6:], validate=True).decode("utf-8").partition(":")
                except (ValueError, UnicodeDecodeError):
                    return False
                if (hmac.compare_digest(user, BASIC_USER)
                        and hmac.compare_digest(pwd, BASIC_PASS)):
                    self.auth_ctx = {"mode": "basic", "user": user,
                                     "admin": True, "device_id": None}
                    return True
            return False
        return AUTH_TOKEN is None

    def _require_admin(self):
        if not self.auth_ctx.get("admin"):
            raise ApiError(403, "réservé au superadmin")

    def _send_auth_required(self):
        """401 ; le challenge Basic n'est émis que si le CLIENT a lui-même
        tenté un Basic (retry curl/API). Depuis RM2334 la page cockpit est
        publique avec une carte de login : challenger les fetch 401 ferait
        surgir le prompt Basic natif du navigateur par-dessus la carte."""
        body = json.dumps(
            {"error": "authentification requise (login, Basic ou X-Karl-Token)"},
            ensure_ascii=False).encode("utf-8")
        self.send_response(401)
        if (BASIC_USER is not None and BASIC_PASS is not None
                and (self.headers.get("Authorization") or "").startswith("Basic ")):
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
        # Routes publiques du cockpit (RM1873/RM2334) : la page et sa config se
        # chargent SANS auth — nécessaire pour afficher la carte de login (mdp
        # → token d'appareil) — et ne divulguent rien de sensible (le ttyd_base
        # est déjà déductible côté client). Depuis RM2334, le mode Basic
        # s'aligne sur le mode token : la page est publique, les DONNÉES sont
        # gated (le Basic navigateur reste accepté en fallback API).
        authed = self._check_auth()
        if path in ("/", "/cockpit"):
            try:
                return self._send_html(200, (COCKPIT_DIR / "index.html").read_text(encoding="utf-8"))
            except FileNotFoundError:
                return self._send_json(404, {"error": "cockpit/index.html absent"})
        if path.startswith("/static/"):      # RM2522 : vendor/ + client terminal
            return self._send_asset(path[len("/static/"):])
        if path == "/cockpit-config":
            return self._send_json(200, {
                "ttyd_base": TTYD_URL,
                "auth_required": AUTH_TOKEN is not None or BASIC_USER is not None,
                # la carte de login user/mdp n'a de sens que si des identifiants
                # existent (superadmin .env et/ou comptes serveur)
                "login_enabled": BASIC_USER is not None or bool(_auth_load(USERS_FILE)),
                "monitors": list(_monitor_presets().keys()),
                "layouts": sorted(LAYOUTS),
                # chips d'actions (RM1893 §2) — texte en langage naturel injecté
                # via /send ; rien de sensible (le client peut déjà /send librement).
                "actions": _actions_catalog(),
                "task_types": _task_types(),
                "priorities": PRIORITIES,
                "engines": list(ENGINES),
                # RM2539 (correctif) : moteurs dont les conversations sont à la
                # fois REPRENABLES et DÉCOUVRABLES — le panneau de reprise les
                # proposait en dur (« claude »), et les sessions opencode/vibe
                # restaient invisibles alors que la reprise savait les traiter.
                "resume_engines": resume_engines(),
                # clés du catalogue par moteur (RM1941) — le client ne voit que les
                # clés, le mapping vers les valeurs réelles reste côté serveur.
                "models": {e: sorted(m) for e, m in _model_catalog().items()},
                # RM2386 — défaut d'apparence de l'instance (dark|light|auto).
                # Route publique : une préférence de thème n'est pas sensible, et
                # le front en a besoin AVANT l'authentification (écran de login).
                "ui_theme": _ui_theme(),
            })
        if not authed:
            return self._send_auth_required()
        try:
            if path == "/auth/whoami":
                return self._send_json(200, {k: v for k, v in self.auth_ctx.items()})
            if path == "/auth/devices":
                return self._send_json(200, op_auth_devices_list(self.auth_ctx))
            if path == "/auth/users":
                self._require_admin()
                return self._send_json(200, op_auth_users_list())
            if path == "/health":
                return self._send_json(200, {
                    "status": "ok",
                    "sessions": len(_list_sessions()),
                    "tmux": _tmux("-V")[0] == 0,
                })
            if path == "/sessions":
                qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                return self._send_json(200, {"sessions": _sessions_view(qs, self.auth_ctx)})
            if path == "/voice/caps":
                return self._send_json(200, op_voice_caps())
            if path == "/session-registry":
                return self._send_json(200, _registry_view())
            if path == "/session-set/estimate":  # RM2451 : coût d'un « tout relancer »
                qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                return self._send_json(200, op_session_set_estimate(qs, self.auth_ctx))
            if path == "/session-set/history":   # RM2443 : versions archivées
                qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                return self._send_json(200, op_session_set_history(qs, self.auth_ctx))
            if path == "/session-sets":       # RM2442 : liste des jeux nommés
                qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                return self._send_json(200, op_session_sets_list(qs, self.auth_ctx))
            if path == "/session-set":
                qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                return self._send_json(200, op_session_set_get(qs, self.auth_ctx))
            if path == "/core/update-status":   # RM2571 — non privilégié (ls-remote)
                qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                return self._send_json(200, op_core_update_status(qs))
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
            if path.startswith("/outline/"):
                return self._send_json(200, op_outline(path[len("/outline/"):]))
            if path.startswith("/usage/"):
                return self._send_json(200, op_usage(path[len("/usage/"):]))
            if path.startswith("/project/"):
                parts = path[len("/project/"):].split("/")
                if len(parts) != 2:
                    return self._send_json(400, {"error": "attendu : /project/<client>/<projet>"})
                return self._send_json(200, op_project(parts[0], parts[1]))
            if path.startswith("/question/"):
                return self._send_json(200, op_question(path[len("/question/"):]))
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
        path = urlparse(self.path).path
        # /auth/login est LA porte d'entrée : pas d'auth préalable (throttle
        # progressif par IP dans op_auth_login).
        if path == "/auth/login":
            try:
                return self._send_json(200, op_auth_login(
                    self._read_json(), self.client_address[0]))
            except ApiError as e:
                return self._send_json(e.code, {"error": e.msg})
            except Exception as e:  # noqa: BLE001
                return self._send_json(500, {"error": f"{type(e).__name__}: {e}"})
        if not self._check_auth():
            return self._send_auth_required()
        try:
            payload = self._read_json()
            if path == "/auth/users":
                self._require_admin()
                return self._send_json(201, op_auth_user_create(payload))
            if path == "/session-set":
                return self._send_json(200, op_session_set_save(payload, self.auth_ctx))
            if path == "/session-set/relaunch":
                return self._send_json(200, op_session_set_relaunch(payload, self.auth_ctx))
            if path == "/session-set/autostart":
                return self._send_json(200, op_session_set_autostart(payload, self.auth_ctx))
            if path == "/session-set/restart":
                return self._send_json(200, op_session_set_restart(payload, self.auth_ctx))
            if path == "/session-set/rename":   # RM2442 : libellé humain du jeu
                return self._send_json(200, op_session_set_rename(payload, self.auth_ctx))
            if path == "/session-set/rule":         # RM2452 : modifier la règle
                return self._send_json(200, op_session_set_rule(payload, self.auth_ctx))
            if path == "/session-set/materialize":  # RM2452 : dérivé → manuel
                return self._send_json(200, op_session_set_materialize(payload, self.auth_ctx))
            if path == "/session-set/retention":    # RM2452 : masquer les inactives
                return self._send_json(200, op_session_set_retention(payload, self.auth_ctx))
            if path == "/session-set/move":     # RM2449 : vers un jeu EXISTANT
                return self._send_json(200, op_session_set_move(payload, self.auth_ctx))
            if path == "/session-set/create":   # RM2447 : nouveau jeu (vide par défaut)
                return self._send_json(201, op_session_set_create(payload, self.auth_ctx))
            if path == "/session-set/current":  # RM2445 : bascule de jeu courant
                return self._send_json(200, op_session_set_current(payload, self.auth_ctx))
            if path == "/session-set/restore":  # RM2443 : rétablir un jeu archivé
                return self._send_json(200, op_session_set_restore(payload, self.auth_ctx))
            if path == "/spawn":
                return self._send_json(201, op_spawn(payload, self.auth_ctx))
            if path == "/resume":
                return self._send_json(201, op_resume(payload, self.auth_ctx))
            if path == "/move-session":
                return self._send_json(200, op_move_session(payload))
            if path == "/tickets":
                return self._send_json(201, op_create_ticket(payload))
            if path == "/send":
                return self._send_json(200, op_send(payload))
            if path == "/approve":
                return self._send_json(200, op_approve(payload))
            if path == "/scroll":
                return self._send_json(200, op_scroll(payload))
            if path == "/approve-all":
                return self._send_json(200, op_approve_all(payload))
            if path == "/auto-yes":
                return self._send_json(200, op_auto_yes(payload))
            if path == "/kill":
                return self._send_json(200, op_kill(payload))
            if path == "/tts":
                return self._send_bytes(200, "audio/wav", op_tts_wav(payload))
            if path == "/stt":                        # RM2533 : dictée → sidecar Whisper
                return self._send_json(200, op_stt(payload))
            if path == "/disposition":
                return self._send_json(200, op_disposition(payload, self.auth_ctx))
            if path == "/monitor":
                return self._send_json(201, op_monitor(payload))
            if path == "/unmonitor":
                return self._send_json(200, op_unmonitor(payload))
            if path == "/layout":
                return self._send_json(200, op_layout(payload))
            if path == "/pm/run":
                return self._send_json(200, op_pm_run(payload))
            if path == "/mr/deliver":
                return self._send_json(200, op_mr_deliver(payload))
            if path == "/pm/settings":
                return self._send_json(200, op_pm_settings_set(payload))
            return self._send_json(404, {"error": f"route inconnue : {path}"})
        except ApiError as e:
            return self._send_json(e.code, {"error": e.msg})
        except Exception as e:  # noqa: BLE001
            return self._send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_PUT(self):
        if not self._check_auth():
            return self._send_auth_required()
        path = urlparse(self.path).path
        try:
            if path.startswith("/auth/users/"):
                self._require_admin()
                return self._send_json(200, op_auth_user_update(
                    path[len("/auth/users/"):], self._read_json()))
            return self._send_json(404, {"error": f"route inconnue : {path}"})
        except ApiError as e:
            return self._send_json(e.code, {"error": e.msg})
        except Exception as e:  # noqa: BLE001
            return self._send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_DELETE(self):
        if not self._check_auth():
            return self._send_auth_required()
        path = urlparse(self.path).path
        try:
            if path == "/session-set":
                qs = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
                return self._send_json(200, op_session_set_delete(qs, self.auth_ctx))
            if path.startswith("/auth/devices/"):
                did = path[len("/auth/devices/"):]
                # un utilisateur normal ne révoque QUE ses propres appareils
                if not self.auth_ctx.get("admin"):
                    with _AUTH_LOCK:
                        rec = _auth_load(DEVICES_FILE).get(did)
                    if not rec or rec.get("user") != self.auth_ctx.get("user"):
                        raise ApiError(403, "appareil d'un autre compte")
                n = _revoke_devices(device_ids={did})
                if not n:
                    raise ApiError(404, f"appareil inconnu : {did}")
                return self._send_json(200, {"device_id": did, "revoked": True})
            if path.startswith("/auth/users/"):
                self._require_admin()
                return self._send_json(200, op_auth_user_delete(path[len("/auth/users/"):]))
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

    # RM2427 : reprise des jeux enregistrés — les sessions réglées `auto` (défaut
    # des `[WIP]`) redémarrent vraiment, en arrière-plan ; toutes les autres
    # attendent en tuile grise (servies par GET /sessions, aucun TUI ouvert).
    ghosts = len(_ghost_sessions(None))
    if ghosts:
        sys.stderr.write(f"sessions enregistrées : {ghosts} reprise(s) en idle "
                         f"(clic sur la tuile pour relancer)\n")
    threading.Thread(target=_autostart_thread, name="autostart", daemon=True).start()

    sys.stderr.write(
        f"karl-agent en écoute sur http://{HOST}:{PORT} "
        f"(prefix={SESSION_PREFIX}, engine={DEFAULT_ENGINE}, "
        f"auth={'on' if AUTH_TOKEN else 'off'})\n"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
