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
    return _load_cfg(pm_dir), proj


def _load_cfg(pm_dir):
    """Charge la config PM d'un arbre de test, puis REDÉSARME le CF partenaire.

    Nettoyage APRÈS le load, jamais avant : `PMConfig.load` charge le `.env` de
    l'utilisateur (~/.config/mmi-pm/.env), qui peut porter
    REDMINE_CF_PARTNER_ISSUE_ID — un pop prématuré serait annulé par le load suivant.
    Sans ça, `push_cf` part sur le réseau et ces tests dépendent de la machine qui
    les exécute (RM2657). Tout rechargement de config dans un test passe par ici.
    """
    cfg = PMConfig.load(pm_dir)
    os.environ.pop("REDMINE_CF_PARTNER_ISSUE_ID", None)   # CF non configuré → aucun réseau
    return cfg


def _args(**kw):
    base = dict(no_commit=True, dry_run=False, no_remote_note=True, url=None,
                instance=None, issue=None, role="related", verbose=False, all=False,
                create_remote=False, remote_description="")
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


# ── pull (N1/RM2655) ───────────────────────────────────────────────────────

class _FakeProvider:
    def __init__(self, issue):
        self.issue = issue

    def fetch_issue(self, issue_id, include=None):
        return self.issue


@contextlib.contextmanager
def _remote(issue, fail=False):
    """Remplace l'accès distant — aucun réseau dans les tests de pull."""
    import pm_partner
    orig = pm_partner.fetch_remote
    if fail:
        def stub(resolution, issue_id, provider=None):
            raise RuntimeError("partenaire injoignable")
    else:
        def stub(resolution, issue_id, provider=None):
            return _FakeProvider(issue).fetch_issue(issue_id, include="journals")
    pm_partner.fetch_remote = stub
    try:
        yield
    finally:
        pm_partner.fetch_remote = orig


def _issue(journals=(), status="En cours"):
    return {"id": 1234, "subject": "Leur ticket", "status": {"name": status},
            "journals": [{"id": j, "notes": n, "user": {"name": "Alice"},
                          "created_on": "2026-08-14T09:30:00Z"} for j, n in journals]}


def _pull(cfg, rm=9001, **kw):
    return _call(cli.cmd_pull, cfg, _args(rm_id=rm, all=False, **kw))


def test_pull_appends_notes_and_advances_pointer():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        _link(cfg, issue=1234, role="mirror")
        with _remote(_issue([(1, "leur commentaire"), (2, "")], status="Résolu")):
            rc, o = _pull(cfg)
        assert rc == 0, o
        log = _log(proj)
        assert "redmine-matnat#1234" in log and "> leur commentaire" in log
        assert "**Résolu**" in log and "non répercuté" in log
        ref = _fm(proj)["refs"][0]
        assert ref["last_seen_journal_id"] == 2      # avance même sur un journal sans note
        assert ref["last_seen_status"] == "Résolu"


def test_pull_is_idempotent():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        _link(cfg, issue=1234)
        issue = _issue([(1, "une note")], status="En cours")
        with _remote(issue):
            _pull(cfg)
            before = _log(proj)
            rc, o = _pull(cfg)
        assert rc == 0 and "rien de neuf" in o
        assert _log(proj) == before, "un second pull ne doit rien réécrire"


def test_pull_never_changes_task_state():
    """Le partenaire informe, il ne décide pas : statut/priorité/assignation intacts."""
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        _link(cfg, issue=1234)
        before = {k: v for k, v in _fm(proj).items() if k != "refs"}
        with _remote(_issue([(1, "on a fermé de notre côté")], status="Fermé")):
            _pull(cfg)
        after = {k: v for k, v in _fm(proj).items() if k != "refs"}
        assert after["status"] == before["status"] == "en_cours"
        assert {k: v for k, v in after.items() if k != "updated"} == \
               {k: v for k, v in before.items() if k != "updated"}


def test_pull_dry_run_writes_nothing():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        _link(cfg, issue=1234)
        log_before = _log(proj)
        with _remote(_issue([(1, "une note")])):
            rc, o = _pull(cfg, dry_run=True)
        assert rc == 0 and "une note" in o
        assert _log(proj) == log_before
        assert _fm(proj)["refs"][0]["last_seen_journal_id"] is None


def test_pull_without_link_is_a_warning_not_a_failure():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))
        rc, o = _pull(cfg)
        assert rc == 0 and "aucun lien partenaire" in o


def test_pull_survives_unreachable_partner():
    """Accès révoqué / réseau coupé : avertissement, pas de plantage, rien de perdu."""
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        _link(cfg, issue=1234)
        with _remote(None, fail=True):
            rc, o = _pull(cfg)
        assert rc == 0 and "injoignable" in o
        assert _fm(proj)["refs"][0]["last_seen_journal_id"] is None


