#!/usr/bin/env python3
"""Tests RM2582 — la précharge NORMS ne doit contenir que des règles.

Le budget de contexte « toujours chargé » avait atteint son plafond à 2 tokens
près : le garde-fou ne signalait plus une dérive, il bloquait l'écriture de la
prochaine règle. Le dégraissage a sorti mode d'emploi et cas particuliers de la
précharge (ils s'ouvrent par déclencheur). Ces tests empêchent le retour en
arrière — silencieux, sinon : un module qui grossit ne prévient personne.

Lancer : python3 scripts/test_norms_precharge.py
"""
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "norms" / "src"
MODULES = SRC / "modules"

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


PRELOAD_RE = re.compile(r"\*\*Préchargé par :\*\*\s*(.+?)\.?\s*$")


def preloaded(path):
    """Rôles déclarés dans l'en-tête, ou [] si le module est hors précharge."""
    for line in path.read_text(encoding="utf-8").splitlines()[:4]:
        m = PRELOAD_RE.search(line)
        if m:
            who = m.group(1)
            if "personne" in who or "*(" in who:
                return []
            return [w.strip().rstrip(".") for w in who.split(",")]
    return []


# — les modules détachés ne doivent JAMAIS revenir dans la précharge —
for nom in ("git-mep-pratique.md", "status-workflow-pratique.md"):
    p = MODULES / nom
    check(f"{nom} existe", p.is_file())
    if p.is_file():
        check(f"{nom} reste hors précharge", preloaded(p) == [])

# — chaque module détaché est atteignable par un déclencheur du KERNEL, sinon
#   son contenu devient invisible : sorti de la précharge ET jamais ouvert —
kernel = (SRC / "NORMS-KERNEL.md").read_text(encoding="utf-8")
for nom in ("git-mep-pratique.md", "status-workflow-pratique.md"):
    check(f"{nom} a un déclencheur au KERNEL", nom in kernel)

# — et il est assemblé dans NORMS.md (sinon il disparaît de la doc complète) —
manifest = (SRC / "manifest.yml").read_text(encoding="utf-8")
for nom in ("git-mep-pratique.md", "status-workflow-pratique.md"):
    check(f"{nom} est au manifeste d'assemblage", nom in manifest)

# — le budget doit rester sous le plafond, avec une marge réelle —
r = subprocess.run([sys.executable, str(HERE / "pm-context-budget.py"), "--check"],
                   capture_output=True, text=True)
check("pm-context-budget --check passe", r.returncode == 0)
pires = [int(m.group(1).replace(",", ""))
         for m in re.finditer(r"^\S+\s+([\d,]+)", r.stdout, re.M)]
plafond = int(re.search(r"^\s*default: (\d+)", (ROOT / "pm.config.yml").read_text(encoding="utf-8"),
                        re.M).group(1))
if pires:
    check(f"marge ≥ 10 % sous le plafond ({max(pires)} / {plafond})",
          max(pires) <= plafond * 0.9)

# — garde-fou de fond : aucun module préchargé ne doit dépasser 5 000 tokens.
#   Au-delà, c'est qu'on y a remis du mode d'emploi. —
gros = []
for p in sorted(MODULES.glob("*.md")):
    if preloaded(p):
        tok = round(p.stat().st_size / 3.6)
        if tok > 5000:
            gros.append(f"{p.name} ({tok})")
check("aucun module préchargé ne dépasse 5 000 tokens" + (" — " + ", ".join(gros) if gros else ""),
      not gros)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests précharge NORMS RM2582 passent")
