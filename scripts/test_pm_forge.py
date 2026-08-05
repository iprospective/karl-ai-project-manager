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


def test_github_detection_and_caps():
    f = pm_forge.get_forge(url="github:octo/hello.git")
    assert isinstance(f, pm_forge.GithubForge) and f.repo_path == "octo/hello"
    assert pm_forge.forge_name("github.com") == "github"
    caps = f.capabilities
    assert caps.pull_request_api is True and caps.access_level_model == "github"


def test_github_state_normalization():
    S = pm_forge.GithubForge._state
    assert S({"merged": True, "state": "closed"}) == "merged"
    assert S({"merged_at": "2026-01-01", "state": "closed"}) == "merged"
    assert S({"merged": False, "state": "open"}) == "opened"
    assert S({"merged": False, "state": "closed"}) == "closed"


def test_github_pr_from():
    f = pm_forge.GithubForge("octo/hello")
    pr = f._pr_from({
        "number": 42, "state": "open", "merged": False,
        "html_url": "https://github.com/octo/hello/pull/42",
        "head": {"ref": "42-fix", "sha": "abc123"}, "base": {"ref": "main"},
    })
    assert pr.iid == 42 and pr.source == "42-fix" and pr.target == "main"
    assert pr.state == "opened" and pr.sha == "abc123"
    assert pr.web_url.endswith("/pull/42")


def test_github_compare_url():
    f = pm_forge.GithubForge("octo/hello")
    assert f.compare_url("42-fix", "main") == "https://github.com/octo/hello/compare/main...42-fix"



# ── RM2541 : une PR se désigne par son URL, pas par le répertoire courant ────
def _with_hosts(fn):
    """Exécute avec des forges déclarées (l'allow-list lit l'environnement)."""
    old = {k: os.environ.get(k) for k in ("GITLAB_URL", "GOGS_URL", "GITHUB_URL")}
    os.environ["GITLAB_URL"] = "https://gitlab.iprospective.fr"
    os.environ["GOGS_URL"] = "https://gogs.iprospective.fr"
    os.environ["GITHUB_URL"] = "https://github.com"
    try:
        fn()
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def test_parse_pr_url_les_trois_forges():
    def go():
        cases = [
            # GitLab : sous-groupes imbriqués, séparateur /-/
            ("https://gitlab.iprospective.fr/iprospective/ai-artificial-intelligence/"
             "ai-project-management/-/merge_requests/333",
             ("gitlab", "iprospective/ai-artificial-intelligence/ai-project-management", 333)),
            # GitLab : forme ancienne, sans /-/
            ("https://gitlab.iprospective.fr/grp/repo/merge_requests/7",
             ("gitlab", "grp/repo", 7)),
            # suffixe d'onglet (diffs, commits) : l'iid s'arrête au premier segment
            ("https://gitlab.iprospective.fr/grp/repo/-/merge_requests/7/diffs",
             ("gitlab", "grp/repo", 7)),
            ("https://github.com/owner/repo/pull/12", ("github", "owner/repo", 12)),
            ("https://gogs.iprospective.fr/Materiaux-Naturels/matnat/pulls/3",
             ("gogs", "Materiaux-Naturels/matnat", 3)),
        ]
        for url, want in cases:
            got = pm_forge.parse_pr_url(url)
            assert got == want, (url, got, want)
    _with_hosts(go)


def test_parse_pr_url_refuse_hote_non_declare():
    """Sécurité : une URL fournie ne doit jamais faire présenter un PAT à un
    hôte arbitraire. Le refus tombe AVANT tout appel réseau."""
    def go():
        for url in ("https://evil.example.com/a/b/-/merge_requests/1",
                    "https://gitlab.iprospective.fr.evil.tld/a/b/-/merge_requests/1"):
            try:
                pm_forge.parse_pr_url(url)
                assert False, f"hôte non déclaré accepté : {url}"
            except pm_forge.ForgeError as e:
                assert "inconnu des forges configur" in str(e), str(e)
    _with_hosts(go)


def test_parse_pr_url_formes_invalides():
    def go():
        for url in ("gitlab:grp/repo/-/merge_requests/1",            # pas une URL web
                    "https://gitlab.iprospective.fr/grp/repo",        # pas une PR
                    "https://gitlab.iprospective.fr/grp/repo/-/merge_requests/abc",
                    "https://gitlab.iprospective.fr/-/merge_requests/5"):  # dépôt absent
            try:
                pm_forge.parse_pr_url(url)
                assert False, f"URL invalide acceptée : {url}"
            except pm_forge.ForgeError:
                pass
    _with_hosts(go)


def test_get_forge_from_pr_url_sans_depot_local():
    """Le gain d'usage : plus besoin d'un checkout ni d'un cwd — l'URL suffit."""
    def go():
        forge, iid = pm_forge.get_forge_from_pr_url(
            "https://gitlab.iprospective.fr/grp/sub/repo/-/merge_requests/42")
        assert forge.name == "gitlab" and iid == 42
        assert forge.repo_path == "grp/sub/repo", forge.repo_path
    _with_hosts(go)


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
