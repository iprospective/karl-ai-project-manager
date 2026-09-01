#!/usr/bin/env python3
"""Tests end-to-end de l'auth par comptes + tokens d'appareil (RM2334).

Lance un karl-agent réel sur un port éphémère avec un superadmin de conf
(.env simulé par variables d'environnement) et un var/ jetable, puis déroule
les critères d'acceptation du ticket via l'API HTTP. Stdlib-only, comme le
daemon. Lancer : python3 scripts/test-karl-agent-auth.py
"""
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ADMIN_USER, ADMIN_PASS = "boss", "s3cret-admin-pw"
FAILURES = []


def check(label, cond, detail=""):
    print(("✓ " if cond else "✗ ") + label + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


def req(port, method, path, payload=None, token=None, basic=None, cookie=None,
        want_headers=False):
    """→ (code, objet_json|texte) ; si want_headers : (code, obj, headers).
    Ne lève jamais : les 4xx/5xx sont renvoyés. `cookie` = valeur brute de
    l'en-tête Cookie (RM2700)."""
    r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
    if payload is not None:
        r.data = json.dumps(payload).encode()
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("X-Karl-Token", token)
    if cookie:
        r.add_header("Cookie", cookie)
    if basic:
        import base64
        r.add_header("Authorization", "Basic " + base64.b64encode(
            f"{basic[0]}:{basic[1]}".encode()).decode())
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            body = resp.read().decode()
            code = resp.status
            headers = resp.headers
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        code = e.code
        headers = e.headers
    try:
        obj = json.loads(body)
    except ValueError:
        obj = body
    return (code, obj, headers) if want_headers else (code, obj)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="karl-auth-test-"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ,
           "KARL_AGENT_PORT": str(port),
           "KARL_WEB_USER": ADMIN_USER, "KARL_WEB_PASS": ADMIN_PASS,
           "KARL_AGENT_AUTH_DIR": str(tmp / "var"),
           "KARL_AGENT_LOG_DIR": str(tmp / "logs")}
    env.pop("KARL_AGENT_TOKEN", None)  # mode identifiants pur
    proc = subprocess.Popen([sys.executable, str(REPO / "scripts" / "karl-agent.py")],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):  # attendre le bind
            try:
                req(port, "GET", "/cockpit-config")
                break
            except (ConnectionRefusedError, urllib.error.URLError):
                time.sleep(0.1)

        # ── page + config publiques, données gated ───────────────────────────
        code, cfg = req(port, "GET", "/cockpit-config")
        check("config publique sans auth", code == 200)
        check("auth_required exposé", cfg.get("auth_required") is True)
        check("login_enabled exposé", cfg.get("login_enabled") is True)
        code, _ = req(port, "GET", "/health")
        check("données gated sans auth (401)", code == 401)

        # ── login : échec, throttle, succès superadmin ───────────────────────
        code, _ = req(port, "POST", "/auth/login", {"user": ADMIN_USER, "pass": "faux"})
        check("mauvais mdp → 401", code == 401)
        for _ in range(3):
            code, _ = req(port, "POST", "/auth/login", {"user": ADMIN_USER, "pass": "faux"})
        check("bruteforce → 429 après échecs répétés", code == 429)
        time.sleep(4.5)  # verrou progressif : 3e échec = 2 s, 4e = 4 s
        code, adm = req(port, "POST", "/auth/login",
                        {"user": ADMIN_USER, "pass": ADMIN_PASS, "device_name": "test-admin"})
        check("login superadmin (.env) → token", code == 200 and bool(adm.get("token")))
        check("superadmin est admin", adm.get("admin") is True)
        atok = adm["token"]

        code, who = req(port, "GET", "/auth/whoami", token=atok)
        check("whoami via token d'appareil", code == 200 and who.get("mode") == "device")
        code, _ = req(port, "GET", "/health", token=atok)
        check("API accessible via token d'appareil", code == 200)
        code, _ = req(port, "GET", "/health", token="n-importe-quoi")
        check("token invalide → 401", code == 401)
        code, _ = req(port, "GET", "/health", basic=(ADMIN_USER, ADMIN_PASS))
        check("fallback Basic conservé (rétrocompat)", code == 200)

        # ── RM2700 : cookie de session même-origine (gate terminal /ttyd) ─────
        code, clog, hdrs = req(port, "POST", "/auth/login",
                               {"user": ADMIN_USER, "pass": ADMIN_PASS,
                                "device_name": "test-cookie"}, want_headers=True)
        setck = hdrs.get("Set-Cookie", "") if hdrs else ""
        check("login → Set-Cookie karl_session", code == 200 and "karl_session=" in setck)
        check("cookie durci (HttpOnly+Secure+SameSite=Strict)",
              all(a in setck for a in ("HttpOnly", "Secure", "SameSite=Strict")))
        ctok = clog["token"]
        ck = f"karl_session={ctok}"
        code, who = req(port, "GET", "/auth/whoami", cookie=ck)
        check("auth via cookie (mode=cookie)", code == 200 and who.get("mode") == "cookie")
        code, _ = req(port, "GET", "/health", cookie=ck)
        check("API accessible via cookie (upgrade /ttyd même origine)", code == 200)
        code, _ = req(port, "GET", "/health", cookie="karl_session=bidon")
        check("cookie invalide → 401", code == 401)
        # logout via cookie : révoque l'appareil courant ET purge le cookie
        code, _, hdrs = req(port, "DELETE", f"/auth/devices/{clog['device_id']}",
                            cookie=ck, want_headers=True)
        clr = hdrs.get("Set-Cookie", "") if hdrs else ""
        check("logout via cookie révoque l'appareil", code == 200)
        check("logout purge le cookie (Max-Age=0)",
              "karl_session=" in clr and "Max-Age=0" in clr)
        code, _ = req(port, "GET", "/health", cookie=ck)
        check("cookie révoqué refusé immédiatement", code == 401)

        # ── comptes normaux : CRUD superadmin-only ───────────────────────────
        code, _ = req(port, "POST", "/auth/users",
                      {"user": "alice", "pass": "alice-pw-123"}, token=atok)
        check("création compte normal (admin)", code == 201)
        code, _ = req(port, "POST", "/auth/users", {"user": ADMIN_USER, "pass": "x" * 10},
                      token=atok)
        check("nom du superadmin réservé", code == 400)
        code, al = req(port, "POST", "/auth/login",
                       {"user": "alice", "pass": "alice-pw-123", "device_name": "tel-alice"})
        check("login compte normal → token", code == 200 and bool(al.get("token")))
        check("compte normal non admin", al.get("admin") is False)
        utok = al["token"]
        code, _ = req(port, "GET", "/auth/users", token=utok)
        check("liste des comptes refusée à un compte normal (403)", code == 403)
        code, _ = req(port, "POST", "/auth/users", {"user": "eve", "pass": "eve-pw-1234"},
                      token=utok)
        check("création de compte refusée à un compte normal (403)", code == 403)

        # ── appareils : liste, périmètre, révocation ─────────────────────────
        code, devs = req(port, "GET", "/auth/devices", token=utok)
        mine = devs.get("devices", [])
        check("un compte normal ne voit que ses appareils",
              code == 200 and len(mine) == 1 and mine[0]["user"] == "alice")
        code, devs = req(port, "GET", "/auth/devices", token=atok)
        check("le superadmin voit tous les appareils",
              code == 200 and len(devs.get("devices", [])) == 2)
        code, _ = req(port, "DELETE", f"/auth/devices/{adm['device_id']}", token=utok)
        check("révocation d'un appareil d'autrui refusée (403)", code == 403)
        code, _ = req(port, "DELETE", f"/auth/devices/{al['device_id']}", token=utok)
        check("logout : révocation de son propre appareil", code == 200)
        code, _ = req(port, "GET", "/health", token=utok)
        check("token révoqué refusé immédiatement", code == 401)

        # ── désactivation : login bloqué + tokens tombés ─────────────────────
        code, al2 = req(port, "POST", "/auth/login", {"user": "alice", "pass": "alice-pw-123"})
        check("re-login alice", code == 200)
        code, _ = req(port, "PUT", "/auth/users/alice", {"disabled": True}, token=atok)
        check("désactivation par le superadmin", code == 200)
        code, _ = req(port, "GET", "/health", token=al2.get("token", "x"))
        check("tokens du compte désactivé révoqués", code == 401)
        code, _ = req(port, "POST", "/auth/login", {"user": "alice", "pass": "alice-pw-123"})
        check("login refusé sur compte désactivé", code == 401)
        code, _ = req(port, "DELETE", "/auth/users/alice", token=atok)
        check("suppression de compte (admin)", code == 200)

        # ── jamais de secret en clair côté serveur ───────────────────────────
        blob = ""
        for f in (tmp / "var").glob("karl-*.json"):
            blob += f.read_text()
        for secret in (ADMIN_PASS, "alice-pw-123", atok):
            check(f"secret absent des stores serveur ({secret[:6]}…)", secret not in blob)
        modes = [oct(f.stat().st_mode & 0o777) for f in (tmp / "var").glob("karl-*.json")]
        check("stores en 0600", modes and all(m == "0o600" for m in modes), str(modes))
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)

    print(f"\n{len(FAILURES)} échec(s)" if FAILURES else "\nTous les tests passent.")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
