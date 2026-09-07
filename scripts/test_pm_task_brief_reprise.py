#!/usr/bin/env python3
"""Tests RM2998 — le dossier de reprise de pm-task-brief.

Ce qui est protégé ici, dans l'ordre d'importance :

  1. **l'état du code est CONSTATÉ**, jamais recopié du frontmatter : celui-ci
     fige la branche à la prise du ticket, or elle a pu être fusionnée,
     supprimée, ou n'avoir jamais reçu un commit. Un dossier de reprise qui
     ment sur le code envoie retravailler ce qui est déjà livré ;
  2. un numéro de ticket se reconnaît **borné** — sans cela « 2510 » mord dans
     « 125100 », dans une taille de fichier, dans un horodatage, et le dossier
     se remplit de bruit qui ressemble à du signal ;
  3. une séance dont le transcript survit propose sa reprise, une séance perdue
     ne la propose pas — c'est toute la différence entre les deux situations ;
  4. le journal est débarrassé de sa plomberie (ticks, accusés Redmine) : sur un
     ticket réel, 33 entrées sur 49. Les garder noierait les cinq lignes qu'on
     est venu lire ;
  5. le brief d'onboarding reste plafonné à 30 lignes ; le dossier, jamais.

Lancer : python3 scripts/test_pm_task_brief_reprise.py
"""
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("pm_task_brief", HERE / "pm-task-brief.py")
tb = importlib.util.module_from_spec(spec)
sys.modules["pm_task_brief"] = tb
spec.loader.exec_module(tb)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# ── 1. reconnaître un ticket, sans mordre à côté ─────────────────────────────
check("« RM2510 » nomme le ticket", tb.mentions_ticket("voir RM2510 pour la suite", 2510))
check("« 2510 » nu aussi", tb.mentions_ticket("on reprend 2510 demain", 2510))
check("casse et espace tolérés", tb.mentions_ticket("rm 2510", 2510))
check("« 125100 » ne le nomme PAS", not tb.mentions_ticket("taille 125100 octets", 2510))
check("« 25101 » non plus", not tb.mentions_ticket("id 25101", 2510))
check("un autre ticket non plus", not tb.mentions_ticket("RM2511", 2510))
check("texte vide toléré", not tb.mentions_ticket(None, 2510))

# ── 2. l'entrée de worklog : la dernière fait foi ────────────────────────────
wl = {"items": [{"ref": "RM42", "status": "en_cours"},
                {"ref": "RM7", "status": "nouveau"},
                {"ref": "RM42", "status": "a_tester_demandeur", "next": "faire tester"}]}
check("l'entrée du ticket est trouvée", tb.worklog_item(wl, 42) is not None)
check("…et c'est la DERNIÈRE (l'état de fin de séance)",
      tb.worklog_item(wl, 42)["status"] == "a_tester_demandeur")
check("un ticket absent rend None", tb.worklog_item(wl, 99) is None)
check("un worklog vide ne casse rien", tb.worklog_item({}, 42) is None)

# ── 3. le journal, débarrassé de sa plomberie ────────────────────────────────
entries = [{"at": "2026-01-01", "by": "Note postée", "first": "constat"},
           {"at": "2026-01-01", "by": "Tick IA (claude-opus-5)", "first": "input=1"},
           {"at": "2026-01-01", "by": "report → Redmine", "first": "note"},
           {"at": "2026-01-02", "by": "Statut : a_faire → en_cours", "first": ""}]
gardees, ecartees = tb.log_signal(entries)
check("les ticks et accusés sont écartés", ecartees == 2)
check("…et rien d'autre", [e["by"] for e in gardees] ==
      ["Note postée", "Statut : a_faire → en_cours"])
check("journal vide toléré", tb.log_signal([]) == ([], 0))

