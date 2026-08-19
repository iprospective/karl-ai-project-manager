#!/usr/bin/env python3
"""Tests RM2531 — pm-project-config (édition ciblée de meta.yml projet/client).

Unitaire (sans réseau, sans arbre PM) : fonctions pures _meta_set / _yaml_scalar,
validateurs, _collect_updates. Lancer : python3 scripts/test_pm_project_config.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_project_config", HERE / "pm-project-config.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["pm_project_config"] = mod
spec.loader.exec_module(mod)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


META = """\
# commentaire à préserver
schema_version: 1.7.1
slug: pm-ai-agents
name: Ancien nom
status: active
redmine:
  instance: null
  project_id: pm-ai-agents
gitlab:
  repo: iprospective/ai-project-management
  group: iprospective
  default_branch: main
"""

# — remplacement d'un scalaire racine —
out = mod._meta_set(META, [("name", "Nouveau nom")])
check("name racine remplacé", "name: Nouveau nom" in out and "Ancien nom" not in out)
check("commentaire préservé", out.startswith("# commentaire à préserver"))
check("autres clés intactes", "schema_version: 1.7.1" in out and "slug: pm-ai-agents" in out)

# — remplacement d'une sous-clé de bloc —
out = mod._meta_set(META, [("gitlab.repo", "iprospective/x-core")])
check("gitlab.repo remplacé", "  repo: iprospective/x-core" in out)
check("gitlab.group intact", "  group: iprospective" in out)
check("redmine.project_id intact", "  project_id: pm-ai-agents" in out)

# — remplacement de default_branch (sous-clé existante) —
out = mod._meta_set(META, [("gitlab.default_branch", "dev")])
check("default_branch remplacé", "  default_branch: dev" in out and "default_branch: main" not in out)

# — insertion d'une sous-clé absente dans un bloc existant —
no_branch = META.replace("  default_branch: main\n", "")
out = mod._meta_set(no_branch, [("gitlab.default_branch", "main")])
check("sous-clé absente insérée dans le bloc", "  default_branch: main" in out)
check("insertion sous le bon bloc", out.index("default_branch: main") > out.index("gitlab:"))

# — bloc entièrement absent → créé —
no_gitlab = "name: X\nslug: y\n"
out = mod._meta_set(no_gitlab, [("gitlab.repo", "a/b")])
check("bloc absent créé", "gitlab:\n  repo: a/b" in out)

# — updates multiples ordonnés en un passage —
out = mod._meta_set(META, [("name", "N2"), ("redmine.project_id", "np"), ("gitlab.default_branch", "dev")])
check("multi-update name", "name: N2" in out)
check("multi-update project_id", "  project_id: np" in out)
check("multi-update branch", "  default_branch: dev" in out)

# — quoting YAML —
import yaml  # noqa: E402  (round-trip de validité)
check("scalaire simple non quoté", mod._yaml_scalar("main") == "main")
check("scalaire vide quoté", mod._yaml_scalar("") == "''")
check("scalaire avec ': ' quoté", mod._yaml_scalar("a: b") == "'a: b'")
check("tiret initial quoté", mod._yaml_scalar("-x") == "'-x'")
# apostrophe en milieu = scalaire plain VALIDE (pas besoin de quoter) ; on vérifie
# que ça se relit à l'identique quel que soit le rendu choisi.
check("apostrophe round-trip", yaml.safe_load("k: " + mod._yaml_scalar("l'x")) == {"k": "l'x"})
name_special = "PM — Agents (dogfooding) & outils"
out = mod._meta_set(META, [("name", name_special)])
check("name spécial reste 1 ligne valide", ("name: " + name_special) in out or ("name: '" in out))

# — validateurs : rejets (signature (field, value)) —
def rejette(field, val):
    try:
        mod._VALIDATORS[field](field, val)
        return False
    except SystemExit:
        return True

check("name multi-ligne rejeté", rejette("name", "a\nb"))
check("project_id espace rejeté", rejette("redmine.project_id", "a b"))
check("default_project_id espace rejeté", rejette("redmine.default_project_id", "a b"))
check("repo espace rejeté", rejette("gitlab.repo", "a b"))
check("branch newline rejeté", rejette("gitlab.default_branch", "x\n"))
check("project_id valide accepté", mod._VALIDATORS["redmine.project_id"]("redmine.project_id", "pm-ai-agents") == "pm-ai-agents")
check("repo valide accepté", mod._VALIDATORS["gitlab.repo"]("gitlab.repo", "iprospective/ai-project-management") == "iprospective/ai-project-management")


# — champs par périmètre : le client n'expose PAS gitlab —
check("PROJECT_FIELDS a gitlab", any(k.startswith("gitlab.") for k, _ in mod.PROJECT_FIELDS))
check("CLIENT_FIELDS sans gitlab", not any(k.startswith("gitlab.") for k, _ in mod.CLIENT_FIELDS))
check("CLIENT_FIELDS redmine = default_project_id",
      ("redmine.default_project_id", "redmine_project_id") in mod.CLIENT_FIELDS)


# — _collect_updates(args, fields) : mapping attr → clé pointée —
class A:  # faux args
    name = "N"
    redmine_project_id = "np"
    gitlab_repo = None
    default_branch = None


up = mod._collect_updates(A, mod.CLIENT_FIELDS)
check("collect client : name+default_project_id", up == [("name", "N"), ("redmine.default_project_id", "np")])
up = mod._collect_updates(A, mod.PROJECT_FIELDS)
check("collect projet : name+project_id", up == [("name", "N"), ("redmine.project_id", "np")])

print()
if fails:
    print(f"{len(fails)} échec(s) : {fails}")
    sys.exit(1)
print("tous les tests passent")
