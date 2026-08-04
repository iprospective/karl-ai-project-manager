#!/usr/bin/env python3
"""Tests offline de `pm-mr close` et de la garde --expect-rm (RM2540).

Lancer : python3 scripts/test_pm_mr_close.py
Aucun réseau : la forge est simulée. Couvre la fermeture d'une PR ouverte,
l'idempotence, le refus d'une PR mergée, la garde d'iid (tripwire #13) et le
cas d'une forge sans API PR.
"""
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
_spec = importlib.util.spec_from_file_location("pm_mr", str(_HERE / "pm-mr.py"))
pm_mr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm_mr)

import pm_forge  # noqa: E402


class FakeForge:
    """Forge minimale : mémorise les fermetures au lieu de les émettre."""

    def __init__(self, state="opened", source="2540-outillage", target="dev",
                 pull_request_api=True):
        self._pr = pm_forge.PrRef(iid=42, source=source, target=target,
                                  web_url="https://forge/mr/42", state=state, sha="abc")
        self.capabilities = pm_forge.Capabilities(pull_request_api, False, "gitlab")
        self.closed = []

    def resolve_project(self, token):
        return pm_forge.ProjectRef(id=79, path="grp/repo")

    def get_pr(self, project, iid, token):
        return self._pr

    def close_pr(self, project, iid, token):
        self.closed.append(iid)
        self._pr.state = "closed"


class Args:
    def __init__(self, **kw):
        self.iid, self.expect_rm = 42, None
        self.__dict__.update(kw)


def _exit_code(fn, *a):
    """Exécute et retourne le message de sys.exit, ou None si aucune sortie."""
    try:
        fn(*a)
        return None
    except SystemExit as e:
        return str(e)


def test_close_pr_ouverte():
    forge = FakeForge(state="opened")
    assert _exit_code(pm_mr.cmd_close, Args(), forge, "tok") is None
    assert forge.closed == [42], forge.closed


def test_close_idempotent():
    """Refermer une PR déjà fermée n'est pas une erreur — et n'appelle pas la forge."""
    forge = FakeForge(state="closed")
    assert _exit_code(pm_mr.cmd_close, Args(), forge, "tok") is None
    assert forge.closed == [], "une PR déjà fermée ne doit pas être refermée"


def test_close_refuse_une_pr_mergee():
    forge = FakeForge(state="merged")
    msg = _exit_code(pm_mr.cmd_close, Args(), forge, "tok")
    assert msg and "MERGÉE" in msg, msg
    assert forge.closed == []


def test_expect_rm_bloque_un_iid_errone():
    """Garde tripwire #13 : la branche source doit être celle du ticket annoncé."""
    forge = FakeForge(source="2499-autre-ticket")
    msg = _exit_code(pm_mr.cmd_close, Args(expect_rm=2540), forge, "tok")
    assert msg and "2499-autre-ticket" in msg, msg
    assert forge.closed == []


def test_expect_rm_laisse_passer_le_bon_ticket():
    forge = FakeForge(source="2540-outillage")
    assert _exit_code(pm_mr.cmd_close, Args(expect_rm=2540), forge, "tok") is None
    assert forge.closed == [42]


def test_expect_rm_admet_les_branches_de_flux():
    """Une promotion dev→main n'est préfixée d'aucun id : elle reste fermable."""
    forge = FakeForge(source="dev", target="main")
    assert _exit_code(pm_mr.cmd_close, Args(expect_rm=2540), forge, "tok") is None
    assert forge.closed == [42]


def test_forge_sans_api_pr():
    forge = FakeForge(pull_request_api=False)
    msg = _exit_code(pm_mr.cmd_close, Args(), forge, "tok")
    assert msg and "API PR" in msg, msg
    assert forge.closed == []


def test_close_est_une_action_manager():
    """Fermer touche à la gestion des PR : casquette manager, comme merge."""
    src = (_HERE / "pm-mr.py").read_text(encoding="utf-8")
    assert '"close": "manager"' in src, "close doit utiliser le token manager"


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
