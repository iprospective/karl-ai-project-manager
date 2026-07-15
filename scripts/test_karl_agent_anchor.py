#!/usr/bin/env python3
"""Tests RM2284 — le contexte d'ancrage ticket transite dans le prompt initial.

Unitaire (sans tmux ni réseau) : _anchor_context et la condition de préfixe
d'op_spawn. Lancer : python3 scripts/test_karl_agent_anchor.py
"""
import importlib.util
import pathlib
import sys
import types

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


# — _anchor_context : ticket résolu en local —
def fake_find(rm_id):
    return pathlib.Path("/x/projects/clients/acme/projects/shop/tasks/RM9_t.md")


ka._find_task_file = fake_find
ka._task_client_project = lambda tf: ("acme", "shop")
ka._read_task_meta = lambda tf: {"title": "Titre du ticket", "status": "a_faire"}
ctx = ka._anchor_context("9")
check("préfixe contient RM<id>", "RM9" in ctx)
check("préfixe contient client/projet", "client acme, projet shop" in ctx)
check("préfixe contient titre et statut", "« Titre du ticket »" in ctx and "statut a_faire" in ctx)
check("préfixe mono-ligne (send-keys -l)", "\n" not in ctx)

# — ticket non résolu : l'id transite quand même —
ka._find_task_file = lambda rm_id: None
ctx2 = ka._anchor_context("77")
check("non résolu : id transite quand même", "RM77" in ctx2 and "\n" not in ctx2)

# — condition de préfixe (celle d'op_spawn) —
cond = lambda rm_id, prompt: ka._is_ticket_sid(rm_id) and f"rm{rm_id}" not in str(prompt).lower()
check("prompt libre sans mention → préfixe", cond("2140", "améliore la lisibilité du cockpit"))
check("prompt mentionnant RM<id> → pas de doublon", not cond("2140", "traite la tâche RM2140"))
check("mention en minuscules → pas de doublon", not cond("2140", "voir rm2140 svp"))
check("session slug (non ticket) → pas de préfixe", not cond("audit-perf", "fais l'audit"))

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests ancrage RM2284 passent")
