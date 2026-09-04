#!/usr/bin/env python3
"""Tests offline du rapatriement du CF35 « Sync ticket externe » (N3, RM2746).

Lancer : python3 scripts/test_pm_task_sync_state_mirror.py
Le CF est une **énumération** : sa valeur arrive en id (« 80 »), jamais en libellé —
c'est le piège que ces tests verrouillent, avec l'autre : un CF vide ne doit pas
écraser un réglage local, parce que « vide » veut dire « pas d'information », pas
« le demandeur a décoché ». Aucun réseau.
"""
import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

spec = importlib.util.spec_from_file_location("pm_task_sync", HERE / "pm-task-sync.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

import pm_partner

CF_ID = 35          # « Sync ticket externe » — cf. redmine.reference.yml


def _issue(value):
    return {"custom_fields": [{"id": CF_ID, "name": "Sync ticket externe",
                               "value": value}]}


def setup():
    """Résolution par NOM depuis redmine.reference.yml — pas d'override d'environnement."""
    os.environ.pop("REDMINE_CF_STATE_MIRROR_ID", None)


# ── décodage des ids d'énumération ─────────────────────────────────────────

def test_chaque_valeur_du_cf_se_decode():
    setup()
    for value, expected in (("77", "signal"), ("78", "outgoing"),
                            ("79", "incoming"), ("80", "mirror")):
        assert sync.state_mirror_from_cf(_issue(value)) == [expected], value


def test_la_valeur_mirror_vaut_les_deux_sens():
    setup()
    from pm_registry import Instance, Resolution
    res = Resolution(Instance("redmine-matnat", "task", "redmine", "https://x"),
                     sync={"mirror": {"map": {}}}, role="secondary")
    fm = {"status": "ferme", "state_mirror": sync.state_mirror_from_cf(_issue("80"))}
    assert pm_partner.effective_regimes(fm, res) == ["signal", "outgoing", "incoming"]


def test_id_inconnu_est_rendu_tel_quel_pas_perdu():
    """pm_partner ignorera la valeur et pm-doctor la signalera — mieux qu'un silence."""
    setup()
    assert sync.state_mirror_from_cf(_issue("999")) == ["999"]


def test_liste_acceptee_si_le_cf_passe_en_multi_valeur():
    setup()
    assert sync.state_mirror_from_cf(_issue(["77", "78"])) == ["signal", "outgoing"]


# ── ce qui ne doit RIEN écraser ────────────────────────────────────────────

def test_cf_decoche_vide_le_regime():
    """Décocher est une INTENTION : laisser le régime actif ferait écrire chez un tiers
    contre la volonté de celui qui vient de le retirer."""
    setup()
    for empty in ("", None, []):
        assert sync.state_mirror_from_cf(_issue(empty)) == [], empty


def test_cf_absent_de_l_issue_ne_dit_rien():
    """Pas exposé sur ce projet ≠ décoché : ici on ne sait rien, on ne touche à rien."""
    setup()
    assert sync.state_mirror_from_cf({"custom_fields": []}) is None
    assert sync.state_mirror_from_cf({}) is None
    assert sync.state_mirror_from_cf({"custom_fields": [{"id": 8, "value": "x"}]}) is None


def test_decochage_produit_bien_un_diff():
    setup()
    fm = {"status": "en_cours", "state_mirror": ["mirror"]}
    coched = sync.state_mirror_from_cf(_issue(None))
    assert coched == [] and list(fm["state_mirror"]) != coched


def test_cf_non_resolu_reste_inerte():
    """Sur une instance qui n'a pas ce CF, le rapatriement ne doit rien tenter."""
    os.environ["REDMINE_CF_STATE_MIRROR_ID"] = "0"      # non numérique valide → None
    try:
        orig = sync.pm_cf_mirror.resolve_cf_id
        sync.pm_cf_mirror.resolve_cf_id = lambda env_var, cf_name: None
        assert sync.state_mirror_from_cf(_issue("80")) is None
    finally:
        sync.pm_cf_mirror.resolve_cf_id = orig
        os.environ.pop("REDMINE_CF_STATE_MIRROR_ID", None)


# ── diff : ce qui part réellement dans le frontmatter ──────────────────────

def test_diff_pose_le_regime_quand_il_change():
    setup()
    fm = {"status": "en_cours", "state_mirror": []}
    coched = sync.state_mirror_from_cf(_issue("80"))
    assert coched is not None and list(fm["state_mirror"]) != coched


def test_diff_muet_quand_le_regime_est_deja_le_bon():
    setup()
    fm = {"status": "en_cours", "state_mirror": ["mirror"]}
    assert list(fm["state_mirror"]) == sync.state_mirror_from_cf(_issue("80"))


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