# ── 4. séances et demandes, sur un décor fabriqué ────────────────────────────
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2998-"))
wdir, store = tmp / "worklogs", tmp / "projects"
(store / "-un-projet").mkdir(parents=True)
wdir.mkdir()
SID_VIVE = "aaaaaaaa-1111-2222-3333-444444444444"   # transcript encore là
SID_MORTE = "bbbbbbbb-1111-2222-3333-555555555555"  # transcript effacé
(store / "-un-projet" / f"{SID_VIVE}.jsonl").write_text("{}\n", encoding="utf-8")
for sid, st, nxt in ((SID_VIVE, "en_cours", "brancher le relais"), (SID_MORTE, "nouveau", "")):
    (wdir / f"{sid}.json").write_text(json.dumps({
        "session_id": sid, "updated": "2026-08-04T10:00",
        "items": [{"ref": "RM2510", "status": st, "next": nxt, "note": "n"},
                  {"ref": "RM999", "status": "ferme"}],
        "notifications": [{"message": "secret exposé sur RM2510"},
                          {"message": "sans rapport"}],
    }), encoding="utf-8")
hist = tmp / "history.jsonl"
hist.write_text("\n".join(json.dumps(o) for o in [
    {"sessionId": SID_VIVE, "timestamp": 100, "display": "on attaque RM2510"},
    {"sessionId": SID_VIVE, "timestamp": 200, "display": "et le relais SMTP ?"},
    {"sessionId": SID_MORTE, "timestamp": 50, "display": "découpe en sous-tâches"},
    {"sessionId": "zzz", "timestamp": 300, "display": "RM2510 ailleurs"},
]) + "\n", encoding="utf-8")
tb.WORKLOG_DIR, tb.CLAUDE_STORES, tb.HISTORY_FILE = wdir, [store], hist

ses = tb.sessions_of_ticket(2510)
check("les deux séances du ticket sont trouvées", len(ses) == 2)
check("celle d'un autre ticket n'entre pas",
      all(s["session_id"] in (SID_VIVE, SID_MORTE) for s in ses))
vive = next(s for s in ses if s["session_id"] == SID_VIVE)
morte = next(s for s in ses if s["session_id"] == SID_MORTE)
check("la séance vivante porte son transcript", vive["transcript"] is not None)
check("la séance perdue n'en a pas", morte["transcript"] is None)
check("la prochaine étape est remontée", vive["next"] == "brancher le relais")
check("seules les notifications parlant du ticket sont retenues",
      vive["notifications"] == ["secret exposé sur RM2510"])

pr, tot = tb.prompts_of([SID_VIVE, SID_MORTE], 2510)
check("seules les demandes nommant le ticket sont retenues",
      [p["text"] for p in pr] == ["on attaque RM2510"])
check("…mais le total par séance est compté", tot == {SID_VIVE: 2, SID_MORTE: 1})
check("une séance étrangère n'entre pas dans le compte", "zzz" not in tot)
pr_all, _ = tb.prompts_of([SID_VIVE, SID_MORTE], 2510, tous=True)
check("--prompts-all rend tout, dans l'ordre chronologique",
      [p["text"] for p in pr_all] ==
      ["découpe en sous-tâches", "on attaque RM2510", "et le relais SMTP ?"])
tb.HISTORY_FILE = tmp / "nexiste-pas.jsonl"
check("historique absent : pas d'exception", tb.prompts_of([SID_VIVE], 2510) == ([], {}))
tb.HISTORY_FILE = hist

# ── 5. l'état du code, constaté dans un vrai dépôt ───────────────────────────
repo = tmp / "depot"
repo.mkdir()
G = ["git", "-C", str(repo)]
subprocess.run(G[:1] + ["init", "-q", "-b", "main", str(repo)], check=True,
               capture_output=True)
for k, v in (("user.email", "t@t"), ("user.name", "t")):
    subprocess.run(G + ["config", k, v], check=True, capture_output=True)
