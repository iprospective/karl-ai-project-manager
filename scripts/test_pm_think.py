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
import pathlib
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


# RM3076 : sans `subprocess_env()`, les scripts appelés cherchent le `.env` du dépôt courant —
# vert dans le core (qui l'a), ROUGE dans tout worktree de dev (qui ne l'a pas). Un test doit se
# suffire à lui-même : le core jetable de `test_support` lui en donne un.
from test_support import subprocess_env, hermetic_core       # noqa: E402

# … et le core jetable doit être posé AVANT tout import in-process d'un module PM
# (`pm-think-harvest` tire `pm_git`, qui charge le `.env` au chargement).
hermetic_core()


def run(*args, stdin=None):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True,
                          input=stdin, env=subprocess_env())


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
        and f.name not in ("pm-task-report.py", "validate-task.py",
                           # RM3085 : c'est LUI qui définit le suffixe — le tester ici serait circulaire
                           "pm_task_log.py")]
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

# RM3091 — mettre à jour les compteurs ne doit RIEN emporter d'autre.
# Le bug : `re.sub(r"(?ms)^think:\n(?:[ \t]+.*\n?)*", …)` — avec DOTALL, « . » matche les
# sauts de ligne, donc `[ \t]+.*` avalait tout le frontmatter situé APRÈS le bloc think.
# Constaté sur RM3079 : `test_protocol` disparu en local (le CF Redmine intact), et le
# protocole de test absent de l'email de compte-rendu client. Perte SILENCIEUSE.
sheet_after = tasks / "RM9101_apres.md"
sheet_after.write_text(
    "---\nredmine_id: 9101\ntitle: 'T'\nstatus: ferme\n"
    "think:\n  questions_open: 0\n  notes_pending: 3\n  decisions: 0\n  features: 0\n"
    'test_protocol: "1. Ouvrir la fiche\\\n  \\ 2. Vérifier le prix"\n'
    "tags:\n- palier\nreporting:\n  notes: []\n---\ncorps\n", encoding="utf-8")
pm_think.set_counters(sheet_after, {"questions_open": 0, "notes_pending": 2, "decisions": 0, "features": 0})
_after = sheet_after.read_text(encoding="utf-8")
check("compteurs mis à jour", "notes_pending: 2" in _after)
check("…sans effacer test_protocol (RM3091)", "test_protocol:" in _after)
check("…ni les clés suivantes (tags, reporting)", "tags:" in _after and "reporting:" in _after)
check("…et le corps est intact", _after.rstrip().endswith("corps"))
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
    json.dumps({"type": "user", "message": {"content": "Il faudra déplacer le worklog dans le core, je pense que c est plus cohérent"}}),
    json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Je propose."},
               {"type": "tool_use", "id": "t1", "name": "AskUserQuestion", "input": {"questions": [{"question": "Frère ou dossier ?", "options": [{"label": "frère"}, {"label": "dossier"}]}]}}]}}),
    json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": '"Frère ou dossier ?"="frère"'}]}}),
    json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t2", "name": "AskUserQuestion", "input": {"questions": [{"question": "Et le seuil ?", "options": []}]}}]}}),
    json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t2", "content": "[Request interrupted by user]"}]}}),
    json.dumps({"type": "user", "message": {"content": "ok"}}),
    json.dumps({"type": "user", "message": {"content": "/context"}}),
    json.dumps({"type": "user", "message": {"content": "[Request interrupted by user]"}}),
    json.dumps({"type": "user", "message": {"content": "Il faudra déplacer le worklog dans le core, je pense que c est plus cohérent"}}),
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
check("hooks : moisson câblée sur Stop, SessionEnd et PreCompact (RM3098)",
      (SCRIPTS / "pm-claude-hooks-sync.py").read_text().count("pm-think-harvest.py") == 3)

print()

