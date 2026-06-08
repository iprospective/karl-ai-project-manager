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

──────────────────────────────────────────────────────────────────────────────
API (JSON, localhost:9876)
  GET  /                        → text/html (cockpit web v0, RM1873)
  GET  /cockpit-config          → {ttyd_base, auth_required}  (public)
  GET  /health                  → {status, sessions, tmux}
  GET  /sessions                → [{rm_id, tmux, created, attached}]
  POST /spawn  {rm_id, cwd?, engine?, prompt?, width?, height?}
                                → {rm_id, tmux, created:true}
  POST /send   {rm_id, msg, enter?=true}
                                → {rm_id, sent:true}
  GET  /capture/<rm_id>[?lines=N]
                                → text/plain (snapshot du pane, + historique)
  GET  /stream/<rm_id>          → text/event-stream (SSE, tail du pipe-pane)
  POST /kill   {rm_id}          → {rm_id, killed:true}

Lancement :
    python3 scripts/karl-agent.py            # bind 127.0.0.1:9876
    KARL_AGENT_PORT=9999 python3 scripts/karl-agent.py
"""
import json
import os
import re
import shlex
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
ENGINES = {
    "claude": os.environ.get("KARL_AGENT_SPAWN_CMD", "claude"),
    "shell": "bash -l",
}
DEFAULT_ENGINE = os.environ.get("KARL_AGENT_DEFAULT_ENGINE", "claude")
DEFAULT_WIDTH = int(os.environ.get("KARL_AGENT_WIDTH", "200"))
DEFAULT_HEIGHT = int(os.environ.get("KARL_AGENT_HEIGHT", "50"))

# Répertoire des logs pipe-pane (alimente /stream et /capture étendu).
LOG_DIR = Path(
    os.environ.get("KARL_AGENT_LOG_DIR")
    or (Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")) / "karl-agent")
)

AUTH_TOKEN = os.environ.get("KARL_AGENT_TOKEN") or None  # optionnel

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


def op_spawn(payload: dict) -> dict:
    rm_id = _require_rm_id(payload)
    if _has_session(rm_id):
        raise ApiError(409, f"session déjà active : {_session_name(rm_id)}")

    engine = payload.get("engine", DEFAULT_ENGINE)
    if engine not in ENGINES:
        raise ApiError(400, f"engine inconnu : {engine} (connus : {list(ENGINES)})")
    cmd = ENGINES[engine]

    try:
        cwd = _resolve_cwd(payload.get("cwd"))
    except ValueError as e:
        raise ApiError(400, str(e))

    width = int(payload.get("width", DEFAULT_WIDTH))
    height = int(payload.get("height", DEFAULT_HEIGHT))
    name = _session_name(rm_id)

    rc, _, err = _tmux(
        "new-session", "-d", "-s", name,
        "-x", str(width), "-y", str(height),
        "-c", str(cwd), cmd,
    )
    if rc != 0:
        raise ApiError(500, f"tmux new-session a échoué : {err.strip()}")

    # pipe-pane : capture continue du pane vers un log (alimente /stream).
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logf = _log_path(rm_id)
    _tmux("pipe-pane", "-o", "-t", name, f"cat >> {shlex.quote(str(logf))}")

    # Prompt initial éventuel, livré par send-keys (jamais dans la cmd).
    prompt = payload.get("prompt")
    if prompt:
        time.sleep(0.3)  # laisse le moteur démarrer son TUI
        op_send({"rm_id": rm_id, "msg": prompt, "enter": True})

    return {"rm_id": rm_id, "tmux": name, "engine": engine, "cwd": str(cwd), "created": True}


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
        if AUTH_TOKEN is None:
            return True
        return self.headers.get("X-Karl-Token") == AUTH_TOKEN

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
        # Routes publiques du cockpit (RM1873) — SANS auth : la page doit pouvoir
        # se charger pour qu'on y saisisse le token, et elle ne divulgue rien de
        # sensible (le ttyd_base est déjà déductible côté client).
        if path in ("/", "/cockpit"):
            try:
                return self._send_html(200, (COCKPIT_DIR / "index.html").read_text(encoding="utf-8"))
            except FileNotFoundError:
                return self._send_json(404, {"error": "cockpit/index.html absent"})
        if path == "/cockpit-config":
            return self._send_json(200, {
                "ttyd_base": TTYD_URL,
                "auth_required": AUTH_TOKEN is not None,
            })
        if not self._check_auth():
            return self._send_json(401, {"error": "token requis (X-Karl-Token)"})
        try:
            if path == "/health":
                return self._send_json(200, {
                    "status": "ok",
                    "sessions": len(_list_sessions()),
                    "tmux": _tmux("-V")[0] == 0,
                })
            if path == "/sessions":
                return self._send_json(200, {"sessions": _list_sessions()})
            if path.startswith("/capture/"):
                rm_id = path[len("/capture/"):]
                qs = parse_qs(parsed.query)
                lines = int(qs["lines"][0]) if "lines" in qs else None
                return self._send_text(200, op_capture(rm_id, lines))
            if path.startswith("/stream/"):
                return self._stream(path[len("/stream/"):])
            return self._send_json(404, {"error": f"route inconnue : {path}"})
        except ApiError as e:
            return self._send_json(e.code, {"error": e.msg})
        except Exception as e:  # noqa: BLE001
            return self._send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        if not self._check_auth():
            return self._send_json(401, {"error": "token requis (X-Karl-Token)"})
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/spawn":
                return self._send_json(201, op_spawn(payload))
            if path == "/send":
                return self._send_json(200, op_send(payload))
            if path == "/kill":
                return self._send_json(200, op_kill(payload))
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
