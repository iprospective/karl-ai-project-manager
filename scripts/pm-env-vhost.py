#!/usr/bin/env python3
"""pm-env-vhost — façade CLI des verbes vhost du helper privilégié (RM2372, porté de `bin/mmi-pm env vhost`).

Le PRIVILÈGE vit dans pm-env-helper (règle sudoers NOPASSWD dédiée) : on route via `sudo -n <helper>` sans mot de passe
et sans nouvelle règle. Chemin du helper : pm.config.yml :: env_runtime.helper (+ override local), défaut /usr/local/sbin/pm-env-helper.
Usage : mmi-pm env-vhost add <name> <docroot> <sock> | proxy-add <name> <port> | karl-add <name> <port> | remove <name>   [--dry-run]
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent
VERBS = ("add", "proxy-add", "karl-add", "remove")


def resolve_helper(core_dir=CORE_DIR) -> str:
    helper = ""
    try:
        import yaml
        for name in ("pm.config.yml", "pm.config.local.yml"):
            p = core_dir / name
            if p.is_file():
                d = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("env_runtime") or {}
                helper = d.get("helper") or helper
    except Exception:  # noqa: BLE001 — défaut historique
        pass
    return helper or "/usr/local/sbin/pm-env-helper"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("verb", choices=VERBS)
    ap.add_argument("args", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    cmd = ["sudo", "-n", resolve_helper(), f"vhost-{a.verb}", *a.args]
    if a.dry_run:
        print("[dry] " + " ".join(cmd)); return 0
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