# ── RM3062/RM3066 : le critère de la note, la moisson filtrée, l'élagage ─────────────────────
print("\n[RM3066] critère sémantique de la note — jeu tiré du corpus réel")
for txt, exp in [
        # dettes réelles : un reste à faire, auto-suffisant
        ("Tu deploies pour l'instant en ssh -A, on verra plus tard pour faire plus propre.", True),
        ("du coup, ticket pour plus tard : permettre de specifier/surcharger pour chaque projet le task manager", True),
        ("go. Juste la modif de champs dans le redmine matnat, on verra plus tard... je dois le valider en equipe.", True),
        ("Il manque aussi le dictionnaire des données dans le projet.", True),
        ("note que le vault age ne se verrouille pas", True),
        # contrainte sans reste à faire, et pas auto-suffisante
        ("le choix des lots doit être figé dans prestashop.", False),
        # ordres à l'agent, même longs, même avec « consigne »
        ("Consigne tout ça dans le ticket maintenant", False),
        ("merge les 6 propres (et consignes le des fois que ce ne soit pas si propre qu'on l'imaginait)", False),
        ("Fais un ticket PM pour analyser si on peut adapter le PM iprospective au même résultat", False),
        # réponse à une question outillée : c'est une décision
        ("Q23 : on administre domaines, boites, alias. Mais pas besoin pour le pilote.", False),
        ("D114 : quelle alternative pour que ca se passe mieux ? Q45 : oui metadonnees", False),
        # collages
        ("root@dev:~# grep -A2 'GC des verrous' /zfs/workspaces/.mmi-pm-core/scripts/cron.example.sh", False),
        ("This session is being continued from a previous conversation that ran out of context.", False),
        # report trop court pour qu'on sache de quoi il s'agit
        ("je stoppe on reprend plus tard", False),
        ("je m'occuperai de la clé API plus tard", False),
]:
    ok, motif = pm_think.note_pertinente(txt)
    check(f"{'garde' if exp else 'écarte'} « {txt[:46]}… » ({motif})", ok == exp)

print("\n[RM3062] signatures, moisson, élagage")
for txt, exp in [("étudie et chiffre la tâche RM3058 du client matnat projet infra", False), ("ok pour /opt. J'ai fait un ssh-add", False),
                 ("core update fait, ferme ce qui est livré", False), ("merge en main je core update pour tester", False), ("c'est à dire ? quelle désinscription ?", False),
                 ("note que le vault age ne se verrouille pas", True), ("il faudra faire un point sur les parties du kernel les plus utilisées", True),
                 ("le choix des lots doit être figé dans prestashop.", False), ("On pourrait réfléchir à découper encore plus fin en modules, avec des renvois vers des fichiers détaillés ?", True),
                 ("Les notes en vrac : je ne veux que ce qui est suffisamment pertinent pour apporter une information utile plus tard", True)]:
    ok, motif = pm_think.note_pertinente(txt)
    check(f"{'garde' if exp else 'écarte'} « {txt[:50]}… » ({motif})", ok == exp)
