#!/usr/bin/env python3
"""Tests de pm-project-new — création directe du modèle co-localisé (RM2228).

Lancer : python3 scripts/test_pm_project_new_coloc.py

Reproduit le bug RM2228 : pm-project-new créait le volet PM en dossier réel sous
`projects/` (gitignoré → non versionné) + symlink `.mmi-pm` dans le workspace,
au lieu du modèle canonique co-localisé (RM1942/RM1949) : `.mmi-pm/` réel dans le
workspace, publié dans un repo `<dossier>-core`, et `projects/` = symlink d'index.

Tests sans réseau : `api_call` est monkey-patchée, tout se joue en `--dry-run`
(le plan annoncé doit décrire le modèle co-localisé) + garde-fou racine git.
"""
import importlib.util
import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# pm-project-new.py : tiret dans le nom → chargement via importlib.
_spec = importlib.util.spec_from_file_location("pm_project_new", str(_HERE / "pm-project-new.py"))
ppn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ppn)

_spec2 = importlib.util.spec_from_file_location("pm_paths", str(_HERE / "pm_paths.py"))
pm_paths = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(pm_paths)
PMConfig = pm_paths.PMConfig


# ── Helpers ─────────────────────────────────────────────────────────────────
def make_cfg(root: Path) -> "PMConfig":
    """PMConfig minimale pointant projects_root sur un tmpdir, sans .env ni fichiers
    de conf réels (même approche que test_pm_paths_iter_projects.make_cfg)."""
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


def fake_api_call(method, url, key, payload=None):
    """Redmine factice : tout projet existe (id=42), tout POST réussit."""
    if method == "GET":
        return 200, {"project": {"id": 42, "identifier": "fake", "parent": None}}
    return 201, {"project": {"id": 43}}


def run_main(argv, env_root: Path):
    """Exécute ppn.main() avec argv + cfg forcée ; capture stdout ; renvoie (stdout, exit)."""
    old_argv, old_load, old_api = sys.argv, ppn.PMConfig.load, ppn.api_call
    sys.argv = ["pm-project-new.py"] + argv
    ppn.PMConfig.load = staticmethod(lambda: make_cfg(env_root))
    ppn.api_call = fake_api_call
    # Secrets factices : api_call est mockée, rien ne sort sur le réseau.
    os.environ.setdefault("REDMINE_URL", "http://redmine.invalid")
    os.environ.setdefault("REDMINE_USER_MAIN_API_KEY", "test-key")
    out, code = io.StringIO(), None
    try:
        with redirect_stdout(out):
            ppn.main()
    except SystemExit as e:
        code = e.code
    finally:
        sys.argv = old_argv
        ppn.PMConfig.load = old_load
        ppn.api_call = old_api
    return out.getvalue(), code


def setup_env(tmp: Path):
    """Arbo minimale : client PM + workspace de code vide."""
    (tmp / "clients" / "testclient" / "projects").mkdir(parents=True)
    ws = tmp / "ws" / "monprojet"
    ws.mkdir(parents=True)
    return ws


BASE_ARGS = ["--client", "testclient", "--slug", "monprojet-pm", "--name", "Mon Projet",
             "--existing-redmine-id", "monprojet-pm", "--no-bootstrap"]


# ── Tests ───────────────────────────────────────────────────────────────────
def test_dry_run_announces_coloc_model():
    """RM2228 (repro) : le plan --dry-run doit décrire le modèle CO-LOCALISÉ,
    pas l'ancien modèle (dossier réel sous projects/ + symlink dans le ws)."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        ws = setup_env(tmp)
        out, code = run_main(BASE_ARGS + ["--workspace", str(ws), "--dry-run"], tmp)
        assert code in (None, 0), f"dry-run ne doit pas échouer : exit={code}\n{out}"
        # Modèle cible : .mmi-pm RÉEL dans le workspace…
        assert f"{ws}/.mmi-pm (réel" in out or f"{ws}/.mmi-pm (dossier réel" in out, \
            f"le plan doit matérialiser .mmi-pm dans le workspace :\n{out}"
        # …publié dans un repo -core…
        assert "monprojet-core" in out, f"le plan doit créer le repo <dossier>-core :\n{out}"
        # …et projects/ n'est qu'un SYMLINK d'index.
        assert "symlink d'index" in out, f"le plan doit poser le symlink d'index projects/ :\n{out}"
        # Anti-régression : l'ancien plan ne doit plus apparaître.
        assert "↔" not in out, f"ancien modèle (symlinks bidirectionnels ↔) encore annoncé :\n{out}"


def test_abort_if_workspace_root_is_git_repo():
    """Garde-fou : racine du workspace déjà un repo git (clone de code pré-norme)
    → abort explicite AVANT toute création (→ pm-env-migrate d'abord)."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        ws = setup_env(tmp)
        (ws / ".git").mkdir()
        out, code = run_main(BASE_ARGS + ["--workspace", str(ws), "--dry-run"], tmp)
        assert code not in (None, 0), f"doit refuser un ws dont la racine est un repo git\n{out}"
        assert "pm-env-migrate" in str(code), \
            f"le message d'erreur doit orienter vers pm-env-migrate : {code!r}"


def test_abort_if_mmipm_already_exists():
    """Garde-fou : .mmi-pm déjà présent dans le workspace → abort (pas d'écrasement)."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        ws = setup_env(tmp)
        (ws / ".mmi-pm").mkdir()
        out, code = run_main(BASE_ARGS + ["--workspace", str(ws), "--dry-run"], tmp)
        assert code not in (None, 0), f"doit refuser un .mmi-pm préexistant\n{out}"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted({k: v for k, v in globals().items() if k.startswith("test_")}.items()):
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {name} : {e}")
    sys.exit(1 if failed else 0)
