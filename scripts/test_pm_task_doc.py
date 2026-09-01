#!/usr/bin/env python3
"""Tests RM1890 — pm-task-doc : garde de slug et édition de related_tickets[].

Le point sensible n'est pas le scaffold (une copie de template) : c'est l'édition du
frontmatter. On l'écrit TEXTUELLEMENT et non par round-trip YAML, précisément pour ne
pas perdre les commentaires de fin de ligne (« # ticket porteur ») qui portent la
moitié de l'information de la liste. Ces tests verrouillent ce contrat.

Lancer : python3 scripts/test_pm_task_doc.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_task_doc", HERE / "pm-task-doc.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["pm_task_doc"] = mod
spec.loader.exec_module(mod)

fails = []


def check(name, cond, detail=""):
    if cond:
        print(f"✓ {name}")
    else:
        fails.append(f"{name} — {detail}")
        print(f"✗ {name} — {detail}")


# — garde de slug : le slug devient l'URL wiki, il doit survivre au ticket —
def refuses(slug):
    try:
        mod.check_slug(slug)
        return False
    except SystemExit:
        return True


for bad in ("cdc-rm2889-refonte", "rm2889-front", "audit-rm2267-workspaces",
            "etude-RM123-x", "x", "Avec-Majuscules", "avec_underscore!", ""):
    check(f"slug refusé : {bad!r}", refuses(bad), "aurait dû être refusé")
for good in ("cockpit-architecture", "wiki-sync", "annuaire-contacts", "multi-vault"):
    check(f"slug accepté : {good!r}", not refuses(good), "refusé à tort")

# — related_tickets : les commentaires SURVIVENT à l'ajout —
FM = """schema_version: 1.0.0
aspect: demo
related_tickets:
  - 2889   # ticket porteur
  - 2765   # étude amont
status: draft
"""
new, changed = mod.add_related(FM, 2792, "nouveau venu")
check("ajout : signalé comme modifié", changed)
check("ajout : le ticket est présent", 2792 in mod.related_ids(new))
check("ajout : commentaires préservés", "# ticket porteur" in new and "# étude amont" in new,
      "un round-trip YAML les aurait mangés")
check("ajout : champs voisins intacts", "status: draft" in new and "aspect: demo" in new)
check("ajout : ordre d'origine conservé", mod.related_ids(new)[:2] == [2889, 2765])

again, changed2 = mod.add_related(new, 2792)
check("idempotence : re-ajout sans effet", not changed2 and again == new)

# — liste vide et liste inline —
empty = "aspect: demo\nrelated_tickets:\nstatus: draft\n"
e2, ch = mod.add_related(empty, 42)
check("liste vide : ajout accepté", ch and mod.related_ids(e2) == [42])
inline = "aspect: demo\nrelated_tickets: []\nstatus: draft\n"
i2, ch = mod.add_related(inline, 42)
check("liste inline [] : ajout accepté", ch and mod.related_ids(i2) == [42])
absent = "aspect: demo\nstatus: draft\n"
a2, ch = mod.add_related(absent, 42)
check("champ absent : la clé est créée", ch and mod.related_ids(a2) == [42])

# — retrait —
back, ch = mod.rm_related(new, 2792)
check("retrait : signalé", ch)
check("retrait : le ticket a disparu", 2792 not in mod.related_ids(back))
check("retrait : les autres restent", mod.related_ids(back) == [2889, 2765])
_, ch = mod.rm_related(back, 2792)
check("retrait idempotent", not ch)

# — la référence en description dérive la MÊME URL que pm-wiki-sync —
from pm_doc import wiki_title_for_slug  # noqa: E402
check("référence : le titre wiki vient de la règle partagée",
      f"[[{wiki_title_for_slug('cockpit-architecture')}]]" in mod.ref_line("cockpit-architecture"))
check("référence : pointe docs/, pas project/", "docs/cockpit-architecture.md" in mod.ref_line("cockpit-architecture"))

print()
if fails:
    print(f"ÉCHECS ({len(fails)}) :")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("OK — pm-task-doc : garde de slug et édition de related_tickets[]")
