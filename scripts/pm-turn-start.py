#!/usr/bin/env python3
"""pm-turn-start — hook UserPromptSubmit : pose le timestamp de début de tour.

Quand tu envoies un message, Claude démarre un « tour ». Ce hook écrit l'instant
de départ (epoch) dans ~/.claude/logs/turn-start-<session_id>.json. À la fin du
tour, le hook Stop (`pm-task-tick`) lit ce fichier, calcule le temps IA wall-clock
écoulé, l'ajoute à `ai_time_total_minutes` du ticket courant, puis efface le fichier.

Isolé par session_id (plusieurs sessions Claude Code en parallèle ne se marchent
pas dessus). Silencieux et non-bloquant : n'échoue JAMAIS (ne doit pas casser la
soumission du prompt).
"""
import json
import re
import sys
import time
from pathlib import Path


def main():
    try:
        evt = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    sid = str(evt.get("session_id") or "unknown")
    sid = re.sub(r"[^A-Za-z0-9_-]", "_", sid)[:80]  # nom de fichier sûr
    d = Path.home() / ".claude" / "logs"
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"turn-start-{sid}.json").write_text(
            json.dumps({"start_epoch": time.time()}), encoding="utf-8")
    except OSError:
        pass


if __name__ == "__main__":
    main()