with tempfile.TemporaryDirectory() as tmp:
    tasks = Path(tmp); sheet = tasks / "RM77_slug.md"; sheet.write_text("---\nredmine_id: 77\ntitle: t\n---\n")
    th = pm_think.think_path(sheet)
    n1 = pm_think.append(th, "note", "ok pour /opt. J'ai fait un ssh-add", rm_id=77, by="M", state="attente")
    n2 = pm_think.append(th, "note", "il faudra revoir la précharge des modules NORMS, elle est trop grosse", rm_id=77, by="M", state="attente")
    n3 = pm_think.append(th, "note", "prends le ticket", rm_id=77, by="M", state="valide")
    r = subprocess.run([sys.executable, str(SCRIPTS / "pm-think-harvest.py"), "--prune", "--all", "--tasks-dir", str(tasks), "--dry-run"], capture_output=True, text=True)
    check("prune --dry-run liste la note sans portée, pas la pertinente ni la déjà traitée", n1 in r.stdout and n2 not in r.stdout and n3 not in r.stdout, r.stdout + r.stderr)
    r = subprocess.run([sys.executable, str(SCRIPTS / "pm-think-harvest.py"), "--prune", "--all", "--tasks-dir", str(tasks), "--no-commit"], capture_output=True, text=True)
    parsed = pm_think.load(th); rows = {x["id"]: x for x in parsed["note"]["rows"]}
    check("prune : la note élaguée passe ❌ avec son motif, l'autre reste 🕐", rows[n1]["state"] == "invalide" and "élaguée (RM3062)" in rows[n1]["cells"][4] and rows[n2]["state"] == "attente", r.stdout + r.stderr)
    check("prune : rejouer n'élague rien de plus", subprocess.run([sys.executable, str(SCRIPTS / "pm-think-harvest.py"), "--prune", "--all", "--tasks-dir", str(tasks), "--dry-run"], capture_output=True, text=True).stdout.strip().endswith("0 note(s) sur 1 think"))
    lines = [json.dumps({"type": "user", "message": {"role": "user", "content": "ok pour /opt. J'ai fait un ssh-add sur la machine"}}), json.dumps({"type": "user", "message": {"role": "user", "content": "il faudra revoir la précharge des modules NORMS, elle est trop grosse"}})]
    import importlib.util
    spec = importlib.util.spec_from_file_location("harv", SCRIPTS / "pm-think-harvest.py"); harv = importlib.util.module_from_spec(spec); spec.loader.exec_module(harv)
    items = harv.harvest_items(lines)
    check("moisson : seule la remarque pertinente devient une note", [i[1] for i in items] == ["il faudra revoir la précharge des modules NORMS, elle est trop grosse"], str(items))
    # lot 3 : signatures nominatives, propositions de l'IA, légende, suppression
    import os
    os.environ["PM_THINK_AUTHOR"] = "Claude Opus 5"; os.environ["PM_THINK_HUMAN"] = "Mathieu"
    check("model_label", pm_think.model_label("claude-fable-5-1") == "Claude Fable 5.1" and pm_think.model_label("qwen3.8:27b") == "Qwen3.8 27b" and pm_think.model_label("deepseek-4-flash") == "Deepseek 4 Flash")
    check("signature : M → demandeur nommé, A → modèle, nom explicite inchangé", pm_think.signature("M") == "Mathieu" and pm_think.signature("A") == "Claude Opus 5" and pm_think.signature("Paul") == "Paul")
    th2 = pm_think.think_path(tasks / "RM78_sig.md"); (tasks / "RM78_sig.md").write_text("---\nredmine_id: 78\ntitle: s\n---\n")
    d1 = pm_think.append(th2, "decision", "on signe", rm_id=78, by="M", state="valide"); c1 = pm_think.append(th2, "decision", "je conseille", rm_id=78, prefix="C", by="A", state="propose")
    txt2 = th2.read_text()
    check("lignes signées par un nom, jamais un code", "· Mathieu" in txt2 and "· Claude Opus 5" in txt2 and " · M)" not in txt2 and " · A)" not in txt2, txt2[-300:])
    check("légende N/Q/D/F dans le gabarit du think", all(pm_think.LEGEND[k].split(" — ")[0] in txt2 for k in pm_think.LEGEND))
    lines_ia = [json.dumps({"type": "assistant", "message": {"model": "claude-opus-5", "content": [{"type": "text", "text": "Je lis le fichier. Je propose de garder le repli en dur pour l'instant : il faudra le remplacer par une config quand le multi-instance arrivera. Ensuite je lance les tests."}]}}),
                json.dumps({"type": "assistant", "message": {"model": "claude-opus-5", "content": [{"type": "text", "text": "Les tests passent, je committe et je pousse la branche."}]}})]
    it2 = harv.harvest_items(lines_ia)
    check("moisson : une proposition de l'IA devient une note (extrait porteur), pas le compte-rendu d'exécution", len(it2) == 1 and it2[0][0] == "note" and it2[0][1].startswith("Je propose de garder le repli en dur") and it2[0][2].get("by") == "A", str(it2))
    harv.apply(th2, 78, it2, sid="s9"); check("note de l'IA signée du modèle", "Je propose de garder le repli en dur" in th2.read_text() and "· Claude Opus 5 · s:s9" in th2.read_text())
    merged = pm_think.render_merged("note", {78: pm_think.load(th2)}); check("légende dans le bloc fusionné", "N note —" in merged)
    n4 = pm_think.append(th2, "note", "ok pour /opt", rm_id=78, by="M", state="attente")
    r = subprocess.run([sys.executable, str(SCRIPTS / "pm-think-harvest.py"), "--prune", "--all", "--tasks-dir", str(tasks), "--delete", "--no-commit"], capture_output=True, text=True)
    left = pm_think.load(th2)["note"]["rows"]; left77 = pm_think.load(th)["note"]["rows"]
    check("prune --delete : la note pourrie disparaît, la pertinente reste ; la déjà-élaguée (❌ RM3062) part aussi", all(x["id"] != n4 for x in left) and any("Je propose" in x["cells"][2] for x in left) and all(x["id"] != n1 for x in left77) and any(x["id"] == n2 for x in left77), r.stdout + r.stderr)
    # RM3066 : un ticket livré n'a plus de note « à trier »
    (tasks / "RM79_livre.md").write_text("---\nredmine_id: 79\nstatus: a_tester_demandeur\n---\n")
    th3 = pm_think.think_path(tasks / "RM79_livre.md")
    pm_think.append(th3, "note", "il faudra revoir le vhost de test plus tard, il pointe encore l'ancien env", rm_id=79, by="M", state="attente")
    check("ticket_livre : a_tester_demandeur = livré, en_cours = non", harv.ticket_livre(tasks / "RM79_livre.md") is True and harv.ticket_livre(tasks / "RM77_slug.md") is False)
    ids = harv.prune(th3, dry=True)
    check("prune : sur un ticket livré, même une vraie dette tombe (elle devait devenir Q ou F avant la livraison)", len(ids) == 1, str(ids))
    # RM3066 : la garde de rattachement — une session d'un projet ne consigne pas dans le ticket d'un autre
    proj = pathlib.Path(tmp) / "wsA"; (proj / ".mmi-pm").mkdir(parents=True); autre = pathlib.Path(tmp) / "wsB"; (autre / ".mmi-pm").mkdir(parents=True)
    fiche = proj / ".mmi-pm" / "tasks" / "RM90_x.md"; fiche.parent.mkdir(); fiche.write_text("---\nredmine_id: 90\n---\n")
    check("même projet : le cwd du workspace porteur passe", harv.meme_projet(fiche, str(proj)) is True)
    check("autre projet : la consignation est refusée", harv.meme_projet(fiche, str(autre)) is False)
    check("cwd hors projet PM-tracké : le doute laisse passer", harv.meme_projet(fiche, tmp) is True)
    del os.environ["PM_THINK_AUTHOR"]; del os.environ["PM_THINK_HUMAN"]


