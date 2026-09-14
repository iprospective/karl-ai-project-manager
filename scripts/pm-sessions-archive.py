#!/usr/bin/env python3
"""pm-sessions-archive — archive les sessions Claude dans leur dépôt git (RM2997).

Pourquoi cet outil existe : le 2026-06-23 à 03:17, un git interrompu a laissé un
`.git/index.lock` dans `~/.claude/projects`. L'archivage — un geste MANUEL — a
échoué dessus pendant 75 jours, **sans que rien ne le signale**. Pendant ce
temps, la rétention par défaut de Claude Code (`cleanupPeriodDays`, 30 jours) a
effacé 42 transcripts définitivement, laissant 70 tickets ouverts sans la
réflexion qui les portait.

Les deux leçons sont dans le code :

  1. **un commit local suffit à immuniser** — git garde le blob même quand
     Claude Code efface le fichier. Le push met hors machine, mais la protection
     commence au commit ;
  2. **aucune suppression n'est consignée** : si un transcript a déjà été
     effacé, son blob doit rester atteignable dans l'historique. On n'ajoute
     jamais que ce qui existe.

Et la troisième, qui n'est pas dans le code mais dans le timer : ce qui n'est pas
surveillé ne tourne pas. `--check` est fait pour être appelé par un contrôle
d'environnement, pas seulement par un humain inquiet.

Usage :
    pm-sessions-archive.py                 # commit + push si nécessaire
    pm-sessions-archive.py --check         # ne modifie rien ; sort 1 si trop vieux/cassé
    pm-sessions-archive.py --no-push       # commit local seul (immunise déjà)
    pm-sessions-archive.py --dry-run
    pm-sessions-archive.py --install-timer # timer systemd --user, horaire
"""
import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import pm_stores  # RM3085 : stores de session résolus une seule fois

STORE = Path(os.environ.get("PM_SESSIONS_ARCHIVE_REPO")
             or (os.environ.get("KARL_AGENT_CLAUDE_STORES") or "").split(":")[0]
             or "~/.claude/projects").expanduser()
HISTORY = Path(os.environ.get("PM_CLAUDE_HISTORY") or "~/.claude/history.jsonl").expanduser()
WORKLOGS = pm_stores.worklog_dir()
LOG = Path(os.environ.get("PM_SESSIONS_ARCHIVE_LOG")
           or "~/.local/log/pm-sessions-archive.log").expanduser()

# Un verrou plus vieux que ça, sans git vivant dans le dépôt, est un cadavre.
# 15 minutes : très au-dessus d'un `git add` sur 400 Mo, très en-dessous du
# temps qu'il a fallu pour s'apercevoir des 75 jours.
LOCK_STALE_S = 15 * 60
MAX_AGE_DAYS = 2          # seuil de --check : l'archivage est horaire

# `~/.claude/projects/<slug>/<sid>.jsonl` : Claude Code énumère les transcripts
# par un glob de profondeur EXACTEMENT deux. Ce qu'on archive en plus doit donc
# vivre plus profond, sinon le moteur prendrait `history.jsonl` pour une
# conversation et `_meta` pour un projet.
EXTRA_DIR = "_meta"


def log(msg, echo=True):
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    if echo:
        print(msg)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def git(repo, *args, check=False):
    p = subprocess.run(["git", "-C", str(repo)] + list(args),
                       capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} : {p.stderr.strip()[:200]}")
    return p


# >>> stale_lock — pure (testée par test_pm_sessions_archive.py)
def stale_lock(exists, mtime, now, git_vivant, min_age_s=LOCK_STALE_S):
    """Ce verrou est-il un cadavre à lever ?

    Deux conditions, toutes deux nécessaires. L'âge seul ne suffit pas : un
    `git add` sur un dépôt de 400 Mo peut être long, et lever le verrou d'un git
    en cours corromprait l'index. La présence d'un git vivant seule ne suffit pas
    non plus : c'est précisément parce qu'aucun ne tournait, en juin, que le
    verrou a survécu 75 jours."""
    return bool(exists) and not git_vivant and (now - mtime) > min_age_s
# <<< stale_lock


def git_vivant(repo):
    """Un processus git de cet utilisateur travaille-t-il dans ce dépôt ?

    Lecture de /proc : on ne regarde que nos propres processus (les autres sont
    illisibles, et ne nous concernent pas — le dépôt vit dans notre home)."""
    cible = str(Path(repo).resolve())
    for p in Path("/proc").glob("[0-9]*"):
        try:
            if (p / "comm").read_text().strip() != "git":
                continue
            cwd = os.readlink(p / "cwd")
        except OSError:
            continue
        if cwd == cible or cwd.startswith(cible + "/"):
            return True
    return False


