#!/usr/bin/env python3
"""Vault agent daemon — keeps the vault session in process memory, exposes a Unix socket.

Design :
- Started by `unlock-vault.sh` (which feeds BW_SESSION via the socket).
- Listens on /run/user/$UID/vault-agentd.sock (chmod 600).
- Exposes a tiny line-based protocol (`<slug>` = instance ; omis → instance par défaut) :
    SET-SESSION [<slug>] <token> → stores session in memory, resets activity
    GET <uri> [field]            → resolves item via the backend, prints requested
                                    field (or full JSON if no field). Resets TTL.
                                    URI : secret://<instance>/<path…>[#field],
                                    secret:<path…>, vaultwarden://<org>/<coll>/<item>
    LOCK                         → wipes ALL sessions, daemon exits cleanly
    LOCK <slug>                  → wipes THAT session ; daemon survives if others live
    STATUS                       → one `<slug>\\t<état>` line per known instance
    STATUS <slug>                → historical one-line format for that instance
    LIST [filter]                → items of the default instance
    LIST-IN <slug> [filter]      → items of a named instance
    SYNC [<slug>]                → refresh the backend's local cache
    PING                         → "OK"
- No disk writes. Sessions live only in this process' memory.
- Inactivity timeout : configurable via env VAULT_IDLE_TIMEOUT (seconds, default 28800 = 8h).
- Daily auto-lock at hour from env VAULT_LOCK_AT_HOUR (24h format, default 23). Disabled if -1.

RM2681 (L0) : la résolution est déléguée à `pm_secrets` (interface `SecretBackend`).

RM2683 (L2) : **un état par instance** (session + horodatages + backend), donc TTL
et verrouillage indépendants — déverrouiller le vault d'un client ne prolonge pas
celui d'iProspective, et son expiration ne le verrouille pas. Le daemon ne quitte
que quand plus aucune instance n'est déverrouillée (comportement d'origine dès lors
qu'il n'y en a qu'une). Le type de chaque instance vient du registre providers
(`axis: secret`, RM2682) **s'il est disponible** : sans lui, le daemon sert la seule
instance `VAULT_INSTANCE` (défaut `vw-ipro`) comme avant. Une instance inconnue est
refusée, jamais résolue en silence sur le vault par défaut.
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
_states = {}           # slug -> _InstanceState
_registry_cache = None  # None = pas encore lu ; {} = registre indisponible


class _InstanceState:
    """État d'UNE instance : sa session et ses horodatages.

    Un état par slug — déverrouiller le vault d'un client ne prolonge pas celui
    d'iProspective, et son expiration ne le verrouille pas.
    """

    def __init__(self, slug, backend_type, options=None):
        self.slug = slug
        self.backend_type = backend_type
        self.session = None
        self.unlocked_at = None
        self.last_access = None
        self.backend = pm_secrets.get_backend(
            backend_type, name=slug,
            session_getter=lambda: self.session, **(options or {}))

    # Les accès à `session` passent tous par le verrou global (cf. helpers).
    def set_session(self, token):
        self.session = token
        self.unlocked_at = time.time()
        self.last_access = time.time()

    def wipe(self):
        self.session = None
        self.unlocked_at = None
        self.last_access = None

    def touch(self):
        self.last_access = time.time()

    @property
    def unlocked(self):
        return self.session is not None

    def status_line(self):
        """Format historique, à l'identique — des scripts l'affichent tel quel."""
        if not self.unlocked:
            return "locked"
        unlocked = datetime.fromtimestamp(self.unlocked_at).isoformat(timespec="seconds")
        last = datetime.fromtimestamp(self.last_access).isoformat(timespec="seconds")
        return f"unlocked since={unlocked} last_access={last} idle_timeout={IDLE_TIMEOUT}s"


def _instance_spec(slug):
    """(type, options) d'une instance, d'après le registre providers s'il est là.

    Le daemon ne DÉPEND pas du registre : sans axe `secret` déclaré (ou sans
    `pm_registry` du tout), il sert la seule instance par défaut, comme avant.
    """
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = {}
        try:
            from pm_paths import PMConfig
            from pm_registry import Registry
            # PM_CORE_DIR : racine de config alternative (défaut = ce dépôt).
            # Couture de testabilité, comme VAULT_SOCK — un daemon de test doit
            # pouvoir déclarer ses propres instances sans toucher à la conf livrée.
            core_dir = os.environ.get("PM_CORE_DIR") or None
            reg = Registry.from_config(PMConfig.load(core_dir).providers)
            for inst in reg.servers.values():
                if inst.axis == "secret":
                    _registry_cache[inst.name] = (inst.type, dict(inst.options))
        except (Exception, SystemExit) as e:  # noqa: BLE001
            # Registre absent, illisible ou incohérent : on DÉGRADE vers l'instance
            # par défaut. `SystemExit` compte : `PMConfig.load()` fait `sys.exit()`
            # sur une config incomplète, et il ne dérive pas d'`Exception` — sans ce
            # cas, il tuerait le thread de service et le client recevrait un silence.
            print(f"vault-agentd: registre providers indisponible ({type(e).__name__}) "
                  f"→ instance unique {INSTANCE!r}", file=sys.stderr)
            _registry_cache = {}
    if slug in _registry_cache:
        return _registry_cache[slug]
    if slug == INSTANCE:
        return BACKEND_TYPE, {}
    return None


def _get_state(slug, create=True):
    """État d'une instance (créé à la demande). `UnsupportedError` si inconnue.

    Une instance inconnue est REFUSÉE : la résoudre en silence sur le vault par
    défaut irait chercher un secret dans le mauvais coffre.
    """
    with _state_lock:
        st = _states.get(slug)
        if st is not None:
            return st
    spec = _instance_spec(slug)
    if spec is None:
        known = ", ".join(sorted(set(list(_registry_cache or {}) + [INSTANCE])))
        raise pm_secrets.UnsupportedError(
            f"instance {slug!r} inconnue (déclarées : {known}) — "
            f"déclare-la dans pm.config.yml :: providers.servers", backend=slug)
    if not create:
        return None
    with _state_lock:
        st = _states.get(slug)
        if st is None:
            st = _InstanceState(slug, spec[0], spec[1])
            _states[slug] = st
        return st


def _slug_of(ref):
    """Slug visé par un URI : celui qu'il nomme, sinon l'instance par défaut."""
    return ref.instance or INSTANCE


def _dashboard():
    """Une ligne `<slug>\\t<état>` par instance connue (déclarée ou touchée)."""
    slugs = set(_states)
    _instance_spec(INSTANCE)                     # amorce la lecture du registre
    slugs |= set(_registry_cache or {})
    slugs.add(INSTANCE)
    lignes = []
    for slug in sorted(slugs):
        with _state_lock:
            st = _states.get(slug)
            etat = st.status_line() if st else "locked"
        lignes.append(f"{slug}\t{etat}")
    return "\n".join(lignes)


def _exit_soon():
    """Sortie propre, après avoir répondu au client (comportement historique)."""
    threading.Thread(
        target=lambda: (time.sleep(0.1), os.kill(os.getpid(), signal.SIGTERM)),
        daemon=True).start()


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
                # Sans slug : tableau de bord, une ligne `<slug>\t<état>` par
                # instance connue. Avec slug : format historique, à l'identique.
                if len(parts) > 1:
                    st = _get_state(parts[1])
                    with _state_lock:
                        self.wfile.write((st.status_line() + "\n").encode())
                else:
                    self.wfile.write((_dashboard() + "\n").encode())
            elif cmd == "SET-SESSION":
                # `SET-SESSION <token>` (instance par défaut) ou
                # `SET-SESSION <slug> <token>` — non ambigu, un token est un seul mot.
                if len(parts) < 2:
                    self.wfile.write(b"ERR SET-SESSION expects a token\n"); return
                slug, token = (parts[1], parts[2]) if len(parts) > 2 else (INSTANCE, parts[1])
                st = _get_state(slug)
                with _state_lock:
                    st.set_session(token)
                self.wfile.write(b"OK\n")
            elif cmd == "LOCK":
                # `LOCK` : tout verrouiller et quitter (comportement historique).
                # `LOCK <slug>` : cette instance seule ; le daemon survit s'il en
                # reste d'autres déverrouillées.
                if len(parts) > 1:
                    st = _get_state(parts[1])
                    with _state_lock:
                        st.wipe()
                        reste = any(s.unlocked for s in _states.values())
                    self.wfile.write(b"OK\n")
                    if not reste:
                        _exit_soon()
                else:
                    with _state_lock:
                        for s in _states.values():
                            s.wipe()
                    self.wfile.write(b"OK\n")
                    _exit_soon()
            elif cmd == "SYNC":
                st = _get_state(parts[1] if len(parts) > 1 else INSTANCE)
                with _state_lock:
                    locked = not st.unlocked
                if locked:
                    self.wfile.write(b"ERR locked\n"); return
                st.backend.sync()
                with _state_lock:
                    st.touch()
                self.wfile.write(b"OK\n")
            elif cmd in ("LIST", "LIST-IN"):
                # LIST [filtre] → instance par défaut (inchangé).
                # LIST-IN <slug> [filtre] → une instance nommée. Deux verbes
                # distincts plutôt qu'un argument ambigu slug-ou-filtre.
                if cmd == "LIST-IN":
                    if len(parts) < 2:
                        self.wfile.write(b"ERR LIST-IN expects an instance [filter]\n"); return
                    slug, filt = parts[1], (parts[2] if len(parts) > 2 else None)
                else:
                    slug, filt = INSTANCE, (parts[1] if len(parts) > 1 else None)
                st = _get_state(slug)
                with _state_lock:
                    locked = not st.unlocked
                if locked:
                    self.wfile.write(b"ERR locked\n"); return
                items = st.backend.list(filt)
                with _state_lock:
                    st.touch()
                out = [f"{it['id']}\t{it['org']}\t{','.join(it['collections']) or '-'}\t{it['name']}"
                       for it in items]
                self.wfile.write(("\n".join(out) + "\n").encode())
            elif cmd == "GET":
                if len(parts) < 2:
                    self.wfile.write(b"ERR GET expects a uri [field]\n"); return
                ref = pm_secrets.parse_uri(parts[1])
                # Le champ explicite du protocole l'emporte sur le `#champ` de l'URI.
                field = parts[2] if len(parts) > 2 else ref.field
                st = _get_state(_slug_of(ref))
                with _state_lock:
                    locked = not st.unlocked
                if locked:
                    self.wfile.write(b"ERR locked\n"); return
                value = st.backend.resolve(ref.path, field)
                with _state_lock:
                    st.touch()
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


def _bg_supervisor(interval=30):
    """Expiration d'inactivité + verrouillage horaire, **instance par instance**.

    Chaque instance a son propre compteur : le vault d'un client expire sans
    toucher à celui d'iProspective. Le daemon ne quitte que quand il ne reste plus
    aucune instance déverrouillée — c'est le comportement historique dès lors qu'il
    n'y en a qu'une.
    """
    while True:
        time.sleep(interval)
        now = time.time()
        horaire = (LOCK_AT_HOUR >= 0
                   and datetime.now().hour == LOCK_AT_HOUR
                   and datetime.now().minute < 1)
        with _state_lock:
            actives = [s for s in _states.values() if s.unlocked]
            if not actives:
                continue
            for st in actives:
                if horaire or (now - (st.last_access or 0)) > IDLE_TIMEOUT:
                    st.wipe()
            reste = any(s.unlocked for s in _states.values())
        if not reste:
            os.kill(os.getpid(), signal.SIGTERM)
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--idle-timeout", type=int, help="Override VAULT_IDLE_TIMEOUT (seconds)")
    ap.add_argument("--lock-at-hour", type=int, help="Override VAULT_LOCK_AT_HOUR (0-23 or -1 to disable)")
    ap.add_argument("--supervisor-interval", type=float, default=30.0,
                    help="Période de contrôle des expirations (s, défaut 30) — "
                         "abaissée par les tests pour observer un TTL réel")
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

    threading.Thread(target=_bg_supervisor, args=(args.supervisor_interval,),
                     daemon=True).start()

    def _shutdown(*_):
        # Toutes les sessions disparaissent avec le process — on les efface
        # explicitement pour ne pas les laisser traîner en mémoire d'ici là.
        with _state_lock:
            for st in _states.values():
                st.wipe()
        try: os.unlink(SOCK_PATH)
        except FileNotFoundError: pass
        sys.exit(0)
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    print(f"vault-agentd listening on {SOCK_PATH}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