def test_pull_all_scans_open_linked_tasks_only():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        _link(cfg, rm=9001, issue=1234)
        with _remote(_issue([(1, "note pour le ticket ouvert")])):
            rc, o = _call(cli.cmd_pull, cfg, _args(rm_id=None, all=True))
        assert rc == 0, o
        assert "1 ticket(s) scanné(s)" in o and "1 avec du neuf" in o
        assert "note pour le ticket ouvert" in _log(proj, 9001)
        assert _log(proj, 9002) == ""          # ticket fermé : jamais réveillé


# ── push (N2/RM2656) ───────────────────────────────────────────────────────

@contextlib.contextmanager
def _capture_push(fail=False):
    """Intercepte l'envoi chez le partenaire. Retourne la liste des notes postées."""
    import pm_partner
    orig = pm_partner.push_status_note
    posted = []

    def stub(resolution, ref, rm_id, title, status, close_reason=None, message="",
             dry_run=False, provider=None):
        note = pm_partner.status_note(rm_id, title, status, close_reason, message)
        if fail:
            raise RuntimeError("partenaire injoignable")
        if not dry_run:
            posted.append((resolution.instance.name, ref.get("issue_id"), note))
        return note
    pm_partner.push_status_note = stub
    try:
        yield posted
    finally:
        pm_partner.push_status_note = orig


def _make_tree_push(tmp, on=("ferme",)):
    """Arbre dont le secondaire déclare des déclencheurs de push."""
    cfg, proj = _make_tree(tmp)
    meta = yaml.safe_load((proj / "meta.yml").read_text(encoding="utf-8"))
    meta["providers"]["task"][1]["sync"] = {"push": {"on": list(on)}}
    (proj / "meta.yml").write_text(yaml.safe_dump(meta, allow_unicode=True),
                                   encoding="utf-8")
    return cfg, proj


def _push(cfg, rm=9001, **kw):
    base = dict(rm_id=rm, status=None, message=None, force=False, quiet=False)
    base.update(kw)
    return _call(cli.cmd_push, cfg, _args(**base))


def test_push_is_inert_without_declared_triggers():
    """Défaut du système : rien ne part chez un tiers tant que ce n'est pas déclaré."""
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))          # secondaire SANS sync.push
        _link(cfg, issue=1234)
        with _capture_push() as posted:
            rc, o = _push(cfg, status="ferme")
        assert rc == 0 and posted == []
        assert "aucun secondaire n'annonce" in o


def test_push_posts_when_status_is_declared():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree_push(Path(d), on=("ferme", "a_tester_demandeur"))
        _link(cfg, issue=1234)
        with _capture_push() as posted:
            rc, o = _push(cfg, status="ferme")
        assert rc == 0, o
        assert len(posted) == 1 and posted[0][0] == "redmine-matnat"
        assert "Suivi iProspective : RM9001" in posted[0][2]
        assert "terminé" in posted[0][2]
        assert "poussée chez" in _log(proj)      # trace locale de ce qui est sorti


def test_push_ignores_non_declared_status():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree_push(Path(d), on=("ferme",))
        _link(cfg, issue=1234)
        with _capture_push() as posted:
            _push(cfg, status="en_cours")
        assert posted == []


def test_push_force_overrides_triggers():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree_push(Path(d), on=())
        _link(cfg, issue=1234)
        with _capture_push() as posted:
            _push(cfg, status="en_cours", force=True)
        assert len(posted) == 1 and "pris en charge" in posted[0][2]


def test_push_dry_run_posts_nothing():
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree_push(Path(d))
        _link(cfg, issue=1234)
        log_before = _log(proj)
        with _capture_push() as posted:
            rc, o = _push(cfg, status="ferme", dry_run=True)
        assert rc == 0 and posted == [] and "Suivi iProspective" in o
        assert _log(proj) == log_before


def test_push_survives_unreachable_partner():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree_push(Path(d))
        _link(cfg, issue=1234)
        with _capture_push(fail=True):
            rc, o = _push(cfg, status="ferme")
        assert rc == 0 and "non postée" in o and "injoignable" in o


def test_push_quiet_says_nothing_when_there_is_nothing_to_do():
    """Le hook de transition appelle `push --quiet` : il ne doit rien afficher ni
    échouer sur les 46 projets sans partenaire, sinon chaque changement de statut
    se met à bavarder."""
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))                    # aucun lien, aucun push déclaré
        with _capture_push() as posted:
            rc, o = _push(cfg, status="ferme", quiet=True)
        assert rc == 0 and posted == [] and o.strip() == "", o


def test_push_without_any_link_is_quiet():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree_push(Path(d))
        with _capture_push() as posted:
            rc, o = _push(cfg, status="ferme")
        assert rc == 0 and posted == [] and "aucun lien partenaire" in o


