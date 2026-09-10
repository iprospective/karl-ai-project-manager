#!/usr/bin/env python3
"""Tests RM3071 — le KERNEL revient dans le contexte après une compaction.

Ce qui doit tenir : le rappel porte le KERNEL EN ENTIER (pas un lien vers lui), il préfère la version dense
quand elle existe, il dit pourquoi il arrive, il ne casse jamais la session qui reprend quand il n'a rien à
dire, et il est câblé dans le bloc de hooks canonique — donc posé à l'installation et vu par le contrôle.
"""
import importlib.util
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("nr", HERE / "pm-norms-recall.py")
NR = importlib.util.module_from_spec(spec); spec.loader.exec_module(NR)
sys.path.insert(0, str(HERE))
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def faux_depot(runtime=True, source=True):
    d = pathlib.Path(tempfile.mkdtemp())
    if runtime:
        (d / "norms" / "runtime").mkdir(parents=True)
        (d / "norms" / "runtime" / "KERNEL.md").write_text("KERNEL DENSE\ngarde-fou 1 : outillage\n")
    if source:
        (d / "norms" / "src").mkdir(parents=True)
        (d / "norms" / "src" / "NORMS-KERNEL.md").write_text("KERNEL HUMAIN\ntripwire 1\n")
    return d


print("[RM3071] quel KERNEL est redonné")
d = faux_depot()
check("la version dense est préférée quand elle existe", NR.kernel_path(d).name == "KERNEL.md"
      and "runtime" in str(NR.kernel_path(d)))
check("sans version dense, la source humaine fait l'affaire",
      NR.kernel_path(faux_depot(runtime=False)).parent.name == "src")
check("aucun KERNEL : rien à redonner, et on le dit", NR.kernel_path(faux_depot(False, False)) is None)

print("\n[RM3071] ce que contient le rappel")
r = NR.rappel("compact", root=d)
check("le KERNEL est redonné EN ENTIER, pas en lien", "garde-fou 1 : outillage" in r)
check("le rappel dit POURQUOI il arrive", "compact" in r.lower() and "normes" in r.lower())
check("il nomme sa source, pour qu'on puisse y retourner", "norms/runtime/KERNEL.md" in r)
check("--plain rend le KERNEL nu, sans en-tête", NR.rappel("compact", plain=True, root=d).startswith("KERNEL DENSE"))
check("une reprise se dit autrement qu'une compaction",
      "reprend" in NR.rappel("resume", root=d) and "reprend" not in NR.rappel("compact", root=d))
check("sans KERNEL, le rappel est vide plutôt qu'inventé", NR.rappel("compact", root=faux_depot(False, False)) == "")

print("\n[RM3071] un hook ne casse jamais la session qui reprend")
vide = faux_depot(False, False)
p = subprocess.run([sys.executable, str(HERE / "pm-norms-recall.py"), "--root", str(vide)],
                   capture_output=True, text=True)
check("aucun KERNEL : sortie muette et code 0", p.returncode == 0 and p.stdout.strip() == "", p.stderr[-120:])
p = subprocess.run([sys.executable, str(HERE / "pm-norms-recall.py"), "--root", str(vide), "--check"],
                   capture_output=True, text=True)
check("--check, lui, signale l'absence (c'est son rôle)", p.returncode == 1)
p = subprocess.run([sys.executable, str(HERE / "pm-norms-recall.py"), "--path", "--root", str(d)],
                   capture_output=True, text=True)
check("--path ne rend que le chemin", p.returncode == 0 and p.stdout.strip().endswith("runtime/KERNEL.md"))

print("\n[RM3071] le rappel du VRAI dépôt")
vrai = NR.kernel_path()
check("ce dépôt porte bien un KERNEL à réinjecter", vrai is not None, "aucun des candidats n'existe")
if vrai:
    r = NR.rappel("compact")
    check("il contient les garde-fous, pas seulement leur titre", "garde-fou" in r.lower() or "tripwire" in r.lower())
    check("il rappelle lui-même qu'il se relit après compaction", "compaction" in r.lower())

print("\n[RM3071] posé à l'installation, et vu par le contrôle")
hooks = (HERE / "pm-claude-hooks-sync.py").read_text()
check("le rappel est dans le bloc de hooks canonique", "pm-norms-recall.py" in hooks)
check("il se déclenche sur une compaction ET sur une reprise", '"compact|resume"' in hooks)
spec2 = importlib.util.spec_from_file_location("hs", HERE / "pm-claude-hooks-sync.py")
HS = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(HS)
ev = [h for h in HS.PM_HOOKS if h[2] == "pm-norms-recall.py"]
check("un seul hook, sur SessionStart", len(ev) == 1 and ev[0][0] == "SessionStart")
g = HS.build_group(*ev[0][1:])
check("la commande passe par le dispatcher relocalisable",
      g["hooks"][0]["command"].startswith("mmi-pm norms-recall"), g["hooks"][0]["command"])
check("sa sortie N'EST PAS silencée : c'est elle, le rappel",
      "&>/dev/null" not in g["hooks"][0]["command"])
check("le contrôle sait le voir manquer",
      not HS.event_has_script([], "pm-norms-recall.py")
      and HS.event_has_script([g], "pm-norms-recall.py"))

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm-norms-recall"))
sys.exit(1 if FAIL else 0)
