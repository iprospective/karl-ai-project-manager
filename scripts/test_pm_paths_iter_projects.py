#!/usr/bin/env python3
"""Tests de PMConfig.iter_projects — bascule du résolveur (RM1949).

Lancer : python3 scripts/test_pm_paths_iter_projects.py

Couvre le patch « suivre les symlinks-vers-dossier + dédup par cible résolue ».
Objectif central : **non-régression** — tant que tous les projets sont des
dossiers réels (état pré-bascule), iter_projects yield exactement la même chose
qu'avant. Puis : un projet symlinké (basculé) est bien découvert, et la dédup
empêche le double-comptage.
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_paths", str(_HERE / "pm_paths.py"))
pm_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm_paths)
PMConfig = pm_paths.PMConfig


# ── Helpers ─────────────────────────────────────────────────────────────────
def make_cfg(root: Path) -> "PMConfig":
    """Construit une PMConfig pointant `projects_root` sur `root`, sans toucher
    aux fichiers de conf réels (on instancie l'objet et on force les attributs)."""
    cfg = PMConfig.__new__(PMConfig)
    cfg.pm_dir = root  # non utilisé par iter_projects
    cfg.projects_root = root.resolve()
    cfg._patterns = {
        "entities_dir": "{projects_root}/clients",
        "entity": "{entities_dir}/{entity}",
        "entity_projects_dir": "{entity}/projects",
    }
    return cfg


def mk_project(root: Path, entity: str, project: str) -> Path:
    """Crée un dossier projet réel `clients/<entity>/projects/<project>/` avec un
    sous-dossier `tasks/` (pour ressembler à un vrai projet PM)."""
    p = root / "clients" / entity / "projects" / project
    (p / "tasks").mkdir(parents=True, exist_ok=True)
    return p


# ── Cas ─────────────────────────────────────────────────────────────────────
def test_non_regression_dossiers_reels():
    """Tout en dossiers réels → liste identique à l'ancien comportement
    (l'ancien : `p.is_dir() and not p.is_symlink()`)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mk_project(root, "calicote", "dolibarr")
        mk_project(root, "calicote", "prestashop")
        mk_project(root, "calicote", "infra")
        mk_project(root, "pisceen", "dolibarr")
        cfg = make_cfg(root)
        got = sorted((e, p) for e, p, _ in cfg.iter_projects())
        want = [
            ("calicote", "dolibarr"),
            ("calicote", "infra"),
            ("calicote", "prestashop"),
            ("pisceen", "dolibarr"),
        ]
        assert got == want, got


def test_filtre_entity():
    """Le filtre `entity=` ne yield que les projets de cette entité."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mk_project(root, "calicote", "dolibarr")
        mk_project(root, "pisceen", "dolibarr")
        cfg = make_cfg(root)
        got = sorted(p for _, p, _ in cfg.iter_projects(entity="calicote"))
        assert got == ["dolibarr"], got


def test_symlink_projet_bascule_suivi():
    """Un projet basculé = symlink `clients/<E>/projects/<P>` → un `.mmi-pm`
    co-localisé hors arbo. Il DOIT être découvert (nouvelle capacité)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # cible co-localisée hors de clients/ (simule .../workspaces/calicote/dpsync/.mmi-pm)
        colocated = root / "workspace_calicote_dpsync" / ".mmi-pm"
        (colocated / "tasks").mkdir(parents=True)
        # un projet réel + un projet symlinké, sous la même entité
        mk_project(root, "calicote", "dolibarr")
        link = root / "clients" / "calicote" / "projects" / "prestasync"
        link.symlink_to(colocated)
        cfg = make_cfg(root)
        got = sorted((e, p) for e, p, _ in cfg.iter_projects())
        assert got == [("calicote", "dolibarr"), ("calicote", "prestasync")], got
        # le path yieldé pour le symlink résout bien vers la cible co-localisée
        ypaths = {p: path for _, p, path in cfg.iter_projects()}
        assert ypaths["prestasync"].resolve() == colocated.resolve()


def test_dedup_par_cible_resolue():
    """Deux entrées pointant la même cible résolue ne sont comptées qu'une fois
    (anti double-comptage : ici un dossier réel + un symlink vers ce dossier)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        real = mk_project(root, "calicote", "dolibarr")
        # alias symlink dans la même arbo projets, pointant le dossier réel
        alias = root / "clients" / "calicote" / "projects" / "dolibarr-alias"
        alias.symlink_to(real)
        cfg = make_cfg(root)
        names = sorted(p for _, p, _ in cfg.iter_projects())
        # `dolibarr` (réel) gagne car trié avant `dolibarr-alias` ; l'alias est dédupé
        assert names == ["dolibarr"], names


def test_fichier_non_yieldé():
    """Un fichier (non-dossier) dans projects/ est ignoré."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mk_project(root, "calicote", "dolibarr")
        (root / "clients" / "calicote" / "projects" / "README.md").write_text("x")
        cfg = make_cfg(root)
        got = sorted(p for _, p, _ in cfg.iter_projects())
        assert got == ["dolibarr"], got


def test_symlink_casse_ignoré():
    """Un symlink cassé (cible inexistante) ne casse pas l'itération."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mk_project(root, "calicote", "dolibarr")
        broken = root / "clients" / "calicote" / "projects" / "ghost"
        broken.symlink_to(root / "nexiste-pas")
        cfg = make_cfg(root)
        got = sorted(p for _, p, _ in cfg.iter_projects())
        assert got == ["dolibarr"], got


CASES = [
    ("non_regression_dossiers_reels", test_non_regression_dossiers_reels),
    ("filtre_entity", test_filtre_entity),
    ("symlink_projet_bascule_suivi", test_symlink_projet_bascule_suivi),
    ("dedup_par_cible_resolue", test_dedup_par_cible_resolue),
    ("fichier_non_yieldé", test_fichier_non_yieldé),
    ("symlink_casse_ignoré", test_symlink_casse_ignoré),
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
