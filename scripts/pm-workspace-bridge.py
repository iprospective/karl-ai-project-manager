#!/usr/bin/env python3
"""pm-workspace-bridge — pose et tient à jour le pont d'onboarding des workspaces (RM1892).

Un agent lancé dans un workspace de code n'a, par défaut, aucun contexte PM. Le pont
est un fichier UNIQUE à la racine des workspaces, lu par **remontée d'arborescence**
depuis n'importe quel sous-dossier :

    <racine>/AGENTS.md          # vendor-neutral (opencode & co)
    <racine>/CLAUDE.md → AGENTS.md   # Claude Code ne lit que CLAUDE.md, mais suit les symlinks

Il dit à l'agent : « si ton workspace a un `.mmi-pm`, tu es un worker PM — résous-le,
lis le KERNEL, applique le protocole ; sinon, ces règles ne te concernent pas. »

Ce fichier est **hors git** : c'est un artefact de provisioning, propre à chaque
instance de la fédération. Sa référence versionnée est `templates/workspace-AGENTS.md`.
D'où ce script : sans lui, « garder les deux synchrones » est un vœu — et l'instance
dérive en silence sur un onboarding périmé.

**Le bloc INSTANCE** (`<!-- BEGIN INSTANCE … -->` … `<!-- END INSTANCE -->`) est la part
machine : chemins, hôtes, transport git, état des agents. `--update` le **préserve
verbatim** et ne rafraîchit que le reste. C'est ce qui rend une mise à jour d'onboarding
jouable sur une instance sans lui faire perdre ce qu'elle sait d'elle-même.

Usage :
    pm-workspace-bridge.py                 # contrôle : présent ? à jour ? (exit 1 si non)
    pm-workspace-bridge.py --install       # première pose (fichier + symlink)
    pm-workspace-bridge.py --update        # rafraîchit le générique, garde le bloc INSTANCE
    pm-workspace-bridge.py --root /chemin  # autre racine (défaut : parent du repo PM)
    …--dry-run                             # montre, n'écrit pas

Exit : 0 tout va bien / 1 il y a un geste à faire (ou une écriture a échoué).
"""
import argparse
import difflib
import os
import re
import shutil
import sys
import time
from pathlib import Path

BEGIN = "<!-- BEGIN INSTANCE"
END = "<!-- END INSTANCE -->"
HEADER_RE = re.compile(r"\A<!--.*?-->\n", re.S)      # commentaire d'en-tête du template


def template_path() -> Path:
    return Path(__file__).resolve().parent.parent / "templates" / "workspace-AGENTS.md"


def default_root() -> Path:
    """Racine des workspaces = le dossier qui CONTIENT les workspaces.

    Déduite du repo PM lui-même (…/<racine>/<groupe>/<repo>) plutôt que codée en dur :
    une instance de la fédération n'a aucune raison d'utiliser `/zfs/workspaces`.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".mmi-pm-core").exists() or (parent / "AGENTS.md").is_file():
            return parent
    return Path("/zfs/workspaces")


# >>> split_instance — pure (testée par test_pm_workspace_bridge.py)
def split_instance(text):
    """(avant, bloc_instance, après) d'un contenu de pont.

    Le bloc rendu inclut ses marqueurs : le recoller suffit à reconstruire le fichier.
    Sans marqueurs → (texte, None, "") : on ne devine pas où commence la part machine.
    """
    if not text:
        return "", None, ""
    i = text.find(BEGIN)
    if i < 0:
        return text, None, ""
    j = text.find(END, i)
    if j < 0:
        return text, None, ""
    j += len(END)
    return text[:i], text[i:j], text[j:]
# <<< split_instance


# >>> generic_part — pure (testée par test_pm_workspace_bridge.py)
def generic_part(text):
    """Le texte SANS sa part machine ni l'en-tête de template — ce qui doit être
    identique entre le template et le fichier déployé. C'est la seule comparaison
    qui a du sens : le bloc INSTANCE diffère par construction, et l'en-tête du
    template ne part jamais sur l'instance."""
    text = HEADER_RE.sub("", text or "", count=1)
    before, block, after = split_instance(text)
    return (before + after).strip() + "\n"
# <<< generic_part


def render(template_text: str, instance_block: str | None) -> str:
    """Contenu à déployer : le template sans son en-tête, avec le bloc INSTANCE
    de la machine s'il en a déjà un (sinon celui du template, qui sert de gabarit)."""
    body = HEADER_RE.sub("", template_text, count=1)
    if instance_block is None:
        return body
    before, _, after = split_instance(body)
    return before + instance_block + after


def report(label: str, ok: bool, detail: str = "", fix: str = "") -> bool:
    print(f"  {'✓' if ok else '✗'} {label}" + (f" — {detail}" if detail else ""))
    if not ok and fix:
        print(f"      → {fix}")
    return ok


