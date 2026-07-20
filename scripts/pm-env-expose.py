#!/usr/bin/env python3
"""pm-env-expose — expose un env de test via un hostname normalisé (RM2358).

Formalise la convention de cette instance : tout env de test est joignable en
    http://<project>-rm<id>[-s<seq>].lxc/
via un vhost Apache du conteneur de dev. Deux cas :
  - env PHP (DocumentRoot) : déjà couvert par pm-env-session + vhost-add ;
  - env porté par un DAEMON HTTP en loopback (karl-agent, serveur de dev
    non-PHP) : ce script crée le vhost **reverse proxy** vers son port, via le
    verbe `vhost-proxy-add` de pm-env-helper (privilégié, sudo NOPASSWD).

Le hostname est dérivé de l'env du ticket (jamais saisi à la main) :
  <repo>-rm<id>            env canonique  envs/<repo>-rm<id>   (pm-env-session)
  <repo>-rm<id>-s<seq>     worktree de session …-s<seq>        (pm-branch-start)

Usage :
    pm-env-expose.py expose  <rmid> --port 9999   [--workspace WS] [--dry-run]
    pm-env-expose.py unexpose <rmid>              [--workspace WS] [--dry-run]
    pm-env-expose.py list                         [--workspace WS]

Effets d'expose : vhost proxy + registre var/env-expose.json + frontmatter
`test_url` + CF Redmine 14 « Environnement de test » + entrée .log.md.
`unexpose` défait tout (test_url/CF nettoyés seulement s'ils pointent encore
vers ce hostname). Idempotent dans les deux sens.

NB : le script n'ALLUME pas le daemon de l'env — il publie le port sur lequel
celui-ci écoute (127.0.0.1:<port>). La résolution DNS <name>.lxc est portée par
la conf dnsmasq côté hôte (déjà en place pour *-rm<id>.lxc sur cette instance).
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import yaml  # noqa: E402
from pm_paths import PMConfig  # noqa: E402

NAME_RE = re.compile(r"^[a-z0-9_.-]+-rm[0-9]+(-s[0-9]+)?$")
PORT_MIN, PORT_MAX = 1024, 65535


def die(msg: str) -> None:
    sys.exit(f"pm-env-expose: {msg}")


def load_env_runtime() -> dict:
    cfg = {}
    for name in ("pm.config.yml", "pm.config.local.yml"):
        p = SCRIPTS.parent / name
        if p.is_file():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            cfg.update(data.get("env_runtime") or {})
    return cfg


def find_task_file(cfg: PMConfig, rmid: int) -> Path:
    hits = sorted(cfg.projects_root.glob(f"clients/*/projects/*/tasks/RM{rmid}_*.md"))
    hits = [h for h in hits if not h.name.endswith(".log.md")]
    if not hits:
        die(f"tâche RM{rmid} introuvable sous {cfg.projects_root}")
    if len(hits) > 1:
        die(f"RM{rmid} ambigu : {[str(h) for h in hits]}")
    return hits[0]


def read_frontmatter(task_file: Path) -> dict:
    text = task_file.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?\n)---\n", text, re.S)
    m or die(f"frontmatter introuvable : {task_file}")
    return yaml.safe_load(m.group(1)) or {}


def resolve_workspace(task_file: Path, override: str | None) -> Path:
    if override:
        ws = Path(override).resolve()
        (ws / ".mmi-pm").exists() or die(f"pas de .mmi-pm dans {ws}")
        return ws
    link = task_file.parent.parent / "workspace"
    if link.is_symlink() or link.is_dir():
        return Path(link).resolve()
    die(f"symlink workspace absent dans {task_file.parent.parent} — passe --workspace")


def resolve_env(ws: Path, fm: dict, rmid: int) -> Path:
    wt = ((fm.get("git") or {}).get("worktree") or "").strip()
    if wt:
        p = Path(wt)
        if p.is_dir() and p.parent == ws / "envs":
            return p
    for cand in sorted((ws / "envs").glob(f"*-rm{rmid}")) + \
            sorted((ws / "envs").glob(f"*-{rmid}-s*")):
        if cand.is_dir():
            return cand
    die(f"aucun env trouvé pour RM{rmid} sous {ws}/envs "
        "(pm-env-session create d'abord ?)")


def derive_name(env_dir: Path, rmid: int) -> str:
    """Hostname canonique depuis le dossier d'env — jamais saisi à la main."""
    base = env_dir.name
    m = re.search(r"-s([0-9]+)$", base)
    seq = f"-s{m.group(1)}" if m else ""
    # repo = dossier d'env débarrassé des suffixes -rm<id>/-dev-<id>-s<n>
    repo = re.sub(rf"(-dev)?-(rm)?{rmid}(-s[0-9]+)?$", "", base)
    if not repo or repo == base:
        die(f"dossier d'env hors convention (attendu <repo>-rm{rmid}[…]) : {base}")
    name = f"{repo}-rm{rmid}{seq}"
    NAME_RE.match(name) or die(f"hostname dérivé invalide : {name}")
    return name


