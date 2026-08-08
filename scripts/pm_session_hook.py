"""Reflète une création / transition de ticket PM dans le worklog de session
(pm-session-status.py), pour que « il reste quoi à faire dans cette session » reste
fidèle sans dépendre de la discipline de l'agent.

Couplage volontairement faible :
  - **no-op hors session Claude Code** (`$CLAUDE_CODE_SESSION_ID` absent → cron, autre
    agent, exécution manuelle) : le worklog par session n'a alors aucun sens ;
  - **best-effort** : toute erreur est avalée. Ce hook ne doit JAMAIS faire échouer
    l'opération PM principale (création / changement de statut du ticket).

Câblage RM1875 (manifest alimenté par les scripts) + RM2068 (enrichissement commit /
prochaine action ; le statut courant est résolu en live côté `show`).
"""
import os
import subprocess
import sys
from pathlib import Path


def log_to_session(ref, label=None, status=None, project=None, note=None,
                   next_action=None, commit=None):
    """Upsert un item dans le worklog de la session courante. Silencieux si hors session.

    `status` omis → l'item garde son statut stocké (utile pour un simple enrichissement,
    ex. le hook post-commit qui ne fait qu'attacher le dernier `commit`). Le statut
    COURANT réel est de toute façon résolu en live par `pm-session-status show` (RM2068)."""
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
    if next_action:
        cmd += ["--next", str(next_action)]
    if commit:
        cmd += ["--commit", str(commit)]
    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=10)
    except Exception:
        pass  # best-effort : jamais bloquant pour l'opération PM


def log_mr_to_session(iid, url=None, repo=None, source=None, target=None,
                      ref=None, state="opened"):
    """RM2583 : reflète une MR (ouverte / mergée / fermée) dans le worklog de la
    session. Mêmes règles que `log_to_session` : no-op hors session Claude Code,
    best-effort — une panne d'écriture du worklog ne doit JAMAIS faire échouer le
    `pm-mr create` qui vient de réussir côté forge."""
    if not os.environ.get("CLAUDE_CODE_SESSION_ID"):
        return
    script = Path(__file__).resolve().parent / "pm-session-status.py"
    if not script.exists():
        return
    cmd = [sys.executable, str(script), "mr", str(iid), "--state", str(state)]
    for flag, val in (("--url", url), ("--repo", repo), ("--source", source),
                      ("--target", target), ("--ref", ref)):
        if val:
            cmd += [flag, str(val)]
    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=10)
    except Exception:
        pass  # best-effort : jamais bloquant pour l'opération forge
