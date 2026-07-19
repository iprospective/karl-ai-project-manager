#!/usr/bin/env python3
"""Tests RM2353 — fiche projet (op_project) pour le panneau principal du cockpit.

Unitaire (sans réseau) : _project_tickets_summary (pure), gardes 400/404,
parsing de conf (meta.yml / frontmatter overview / les deux) sur un projet
fabriqué en tmpdir. Lancer : python3 scripts/test_karl_agent_project.py
"""
import importlib.util
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# — _project_tickets_summary : tri par récence, cap, comptage —
tk = lambda rm, st, mt: {"rm_id": rm, "title": "t" + rm, "status": st, "type": "feature", "mtime": mt}
tasks = [tk("1", "ferme", 10), tk("2", "en_cours", 50), tk("3", "ferme", 90),
         tk("4", "a_tester_demandeur", 20), tk("5", "en_cours", 70)]
s = ka._project_tickets_summary(tasks)
check("fermés récents d'abord", [t["rm_id"] for t in s["closed_recent"]] == ["3", "1"])
check("ouverts récents d'abord", [t["rm_id"] for t in s["open_recent"]] == ["5", "2", "4"])
check("comptage par statut", s["open_by_status"] == {"en_cours": 2, "a_tester_demandeur": 1})
check("total", s["total"] == 5)
many = [tk(str(i), "ferme", i) for i in range(50)]
check("cap fermés à 12", len(ka._project_tickets_summary(many)["closed_recent"]) == 12)
check("liste vide", ka._project_tickets_summary([]) == {
    "closed_recent": [], "open_recent": [], "open_by_status": {}, "total": 0})

# — op_project : projet fabriqué (meta.yml + overview + tasks + docs) —
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2353-"))
ka.PROJECTS_BASE = tmp
ka.REPO_ROOT = tmp        # _project_docs rend les chemins relatifs à REPO_ROOT
pdir = tmp / "acme" / "projects" / "shop"
(pdir / "tasks").mkdir(parents=True)
(pdir / "project").mkdir()
(pdir / "docs").mkdir()
(pdir / "meta.yml").write_text("name: Boutique ACME\nredmine:\n  project_id: acme-shop\n")
(pdir / "project" / "overview.md").write_text(
    "---\ngitlab:\n  repo: acme/shop-core\n  default_branch: main\n---\n\n## Description\n")
(pdir / "docs" / "cdc.md").write_text("# CDC\n")
(pdir / "tasks" / "RM10_fait.md").write_text("---\ntitle: Fini\nstatus: ferme\ntype: feature\n---\n")
(pdir / "tasks" / "RM11_encours.md").write_text("---\ntitle: En cours\nstatus: en_cours\ntype: bugfix\n---\n")
(pdir / "tasks" / "RM11_encours.log.md").write_text("journal\n")
os.environ["REDMINE_URL"] = "https://redmine.test"

d = ka.op_project("acme", "shop")
check("conf meta.yml : name + slug redmine", d["name"] == "Boutique ACME"
      and d["redmine_project_url"] == "https://redmine.test/projects/acme-shop")
check("lien liste des tickets", d["redmine_issues_url"].endswith("/projects/acme-shop/issues"))
check("conf overview : repo gitlab + branche", d["gitlab_repo"] == "acme/shop-core"
      and d["default_branch"] == "main")
check("docs surfacées (project/ + docs/)",
      {x["name"] for x in d["docs"]} == {"overview.md", "cdc.md"})
check("tickets : .log.md exclu, total 2", d["total"] == 2)
check("dernier traité = RM10", [t["rm_id"] for t in d["closed_recent"]] == ["10"])
check("ouvert = RM11 (statut compté)", d["open_by_status"] == {"en_cours": 1})

# — gardes —
try:
    ka.op_project("acme", "inconnu")
    check("projet inconnu → 404", False)
except ka.ApiError as e:
    check("projet inconnu → 404", e.code == 404)
try:
    ka.op_project("../etc", "shop")
    check("traversée de chemin → 400", False)
except ka.ApiError as e:
    check("traversée de chemin → 400", e.code == 400)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests fiche projet RM2353 passent")