(repo / "a.txt").write_text("1")
subprocess.run(G + ["add", "a.txt"], check=True, capture_output=True)
subprocess.run(G + ["commit", "-qm", "base"], check=True, capture_output=True)
# `origin/dev` simulé par une ref distante locale : code_state compare à elle
subprocess.run(G + ["update-ref", "refs/remotes/origin/dev", "HEAD"], check=True,
               capture_output=True)
subprocess.run(G + ["checkout", "-qb", "2510-relais"], check=True, capture_output=True)
(repo / "b.txt").write_text("2")
subprocess.run(G + ["add", "b.txt"], check=True, capture_output=True)
subprocess.run(G + ["commit", "-qm", "travail en cours"], check=True, capture_output=True)
(repo / "c.txt").write_text("3")          # non commité → worktree sale

fm = {"git": {"branch": "2510-relais", "worktree": str(repo), "mr_url": None}}
faux_md = tmp / "p" / "tasks" / "RM2510_x.md"
faux_md.parent.mkdir(parents=True)
st = tb.code_state(fm, faux_md)
check("la branche est constatée présente", st["branch_exists"])
check("le commit non fusionné est vu", len(st["unmerged"]) == 1)
check("…et le ticket n'est donc PAS déclaré fusionné", st["merged"] is False)
check("la base de comparaison est origin/dev", st["base"] == "origin/dev")
check("le worktree sale est signalé", st["dirty"] == 1)

st2 = tb.code_state({"git": {"branch": "branche-fantome", "worktree": str(repo)}}, faux_md)
check("une branche disparue est dite introuvable", st2["branch_exists"] is False)
check("…sans prétendre qu'elle est fusionnée", st2["merged"] is None)
st3 = tb.code_state({"git": {}}, faux_md)
check("aucune branche notée : pas d'exception", st3["branch_exists"] is False)
st4 = tb.code_state({"git": {"branch": "x", "worktree": str(tmp / "nulle-part")}}, faux_md)
check("un worktree disparu est signalé absent", st4["worktree_exists"] is False)

# ── 6. le rendu ──────────────────────────────────────────────────────────────
data = {"rm_id": 2510, "sessions": ses, "prompts": pr, "prompts_total": tot,
        "prompts_filtres": True, "code": st, "log_full": entries}
txt = "\n".join(tb.reprise_lines(data))
check("la prochaine étape est mise en tête", txt.index("prochaine étape") < txt.index("séances"))
check("la séance vivante propose sa reprise", f"claude --resume {SID_VIVE}" in txt)
check("la séance perdue ne la propose pas", f"claude --resume {SID_MORTE}" not in txt)

# La séance perdue doit renvoyer là où elle survit encore.
recons = tmp / "clients" / "c" / "projects" / "p" / "docs" / "sessions-perdues-2026-09-06"
recons.mkdir(parents=True)
(recons / f"{SID_MORTE}.md").write_text("# séance", encoding="utf-8")
check("la reconstitution d'une séance perdue est retrouvée",
      tb.reconstitution_of(SID_MORTE, tmp / "clients") == str(recons / f"{SID_MORTE}.md"))
check("…et rien n'est inventé pour une séance sans reconstitution",
      tb.reconstitution_of(SID_VIVE, tmp / "clients") is None)
check("racine absente : pas d'exception", tb.reconstitution_of(SID_MORTE, None) is None)
morte["reconstitution"] = str(recons / f"{SID_MORTE}.md")
txt2 = "\n".join(tb.reprise_lines(data))
check("le rendu renvoie vers la reconstitution", "reconstitution :" in txt2)
check("le commit non fusionné apparaît", "travail en cours" in txt)
check("la plomberie du journal est comptée, pas affichée",
      "de plomberie écartées" in txt and "Tick IA" not in txt)
vide = "\n".join(tb.reprise_lines({"rm_id": 1, "sessions": [], "prompts": [],
                                   "prompts_total": {}, "code": {}, "log_full": []}))
check("un ticket sans rien ne casse pas le rendu", "aucune séance enregistrée" in vide)
check("…et le dit pour le code aussi", "aucune branche notée" in vide)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
