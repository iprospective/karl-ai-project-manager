#!/usr/bin/env python3
"""Tests offline de pm_doc — interface DocProvider + backend wiki Redmine (P3/RM2545).

Lancer : python3 scripts/test_pm_doc.py
Couvre : capabilities, fabrique get_doc_provider (défaut / instance / registre P0 /
backend non supporté), get_doc/put_doc (200/404/erreur), description projet, contrat
générique non implémenté. Aucun réseau (http_json et redmine_creds monkeypatchés).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_doc
import pm_registry

Instance = pm_registry.Instance
Registry = pm_registry.Registry


def _patch_creds():
    orig = pm_doc._ru.redmine_creds
    pm_doc._ru.redmine_creds = lambda: ("https://tasks.example", "KEY")
    return orig


def test_redmine_wiki_capabilities():
    caps = pm_doc.RedmineWikiDocProvider().capabilities
    assert caps.versioning and caps.wiki_links and caps.attachments
    assert caps.project_description


def test_factory_default_is_redmine_wiki():
    p = pm_doc.get_doc_provider()
    assert isinstance(p, pm_doc.RedmineWikiDocProvider) and p.name == "redmine_wiki"
    assert p.instance is None


def test_factory_explicit_instance():
    inst = Instance("redmine-wiki", "doc", "redmine_wiki", "https://tasks.example")
    p = pm_doc.get_doc_provider(instance=inst)
    assert isinstance(p, pm_doc.RedmineWikiDocProvider) and p.instance is inst


def test_factory_unsupported_backend():
    inst = Instance("nc-ipro", "doc", "nextcloud", "https://cloud.example")
    try:
        pm_doc.get_doc_provider(instance=inst)
        raise AssertionError("attendu DocProviderError")
    except pm_doc.DocProviderError:
        pass


def test_factory_via_registry_default():
    reg = Registry.from_config({
        "defaults": {"doc": "redmine-wiki"},
        "servers": {"redmine-wiki": {"axis": "doc", "type": "redmine_wiki",
                                     "url": "https://tasks.example"}},
    })
    p = pm_doc.get_doc_provider(project_meta={}, registry=reg)
    assert isinstance(p, pm_doc.RedmineWikiDocProvider)
    assert p.instance.name == "redmine-wiki"


def test_get_doc_exists():
    orig_c = _patch_creds()
    orig_h = pm_doc._ru.http_json

    def stub(method, url, key, payload=None, timeout=20):
        assert method == "GET" and url.endswith("/projects/proj/wiki/Page.json")
        return 200, {"wiki_page": {"text": "hello", "version": 3}}
    pm_doc._ru.http_json = stub
    try:
        exists, text, ver = pm_doc.RedmineWikiDocProvider().get_doc("proj", "Page")
        assert exists is True and text == "hello" and ver == 3
    finally:
        pm_doc._ru.http_json = orig_h
        pm_doc._ru.redmine_creds = orig_c


def test_get_doc_absent():
    orig_c = _patch_creds()
    orig_h = pm_doc._ru.http_json
    pm_doc._ru.http_json = lambda *a, **k: (404, {"_error": "not found"})
    try:
        exists, text, ver = pm_doc.RedmineWikiDocProvider().get_doc("proj", "Nope")
        assert exists is False and text == "" and ver is None
    finally:
        pm_doc._ru.http_json = orig_h
        pm_doc._ru.redmine_creds = orig_c


def test_get_doc_error_raises():
    orig_c = _patch_creds()
    orig_h = pm_doc._ru.http_json
    pm_doc._ru.http_json = lambda *a, **k: (500, {"_error": "boom"})
    try:
        pm_doc.RedmineWikiDocProvider().get_doc("proj", "X")
        raise AssertionError("attendu DocProviderError")
    except pm_doc.DocProviderError:
        pass
    finally:
        pm_doc._ru.http_json = orig_h
        pm_doc._ru.redmine_creds = orig_c


def test_put_doc_ok_and_error():
    orig_c = _patch_creds()
    orig_h = pm_doc._ru.http_json
    seen = {}

    def stub(method, url, key, payload=None, timeout=20):
        seen["v"] = (method, url, payload)
        return 201, {}
    pm_doc._ru.http_json = stub
    try:
        code = pm_doc.RedmineWikiDocProvider().put_doc("proj", "Page", "body")
        assert code == 201
        assert seen["v"][0] == "PUT" and seen["v"][2] == {"wiki_page": {"text": "body"}}
        pm_doc._ru.http_json = lambda *a, **k: (403, {"_error": "forbidden"})
        try:
            pm_doc.RedmineWikiDocProvider().put_doc("proj", "Page", "body")
            raise AssertionError("attendu DocProviderError")
        except pm_doc.DocProviderError:
            pass
    finally:
        pm_doc._ru.http_json = orig_h
        pm_doc._ru.redmine_creds = orig_c


def test_project_description_get():
    orig_c = _patch_creds()
    orig_h = pm_doc._ru.http_json
    pm_doc._ru.http_json = lambda *a, **k: (200, {"project": {"description": "desc"}})
    try:
        assert pm_doc.RedmineWikiDocProvider().get_project_description("proj") == "desc"
    finally:
        pm_doc._ru.http_json = orig_h
        pm_doc._ru.redmine_creds = orig_c


def test_generic_contract_not_implemented():
    base = pm_doc.DocProvider()
    for call in (lambda: base.get_doc("p", "t"), lambda: base.put_doc("p", "t", "c")):
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
