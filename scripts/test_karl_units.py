#!/usr/bin/env python3
"""Tests RM3070 L1 — les units systemd de karl ne portent plus de chemin en dur.

Elles portent `@PM_ROOT@`, que `deploy/karl-agent/install.sh` (et `karl-voice-setup.sh`) rend à
la pose. Ce test rend chaque unit sur CE dépôt et vérifie qu'elle vise des fichiers qui existent.

Lancer : python3 scripts/test_karl_units.py
"""
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
UNITS = sorted((REPO / "deploy" / "karl-agent").glob("*.service")) + \
        sorted((REPO / "deploy" / "karl-agent").glob("*.timer"))
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


print("[L1] plus aucun chemin d'instance en dur")
durs = [u.name for u in UNITS if "/zfs/workspaces" in u.read_text(encoding="utf-8")]
check("aucune unit ne cite /zfs/workspaces — elle ne s'installerait nulle part ailleurs", not durs, durs)

print("\n[L1] le rendu vise des fichiers réels")
for u in UNITS:
    rendu = u.read_text(encoding="utf-8").replace("@PM_ROOT@", str(REPO))
    rendu = "\n".join(l for l in rendu.splitlines() if not l.lstrip().startswith("#"))  # un commentaire ne lance rien
    chemins = re.findall(re.escape(str(REPO)) + r"[^\s;\"']*", rendu)
    absents = [c for c in chemins if not pathlib.Path(c.rstrip("/")).exists()]
    check(f"{u.name} : {len(chemins)} chemin(s) rendu(s), tous existants", not absents, absents)

print("\n[L1] ce qui ne doit jamais se perdre en templatant")
ka = (REPO / "deploy" / "karl-agent" / "karl-agent.service").read_text(encoding="utf-8")
check("karl-agent.service garde KillMode=process — sinon un restart tue toutes les sessions tmux",
      re.search(r"^KillMode=process$", ka, re.M))
inst = (REPO / "deploy" / "karl-agent" / "install.sh").read_text(encoding="utf-8")
check("install.sh ne COPIE plus d'unit : il les rend toutes",
      not re.search(r'^cp "\$UNIT_SRC/[^"]+\.(service|timer)"', inst, re.M))
check("install.sh refuse une unit restée avec @PM_ROOT@", 'grep -q "@PM_ROOT@"' in inst)
r = subprocess.run(["bash", "-n", str(REPO / "deploy" / "karl-agent" / "install.sh")], capture_output=True)
check("install.sh est un bash valide", r.returncode == 0, r.stderr)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — units karl sans chemin en dur (RM3070 L1)"))
sys.exit(1 if FAIL else 0)
