#!/usr/bin/env python3
"""pm-env-status — santé du poste PM, en une commande (RM2458).

Même moteur que la page cockpit (`op_env_status` de karl-agent.py) : outils &
dépendances, secrets, git/GitLab (tous les repos PM), SSH, PM. Chaque ligne
rouge/orange porte SA commande de remédiation.

Deux usages :
  • humain   : `pm-env-status.py`            → rapport lisible, coloré
  • machine  : `pm-env-status.py --json`     → JSON complet (un agent le lit en
               début de session pour signaler ce qui bloque avant de commencer)

Code retour : 0 si tout est vert/info ; 2 si au moins un contrôle est en ERREUR ;
1 sur erreur interne. Aucun secret n'est jamais affiché.
"""
import argparse
import importlib.util
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent


def _load_karl_agent():
    spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["karl_agent"] = mod
    spec.loader.exec_module(mod)
    return mod


_ICON = {"ok": "✓", "info": "·", "warn": "!", "error": "✗"}
_COLOR = {"ok": "\033[32m", "info": "\033[90m", "warn": "\033[33m", "error": "\033[31m"}
_RESET = "\033[0m"


def _render_human(report, color=True):
    def c(level, s):
        return (_COLOR.get(level, "") + s + _RESET) if color else s
    lines = []
    s = report["summary"]["counts"]
    head = (f"État du poste — {report['generated_at']}  "
            f"[✓ {s['ok']}  ! {s['warn']}  ✗ {s['error']}]")
    lines.append(head)
    for g in report["groups"]:
        lines.append("")
        lines.append(f"── {g['name']} ──")
        for chk in g["checks"]:
            lv = chk.get("level", "info")
            mark = c(lv, _ICON.get(lv, "·"))
            lines.append(f"  {mark} {chk['label']}: {chk.get('detail', '')}")
            if chk.get("fix"):
                lines.append(f"      → {chk['fix']}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Santé du poste PM (RM2458)")
    ap.add_argument("--json", action="store_true", help="sortie JSON complète (mode machine)")
    ap.add_argument("--no-color", action="store_true", help="désactive la couleur ANSI")
    args = ap.parse_args(argv)
    try:
        ka = _load_karl_agent()
        report = ka.op_env_status()
    except Exception as exc:  # noqa: BLE001 — un diagnostic ne doit pas planter sec
        print(f"pm-env-status : erreur interne ({exc.__class__.__name__}: {exc})",
              file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render_human(report, color=(not args.no_color) and sys.stdout.isatty()))
    return 2 if report["summary"]["worst"] == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