def test_link_create_remote_creates_then_links():
    import pm_partner
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        meta = yaml.safe_load((proj / "meta.yml").read_text(encoding="utf-8"))
        meta["providers"]["task"][1]["create"] = {"tracker_id": 3}
        (proj / "meta.yml").write_text(yaml.safe_dump(meta, allow_unicode=True),
                                       encoding="utf-8")
        cfg = _load_cfg(Path(d) / "pm")
        orig = pm_partner.create_remote_issue
        pm_partner.create_remote_issue = lambda res, subject, description="", provider=None: 4242
        try:
            rc, o = _call(cli.cmd_link, cfg,
                          _args(rm_id=9001, instance="redmine-matnat", issue=None,
                                role="mirror", create_remote=True, remote_description=""))
        finally:
            pm_partner.create_remote_issue = orig
        assert rc == 0, o
        refs = _fm(proj)["refs"]
        assert len(refs) == 1 and refs[0]["issue_id"] == 4242


def test_link_create_remote_conflicts_with_issue():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))
        rc, o = _call(cli.cmd_link, cfg,
                      _args(rm_id=9001, instance="redmine-matnat", issue=1,
                            create_remote=True, remote_description=""))
        assert rc != 0 and "exclusifs" in o


def test_link_without_issue_nor_create_remote_fails():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))
        rc, o = _call(cli.cmd_link, cfg,
                      _args(rm_id=9001, instance="redmine-matnat", issue=None))
        assert rc != 0 and "--issue" in o


# ── référence externe (CF) et son rattrapage — RM2657 ──────────────────────

@contextlib.contextmanager
def _cf(activated=True, cf_id="9"):
    """Simule le CF Redmine : `activated=False` reproduit le piège — Redmine répond
    200 mais ignore la valeur quand le champ n'est pas activé pour le projet."""
    store = {}
    orig = cli.get_task_provider          # la CLI a importé le symbole : patcher ICI

    class _P:
        def update_fields(self, rm_id, custom_fields=None, **kw):
            if activated:
                store[rm_id] = custom_fields[0]["value"]
            return True, ""                     # Redmine accepte dans les deux cas

        def fetch_issue(self, rm_id, include=None):
            cfs = ([{"id": int(cf_id), "name": "Réf ticket outil externe",
                     "value": store.get(rm_id, "")}] if activated else [])
            return {"id": rm_id, "project": {"name": "site"}, "custom_fields": cfs}

    cli.get_task_provider = lambda *a, **k: _P()
    old = os.environ.get("REDMINE_CF_PARTNER_ISSUE_ID")
    os.environ["REDMINE_CF_PARTNER_ISSUE_ID"] = cf_id
    try:
        yield store
    finally:
        cli.get_task_provider = orig
        if old is None:
            os.environ.pop("REDMINE_CF_PARTNER_ISSUE_ID", None)
        else:
            os.environ["REDMINE_CF_PARTNER_ISSUE_ID"] = old


def test_cf_gets_a_compact_reference():
    """16 caractères max : c'est `matnat#5576` qui part, pas l'URL."""
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))
        with _cf() as store:
            _link(cfg, issue=5576, role="mirror")
        assert store[9001] == "matnat#5576"
        assert len(store[9001]) <= 16


def test_cf_not_activated_is_reported_not_silently_ok():
    """Le piège : HTTP 200 sans effet ne doit PAS passer pour un succès."""
    with tempfile.TemporaryDirectory() as d:
        cfg, proj = _make_tree(Path(d))
        with _cf(activated=False):
            rc, o = _link(cfg, issue=5576)
        assert rc == 0                                   # le lien local est posé
        assert "non activé pour le projet" in o
        assert len(_fm(proj)["refs"]) == 1


def test_sync_cf_repairs_existing_links():
    """Après activation du champ côté admin, on rattrape sans délier/relier."""
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))
        with _cf(activated=False):
            _link(cfg, issue=5576, role="mirror")        # CF non posé à l'époque
        with _cf() as store:
            rc, o = _call(cli.cmd_sync_cf, cfg, _args(rm_id=9001, all=False))
        assert rc == 0 and store[9001] == "matnat#5576"
        assert "1 ticket(s) à jour" in o


def test_sync_cf_all_skips_unlinked_and_closed():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))
        with _cf(activated=False):
            _link(cfg, issue=5576)
        with _cf() as store:
            rc, o = _call(cli.cmd_sync_cf, cfg, _args(rm_id=None, all=True))
        assert rc == 0 and list(store) == [9001]         # 9002 est fermé → ignoré
        assert "1 ticket(s) à jour" in o


def test_unlink_clears_the_reference():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _make_tree(Path(d))
        with _cf() as store:
            _link(cfg, issue=5576)
            assert store[9001] == "matnat#5576"
            _call(cli.cmd_unlink, cfg, _args(rm_id=9001, instance="redmine-matnat",
                                             issue=5576))
            assert store[9001] == ""                     # plus de lien → champ vidé


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
