#!/usr/bin/env python3
"""Tests d'intégration de `pm-task-partner mirror` — miroir d'états (N3, RM2746).

Lancer : python3 scripts/test_pm_task_partner_mirror_cli.py
Monte le même **arbre PM hermétique** que `test_pm_task_partner_cli.py` et appelle la
sous-commande réelle : ce qui est vérifié ici et pas dans `test_pm_partner_mirror.py`,
c'est l'écriture effective dans le lien (`last_seen_status`, `mirror_declined`), les
appends au `.log.md`, et le fait que la commande **ne fait rien** sans option.

Aucun réseau : le provider de tâches est remplacé par un double, et `--accept` n'est
exercé qu'en `--dry-run` — l'accepter pour de vrai délègue à `pm-task-status-update`,
qui appelle Redmine et relève de son propre test.
"""
import argparse
import contextlib
import importlib.util
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis")

SCRIPTS = Path(__file__).resolve().parent
REAL_CONFIG = SCRIPTS.parent / "pm.config.yml"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, str(SCRIPTS / filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cli = _load("pm_task_partner", "pm-task-partner.py")
import pm_partner

MAP = {"en_cours": {"label": "En cours", "id": 2},
       "a_tester_demandeur": {"label": "Résolu", "id": 3},
       "ferme": {"label": "Fermé", "id": 5}}

TASK_MD = """---
schema_version: 1.11.0
redmine_id: {rm}
title: Ticket de test {rm}
type: feature
creator: iprospective
status: {status}
priority: normal
{state_mirror}refs:
- type: partner_issue
  instance: redmine-matnat
  issue_id: 5576
  url: https://tasks.materiaux-naturels.fr/issues/5576
  role: mirror
  last_seen_journal_id: null
  last_seen_status: {seen}
  added: '2026-09-04'
created: '2026-09-04'
updated: 2026-09-04T10:00
status_history:
- status: {status}
  at: 2026-09-04T10:00
  by: iprospective
---

## Contexte

Corps du ticket.
"""


def _make_tree(tmp, mirror=None, status="ferme", seen="En cours", coched=None):
    pm_dir, projects = tmp / "pm", tmp / "projects"
    pm_dir.mkdir()
    cfg = yaml.safe_load(REAL_CONFIG.read_text(encoding="utf-8"))
    cfg["roots"] = {"pm_dir": str(pm_dir), "projects_root": str(projects),
                    "state_dir": str(tmp / "var"), "conf_dir": str(pm_dir),
                    "log_dir": str(tmp / "var" / "log")}
    (pm_dir / "pm.config.yml").write_text(yaml.safe_dump(cfg, allow_unicode=True),
                                          encoding="utf-8")
    proj = projects / "clients" / "acme" / "projects" / "site"
    (proj / "tasks").mkdir(parents=True)
    (proj / "project").mkdir()
    (proj / "project" / "overview.md").write_text("---\ntitle: site\n---\n", encoding="utf-8")
    sec = {"instance": "redmine-matnat", "role": "secondary", "project_id": 12}
    if mirror is not None:
        sec["sync"] = {"mirror": mirror}
    (proj / "meta.yml").write_text(yaml.safe_dump({"providers": {"task": [
        {"instance": "redmine-ipro", "role": "primary", "project_id": "acme-site"},
        sec]}}, allow_unicode=True), encoding="utf-8")
    sm = f"state_mirror: [{', '.join(coched)}]\n" if coched else ""
    (proj / "tasks" / "RM9001_test.md").write_text(
        TASK_MD.format(rm=9001, status=status, seen=seen, state_mirror=sm),
        encoding="utf-8")
    cfg_obj = PMConfig.load(pm_dir)
    os.environ.pop("REDMINE_CF_PARTNER_ISSUE_ID", None)
    return cfg_obj, proj


def _args(**kw):
    base = dict(rm_id=9001, push=False, accept=False, reject=False,
                dry_run=False, no_commit=True, verbose=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _call(cfg, **kw):
    buf, rc = io.StringIO(), 0
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            cli.cmd_mirror(cfg, _args(**kw))
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    return rc, buf.getvalue()


def _fm(proj):
    txt = (proj / "tasks" / "RM9001_test.md").read_text(encoding="utf-8")
    return yaml.safe_load(txt.split("---")[1])


def _log(proj):
    p = proj / "tasks" / "RM9001_test.log.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


class _Provider:
    """Double du provider de tâches : mémorise les écritures au lieu de les envoyer."""

    def __init__(self):
        self.calls = []

    def update_fields(self, issue_id, **kw):
        self.calls.append((issue_id, kw))


@contextlib.contextmanager
def _stub_provider():
    prov = _Provider()
    orig = pm_partner.get_task_provider
    pm_partner.get_task_provider = lambda instance=None: prov
    try:
        yield prov
    finally:
        pm_partner.get_task_provider = orig


# ── lecture seule : rendre compte, ne rien faire ───────────────────────────

def test_sans_option_ne_modifie_rien():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d), mirror={"regimes": ["signal"], "map": MAP})
        before = (proj / "tasks" / "RM9001_test.md").read_text(encoding="utf-8")
        rc, o = _call(cfg)
        assert rc == 0, o
        assert "DIVERGENCE" in o and "En cours" in o
        assert (proj / "tasks" / "RM9001_test.md").read_text(encoding="utf-8") == before
        assert _log(proj) == "", "aucune écriture de log en lecture seule"