# ── RM3090 : ce que le DEMANDEUR se demande est une question, pas une note ───
print("· classement des questions du demandeur (RM3090)")
spec_c = importlib.util.spec_from_file_location("classify", SCRIPTS / "pm-think-classify.py")
C = importlib.util.module_from_spec(spec_c); spec_c.loader.exec_module(C)

for texte, attendu in [
    ("est-ce que les demandes du worklog sont reliées aux questions ouvertes ?", "question"),
    ("pourquoi la jauge affiche 99 % alors que /context dit 20 % ?", "question"),
    ("faut-il garder le worklog ou le fusionner avec var/sessions ?", "question"),
    ("fais un ticket pour ça", "dette"),
    ("go 3015", "dette"),
    ("ajoute un réglage pour masquer les commandes tmux, ce serait bien", "dette"),
    ("mets les titres sur deux lignes, tu en penses quoi ?", "dette"),
]:
    check("« " + texte[:52] + "… » → " + attendu, C.type_heuristique("M", texte) == attendu,
          C.type_heuristique("M", texte))
check("un tour de l'AGENT n'est jamais une question du demandeur",
      C.type_heuristique("A", "et si on faisait autrement ?") == "dette")

lignes = [json.dumps({"type": "user", "message": {"content": "est-ce que les demandes du worklog sont reliées aux questions ouvertes ?"}}),
          json.dumps({"type": "user", "message": {"content": "ok super"}}),
          json.dumps({"type": "user", "message": {"content": "fais la MR et merge"}})]
