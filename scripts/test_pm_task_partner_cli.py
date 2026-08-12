#!/usr/bin/env python3
"""Tests d'intégration de `pm-task-partner` — link / unlink / show (N0, RM2654).

Lancer : python3 scripts/test_pm_task_partner_cli.py
Monte un **arbre PM hermétique** (config + client/projet/tâches en tmpdir), charge la
config de test via `PMConfig.load(pm_dir)` et appelle les sous-commandes réelles.
Aucun réseau : le CF « Ticket partenaire » n'est pas configuré (donc jamais poussé) et
la note distante est désactivée par `no_remote_note`.

Ce qui est vérifié ici et pas dans `test_pm_partner.py` : l'écriture réelle du
frontmatter (`refs[]`, `updated`), l'append au `.log.md`, le refus d'une instance non
déclarée, et le contrôle `pm-doctor` (tickets ouverts seulement).
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
doctor = _load("pm_doctor", "pm-doctor.py")

TASK_MD = """---
schema_version: 1.11.0
redmine_id: {rm}
title: Ticket de test {rm}
type: feature
creator: iprospective
status: {status}
priority: normal
refs: []
created: '2026-08-12'
updated: 2026-08-12T10:00
status_history:
- status: {status}
  at: 2026-08-12T10:00
  by: iprospective
---

## Contexte

