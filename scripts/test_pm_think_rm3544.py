#!/usr/bin/env python3
"""Tests RM3544 — une question du demandeur n'est plus une Q « à trancher » par heuristique.

  - hook : question du demandeur -> N `auto` (pas de Q) ; AskUserQuestion sans réponse -> Q `agent` ;
  - garde de merge / de MEP : une Q `auto` est ignorée, une Q `agent` / `llm` bloque, le message dit la source ;
  - fermeture du ticket : ni Q `auto` ni N `auto` ne bloquent ;
  - prune-auto : dry-run juste, --apply invalide, --en-note requalifie ;
  - pm-think-classify : sans fournisseur, sort en 0.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core, subprocess_env        # noqa: E402
hermetic_core()
import pm_think                                                # noqa: E402
import pm_questions_gate as G                                  # noqa: E402

FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def load(name, fname):
    spec = importlib.util.spec_from_file_location(name, str(HERE / fname))
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m)
    return m


harv = load("harv3544", "pm-think-harvest.py")
tmp = Path(tempfile.mkdtemp(prefix="pm-rm3544-"))


def sheet(rm_id, status="a_mep"):
    p = tmp / f"RM{rm_id}_t.md"
    p.write_text(f"---\nredmine_id: {rm_id}\ntitle: 'T'\nstatus: {status}\nstatus_history: []\n"
                 f"updated: 2026-01-01T10:00\n---\n\n## Contexte\n", encoding="utf-8")
    return p


print("[hook] question du demandeur -> N auto")
Q = "est-ce que les demandes du worklog sont reliées aux questions ouvertes ?"
lignes = [json.dumps({"type": "user", "message": {"content": Q}}),
          json.dumps({"type": "assistant", "message": {"content": "Voici ce que je vois : les deux vues lisent le même carnet."}})]
items = harv.harvest_items(lignes)
check("aucune Q créée", not [i for i in items if i[0] == "question"], str(items))
check("une N signée du demandeur, source auto", [(k, e.get("by"), e.get("source")) for k, _t, e in items] == [("note", "M", "auto")], str(items))
th = pm_think.think_path(sheet(9501))
harv.apply(th, 9501, items, sid="abcd1234efgh")
txt = th.read_text(encoding="utf-8")
check("la ligne porte src:auto et reste une note", "src:auto" in txt and pm_think.counters(pm_think.load(th))["questions_open"] == 0)
check("N auto : hors du compteur « à trier » bloquant", pm_think.counters(pm_think.load(th))["notes_pending"] == 0
      and pm_think.notes_auto(pm_think.load(th)) == 1)

ask = [json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t2", "name": "AskUserQuestion",
                  "input": {"questions": [{"question": "Et le seuil ?", "options": []}]}}]}}),
       json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t2", "content": "[Request interrupted by user]"}]}})]
it2 = harv.harvest_items(ask)
check("AskUserQuestion sans réponse -> Q source agent", [(k, e.get("source")) for k, _t, e in it2] == [("question", "agent")], str(it2))
th2 = pm_think.think_path(sheet(9502))
harv.apply(th2, 9502, it2, sid="abcd1234efgh")
sec = pm_think.load(th2)["question"]
check("elle compte comme question ouverte, source agent",
      pm_think.counters(pm_think.load(th2))["questions_open"] == 1 and pm_think.row_source(sec["rows"][0]) == "agent")

print("\n[garde] merge / MEP")
s = sheet(9503)
t = pm_think.think_path(s)
pm_think.append(t, "question", "capture heuristique", rm_id=9503, by="M", sid="s1234567", source="auto")
check("Q auto seule : la garde ne bloque pas", G.open_questions_of_sheet(s) == [])
pm_think.append(t, "question", "arbitrage de l'agent", rm_id=9503, by="A", sid="s1234567")
pm_think.append(t, "question", "arbitrage du tri LLM", rm_id=9503, by="M", sid="s1234567", source="llm")
qs = G.open_questions_of_sheet(s)
check("Q agent + Q llm bloquent, la Q auto non", [q for q, _ in qs] == ["Q002", "Q003"], str(qs))
msg = G.refusal({9503: qs}, "merge de !1", "--ignore-questions")
check("le message liste chaque Q avec sa source", "Q002 [source agent]" in msg and "Q003 [source llm]" in msg and "Q001" not in msg, msg)
check("les anciens appelants dépaquettent toujours (id, texte)", all(len(x) == 2 for x in qs))

print("\n[fermeture] une N/Q auto ne bloque pas")
s4 = sheet(9504, status="a_tester_demandeur")
t4 = pm_think.think_path(s4)
pm_think.append(t4, "note", "une question du demandeur", rm_id=9504, by="M", sid="s1234567", source="auto")
pm_think.append(t4, "question", "capture", rm_id=9504, by="M", sid="s1234567", source="auto")
c = pm_think.counters(pm_think.load(t4))
check("questions_open = 0 et notes_pending = 0", c["questions_open"] == 0 and c["notes_pending"] == 0, str(c))
pm_think.append(t4, "note", "note de l'agent à trier", rm_id=9504, by="A", sid="s1234567")
check("une N normale bloque encore", pm_think.counters(pm_think.load(t4))["notes_pending"] == 1)
src = (HERE / "pm-task-status-update.py").read_text(encoding="utf-8")
check("la fermeture lit les compteurs (donc exclut les auto)", '_c["questions_open"] or _c["notes_pending"]' in src)

print("\n[prune-auto]")
d = tmp / "pa"; d.mkdir()
(d / "RM9601_x.md").write_text("---\nredmine_id: 9601\ntitle: T\nstatus: en_cours\n---\n", encoding="utf-8")
tp = d / "RM9601_x.think.md"
pm_think.append(tp, "question", "tu peux enchaîner ?", rm_id=9601, by="M", sid="s1234567", when="2026-10-20")    # fausse
pm_think.append(tp, "question", "une autre blague ?", rm_id=9601, by="M", sid="s1234567", when="2026-10-21")      # fausse
pm_think.append(tp, "question", "ancienne (avant RM3090)", rm_id=9601, by="M", sid="s1234567", when="2026-08-01")  # trop vieille
pm_think.append(tp, "question", "posée à la main", rm_id=9601, by="M", when="2026-10-20")                         # sans session
pm_think.append(tp, "question", "AskUserQuestion sans réponse", rm_id=9601, by="A", sid="s1234567", when="2026-10-20")  # agent
pm_think.append(tp, "question", "voulue par le tri", rm_id=9601, by="M", sid="s1234567", when="2026-10-20", source="llm")
pm_think.append(tp, "question", "déjà tranchée", rm_id=9601, by="M", sid="s1234567", when="2026-10-20", state="valide")
r = subprocess.run([sys.executable, str(HERE / "pm-think-harvest.py"), "--prune-auto", "--tasks-dir", str(d)],
                   capture_output=True, text=True, env=subprocess_env())
check("dry-run : 2 fausses Q, rien d'écrit", "2 fausse(s) Q sur 1 ticket(s)" in r.stdout and "Q001, Q002" in r.stdout
      and "🕐" in tp.read_text() and "RM3544" not in tp.read_text(), r.stdout + r.stderr)
r = subprocess.run([sys.executable, str(HERE / "pm-think-harvest.py"), "--prune-auto", "--apply", "--no-commit", "--tasks-dir", str(d)],
                   capture_output=True, text=True, env=subprocess_env())
sec = pm_think.load(tp)["question"]
etat = {x["id"]: x["state"] for x in sec["rows"]}
check("--apply : Q001 et Q002 passent ❌ avec le motif", etat["Q001"] == "invalide" and etat["Q002"] == "invalide"
      and "moisson automatique (RM3544)" in tp.read_text(), str(etat))
check("les autres Q sont intactes", etat["Q003"] == "attente" and etat["Q004"] == "attente" and etat["Q005"] == "attente"
      and etat["Q006"] == "attente", str(etat))
check("rejouer ne trouve plus rien", harv.fausses_questions(tp) == [])
d2 = tmp / "pa2"; d2.mkdir()
(d2 / "RM9602_x.md").write_text("---\nredmine_id: 9602\ntitle: T\nstatus: en_cours\n---\n", encoding="utf-8")
tp2 = d2 / "RM9602_x.think.md"
pm_think.append(tp2, "question", "une question captée", rm_id=9602, by="M", sid="s1234567", when="2026-10-20")
harv.prune_auto(tp2, apply=True, en_note=True)
p2 = pm_think.load(tp2)
check("--en-note : une N auto (ex-Q001), plus de Q ouverte",
      pm_think.notes_auto(p2) == 1 and pm_think.counters(p2)["questions_open"] == 0 and "ex-Q001" in tp2.read_text())

print("\n[classify] sans fournisseur")
import io, os, contextlib                                             # noqa: E402
cl = load("cl3544", "pm-think-classify.py")
for k in ("OLLAMA_HOST", "OLLAMA_API_KEY", "LLM_BASE_URL", "ANTHROPIC_API_KEY", "PM_CLASSIFY_CMD"):
    os.environ.pop(k, None)
cl.moteur_du_registre = lambda project=None: (None, None)
appels = []
cl.appelle = lambda *a, **k: appels.append(a) or ("[]", 0.0)
buf = io.StringIO(); argv0 = sys.argv
sys.argv = ["pm-think-classify", "--all", "--limit", "1"]
with contextlib.redirect_stdout(buf):
    rc = cl.main()
sys.argv = argv0
check("sortie 0 + message explicite, aucun appel de modèle (ni claude -p)", rc == 0 and "aucun fournisseur" in buf.getvalue() and not appels, buf.getvalue())

if FAIL:
    print(f"✗ {len(FAIL)} échec(s) : " + ", ".join(FAIL)); sys.exit(1)
print("OK — RM3544 (moisson, garde, fermeture, prune-auto, classify)")
