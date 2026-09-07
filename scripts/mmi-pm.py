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
    mmi-pm core update               ->  pm-core-update.py   (RM3033 : `<nom> <verbe>` → `pm-<nom>-<verbe>`, l'ancienne
                                                              grammaire de bin/mmi-pm reste valide ; sudo demandé par le verbe)
    mmi-core update / mmi-task add … ->  un lien `mmi-<domaine>` vers ce script préfixe le domaine

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
    """Sous-commandes = scripts `pm-*` (les modules `pm_*` ne matchent pas le glob).

    Le filtre portait sur « test » n'importe où dans le nom : il masquait des
    verbes réels — `mmi-pm test` (la suite, RM2749) et `mmi-pm cockpit-test-env`
    fonctionnaient sans jamais apparaître dans `--list`. Les fichiers de test
    s'appellent `test_*.py` : ils ne peuvent pas matcher `pm-*`.
    """
    cmds = set()
    for p in SCRIPTS.glob("pm-*"):
        if not p.is_file() or p.suffix not in ("", ".py"):
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
        prefix = (argv[1] + "-") if len(argv) > 1 else ""
        print("\n".join(c for c in _list_commands() if c.startswith(prefix)))
        return 0

    cmd, rest = argv[0], argv[1:]
    target, rest = resolve(cmd, rest)
    if target:
        _exec(target, rest)  # ne revient pas (execv)
    sys.exit(
        f"mmi-pm : sous-commande inconnue '{cmd}' "
        f"(pas de {SCRIPTS}/pm-{cmd}[.py]) — voir `mmi-pm --list`"
    )


def resolve(cmd: str, rest):
    """`<cmd>` → `pm-<cmd>` ; sinon (RM3033) `<nom> <verbe>` → `pm-<nom>-<verbe>` : la grammaire historique de bin/mmi-pm
    (`core update`, `index add`, `env vhost`, `hooks install`, `norms version`) reste valide sans dupliquer un routeur."""
    for target in _candidates(cmd):
        if target.is_file():
            return target, list(rest)
    if rest and rest[0] and not rest[0].startswith("-"):
        for target in _candidates(f"{cmd}-{rest[0]}"):
            if target.is_file():
                return target, list(rest[1:])
    return None, list(rest)


def argv_for(prog: str, argv):
    """RM3033 : un lien `mmi-<domaine>` vers ce script préfixe le domaine — `mmi-core update` ≡ `mmi-pm core-update`,
    `mmi-task show 42` ≡ `mmi-pm task-show 42` ; `mmi-<domaine>` seul liste les verbes du domaine."""
    name = Path(prog).name
    if name.endswith(".py"):
        name = name[:-3]
    if not name.startswith("mmi-") or name == "mmi-pm":
        return list(argv)
    domain = name[4:]
    if not argv or argv[0] in ("--list", "-h", "--help", "help"):
        return ["--list", domain]
    return [f"{domain}-{argv[0]}", *argv[1:]]


if __name__ == "__main__":
    sys.exit(main(argv_for(sys.argv[0], sys.argv[1:])))
