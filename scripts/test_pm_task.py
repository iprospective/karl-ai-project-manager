#!/usr/bin/env python3
"""Tests offline de pm_task — interface TaskProvider + backend Redmine (P1/RM2543).

Lancer : python3 scripts/test_pm_task.py
Couvre : capabilities Redmine, fabrique get_task_provider (défaut / instance
explicite / via registre P0 / backend non supporté), délégation stricte à
redmine_utils (monkeypatch, aucun réseau), contrat générique non implémenté.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_task
import pm_registry

Instance = pm_registry.Instance
Registry = pm_registry.Registry


def test_redmine_capabilities():
    caps = pm_task.RedmineTaskProvider().capabilities
    assert caps.custom_fields and caps.time_tracking and caps.wiki
    assert caps.full_text_search and caps.parent_link and caps.ia_tag


def test_factory_default_is_redmine():
    p = pm_task.get_task_provider()
    assert isinstance(p, pm_task.RedmineTaskProvider) and p.name == "redmine"
    assert p.instance is None  # usage direct mono-instance


def test_factory_explicit_instance():
    inst = Instance("redmine-ipro", "task", "redmine", "https://tasks.example")
    p = pm_task.get_task_provider(instance=inst)
    assert isinstance(p, pm_task.RedmineTaskProvider) and p.instance is inst


def test_factory_unsupported_backend():
    inst = Instance("gh-issues", "task", "github_issues", "https://github.com")
    try:
        pm_task.get_task_provider(instance=inst)
        raise AssertionError("attendu TaskProviderError")
    except pm_task.TaskProviderError:
        pass


def test_factory_via_registry_legacy_meta():
    reg = Registry.from_config({
        "defaults": {"task": "redmine-ipro"},
        "servers": {"redmine-ipro": {"axis": "task", "type": "redmine",
                                     "url": "https://tasks.example"}},
    })
    meta = {"redmine": {"project_id": 42}}   # bloc legacy → défaut task
    p = pm_task.get_task_provider(project_meta=meta, registry=reg)
    assert isinstance(p, pm_task.RedmineTaskProvider)
    assert p.instance.name == "redmine-ipro"


def test_delegation_fetch_issue():
    calls = {}
    orig = pm_task._ru.fetch_issue

    def stub(iid, include=None):
        calls["args"] = (iid, include)
        return {"id": iid}
    pm_task._ru.fetch_issue = stub
    try:
        out = pm_task.RedmineTaskProvider().fetch_issue(1669, include="journals")
        assert out == {"id": 1669}
        assert calls["args"] == (1669, "journals")
    finally:
        pm_task._ru.fetch_issue = orig


def test_delegation_add_note():
    seen = {}
    orig = pm_task._ru.add_issue_note

    def stub(iid, note, **kw):
        seen["v"] = (iid, note)
        return True
    pm_task._ru.add_issue_note = stub
    try:
        assert pm_task.RedmineTaskProvider().add_note(42, "hello") is True
        assert seen["v"] == (42, "hello")
    finally:
        pm_task._ru.add_issue_note = orig


def test_delegation_set_parent():
    seen = {}
    orig = pm_task._ru.set_issue_parent
    pm_task._ru.set_issue_parent = lambda iid, pid: seen.setdefault("v", (iid, pid))
    try:
        pm_task.RedmineTaskProvider().set_parent(10, 5)
        assert seen["v"] == (10, 5)
    finally:
        pm_task._ru.set_issue_parent = orig


class _FakeForge:
    """Faux GitlabForge : renvoie des réponses canned, aucun réseau."""
    def __init__(self, responses):
        self._responses = responses  # list de (status, data, raw), consommée en ordre
        self.calls = []

    def api(self, method, path, token, fields=None):
        self.calls.append((method, path))
        return self._responses.pop(0)


def _gl_provider(responses):
    p = pm_task.GitlabIssuesTaskProvider(repo="grp/repo")  # GitlabForge réel, pas d'appel réseau
    p._forge = _FakeForge(list(responses))
    p._token_cache = "tok"
    p._pid = 79
    return p


def test_gitlab_issues_capabilities():
    caps = pm_task.GitlabIssuesTaskProvider(repo="grp/repo").capabilities
    assert caps.full_text_search is True
    assert caps.custom_fields is False and caps.time_tracking is False and caps.ia_tag is False


def test_factory_gitlab_issues_via_instance():
    inst = Instance("gl-issues", "task", "gitlab_issues", "https://gl.example",
                    options={"repo": "grp/repo"})
    p = pm_task.get_task_provider(instance=inst)
    assert isinstance(p, pm_task.GitlabIssuesTaskProvider) and p.instance is inst


def test_gitlab_issues_requires_repo():
    inst = Instance("gl-issues", "task", "gitlab_issues", "https://gl.example")  # pas de repo
    try:
        pm_task.get_task_provider(instance=inst)
        raise AssertionError("attendu TaskProviderError (repo requis)")
    except pm_task.TaskProviderError:
        pass


def test_gitlab_issues_list_and_fetch():
    p = _gl_provider([(200, [{"iid": 1}, {"iid": 2}], "")])
    issues = p.list_issues(limit=5)
    assert [i["iid"] for i in issues] == [1, 2]
    assert p._forge.calls[0][0] == "GET" and "/projects/79/issues" in p._forge.calls[0][1]
    p2 = _gl_provider([(200, {"iid": 7, "title": "x"}, "")])
    assert p2.fetch_issue(7)["iid"] == 7


def test_gitlab_issues_http_error_raises():
    p = _gl_provider([(403, None, "forbidden")])
    try:
        p.list_issues()
        raise AssertionError("attendu TaskProviderError (HTTP 403)")
    except pm_task.TaskProviderError:
        pass


def test_gitlab_issues_write_out_of_scope():
    p = pm_task.GitlabIssuesTaskProvider(repo="grp/repo")
    for call in (lambda: p.add_note(1, "x"), lambda: p.create_issue(), lambda: p.set_parent(1, 2)):
        try:
            call()
            raise AssertionError("attendu TaskProviderError (lecture seule)")
        except pm_task.TaskProviderError:
            pass


def test_generic_contract_not_implemented():
    base = pm_task.TaskProvider()
    for call in (lambda: base.fetch_issue(1), lambda: base.add_note(1, "x"),
                 lambda: base.create_issue(), lambda: base.set_parent(1, 2)):
        try:
            call()
            raise AssertionError("attendu NotImplementedError")
        except NotImplementedError:
            pass


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
