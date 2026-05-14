#!/usr/bin/env python3
"""Vault agent daemon — keeps Vaultwarden session in process memory, exposes a Unix socket.

Design :
- Started by `unlock-vault.sh` (which feeds BW_SESSION via the socket).
- Listens on /run/user/$UID/vault-agentd.sock (chmod 600).
- Exposes a tiny line-based protocol :
    SET-SESSION <BW_SESSION>     → stores session in memory, resets activity
    GET <vaultwarden://o/c/i> [field]
                                  → resolves item via `bw`, prints requested field
                                    (or full JSON if no field). Resets activity TTL.
    LOCK                         → wipes session in memory, daemon exits cleanly
    STATUS                       → prints "unlocked since <ts>" or "locked"
    PING                         → "OK"
- No disk writes. BW_SESSION lives only in this process' memory.
- Inactivity timeout : configurable via env VAULT_IDLE_TIMEOUT (seconds, default 28800 = 8h).
- Daily auto-lock at hour from env VAULT_LOCK_AT_HOUR (24h format, default 23). Disabled if -1.
"""

import argparse
import json
import os
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta

SOCK_DIR = f"/run/user/{os.getuid()}"
SOCK_PATH = f"{SOCK_DIR}/vault-agentd.sock"

IDLE_TIMEOUT = int(os.environ.get("VAULT_IDLE_TIMEOUT", "28800"))   # 8h
LOCK_AT_HOUR = int(os.environ.get("VAULT_LOCK_AT_HOUR", "23"))      # 23h ; -1 to disable

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


def _parse_uri(uri: str):
    # vaultwarden://<org>/<collection>/<item>
    if not uri.startswith("vaultwarden://"):
        raise ValueError(f"unsupported scheme: {uri}")
    rest = uri[len("vaultwarden://"):]
    parts = rest.split("/", 2)
    if len(parts) != 3:
        raise ValueError(f"expected vaultwarden://<org>/<collection>/<item>, got {uri}")
    return parts  # org, collection, item


def _bw_get(item: str, session: str):
    """Call `bw get item <item> --session <session>` and return the parsed JSON."""
    p = subprocess.run(
        ["bw", "get", "item", item, "--session", session],
        capture_output=True, text=True, timeout=15,
    )
    if p.returncode != 0:
        raise RuntimeError(f"bw failed: {p.stderr.strip()}")
    return json.loads(p.stdout)


def _extract_field(item_json: dict, field: str | None):
    if field is None:
        # default: pretty-print just login.password if present, else full json
        login = (item_json.get("login") or {})
        if "password" in login and login["password"]:
            return login["password"]
        return json.dumps(item_json, ensure_ascii=False)
    # canonical fields
    if field == "password":
        return (item_json.get("login") or {}).get("password", "")
    if field == "username":
        return (item_json.get("login") or {}).get("username", "")
    if field == "notes":
        return item_json.get("notes") or ""
    if field == "uri":
        uris = (item_json.get("login") or {}).get("uris") or []
        return uris[0]["uri"] if uris else ""
    # custom fields
    for f in item_json.get("fields") or []:
        if f.get("name") == field:
            return f.get("value", "")
    return ""


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
                with _state_lock:
                    session = _bw_session
                if session is None:
                    self.wfile.write(b"ERR locked\n"); return
                p = subprocess.run(["bw", "sync", "--session", session],
                                   capture_output=True, text=True, timeout=60)
                _touch()
                if p.returncode != 0:
                    self.wfile.write(f"ERR bw sync: {p.stderr.strip()}\n".encode())
                else:
                    self.wfile.write(b"OK\n")
            elif cmd == "LIST":
                with _state_lock:
                    session = _bw_session
                if session is None:
                    self.wfile.write(b"ERR locked\n"); return
                # optional filter on collection name (substring match)
                filt = parts[1] if len(parts) > 1 else None
                p = subprocess.run(["bw", "list", "items", "--session", session],
                                   capture_output=True, text=True, timeout=15)
                if p.returncode != 0:
                    self.wfile.write(f"ERR bw list: {p.stderr.strip()}\n".encode())
                    return
                _touch()
                items = json.loads(p.stdout)
                # build a brief summary, one item per line
                out = []
                for it in items:
                    name = it.get("name", "")
                    iid = it.get("id", "")
                    coll_ids = it.get("collectionIds") or []
                    org_id = it.get("organizationId") or "-"
                    line = f"{iid}\t{org_id}\t{','.join(coll_ids) or '-'}\t{name}"
                    if filt is None or filt.lower() in name.lower():
                        out.append(line)
                self.wfile.write(("\n".join(out) + "\n").encode())
            elif cmd == "GET":
                if len(parts) < 2:
                    self.wfile.write(b"ERR GET expects a uri [field]\n"); return
                uri = parts[1]
                field = parts[2] if len(parts) > 2 else None
                with _state_lock:
                    session = _bw_session
                    locked = session is None
                if locked:
                    self.wfile.write(b"ERR locked\n"); return
                org, coll, item = _parse_uri(uri)
                item_json = _bw_get(item, session)
                _touch()
                # confirm item is in expected org/collection? optional; bw doesn't easily expose that.
                value = _extract_field(item_json, field)
                # never log the value, just send it back
                self.wfile.write((value + "\n").encode())
            else:
                self.wfile.write(f"ERR unknown command: {cmd}\n".encode())
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
