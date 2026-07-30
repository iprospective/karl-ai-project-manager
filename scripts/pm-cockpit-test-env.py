#!/usr/bin/env python3
"""pm-cockpit-test-env — instance karl-agent de TEST pour un ticket cockpit (RM2356).

Le projet PM n'a pas de bloc `runtime:` : son env de session est un worktree de
code sans vhost — rien à « déployer » pour tester un ticket cockpit. Cet outil
lance une instance karl-agent DÉDIÉE sur le worktree de la branche du ticket :

    pm-cockpit-test-env.py create <rm_id>     # unités systemd user + test_url
    pm-cockpit-test-env.py teardown <rm_id>   # stop + vide test_url
    pm-cockpit-test-env.py list               # instances enregistrées

- port déterministe : 9900 + (rm_id % 90) ;
- deux unités systemd USER : karl-test-<id> (karl-agent du worktree, port local)
  et karl-test-<id>-bridge (socat lié sur l'IP du conteneur → accès direct
  http://dev.lxc:<port>/ depuis l'hôte, ttyd partagé déjà exposé) ;
- `test_url` posé/vidé dans le frontmatter + CF Redmine (set_test_url de
  pm-env-session — même mécanique que les envs applicatifs) ;
- registre : ~/.local/state/karl-cockpit-test/registry.json.

Capability-based : refuse un ticket dont le worktree ne contient pas
scripts/karl-agent.py (ce n'est pas un ticket cockpit-testable).
"""
import argparse
import pathlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

# réutilise find_workspace / load_repos / set_test_url de pm-env-session (RM2229)
_spec = importlib.util.spec_from_file_location("pm_env_session", HERE / "pm-env-session.py")
_pes = importlib.util.module_from_spec(_spec)
sys.modules["pm_env_session"] = _pes
_spec.loader.exec_module(_pes)

REGISTRY = Path.home() / ".local" / "state" / "karl-cockpit-test" / "registry.json"
PORT_BASE = 9900
PORT_SPAN = 90


def port_for(rm_id: int) -> int:
    """Port déterministe du ticket — stable entre create/teardown/répétitions."""
    return PORT_BASE + (rm_id % PORT_SPAN)


def prod_projects_base(ws) -> str:
    """Arbre `projects/clients` de l'instance DÉPLOYÉE (RM2452) : un worktree de
    code n'en a pas, les données PM vivant dans l'autre dépôt."""
    # Deux fausses pistes écartées : l'emplacement de l'OUTIL (lancé depuis une
    # branche, il vit dans un worktree de code, précisément dépourvu de
    # `projects/`) et le `.mmi-pm` du workspace (répertoire co-localisé —
    # `resolve()` ne traverse pas le bind mount). On lit donc le chemin de
    # l'instance RÉELLEMENT déployée, dans l'unité systemd qui la fait tourner.
    unit = pathlib.Path.home() / ".config/systemd/user/karl-agent.service"
    try:
        for line in unit.read_text(encoding="utf-8").splitlines():
            if line.startswith("ExecStart="):
                for tok in line.split():
                    if tok.endswith("/scripts/karl-agent.py"):
                        base = pathlib.Path(tok).parent.parent / "projects" / "clients"
                        return str(base) if base.is_dir() else ""
    except OSError:
        pass
    return ""


def prod_state_dir() -> Path:
    """État de session prod partagé (RM2385) — MIROIR du défaut `STATE_DIR`/
    `LOG_DIR` de karl-agent : `$XDG_STATE_HOME/karl-agent` sinon
    `~/.local/state/karl-agent`. C'est là que vivent keys/, sessions/, tasks/
    que l'instance de test doit lire pour résoudre les sessions live."""
    base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    return Path(base) / "karl-agent"


def container_ip() -> str:
    """IP sortante du conteneur (interface vers la passerelle) — point d'accès
    host-side (http://dev.lxc:<port>/ résout dessus)."""
    out = subprocess.run(["ip", "-4", "route", "get", "1.1.1.1"],
                         capture_output=True, text=True, timeout=5).stdout
    m = re.search(r"\bsrc (\d+\.\d+\.\d+\.\d+)", out)
    if not m:
        sys.exit("ERREUR : IP du conteneur introuvable (ip route get)")
    return m.group(1)


def _registry() -> dict:
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_registry(reg: dict) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(REGISTRY)


def resolve_worktree(ws: Path, rm_id: int) -> Path:
    repos = _pes.load_repos(ws)
    if len(repos) != 1:
        sys.exit(f"ERREUR : {len(repos)} repo(s) au manifeste — mono-repo requis")
    name = repos[0]["name"]
    # Résolution PAR BRANCHE (RM2394, partagée avec pm-env-session) : le worktree
    # du ticket peut être monté sous un nom discriminé par session (RM2034) ou
    # canonique — on le trouve par sa branche `<id>-*`, jamais par chemin deviné.
    # Repli sur le chemin canonique si un worktree y est mais sans branche `<id>-*`
    # (état atypique) — préserve le message d'erreur historique.
    bare = ws / "repos" / f"{name}.git"
    found = _pes.worktree_for_branch(bare, name, rm_id) if bare.is_dir() else None
    wt = found[0] if found else ws / "envs" / f"{name}-rm{rm_id}"
    if not wt.is_dir():
        sys.exit(f"ERreur : worktree absent : {wt}\n"
                 f"  → prendre le ticket (en_cours) crée l'env de session, ou pm-env-session create {rm_id}"
                 .replace("ERreur", "ERREUR"))
    if not (wt / "scripts" / "karl-agent.py").is_file():
        sys.exit("ERREUR : ce worktree ne contient pas scripts/karl-agent.py — "
                 "pas un ticket cockpit-testable (utiliser pm-env-session pour un env applicatif)")
    return wt


