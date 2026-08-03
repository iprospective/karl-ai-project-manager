#!/usr/bin/env python3
"""Tests offline de pm_forge — abstraction de forge (T2/RM2498).

Lancer : python3 scripts/test_pm_forge.py
Couvre : parse_remote (toutes formes), détection de forge, capabilities,
compare_url (GitLab/Gogs), fabrique get_forge + override PM_FORGE. Aucun réseau.
"""
import importlib.util
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_forge", str(_HERE / "pm_forge.py"))
pm_forge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm_forge)


def test_parse_remote_forms():
    cases = [
        ("gitlab:iprospective/ai/foo.git", ("gitlab", "iprospective/ai/foo")),
        ("git@gitlab.iprospective.fr:grp/repo.git", ("gitlab.iprospective.fr", "grp/repo")),
        ("https://gitlab.iprospective.fr/grp/sub/repo", ("gitlab.iprospective.fr", "grp/sub/repo")),
        ("ssh://gogs@localhost:28022/Materiaux-Naturels/matnat_old.git",
         ("localhost", "Materiaux-Naturels/matnat_old")),
        ("gogs:Materiaux-Naturels/matnat_old.git", ("gogs", "Materiaux-Naturels/matnat_old")),
    ]
    for url, want in cases:
        got = pm_forge.parse_remote(url)
        assert got == want, (url, got)


def test_forge_name():
    assert pm_forge.forge_name("gitlab") == "gitlab"
    assert pm_forge.forge_name("gitlab.iprospective.fr") == "gitlab"
    assert pm_forge.forge_name("gogs.materiaux-naturels.fr") == "gogs"
    assert pm_forge.forge_name("github.com") == "github"
    # cas connu à trancher explicitement : Gogs tunnelé en localhost → non détectable
    assert pm_forge.forge_name("localhost") is None
    assert pm_forge.forge_name("") is None


def test_capabilities():
    gl = pm_forge.GitlabForge("grp/repo").capabilities
    assert gl.pull_request_api is True and gl.async_merge_status is True
    go = pm_forge.GogsForge("o/r").capabilities
    assert go.pull_request_api is False and go.access_level_model == "gitea"


def test_compare_url_gogs():
    os.environ["GOGS_URL"] = "https://gogs.materiaux-naturels.fr"
    f = pm_forge.GogsForge("Materiaux-Naturels/matnat_old")
    assert f.compare_url("5564-x", "dev") == \
        "https://gogs.materiaux-naturels.fr/Materiaux-Naturels/matnat_old/compare/dev...5564-x"


def test_gogs_create_pr_is_compare_link():
    os.environ["GOGS_URL"] = "https://gogs.materiaux-naturels.fr"
    f = pm_forge.GogsForge("o/r")
    pr = f.create_pr(f.resolve_project("tok"), "b", "dev", "t", "d", "tok")
    assert pr.is_compare_link is True and pr.iid is None
    assert pr.web_url.endswith("/o/r/compare/dev...b"), pr.web_url


def test_compare_url_gitlab():
    os.environ["GITLAB_URL"] = "https://gitlab.iprospective.fr"
    f = pm_forge.GitlabForge("grp/repo")
    assert f.compare_url("b", "dev") == \
        "https://gitlab.iprospective.fr/grp/repo/-/compare/dev...b"


def test_get_forge_detects_and_overrides():
    # détection auto depuis l'URL (alias gitlab:)
    f = pm_forge.get_forge(url="gitlab:grp/repo.git")
    assert isinstance(f, pm_forge.GitlabForge) and f.repo_path == "grp/repo"
    # localhost non détectable → PM_FORGE force le choix
    os.environ["PM_FORGE"] = "gogs"
    try:
        f = pm_forge.get_forge(url="ssh://gogs@localhost:28022/o/r.git")
        assert isinstance(f, pm_forge.GogsForge) and f.repo_path == "o/r"
    finally:
        del os.environ["PM_FORGE"]
    # non reconnu sans override → erreur explicite
    try:
        pm_forge.get_forge(url="ssh://gogs@localhost:28022/o/r.git")
        raise AssertionError("attendu ForgeError")
    except pm_forge.ForgeError:
        pass


def test_get_forge_explicit_arg():
    f = pm_forge.get_forge(url="ssh://gogs@localhost:28022/o/r.git", forge="gogs")
    assert isinstance(f, pm_forge.GogsForge) and f.repo_path == "o/r"


def test_get_forge_git_config():
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        run = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True)
        run("init", "-q")
        run("remote", "add", "origin", "ssh://gogs@localhost:28022/Materiaux-Naturels/matnat_old.git")
        # sans signal : host 'localhost' non détectable → erreur
        try:
            pm_forge.get_forge(repo=d)
            raise AssertionError("attendu ForgeError (localhost non détectable)")
        except pm_forge.ForgeError:
            pass
        # avec git config pm.forge gogs → GogsForge
        run("config", "pm.forge", "gogs")
        f = pm_forge.get_forge(repo=d)
        assert isinstance(f, pm_forge.GogsForge), type(f)
        assert f.repo_path == "Materiaux-Naturels/matnat_old", f.repo_path


CASES = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    fails = 0
    for fn in CASES:
        try:
            fn(); print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            fails += 1; print(f"  ✗ {fn.__name__} — {e}")
        except Exception as e:  # noqa: BLE001
            fails += 1; print(f"  ✗ {fn.__name__} — ERREUR {type(e).__name__}: {e}")
    print(f"\n{len(CASES) - fails}/{len(CASES)} ok")
    sys.exit(1 if fails else 0)
