#!/usr/bin/env python3
"""Tests RM3030 — pm_license : catalogue SPDX, normalisation, rendu (MIT daté, propriétaire court), question (numéro, identifiant,
défaut, EOF), choix hors terminal, écriture idempotente (+ NOTICE Apache), lecture depuis le projet PM ; pm-repo-new.ensure_license."""
import importlib.util
import io
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_license as L  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


check("catalogue : 7 choix, MPL-2.0 recommandée en tête, textes SPDX présents", L.IDS[0] == "MPL-2.0" and L.CATALOG[0]["recommended"] and len(L.IDS) == 7 and all((L.TEMPLATES / c["file"]).is_file() for c in L.CATALOG if c["file"]))
check("normalisation", L.normalize("mit") == "MIT" and L.normalize("gpl-3.0") == "GPL-3.0" and L.normalize("none") == "proprietary" and L.normalize("aucune") == "proprietary" and L.normalize("WTFPL") is None and L.normalize(None) is None)
mit = L.render("MIT", "ACME SAS", 2026); check("MIT : année et titulaire renseignés, texte intégral", "Copyright (c) 2026 ACME SAS" in mit and "Permission is hereby granted" in mit and "<year>" not in mit and "[fullname]" not in mit)
mpl = L.render("MPL-2.0"); check("MPL-2.0 : texte SPDX intégral", mpl.startswith("Mozilla Public License Version 2.0") and "Exhibit A" in mpl and len(mpl) > 15000)
for lid, needle in (("Apache-2.0", "Apache License"), ("GPL-3.0", "GNU GENERAL PUBLIC LICENSE"), ("LGPL-3.0", "GNU LESSER GENERAL PUBLIC LICENSE"), ("AGPL-3.0", "GNU AFFERO GENERAL PUBLIC LICENSE")):
    check(f"{lid} : texte intégral", needle in L.render(lid))
prop = L.render("proprietary", "ACME", 2026); check("propriétaire : court, titulaire, tous droits réservés", prop.startswith("Copyright (c) 2026 ACME. Tous droits réservés.") and len(prop) < 400)
try:
    L.render("WTFPL"); check("licence inconnue refusée", False)
except ValueError as e:
    check("licence inconnue refusée", "connues" in str(e))
ask = lambda inp: L.ask("MPL-2.0", stdin=io.StringIO(inp), stdout=io.StringIO())  # noqa: E731
check("défaut de la question : GPL-3.0 (décision RM3029), marqué dans le menu", L.DEFAULT_LICENSE == "GPL-3.0" and "GPL-3.0" in L.menu_text().split("← défaut")[0].splitlines()[-1] and L.ask(stdin=io.StringIO("\n"), stdout=io.StringIO()) == "GPL-3.0")
check("question : numéro, identifiant, Entrée = défaut, EOF = défaut, saisie inconnue redemandée", ask("3\n") == "MIT" and ask("apache-2.0\n") == "Apache-2.0" and ask("\n") == "MPL-2.0" and ask("") == "MPL-2.0" and ask("zz\n7\n") == "proprietary")
out = io.StringIO(); L.ask("MPL-2.0", stdin=io.StringIO("zz\n1\n"), stdout=out); check("le menu explique chaque choix et signale une saisie inconnue", "cœur ouvert" in out.getvalue() and "« zz » inconnu" in out.getvalue())
warns = []; check("choose : option validée / TTY → question / hors TTY → proprietary + avertissement",
                  L.choose("mit") == "MIT" and L.choose(None, interactive=True, stdin=io.StringIO("2\n"), stdout=io.StringIO()) == "Apache-2.0" and L.choose(None, interactive=False, warn=warns.append) == "proprietary" and "aucune licence choisie" in warns[0])
try:
    L.choose("WTFPL"); check("--license inconnu refusé", False)
except ValueError:
    check("--license inconnu refusé", True)
