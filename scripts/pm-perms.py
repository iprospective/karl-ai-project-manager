#!/usr/bin/env python3
"""pm-perms — applique/répare le modèle de perms multi-user PM (RM2438 / T6 RM2502).

Outil IDEMPOTENT et committé (remplace les runbooks scratchpad éphémères, source de
dérive — c'est un tel oubli qui a laissé matnat/infra en sticky, bug RM2438). Opère
sur UN workspace projet (dossiers seulement, PAS de récursion dans les worktrees
per-dev sous `envs/`), et optionnellement (`--var`) sur le `var/` (state_dir) ET les
fichiers env communs du core.

Modèle (dérivé du CDC §3.4 + d'un projet sain) :
    SQUELETTE  pm:pm 2750  — racine workspace, repos/         (group r-x, PAS d'écriture)
    CHURN      pm:pm 2770  — .mmi-pm, tasks, docs, envs        (group-write, JAMAIS sticky)
                             + tmp, sessions, logs, data       (partagés du layout RM1993)
    CHURN+r    pm:pm 2775  — .mmi-pm/{memory,project,.wiki-sync} (idem + other-read)
    STATE      pm:pm 2775  — var/, var/locks, var/sessions (ticket-locks partagés)
    ENV        root:pm 640 — pm.env, .env du core (secrets/config partagés)

Fichiers env (`--var`) : owner **root** (privilégié : seul root/sudo réécrit), groupe
**pm** (les comptes de rôle `<dev>-pm` DOIVENT lire config+secrets communs pour tourner),
mode **640** (pas d'`other`). Corrige l'exposition initiale (`.env` en `root:mathieu` →
un futur `<dev2>-pm` hors groupe `mathieu` ne pouvait pas lire les secrets communs).

Invariants DURS (la cause-racine du bug RM2438) :
  · AUCUN dossier churn ne porte le sticky bit — `atomic_write` (os.replace) doit
    pouvoir remplacer un fichier qu'il ne possède pas ; sous sticky → EPERM.
  · Le groupe des dossiers/fichiers partagés = `pm`.
  · Le squelette n'est PAS group-writable (anti-déstructuration).

Usage :
    pm-perms.py [WORKSPACE]        # DRY-RUN : liste les écarts, ne change rien (exit 1 si écart)
    pm-perms.py --apply [WS]       # applique (chmod + chgrp pm ; owner si root)
    pm-perms.py --var [WS]         # inclut aussi var/ (state_dir) + pm.env/.env du core
    pm-perms.py --list-dirs        # liste les dossiers du modèle (rel.), un par ligne
    WORKSPACE défaut = auto-détection en remontant jusqu'au .mmi-pm du cwd.

`--list-dirs` est le contrat consommé par `pm-env-helper ws-init` (RM2909) : le helper
privilégié CRÉE les dossiers, ce module reste la SEULE définition du modèle. Rien à
resynchroniser dans le shell quand le layout bouge.

--apply nécessite d'être `pm` ou `root` (chmod/chgrp de fichiers pm-owned ; l'ownership
root des fichiers env n'est posé qu'en root).
"""
import argparse
import grp
import os
import pwd
import stat
import sys
from pathlib import Path

# rel_path sous le workspace -> mode octal attendu (setgid, JAMAIS sticky)
WORKSPACE_MODEL = {
    ".": 0o2750,
    "repos": 0o2750,
    "envs": 0o2770,
    ".mmi-pm": 0o2770,
    ".mmi-pm/tasks": 0o2770,
    ".mmi-pm/docs": 0o2770,
    ".mmi-pm/memory": 0o2775,
    ".mmi-pm/project": 0o2775,
    ".mmi-pm/.wiki-sync": 0o2775,
    # Dossiers partagés du layout (RM1993, créés par pm-env-init) : churn — plusieurs
    # devs et leurs agents y écrivent. Modélisés ici pour que `ws-init` (RM2909) n'ait
    # pas à redéclarer le modèle dans le shell du helper privilégié.
    "tmp": 0o2770,
    "sessions": 0o2770,
    "logs": 0o2770,
    "data": 0o2770,
}
STATE_MODEL = {".": 0o2775, "locks": 0o2775, "sessions": 0o2775}
# Fichiers env communs du core (à la racine pm_dir) → root:pm 640.
ENV_FILES = ("pm.env", ".env")
ENV_FILE_MODE = 0o640
ROOT_UID = 0
STICKY = 0o1000


def _pm_gid():
    try:
        return grp.getgrnam("pm").gr_gid
    except KeyError:
        return None


def _pm_uid():
    try:
        return pwd.getpwnam("pm").pw_uid
    except KeyError:
        return None


