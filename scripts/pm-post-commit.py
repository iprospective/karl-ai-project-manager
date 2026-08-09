#!/usr/bin/env python3
"""pm-post-commit — hook git post-commit (repos PM-trackés).

À CHAQUE commit d'un repo PM-tracké, reporte la consommation du ticket vers Redmine
(time_entries + CF17) et, si le commit est substantiel, co-poste son MESSAGE comme
note de journal (garde-fou anti-conso dans pm-task-report). C'est le déclencheur
« push à chaque commit » de RM2035.

Résolution du ticket :
  1. RM-id dans le message de commit (`RM\\d+`) — convention de commit du PM.
  2. sinon `.mmi-pm/CURRENT_TASK` du repo.

No-op (rien à faire) si :
  - repo non PM-tracké (pas de `.mmi-pm`),
  - commit de chore/report PM (évite bruit + auto-déclenchement),
  - aucun RM-id résolu.

Non-bloquant : lance pm-task-report en ARRIÈRE-PLAN détaché, `--no-commit` (pas de
nouveau commit → pas de boucle), et exit 0 quoi qu'il arrive (ne casse jamais le commit).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Racine du code PM. Surchargée par PM_CORE_DIR (relocalisable, RM2580) ; défaut
# = emplacement de déploiement actuel (0 régression). Hook symlinké → on pourrait
# aussi s'auto-localiser, mais l'override env est le mécanisme canonique (pm_paths).
PM_CORE = os.environ.get("PM_CORE_DIR") or "/zfs/workspaces/.mmi-pm-core"
REPORT = PM_CORE + "/scripts/pm-task-report.py"


def _git(*args):
    return subprocess.check_output(["git", *args], text=True,
                                   stderr=subprocess.DEVNULL).strip()


def main():
    cwd = Path(os.getcwd())          # git positionne le hook à la racine du worktree
    # Repo PM = workspace avec .mmi-pm, OU le repo core .mmi-pm-core lui-même (code PM-system :
    # le ticket y est résolu via le RM<id> du message de commit, pas de .mmi-pm/CURRENT_TASK).
    try:
        is_core = cwd.resolve() == Path(PM_CORE).resolve()
    except OSError:
        is_core = False
    if not (cwd / ".mmi-pm").exists() and not is_core:
        return                        # repo non PM-tracké
    try:
        commit = _git("rev-parse", "HEAD")
        subject = _git("log", "-1", "--format=%s")
    except Exception:
        return
    # Skip les commits d'outillage PM (tick/report/chore) : pas de note, pas de
    # déclenchement récursif. (pm-task-report --no-commit ne committe pas, mais ces
    # commits-là n'ont de toute façon rien de substantiel à reporter en note.)
    if re.match(r"^(chore\(pm\)|pm\(report\)|pm\(tick\)|pm\(report\))", subject):
        return
    m = re.search(r"\bRM(\d+)", subject)
    rm = m.group(1) if m else None
    if not rm:
        ct = cwd / ".mmi-pm" / "CURRENT_TASK"
        try:
            mm = re.search(r"(\d+)", ct.read_text(encoding="utf-8"))
            rm = mm.group(1) if mm else None
        except OSError:
            rm = None
    if not rm:
        return
    # Worklog de session (best-effort, no-op hors session Claude Code) : attacher le
    # dernier commit au ticket touché, pour que « il reste quoi à faire » montre l'avancée
    # réelle. Statut non forcé → résolu en live par `pm-session-status show` (RM2068).
    try:
        import pm_session_hook
        pm_session_hook.log_to_session(f"RM{rm}", commit=commit[:9])
    except Exception:
        pass
    cmd = [sys.executable, REPORT, "--rm-id", rm, "--apply",
           "--commit", commit, "--note", subject, "--no-commit"]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)   # ne bloque JAMAIS le commit