with tempfile.TemporaryDirectory() as td:
    d = pathlib.Path(td)
    w = L.write_license(d, "Apache-2.0", "ACME", 2026); check("écriture : LICENSE + NOTICE pour Apache", w == d / "LICENSE" and (d / "NOTICE").is_file() and "ACME" in (d / "NOTICE").read_text())
    check("idempotente : déjà présent → None, contenu intact", L.write_license(d, "MIT") is None and "Apache License" in (d / "LICENSE").read_text())
    check("force → réécrit", L.write_license(d, "MIT", "X", 2026, force=True) is not None and "Copyright (c) 2026 X" in (d / "LICENSE").read_text())
    (d / "COPYING").write_text("x"); (d / "LICENSE").unlink(); check("COPYING compte comme licence présente", L.write_license(d, "MIT") is None)
    # lecture depuis le projet PM : .mmi-pm → project/overview.md avec frontmatter license:
    ws = d / "ws"; pm = d / "pm" / "project"; pm.mkdir(parents=True); (ws / "repos" / "x").mkdir(parents=True); (ws / ".mmi-pm").symlink_to(d / "pm")
    (pm / "overview.md").write_text("---\nslug: x\nlicense: MPL-2.0   # commentaire\n---\n## Description\n")
    ov = L.project_overview_from_workspace(ws / "repos" / "x"); check("remontée jusqu'au .mmi-pm du workspace", ov == pm / "overview.md")
    check("license: lue et normalisée", L.read_from_overview(ov) == "MPL-2.0")
    (d / "pm" / "meta.yml").write_text("schema_version: '1.7.1'\nslug: x\nlicense: GPL-3.0\n"); check("meta.yml prime sur l'overview", L.project_overview_from_workspace(ws / "repos" / "x") == d / "pm" / "meta.yml" and L.read_from_overview(d / "pm" / "meta.yml") == "GPL-3.0"); (d / "pm" / "meta.yml").unlink()
    (pm / "overview.md").write_text("## Description\nsans frontmatter\n"); check("sans frontmatter → None", L.read_from_overview(ov) is None)
    check("hors workspace PM → None", L.project_overview_from_workspace(d / "ailleurs") is None)
    # pm-repo-new.ensure_license sur un vrai dépôt git local
    spec = importlib.util.spec_from_file_location("pm_repo_new", HERE / "pm-repo-new.py"); RN = importlib.util.module_from_spec(spec); sys.modules["pm_repo_new"] = RN; spec.loader.exec_module(RN)
    repo = d / "repo"; repo.mkdir(); subprocess.run(["git", "init", "-q", str(repo)], check=True); subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True); subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "README.md").write_text("x"); subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "seed"], check=True)
    said = []; RN.say = said.append
    check("dry-run : dit ce qu'il écrirait, n'écrit rien", RN.ensure_license(repo, "MIT", "ACME", True) == "MIT" and not (repo / "LICENSE").exists() and any("[dry] écrirait LICENSE (MIT)" in x for x in said))
    check("écrit et committe LICENSE avant le push", RN.ensure_license(repo, "MIT", "ACME", False) == "MIT" and (repo / "LICENSE").is_file() and "licence MIT" in subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%s"], capture_output=True, text=True).stdout and not subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True).stdout)
    check("déjà licencié → rien", RN.ensure_license(repo, None, None, False) is None)
    # sans option : lit le projet PM du workspace qui contient le dépôt
    repo2 = ws / "repos" / "x"; subprocess.run(["git", "init", "-q", str(repo2)], check=True); subprocess.run(["git", "-C", str(repo2), "config", "user.email", "t@t"], check=True); subprocess.run(["git", "-C", str(repo2), "config", "user.name", "t"], check=True)
    (pm / "overview.md").write_text("---\nlicense: Apache-2.0\n---\n"); (repo2 / "a").write_text("a"); subprocess.run(["git", "-C", str(repo2), "add", "-A"], check=True); subprocess.run(["git", "-C", str(repo2), "commit", "-qm", "s"], check=True)
    check("sans --license : la licence du projet PM est reprise (+ NOTICE Apache)", RN.ensure_license(repo2, None, None, False) == "Apache-2.0" and (repo2 / "NOTICE").is_file())

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — pm_license / pm-repo-new licence (RM3030)")
