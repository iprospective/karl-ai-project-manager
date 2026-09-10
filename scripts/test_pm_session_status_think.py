#!/usr/bin/env python3
"""Tests RM3076 — le pont session → `.think.md` du ticket (RM3053) écrit vraiment.

Le bug : `_think_note()` appelait `pm_git.autocommit(...)` sans que `pm_git` soit importé,
et son `except Exception` transformait la `NameError` en simple avertissement console. La
demande était bien enregistrée au worklog ; la note n'atteignait jamais le think. Un pont
« best-effort » muet est un pont mort — d'où deux verrous ici :

  1. `pm_git` (et tout ce que `_think_note` utilise) est RÉSOLVABLE au niveau module — un
     import manquant se voit sans exécuter le chemin ;
  2. `request --ticket` et `notify --ref` écrivent la note dans le `.think.md`, sans
     avertissement, et le second appel identique n'ajoute rien (dédoublonnage).

Hermétique : arbo PM temporaire, worklog temporaire, auto-commit débrayé (PM_GIT_AUTOCOMMIT=0).
Lancer : python3 scripts/test_pm_session_status_think.py
"""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_think                                                     # noqa: E402
from test_support import subprocess_env                             # noqa: E402

spec = importlib.util.spec_from_file_location("pss", HERE / "pm-session-status.py")
pss = importlib.util.module_from_spec(spec); sys.modules["pss"] = pss; spec.loader.exec_module(pss)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# ── 1. les noms qu'utilise le pont existent au niveau module ─────────────────
# C'est CE test qui aurait attrapé le bug sans jouer le chemin complet.
for name in ("pm_git", "pmout", "re"):
    check(f"`{name}` est résolvable dans pm-session-status", hasattr(pss, name))
check("pm_git expose autocommit", callable(getattr(getattr(pss, "pm_git", None), "autocommit", None)))

# ── 2. le pont écrit vraiment, et une seule fois ─────────────────────────────
tmp = pathlib.Path(tempfile.mkdtemp(prefix="pm-think-bridge-"))
projects = tmp / "projects" / "clients" / "acme" / "projects" / "site"
tasks = projects / "tasks"; tasks.mkdir(parents=True)
(projects / "meta.yml").write_text("redmine:\n  project_id: 1\n", encoding="utf-8")
sheet = tasks / "RM4242_essai-du-pont.md"
sheet.write_text("---\nschema_version: 1.11.0\nredmine_id: 4242\ntitle: Essai du pont\n"
                 "status: en_cours\nupdated: 2026-09-10T10:00\n---\n\n## Contexte\n\nx\n", encoding="utf-8")
(tasks / "RM4242_essai-du-pont.log.md").write_text("# Journal RM4242\n", encoding="utf-8")
(tmp / "pm.config.yml").write_text(
    "roots:\n  projects_root: " + str(tmp / "projects") + "\n"
    "paths:\n  entity: 'clients/{entity}'\n  project: 'clients/{entity}/projects/{project}'\n"
    "  tasks_dir: 'clients/{entity}/projects/{project}/tasks'\n"
    "  docs_dir: 'clients/{entity}/projects/{project}/docs'\n", encoding="utf-8")

worklogs = tmp / "worklogs"; worklogs.mkdir()
env = subprocess_env(PM_CONFIG=str(tmp / "pm.config.yml"), PROJECTS_PATH=str(tmp / "projects"),
                     PM_SESSION_WORKLOG_DIR=str(worklogs), PM_GIT_AUTOCOMMIT="0",
                     CLAUDE_CODE_SESSION_ID="sess-test-3076", KARL_JOURNAL_DIR=str(tmp / "logs"))


def run(*args):
    return subprocess.run([sys.executable, str(HERE / "pm-session-status.py"), *args],
                          capture_output=True, text=True, env=env, cwd=str(tmp))


r = run("request", "une demande rattachée au ticket", "--status", "ticketee", "--ticket", "RM4242")
think = pm_think.think_path(sheet)
check("request --ticket : sortie sans avertissement", "think non mis à jour" not in (r.stdout + r.stderr),
      (r.stdout + r.stderr)[-300:])
check("request --ticket : la note est dans le .think.md", think.is_file()
      and "une demande rattachée au ticket" in think.read_text(encoding="utf-8"),
      think.read_text(encoding="utf-8")[-300:] if think.is_file() else "pas de think")
check("les compteurs sont posés sur la fiche", "think:" in sheet.read_text(encoding="utf-8")
      and "notes_pending: 1" in sheet.read_text(encoding="utf-8"))

run("request", "une demande rattachée au ticket", "--status", "ticketee", "--ticket", "RM4242")
n_notes = len(pm_think.load(think).get("note", {}).get("rows", []))
check("le même texte n'est pas consigné deux fois", n_notes == 1, f"{n_notes} note(s)")

r = run("notify", "garde-fou déclenché sur la branche", "--kind", "garde-fou", "--ref", "RM4242")
txt = think.read_text(encoding="utf-8")
check("notify --ref : sortie sans avertissement", "think non mis à jour" not in (r.stdout + r.stderr),
      (r.stdout + r.stderr)[-300:])
check("notify --ref : la notification est consignée avec son niveau et son type",
      "garde-fou déclenché sur la branche" in txt and "[notification warn/garde-fou]" in txt)

r = run("request", "une demande sans ticket")
check("sans ticket : rien n'est écrit dans un think, et aucun avertissement",
      len(pm_think.load(think).get("note", {}).get("rows", [])) == 2
      and "think non mis à jour" not in (r.stdout + r.stderr))

# ── 3. un échec du pont est journalisé, jamais bloquant ──────────────────────
src = (HERE / "pm-session-status.py").read_text(encoding="utf-8")
check("l'échec du pont part aussi au journal structuré (catégorie worklog)",
      'pont session → think en échec' in src and '_jlog("worklog"' in src)
check("l'enregistrement de la demande reste protégé par un except", "except Exception as e:" in src)

wl = json.loads(next(worklogs.glob("*.json")).read_text(encoding="utf-8"))
# le registre de session garde TOUT (même un doublon : c'est une trace de ce qui a été dit) ;
# c'est le think qui dédoublonne. Deux registres, deux règles — et c'est voulu.
check("le worklog garde les 3 demandes (dont le doublon) et la notification",
      len(wl.get("requests") or []) == 3 and len(wl.get("notifications") or []) == 1,
      f"{len(wl.get('requests') or [])} demande(s)")

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — pont session → .think.md (RM3076)")
