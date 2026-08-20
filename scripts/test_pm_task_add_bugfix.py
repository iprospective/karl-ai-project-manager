#!/usr/bin/env python3
"""Tests RM2752 — un ticket `--type bugfix` doit naître VALIDE.

`validate-task.py` impose `bug.reproducibility` + `bug.reproduce_steps` pour
type=bugfix. `pm-task-add` ne posait pas ce bloc et n'offrait aucun flag pour le
renseigner : TOUT bugfix créé par l'outil canonique sortait invalide, avec pour
seul remède un « pm-doctor RM<id> » qui n'accepte pas d'argument. Le ticket qui
décrivait ce défaut l'a reproduit en se créant.

Offline : aucun appel Redmine, aucune écriture hors dossier temporaire.
Lancer : python3 scripts/test_pm_task_add_bugfix.py
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_spec = importlib.util.spec_from_file_location("pm_task_add", str(HERE / "pm-task-add.py"))
pta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pta)

_vspec = importlib.util.spec_from_file_location("validate_task", str(HERE / "validate-task.py"))
vt = importlib.util.module_from_spec(_vspec)
_vspec.loader.exec_module(vt)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def add(*extra):
    """`pm-task-add` sur un projet bidon : on ne teste QUE les gardes d'argv,
    qui s'appliquent avant toute résolution de projet ou appel Redmine."""
    return subprocess.run(
        [sys.executable, str(HERE / "pm-task-add.py"), "--title", "t",
         "--project", "ent/proj", "--dry-run"] + list(extra),
        capture_output=True, text=True)


# — 1. les deux listes de valeurs ne doivent JAMAIS diverger ——————————————
check("les reproductibilités acceptées sont celles de validate-task",
      set(pta.VALID_REPRODUCIBILITIES) == set(vt.VALID_REPRODUCIBILITIES))

# — 2. le bloc est posé, et posé au bon endroit ——————————————————————————
fm = {"title": "t", "type": "bugfix", "bootstrap_template": None, "status": "nouveau"}
out = pta._with_bug(fm, "often", "1. lancer\n2. observer")
check("le bloc bug suit immédiatement `type` (MD lisible comme à la main)",
      list(out)[:3] == ["title", "type", "bug"])
check("l'ordre des autres clés est conservé",
      [k for k in out if k != "bug"] == list(fm))
check("reproducibility et étapes sont portées telles quelles",
      out["bug"]["reproducibility"] == "often"
      and out["bug"]["reproduce_steps"].startswith("1. lancer"))
check("les étapes se terminent par un saut de ligne (bloc YAML littéral propre)",
      out["bug"]["reproduce_steps"].endswith("\n"))

# — 3. le frontmatter produit passe validate-task ————————————————————————
# On ne simule pas la validation : on appelle le vrai validateur sur un vrai MD.
import yaml  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    # Frontmatter minimal ACCEPTÉ par validate-task, hors le bloc `bug` : c'est
    # lui, et lui seul, que ce test met en cause.
    base = {"schema_version": "1.11.0", "redmine_id": 1, "title": "t", "type": "bugfix",
            "status": "nouveau", "close_reason": None, "priority": "normal",
            "completion_pct": 0, "creator": "iprospective",
            "team": [{"username": "iprospective", "email": "m@x.fr", "role": "owner"}],
            "estimate": {"difficulty": "medium", "confidence": 0.5},
            "created": "2026-08-20", "updated": "2026-08-20T00:00",
            "status_history": [{"status": "nouveau", "at": "2026-08-20T00:00",
                                "by": "iprospective"}]}
    md = Path(tmp, "RM1_t.md")

    # sans le bloc : le validateur DOIT refuser (sinon ce test ne prouve rien)
    md.write_text("---\n" + yaml.safe_dump(base, allow_unicode=True, sort_keys=False)
                  + "---\n\n## Contexte\n\nx\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(HERE / "validate-task.py"), str(md)],
                       capture_output=True, text=True)
    check("sans bloc bug, validate-task refuse (le test mord)", r.returncode != 0)

    # avec le bloc posé par pm-task-add : accepté
    withbug = pta._with_bug(base, "always", "1. lancer la commande\n2. observer l'erreur")
    md.write_text("---\n" + yaml.safe_dump(withbug, allow_unicode=True, sort_keys=False)
                  + "---\n\n## Contexte\n\nx\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(HERE / "validate-task.py"), str(md)],
                       capture_output=True, text=True)
    check("avec le bloc posé par pm-task-add, validate-task accepte",
          r.returncode == 0)

# — 4. les gardes d'argv ————————————————————————————————————————————————
r = add("--type", "bugfix")
check("un bugfix sans étapes est REFUSÉ, pas créé invalide", r.returncode != 0)
check("… et le refus nomme les deux flags qui débloquent",
      "--bug-steps" in r.stderr and "--bug-reproducibility" in r.stderr)

r = add("--type", "feature", "--bug-steps", "1. x")
check("--bug-* sur un type non-bugfix est refusé (erreur de frappe, pas un silence)",
      r.returncode != 0 and "bugfix" in r.stderr)

r = add("--type", "bugfix", "--bug-steps", "1. x", "--bug-reproducibility", "jamais")
check("une reproductibilité hors énumération est refusée par argparse",
      r.returncode != 0)

# — 5. le remède affiché doit être une commande QUI EXISTE ————————————————
src = (HERE / "pm-task-add.py").read_text(encoding="utf-8")
check("le message de warning ne renvoie plus vers `pm-doctor RM<id>`",
      'validate → pm-doctor' not in src)
check("… il renvoie vers validate-task.py, qui accepte un chemin",
      "validate-task.py {md_path}" in src)
r = subprocess.run([sys.executable, str(HERE / "pm-doctor.py"), "RM1"],
                   capture_output=True, text=True)
check("preuve du défaut d'origine : pm-doctor refuse bien un argument RM",
      r.returncode != 0 and "unrecognized arguments" in (r.stderr + r.stdout))

if fails:
    print("\nÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("\nOK — un bugfix créé par pm-task-add naît valide (RM2752)")