def _uname(uid):
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def diagnose(path: Path, want_mode: int, want_gid, want_uid=None):
    """Retourne la liste des écarts (chaînes) pour un chemin — fonction PURE (testable
    sans privilège). Vérifie mode, sticky (jamais, sur les DOSSIERS), groupe, et — si
    `want_uid` fourni (fichiers env) — le propriétaire."""
    issues = []
    if path.is_symlink():
        # `stat()`/`chmod()`/`chown()` DÉRÉFÉRENCENT : normaliser un lien reviendrait à
        # muter sa cible, potentiellement hors du workspace (un `.mmi-pm` symlinké vers
        # le core PROD root-owned se retrouverait chown pm). Hors modèle → hors sujet.
        return [f"lien symbolique → ignoré (le modèle ne normalise que des dossiers réels)"]
    try:
        st = path.stat()
    except FileNotFoundError:
        return issues  # chemin absent → ignoré (projets partiels)
    cur = stat.S_IMODE(st.st_mode)
    if stat.S_ISDIR(st.st_mode) and cur & STICKY:
        issues.append(f"sticky bit présent (mode {cur:04o}) — INTERDIT sur churn")
    if cur != want_mode:
        issues.append(f"mode {cur:04o} ≠ attendu {want_mode:04o}")
    if want_gid is not None and st.st_gid != want_gid:
        try:
            gname = grp.getgrgid(st.st_gid).gr_name
        except KeyError:
            gname = str(st.st_gid)
        issues.append(f"groupe {gname} ≠ pm")
    if want_uid is not None and st.st_uid != want_uid:
        issues.append(f"propriétaire {_uname(st.st_uid)} ≠ {_uname(want_uid)}")
    return issues


def model_dirs() -> list:
    """Dossiers du modèle en chemins relatifs au workspace, PARENTS D'ABORD.

    `"."` (la racine) est émis en premier ; le tri par profondeur garantit qu'un
    consommateur peut créer les dossiers dans l'ordre reçu sans `mkdir -p`."""
    return sorted(WORKSPACE_MODEL, key=lambda r: (0 if r == "." else 1, r.count("/"), r))


def _find_workspace(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / ".mmi-pm").is_dir():
            return d
    sys.exit(f"ERREUR : aucun .mmi-pm trouvé en remontant depuis {start}")


def _core_paths():
    """(pm_dir, state_dir) du core, ou (None, None). PMConfig d'abord, PM_CORE_DIR en repli."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from pm_paths import PMConfig  # noqa
        cfg = PMConfig.load()
        return cfg.pm_dir, cfg.state_dir
    except Exception:
        c = os.environ.get("PM_CORE_DIR")
        if c:
            core = Path(c).expanduser().resolve()
            return core, core / "var"
        return None, None


def _targets(ws: Path, include_var: bool):
    """[(path, want_mode, want_uid)] pour les chemins existants du modèle.
    want_uid : pm pour dossiers, root pour fichiers env, None si user pm absent."""
    pm_uid = _pm_uid()
    out = [(ws / (rel if rel != "." else ""), m, pm_uid) for rel, m in WORKSPACE_MODEL.items()]
    if include_var:
        core, state = _core_paths()
        if state:
            out += [(state / (rel if rel != "." else ""), m, pm_uid)
                    for rel, m in STATE_MODEL.items()]
        if core:
            out += [(core / f, ENV_FILE_MODE, ROOT_UID) for f in ENV_FILES]
    return [(p, m, u) for p, m, u in out if p.exists() and not p.is_symlink()]


def _apply(path: Path, want_mode: int, want_gid, want_uid, can_chown: bool):
    done = []
    st = path.stat()
    if stat.S_IMODE(st.st_mode) != want_mode:
        os.chmod(path, want_mode)  # pose setgid, retire sticky
        done.append(f"chmod {want_mode:04o}")
    if want_gid is not None and st.st_gid != want_gid:
        os.chown(path, -1, want_gid)  # chgrp pm
        done.append("chgrp pm")
    if can_chown and want_uid is not None and st.st_uid != want_uid:
        try:
            os.chown(path, want_uid, -1)
            done.append(f"chown {_uname(want_uid)}")
        except (KeyError, PermissionError):
            pass
    return done


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", nargs="?", default=None)
    ap.add_argument("--apply", action="store_true", help="Applique (défaut : dry-run).")
    ap.add_argument("--var", action="store_true",
                    help="Inclut aussi var/ (state_dir) + pm.env/.env du core.")
    ap.add_argument("--list-dirs", action="store_true",
                    help="Liste les dossiers du modèle (chemins relatifs), un par ligne, "
                         "et sort. Contrat consommé par `pm-env-helper ws-init` (RM2909).")
    args = ap.parse_args()

    if args.list_dirs:
        for rel in model_dirs():
            print(rel)
        return 0

    ws = Path(args.workspace).resolve() if args.workspace else _find_workspace(Path.cwd())
    gid = _pm_gid()
    if gid is None:
        print("⚠ groupe 'pm' introuvable — vérif groupe désactivée")
    can_chown = (os.geteuid() == 0)

    targets = _targets(ws, args.var)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== pm-perms [{mode}] {ws} ===")
    drift = 0
    for path, want, uid in sorted(targets, key=lambda t: str(t[0])):
        issues = diagnose(path, want, gid, uid)
        if not issues:
            continue
        drift += 1
        rel = os.path.relpath(path, ws)
        print(f"  ⚠ {rel} : {'; '.join(issues)}")
        if args.apply:
            try:
                done = _apply(path, want, gid, uid, can_chown)
                print(f"      → {', '.join(done) if done else 'rien à faire'}")
            except PermissionError as e:
                print(f"      ✗ échec ({e}) — relance en `pm` ou `root`")
    if drift == 0:
        print("  ✓ conforme — rien à corriger")
    elif not args.apply:
        print(f"\n{drift} écart(s). Relance avec --apply (en pm/root) pour corriger.")
    return 1 if (drift and not args.apply) else 0


if __name__ == "__main__":
    sys.exit(main())
