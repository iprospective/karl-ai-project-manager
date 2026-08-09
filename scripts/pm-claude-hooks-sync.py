#!/usr/bin/env python3
"""pm-claude-hooks-sync — installe le bloc de hooks PM dans le settings.json Claude Code.

Le tracking de conso IA (NORMS § ROI assisté par IA) repose sur des hooks Claude
Code au niveau du profil utilisateur (`~/.claude/settings.json`) : sans eux, les
sessions interactives ne tickent pas (tokens_total=0 sur les tickets — RM2306).
Ce settings.json est un artefact de provisioning d'instance, hors git : après une
réinstallation / migration de profil, le bloc hooks disparaît silencieusement.

Ce script (ré)installe idempotemment le bloc hooks PM, sans toucher au reste du
fichier (model, theme, hooks non-PM comme un sync de sessions propre à la machine…).
Les commandes émises sont `mmi-pm <cmd>` (RM2580) : PATH-résolu, RELOCALISABLE — un
déménagement du code (/opt, paquet) ne casse pas les hooks, seul le symlink PATH de
mmi-pm change. Prérequis : `mmi-pm` sur le PATH (root, une fois :
`ln -sfn <core>/scripts/mmi-pm.py /usr/local/bin/mmi-pm`).

Usage :
  pm-claude-hooks-sync.py               # installe les hooks manquants (forme mmi-pm)
  pm-claude-hooks-sync.py --migrate     # convertit les hooks abs-path existants → mmi-pm
  pm-claude-hooks-sync.py --dry-run     # montre les actions sans rien modifier
  pm-claude-hooks-sync.py --check       # exit 1 si un hook PM manque (pour pm-doctor)
  pm-claude-hooks-sync.py --settings F  # fichier settings cible (défaut: ~/.claude/settings.json)
  pm-claude-hooks-sync.py --pm-root D   # racine PM où VÉRIFIER la présence des scripts cibles
                                        # (les commandes émises restent `mmi-pm <cmd>`)

Garde-fous :
  - présence détectée par nom de script (un hook déjà câblé via un autre chemin —
    p. ex. l'alias historique ai/project-management — est laissé tel quel) ;
  - n'écrase ni ne supprime jamais un hook existant ; ajout seulement ;
  - backup `settings.json.pm-hooks-sync.bak` avant toute écriture.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

PM_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PM_ROOT / "scripts"

# Bloc hooks PM canonique : (événement, matcher, script, args, timeout).
# matcher=None → pas de clé matcher (événements non filtrables).
PM_HOOKS = [
    # mesure ai_time : début de tour…
    ("UserPromptSubmit", None, "pm-turn-start.py", "", None),
    # …pause pendant les questions à l'utilisateur…
    ("PreToolUse", "AskUserQuestion|ExitPlanMode", "pm-turn-wait.py", " start", None),
    ("PostToolUse", "AskUserQuestion|ExitPlanMode", "pm-turn-wait.py", " stop", None),
    # …tick conso par tour (frontmatter + note Redmine)
    ("Stop", "", "pm-task-tick.py", "", None),
    # report conso consolidé en fin de session
    ("SessionEnd", None, "pm-task-report.py", " --all --apply", 180),
    # worklog de session (RM2068) : refresh au démarrage et avant compaction
    ("SessionStart", None, "pm-session-status.py", " refresh &>/dev/null || true", 30),
    ("PreCompact", None, "pm-session-status.py", " refresh &>/dev/null || true", 30),
]


def _cmd_name(script_name: str) -> str:
    """Sous-commande mmi-pm depuis le nom de script : pm-session-status.py → session-status."""
    n = script_name[3:] if script_name.startswith("pm-") else script_name
    return n[:-3] if n.endswith(".py") else n


def _mmi_command(script_name: str, args_str: str) -> str:
    """Commande de hook via le dispatcher RELOCALISABLE (RM2580) : `mmi-pm <cmd>[ args]`.
    Survit au déménagement du code (/opt, paquet) — seul le symlink PATH de mmi-pm bouge."""
    return f"mmi-pm {_cmd_name(script_name)}{args_str}"


def event_has_script(groups, script_name: str) -> bool:
    """Vrai si un hook de l'événement référence déjà ce script — forme `mmi-pm <cmd>`
    OU ancienne forme abs-path `…/pm-<cmd>.py` (peu importe le chemin)."""
    new_form = f"mmi-pm {_cmd_name(script_name)}"
    for group in groups or []:
        for hook in group.get("hooks", []):
            cmd = hook.get("command", "")
            if script_name in cmd or new_form in cmd:
                return True
    return False


def build_group(matcher, script_name, args_str, timeout):
    hook = {"type": "command", "command": _mmi_command(script_name, args_str)}
    if timeout is not None:
        hook["timeout"] = timeout
    group = {}
    if matcher is not None:
        group["matcher"] = matcher
    group["hooks"] = [hook]
    return group


def main() -> int:
    ap = argparse.ArgumentParser(description="Installe le bloc hooks PM dans le settings.json Claude Code.")
    ap.add_argument("--settings", type=Path, default=Path.home() / ".claude" / "settings.json",
                    help="Fichier settings cible (défaut: ~/.claude/settings.json)")
    ap.add_argument("--dry-run", action="store_true", help="Affiche sans modifier.")
    ap.add_argument("--check", action="store_true",
                    help="Vérifie seulement : exit 1 si un hook PM manque (aucune écriture).")
    ap.add_argument("--pm-root", type=Path, default=None,
                    help="Racine PM où VÉRIFIER la présence des scripts cibles (défaut: le repo "
                         "de ce script). N.B. les commandes émises sont `mmi-pm <cmd>` "
                         "(PATH-résolu, relocalisable) — ce chemin ne sert qu'au contrôle d'existence.")
    ap.add_argument("--migrate", action="store_true",
                    help="Convertit les hooks PM existants de l'ancienne forme abs-path "
                         "…/pm-<cmd>.py vers `mmi-pm <cmd>` (relocalisable). Backup avant écriture.")
    args = ap.parse_args()

    global SCRIPTS
    if args.pm_root:
        SCRIPTS = args.pm_root.expanduser().resolve() / "scripts"
    if not args.check:
        absent = list(dict.fromkeys(s for _, _, s, _, _ in PM_HOOKS
                                    if not (SCRIPTS / s).is_file()))
        if absent:
            print(f"✗ scripts introuvables sous {SCRIPTS} : {', '.join(absent)} — "
                  f"rien ne sera câblé (mauvais --pm-root ? core pas déployé ?)")
            return 1
        # Les hooks émis appellent `mmi-pm <cmd>` → mmi-pm DOIT être résoluble au runtime
        # des hooks. Refuse de câbler/migrer sinon (aperçu seul autorisé en --dry-run).
        if not shutil.which("mmi-pm"):
            msg = ("'mmi-pm' introuvable sur le PATH — les hooks ne résoudraient pas.\n"
                   "  Installe (root, une fois) : "
                   "sudo ln -sfn <core>/scripts/mmi-pm.py /usr/local/bin/mmi-pm")
            if not args.dry_run:
                print("✗ " + msg)
                return 1
            print("⚠ " + msg + "\n  (--dry-run : aperçu quand même)")

    settings_path = args.settings.expanduser()
    settings = {}
    if settings_path.is_file():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"✗ {settings_path} illisible ({e}) — rien ne sera modifié.")
            return 1

    hooks_cfg = settings.setdefault("hooks", {})

    # Migration (opt-in) : réécrit les hooks PM existants de l'ancienne forme abs-path
    # vers `mmi-pm <cmd>`. AVANT le calcul des manquants (un migré compte présent).
    migrated = []
    if args.migrate and not args.check:
        for event, matcher, script_name, args_str, timeout in PM_HOOKS:
            new_cmd = _mmi_command(script_name, args_str)
            for group in hooks_cfg.get(event, []):
                for hook in group.get("hooks", []):
                    cmd = hook.get("command", "")
                    if script_name in cmd and not cmd.startswith("mmi-pm "):
                        hook["command"] = new_cmd
                        migrated.append((event, script_name))
        for event, script_name in migrated:
            print(f"~ migré {event} → {_mmi_command(script_name, '')}")

    missing, present = [], 0
    for event, matcher, script_name, args_str, timeout in PM_HOOKS:
        if event_has_script(hooks_cfg.get(event), script_name):
            present += 1
            continue
        missing.append((event, matcher, script_name, args_str, timeout))

    label = f"{settings_path} : {present} hook(s) PM présent(s), {len(missing)} manquant(s)"
    if args.check:
        print(("✗ " if missing else "✓ ") + label)
        for event, _, script_name, _, _ in missing:
            print(f"  - {event} → {script_name}")
        return 1 if missing else 0

    if not missing and not migrated:
        print(f"✓ {label} — rien à faire.")
        return 0

    for event, matcher, script_name, args_str, timeout in missing:
        print(f"+ {event}{f' [{matcher}]' if matcher else ''} → {_mmi_command(script_name, args_str)}")
        hooks_cfg.setdefault(event, []).append(build_group(matcher, script_name, args_str, timeout))

    if args.dry_run:
        print(f"\n[dry-run] {len(migrated)} migré(s) + {len(missing)} à ajouter dans "
              f"{settings_path} — rien écrit.")
        return 0

    if settings_path.is_file():
        shutil.copy2(settings_path, settings_path.with_suffix(".json.pm-hooks-sync.bak"))
    else:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    print(f"\n✓ {len(migrated)} migré(s), {len(missing)} ajouté(s) dans {settings_path} "
          f"(backup .pm-hooks-sync.bak). Actifs à la prochaine session.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
