#!/usr/bin/env python3
"""mmi-pm — point d'entrée UNIQUE du système PM (RM2580 étape 3a).

Route `mmi-pm <cmd> [args…]` vers le script `pm-<cmd>` co-localisé, en
s'auto-localisant (survit au déménagement du code : /opt, paquet). But :
remplacer les chemins absolus `/zfs/workspaces/.mmi-pm-core/scripts/pm-*.py`
codés en dur (hooks `.claude/settings.local.json`, skills, cron) par une
commande stable — `mmi-pm <cmd>` (→ `/usr/bin/mmi-pm` une fois packagé).

    mmi-pm task-add --title …        ->  pm-task-add.py --title …
    mmi-pm session-status refresh    ->  pm-session-status.py refresh
    mmi-pm --list                    ->  liste les sous-commandes disponibles
    mmi-pm task-show 2580            ->  pm-task-show.py 2580

Résolution du code (priorité) : $PM_CORE_DIR/scripts (relocalisable, cohérent
avec pm_paths), sinon le dossier de CE script (auto-localisation robuste : un
symlink /usr/bin/mmi-pm → …/scripts/mmi-pm.py est suivi par resolve()).

Périmètre 3a : le dispatcher exécute en identité de L'APPELANT (transparent,
via os.execv — cwd/env/tty/signaux/exit-code conservés). La MUTATION de
structure (niveaux `pm 2750`, cf. RM2502) passera par le DAEMON `pm` (transport
(c), auth SO_PEERCRED) — le dispatcher route déjà, le transport privilégié se
branche derrière SANS changer l'interface d'appel.
"""
import os
import sys
from pathlib import Path

_core = os.environ.get("PM_CORE_DIR")
SCRIPTS = (Path(_core).expanduser().resolve() / "scripts") if _core \
    else Path(__file__).resolve().parent


def _candidates(cmd: str):
    """`mmi-pm <cmd>` → `pm-<cmd>.py` puis `pm-<cmd>` (scripts sans extension)."""
    return [SCRIPTS / f"pm-{cmd}.py", SCRIPTS / f"pm-{cmd}"]


def _list_commands():
    """Sous-commandes = scripts `pm-*` (hors modules `pm_*`, hors tests)."""
    cmds = set()
    for p in SCRIPTS.glob("pm-*"):
        if not p.is_file() or "test" in p.name or p.suffix not in ("", ".py"):
            continue
        cmds.add(p.stem[3:] if p.suffix == ".py" else p.name[3:])
    return sorted(cmds)


def _exec(target: Path, rest):
    """Remplace le process courant par la sous-commande (transparent)."""
    if target.suffix == ".py":
        os.execv(sys.executable, [sys.executable, str(target), *rest])
    else:  # script exécutable sans extension (shebang propre)
        os.execv(str(target), [str(target), *rest])


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("usage: mmi-pm <cmd> [args…]   |   mmi-pm --list", file=sys.stderr)
        print(f"  (code PM résolu : {SCRIPTS})", file=sys.stderr)
        return 0
    if argv[0] == "--list":
        print("\n".join(_list_commands()))
        return 0

    cmd, rest = argv[0], argv[1:]
    for target in _candidates(cmd):
        if target.is_file():
            _exec(target, rest)  # ne revient pas (execv)
    sys.exit(
        f"mmi-pm : sous-commande inconnue '{cmd}' "
        f"(pas de {SCRIPTS}/pm-{cmd}[.py]) — voir `mmi-pm --list`"
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
