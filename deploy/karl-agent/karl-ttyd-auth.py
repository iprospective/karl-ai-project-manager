#!/usr/bin/env python3
"""Validateur d'accès au terminal distant `/ttyd` (RM2700) — gate même-origine.

Apache ne sait pas faire de sous-requête d'auth « à la nginx » ; on branche donc
un `RewriteMap prg:` qui, pour chaque upgrade WebSocket vers `/ttyd`, valide le
**cookie de session karl** (déposé par `/auth/login`, RM2334/RM2700) en
interrogeant karl-agent en loopback (`/auth/whoami`, déjà gated). Le token du
terminal voyage dans la 1re frame ttyd — invisible à l'upgrade HTTP — donc le
cookie même-origine est le SEUL credential qu'Apache peut vérifier à ce stade.

Contrat RewriteMap prg (mod_rewrite) :
  - une ligne de clé arrive sur stdin (ici : l'en-tête Cookie brut) ;
  - on répond une ligne sur stdout : « OK » (autorisé) ou « DENY » (refusé) ;
  - stdout DOIT être flushé à chaque ligne ; le process reste vivant en boucle ;
  - fail-closed : toute anomalie (parse, réseau, timeout) → « DENY ».

Conf Apache (vhost public mmi, et vhosts locaux rendus par karl-vhost-render.sh — RM2146) :
  RewriteEngine On
  RewriteMap  karlauth "prg:/usr/local/sbin/karl-ttyd-auth [--verify-url URL]"
  RewriteCond "${karlauth:%{HTTP:Cookie}}" "!=OK"
  RewriteRule "^/ttyd"  "-"  [F]

Test hors Apache :
  karl-ttyd-auth --check 'karl_session=<token>'      # → OK / DENY
  KARL_VERIFY_URL=http://127.0.0.1:9876/api/auth/whoami   (défaut ; RM3004 : cible /api)
  --verify-url URL (RM2146) prime sur KARL_VERIFY_URL : chaque vhost local valide le
  cookie auprès du karl-agent de SON instance (les instances de test ont leur port).
"""
import os
import sys
import urllib.error
import urllib.request
from http.cookies import SimpleCookie

VERIFY_URL = os.environ.get("KARL_VERIFY_URL", "http://127.0.0.1:9876/api/auth/whoami")
SESSION_COOKIE = "karl_session"
TIMEOUT_S = float(os.environ.get("KARL_VERIFY_TIMEOUT", "3"))


def _has_session(cookie_header: str) -> bool:
    """Le cookie de session karl est-il présent et non vide dans l'en-tête ?"""
    if not cookie_header or SESSION_COOKIE not in cookie_header:
        return False
    try:
        jar = SimpleCookie()
        jar.load(cookie_header)
    except Exception:  # noqa: BLE001 — en-tête malformé
        return False
    m = jar.get(SESSION_COOKIE)
    return bool(m and m.value)


def verify(cookie_header: str, url: str = None) -> bool:
    """True si le cookie présenté ouvre une session karl valide. Fail-closed :
    toute erreur (réseau, timeout, non-200) → False."""
    if not _has_session(cookie_header):
        return False
    req = urllib.request.Request(url or VERIFY_URL, method="GET")
    req.add_header("Cookie", cookie_header)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return resp.status == 200
    except urllib.error.HTTPError:
        return False            # 401/403 → refus
    except Exception:           # noqa: BLE001 — connexion, timeout, DNS…
        return False


def _answer(cookie_header: str, url: str = None) -> str:
    return "OK" if verify(cookie_header, url) else "DENY"


def main() -> int:
    args, url = sys.argv[1:], None
    if len(args) >= 2 and args[0] == "--verify-url":
        url, args = args[1], args[2:]
    if len(args) >= 2 and args[0] == "--check":
        print(_answer(args[1], url))
        return 0
    # Mode RewriteMap : boucle ligne à ligne, stdout flushé, jamais fatal.
    for line in sys.stdin:
        cookie_header = line.rstrip("\n")
        try:
            out = _answer(cookie_header, url)
        except Exception:  # noqa: BLE001 — ne jamais tuer le map
            out = "DENY"
        sys.stdout.write(out + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
