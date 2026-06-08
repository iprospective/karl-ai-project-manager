"""Reflète une création / transition de ticket PM dans le worklog de session
(pm-session-status.py), pour que « il reste quoi à faire dans cette session » reste
fidèle sans dépendre de la discipline de l'agent.

Couplage volontairement faible :
  - **no-op hors session Claude Code** (`$CLAUDE_CODE_SESSION_ID` absent → cron, autre
    agent, exécution manuelle) : le worklog par session n'a alors aucun sens ;
  - **best-effort** : toute erreur est avalée. Ce hook ne doit JAMAIS faire échouer
    l'opération PM principale (création / changement de statut du ticket).

Implémente le câblage évoqué dans RM1875 (manifest déclaratif alimenté par les scripts).
"""
import os
import subprocess
import sys
from pathlib import Path


def log_to_session(ref, label=None, status=None, project=None, note=None):
    """Upsert un item dans le worklog de la session courante. Silencieux si hors session."""
    if not os.environ.get("CLAUDE_CODE_SESSION_ID"):
        return
    script = Path(__file__).resolve().parent / "pm-session-status.py"
    if not script.exists():
        return
    cmd = [sys.executable, str(script), "add", str(ref)]
    if label:
        cmd.append(str(label))
    if status:
        cmd += ["--status", str(status)]
    if project:
        cmd += ["--project", str(project)]
    if note:
        cmd += ["--note", str(note)]
    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=10)
    except Exception:
        pass  # best-effort : jamais bloquant pour l'opération PM