# >>> a_ajouter — pure (testée par test_pm_sessions_archive.py)
def a_ajouter(porcelain):
    """Chemins à indexer, d'après `git status --porcelain -z` (déjà découpé).

    **Jamais les suppressions.** Un transcript effacé par la rétention de Claude
    Code ne doit pas voir sa disparition consignée : son blob resterait dans
    l'historique, mais l'arbre courant le perdrait — et un clone frais ne le
    ramènerait plus. On n'ajoute que ce qui existe."""
    out = []
    for e in porcelain:
        if len(e) < 4:
            continue
        x, y, chemin = e[0], e[1], e[3:]
        if x == "D" or y == "D":
            continue
        out.append(chemin)
    return out
# <<< a_ajouter


# >>> etat_check — pure (testée par test_pm_sessions_archive.py)
def etat_check(depot_ok, dernier_commit, now, en_avance, verrou, max_age_days=MAX_AGE_DAYS):
    """(ok, lignes) du contrôle. Pure pour que le verdict soit testable sans dépôt.

    Trois pannes distinctes, à ne pas confondre : pas de dépôt du tout, dépôt qui
    n'a plus reçu de commit (le cas de juin), et commits non poussés (l'archive
    existe mais ne quitte pas la machine)."""
    lignes, ok = [], True
    if not depot_ok:
        return False, ["✗ aucun dépôt git : les sessions ne sont archivées nulle part"]
    if dernier_commit is None:
        return False, ["✗ dépôt sans commit : rien n'est archivé"]
    age_j = (now - dernier_commit) / 86400.0
    if age_j > max_age_days:
        ok = False
        lignes.append(f"✗ dernier archivage il y a {age_j:.1f} j "
                      f"(seuil {max_age_days} j) — l'archivage ne tourne plus")
    else:
        lignes.append(f"archivé il y a {age_j * 24:.0f} h")
    if verrou:
        ok = False
        lignes.append("✗ verrou .git/index.lock périmé : chaque archivage échouera")
    if en_avance:
        ok = False
        lignes.append(f"✗ {en_avance} commit(s) non poussé(s) : l'archive ne quitte "
                      "pas la machine")
    return ok, lignes
# <<< etat_check


def copier_extras(repo, dry):
    """`history.jsonl` et les worklogs vivent HORS du store, et hors du périmètre
    du nettoyage de Claude Code. Ce sont eux qui ont permis de reconstituer
    42 séances effacées : ils méritent le même archivage que les transcripts."""
    dest = repo / EXTRA_DIR
    n = 0
    if HISTORY.is_file():
        d = dest / "history"
        if not dry:
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy2(HISTORY, d / HISTORY.name)
        n += 1
    if WORKLOGS.is_dir():
        d = dest / "worklogs"
        if not dry:
            d.mkdir(parents=True, exist_ok=True)
        for f in WORKLOGS.iterdir():
            if f.is_file():
                if not dry:
                    shutil.copy2(f, d / f.name)
                n += 1
    return n


def lever_verrou(repo, dry, verbose):
    lock = Path(repo) / ".git" / "index.lock"
    try:
        exists, mtime = lock.exists(), lock.stat().st_mtime if lock.exists() else 0
    except OSError:
        return False
    if not exists:
        return False
    vivant = git_vivant(repo)
    if not stale_lock(exists, mtime, time.time(), vivant):
        log(f"⚠ verrou présent mais {'un git tourne' if vivant else 'trop récent'} "
            "— on ne touche pas")
        return False
    age = (time.time() - mtime) / 3600
    log(f"⚠ verrou .git/index.lock périmé ({age:.1f} h, aucun git vivant) — levé")
    if not dry:
        try:
            lock.rename(lock.with_suffix(".lock.perime-" + str(int(time.time()))))
        except OSError as e:
            log(f"✗ impossible de lever le verrou : {e}")
            return False
    return True