def registry_path(ws: Path) -> Path:
    return ws / "var" / "env-expose.json"


def load_registry(ws: Path) -> dict:
    try:
        return json.loads(registry_path(ws).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_registry(ws: Path, reg: dict) -> None:
    p = registry_path(ws)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


MMI_PM = SCRIPTS.parent / "bin" / "mmi-pm"


def run_vhost(args: list, dry: bool) -> None:
    """Verbes vhost du helper, routés par la CLI unique `mmi-pm env vhost`
    (RM2372). mmi-pm appelle en interne pm-env-helper (NOPASSWD) — pas de
    mot de passe, surface de confiance inchangée. `args` = ["vhost-<verbe>", …]
    (forme helper) ; on dérive le sous-verbe mmi-pm en retirant le préfixe."""
    helper_verb = args[0]
    verb = helper_verb[len("vhost-"):] if helper_verb.startswith("vhost-") else helper_verb
    cmd = [str(MMI_PM), "env", "vhost", verb, *args[1:]]
    if dry:
        cmd.insert(1, "--dry-run")
        print(f"  [dry-run] {' '.join(cmd)}")
        return
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        if "verbe inconnu" in err and "vhost" in err:
            die(f"{err}\n  → le `mmi-pm` déployé est antérieur à RM2372, ou le "
                "helper à RM2358 ; déployer :\n    sudo mmi-pm core update  (×2 : "
                "le 1er pose le nouveau bin, le 2e le helper)")
        die(f"mmi-pm env vhost a échoué : {err}")


def update_test_url(task_file: Path, url: str | None, expect: str | None) -> bool:
    """Pose (url) ou nettoie (None) test_url, avec verrou optimiste simple.
    En mode nettoyage, ne touche que si la valeur actuelle commence par expect."""
    text = task_file.read_text(encoding="utf-8")
    m = re.search(r"^test_url: (.*)$", text, re.M)
    if not m:
        return False
    if url is None:
        if not expect or not m.group(1).strip().startswith(expect):
            return False
        new_line = "test_url: null"
    else:
        new_line = f"test_url: {url}"
    if m.group(0) == new_line:
        return False
    text = text[:m.start()] + new_line + text[m.end():]
    stamp = time.strftime("%Y-%m-%dT%H:%M")
    text = re.sub(r"^updated: .*$", f"updated: {stamp}", text, count=1, flags=re.M)
    task_file.write_text(text, encoding="utf-8")
    return True


def push_cf14(rmid: int, value: str, dry: bool) -> None:
    if dry:
        print(f"  [dry-run] CF 14 « Environnement de test » ← {value!r}")
        return
    try:
        import redmine_utils as ru
        ru.update_issue_fields(rmid, custom_fields=[{"id": 14, "value": value}])
        print(f"✓ CF 14 « Environnement de test » : {value or '(vidé)'}")
    except Exception as e:  # noqa: BLE001 — Redmine best-effort, le local fait foi
        print(f"  ⚠ CF 14 non poussé ({e}) — poser à la main si besoin", file=sys.stderr)


def append_log(task_file: Path, rmid: int, msg: str, dry: bool) -> None:
    if dry:
        return
    log = task_file.with_name(task_file.name[:-3] + ".log.md")
    stamp = time.strftime("%Y-%m-%dT%H:%M")
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n## {stamp} — pm-env-expose\n{msg}\n")


def pick_port(reg: dict, asked: int | None) -> int:
    if asked is not None:
        (PORT_MIN <= asked <= PORT_MAX) or die(f"port hors bornes : {asked}")
        return asked
    used = {e["port"] for e in reg.values()}
    for p in range(21000, 22000):
        if p not in used:
            return p
    die("aucun port libre dans le pool 21000-21999")


def cmd_expose(a) -> None:
    cfg = PMConfig.load()
    task_file = find_task_file(cfg, a.rmid)
    fm = read_frontmatter(task_file)
    ws = resolve_workspace(task_file, a.workspace)
    env_dir = resolve_env(ws, fm, a.rmid)
    name = derive_name(env_dir, a.rmid)
    reg = load_registry(ws)
    prev = reg.get(str(a.rmid))
    port = a.port if a.port is not None else (prev or {}).get("port")
    port = pick_port(reg, port)
    url = f"http://{name}.lxc/"
    print(f"RM{a.rmid} : env {env_dir.name} → {url} (proxy 127.0.0.1:{port})")
    run_vhost(["vhost-proxy-add", name, str(port)], a.dry_run)
    if not a.dry_run:
        reg[str(a.rmid)] = {"name": name, "port": port, "env_dir": str(env_dir),
                            "created": (prev or {}).get("created")
                            or time.strftime("%Y-%m-%dT%H:%M:%S")}
        save_registry(ws, reg)
        if update_test_url(task_file, url, None):
            print(f"✓ frontmatter test_url : {url}")
    push_cf14(a.rmid, url, a.dry_run)
    append_log(task_file, a.rmid,
               f"Env exposé : {url} → 127.0.0.1:{port} (vhost proxy, env {env_dir.name}).",
               a.dry_run)
    print(f"→ vérif locale : curl -H 'Host: {name}.lxc' http://127.0.0.1/  "
          f"(le daemon doit écouter sur 127.0.0.1:{port})")


def cmd_unexpose(a) -> None:
    cfg = PMConfig.load()
    task_file = find_task_file(cfg, a.rmid)
    ws = resolve_workspace(task_file, a.workspace)
    reg = load_registry(ws)
    entry = reg.get(str(a.rmid))
    if not entry:
        # rien au registre : tenter quand même le nom canonique (idempotence)
        fm = read_frontmatter(task_file)
        env_dir = resolve_env(ws, fm, a.rmid)
        entry = {"name": derive_name(env_dir, a.rmid)}
    name = entry["name"]
    print(f"RM{a.rmid} : retrait de {name}.lxc")
    run_vhost(["vhost-remove", name], a.dry_run)
    if not a.dry_run:
        if reg.pop(str(a.rmid), None):
            save_registry(ws, reg)
        if update_test_url(task_file, None, f"http://{name}.lxc"):
            print("✓ frontmatter test_url nettoyé")
    push_cf14(a.rmid, "", a.dry_run)
    append_log(task_file, a.rmid, f"Env dé-exposé : vhost {name}.lxc retiré.", a.dry_run)


def cmd_list(a) -> None:
    if a.workspace:
        ws = Path(a.workspace).resolve()
    else:
        ws = Path.cwd()
        while not (ws / ".mmi-pm").exists():
            if ws.parent == ws:
                die("aucun .mmi-pm en remontant depuis cwd — passe --workspace")
            ws = ws.parent
    reg = load_registry(ws)
    if not reg:
        print("(aucun env exposé au registre)")
        return
    for rmid, e in sorted(reg.items(), key=lambda kv: int(kv[0])):
        print(f"RM{rmid:>6}  http://{e['name']}.lxc/  → 127.0.0.1:{e['port']}  ({e['env_dir']})")


def main() -> None:
    ap = argparse.ArgumentParser(description="expose un env de test en <project>-rm<id>[-s<seq>].lxc")
    sub = ap.add_subparsers(dest="verb", required=True)
    for verb, fn in (("expose", cmd_expose), ("unexpose", cmd_unexpose)):
        s = sub.add_parser(verb)
        s.add_argument("rmid", type=int)
        s.add_argument("--port", type=int, default=None,
                       help="port loopback du daemon (défaut : registre, sinon pool 21000+)")
        s.add_argument("--workspace", default=None)
        s.add_argument("--dry-run", action="store_true")
        s.set_defaults(fn=fn)
    s = sub.add_parser("list")
    s.add_argument("--workspace", default=None)
    s.set_defaults(fn=cmd_list)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
