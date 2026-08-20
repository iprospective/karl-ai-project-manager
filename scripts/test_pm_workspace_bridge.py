#!/usr/bin/env python3
"""Tests RM1892 — pont d'onboarding des workspaces (AGENTS.md + symlink CLAUDE.md).

Ce qui compte : qu'une mise à jour de l'onboarding NE PERDE JAMAIS ce que l'instance
sait d'elle-même (chemins, hôtes, transport git). Tout se joue sur une racine
temporaire — le pont de la machine n'est jamais touché.

Lancer : python3 scripts/test_pm_workspace_bridge.py
"""
import importlib.util
import io
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("bridge", str(_HERE / "pm-workspace-bridge.py"))
b = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def run(argv):
    """Lance main() avec argv, rend (code, stdout+stderr)."""
    out, err = io.StringIO(), io.StringIO()
    old = sys.argv
    sys.argv = ["pm-workspace-bridge.py"] + argv
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = b.main()
    finally:
        sys.argv = old
    return code, out.getvalue() + err.getvalue()


# ── découpage : où s'arrête le générique, où commence la machine ─────────────
doc = ("entête\n" + b.BEGIN + " -->\nchemins de la machine\n" + b.END + "\nsuite\n")
before, block, after = b.split_instance(doc)
check("bloc INSTANCE isolé avec ses marqueurs",
      block.startswith(b.BEGIN) and block.endswith(b.END) and "chemins de la machine" in block)
check("le générique encadre le bloc", before == "entête\n" and after == "\nsuite\n")
check("sans marqueurs, on ne devine pas la part machine",
      b.split_instance("juste du texte") == ("juste du texte", None, ""))
check("marqueur d'ouverture sans fermeture → pas de bloc",
      b.split_instance("a\n" + b.BEGIN + " -->\nb\n")[1] is None)

g1 = b.generic_part("<!--\n en-tête de template\n-->\n" + doc)
g2 = b.generic_part(doc.replace("chemins de la machine", "UNE AUTRE MACHINE"))
check("deux instances différentes ont le MÊME générique", g1 == g2)
check("l'en-tête du template ne compte pas dans le générique",
      "en-tête de template" not in g1)

# ── pose puis mise à jour : la part machine survit ───────────────────────────
tmp = Path(tempfile.mkdtemp(prefix="rm1892-"))
root = tmp / "workspaces"
root.mkdir()

code, out = run(["--root", str(root)])
check("contrôle : pont absent → geste à faire (exit 1)", code == 1 and "absent" in out)
check("contrôle : dit comment le poser", "--install" in out)

code, out = run(["--root", str(root), "--install", "--dry-run"])
check("pose en dry-run : n'écrit rien",
      code == 0 and not (root / "AGENTS.md").exists() and "[dry]" in out)

code, out = run(["--root", str(root), "--install"])
agents, claude = root / "AGENTS.md", root / "CLAUDE.md"
check("pose : AGENTS.md écrit", code == 0 and agents.is_file())
check("pose : CLAUDE.md est un symlink RELATIF vers AGENTS.md",
      claude.is_symlink() and os.readlink(claude) == "AGENTS.md")
posed = agents.read_text(encoding="utf-8")
check("pose : l'en-tête de template ne part pas sur l'instance",
      not posed.startswith("<!--\n  SOURCE CANONIQUE"))
check("pose : le fichier porte la condition d'onboarding", ".mmi-pm" in posed)
check("pose : le bloc INSTANCE est présent comme gabarit",
      b.split_instance(posed)[1] is not None)

code, out = run(["--root", str(root), "--install"])
check("pose sur un pont existant : REFUSÉE (n'écrase pas la part machine)",
      code == 1 and "--update" in out)

# l'instance personnalise SON bloc, puis on met à jour
perso = posed.replace("_(Section à renseigner au provisioning de l'instance",
                      "hostname = box-maison ; PM dans /srv/pm\n_(Section à renseigner")
agents.write_text(perso, encoding="utf-8")
code, out = run(["--root", str(root)])
check("contrôle : pont posé et à jour → exit 0", code == 0)
check("contrôle : le bloc INSTANCE est compté", "préservées" in out)

code, out = run(["--root", str(root), "--update"])
after_update = agents.read_text(encoding="utf-8")
check("mise à jour : la part machine est PRÉSERVÉE",
      "hostname = box-maison ; PM dans /srv/pm" in after_update)
check("mise à jour : une sauvegarde est laissée",
      any(p.name.startswith("AGENTS.md.bak-") or ".bak-" in p.name
          for p in root.iterdir()))

# dérive du générique : détectée, et corrigée sans perdre la machine
agents.write_text(after_update.replace("## Protocole quand on te confie une tâche",
                                       "## Protocole (version bricolée sur place)"),
                  encoding="utf-8")
code, out = run(["--root", str(root)])
check("contrôle : dérive du générique détectée", code == 1 and "dérivé" in out)
code, out = run(["--root", str(root), "--update"])
fixed = agents.read_text(encoding="utf-8")
check("mise à jour : le générique est rétabli",
      "## Protocole quand on te confie une tâche" in fixed)
check("mise à jour : la machine est toujours là",
      "hostname = box-maison ; PM dans /srv/pm" in fixed)

# un pont sans marqueurs (le cas des instances d'avant RM1892) : prévenir, sauvegarder
legacy = root / "legacy"
legacy.mkdir()
(legacy / "AGENTS.md").write_text("# vieux pont\nsans marqueurs, plein de chemins locaux\n",
                                  encoding="utf-8")
code, out = run(["--root", str(legacy)])
check("pont hérité : absence de délimitation signalée", code == 1 and "non délimité" in out)
code, out = run(["--root", str(legacy), "--update"])
check("pont hérité : la mise à jour PRÉVIENT avant de reprendre la main",
      "reporte à la main" in out)
check("pont hérité : l'ancien fichier est sauvegardé",
      any(".bak-" in p.name for p in legacy.iterdir()))

shutil.rmtree(tmp, ignore_errors=True)
print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("✓ tous les tests passent")
