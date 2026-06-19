#!/usr/bin/env python3
"""pm-turn-wait — hooks PreToolUse / PostToolUse (matcher AskUserQuestion|ExitPlanMode).

Mesure l'attente HUMAINE quand Claude pose une question bloquante (outil
AskUserQuestion, ou ExitPlanMode) : ces outils maintiennent le tour OUVERT pendant
ta délibération (pas de Stop, et ta réponse est un résultat d'outil, pas un nouveau
prompt → pas de nouveau départ). Sans ça, ton temps de décision est compté comme du
temps IA. On encadre donc l'attente pour la SOUSTRAIRE ensuite (pm-task-tick).

  PreToolUse  -> `pm-turn-wait.py start` : pose wait_start = now.
  PostToolUse -> `pm-turn-wait.py stop`  : human_wait_seconds += now - wait_start.

Écrit dans le même fichier de tour que pm-turn-start (~/.claude/logs/turn-start-<sid>.json).
Non-bloquant : n'échoue JAMAIS (ne doit pas casser un appel d'outil).
"""
import json
import re
import sys
import time
from pathlib import Path


def turn_file(evt):
    sid = re.sub(r"[^A-Za-z0-9_-]", "_", str(evt.get("session_id") or "unknown"))[:80]
    return Path.home() / ".claude" / "logs" / f"turn-start-{sid}.json"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        evt = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    p = turn_file(evt)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return  # pas de tour en cours (fichier absent/illisible) → rien à faire
    now = time.time()
    if mode == "start":
        data["wait_start"] = now
    elif mode == "stop":
        ws = data.pop("wait_start", None)
        if ws:
            data["human_wait_seconds"] = (
                float(data.get("human_wait_seconds", 0) or 0) + (now - float(ws)))
    else:
        return
    try:
        p.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


if __name__ == "__main__":
    main()
