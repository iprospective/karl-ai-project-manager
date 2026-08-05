#!/usr/bin/env python3
"""Tests offline de la désignation d'une PR par `pm-mr` (RM2541).

Lancer : python3 scripts/test_pm_mr_target.py
Aucun réseau. Couvre `_resolve_pr` (URL > raccourci --rm-id > iid nu), le refus
d'un iid nu sans `--repo` explicite, le raccourci ticket (0 / 1 / N PR) et
`_record_pr_url` (persistance de l'URL dans le frontmatter).

Contexte : un iid nu n'a de sens que rapporté à un dépôt. Ce dépôt venait du
répertoire courant — d'où deux incidents vécus : une MR ouverte sur le mauvais
projet (RM2522) et un `merge` lancé depuis le dépôt de DONNÉES, qui échouait en
404 opaque (RM2537). L'URL, elle, porte sa propre cible.
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
_spec = importlib.util.spec_from_file_location("pm_mr", str(_HERE / "pm-mr.py"))
pm_mr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm_mr)

import pm_forge  # noqa: E402

URL = ("https://gitlab.iprospective.fr/iprospective/ai-artificial-intelligence/"
       "ai-project-management/-/merge_requests/333")


class Args:
    def __init__(self, **kw):
        self.target_pr, self.rm_id, self.repo = None, None, None
        self.__dict__.update(kw)


def _exit_msg(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except SystemExit as e:
        return str(e)


def _with_env(fn):
    old = {k: os.environ.get(k) for k in ("GITLAB_URL", "GITLAB_MANAGER_TOKEN")}
    os.environ["GITLAB_URL"] = "https://gitlab.iprospective.fr"
    os.environ["GITLAB_MANAGER_TOKEN"] = "tok-test"
    try:
        fn()
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def test_url_resout_forge_projet_et_iid():
    """Le cas canonique : aucun dépôt local, aucun cwd — l'URL suffit."""
    def go():
        forge, token, iid, origin = pm_mr._resolve_pr(Args(target_pr=URL), "manager")
        assert forge.name == "gitlab" and iid == 333, (forge.name, iid)
        assert forge.repo_path == "iprospective/ai-artificial-intelligence/ai-project-management"
        assert token == "tok-test"
        assert URL in origin, origin        # l'origine est tracée pour les messages
    _with_env(go)


def test_iid_nu_sans_repo_refuse():
    """Le cœur de RM2541 : plus de dépôt déduit du répertoire courant."""
    msg = _exit_msg(pm_mr._resolve_pr, Args(target_pr="333"), "manager")
    assert msg and "--repo" in msg and "répertoire courant" in msg, msg


def test_aucune_cible_refuse_avec_les_trois_voies():
    msg = _exit_msg(pm_mr._resolve_pr, Args(), "manager")
    assert msg and "URL" in msg and "--rm-id" in msg, msg


def test_hote_non_declare_refuse_avant_tout_appel():
    def go():
        msg = _exit_msg(pm_mr._resolve_pr,
                        Args(target_pr="https://evil.example.com/a/b/-/merge_requests/1"),
                        "manager")
        # remonte en ForgeError (traitée par main) plutôt qu'en SystemExit
        assert msg is None
    try:
        _with_env(go)
        assert False, "hôte non déclaré accepté"
    except pm_forge.ForgeError as e:
        assert "inconnu des forges" in str(e), str(e)


# ── raccourci --rm-id : commodité, et seulement si NON AMBIGU ────────────────
def _fake_task(tmp, urls):
    """Écrit un MD de tâche minimal et branche PMConfig.find_task dessus."""
    md = Path(tmp) / "RM9999_test.md"
    lst = "".join(f"\n  - {u}" for u in urls)
    md.write_text("---\nredmine_id: 9999\ngit:\n  repo: r\n  branch: b\n"
                  f"  mr_urls:{lst if urls else ' []'}\n---\n\ncorps\n", encoding="utf-8")

    class FakeCfg:
        def find_task(self, rm_id):
            return md
    pm_mr.PMConfig.load = staticmethod(lambda *a, **k: FakeCfg())
    return md


def test_rm_id_une_seule_pr():
    def go():
        with tempfile.TemporaryDirectory() as tmp:
            _fake_task(tmp, [URL])
            forge, _tok, iid, origin = pm_mr._resolve_pr(Args(rm_id=9999), "manager")
            assert iid == 333 and forge.name == "gitlab"
            assert "RM9999" in origin, origin
    _with_env(go)


def test_rm_id_plusieurs_pr_refuse_en_listant():
    """Jamais de choix silencieux : un ticket porte 0, 1 ou N PR."""
    def go():
        with tempfile.TemporaryDirectory() as tmp:
            other = URL.replace("/333", "/334")
            _fake_task(tmp, [URL, other])
            msg = _exit_msg(pm_mr._resolve_pr, Args(rm_id=9999), "manager")
            assert msg and "2 PR" in msg and other in msg, msg
    _with_env(go)


def test_rm_id_sans_pr_memorisee():
    def go():
        with tempfile.TemporaryDirectory() as tmp:
            _fake_task(tmp, [])
            msg = _exit_msg(pm_mr._resolve_pr, Args(rm_id=9999), "manager")
            assert msg and "aucune PR mémorisée" in msg, msg
    _with_env(go)


def test_url_prime_sur_le_raccourci():
    """Si les deux sont donnés, l'explicite gagne — jamais l'inverse."""
    def go():
        with tempfile.TemporaryDirectory() as tmp:
            _fake_task(tmp, [URL.replace("/333", "/999")])
            _f, _t, iid, _o = pm_mr._resolve_pr(Args(target_pr=URL, rm_id=9999), "manager")
            assert iid == 333, iid
    _with_env(go)


# ── persistance : create doit laisser une trace côté MD, pas seulement Redmine ─
def test_record_pr_url_ecrit_une_liste():
    with tempfile.TemporaryDirectory() as tmp:
        md = _fake_task(tmp, [])
        pm_mr._record_pr_url(9999, URL)
        txt = md.read_text(encoding="utf-8")
        assert URL in txt and "mr_urls:" in txt, txt
        assert "corps" in txt, "le corps du MD doit être préservé"
        pm_mr._record_pr_url(9999, URL)                       # idempotent
        assert txt.count(URL) == md.read_text(encoding="utf-8").count(URL)


def test_record_pr_url_reprend_l_ancien_scalaire():
    """Migration douce : un `git.mr_url` existant entre dans la liste."""
    with tempfile.TemporaryDirectory() as tmp:
        md = Path(tmp) / "RM9999_test.md"
        old = URL.replace("/333", "/300")
        md.write_text(f"---\nredmine_id: 9999\ngit:\n  mr_url: {old}\n---\n\ncorps\n",
                      encoding="utf-8")

        class FakeCfg:
            def find_task(self, rm_id):
                return md
        pm_mr.PMConfig.load = staticmethod(lambda *a, **k: FakeCfg())
        pm_mr._record_pr_url(9999, URL)
        txt = md.read_text(encoding="utf-8")
        assert old in txt and URL in txt, txt


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
