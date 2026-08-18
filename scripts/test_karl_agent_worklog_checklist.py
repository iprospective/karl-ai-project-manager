#!/usr/bin/env python3
"""Tests RM2695 — avancement d'un ticket dans le worklog (checklist + sous-tâches).

Le principe qu'on protège ici : l'avancement se LIT là où il est déjà tenu (la
checklist des critères d'acceptation, tripwire #9), on n'ouvre pas un second
référentiel de tâches. Les tests portent donc sur le parseur, sur la fusion avec
l'état live du worklog, et sur le fait qu'un ticket SANS checklist ne fabrique
rien (« 0/0 » se lirait comme un ticket vide).

Lancer : python3 scripts/test_karl_agent_worklog_checklist.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# — parse_checklist : formes rencontrées dans les descriptions PM —
BODY = """## Contexte

Du texte avec un [lien] et un - tiret qui n'est pas une case.

## Critères d'acceptation

- [ ] Premier critère
- [x] Deuxième, fait
- [X] Troisième, fait (majuscule)
* [ ] Puce étoile
  + [ ] Puce indentée
-[ ] pas une case (pas d'espace après le tiret)
- [] pas une case non plus
- [ ]
"""
cl = ka.parse_checklist(BODY)
check("total = toutes les cases valides", cl["total"] == 5, f"total={cl['total']}")
check("done = les cases cochées, x et X", cl["done"] == 2, f"done={cl['done']}")
check("items = les cases NON cochées seulement", len(cl["items"]) == 3, f"{cl['items']}")
check("le texte du critère est conservé", cl["items"][0] == "Premier critère")
check("puces * et + reconnues, indentation tolérée",
      "Puce étoile" in cl["items"] and "Puce indentée" in cl["items"])
check("une case vide n'est pas un critère", all(i.strip() for i in cl["items"]))
check("pas de troncature ici", cl["truncated"] is False)

vide = ka.parse_checklist("## Contexte\n\ndu texte sans case\n")
check("aucune case → total 0 (l'UI n'affichera rien)", vide["total"] == 0 and vide["items"] == [])
check("corps vide / None toléré",
      ka.parse_checklist("")["total"] == 0 and ka.parse_checklist(None)["total"] == 0)

# plafond : on compte tout, on ne LISTE qu'un maximum — sinon un compteur mentirait
gros = "\n".join(f"- [ ] critère {i}" for i in range(60)) + "\n- [x] fait\n"
g = ka.parse_checklist(gros, max_items=10)
check("le compteur porte sur TOUT (pas sur la liste tronquée)",
      g["total"] == 61 and g["done"] == 1, f"{g['done']}/{g['total']}")
check("la liste est plafonnée", len(g["items"]) == 10)
check("la troncature est ANNONCÉE", g["truncated"] is True)

# — fusion avec l'état live du worklog —
items = [{"ref": "RM1", "status": "nouveau", "opened_status": "nouveau"},
         {"ref": "RM2", "status": "en_cours", "opened_status": "en_cours"},
         {"ref": "chantier-libre", "status": "en_cours"}]
live = {
    "RM1": {"status": "en_cours",
            "checklist": {"done": 2, "total": 5, "items": ["reste A"], "truncated": False},
            "sub_tasks": [{"rm_id": "7", "status": "a_faire", "title": "T"}]},
    "RM2": {"status": "ferme"},
}
merged = ka._worklog_apply_live(items, live)
check("le statut live prime", merged[0]["status"] == "en_cours" and merged[1]["status"] == "ferme")
check("la checklist suit l'item", merged[0]["checklist"]["total"] == 5)
check("les sous-tâches suivent l'item", merged[0]["sub_tasks"][0]["rm_id"] == "7")
check("un ticket sans checklist n'en reçoit pas", "checklist" not in merged[1])
check("un chantier hors ticket est intact", merged[2] == items[2])
check("l'entrée d'origine n'est pas mutée", "checklist" not in items[0])
# forme héritée (cache chaud d'avant RM2695) : statut nu
old = ka._worklog_apply_live([{"ref": "RM1", "status": "nouveau"}], {"RM1": "ferme"})
check("statut live sous forme de chaîne encore accepté", old[0]["status"] == "ferme")

# — worklog_buckets propage l'avancement jusqu'à l'UI —
b = ka.worklog_buckets(merged)
row = next(r for r in b["todo"] + b["waiting"] + b["done"] + b["unknown"] if r["ref"] == "RM1")
check("l'avancement arrive dans le bucket", row.get("checklist", {}).get("total") == 5)
check("les sous-tâches aussi", len(row.get("sub_tasks") or []) == 1)
row2 = next(r for r in b["todo"] + b["waiting"] + b["done"] + b["unknown"] if r["ref"] == "RM2")
check("aucune clé fabriquée pour un ticket sans checklist", "checklist" not in row2)

# — _subtasks_status : ids invalides ignorés, forme stable —
subs = ka._subtasks_status(["RM2695", "2696", "pas-un-id", None])
check("sous-tâches : ids valides seulement", [s["rm_id"] for s in subs] == ["2695", "2696"],
      str(subs))
check("chaque sous-tâche porte rm_id/status/title",
      all({"rm_id", "status", "title"} <= set(s) for s in subs))
check("liste absente tolérée", ka._subtasks_status(None) == [])

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests avancement worklog RM2695 passent")
