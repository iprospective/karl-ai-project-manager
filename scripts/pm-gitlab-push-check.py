#!/usr/bin/env python3
"""pm-gitlab-push-check — watchdog : karl peut-il pousser sur GitLab ? (RM2376)

Le transport git des repos PM est SSH-first via l'alias `gitlab:` et la clé dédiée
SANS passphrase de karl-dev (`~/.ssh/id_ed25519_gitlab`, RM2158). Si cette auth
casse (clé absente/déplacée, `Host gitlab` cassé, membership GitLab retiré,
known_hosts obsolète), deux pannes SILENCIEUSES : le push se reporte indéfiniment,
et `git fetch` échoue sans bruit → refs `origin/*` périmées.

Ce check vérifie l'auth (léger, SANS effet de bord distant) : `ssh gitlab` doit
répondre « Welcome to GitLab, @<user>! ». `SSH_AUTH_SOCK` est NEUTRALISÉ pour
tester la clé DÉDIÉE, pas un agent de passage (comme la validation RM2158).

Écrit l'état dans <STATE_DIR>/gitlab-push.json ; le cockpit (karl-agent) le lit et
le surface dans la page « 🩺 poste » (famille Git / GitLab).

Code retour : 0 si OK, 2 si KO (à surveiller par un timer/cron), 1 sur erreur interne.

Usage :
    pm-gitlab-push-check.py            # rapport lisible, écrit l'état JSON
    pm-gitlab-push-check.py --json     # sortie JSON (mode machine)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

GITLAB_ALIAS = os.environ.get("KARL_GITLAB_SSH_ALIAS", "gitlab")
REMEDIATION = ("vérifier : `ssh -o BatchMode=yes " + GITLAB_ALIAS + "` ; la clé dédiée "
               "~/.ssh/id_ed25519_gitlab (RM2158) ; le `Host gitlab` de ~/.ssh/config ; "
               "le membership GitLab de karl-dev ; known_hosts.")


def state_path() -> Path:
    """Même résolution que karl-agent (STATE_DIR), surchargeable pour partager le
    fichier entre le timer et le serveur si leurs homes diffèrent."""
    override = os.environ.get("KARL_GITLAB_CHECK_STATE")
    if override:
        return Path(override)
    sd = os.environ.get("KARL_AGENT_STATE_DIR") or os.environ.get("KARL_AGENT_LOG_DIR")
    if not sd:
        xdg = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
        sd = str(Path(xdg) / "karl-agent")
    return Path(sd) / "gitlab-push.json"


def run_check(timeout: int = 10) -> dict:
    """(ok, detail, user) de l'auth SSH GitLab. Aucun effet de bord distant."""
    env = dict(os.environ)
    env.pop("SSH_AUTH_SOCK", None)   # clé dédiée, pas un agent de passage (RM2158)
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
            "-o", "StrictHostKeyChecking=accept-new", GITLAB_ALIAS]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "detail": f"timeout ({timeout}s) — hôte gitlab injoignable ?", "user": None}
    except OSError as exc:
        return {"ok": False, "detail": f"ssh indisponible ({exc})", "user": None}
    out = (p.stdout or "") + (p.stderr or "")
    m = re.search(r"Welcome to GitLab, @([\w.-]+)!", out)
    if m:
        return {"ok": True, "detail": f"auth OK (@{m.group(1)})", "user": m.group(1)}
    if p.returncode == 0:
        return {"ok": True, "detail": "auth OK", "user": None}
    last = next((l for l in reversed(out.splitlines()) if l.strip()), "")
    return {"ok": False, "detail": (last[:160] or f"RC={p.returncode}"), "user": None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Watchdog auth SSH GitLab de karl (RM2376)")
    ap.add_argument("--json", action="store_true", help="sortie JSON (mode machine)")
    ap.add_argument("--timeout", type=int, default=10, help="timeout ssh (s)")
    args = ap.parse_args(argv)
    res = run_check(args.timeout)
    state = {
        "ok": bool(res["ok"]),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "detail": res["detail"],
        "user": res.get("user"),
        "method": "ssh " + GITLAB_ALIAS,
        "remediation": None if res["ok"] else REMEDIATION,
    }
    sp = state_path()
    try:
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"pm-gitlab-push-check : état non écrit ({exc})", file=sys.stderr)
    if args.json:
        print(json.dumps(state, ensure_ascii=False))
    else:
        print(("✓ " if state["ok"] else "✗ ") + "push GitLab (karl) : " + state["detail"])
        if not state["ok"]:
            print("  → " + REMEDIATION)
    return 0 if state["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