items = harv.harvest_items(lignes)
check("la moisson en fait une QUESTION, signée du demandeur",
      [(k, e.get("by")) for k, _t, e in items] == [("question", "M")], str(items))

# elle ne passe PAS par le critère de la note : une question ne porte pas de dette
check("le critère de la note l'aurait écartée — c'est bien pour ça qu'on la teste avant",
      pm_think.note_pertinente("est-ce que les demandes du worklog sont reliées aux questions ouvertes ?")[0] is False)

# reprise : pas de doublon, même si le classement change
dossier90 = tasks.parent / "t3090"; dossier90.mkdir(exist_ok=True)
th90 = dossier90 / "RM90_reprise.think.md"
(dossier90 / "RM90_reprise.md").write_text("---\nredmine_id: 90\ntitle: Reprise\n---\n", encoding="utf-8")
pm_think.append(th90, "note", "une remarque relue plus tard", rm_id=90)
p90 = pm_think.load(th90)
check("un texte déjà consigné en note n'est pas rajouté en question",
      pm_think.has_text_anywhere(p90, "une remarque relue plus tard") is True)
check("…et un texte inconnu passe", pm_think.has_text_anywhere(p90, "tout autre chose ici") is False)
check("rejouer la moisson sur le même transcript n'ajoute rien",
      harv.apply(th90, 90, [("question", "une remarque relue plus tard", {"by": "M"})]) == [])

# le critère vit à UN endroit
src_h = (SCRIPTS / "pm-think-harvest.py").read_text(encoding="utf-8")
check("la moisson IMPORTE le critère, elle ne le recopie pas (D023)",
      "pm-think-classify.py" in src_h and "_ORDRE" not in src_h and "_INTERRO" not in src_h)
check("NORMS porte la définition arbitrée (D011) et la distinction demande / question",
      "tout ce qui n'est pas tranché" in (SCRIPTS.parent / "norms/src/modules/session-tooling.md").read_text(encoding="utf-8"))

print("✓ questions du demandeur (RM3090) : critère partagé, moisson, auteur, reprise sans doublon")

# ── RM3098 : avant compaction, on relit TOUT ─────────────────────────────────
print("· passe complète avant compaction (RM3098)")
src_h = (SCRIPTS / "pm-think-harvest.py").read_text(encoding="utf-8")
check("le mode hook accepte une passe complète", "def hook_mode(full: bool = False)" in src_h)
check("…et c'est elle qui décide de l'incrémental", "incremental=not full" in src_h)
check("--full existe en CLI", '"--full"' in src_h)
src_hooks = (SCRIPTS / "pm-claude-hooks-sync.py").read_text(encoding="utf-8")
check("la moisson est câblée sur PreCompact, en passe complète",
      '("PreCompact", None, "pm-think-harvest.py", " --full"' in src_hooks)
check("…et le hook reste borné en temps (une compaction n'attend pas)",
      '"pm-think-harvest.py", " --full", 90' in src_hooks)
check("les autres câblages n'ont pas bougé (Stop, SessionEnd)",
      src_hooks.count('"pm-think-harvest.py"') == 3)
norms = (SCRIPTS.parent / "norms/src/modules/session-tooling.md").read_text(encoding="utf-8")
check("NORMS dit ce qu'il faut consigner avant une compaction",
      "Avant une compaction" in norms and "--next" in norms and "n'existe plus" in norms)
kernel = (SCRIPTS.parent / "norms/src/NORMS-KERNEL.md").read_text(encoding="utf-8")
check("…et le KERNEL le déclenche quand le contexte se remplit",
      "une compaction approche" in kernel)

if FAIL:
    print(f"✗ {len(FAIL)} échec(s) : " + ", ".join(FAIL)); sys.exit(1)
print("OK — pm_think / pm-task-think / pm-think-merge / pm-think-harvest")
