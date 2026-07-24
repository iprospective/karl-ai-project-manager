#!/usr/bin/env python3
"""pm-post-commit — hook git post-commit (repos PM-trackés).

À CHAQUE commit d'un repo PM-tracké, reporte la consommation du ticket vers Redmine
(time_entries + CF17) et, si le commit est substantiel, co-poste son MESSAGE comme
note de journal (garde-fou anti-conso dans pm-task-report). C'est le déclencheur
« push à chaque commit » de RM2035.

Niveau de note par commit (`traceability.commit_note_level`, NORMS § « Unité de
traçabilité » — RM2409) :
  work (défaut) : note pour les commits de travail uniquement — les commits
                  d'outillage (`pm(*)`, `chore(*)`) reportent la conso SANS note ;
  all           : tout commit rattaché à une tâche est noté ;
  none          : aucune note auto (conso + .log.md conservés).
Résolution du niveau : `meta.yml` du projet (via `.mmi-pm`) > `pm.config.local.yml`
> `pm.config.yml` du core > défaut `work`.

Résolution du ticket :
  1. RM-id dans le message de commit (`RM\\d+`) — convention de commit du PM.
  2. sinon `.mmi-pm/CURRENT_TASK` du repo.

No-op (rien à faire) si :
  - repo non PM-tracké (pas de `.mmi-pm`),
  - commit de tick/report PM (auto-déclenchement, rien à reporter),
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

PM_CORE = "/zfs/workspaces/.mmi-pm-core"
REPORT = PM_CORE + "/scripts/pm-task-report.py"

NOTE_LEVELS = {"work", "all", "none"}
# Commit d'outillage PM (auto-commits des scripts pm-*, chores) : housekeeping,
# jamais substantiel — exclu de la note au niveau `work`.
TOOLING_RE = re.compile(r"^(chore(\([^)]*\))?:|pm\([a-z-]+\))")


def _git(*args):
    return subprocess.check_output(["git", *args], text=True,
                                   stderr=subprocess.DEVNULL).strip()


def _yaml_note_level(path):
    """`traceability.commit_note_level` d'un YAML, ou None (absent/invalide)."""
    try:
        import yaml
        d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        lvl = (d.get("traceability") or {}).get("commit_note_level")
        return lvl if lvl in NOTE_LEVELS else None
    except Exception:
        return None


def _note_level(cwd):
    """Niveau effectif : meta.yml projet > config locale > config core > `work`.
    Best-effort — toute erreur retombe sur le défaut (le hook ne casse jamais)."""
    for path in (cwd / ".mmi-pm" / "meta.yml",
                 Path(PM_CORE) / "pm.config.local.yml",
                 Path(PM_CORE) / "pm.config.yml"):
        if path.is_file():
            lvl = _yaml_note_level(path)
            if lvl:
                return lvl
    return "work"


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
    # Anti-récursion : les commits produits par le tick/report eux-mêmes ne
    # déclenchent RIEN (leur conso est déjà celle qu'ils viennent de reporter).
    if re.match(r"^(chore\(pm\)|pm\(report\)|pm\(tick\))", subject):
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
    cmd = [sys.executable, REPORT, "--rm-id", rm, "--apply", "--no-commit"]
    level = _note_level(cwd)
    if level == "all" or (level == "work" and not TOOLING_RE.match(subject)):
        cmd += ["--commit", commit, "--note", subject]
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
