#!/usr/bin/env python3
"""Tests offline de pm-claude-hooks-sync — forme de hook `mmi-pm <cmd>` (RM2580).

Lancer : python3 scripts/test_pm_claude_hooks_sync.py
Couvre : dérivation nom→sous-commande, commande mmi-pm, détection double-forme
(abs-path ET mmi-pm), build_group émet mmi-pm (+ matcher/timeout).
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load():
    spec = importlib.util.spec_from_file_location("pm_hooks_sync", HERE / "pm-claude-hooks-sync.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    m = _load()

    # 1. _cmd_name / _mmi_command
    assert m._cmd_name("pm-session-status.py") == "session-status"
    assert m._cmd_name("pm-turn-wait.py") == "turn-wait"
    assert m._mmi_command("pm-session-status.py", " refresh") == "mmi-pm session-status refresh"
    assert m._mmi_command("pm-task-report.py", " --all --apply") == "mmi-pm task-report --all --apply"
    print("✓ _cmd_name / _mmi_command : pm-<x>.py → mmi-pm <x>")

    # 2. event_has_script détecte l'ancienne forme abs-path ET la forme mmi-pm
    old = [{"hooks": [{"command": "/zfs/.../scripts/pm-task-tick.py"}]}]
    new = [{"hooks": [{"command": "mmi-pm task-tick"}]}]
    other = [{"hooks": [{"command": "mmi-pm autre-chose"}]}]
    assert m.event_has_script(old, "pm-task-tick.py")
    assert m.event_has_script(new, "pm-task-tick.py")
    assert not m.event_has_script(other, "pm-task-tick.py")
    assert not m.event_has_script(None, "pm-task-tick.py")
    print("✓ event_has_script détecte abs-path ET mmi-pm (et pas les autres)")

    # 3. build_group émet la forme mmi-pm, respecte matcher/timeout
    g = m.build_group("", "pm-task-tick.py", "", None)
    assert g["hooks"][0]["command"] == "mmi-pm task-tick", g
    assert g["matcher"] == "" and "timeout" not in g["hooks"][0]
    g2 = m.build_group(None, "pm-session-status.py", " refresh &>/dev/null || true", 30)
    assert g2["hooks"][0]["command"] == "mmi-pm session-status refresh &>/dev/null || true"
    assert g2["hooks"][0]["timeout"] == 30 and "matcher" not in g2  # matcher=None → pas de clé
    print("✓ build_group émet mmi-pm (+ matcher/timeout corrects)")

    # 4. Cohérence : tous les scripts de PM_HOOKS donnent une sous-commande non vide
    for _, _, script_name, _, _ in m.PM_HOOKS:
        assert m._cmd_name(script_name) and not m._cmd_name(script_name).endswith(".py")
    print(f"✓ PM_HOOKS ({len(m.PM_HOOKS)}) : sous-commandes dérivées propres")

    print("\nOK — tests pm-claude-hooks-sync passent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
