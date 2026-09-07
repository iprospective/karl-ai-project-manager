#!/usr/bin/env python3
"""Tests RM3008 — cockpit-view-cost : couches par suffixe, mesure d'un domaine, garde --check."""
import importlib.util
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("cvc", HERE / "cockpit-view-cost.py")
cvc = importlib.util.module_from_spec(spec); spec.loader.exec_module(cvc)
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


for name, layer in [("sets.js", "model"), ("setsGroups.js", "model"), ("SetsRepository.js", "repository"), ("sets.service.js", "service"),
                    ("SetsViewModel.js", "viewmodel"), ("SessionsViewModels.js", "viewmodel"), ("Sets.view.js", "view"), ("sets.controller.js", "controller"), ("sets.scss", "style")]:
    check(f"couche de {name} = {layer}", cvc.layer_of(name) == layer, cvc.layer_of(name))
check("4 caractères ≈ 1 token, arrondi au-dessus", cvc.tokens(4) == 1 and cvc.tokens(5) == 2 and cvc.tokens(0) == 0)

with tempfile.TemporaryDirectory() as td:
    ck = pathlib.Path(td); (ck / "src" / "modules" / "demo").mkdir(parents=True); (ck / "src" / "core").mkdir()
    (ck / "src" / "modules" / "demo" / "demo.js").write_text("x" * 400)
    (ck / "src" / "modules" / "demo" / "Demo.view.js").write_text("v" * 800)
    (ck / "src" / "modules" / "demo" / "demo.controller.js").write_text("c" * 1200)
    (ck / "src" / "modules" / "demo" / "demo.scss").write_text("s" * 40)
    (ck / "src" / "modules" / "demo" / "notes.md").write_text("ignoré")
    (ck / "test_cockpit_demo.js").write_text("t" * 200)
    (ck / "src" / "core" / "html.js").write_text("h" * 4000)
    rows = cvc.measure_all(ck)
    demo = next(r for r in rows if r["domain"] == "demo"); core = next(r for r in rows if r["domain"] == "core")
    check("un domaine : total = js + scss + test, hors .md", demo["chars"] == 2640 and demo["tokens"] == 660, str(demo))
    check("ventilation par couche", demo["layers"]["model"] == 100 and demo["layers"]["view"] == 200 and demo["layers"]["controller"] == 300 and demo["layers"]["style"] == 10 and demo["layers"]["test"] == 50, str(demo["layers"]))
    check("coût « vue » = ViewModel + vue + contrôleur + test", demo["view_tokens"] == 550, str(demo["view_tokens"]))
    check("core est mesuré comme un domaine, avec son test s'il existe", core["tokens"] == 1000 and rows[0]["domain"] == "core", str(rows))
    md = cvc.table(rows, True, 900)
    check("tableau markdown : en-tête, marque ⚠ au-dessus du seuil", md.startswith("| domaine | total | vue |") and "| core ⚠ |" in md and "| demo |" in md, md)

r = subprocess.run([sys.executable, str(HERE / "cockpit-view-cost.py"), "--check", "1"], capture_output=True, text=True)
check("--check trop bas sur le vrai cockpit → sortie 1 et liste des domaines, core exclu", r.returncode == 1 and "au-dessus de 1 tokens" in r.stderr and "sets" in r.stderr and "core" not in r.stderr, r.stderr[:200])
r = subprocess.run([sys.executable, str(HERE / "cockpit-view-cost.py"), "--check", "10000000"], capture_output=True, text=True)
check("--check large → sortie 0", r.returncode == 0 and "✓ aucun domaine" in r.stdout)
r = subprocess.run([sys.executable, str(HERE / "cockpit-view-cost.py"), "--domain", "journal"], capture_output=True, text=True)
check("--domain : fichier par fichier", r.returncode == 0 and "journal.controller.js" in r.stdout and "total" in r.stdout)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — cockpit-view-cost")
