#!/usr/bin/env python3
"""pm-cockpit-test-env — instance karl-agent de TEST pour un ticket cockpit (RM2356).

Le projet PM n'a pas de bloc `runtime:` : son env de session est un worktree de
code sans vhost — rien à « déployer » pour tester un ticket cockpit. Cet outil
lance une instance karl-agent DÉDIÉE sur le worktree de la branche du ticket :

    pm-cockpit-test-env.py create <rm_id>     # unités systemd user + test_url
    pm-cockpit-test-env.py teardown <rm_id>   # stop + vide test_url
    pm-cockpit-test-env.py list               # instances enregistrées

- port déterministe : 9900 + (rm_id % 90) ;
- une unité systemd USER karl-test-<id> (karl-agent du worktree, en loopback) ;
- exposition HTTPS via un vhost Apache karl COMPLET (RM2565) : `mmi-pm env vhost
  karl-add <repo>-rm<id> <port>` → https://<repo>-rm<id>.lxc/ avec la MÊME conf
  que le déploiement de prod (redirect 80→443, terminal wss /ttyd/ws, contexte
  sécurisé requis par le micro/Whisper). Le ttyd de prod est partagé (pas de
  listener :7681 dédié). Le privilège root vit dans pm-env-helper (NOPASSWD),
  jamais de sudo direct ici ;
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

# Façade CLI vers les verbes vhost du helper privilégié (RM2372) — même binaire
# que celui consommé par pm-env-expose. Le privilège root vit dans pm-env-helper
# (NOPASSWD) ; cet outil ne fait jamais de sudo direct sur Apache.
MMI_PM = HERE.parent / "bin" / "mmi-pm"


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


def core_dir() -> str:
    """Racine du core PM — celle qui porte le `.env` (secrets + chemins).

    Un worktree de code n'en a PAS : `PMConfig.load()` y échoue (« aucun .env
    trouvé ») et TOUTE commande du catalogue ⚙ meurt en rc=1 dans une instance de
    test (constaté sur `conso-report` comme sur la relève mail, RM2668). Le repli
    `PM_CORE_DIR` de `pm_paths` existe pour exactement ce cas : on le transmet.
    """
    env = os.environ.get("PM_CORE_DIR")
    if env:
        return env
    # Repli : le core déployé, lu dans l'unité systemd de l'instance prod — même
    # source de vérité que `prod_projects_base` (pas de chemin en dur : une autre
    # instance de la fédération n'a pas la même arborescence).
    unit = Path.home() / ".config/systemd/user/karl-agent.service"
    try:
        for line in unit.read_text(encoding="utf-8").splitlines():
            if line.startswith("WorkingDirectory="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return str(HERE.parent)


def prod_state_dir() -> Path:
    """État de session prod partagé (RM2385) — MIROIR du défaut `STATE_DIR`/
    `LOG_DIR` de karl-agent : `$XDG_STATE_HOME/karl-agent` sinon
    `~/.local/state/karl-agent`. C'est là que vivent keys/, sessions/, tasks/
    que l'instance de test doit lire pour résoudre les sessions live."""
    base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    return Path(base) / "karl-agent"


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


def vhost_name(ws: Path, rm_id: int) -> str:
    """Nom du vhost de test : <repo>-rm<id> (satisfait vname_ok du helper). Le
    mono-repo est déjà garanti par resolve_worktree ; on relit juste son nom."""
    return f"{_pes.load_repos(ws)[0]['name']}-rm{rm_id}"


def mmi_pm_vhost(*args: str, check=True) -> subprocess.CompletedProcess:
    """Applique une opération vhost via `mmi-pm env vhost …` (→ pm-env-helper
    NOPASSWD, RM2372). Surface le stdout du helper (ligne de confirmation)."""
    r = run([str(MMI_PM), "env", "vhost", *args], check=check)
    if r.stdout.strip():
        print(r.stdout.strip())
    return r


