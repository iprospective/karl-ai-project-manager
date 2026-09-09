#!/usr/bin/env python3
"""Tests hors ligne du fichier de réflexion par ticket (RM3015/RM3053) : `pm_think`,
`pm-task-think`, `pm-think-merge`, `pm-think-harvest`, la garde de clôture et le sweep.

Ce qui casserait en silence si on se trompait :
  - `is_task_sheet` : un `.think.md` pris pour la fiche (leçon RM2362) — et le sweep : plus AUCUN
    site n'exclut les frères par `endswith(".log.md")` ;
  - le parseur : ids, états (✅ ❌ 🟡 🕐 ⏸), lignes barrées, compteurs ;
  - l'ajout : id auto par rubrique et par préfixe (D/C), gabarit créé à la volée, dédoublonnage ;
  - la fusion : bloc entre marqueurs régénéré, ce qui est HORS marqueurs conservé, ids préfixés ;
  - la moisson : questions répondues → D ✅ (la Q homonyme se ferme), sans réponse → Q, demandes → N ;
  - le renommage des anciens `cdc-<prefix>-NN-*.md` et la correction des liens.
Aucun réseau, aucun git : tout en répertoire temporaire, `--no-commit`.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import pm_think                                        # noqa: E402

FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def run(*args, stdin=None):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, input=stdin)


# ── 1. reconnaissance des frères ────────────────────────────────────────────
print("· is_task_sheet / frères")
check("fiche reconnue", pm_think.is_task_sheet("RM3015_slug-kebab.md"))
check(".think.md n'est pas la fiche", not pm_think.is_task_sheet("RM3015_slug.think.md"))
check(".log.md n'est pas la fiche", not pm_think.is_task_sheet("RM3015_slug.log.md"))
check("sheet_of remonte au .md", pm_think.sheet_of(Path("/x/RM1_a.think.md")).name == "RM1_a.md")
check("think_path", pm_think.think_path(Path("/x/RM1_a.md")).name == "RM1_a.think.md")

# le sweep : aucun script ne filtre plus les frères par le seul `.log.md`
rest = [f.name for f in SCRIPTS.glob("*.py") if not f.name.startswith("test_")
        and re.search(r'\.name\.endswith\("\.log\.md"\)', f.read_text(encoding="utf-8"))
        and f.name not in ("pm-task-report.py", "validate-task.py")]
check("sweep : plus d'exclusion `.log.md` seule dans les scripts", not rest, str(rest))

# l'ordre du glob ne compte plus : find_sheet ignore le think même s'il sort en premier
tmp = Path(tempfile.mkdtemp(prefix="pm-think-"))
tasks = tmp / "tasks"; tasks.mkdir()
sheet = tasks / "RM42_essai.md"
sheet.write_text("---\nschema_version: 1.11.0\nredmine_id: 42\ntitle: Essai\nstatus: en_cours\nupdated: 2026-09-09T10:00\n---\n\n## Contexte\n\nx\n", encoding="utf-8")
(tasks / "RM42_essai.log.md").write_text("# Journal RM42\n", encoding="utf-8")
(tasks / "RM42_essai.think.md").write_text(pm_think.gabarit(42, "Essai"), encoding="utf-8")
check("find_sheet rend la fiche malgré log + think", pm_think.find_sheet(tasks, 42) == sheet)
check("iter_sheets : une seule fiche", [f.name for f in pm_think.iter_sheets(tasks)] == ["RM42_essai.md"])

# ── 2. parseur + compteurs sur un think réaliste ─────────────────────────────
print("· parseur")
sample = """# RM7 — Réflexion

## Notes — vrac

| # | Date · auteur | Verbatim | État | Traitée par |
|---|---|---|---|---|
| N001 | 2026-09-06 · M | « une idée » | ✅ | D001 |
| N002 | 2026-09-08 · M | « une autre » | 🕐 | |

## Questions ouvertes

| # | Question | Bloque | Urgence | État |
|---|---|---|---|---|
| Q001 | Où ? | L1 | haute | 🟡 avis A |
| ~~Q002~~ | ~~Quand ?~~ | | | ✅ tranchée par D001 |

## Décisions

| # | Objet | État |
|---|---|---|
| D001 | On fait X | ✅ 2026-09-06 |
| D002 | On ferait Y | 🟡 |
| C001 | Conseil | ✅ retenu |

### D001 — détail
prose