def archiver(args):
    repo = STORE
    if not (repo / ".git").exists():
        log(f"✗ {repo} n'est pas un dépôt git — rien à archiver")
        return 1
    lever_verrou(repo, args.dry_run, args.verbose)
    n_extra = copier_extras(repo, args.dry_run)

    p = git(repo, "status", "--porcelain", "-z")
    if p.returncode != 0:
        log(f"✗ git status : {p.stderr.strip()[:200]}")
        return 1
    chemins = a_ajouter([e for e in p.stdout.split("\0") if e])
    if not chemins:
        log("rien de neuf à archiver" if args.verbose else "", echo=args.verbose)
    else:
        if args.dry_run:
            log(f"(dry-run) {len(chemins)} fichier(s) seraient archivés")
        else:
            for i in range(0, len(chemins), 200):        # ligne de commande bornée
                r = git(repo, "add", "--", *chemins[i:i + 200])
                if r.returncode != 0:
                    log(f"✗ git add : {r.stderr.strip()[:200]}")
                    return 1
            horo = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            msg = (f"sessions {socket.gethostname()} {horo}\n\n"
                   f"{len(chemins)} fichier(s) ajoutés ou modifiés"
                   + (f", dont {n_extra} hors store (history.jsonl, worklogs)" if n_extra else "")
                   + ".\nAucune suppression consignée : les blobs des transcripts déjà "
                     "effacés\nrestent atteignables dans l'historique (RM2997).\n")
            r = git(repo, "commit", "-q", "-m", msg)
            if r.returncode != 0:
                log(f"✗ git commit : {(r.stderr or r.stdout).strip()[:200]}")
                return 1
            log(f"✓ {len(chemins)} fichier(s) archivés")

    if args.no_push or args.dry_run:
        return 0
    br = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "dev"
    r = git(repo, "push", "origin", br)
    if r.returncode != 0:
        # Le commit tient : l'immunisation est acquise, seule la copie hors
        # machine manque. On le dit, sans effacer le bénéfice.
        log(f"⚠ push impossible ({r.stderr.strip()[:120]}) — l'archive locale, elle, "
            "est faite")
        return 2
    log(f"✓ poussé sur origin/{br}" if args.verbose else "", echo=args.verbose)
    return 0


def controler(args):
    repo = STORE
    depot_ok = (repo / ".git").exists()
    dernier = None
    en_avance = 0
    if depot_ok:
        s = git(repo, "log", "-1", "--format=%ct").stdout.strip()
        dernier = int(s) if s.isdigit() else None
        br = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "dev"
        c = git(repo, "rev-list", "--count", f"origin/{br}..{br}").stdout.strip()
        en_avance = int(c) if c.isdigit() else 0
    lock = repo / ".git" / "index.lock"
    verrou = False
    if lock.exists():
        try:
            verrou = stale_lock(True, lock.stat().st_mtime, time.time(), git_vivant(repo))
        except OSError:
            verrou = False
    ok, lignes = etat_check(depot_ok, dernier, time.time(), en_avance, verrou,
                            args.max_age_days)
    for l in lignes:
        print(l)
    return 0 if ok else 1


UNIT_SERVICE = """[Unit]
Description=Archivage des sessions Claude (transcripts, demandes, worklogs) — RM2997

[Service]
Type=oneshot
# Le script arrive au runtime avec le déploiement : jusque-là l'unité est
# ignorée plutôt que mise en échec — un timer rouge pour cause d'attente ferait
# du bruit là où on veut que seul un VRAI défaut d'archivage se voie.
ConditionPathExists={script}
ExecStart={python} {script}
"""

UNIT_TIMER = """[Unit]
Description=Archivage horaire des sessions Claude — RM2997

[Timer]
OnCalendar=hourly
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
"""


def chemin_runtime():
    """Chemin STABLE du script, pour un timer qui doit survivre au ticket.

    RM3151 : la résolution vit dans `pm_paths.runtime_script` — recopiée ici et là-bas, elle aurait
    divergé au premier ajustement, et un timer qui pointe un worktree détruit s'arrête en silence.
    """
    from pm_paths import runtime_script
    return runtime_script(Path(__file__).name, depuis=Path(__file__))


def installer_timer(args):
    d = Path("~/.config/systemd/user").expanduser()
    script, err = chemin_runtime()
    if err:
        log("✗ installation refusée : " + err)
        return 1
    d.mkdir(parents=True, exist_ok=True)
    (d / "pm-sessions-archive.service").write_text(
        UNIT_SERVICE.format(python=sys.executable, script=script), encoding="utf-8")
    (d / "pm-sessions-archive.timer").write_text(UNIT_TIMER, encoding="utf-8")
    for cmd in (["daemon-reload"], ["enable", "--now", "pm-sessions-archive.timer"]):
        r = subprocess.run(["systemctl", "--user"] + cmd, capture_output=True, text=True)
        if r.returncode != 0:
            log(f"✗ systemctl --user {' '.join(cmd)} : {r.stderr.strip()[:200]}")
            return 1
    log("✓ timer installé et activé (horaire) — "
        "arrêt : systemctl --user disable --now pm-sessions-archive.timer")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="Ne modifie rien ; sort 1 si l'archivage est vieux, "
                         "bloqué ou non poussé.")
    ap.add_argument("--max-age-days", type=float, default=MAX_AGE_DAYS)
    ap.add_argument("--no-push", action="store_true",
                    help="Commit local seul — suffit déjà à immuniser contre le "
                         "nettoyage de Claude Code.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--install-timer", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.install_timer:
        return installer_timer(args)
    if args.check:
        return controler(args)
    return archiver(args)


if __name__ == "__main__":
    sys.exit(main())