def cmd_create(args):
    ws = _pes.find_workspace(Path(args.workspace).resolve() if args.workspace else Path.cwd())
    wt = resolve_worktree(ws, args.rmid)
    name = vhost_name(ws, args.rmid)
    port = port_for(args.rmid)
    unit = f"karl-test-{args.rmid}"
    url = f"https://{name}.lxc/"
    print(f"workspace : {ws}\nworktree  : {wt}\nvhost     : {name}.lxc → 127.0.0.1:{port}")
    if args.dry_run:
        print(f"[dry-run] systemd-run --user {unit} ; "
              f"mmi-pm env vhost karl-add {name} {port} ; test_url = {url}")
        return
    # idempotent : stop d'une éventuelle instance précédente du même ticket
    subprocess.run(["systemctl", "--user", "stop", unit],
                   capture_output=True, timeout=30)
    subprocess.run(["systemctl", "--user", "reset-failed", unit],
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
         # RM2668 : sans PM_CORE_DIR, un worktree de code n'a pas de `.env` et
         # TOUTE commande du catalogue ⚙ meurt (« aucun .env trouvé »).
         f"--setenv=PM_CORE_DIR={core_dir()}",
         "/usr/bin/python3", "scripts/karl-agent.py"])
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
        run(["systemctl", "--user", "stop", unit], check=False)
        sys.exit(f"ERREUR : l'instance ne répond pas sur 127.0.0.1:{port} — "
                 f"journalctl --user -u {unit}")
    # Exposition HTTPS (RM2565) : vhost karl COMPLET (terminal wss + micro), même
    # conf que la prod, via le helper privilégié. Si l'application échoue (ex.
    # renderer pas encore co-déployé : `mmi-pm core update`), on stoppe l'instance
    # pour ne pas laisser un karl-agent orphelin sans exposition.
    try:
        mmi_pm_vhost("karl-add", name, str(port))
    except SystemExit:
        run(["systemctl", "--user", "stop", unit], check=False)
        raise
    _pes.set_test_url(ws, args.rmid, url, False)
    reg = _registry()
    reg[str(args.rmid)] = {"port": port, "worktree": str(wt), "url": url,
                           "vhost": name, "unit": unit, "created": int(time.time())}
    _save_registry(reg)
    print(f"✓ instance cockpit de test RM{args.rmid} : {url}\n"
          f"  (mêmes identifiants que le cockpit ; cert auto-signé à accepter une "
          f"fois ; teardown : pm-cockpit-test-env.py teardown {args.rmid})")


def cmd_teardown(args):
    unit = f"karl-test-{args.rmid}"
    # `bridge` : legacy (exposition socat avant RM2565) — stoppé aussi pour
    # nettoyer une instance créée par l'ancien flux.
    bridge = f"{unit}-bridge"
    reg = _registry()
    known = reg.pop(str(args.rmid), None)
    if args.if_exists and not known:
        # rien d'enregistré : silencieux (hook best-effort à la fermeture du ticket)
        return
    ws = _pes.find_workspace(Path(args.workspace).resolve() if args.workspace else Path.cwd())
    vh = (known or {}).get("vhost") or vhost_name(ws, args.rmid)
    if args.dry_run:
        print(f"[dry-run] stop {unit} (+ {bridge} legacy) ; "
              f"mmi-pm env vhost remove {vh} ; test_url vidé")
        return
    subprocess.run(["systemctl", "--user", "stop", unit, bridge],
                   capture_output=True, timeout=30)
    subprocess.run(["systemctl", "--user", "reset-failed", unit, bridge],
                   capture_output=True, timeout=30)
    # Retrait du vhost (best-effort, idempotent côté helper : « absent » = no-op).
    mmi_pm_vhost("remove", vh, check=False)
    _pes.set_test_url(ws, args.rmid, None, False)
    _save_registry(reg)
    print(f"✓ instance de test RM{args.rmid} démontée (vhost retiré, test_url vidé)")


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