## Fonctionnalités à implémenter

| # | Fonctionnalité | Domaine | Version | Origine | État | Lot |
|---|---|---|---|---|---|---|
| F001 | Outil | consignation | V1 | N001 | 🕐 | L1 |
"""
p = pm_think.parse(sample)
check("4 rubriques", set(p) == {"note", "question", "decision", "feature"})
check("ligne barrée = fermée", p["question"]["rows"][1]["closed"] and p["question"]["rows"][1]["id"] == "Q002")
check("état lu dans la colonne État", p["question"]["rows"][0]["state"] == "propose" and p["note"]["rows"][1]["state"] == "attente")
c = pm_think.counters(p)
check("compteurs", c == {"questions_open": 1, "notes_pending": 1, "decisions": 1, "features": 1}, str(c))
check("next_id par préfixe", pm_think.next_id(p, "decision", "D") == "D003" and pm_think.next_id(p, "decision", "C") == "C002")
check("has_text : verbatim avec guillemets retrouvé sans", pm_think.has_text(p, "note", "une autre"))
check("has_text : texte court exact seulement", not pm_think.has_text(p, "question", "Où"))

# ── 3. ajout / états / gabarit / compteurs frontmatter ──────────────────────
print("· append / set_state / set_counters")
th = tasks / "RM43_neuf.think.md"
sheet43 = tasks / "RM43_neuf.md"
sheet43.write_text("---\nredmine_id: 43\ntitle: Neuf\nupdated: 2026-09-09T10:00\n---\n\ncorps\n", encoding="utf-8")
n1 = pm_think.append(th, "note", "Texte | avec barre", rm_id=43, title="Neuf", by="M", sid="abcdef0123456789")
q1 = pm_think.append(th, "question", "Pourquoi ?", rm_id=43, bloque="L1", urgence="haute")
d1 = pm_think.append(th, "decision", "On tranche", rm_id=43, state="valide")
c1 = pm_think.append(th, "decision", "Je conseille", rm_id=43, prefix="C")
f1 = pm_think.append(th, "feature", "Un outil", rm_id=43, domaine="consignation", version="V1", lot="L1")
check("gabarit créé + ids", (n1, q1, d1, c1, f1) == ("N001", "Q001", "D001", "C001", "F001"))
txt = th.read_text(encoding="utf-8")
check("barre verticale neutralisée, session courte", "Texte / avec barre" in txt and "s:abcdef01" in txt)
check("set_state", pm_think.set_state(th, "N001", "valide", dest="D001") and "| N001 | " in th.read_text() and "| ✅ | D001 |" in th.read_text())
check("set_state inconnu → False", not pm_think.set_state(th, "Z999", "valide"))
cnt = pm_think.counters(pm_think.load(th))
check("compteurs après ajouts", cnt == {"questions_open": 1, "notes_pending": 0, "decisions": 1, "features": 1}, str(cnt))
check("set_counters écrit le bloc think:", pm_think.set_counters(sheet43, cnt) and "think:\n  questions_open: 1\n" in sheet43.read_text())
check("set_counters idempotent", not pm_think.set_counters(sheet43, cnt))
check("set_counters remplace sans dupliquer", pm_think.set_counters(sheet43, {**cnt, "features": 2})
      and sheet43.read_text().count("think:") == 1 and "features: 2" in sheet43.read_text()
      and "updated: 2026-09-09T10:00" in sheet43.read_text())
check("corps intact", sheet43.read_text().endswith("---\n\ncorps\n"))

# ── 4. fusion vers les fichiers projet ───────────────────────────────────────
print("· pm-think-merge")
docs = tmp / "docs"; docs.mkdir()
(docs / "INDEX.md").write_text("# INDEX\n\n- [a.md](a.md) — a\n", encoding="utf-8")
# un registre projet tenu à la main AVANT les think doit survivre à la fusion
(docs / "cdc-decisions.md").write_text("# Registre\n\n| # | Objet | État |\n|---|---|---|\n| D001 | décision projet historique | ✅ |\n", encoding="utf-8")
r = run(SCRIPTS / "pm-think-merge.py", "--docs-dir", docs, "--tasks-dir", tasks, "--project", "t/p", "--no-commit")
check("merge sort 0", r.returncode == 0, r.stderr[-300:])
for name in pm_think.PROJECT_FILES:
    check(f"{name} présent", (docs / name).is_file())
dec = (docs / "cdc-decisions.md").read_text(encoding="utf-8")
check("hors marqueurs conservé", "décision projet historique" in dec)
check("ids préfixés RM43-", "| RM43-D001 | RM43 |" in dec and "| RM43-C001 |" in dec)
check("questions fusionnées", "| RM43-Q001 | RM43 | Pourquoi ?" in (docs / "cdc-questions.md").read_text())
check("features par domaine × version", "### consignation" in (docs / "cdc-features.md").read_text() and "**V1**" in (docs / "cdc-features.md").read_text())
check("INDEX complété", "cdc-questions.md" in (docs / "INDEX.md").read_text())
check("--check vert après fusion", run(SCRIPTS / "pm-think-merge.py", "--docs-dir", docs, "--tasks-dir", tasks, "--project", "t/p", "--check").returncode == 0)
pm_think.append(th, "question", "Encore une ?", rm_id=43)
rc = run(SCRIPTS / "pm-think-merge.py", "--docs-dir", docs, "--tasks-dir", tasks, "--project", "t/p", "--check")
check("--check rouge quand un think a bougé", rc.returncode == 1 and "cdc-questions.md" in rc.stdout, rc.stdout)
run(SCRIPTS / "pm-think-merge.py", "--docs-dir", docs, "--tasks-dir", tasks, "--project", "t/p", "--no-commit")
dec2 = (docs / "cdc-decisions.md").read_text(encoding="utf-8")
check("régénération : un seul bloc, historique toujours là", dec2.count(pm_think.MERGE_BEGIN) == 1 and "historique" in dec2)

# ── 5. renommage des anciens noms (D008) ─────────────────────────────────────
print("· --rename-legacy")
docs2 = tmp / "docs2"; docs2.mkdir(); (docs2 / "cdc-pm").mkdir()
(docs2 / "cdc-pm-00-sommaire.md").write_text("# CDC\n[déc](cdc-pm-90-decisions.md) [f](cdc-pm-10-fonctionnalites.md)\n", encoding="utf-8")
(docs2 / "cdc-pm-90-decisions.md").write_text("# D\n| D001 | x | ✅ |\n", encoding="utf-8")
(docs2 / "cdc-pm-91-vrac.md").write_text("# N\n", encoding="utf-8"); (docs2 / "cdc-pm-99-questions-ouvertes.md").write_text("# Q\n", encoding="utf-8")
(docs2 / "cdc-pm-10-fonctionnalites.md").write_text("# F\n", encoding="utf-8")
(docs2 / "cdc-pm" / "fonctionnalites.yml").write_text("prefix: pm\nprojet: t/p\ndomaines: []\njalons: []\nentrees: []\n", encoding="utf-8")
(docs2 / "cdc-rm77-feature.md").write_text("# CDC ticket\n", encoding="utf-8")
(docs2 / "INDEX.md").write_text("- [cdc-pm-90-decisions.md](cdc-pm-90-decisions.md) — d\n", encoding="utf-8")
tasks2 = tmp / "tasks2"; tasks2.mkdir()
r = run(SCRIPTS / "pm-think-merge.py", "--docs-dir", docs2, "--tasks-dir", tasks2, "--project", "t/p", "--rename-legacy", "--no-commit")
check("rename sort 0", r.returncode == 0, r.stderr[-300:])
check("fichiers renommés", all((docs2 / n).is_file() for n in ("cdc.md", "cdc-decisions.md", "cdc-notes.md", "cdc-questions.md", "cdc-features.md"))
      and not (docs2 / "cdc-pm-90-decisions.md").exists())
check("registre déplacé dans cdc/", (docs2 / "cdc" / "fonctionnalites.yml").is_file())
check("liens corrigés (sommaire + INDEX)", "(cdc-decisions.md)" in (docs2 / "cdc.md").read_text() and "cdc-decisions.md" in (docs2 / "INDEX.md").read_text()
      and "cdc-pm-90" not in (docs2 / "INDEX.md").read_text())
check("CDC de ticket intouché", (docs2 / "cdc-rm77-feature.md").is_file())
check("décision historique conservée sous le bloc", "| D001 | x | ✅ |" in (docs2 / "cdc-decisions.md").read_text())
check("pm-cdc-features lit docs/cdc/ et écrit cdc-features.md",
      run(SCRIPTS / "pm-cdc-features.py", "--docs-dir", docs2, "--tasks-dir", tasks2, "--project", "t/p", "--check").returncode in (0, 1)
      and "cdc-features.md" in run(SCRIPTS / "pm-cdc-features.py", "--docs-dir", docs2, "--tasks-dir", tasks2, "--project", "t/p", "--check").stdout)
feat = (docs2 / "cdc-features.md").read_text(encoding="utf-8")
check("cdc-features.md : partie générée + bloc think conservé", "Généré" in feat and pm_think.MERGE_BEGIN in feat)

# ── 6. moisson depuis un transcript ──────────────────────────────────────────
print("· pm-think-harvest")
sys.path.insert(0, str(SCRIPTS))
import importlib.util
spec = importlib.util.spec_from_file_location("harv", SCRIPTS / "pm-think-harvest.py"); harv = importlib.util.module_from_spec(spec); spec.loader.exec_module(harv)
lines = [
    json.dumps({"type": "user", "message": {"content": "Peux-tu déplacer le worklog dans le core ?"}}),
    json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Je propose."},
               {"type": "tool_use", "id": "t1", "name": "AskUserQuestion", "input": {"questions": [{"question": "Frère ou dossier ?", "options": [{"label": "frère"}, {"label": "dossier"}]}]}}]}}),
    json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": '"Frère ou dossier ?"="frère"'}]}}),
    json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t2", "name": "AskUserQuestion", "input": {"questions": [{"question": "Et le seuil ?", "options": []}]}}]}}),
    json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t2", "content": "[Request interrupted by user]"}]}}),
    json.dumps({"type": "user", "message": {"content": "ok"}}),
    json.dumps({"type": "user", "message": {"content": "/context"}}),
    json.dumps({"type": "user", "message": {"content": "[Request interrupted by user]"}}),
    json.dumps({"type": "user", "message": {"content": "Peux-tu déplacer le worklog dans le core ?"}}),
]
items = harv.harvest_items(lines)
kinds = [k for k, _, _ in items]
check("moisson : note, décision, question ; ni « ok », ni commande, ni interruption, ni doublon", kinds == ["note", "decision", "question"], str(kinds))
check("décision = question → réponse", items[1][1] == "Frère ou dossier ? → frère")
th44 = tasks / "RM44_moisson.think.md"
(tasks / "RM44_moisson.md").write_text("---\nredmine_id: 44\ntitle: Moisson\n---\n", encoding="utf-8")
added = harv.apply(th44, 44, items, sid="s1")
check("3 lignes ajoutées", len(added) == 3, str(added))
check("rejouer n'ajoute rien", harv.apply(th44, 44, items, sid="s1") == [])
# la question laissée ouverte se ferme quand la réponse arrive dans un tour suivant
later = harv.harvest_items(lines + [json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t3", "name": "AskUserQuestion", "input": {"questions": [{"question": "Et le seuil ?", "options": []}]}}]}}),
                                    json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t3", "content": '"Et le seuil ?"="300 lignes"'}]}})])
harv.apply(th44, 44, later, sid="s2")
p44 = pm_think.load(th44)
q_open = [r for r in p44["question"]["rows"] if r["state"] not in ("valide", "invalide")]
check("Q homonyme tranchée à l'arrivée de la réponse", not q_open and pm_think.counters(p44)["decisions"] == 2, str(pm_think.counters(p44)))

# ── 7. pm-task-think en CLI (sans config PM : --path/--show passent par PMConfig → on teste le parseur d'arguments seulement)
print("· pm-task-think --help")
check("aide", "--decide" in run(SCRIPTS / "pm-task-think.py", "--help").stdout)

# ── 8. garde de clôture : lecture pure des compteurs ──────────────────────────
print("· garde de clôture")
src = (SCRIPTS / "pm-task-status-update.py").read_text(encoding="utf-8")
check("status-update refuse `ferme` avec des Q ouvertes (sauf --ignore-think)", "questions_open" in src and "--ignore-think" in src)
check("hooks : moisson câblée sur Stop et SessionEnd", (SCRIPTS / "pm-claude-hooks-sync.py").read_text().count("pm-think-harvest.py") == 2)

print()
if FAIL:
    print(f"✗ {len(FAIL)} échec(s) : " + ", ".join(FAIL)); sys.exit(1)
print("OK — pm_think / pm-task-think / pm-think-merge / pm-think-harvest")
