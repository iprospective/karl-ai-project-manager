#!/usr/bin/env python3
"""Tests RM3293 — déplacer un ticket vers un autre projet, exposé au cockpit.

Ce qui est protégé :

  1. la commande est **déclarée** (nom, script, confirmation) : le cockpit n'a aucune
     logique de déplacement à lui, il appelle `pm-task-move.py` — l'outil qui fait déjà
     fiche, fichiers frères, projet Redmine et journal ;
  2. le projet cible est un **choix dans une liste**, calculée à chaque appel : un slug nu
     est refusé par l'outil (tripwire #14), et la liste des projets change sans prévenir ;
  3. remplir ces choix ne **mute jamais** le registre d'origine — une commande servie une
     fois avec les projets d'alors les garderait pour toutes les suivantes ;
  4. `--force` existe mais reste un **bool non coché** : un ticket qui porte une branche de
     code ne se déplace pas par inadvertance ;
  5. sans données PM joignables, la liste est **vide plutôt qu'en erreur** : le cockpit doit
     rendre son formulaire même sur une instance mal configurée.

Lancer : python3 scripts/test_karl_agent_task_move.py
"""
import importlib.util
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core            # noqa: E402
hermetic_core()
tmp = tempfile.mkdtemp(prefix="karl-move-")
os.environ["KARL_AGENT_PROJECTS_BASE"] = str(pathlib.Path(tmp) / "clients")
os.environ["KARL_JOURNAL_DIR"] = tmp
os.environ["KARL_JOURNAL_STDERR"] = "0"
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

OK = []


def check(label, cond, detail=""):
    OK.append(bool(cond))
    print(("  ✓ " if cond else "  ✗ ") + label + (("" if cond else " — " + str(detail))))


def cmd(name, cmds=None):
    return next((c for c in (cmds if cmds is not None else ka._pm_commands())
                 if c.get("name") == name), None)


def arg(c, name):
    return next((a for a in (c.get("args") or []) if a.get("name") == name), None)


# ── 1. la commande est déclarée ─────────────────────────────────────────────
c = cmd("task-move")
check("la commande existe dans le registre", c is not None)
check("elle appelle l'outil, sans logique dupliquée", c and c.get("script") == "pm-task-move.py",
      c and c.get("script"))
check("elle est classée avec les gestes de ticket", c and c.get("category") == "ticket")
check("elle demande confirmation : l'opération écrit dans Redmine",
      c and c.get("confirm") is True and c.get("mutate") is True)

# ── 2. ses arguments ────────────────────────────────────────────────────────
rm, to, force = arg(c, "rm_id"), arg(c, "to"), arg(c, "force")
check("le ticket est un rm_id positionnel requis",
      rm and rm.get("type") == "rm_id" and rm.get("required") and rm.get("positional"))
check("le projet cible part en --to, requis, choisi dans une liste",
      to and to.get("flag") == "--to" and to.get("required") and to.get("type") == "enum")
check("la liste est dynamique, pas figée dans le registre",
      to and to.get("choices_from") == "projects")
check("--force est un bool, donc décoché par défaut",
      force and force.get("type") == "bool" and force.get("flag") == "--force")

# ── 3. les choix sont calculés, et n'abîment pas le registre ────────────────
REFS = ["clienta/site", "clientb/infra"]
_orig = ka._pm_project_refs
ka._pm_project_refs = lambda: REFS
try:
    servie = cmd("task-move")
    check("les choix sont remplis à l'appel", arg(servie, "to").get("choices") == REFS,
          arg(servie, "to").get("choices"))
    check("le registre d'origine reste vierge",
          arg(cmd("task-move", ka._PM_COMMANDS_DEFAULT), "to").get("choices") == [])
    ka._pm_project_refs = lambda: ["clientc/erp"]
    check("un projet créé entre deux appels apparaît",
          arg(cmd("task-move"), "to").get("choices") == ["clientc/erp"])
    ka._pm_project_refs = lambda: REFS
    autre = cmd("task-status")
    check("une commande sans choix dynamique passe telle quelle",
          autre is not None and all(a.get("choices_from") is None for a in autre["args"]))
finally:
    ka._pm_project_refs = _orig

# ── 4. sans données joignables : vide, pas d'erreur ─────────────────────────
try:
    saved = os.environ.get("PM_CORE_DIR")
    os.environ["PM_CORE_DIR"] = str(pathlib.Path(tmp) / "nexistepas")
    refs = ka._pm_project_refs()
    check("liste vide plutôt qu'une exception", isinstance(refs, list))
finally:
    if saved is None:
        os.environ.pop("PM_CORE_DIR", None)
    else:
        os.environ["PM_CORE_DIR"] = saved

# ── 5. la validation d'un argument refuse ce qui n'est pas un ticket ────────
try:
    ka._pm_validate_arg({"name": "rm_id", "type": "rm_id"}, "dolibarr/dolibarr-dev")
    check("un projet passé en rm_id est refusé", False, "aucune erreur levée")
except Exception as e:
    check("un projet passé en rm_id est refusé", "rm_id" in str(e) or "RM-id" in str(e), e)

print(f"\n{sum(OK)}/{len(OK)} ok")
sys.exit(0 if all(OK) else 1)
