#!/usr/bin/env python3
"""Tests offline de la garde `check_state_mirror` de pm-doctor (N3, RM2746).

Lancer : python3 scripts/test_pm_doctor_state_mirror.py
La garde est exécutée POUR DE VRAI sur une arborescence de tâches temporaire : un
contrôle vert sur zéro donnée ne prouverait rien — ce qu'on veut vérifier, c'est
qu'il parcourt bien les fiches et qu'il voit la divergence quand elle existe.
Aucun réseau, aucune écriture hors du dossier temporaire.
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

spec = importlib.util.spec_from_file_location("pm_doctor", HERE / "pm-doctor.py")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)

PROVIDERS = {
    "defaults": {"task": "redmine-ipro"},
    "servers": {
        "redmine-ipro":   {"axis": "task", "type": "redmine", "url": "https://tasks.ipro"},
        "redmine-matnat": {"axis": "task", "type": "redmine", "url": "https://tasks.clientd",
                           "slug": "clientd"},
    },
}
MAP = {"en_cours": {"label": "En cours", "id": 2},
       "a_tester_demandeur": {"label": "Résolu", "id": 3},
       "a_mep": "Résolu",
       "ferme": {"label": "Fermé", "id": 5}}


class Cfg:
    """Double minimal de PMConfig : la garde n'utilise que `providers` et `path`."""

    def __init__(self, tasks_dir):
        self.providers = PROVIDERS
        self._dir = Path(tasks_dir)

    def path(self, kind, entity=None, project=None):
        assert kind == "tasks_dir"
        return self._dir


def _overview(mirror=None, secondary=True):
    task = [{"instance": "redmine-ipro", "role": "primary", "project_id": "p"}]
    if secondary:
        sec = {"instance": "redmine-matnat", "role": "secondary", "project_id": 12}
        if mirror is not None:
            sec["sync"] = {"mirror": mirror}
        task.append(sec)
    return {"providers": {"task": task}}


def _write_task(d, rm_id, status, seen, coched=None, extra_ref=True):
    refs = ""
    if extra_ref:
        refs = (f"refs:\n"
                f"- type: partner_issue\n"
                f"  instance: redmine-matnat\n"
                f"  issue_id: 5576\n"
                f"  role: mirror\n"
                f"  last_seen_status: {seen}\n")
    sm = f"state_mirror: [{', '.join(coched)}]\n" if coched else ""
    (Path(d) / f"RM{rm_id}_t.md").write_text(
        f"---\nredmine_id: {rm_id}\nstatus: {status}\n{sm}{refs}---\n\ncorps\n",
        encoding="utf-8")


def _run(mirror=None, status="ferme", seen="En cours", coched=None, **kw):
    """Exécute la garde et rend ses avertissements."""
    with tempfile.TemporaryDirectory() as d:
        _write_task(d, 2746, status, seen, coched, **kw)
        errors, warns = [], []
        ovs = {("iprospective", "pm-ai-agents"): _overview(mirror)}
        doctor.check_state_mirror(Cfg(d), ovs, errors, warns)
        assert errors == [], f"la garde ne doit rien porter en erreur : {errors}"
        return warns


# ── le contrôle voit réellement les fiches ─────────────────────────────────

def test_divergence_vue_sur_une_fiche_reelle():
    warns = _run(mirror={"regimes": ["signal"], "map": MAP})
    assert len(warns) == 1, warns
    assert "RM2746" in warns[0] and "En cours" in warns[0] and "Fermé" in warns[0]
    assert "pm-task-partner mirror" in warns[0], "l'avertissement doit dire quoi faire"


def test_aucun_bruit_quand_les_etats_concordent():
    assert _run(mirror={"regimes": ["signal"], "map": MAP}, seen="Fermé") == []


# ── inertie : ne rien dire tant que rien n'est déclaré ─────────────────────

def test_projet_muet_ne_produit_aucun_avertissement():
    assert _run(mirror=None) == []


def test_projet_sans_secondaire_est_ignore():
    with tempfile.TemporaryDirectory() as d:
        _write_task(d, 2746, "ferme", "En cours")
        errors, warns = [], []
        doctor.check_state_mirror(
            Cfg(d), {("i", "p"): _overview(secondary=False)}, errors, warns)
        assert (errors, warns) == ([], [])


def test_fiche_sans_lien_partenaire_est_ignoree():
    assert _run(mirror={"regimes": ["signal"], "map": MAP}, extra_ref=False) == []


# ── la case cochée sur le ticket pilote la garde ───────────────────────────

def test_ticket_active_le_miroir_sans_le_projet():
    warns = _run(mirror={"map": MAP}, coched=["signal"])
    assert len(warns) == 1 and "RM2746" in warns[0]


def test_ticket_none_fait_taire_un_projet_bavard():
    assert _run(mirror={"regimes": ["signal"], "map": MAP}, coched=["none"]) == []


def test_regime_inconnu_est_signale():
    warns = _run(mirror={"regimes": ["signal"], "map": MAP}, coched=["signal", "zzz"])
    assert any("inconnu" in w and "zzz" in w for w in warns), warns


# ── entrant : proposition et table ambiguë ─────────────────────────────────

def test_proposition_entrante_est_annoncee_comme_a_valider():
    warns = _run(mirror={"regimes": ["incoming"], "map": MAP}, status="en_cours",
                 seen="Fermé")
    prop = [w for w in warns if "propose" in w]
    assert len(prop) == 1 and "--accept" in prop[0], warns


def test_table_ambigue_est_dite_inoperante_en_entrant():
    warns = _run(mirror={"regimes": ["incoming"], "map": MAP}, status="en_cours",
                 seen="Résolu")
    assert any("inopérant" in w and "map_in" in w for w in warns), warns


def test_ambiguite_muette_hors_regime_entrant():
    """Le sens NORMS→eux reste défini : l'ambiguïté ne gêne que l'inverse."""
    warns = _run(mirror={"regimes": ["signal", "outgoing"], "map": MAP},
                 status="en_cours", seen="Résolu")
    assert not any("inopérant" in w for w in warns), warns


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
