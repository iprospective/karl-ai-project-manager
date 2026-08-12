#!/usr/bin/env python3
"""pm-perms — applique/répare le modèle de perms multi-user PM (RM2438 / T6 RM2502).

Outil IDEMPOTENT et committé (remplace les runbooks scratchpad éphémères, source de
dérive — c'est un tel oubli qui a laissé matnat/infra en sticky, bug RM2438). Opère
sur UN workspace projet (dossiers seulement, PAS de récursion dans les worktrees
per-dev sous `envs/`), et optionnellement sur le `var/` (state_dir) du core.

Modèle (dérivé du CDC §3.4 + d'un projet sain) :
    SQUELETTE  pm:pm 2750  — racine workspace, repos/         (group r-x, PAS d'écriture)
    CHURN      pm:pm 2770  — .mmi-pm, tasks, docs, envs        (group-write, JAMAIS sticky)
    CHURN+r    pm:pm 2775  — .mmi-pm/{memory,project,.wiki-sync} (idem + other-read)
    STATE      pm:pm 2775  — var/, var/locks, var/sessions (ticket-locks partagés)

Invariants DURS (la cause-racine du bug RM2438) :
  · AUCUN dossier churn ne porte le sticky bit — `atomic_write` (os.replace) doit
    pouvoir remplacer un fichier qu'il ne possède pas ; sous sticky → EPERM.
  · Le groupe des dossiers partagés = `pm`.
  · Le squelette n'est PAS group-writable (anti-déstructuration).

Usage :
    pm-perms.py [WORKSPACE]        # DRY-RUN : liste les écarts, ne change rien (exit 1 si écart)
    pm-perms.py --apply [WS]       # applique (chmod + chgrp pm ; owner si root)
    pm-perms.py --var [WS]         # inclut aussi le var/ du core (PM_CORE_DIR / pm.config)
    WORKSPACE défaut = auto-détection en remontant jusqu'au .mmi-pm du cwd.

--apply nécessite d'être `pm` ou `root` (chmod/chgrp de fichiers pm-owned).
"""
import argparse
import grp
import os
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
}
STATE_MODEL = {".": 0o2775, "locks": 0o2775, "sessions": 0o2775}
STICKY = 0o1000


def _pm_gid():
    try:
        return grp.getgrnam("pm").gr_gid
    except KeyError:
        return None


def diagnose(path: Path, want_mode: int, want_gid):
    """Retourne la liste des écarts (chaînes) pour un dossier — fonction PURE (testable
    sans privilège). Vérifie mode, sticky (jamais), et groupe."""
    issues = []
    try:
        st = path.stat()
    except FileNotFoundError:
        return issues  # dossier absent → ignoré (projets partiels)
    cur = stat.S_IMODE(st.st_mode)
    if cur & STICKY:
        issues.append(f"sticky bit présent (mode {cur:04o}) — INTERDIT sur churn")
    if cur != want_mode:
        issues.append(f"mode {cur:04o} ≠ attendu {want_mode:04o}")
    if want_gid is not None and st.st_gid != want_gid:
        try:
            gname = grp.getgrgid(st.st_gid).gr_name
        except KeyError:
            gname = str(st.st_gid)
        issues.append(f"groupe {gname} ≠ pm")
    return issues


def _find_workspace(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / ".mmi-pm").is_dir():
            return d
    sys.exit(f"ERREUR : aucun .mmi-pm trouvé en remontant depuis {start}")


def _targets(ws: Path, include_var: bool):
    """[(path, want_mode)] pour les dossiers existants du modèle."""
    out = [(ws / (rel if rel != "." else ""), m) for rel, m in WORKSPACE_MODEL.items()]
    if include_var:
        core = os.environ.get("PM_CORE_DIR")
        var = Path(core).resolve() / "var" if core else ws.parent  # fallback improbable
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from pm_paths import PMConfig  # noqa
            var = PMConfig.load().state_dir
        except Exception:
            pass
        out += [(var / (rel if rel != "." else ""), m) for rel, m in STATE_MODEL.items()]
    return [(p, m) for p, m in out if p.exists()]


def _apply(path: Path, want_mode: int, want_gid, can_chown: bool):
    done = []
    st = path.stat()
    if stat.S_IMODE(st.st_mode) != want_mode:
        os.chmod(path, want_mode)  # pose setgid, retire sticky
        done.append(f"chmod {want_mode:04o}")
    if want_gid is not None and st.st_gid != want_gid:
        os.chown(path, -1, want_gid)  # chgrp pm
        done.append("chgrp pm")
    if can_chown and want_gid is not None:
        # owner idéal = pm pour les DOSSIERS (fichiers = dernier writer, laissés tels quels)
        try:
            pm_uid = __import__("pwd").getpwnam("pm").pw_uid
            if st.st_uid != pm_uid:
                os.chown(path, pm_uid, -1)
                done.append("chown pm")
        except (KeyError, PermissionError):
            pass
    return done


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", nargs="?", default=None)
    ap.add_argument("--apply", action="store_true", help="Applique (défaut : dry-run).")
    ap.add_argument("--var", action="store_true", help="Inclut aussi le var/ (state_dir).")
    args = ap.parse_args()

    ws = Path(args.workspace).resolve() if args.workspace else _find_workspace(Path.cwd())
    gid = _pm_gid()
    if gid is None:
        print("⚠ groupe 'pm' introuvable — vérif groupe désactivée")
    can_chown = (os.geteuid() == 0)

    targets = _targets(ws, args.var)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== pm-perms [{mode}] {ws} ===")
    drift = 0
    for path, want in sorted(targets):
        issues = diagnose(path, want, gid)
        if not issues:
            continue
        drift += 1
        rel = os.path.relpath(path, ws)
        print(f"  ⚠ {rel} : {'; '.join(issues)}")
        if args.apply:
            try:
                done = _apply(path, want, gid, can_chown)
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
