#!/usr/bin/env python3
"""Vault agent daemon — keeps the vault session in process memory, exposes a Unix socket.

Design :
- Started by `unlock-vault.sh` (which feeds BW_SESSION via the socket).
- Listens on /run/user/$UID/vault-agentd.sock (chmod 600).
- Exposes a tiny line-based protocol :
    SET-SESSION <BW_SESSION>     → stores session in memory, resets activity
    GET <uri> [field]            → resolves item via the backend, prints requested
                                    field (or full JSON if no field). Resets TTL.
                                    URI : secret://<instance>/<path…>[#field],
                                    secret:<path…>, vaultwarden://<org>/<coll>/<item>
    LOCK                         → wipes session in memory, daemon exits cleanly
    STATUS                       → prints "unlocked since <ts>" or "locked"
    PING                         → "OK"
- No disk writes. The session lives only in this process' memory.
- Inactivity timeout : configurable via env VAULT_IDLE_TIMEOUT (seconds, default 28800 = 8h).
- Daily auto-lock at hour from env VAULT_LOCK_AT_HOUR (24h format, default 23). Disabled if -1.

RM2681 (L0) : la résolution est déléguée à `pm_secrets` (interface `SecretBackend`).
Ce daemon ne sert **qu'une** instance — celle nommée `VAULT_INSTANCE` (défaut
`vw-ipro`) ; un URI visant un autre slug est refusé explicitement. Le multi-instances
arrive en RM2683 (L2), la résolution du slug par projet/client en RM2682 (L1).
"""

import argparse
import importlib.util
import os
import signal
import socket
import socketserver
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_secrets", str(_HERE / "pm_secrets.py"))
pm_secrets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm_secrets)

# VAULT_SOCK : chemin du socket (défaut inchangé). Sert au harnais de
# non-régression, qui doit lancer un daemon sans toucher celui de la session.
SOCK_PATH = os.environ.get("VAULT_SOCK") or f"/run/user/{os.getuid()}/vault-agentd.sock"
SOCK_DIR = os.path.dirname(SOCK_PATH)

IDLE_TIMEOUT = int(os.environ.get("VAULT_IDLE_TIMEOUT", "28800"))   # 8h
LOCK_AT_HOUR = int(os.environ.get("VAULT_LOCK_AT_HOUR", "23"))      # 23h ; -1 to disable
INSTANCE = os.environ.get("VAULT_INSTANCE", "vw-ipro")              # slug servi
BACKEND_TYPE = os.environ.get("VAULT_BACKEND", "vaultwarden")

_state_lock = threading.Lock()
_bw_session = None
_unlocked_at = None
_last_access = None


def _wipe_session():
    global _bw_session, _unlocked_at, _last_access
    with _state_lock:
        _bw_session = None
        _unlocked_at = None
        _last_access = None


def _set_session(token: str):
    global _bw_session, _unlocked_at, _last_access
    with _state_lock:
        _bw_session = token
        _unlocked_at = time.time()
        _last_access = time.time()


def _touch():
    global _last_access
    with _state_lock:
        _last_access = time.time()


def _status_line():
    with _state_lock:
        if _bw_session is None:
            return "locked"
        unlocked = datetime.fromtimestamp(_unlocked_at).isoformat(timespec="seconds")
        last = datetime.fromtimestamp(_last_access).isoformat(timespec="seconds")
        return f"unlocked since={unlocked} last_access={last} idle_timeout={IDLE_TIMEOUT}s"


def _session_or_none():
    """Session courante, lue sous verrou. Le backend l'obtient à chaque appel :
    il reste sans état, la session ne vit qu'ici."""
    with _state_lock:
        return _bw_session


_backend = pm_secrets.get_backend(BACKEND_TYPE, name=INSTANCE,
                                  session_getter=_session_or_none)


def _check_instance(ref):
    """Refuse explicitement un URI visant une autre instance que celle servie.

    Ignorer le slug silencieusement résoudrait dans le mauvais vault — mieux vaut
    un refus lisible tant que le multi-instances n'est pas livré (RM2683/L2)."""
    if ref.instance and ref.instance != INSTANCE:
        raise pm_secrets.UnsupportedError(
            f"instance {ref.instance!r} inconnue de ce daemon (il sert "
            f"{INSTANCE!r}) — multi-instances : RM2683", backend=INSTANCE)


class VaultHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            line = self.rfile.readline().decode("utf-8", errors="replace").rstrip("\n")
        except Exception as e:
            self.wfile.write(f"ERR read: {e}\n".encode())
            return

        parts = line.split(" ", 2)
        cmd = parts[0].upper() if parts else ""

        try:
            if cmd == "PING":
                self.wfile.write(b"OK\n")
            elif cmd == "STATUS":
                self.wfile.write((_status_line() + "\n").encode())
            elif cmd == "SET-SESSION":
                if len(parts) < 2:
                    self.wfile.write(b"ERR SET-SESSION expects a token\n"); return
                _set_session(parts[1])
                self.wfile.write(b"OK\n")
            elif cmd == "LOCK":
                _wipe_session()
                self.wfile.write(b"OK\n")
                # graceful exit
                threading.Thread(target=lambda: (time.sleep(0.1), os.kill(os.getpid(), signal.SIGTERM)), daemon=True).start()
            elif cmd == "SYNC":
                if _session_or_none() is None:
                    self.wfile.write(b"ERR locked\n"); return
                _backend.sync()
                _touch()
                self.wfile.write(b"OK\n")
            elif cmd == "LIST":
                if _session_or_none() is None:
                    self.wfile.write(b"ERR locked\n"); return
                # optional filter on item name (substring match)
                filt = parts[1] if len(parts) > 1 else None
                items = _backend.list(filt)
                _touch()
                out = [f"{it['id']}\t{it['org']}\t{','.join(it['collections']) or '-'}\t{it['name']}"
                       for it in items]
                self.wfile.write(("\n".join(out) + "\n").encode())
            elif cmd == "GET":
                if len(parts) < 2:
                    self.wfile.write(b"ERR GET expects a uri [field]\n"); return
                ref = pm_secrets.parse_uri(parts[1])
                _check_instance(ref)
                # Le champ explicite du protocole l'emporte sur le `#champ` de l'URI.
                field = parts[2] if len(parts) > 2 else ref.field
                if _session_or_none() is None:
                    self.wfile.write(b"ERR locked\n"); return
                value = _backend.resolve(ref.path, field)
                _touch()
                # never log the value, just send it back
                self.wfile.write((value + "\n").encode())
            else:
                self.wfile.write(f"ERR unknown command: {cmd}\n".encode())
        except pm_secrets.LockedError:
            # Contrat historique : `resolve-secret.sh` teste le préfixe "ERR locked".
            self.wfile.write(b"ERR locked\n")
        except pm_secrets.SecretError as e:
            self.wfile.write(f"ERR {e.code}: {e}\n".encode())
        except Exception as e:
            self.wfile.write(f"ERR {type(e).__name__}: {e}\n".encode())


def _bg_supervisor():
    """Check idle timeout + daily lock hour periodically. Wipe session if exceeded."""
    while True:
        time.sleep(30)
        with _state_lock:
            if _bw_session is None:
                continue
            idle = time.time() - (_last_access or 0)
        if idle > IDLE_TIMEOUT:
            _wipe_session()
            os.kill(os.getpid(), signal.SIGTERM)
            return
        if LOCK_AT_HOUR >= 0 and datetime.now().hour == LOCK_AT_HOUR and datetime.now().minute < 1:
            _wipe_session()
            os.kill(os.getpid(), signal.SIGTERM)
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--idle-timeout", type=int, help="Override VAULT_IDLE_TIMEOUT (seconds)")
    ap.add_argument("--lock-at-hour", type=int, help="Override VAULT_LOCK_AT_HOUR (0-23 or -1 to disable)")
    args = ap.parse_args()
    global IDLE_TIMEOUT, LOCK_AT_HOUR
    if args.idle_timeout is not None:
        IDLE_TIMEOUT = args.idle_timeout
    if args.lock_at_hour is not None:
        LOCK_AT_HOUR = args.lock_at_hour

    os.makedirs(SOCK_DIR, exist_ok=True)
    if os.path.exists(SOCK_PATH):
        # Try to ping existing daemon to know if it's alive
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(SOCK_PATH)
            s.sendall(b"PING\n")
            resp = s.recv(64).decode().strip()
            s.close()
            if resp == "OK":
                print("Another vault-agentd is already running.", file=sys.stderr)
                sys.exit(1)
        except Exception:
            pass
        os.unlink(SOCK_PATH)

    server = socketserver.ThreadingUnixStreamServer(SOCK_PATH, VaultHandler)
    os.chmod(SOCK_PATH, 0o600)

    threading.Thread(target=_bg_supervisor, daemon=True).start()

    def _shutdown(*_):
        _wipe_session()
        try: os.unlink(SOCK_PATH)
        except FileNotFoundError: pass
        sys.exit(0)
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    print(f"vault-agentd listening on {SOCK_PATH}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
