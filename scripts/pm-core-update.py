#!/usr/bin/env python3
"""pm-core-update — met à jour le code déployé de l'instance PM et le re-verrouille (RM3033, porté de `bin/mmi-pm core update`).

Le checkout de l'instance (`.mmi-pm-core`) est ROOT-owned (verrou 3 couches, RM2032) : ce verbe est LE SEUL geste privilégié du
CLI. Lancé sans être root, il se ré-exécute lui-même par `sudo` (mot de passe demandé — barrière humaine §13a, jamais NOPASSWD),
sauf en `--dry-run`, qui prévisualise sans privilège. Enchaînement (inchangé depuis le bash) :
  1. agent SSH éphémère (RM2239) + multiplexing SSH (RM2069) : UNE saisie de passphrase pour fetch + pull + submodules ;
  2. `git pull --ff-only origin <branche>` + `submodule update --init --recursive` ;
  3. re-verrou par `scripts/core-lock lock` (SOURCE UNIQUE de la politique 3 couches) ;
  4. hooks PM du core lui-même (post-commit, pre-push, pre-commit — .git/hooks root-owned, RM2240) ;
  5. si `scripts/karl-agent.py` a changé : redémarrage du service USER karl-agent (RM2308 — KillMode=process, tmux intacts) ;
  6. co-déploiement de pm-env-helper (RM2358) et karl-vhost-render (RM2565) dans /usr/local/sbin s'ils diffèrent ;
  7c. déclencheur périodique de l'ordonnanceur posé s'il manque (RM3151, `pm-scheduler install-timer`,
     en tant que `KARL_USER`) — idempotent : sans changement, il n'écrit ni ne recharge rien ;
  7b. stores de session ramenés du HOME vers `var/` du core s'il en reste (RM2992, `pm-stores-migrate`, en tant que
     `KARL_USER`) — après le restart, pour que l'agent écrive déjà au nouveau chemin ; ne remplace jamais ;
  7. provisioning UTILISATEUR de l'instance (RM3054, user `KARL_USER` du .env) : hooks Claude Code manquants posés par
     `pm-claude-hooks-sync` (ajout seulement) et symlinks `~/.claude/skills/<nom>` → `<core>/skills/<nom>` pour les skills
     du core — un lien vers ailleurs ou un vrai dossier n'est jamais écrasé (⚠ manuel).
NB : ce verbe s'exécute depuis l'ANCIEN code — une évolution de ce fichier ne prend effet qu'au run suivant. Le re-exec sudo
passe par `<core>/bin/mmi-pm core update` : c'est le chemin que la règle sudoers autorise en root (deploy/mmi-pm.sudoers.example).
Usage : mmi-pm core-update [--dry-run]     (alias : mmi-pm core update, mmi-core update)
"""
import argparse
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent
HOOKS = (("post-commit", "pm-post-commit.py"), ("pre-push", "pm-pre-push"), ("pre-commit", "pm-pre-commit.py"))
DEPLOYS = (("tools/env-runtime/pm-env-helper.sh", "/usr/local/sbin/pm-env-helper", "RM2358"),
           ("deploy/karl-agent/karl-vhost-render.sh", "/usr/local/sbin/karl-vhost-render", "RM2565"))
# RM3033 : alias courts `mmi-<domaine> <verbe>` ≡ `mmi-pm <domaine>-<verbe>` — des liens vers le dispatcher, à côté de /usr/local/bin/mmi-pm
ALIAS_DOMAINS = ("core", "task", "env", "index", "session", "mr", "norms", "project", "client")
BIN_DIR = Path("/usr/local/bin")


def log(msg): print(f"mmi-pm core-update: {msg}")
def die(msg): sys.exit(f"mmi-pm core-update: {msg}")