def test_miroir_inactif_est_dit_explicitement():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))
        rc, o = _call(cfg)
        assert rc == 0 and "inactif" in o, o


def test_origine_de_la_declaration_est_affichee():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d), mirror={"regimes": ["signal"], "map": MAP})
        assert "au projet" in _call(cfg)[1]
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d), mirror={"map": MAP}, coched=["signal"])
        assert "au ticket" in _call(cfg)[1]


def test_statut_distant_jamais_observe_invite_a_puller():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d), mirror={"regimes": ["signal"], "map": MAP}, seen="")
        assert "pull" in _call(cfg)[1]


# ── sortant : écrire chez eux ──────────────────────────────────────────────

def test_push_pose_le_statut_et_memorise_ce_qui_a_ete_pose():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d), mirror={"regimes": ["outgoing"], "map": MAP})
        with _stub_provider() as prov:
            rc, o = _call(cfg, push=True)
        assert rc == 0, o
        assert prov.calls == [(5576, {"status_id": 5})], prov.calls
        # sans cette mémorisation, le passage suivant repousserait le même statut
        assert _fm(proj)["refs"][0]["last_seen_status"] == "Fermé"
        assert "Miroir sortant" in _log(proj)


def test_push_dry_run_n_ecrit_ni_chez_eux_ni_chez_nous():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d), mirror={"regimes": ["outgoing"], "map": MAP})
        with _stub_provider() as prov:
            rc, o = _call(cfg, push=True, dry_run=True)
        assert rc == 0 and prov.calls == []
        assert _fm(proj)["refs"][0]["last_seen_status"] == "En cours"
        assert _log(proj) == ""


def test_push_sans_regime_sortant_n_ecrit_pas():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d), mirror={"regimes": ["signal"], "map": MAP})
        with _stub_provider() as prov:
            rc, o = _call(cfg, push=True)
        assert rc == 0 and prov.calls == [], o
        assert _log(proj) == ""


def test_push_deja_dans_l_etat_n_ecrit_pas():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d), mirror={"regimes": ["outgoing"], "map": MAP},
                            seen="Fermé")
        with _stub_provider() as prov:
            _call(cfg, push=True)
        assert prov.calls == []


def test_push_sans_id_dans_la_table_est_signale_sans_planter():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d), status="a_mep",
                            mirror={"regimes": ["outgoing"], "map": {"a_mep": "Résolu"}})
        with _stub_provider() as prov:
            rc, o = _call(cfg, push=True)
        assert rc == 0 and prov.calls == []
        assert "id" in o


# ── entrant : proposer, refuser ────────────────────────────────────────────

def test_proposition_entrante_affichee_sans_etre_appliquee():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d), status="en_cours", seen="Fermé",
                               mirror={"regimes": ["incoming"], "map": MAP})
        rc, o = _call(cfg)
        assert rc == 0 and "proposition entrante" in o, o
        assert _fm(proj)["status"] == "en_cours", "le statut ne doit PAS bouger"


def test_reject_memorise_le_refus_et_le_rend_muet():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d), status="en_cours", seen="Fermé",
                               mirror={"regimes": ["incoming"], "map": MAP})
        rc, o = _call(cfg, reject=True)
        assert rc == 0, o
        assert _fm(proj)["refs"][0]["mirror_declined"] == "Fermé"
        assert "refusée" in _log(proj)
        # rechargé, le même état distant ne se propose plus
        cfg2 = PMConfig.load(Path(d) / "pm")
        assert "proposition entrante" not in _call(cfg2)[1]


def test_accept_dry_run_annonce_sans_transitionner():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d), status="en_cours", seen="Fermé",
                               mirror={"regimes": ["incoming"], "map": MAP})
        rc, o = _call(cfg, accept=True, dry_run=True)
        assert rc == 0 and "accepterait" in o, o
        assert _fm(proj)["status"] == "en_cours"


def test_accept_sans_proposition_ne_fait_rien():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d), status="ferme", seen="Fermé",
                               mirror={"regimes": ["incoming"], "map": MAP})
        rc, o = _call(cfg, accept=True)
        assert rc == 0 and "aucune proposition" in o, o
        assert _fm(proj)["status"] == "ferme"


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
