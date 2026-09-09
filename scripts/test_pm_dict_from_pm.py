#!/usr/bin/env python3
"""Tests RM3061 — pm-dict-from-pm : les tables générées du dictionnaire PM (sources réelles du repo), --check, tables curées jamais touchées."""
import pathlib
import subprocess
import sys
import tempfile

import yaml

HERE = pathlib.Path(__file__).resolve().parent
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


with tempfile.TemporaryDirectory() as tmp:
    docs = pathlib.Path(tmp) / "docs"; (docs / "dict").mkdir(parents=True)
    (docs / "dict" / "entites.yml").write_text("- {id: x, nom: X, domaine: pm, etat: ✅, role: curée}\n")
    run = lambda *a: subprocess.run([sys.executable, str(HERE / "pm-dict-from-pm.py"), "--docs-dir", str(docs)] + list(a), capture_output=True, text=True)
    r = run(); check("génération sans erreur", r.returncode == 0, r.stdout + r.stderr)
    d = {f.stem: yaml.safe_load(f.read_text()) for f in (docs / "dict").glob("*.yml")}
    check("sept tables générées + la curée intacte", set(d) == {"champs", "enumerations", "normes", "routes", "composants", "actions", "templates", "entites"} and d["entites"][0]["role"] == "curée")
    check("champs : tâche/projet/client depuis les gabarits, redmine_id obligatoire", {"tache", "projet", "client"} <= set(d["champs"]) and any(c["nom"] == "redmine_id" and c["obligatoire"] == "oui" for c in d["champs"]["tache"]))
    check("énumérations : status et close_reason du KERNEL", "status" in d["enumerations"] and any(v["id"] == "ferme" for v in d["enumerations"]["status"]["valeurs"]) and "close_reason" in d["enumerations"])
    check("normes : les garde-fous du KERNEL (≥ 17), id GF01…", len(d["normes"]) >= 17 and d["normes"][0]["id"] == "GF01" and "Outillage" in d["normes"][0]["nom"])
    check("routes : la carte des routes (≥ 100, cibles /api/)", len(d["routes"]) >= 100 and all(r["chemin"].startswith("/api/") for r in d["routes"]))
    check("composants : noyau et modules du cockpit avec un rôle", len(d["composants"]["noyau"]) >= 10 and any(m["id"] == "cdc" and m["role"] for m in d["composants"]["module"]))
    check("actions : les scripts pm-* (≥ 100) avec un libellé", len(d["actions"]) >= 100 and any(a["id"] == "task-take" and a["libelle"] for a in d["actions"]))
    check("templates : gabarits et aspects", any(t["nom"] == "task.md" for t in d["templates"]) and any(t["contexte"] == "aspects" for t in d["templates"]))
    check("--check vert juste après génération", run("--check").returncode == 0)
    (docs / "dict" / "routes.yml").write_text("[]\n"); check("--check rouge si une table générée a été retouchée", run("--check").returncode == 1)
    header = (docs / "dict" / "normes.yml").read_text().splitlines()[0]; check("en-tête GÉNÉRÉ sur chaque table dérivée", "GÉNÉRÉ" in header)
print("\n" + ("ÉCHEC : " + ", ".join(fails) if fails else "OK — pm-dict-from-pm"))
sys.exit(1 if fails else 0)