def run(cmd: list, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if check and r.returncode != 0:
        sys.exit(f"ERREUR : {' '.join(cmd)} → rc={r.returncode}\n{(r.stderr or r.stdout).strip()}")
    return r


def cmd_create(args):
    ws = _pes.find_workspace(Path(args.workspace).resolve() if args.workspace else Path.cwd())
    wt = resolve_worktree(ws, args.rmid)
    port = port_for(args.rmid)
    ip = container_ip()
    unit, bridge = f"karl-test-{args.rmid}", f"karl-test-{args.rmid}-bridge"
    url = f"http://dev.lxc:{port}/"
    print(f"workspace : {ws}\nworktree  : {wt}\nport      : {port} (ip {ip})")
    if args.dry_run:
        print(f"[dry-run] systemd-run --user {unit} + {bridge} ; test_url = {url}")
        return
    # idempotent : stop d'une éventuelle instance précédente du même ticket
    subprocess.run(["systemctl", "--user", "stop", unit, bridge],
                   capture_output=True, timeout=30)
    subprocess.run(["systemctl", "--user", "reset-failed", unit, bridge],
                   capture_output=True, timeout=30)
    # LOG_DIR isolé par instance (logs HTTP/pipe/pm-runs propres au test) MAIS
    # STATE_DIR pointé sur l'état de session PARTAGÉ de la prod (keys/sessions/
    # tasks) : sans ça l'instance de test ne résout aucune session live → /usage
    # et /outline vides (RM2385). karl-agent : STATE_DIR défaut = LOG_DIR, donc
    # on l'override explicitement ici vers le défaut prod.
    log_dir = REGISTRY.parent / f"logdir-{args.rmid}"
    shared_state = prod_state_dir()
    run(["systemd-run", "--user", f"--unit={unit}",
         f"--working-directory={wt}",
         f"--setenv=KARL_AGENT_PORT={port}",
         f"--setenv=KARL_AGENT_LOG_DIR={log_dir}",
         f"--setenv=KARL_AGENT_STATE_DIR={shared_state}",
         # RM2452 : l'arbre `projects/` n'existe pas dans un worktree de code —
         # sans lui, client/projet ne se résolvent pas et les jeux dérivés sont
         # vides. On pointe celui de l'instance déployée, en lecture seule.
         f"--setenv=KARL_AGENT_PROJECTS_BASE={prod_projects_base(ws)}",
         "/usr/bin/python3", "scripts/karl-agent.py"])
    run(["systemd-run", "--user", f"--unit={bridge}",
         "/usr/bin/socat", f"TCP-LISTEN:{port},bind={ip},fork,reuseaddr",
         f"TCP:127.0.0.1:{port}"])
    # sonde /health (l'auth peut répondre 401 : on veut juste « ça écoute »)
    ok = False
    for _ in range(20):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
            ok = True
            break
        except urllib.error.HTTPError:
            ok = True          # 401/4xx = serveur vivant
            break
        except OSError:
            continue
    if not ok:
        run(["systemctl", "--user", "stop", unit, bridge], check=False)
        sys.exit(f"ERREUR : l'instance ne répond pas sur 127.0.0.1:{port} — "
                 f"journalctl --user -u {unit}")
    _pes.set_test_url(ws, args.rmid, url, False)
    reg = _registry()
    reg[str(args.rmid)] = {"port": port, "worktree": str(wt), "url": url,
                           "units": [unit, bridge], "created": int(time.time())}
    _save_registry(reg)
    print(f"✓ instance cockpit de test RM{args.rmid} : {url} "
          f"(mêmes identifiants que le cockpit ; teardown : pm-cockpit-test-env.py teardown {args.rmid})")


def cmd_teardown(args):
    unit, bridge = f"karl-test-{args.rmid}", f"karl-test-{args.rmid}-bridge"
    reg = _registry()
    known = reg.pop(str(args.rmid), None)
    if args.if_exists and not known:
        # rien d'enregistré : silencieux (hook best-effort à la fermeture du ticket)
        return
    if args.dry_run:
        print(f"[dry-run] stop {unit} + {bridge} ; test_url vidé")
        return
    subprocess.run(["systemctl", "--user", "stop", unit, bridge],
                   capture_output=True, timeout=30)
    subprocess.run(["systemctl", "--user", "reset-failed", unit, bridge],
                   capture_output=True, timeout=30)
    ws = _pes.find_workspace(Path(args.workspace).resolve() if args.workspace else Path.cwd())
    _pes.set_test_url(ws, args.rmid, None, False)
    _save_registry(reg)
    print(f"✓ instance de test RM{args.rmid} démontée (test_url vidé)")


def cmd_list(args):
    reg = _registry()
    if not reg:
        print("aucune instance cockpit de test enregistrée")
        return
    for rm, e in sorted(reg.items(), key=lambda kv: int(kv[0])):
        print(f"RM{rm}  {e['url']}  ({e['worktree']})")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("create", help="lance l'instance de test du ticket")
    pc.add_argument("rmid", type=int)
    pc.add_argument("workspace", nargs="?")
    pc.add_argument("--dry-run", action="store_true")
    pc.set_defaults(fn=cmd_create)
    pt = sub.add_parser("teardown", help="stoppe l'instance + vide test_url")
    pt.add_argument("rmid", type=int)
    pt.add_argument("workspace", nargs="?")
    pt.add_argument("--if-exists", action="store_true",
                    help="silencieux si aucune instance enregistrée (hook fermeture)")
    pt.add_argument("--dry-run", action="store_true")
    pt.set_defaults(fn=cmd_teardown)
    pl = sub.add_parser("list", help="instances enregistrées")
    pl.set_defaults(fn=cmd_list)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
