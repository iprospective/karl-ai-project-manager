#!/usr/bin/env python3
"""Tests RM3238 — pas de MEP prod ni de merge vers main/master avec une question non tranchée.

Ce qui doit tenir : la garde voit les MÊMES tickets que pm-promote (branche `<id>-`, « RM<id> »,
« Merge branch '<id>-… »), ne regarde QUE la prod (`main`/`master`) et jamais un dépôt de données PM,
refuse avec les questions nommées, se lève par un drapeau explicite, et ne bloque pas sur de l'inconnu.

Lancer : python3 scripts/test_pm_questions_gate.py
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core           # noqa: E402

hermetic_core()                                  # AVANT l'import des modules PM
import pm_questions_gate as G                    # noqa: E402
import pm_think                                  # noqa: E402
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def load(name, fname):
    spec = importlib.util.spec_from_file_location(name, str(HERE / fname))
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m)
    return m


tmp = Path(tempfile.mkdtemp(prefix="pm-qgate-"))


def sheet(rm_id, status="a_mep", questions=(), tranchees=()):
    p = tmp / f"RM{rm_id}_test.md"
    p.write_text(f"---\nredmine_id: {rm_id}\ntitle: 'T'\nstatus: {status}\nstatus_history: []\n"
                 f"updated: 2026-01-01T10:00\n---\n\n## Contexte\n", encoding="utf-8")
    t = pm_think.think_path(p)
    for q in questions:
        pm_think.append(t, "question", q, rm_id=rm_id)
    for qid in tranchees:
        pm_think.set_state(t, qid, "valide")
    return p


print("[RM3238] lecture des tickets — la même que pm-promote")
check("« RM<id> » et « Merge branch '<id>-… » sont lus, sans doublon",
      G.ids_in_text("RM3001 : x\nMerge branch '3002-slug' into 'dev'\nRM3001 encore") == [3001, 3002])
check("un auto-commit pm(...) nomme son ticket", G.ids_in_text("pm(think): RM3218 +Q001") == [3218])
check("branche <id>-slug → ticket", G.id_from_branch("3238-bloquer-la-mep") == 3238)
check("branche sans préfixe → aucun", G.id_from_branch("dev") is None and G.id_from_branch("feature/x") is None)
promote = (HERE / "pm-promote.py").read_text(encoding="utf-8")
check("pm-promote délègue sa lecture à la garde (une seule définition)", "pm_questions_gate.carried_ids" in promote)

print("\n[RM3239] tickets PORTÉS par un lot, pas simplement cités")
LOT = ["Merge branch '3238-bloquer-la-mep-prod-et-le-merge-vers-mai-m1-s112' into 'dev'",
       "Merge origin/dev dans RM3238 : normes 2.54.0 après 2.53.0 (RM3228), plafond relevé (RM3035)",
       "Merge remote-tracking branch 'origin/dev' into 3228-statut-redmine-24-etude-cdc-a-corriger-m-m1-s112",
       "Merge branch '3227-cockpit-commentaire' into 'dev'",
       "RM3226 : les questions passent dans le CF 36\n\nSort la section RM3116 de la description ; RM3035.",
       "pm(think): RM3218 +Q001"]
got = G.carried_ids(LOT)
check("le lot réel du 2026-09-18 : 3238, 3228, 3227, 3226", sorted(got) == [3226, 3227, 3228, 3238], got)
check("un auto-commit `pm(…): RM<id>` (plomberie de données) ne porte pas de livraison", 3218 not in got)
check("un ticket cité dans un CORPS n'est pas porté (RM3116, RM3035)", 3116 not in got and 3035 not in got)
check("…ni cité en fin de SUJET", 3035 not in G.carried_ids(["Merge origin/dev dans RM3238 : blabla (RM3035)"]))
check("« into '<id>-…' » est reconnu", G.carried_ids(["Merge branch 'dev' into '4001-x'"]) == [4001])
check("la lecture large d'annotation (RM2809) reste inchangée", 3035 in G.ids_in_text("\n".join(LOT)))

print("\n[RM3238] ce qui est de la prod, ce qui n'en est pas")
check("main et master sont la prod", G.is_prod_branch("main") and G.is_prod_branch("master"))
check("dev n'est pas la prod", not G.is_prod_branch("dev") and not G.is_prod_branch("3238-x"))
check("un dépôt *-core est un dépôt de données (sans dépôt local)", G.is_data_repo("iprospective/x/ai-pm-core"))
check("un dépôt de code ne l'est pas", not G.is_data_repo("sfy/pisceen-dercya/pisceen-prestashop"))
core = tmp / "core"; core.mkdir(); subprocess.run(["git", "init", "-q", str(core)], check=True)
(core / ".mmi-pm").mkdir()
check("le dépôt local fait foi : `.mmi-pm/` réel ⇒ données, même sans le suffixe", G.is_data_repo("a/b", local_repo=core))

print("\n[RM3238] questions ouvertes d'une fiche")
s1 = sheet(9101, questions=["Base dédiée ou partagée ?", "Quelle branche ?"], tranchees=["Q001"])
qs = G.open_questions_of_sheet(s1)
check("seules les questions NON tranchées comptent", [q for q, _ in qs] == ["Q002"], qs)
check("avec leur texte", qs and "Quelle branche" in qs[0][1])
check("pas de think ⇒ rien", G.open_questions_of_sheet(sheet(9102)) == [])
check("toutes tranchées ⇒ rien", G.open_questions_of_sheet(sheet(9103, questions=["x ?"], tranchees=["Q001"])) == [])
cfg = type("C", (), {"find_task": lambda self, i: {9101: s1}.get(int(i))})()
check("blocked() ne garde que les tickets bloquants ; ticket inconnu ⇒ pas de faux blocage",
      list(G.blocked([9101, 9102, 4242], cfg)) == [9101])
msg = G.refusal({9101: qs}, "merge de !1", "--ignore-questions")
check("le refus nomme ticket, question, et le contournement", "RM9101" in msg and "Q002" in msg and "--ignore-questions" in msg)

print("\n[RM3238] statuts — pm-task-status-update")
ST = load("pm_task_status_update", "pm-task-status-update.py")
check("MEP prod gardée : a_mep_prod et en_mep", set(G.GATED_STATUSES) == {"a_mep_prod", "en_mep"})
check("a_mep (préprod) avertit seulement", G.WARN_STATUSES == ("a_mep",))
src = (HERE / "pm-task-status-update.py").read_text(encoding="utf-8")
check("le refus passe par la garde partagée, levable par --ignore-think",
      '_qg.refusal(_bm, f"passage en {args.status}", "--ignore-think")' in src)
check("le contournement est tracé dans la note Redmine", "garde RM3238 levée par --ignore-think" in src
      and "extra_notes = [_gate_note] if _gate_note else []" in src)
s2 = sheet(9104, status="a_mep", questions=["Encore ouverte ?"])
ST.PMConfig.load = staticmethod(lambda: type("C", (), {"find_task": lambda self, i: s2})())
d = ST.next_transitions(9104, check_redmine=False)
t = {x["status"]: x for x in d["transitions"]}
check("--list-next marque en_mep bloquée par Q001", t.get("en_mep", {}).get("blocked_by_questions") == ["Q001"], t.get("en_mep"))
check("…et laisse les autres transitions libres", t.get("en_pause", {}).get("blocked_by_questions") == [])
s3 = sheet(9105, status="a_mep")
ST.PMConfig.load = staticmethod(lambda: type("C", (), {"find_task": lambda self, i: s3})())
check("sans question ouverte, rien n'est bloqué",
      all(not x["blocked_by_questions"] for x in ST.next_transitions(9105, check_redmine=False)["transitions"]))

print("\n[RM3238] merge — pm-mr")
MR = load("pm_mr", "pm-mr.py")
G.open_questions = lambda i, cfg=None: {3001: [("Q001", "ouverte")]}.get(int(i), [])
PR = lambda src, tgt: type("P", (), {"iid": 7, "source": src, "target": tgt})()
PRJ = lambda path="grp/site": type("J", (), {"path": path})()
class Forge:
    def __init__(self, msgs): self.msgs, self.calls = msgs, 0
    def pr_commit_messages(self, project, iid, token): self.calls += 1; return self.msgs
def refuse(forge, pr, prj=None, ignore=False, ids=None):
    try:
        MR._guard_questions(forge, prj or PRJ(), pr, "tok", ids=ids, ignore=ignore)
        return False
    except SystemExit as e:
        return "RM3001" in str(e)
check("MR <id>-… → main avec question ouverte : refusée", refuse(Forge([]), PR("3001-x", "main")))
check("…vers master aussi", refuse(Forge([]), PR("3001-x", "master")))
check("…et passe avec --ignore-questions", not refuse(Forge([]), PR("3001-x", "main"), ignore=True))
f = Forge(["RM3001 : x"])
check("MR vers dev : jamais concernée (et la forge n'est même pas interrogée)",
      not refuse(f, PR("3001-x", "dev")) and f.calls == 0)
check("promotion dev → main : les tickets viennent des commits de la MR",
      refuse(Forge(["Merge branch '3001-x' into 'dev'"]), PR("dev", "main")))
check("dépôt de données *-core : jamais bloqué", not refuse(Forge(["RM3001"]), PR("dev", "main"), prj=PRJ("a/b-core")))
check("forge muette sur les commits : on ne bloque pas sur de l'inconnu", not refuse(Forge(None), PR("dev", "main")))
check("un ticket sans question ne bloque pas", not refuse(Forge(["RM4242"]), PR("4242-x", "main")))
check("RM3239 : un ticket seulement CITÉ dans un commit de la MR ne bloque pas",
      not refuse(Forge(["RM4242 : x\n\nvoir aussi RM3001"]), PR("dev", "main")))
check("RM3239 : …mais un commit qui le PORTE bloque", refuse(Forge(["RM3001 : x"]), PR("dev", "main")))
check("pm-promote fournit son lot : il fait foi", refuse(Forge([]), PR("dev", "main"), ids=[3001]))
mr = (HERE / "pm-mr.py").read_text(encoding="utf-8")
check("merge et create --merge exposent --ignore-questions", mr.count('add_argument("--ignore-questions"') == 2)
check("la garde n'agit que sur une MR encore ouverte", 'if pr.state == "opened":\n        _guard_questions' in mr)
check("pm-promote : garde ET annotation lisent les SUJETS du lot (portés) — RM3222",
      'carried_ids(p.stdout.splitlines())' in promote and "ids_in_text" not in promote)
check("pm-promote : refus hors dry-run, annonce en dry-run",
      "not args.dry_run and not args.ignore_questions" in promote and "questions non tranchées (RM3238)" in promote)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — garde des questions avant la prod (RM3238)"))
sys.exit(1 if FAIL else 0)