Corps du ticket.
"""


def _make_tree(tmp, secondary=True, policy="required"):
    """Arbre PM minimal : pm_dir (config) + projects_root (client/projet/tâches)."""
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
    task = [{"instance": "redmine-ipro", "role": "primary", "project_id": "acme-site"}]
    if secondary:
        task.append({"instance": "redmine-matnat", "role": "secondary",
                     "project_id": 12, "link": {"policy": policy}})
    (proj / "meta.yml").write_text(
        yaml.safe_dump({"providers": {"task": task}}, allow_unicode=True), encoding="utf-8")
    for rm, status in ((9001, "en_cours"), (9002, "ferme")):
        (proj / "tasks" / f"RM{rm}_test.md").write_text(
            TASK_MD.format(rm=rm, status=status), encoding="utf-8")
    os.environ.pop("REDMINE_CF_PARTNER_ISSUE_ID", None)   # CF non configuré → aucun réseau
    return PMConfig.load(pm_dir), proj


def _args(**kw):
    base = dict(no_commit=True, dry_run=False, no_remote_note=True, url=None,
                instance=None, issue=None, role="related", verbose=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _call(fn, cfg, args):
    """Exécute une sous-commande. Retourne (rc, sortie) — rc≠0 si out.fail a coupé."""
    buf = io.StringIO()
    rc = 0
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            fn(cfg, args)
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    return rc, buf.getvalue()


def _link(cfg, rm=9001, instance="redmine-matnat", issue=1234, role="related", **kw):
    return _call(cli.cmd_link, cfg,
                 _args(rm_id=rm, instance=instance, issue=issue, role=role, **kw))


def _fm(proj, rm=9001):
    txt = (proj / "tasks" / f"RM{rm}_test.md").read_text(encoding="utf-8")
    return yaml.safe_load(txt.split("---")[1])


def _log(proj, rm=9001):
    p = proj / "tasks" / f"RM{rm}_test.log.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ── link ───────────────────────────────────────────────────────────────────

def test_link_writes_ref_and_log():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        rc, o = _link(cfg, role="mirror")
        assert rc == 0, o
        fm = _fm(proj)
        assert len(fm["refs"]) == 1
        ref = fm["refs"][0]
        assert ref["type"] == "partner_issue" and ref["instance"] == "redmine-matnat"
        assert ref["issue_id"] == 1234 and ref["role"] == "mirror"
        assert ref["url"] == "https://tasks.materiaux-naturels.fr/issues/1234"
        assert ref["last_seen_journal_id"] is None
        assert fm["updated"] != "2026-08-12T10:00", "updated doit être rafraîchi"
        assert "redmine-matnat#1234" in _log(proj)
        # le corps du ticket survit à la réécriture du frontmatter
        assert "## Contexte" in (proj / "tasks" / "RM9001_test.md").read_text(encoding="utf-8")


def test_link_dry_run_writes_nothing():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        rc, o = _link(cfg, dry_run=True)
        assert rc == 0 and "dry-run" in o
        assert _fm(proj)["refs"] == [] and _log(proj) == ""


def test_link_refuses_undeclared_instance():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        rc, o = _link(cfg, instance="redmine-pisceen")
        assert rc != 0 and "secondaire" in o
        assert _fm(proj)["refs"] == []


def test_link_refuses_the_primary_itself():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        rc, o = _link(cfg, instance="redmine-ipro")
        assert rc != 0 and "secondaire" in o


def test_link_refuses_second_mirror_and_duplicate():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        assert _link(cfg, issue=1234, role="mirror")[0] == 0
        rc, o = _link(cfg, issue=5678, role="mirror")
        assert rc != 0 and "miroir" in o
        rc, o = _link(cfg, issue=1234, role="related")
        assert rc != 0 and "déjà présent" in o
        assert _link(cfg, issue=5678, role="related")[0] == 0   # celui-ci est légitime
        assert len(_fm(proj)["refs"]) == 2


def test_link_on_project_without_secondary():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d), secondary=False)
        rc, o = _link(cfg)
        assert rc != 0 and "aucun provider secondaire" in o


# ── unlink ─────────────────────────────────────────────────────────────────

def test_unlink_removes_only_the_target():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        _link(cfg, issue=1234, role="mirror")
        _link(cfg, issue=5678, role="related")
        rc, o = _call(cli.cmd_unlink, cfg,
                      _args(rm_id=9001, instance="redmine-matnat", issue=1234))
        assert rc == 0, o
        refs = _fm(proj)["refs"]
        assert len(refs) == 1 and refs[0]["issue_id"] == 5678
        assert "Délié" in _log(proj)


def test_unlink_unknown_link_fails_cleanly():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        rc, o = _call(cli.cmd_unlink, cfg,
                      _args(rm_id=9001, instance="redmine-matnat", issue=None))
        assert rc != 0 and "pas de lien partenaire" in o
        assert _fm(proj)["refs"] == []


def test_unlink_dry_run_keeps_the_ref():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        _link(cfg, issue=1234)
        rc, o = _call(cli.cmd_unlink, cfg,
                      _args(rm_id=9001, instance="redmine-matnat", issue=1234,
                            dry_run=True))
        assert rc == 0 and "dry-run" in o
        assert len(_fm(proj)["refs"]) == 1


# ── show ───────────────────────────────────────────────────────────────────

def test_show_lists_secondaries_and_missing_required():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))
        rc, o = _call(cli.cmd_show, cfg, _args(rm_id=9001))
        assert rc == 0
        assert "redmine-matnat" in o and "policy=required" in o
        assert "liens partenaires : aucun" in o and "OBLIGATOIRE manquant" in o
        _link(cfg, issue=42)
        rc, o = _call(cli.cmd_show, cfg, _args(rm_id=9001))
        assert "redmine-matnat#42" in o and "OBLIGATOIRE manquant" not in o


def test_show_project_without_secondary_is_quiet():
    """Le cas de 46 projets sur 47 : rien de déclaré, rien d'exigé."""
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d), secondary=False)
        rc, o = _call(cli.cmd_show, cfg, _args(rm_id=9001))
        assert rc == 0 and "secondaires déclarés : aucun" in o
        assert "OBLIGATOIRE" not in o


def test_show_unknown_task():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))
        rc, o = _call(cli.cmd_show, cfg, _args(rm_id=9999))
        assert rc != 0 and "introuvable" in o


# ── pm-doctor ──────────────────────────────────────────────────────────────

def _doctor(cfg):
    errors, warns = [], []
    doctor.check_partner_links(cfg, doctor.load_overviews(cfg), errors, warns)
    return errors, warns


def test_doctor_flags_open_tasks_only():
    """`link.policy: required` ne réclame rien sur un ticket déjà fermé."""
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))
        errors, warns = _doctor(cfg)
        assert errors == []
        assert any("RM9001" in w for w in warns), warns
        assert not any("RM9002" in w for w in warns), "un ticket fermé ne se rattache plus"


def test_doctor_silent_once_linked_and_when_optional():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))
        _link(cfg, issue=1)
        assert _doctor(cfg) == ([], [])
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d), policy="optional")
        assert _doctor(cfg) == ([], [])
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d), secondary=False)
        assert _doctor(cfg) == ([], [])


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