def cmd_check(root: Path, tpl: str, verbose: bool) -> int:
    agents, claude = root / "AGENTS.md", root / "CLAUDE.md"
    print(f"── pont d'onboarding — {root} ──")
    ok = True
    if not agents.is_file():
        report("AGENTS.md", False, "absent",
               f"pm-workspace-bridge.py --root {root} --install")
        return 1
    deployed = agents.read_text(encoding="utf-8", errors="replace")
    report("AGENTS.md", True, f"{len(deployed.splitlines())} lignes")

    if claude.is_symlink() and os.readlink(claude) == "AGENTS.md":
        report("CLAUDE.md → AGENTS.md", True)
    else:
        ok = report("CLAUDE.md → AGENTS.md", False,
                    "symlink absent (Claude Code ne lit QUE CLAUDE.md)",
                    f"ln -s AGENTS.md {claude}") and ok

    _, block, _ = split_instance(deployed)
    if block is None:
        ok = report("bloc INSTANCE", False,
                    "non délimité — une mise à jour écraserait la part machine",
                    f"pm-workspace-bridge.py --root {root} --update  "
                    f"(puis re-délimiter à la main ce qui est propre à la machine)") and ok
    else:
        report("bloc INSTANCE", True, f"{len(block.splitlines())} lignes préservées")

    a, b = generic_part(deployed), generic_part(tpl)
    if a == b:
        report("partie générique", True, "identique au template versionné")
    else:
        ok = report("partie générique", False, "a dérivé du template",
                    f"pm-workspace-bridge.py --root {root} --update") and ok
        if verbose:
            print("".join(difflib.unified_diff(
                b.splitlines(keepends=True), a.splitlines(keepends=True),
                fromfile="template", tofile="déployé", n=1))[:4000])
    return 0 if ok else 1


def write_bridge(root: Path, content: str, dry: bool, backup_of: Path | None) -> bool:
    agents, claude = root / "AGENTS.md", root / "CLAUDE.md"
    if dry:
        print(f"  [dry] écrirait {agents} ({len(content.splitlines())} lignes)")
        if not claude.exists():
            print(f"  [dry] créerait le symlink {claude} → AGENTS.md")
        return True
    if backup_of and backup_of.is_file():
        bak = backup_of.with_suffix(f".md.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(backup_of, bak)
        print(f"  · sauvegarde : {bak}")
    try:
        agents.write_text(content, encoding="utf-8")
    except OSError as e:
        print(f"  ✗ écriture impossible : {e}", file=sys.stderr)
        print(f"      → droits sur {root} ? (le pont appartient au provisioning)",
              file=sys.stderr)
        return False
    print(f"  ✓ {agents}")
    if claude.is_symlink() or claude.exists():
        return True
    try:
        claude.symlink_to("AGENTS.md")
        print(f"  ✓ {claude} → AGENTS.md")
    except OSError as e:
        print(f"  ⚠ symlink non créé ({e.__class__.__name__}) — à poser : "
              f"ln -s AGENTS.md {claude}", file=sys.stderr)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=lambda s: Path(s).resolve(), default=None,
                    help="racine des workspaces (défaut : déduite du repo PM)")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--install", action="store_true", help="première pose")
    grp.add_argument("--update", action="store_true",
                     help="rafraîchit le générique, préserve le bloc INSTANCE")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="montre le diff de dérive")
    args = ap.parse_args()

    root = args.root or default_root()
    tpl_file = template_path()
    if not tpl_file.is_file():
        print(f"✗ template introuvable : {tpl_file}", file=sys.stderr)
        return 1
    tpl = tpl_file.read_text(encoding="utf-8")
    agents = root / "AGENTS.md"

    if args.install:
        if agents.is_file():
            print(f"✗ {agents} existe déjà — utiliser --update (qui préserve le bloc "
                  f"INSTANCE) plutôt que d'écraser une part machine.", file=sys.stderr)
            return 1
        if not root.is_dir():
            print(f"✗ racine inexistante : {root}", file=sys.stderr)
            return 1
        print(f"── pose du pont — {root} ──")
        return 0 if write_bridge(root, render(tpl, None), args.dry_run, None) else 1

    if args.update:
        if not agents.is_file():
            print(f"✗ {agents} absent — utiliser --install", file=sys.stderr)
            return 1
        deployed = agents.read_text(encoding="utf-8", errors="replace")
        _, block, _ = split_instance(deployed)
        print(f"── mise à jour du pont — {root} ──")
        if block is None:
            print("  ⚠ aucun bloc INSTANCE dans le fichier déployé : la part machine "
                  "n'est pas délimitée.")
            print("    Le générique du template va être posé et l'ancien fichier "
                  "sauvegardé — reporte à la main ce qui est propre à la machine "
                  "entre les marqueurs BEGIN/END INSTANCE.")
        return 0 if write_bridge(root, render(tpl, block), args.dry_run, agents) else 1

    return cmd_check(root, tpl, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
