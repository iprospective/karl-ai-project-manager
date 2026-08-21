#!/usr/bin/env python3
"""Tests RM2724 — le worklog groupe ses tickets par projet.

Le projet vivait en suffixe de ligne (`_(pisceen-presta)_`), noyé en fin d'une
ligne qui porte déjà statut, ref, titre, dérive et commit. Dès que la session
mélange deux projets — le cas normal ici — on ne voit plus à quoi on touche.

Ce que ces tests verrouillent, dans l'ordre d'importance :
  1. un item ne perd JAMAIS son projet — même ouvert sans `--project`, il est
     rattrapé depuis le chemin de sa tâche ; le repli `hors projet` est un
     dernier recours, pas une issue commode ;
  2. le regroupement est un rendu, pas un tri : l'ordre des items DANS un
     groupe reste celui de la session, et l'ordre des groupes celui de leur
     première apparition — sauf `hors projet`, qui ferme la marche.

Lancer : python3 scripts/test_pm_session_status_grouping.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core          # noqa: E402

hermetic_core()   # RM2749 : core PM jetable — le rendu passe par PMConfig.load(),
                  # qui sort en `sys.exit()` sans `.env`. Le test mourait donc dans
                  # un shell nu et passait dans un shell où PM_CORE_DIR traînait.

spec = importlib.util.spec_from_file_location("pss", HERE / "pm-session-status.py")
pss = importlib.util.module_from_spec(spec)
sys.modules["pss"] = pss
spec.loader.exec_module(pss)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# --- 1. projet déduit du chemin de la tâche ---------------------------------

P = pss.project_from_task_path
check("le projet se lit dans le chemin canonique d'une tâche",
      P("/z/projects/clients/pisceen/projects/pisceen-presta/tasks/RM1_x.md")
      == "pisceen-presta")
check("… quel que soit le client",
      P("/z/projects/clients/iprospective/projects/pm-ai-agents/tasks/RM2_y.md")
      == "pm-ai-agents")
check("un chemin sans dossier `tasks` ne fabrique pas un faux projet",
      P("/z/quelque/part/RM3.md") is None)
check("`tasks` en tête de chemin ne fait pas déborder l'index",
      P("tasks/RM4.md") is None)
check("un chemin non résolu ne lève pas",
      P("") is None)


# --- 2. rendu groupé --------------------------------------------------------

def item(ref, project=None, label=None, status="a_faire"):
    it = {"ref": ref, "status": status, "opened_status": status}
    if project:
        it["project"] = project
    if label:
        it["label"] = label
    return it


data = {
    "session_id": "s-test", "updated": "2026-08-18T00:00",
    "items": [item("RM10", "pisceen-presta", "site A"),
              item("RM11", "pm-ai-agents", "outil B"),
              item("RM12", None, "orphelin"),
              item("RM13", "pisceen-presta", "site C")],
}
md = pss.render_md(data, live={})
body = md if isinstance(md, str) else "\n".join(md)

check("chaque projet devient un titre de groupe",
      "### pisceen-presta" in body and "### pm-ai-agents" in body)
check("le suffixe `_(projet)_` a disparu de la ligne",
      "_(pisceen-presta)_" not in body)
check("les items d'un même projet sont regroupés, l'ordre de session préservé",
      body.index("site A") < body.index("site C") < body.index("orphelin"))
check("un item sans projet connu tombe dans « hors projet »",
      "### hors projet" in body)
check("… et ce groupe ferme la marche, il n'ouvre pas la liste",
      body.index("### hors projet") > body.index("### pm-ai-agents"))

# le repli `live` : l'item n'a pas de projet stocké, la tâche résolue si.
live = {"RM12": {"status": "a_faire", "title": "vrai titre",
                 "project": "pisceen-presta", "docs": []}}
md2 = pss.render_md(data, live=live)
body2 = md2 if isinstance(md2, str) else "\n".join(md2)
check("un item ouvert sans --project est rattrapé par le projet de sa tâche",
      "### hors projet" not in body2)
check("… et il rejoint bien le groupe existant, sans le dupliquer",
      body2.count("### pisceen-presta") == 1)


# --- 3. libellé : ne pas afficher « RM2680 — RM2680 » -----------------------

data3 = {"session_id": "s3", "updated": "2026-08-18T00:00", "items": [item("RM20", "p", label="RM20")]}
live3 = {"RM20": {"status": "a_faire", "title": "le vrai titre",
                  "project": "p", "docs": []}}
md3 = pss.render_md(data3, live=live3)
body3 = md3 if isinstance(md3, str) else "\n".join(md3)
check("un label qui n'est que la référence cède la place au titre de la tâche",
      "le vrai titre" in body3 and "**RM20** — RM20" not in body3)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests regroupement par projet RM2724 passent")