def read_env(path: Path) -> dict:
    """KEY=VALUE d'un .env, quotes dépouillées, sans écraser l'environnement."""
    out = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1); out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def run(cmd, check=False, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if check and r.returncode != 0:
        die(f"`{' '.join(map(str, cmd))}` a échoué : {(r.stderr or r.stdout).strip()[:300]}")
    return r


def git(core_dir, *a, check=False, env=None):
    return run(["git", "-C", str(core_dir), *a], check=check, env=env)


def needs_agent_restart(changed_files) -> list:
    """Les fichiers Python de `scripts/` qui viennent de changer — donc ce qui impose un redémarrage.

    RM2308 posait la règle « seul le démon lui-même », au motif que « les pm-* sont relus à chaque
    appel ». C'est vrai des SCRIPTS `pm-*.py`, lancés en sous-processus. Ça ne l'est pas des MODULES
    `pm_*.py` : l'agent en importe au moins treize — `karl_api_routes`, `pm_log`, `pm_notify`,
    `pm_bus`, `pm_modules`, `pm_monitor`, `pm_secrets`… — dont plusieurs en import paresseux, au
    fil des fonctions. Le processus garde en mémoire la version importée au démarrage, et un module
    livré restait donc invisible (RM3178 : une route déclarée partout rendait « route inconnue »).

    Suivre la liste exacte des imports serait plus fin et plus fragile : un import ajouté demain
    rouvrirait le trou sans prévenir. Le compromis est franc — un redémarrage de trop coûte une
    reconnexion du cockpit, sessions tmux intactes (KillMode=process) ; un redémarrage manquant coûte
    un défaut invisible, et la confiance dans le déploiement.
    """
    return sorted(f.strip() for f in (changed_files or [])
                  if f.strip().startswith("scripts/") and f.strip().endswith(".py"))


def hooks_plan(core_dir: Path):
    """[(nom, source, action)] : `link` (poser/rafraîchir), `skip-missing` (source absente), `manual` (fichier non-symlink existant)."""
    hkdir = core_dir / ".git" / "hooks"; out = []
    for name, src_name in HOOKS:
        src = core_dir / "scripts" / src_name; dst = hkdir / name
        if not src.is_file():
            out.append((name, src, "skip-missing"))
        elif dst.exists() and not dst.is_symlink():
            out.append((name, src, "manual"))
        else:
            out.append((name, src, "link"))
    return out


def deploy_plan(core_dir: Path):
    """[(src, dst, ref, à_installer)] pour les binaires co-déployés hors repo."""
    out = []
    for rel, dst, ref in DEPLOYS:
        src = core_dir / rel
        if not src.is_file():
            continue
        same = Path(dst).is_file() and filecmp.cmp(str(src), dst, shallow=False)
        out.append((src, Path(dst), ref, not same))
    return out


def alias_plan(core_dir: Path, bin_dir: Path = BIN_DIR):
    """[(lien, cible, action)] : `link` (à poser/corriger), `ok`, `skip` (mmi-pm lui-même absent du bin — instance non installée)."""
    main_link = bin_dir / "mmi-pm"
    if not main_link.is_symlink():
        return [(bin_dir / f"mmi-{d}", None, "skip") for d in ALIAS_DOMAINS]
    target = Path(os.readlink(main_link))
    out = []
    for d in ALIAS_DOMAINS:
        link = bin_dir / f"mmi-{d}"
        if link.is_symlink() and Path(os.readlink(link)) == target:
            out.append((link, target, "ok"))
        elif link.exists() and not link.is_symlink():
            out.append((link, target, "manual"))
        else:
            out.append((link, target, "link"))
    return out


def ensure_safe_directory(core_dir: Path):
    r = run(["git", "config", "--global", "--get-all", "safe.directory"])
    if str(core_dir) not in (r.stdout or "").split("\n"):
        run(["git", "config", "--global", "--add", "safe.directory", str(core_dir)])


def with_ssh_session(core_dir: Path, work):
    """Agent SSH éphémère (RM2239) + multiplexing (RM2069) autour de `work(env)` : une seule passphrase pour tout le trajet."""
    env = dict(os.environ); agent_pid = None
    st = run(["ssh-add", "-l"]).returncode          # 0 = clés chargées ; 1 = agent vide ; ≥2 = pas d'agent
    if st == 1:
        subprocess.run(["ssh-add", "-t", "120"], check=False)
    elif st >= 2:
        r = run(["ssh-agent", "-s"])
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if line.startswith("SSH_AUTH_SOCK=") or line.startswith("SSH_AGENT_PID="):
                    k, v = line.split(";", 1)[0].split("=", 1); env[k] = v
            agent_pid = env.get("SSH_AGENT_PID")
            subprocess.run(["ssh-add", "-t", "120"], check=False, env=env)
    cmdir = tempfile.mkdtemp(prefix="mmi-pm-cm-")
    env["GIT_SSH_COMMAND"] = f"ssh -o ControlMaster=auto -o ControlPath={cmdir}/cm-%C -o ControlPersist=20s"
    host = (git(core_dir, "remote", "get-url", "origin").stdout.strip().split(":", 1)[0]) or ""
    try:
        return work(env)
    finally:
        if host:
            run(["ssh", "-o", f"ControlPath={cmdir}/cm-%C", "-O", "exit", host], env=env)
        shutil.rmtree(cmdir, ignore_errors=True)
        if agent_pid:
            run(["ssh-agent", "-k"], env=env)


# ── RM3054 : provisioning utilisateur (hooks Claude, skills) ─────────────────
def instance_user(core_dir: Path):
    """(login, uid, gid, home) de l'utilisateur de l'instance (`KARL_USER`), ou None."""
    ku = read_env(core_dir / ".env").get("KARL_USER") or ""
    if not ku:
        return None
    try:
        import pwd
        pw = pwd.getpwnam(ku)
    except KeyError:
        return None
    return ku, pw.pw_uid, pw.pw_gid, Path(pw.pw_dir)


def skills_plan(core_dir: Path, home: Path):
    """[(lien, cible, action)] — action : link (à poser) / ok (déjà le bon lien) / manual (occupé par autre chose)."""
    out = []
    sdir = core_dir / "skills"
    if not sdir.is_dir():
        return out
    for d in sorted(x for x in sdir.iterdir() if x.is_dir() and (x / "SKILL.md").is_file()):
        link = home / ".claude" / "skills" / d.name
        if link.is_symlink():
            try:
                same = link.resolve() == d.resolve()
            except OSError:
                same = False
            out.append((link, d, "ok" if same else "manual"))
        elif link.exists():
            out.append((link, d, "manual"))
        else:
            out.append((link, d, "link"))
    return out


def claude_hooks_missing(core_dir: Path, home: Path) -> bool:
    """Vrai si `pm-claude-hooks-sync --check` dit qu'un hook PM manque dans le settings.json de cet utilisateur."""
    r = run([sys.executable, str(core_dir / "scripts" / "pm-claude-hooks-sync.py"), "--check",
             "--settings", str(home / ".claude" / "settings.json"), "--pm-root", str(core_dir)])
    return r.returncode != 0


def sync_user_provisioning(core_dir: Path):
    """Étape 7 : hooks Claude + skills pour l'utilisateur de l'instance. Best-effort, journalisé, jamais bloquant."""
    who = instance_user(core_dir)
    if not who:
        log("⚠ provisioning utilisateur ignoré — KARL_USER inconnu dans .env (hooks Claude / skills à poser à la main : pm-claude-hooks-sync)"); return
    ku, uid, gid, home = who
    if claude_hooks_missing(core_dir, home):
        r = run(["runuser", "-u", ku, "--", "env", f"HOME={home}", "PATH=/usr/local/bin:/usr/bin:/bin",
                 sys.executable, str(core_dir / "scripts" / "pm-claude-hooks-sync.py"), "--pm-root", str(core_dir)])
        if r.returncode == 0:
            log(f"hooks Claude Code de {ku} synchronisés (pm-claude-hooks-sync, ajout seulement)")
        else:
            log(f"⚠ pm-claude-hooks-sync a échoué pour {ku} : {(r.stdout or r.stderr).strip()[-200:]} — relancer à la main")
    else:
        log(f"hooks Claude Code de {ku} : déjà complets")
    posed, manual = [], []
    for link, target, action in skills_plan(core_dir, home):
        if action == "link":
            try:
                link.parent.mkdir(parents=True, exist_ok=True)
                for d in (link.parent, link.parent.parent):
                    if d.stat().st_uid != uid:
                        os.chown(d, uid, gid)
                link.symlink_to(target); os.lchown(link, uid, gid); posed.append(link.name)
            except OSError as e:
                manual.append(f"{link.name} ({e})")
        elif action == "manual":
            manual.append(link.name)
    if posed:
        log(f"skills liés dans {home}/.claude/skills : " + ", ".join(posed))
    if manual:
        log("⚠ skills NON liés (occupés par un dossier ou un autre lien) : " + ", ".join(manual))


def restart_karl_agent(core_dir: Path, motifs=None):
    """`motifs` : les fichiers qui l'imposent. Les NOMMER évite la question « pourquoi a-t-il
    redémarré ? » — et, quand il ne redémarre pas, de chercher ailleurs pendant une heure."""
    quoi = ", ".join(motifs[:4]) + ("…" if motifs and len(motifs) > 4 else "") if motifs else "karl-agent.py"
    ku = read_env(core_dir / ".env").get("KARL_USER") or ""
    uid = run(["id", "-u", ku]).stdout.strip() if ku else ""
    if not (ku and uid):
        log(f"⚠ {quoi} modifié — KARL_USER inconnu dans .env ; si cette instance fait tourner l'agent : systemctl --user restart karl-agent"); return
    base = ["runuser", "-u", ku, "--", "env", f"XDG_RUNTIME_DIR=/run/user/{uid}", "systemctl", "--user"]
    if run(base + ["is-active", "--quiet", "karl-agent.service"]).returncode != 0:
        log(f"⚠ {quoi} modifié — service karl-agent inactif/introuvable ici ; si cette instance le fait tourner : systemctl --user restart karl-agent (user {ku})"); return
    if run(base + ["restart", "karl-agent.service"]).returncode == 0:
        log(f"{quoi} modifié → karl-agent.service redémarré (KillMode=process : sessions tmux intactes)")
    else:
        log(f"⚠ {quoi} modifié mais restart ÉCHOUÉ — l'agent sert l'ancien code ; relancer en tant que {ku} : systemctl --user restart karl-agent")


def migrate_stores(core_dir: Path, dry: bool):
    """Étape 8 (RM2992) : ramène les stores de session du HOME vers `var/`, en tant que
    l'utilisateur de l'instance.

    En root, ce déplacement créerait des dossiers root-owned dans un `var/` que les agents doivent
    pouvoir écrire — d'où `runuser`, comme pour le provisioning. Le script ne remplace jamais un
    fichier déjà à destination : le lancer APRÈS le redémarrage de karl-agent (qui écrit alors déjà
    au nouveau chemin) ramasse ce que l'ancien code avait laissé derrière, sans course."""
    who = instance_user(core_dir)
    script = core_dir / "scripts" / "pm-stores-migrate.py"
    if not script.is_file():
        return
    if not who:
        log("⚠ migration des stores ignorée — KARL_USER inconnu dans .env (à lancer à la main : mmi-pm stores-migrate)"); return
    ku, _uid, _gid, home = who
    cmd = ["runuser", "-u", ku, "--", "env", f"HOME={home}", f"PM_CORE_DIR={core_dir}",
           "PATH=/usr/local/bin:/usr/bin:/bin", sys.executable, str(script)]
    if dry:
        cmd.append("--dry-run")
    r = run(cmd)
    for line in (r.stdout or "").splitlines():
        if line.strip():
            log(line.strip())
    if r.returncode != 0:
        log(f"⚠ migration des stores en échec : {(r.stderr or '').strip()[-200:]} — relancer : mmi-pm stores-migrate")


def install_scheduler_timer(core_dir: Path, dry: bool):
    """Étape 9 (RM3151) : pose le déclencheur périodique de l'ordonnanceur, en tant que
    l'utilisateur de l'instance.

    Sans lui, le registre `jobs.reference.yml` entier dort et rien ne le dit. En root, un timer
    *user* serait posé pour root — c'est-à-dire nulle part : d'où `runuser`, comme le provisioning.
    L'installation est idempotente : relancée sans changement, elle n'écrit rien et ne recharge rien,
    ce qui permet de l'appeler à chaque mise à jour sans se demander si c'est prudent."""
    who = instance_user(core_dir)
    script = core_dir / "scripts" / "pm-scheduler.py"
    if not script.is_file():
        return
    if not who:
        log("⚠ timer de l'ordonnanceur ignoré — KARL_USER inconnu dans .env (à poser à la main : mmi-pm scheduler install-timer)"); return
    ku, uid, _gid, home = who
    cmd = ["runuser", "-u", ku, "--", "env", f"HOME={home}", f"PM_CORE_DIR={core_dir}",
           f"XDG_RUNTIME_DIR=/run/user/{uid}", "PATH=/usr/local/bin:/usr/bin:/bin",
           sys.executable, str(script), "install-timer"]
    if dry:
        cmd.append("--dry-run")
    r = run(cmd)
    for line in (r.stdout or "").splitlines():
        if line.strip():
            log(line.strip())
    if r.returncode != 0:
        log(f"⚠ timer de l'ordonnanceur : {(r.stderr or '').strip()[-200:]} — relancer : mmi-pm scheduler install-timer")


def update(core_dir: Path, dry: bool) -> int:
    if not (core_dir / ".git").exists():
        die(f"{core_dir} n'est pas un dépôt git")
    branch = git(core_dir, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"
    old = git(core_dir, "rev-parse", "--short", "HEAD").stdout.strip() or "?"
    if dry:
        log(f"[dry] git pull --ff-only origin {branch} ; submodule update ; scripts/core-lock lock (re-verrou 3 couches) ; "
            "restart karl-agent si scripts/karl-agent.py modifié (RM2308) ; co-déploiement helper/renderer si différents")
        for name, src, action in hooks_plan(core_dir):
            log(f"[dry] hook {name} : {action} ({src.name})")
        for src, dst, ref, todo in deploy_plan(core_dir):
            log(f"[dry] {dst} : {'à installer' if todo else 'à jour'} ({ref})")
        for link, target, action in alias_plan(core_dir):
            log(f"[dry] alias {link.name} : {action}" + (f" → {target}" if target else ""))
        who = instance_user(core_dir)
        if who:
            ku, _, _, home = who
            log(f"[dry] hooks Claude de {ku} : {'à compléter (pm-claude-hooks-sync)' if claude_hooks_missing(core_dir, home) else 'complets'}")
            for link, target, action in skills_plan(core_dir, home):
                if action != "ok":
                    log(f"[dry] skill {link.name} : {action}")
        else:
            log("[dry] provisioning utilisateur : KARL_USER inconnu dans .env — ignoré")
        return 0
    if os.geteuid() != 0:
        die("doit tourner en root (sudo) — le code de l'instance est root-owned")
    ensure_safe_directory(core_dir)

    def pull(env):
        git(core_dir, "fetch", "--quiet", "origin", check=True, env=env)
        git(core_dir, "pull", "--ff-only", "origin", branch, check=True, env=env)
        git(core_dir, "submodule", "update", "--init", "--recursive", env=env)
    with_ssh_session(core_dir, pull)
    new = git(core_dir, "rev-parse", "--short", "HEAD").stdout.strip()
    lock = core_dir / "scripts" / "core-lock"
    if not os.access(lock, os.X_OK):
        die("scripts/core-lock absent/inexécutable")
    run([str(lock), "lock", str(core_dir)], check=True)
    hkdir = core_dir / ".git" / "hooks"; hkdir.mkdir(parents=True, exist_ok=True)
    for name, src, action in hooks_plan(core_dir):
        if action == "manual":
            log(f"hook {name} du core : fichier existant non-symlink → fusion manuelle")
        elif action == "link":
            dst = hkdir / name
            if dst.is_symlink(): dst.unlink()
            dst.symlink_to(src)
    log("hooks PM du core posés/rafraîchis (post-commit, pre-push, pre-commit)")
    if old not in ("?", new):
        changed = git(core_dir, "diff", "--name-only", old, new).stdout.splitlines()
        motifs = needs_agent_restart(changed)
        if motifs:
            restart_karl_agent(core_dir, motifs)
    migrate_stores(core_dir, dry)
    install_scheduler_timer(core_dir, dry)
    for src, dst, ref, todo in deploy_plan(core_dir):
        if todo:
            run(["install", "-o", "root", "-g", "root", "-m", "755", str(src), str(dst)], check=True)
            log(f"{dst.name} déployé → {dst} (source {src.relative_to(core_dir)}, {ref})")
    posed = []
    for link, target, action in alias_plan(core_dir):
        if action == "link":
            if link.is_symlink(): link.unlink()
            link.symlink_to(target); posed.append(link.name)
        elif action == "manual":
            log(f"⚠ {link} existe et n'est pas un lien — alias non posé")
    if posed:
        log("alias posés dans /usr/local/bin : " + ", ".join(posed) + " (mmi-<domaine> <verbe> ≡ mmi-pm <domaine>-<verbe>)")
    try:
        sync_user_provisioning(core_dir)           # RM3054 : jamais bloquant
    except Exception as e:                         # noqa: BLE001
        log(f"⚠ provisioning utilisateur (hooks Claude / skills) en échec : {e}")
    log(f"outil {old} -> {new} ({branch}) ; re-verrouillé via core-lock (politique 3 couches)")
    log("NB : pointeur de submodule du repo env NON committé automatiquement (geste séparé).")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="prévisualise sans sudo ni écriture")
    ap.add_argument("--core-dir", default=None, help=argparse.SUPPRESS)   # tests
    a = ap.parse_args(argv)
    core_dir = Path(a.core_dir).resolve() if a.core_dir else CORE_DIR
    if not a.dry_run and os.geteuid() != 0:
        # Le re-exec passe par `<core>/bin/mmi-pm core update` : c'est LE chemin que la règle sudoers autorise en root
        # (deploy/mmi-pm.sudoers.example, ligne 2 — `bin/mmi-pm core update*`). Un `sudo python3 …` direct serait refusé
        # sur une instance dont le compte n'a que ces droits. bin/mmi-pm relaie au dispatcher → ce script, en root.
        log("opération privilégiée (code root-owned) → re-exec sudo (mot de passe requis)")
        entry = core_dir / "bin" / "mmi-pm"
        extra = [x for x in (argv if argv is not None else sys.argv[1:]) if x not in ("--dry-run",)]
        os.execvp("sudo", ["sudo", str(entry), "core", "update", *extra])
    return update(core_dir, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
