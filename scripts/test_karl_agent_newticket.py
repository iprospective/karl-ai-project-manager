#!/usr/bin/env python3
"""Tests RM2672 — création de ticket : champs complets du formulaire pleine page.

Unitaire, sans réseau (pm-task-add simulé) : les champs que la carte repliée ne
portait pas (passe agent-testeur, env cible, estimation, difficulté) sont transmis,
validés, et omis quand ils sont vides.

Lancer : python3 scripts/test_karl_agent_newticket.py
"""
import importlib.util
import os
import pathlib
import sys
import tempfile

os.environ["KARL_AGENT_STATE_DIR"] = tempfile.mkdtemp(prefix="rm2672-")
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("\u2713 " if cond else "\u2717 ") + name)
    if not cond:
        fails.append(name)


calls = []


class FakeProc:
    returncode, stdout, stderr = 0, "9998\n", ""


ka.subprocess.run = lambda cmd, **kw: (calls.append(cmd), FakeProc())[1]
BASE = {"title": "Un titre", "project": "iprospective/pm-ai-agents",
        "type": "feature", "priority": "normal"}

r = ka.op_create_ticket(dict(BASE, agent_test="non", target_env="test",
                             est_human_minutes="30", est_ai_minutes="90",
                             est_tokens="80000", difficulty="medium",
                             tags="cockpit", description="Détails."))
argv = calls[-1]
check("id capturé de la sortie porcelain (jamais prédit)", r["rm_id"] == "9998")
for flag, val in (("--agent-test", "non"), ("--target-env", "test"),
                  ("--est-human-minutes", "30"), ("--est-ai-minutes", "90"),
                  ("--est-tokens", "80000"), ("--est-difficulty", "medium")):
    check(f"champ transmis : {flag}", flag in argv and val in argv)
check("description passée par fichier ou argument",
      "--description" in argv or "--description-file" in argv)


def refuses(**bad):
    try:
        ka.op_create_ticket(dict(BASE, **bad))
        return False
    except ka.ApiError:
        return True


check("passe agent-testeur inventée refusée", refuses(agent_test="peut-etre"))
check("env cible non kebab-case refusé", refuses(target_env="PROD; rm -rf /"))
check("temps non numérique refusé", refuses(est_ai_minutes="beaucoup"))
check("temps négatif refusé", refuses(est_tokens="-5"))
check("difficulté hors catalogue refusée", refuses(difficulty="enorme"))
check("type hors catalogue refusé", refuses(type="epic"))
check("projet sans client refusé", refuses(project="pm-ai-agents"))

ka.op_create_ticket(BASE)
argv = calls[-1]
check("champs optionnels omis quand vides",
      "--agent-test" not in argv and "--est-human-minutes" not in argv
      and "--target-env" not in argv)

print()
if fails:
    print(f"\u2717 {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("\u2713 tous les tests passent")
