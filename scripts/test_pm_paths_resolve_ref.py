#!/usr/bin/env python3
"""Tests de PMConfig.resolve_project_ref — résolution projet→Redmine précise (RM2430).

Lancer : python3 scripts/test_pm_paths_resolve_ref.py

Objectif : plus de match de slug silencieux. Un slug partagé par plusieurs
clients (ex. `infra`) DOIT lever une erreur listant les candidats ; la
désambiguïsation passe par `client/slug` ou par le `redmine.project_id` unique.
`require_redmine=True` refuse un projet sans `redmine.project_id` en conf.
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_paths", str(_HERE / "pm_paths.py"))
pm_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm_paths)
PMConfig = pm_paths.PMConfig


def make_cfg(root: Path) -> "PMConfig":
    cfg = PMConfig.__new__(PMConfig)
    cfg.pm_dir = root
    cfg.projects_root = root.resolve()
    cfg._patterns = {
        "entities_dir": "{projects_root}/clients",
        "entity": "{entities_dir}/{entity}",
        "entity_projects_dir": "{entity}/projects",
        "project": "{entity_projects_dir}/{project}",
    }
    return cfg


def mk_project(root: Path, entity: str, project: str, redmine_id=None) -> Path:
    p = root / "clients" / entity / "projects" / project
    (p / "tasks").mkdir(parents=True, exist_ok=True)
    meta = f"client: {entity}\nslug: {project}\n"
    if redmine_id is not None:
        meta += f"redmine:\n  project_id: {redmine_id}\n"
    (p / "meta.yml").write_text(meta, encoding="utf-8")
    return p


def _expect_valueerror(fn, needle=None):
    try:
        fn()
    except ValueError as e:
        if needle and needle not in str(e):
            raise AssertionError(f"message inattendu : {e}")
        return
    raise AssertionError("ValueError attendue, non levée")


# ── Cas ─────────────────────────────────────────────────────────────────────
def test_slug_ambigu_leve():
    """Slug partagé par 2 clients → ValueError listant les candidats (pas de choix silencieux)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mk_project(root, "abatik", "infra", "abatik-infra")
        mk_project(root, "matnat", "infra", "matnat-infra")
        cfg = make_cfg(root)
        _expect_valueerror(lambda: cfg.resolve_project_ref("infra"), needle="ambiguë")
        # les deux candidats sont cités
        try:
            cfg.resolve_project_ref("infra")
        except ValueError as e:
            assert "abatik/infra" in str(e) and "matnat/infra" in str(e), str(e)


def test_client_slug_desambigue():
    """`client/slug` cible précisément le bon projet malgré la collision."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mk_project(root, "abatik", "infra", "abatik-infra")
        mk_project(root, "matnat", "infra", "matnat-infra")
        cfg = make_cfg(root)
        ent, proj, _ = cfg.resolve_project_ref("matnat/infra")
        assert (ent, proj) == ("matnat", "infra"), (ent, proj)


def test_redmine_project_id_desambigue():
    """Le `redmine.project_id` unique résout sans ambiguïté."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mk_project(root, "abatik", "infra", "abatik-infra")
        mk_project(root, "matnat", "infra", "matnat-infra")
        cfg = make_cfg(root)
        ent, proj, _ = cfg.resolve_project_ref("matnat-infra")
        assert (ent, proj) == ("matnat", "infra"), (ent, proj)


def test_slug_non_ambigu_ok():
    """Un slug présent chez un seul client reste résoluble tel quel (rétro-compat)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mk_project(root, "iprospective", "pm-ai-agents", "pm-ai-agents")
        cfg = make_cfg(root)
        ent, proj, _ = cfg.resolve_project_ref("pm-ai-agents")
        assert (ent, proj) == ("iprospective", "pm-ai-agents"), (ent, proj)


def test_introuvable_leve():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mk_project(root, "matnat", "infra", "matnat-infra")
        cfg = make_cfg(root)
        _expect_valueerror(lambda: cfg.resolve_project_ref("nexiste-pas"), needle="introuvable")


def test_require_redmine_absent_leve():
    """require_redmine=True + projet sans redmine.project_id → bloque."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mk_project(root, "matnat", "sansredmine", redmine_id=None)
        cfg = make_cfg(root)
        _expect_valueerror(
            lambda: cfg.resolve_project_ref("matnat/sansredmine", require_redmine=True),
            needle="redmine.project_id",
        )


def test_require_redmine_present_ok():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mk_project(root, "matnat", "infra", "matnat-infra")
        cfg = make_cfg(root)
        ent, proj, _ = cfg.resolve_project_ref("matnat/infra", require_redmine=True)
        assert (ent, proj) == ("matnat", "infra"), (ent, proj)


CASES = [
    ("slug_ambigu_leve", test_slug_ambigu_leve),
    ("client_slug_desambigue", test_client_slug_desambigue),
    ("redmine_project_id_desambigue", test_redmine_project_id_desambigue),
    ("slug_non_ambigu_ok", test_slug_non_ambigu_ok),
    ("introuvable_leve", test_introuvable_leve),
    ("require_redmine_absent_leve", test_require_redmine_absent_leve),
    ("require_redmine_present_ok", test_require_redmine_present_ok),
]

if __name__ == "__main__":
    fails = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            fails += 1
            print(f"  ✗ {name} — {e}")
        except Exception as e:  # noqa: BLE001
            fails += 1
            print(f"  ✗ {name} — ERREUR {type(e).__name__}: {e}")
    print(f"\n{len(CASES) - fails}/{len(CASES)} ok")
    sys.exit(1 if fails else 0)
