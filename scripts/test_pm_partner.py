#!/usr/bin/env python3
"""Tests offline de pm_partner — liens vers un gestionnaire partenaire (N0/RM2654).

Lancer : python3 scripts/test_pm_partner.py
Couvre : lecture des refs typés, résolution d'un secondaire déclaré (et refus des
autres), construction/validation d'un lien, unicité du miroir, gabarit de note
(fermé : rien d'interne), politique `link.policy: required`. Aucun réseau.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_partner
from pm_registry import Registry, RegistryError

PartnerError = pm_partner.PartnerError


def _reg():
    return Registry.from_config({
        "defaults": {"task": "redmine-ipro", "forge": "gitlab-ipro", "doc": "redmine-wiki"},
        "servers": {
            "redmine-ipro":   {"axis": "task", "type": "redmine", "url": "https://tasks.example"},
            "redmine-matnat": {"axis": "task", "type": "redmine", "url": "https://tasks.matnat"},
            "redmine-pisceen": {"axis": "task", "type": "redmine", "url": "https://rm.pisceen"},
            "gitlab-ipro":    {"axis": "forge", "type": "gitlab", "url": "https://gl.example"},
            "redmine-wiki":   {"axis": "doc", "type": "redmine_wiki", "url": "https://tasks.example"},
        },
    })


def _meta(policy="required", extra_secondary=False):
    task = [
        {"instance": "redmine-ipro", "role": "primary", "project_id": "proj"},
        {"instance": "redmine-matnat", "role": "secondary", "project_id": 12,
         "link": {"policy": policy}},
    ]
    if extra_secondary:
        task.append({"instance": "redmine-pisceen", "role": "secondary",
                     "link": {"policy": "optional"}})
    return {"providers": {"task": task}}


def _ref(instance="redmine-matnat", issue_id=1234, role="mirror"):
    return {"type": "partner_issue", "instance": instance, "issue_id": issue_id,
            "url": f"https://x/issues/{issue_id}", "role": role,
            "last_seen_journal_id": None, "added": "2026-08-12"}


# ── lecture ────────────────────────────────────────────────────────────────

def test_partner_refs_ignores_other_ref_types():
    fm = {"refs": [
        {"type": "commit", "sha": "abc123"},
        _ref(),
        "une chaîne libre",
        None,
    ]}
    refs = pm_partner.partner_refs(fm)
    assert len(refs) == 1 and refs[0]["issue_id"] == 1234


def test_partner_refs_on_empty_task():
    assert pm_partner.partner_refs({}) == []
    assert pm_partner.partner_refs({"refs": None}) == []
    assert pm_partner.partner_refs(None) == []


def test_find_and_mirror():
    fm = {"refs": [_ref(role="related"), _ref(instance="redmine-pisceen", issue_id=7,
                                              role="mirror")]}
    assert pm_partner.find_ref(fm, instance="redmine-pisceen")["issue_id"] == 7
    assert pm_partner.find_ref(fm, issue_id=1234)["instance"] == "redmine-matnat"
    assert pm_partner.find_ref(fm, instance="inconnue") is None
    assert pm_partner.mirror_ref(fm)["issue_id"] == 7
    assert pm_partner.mirror_ref({"refs": [_ref(role="related")]}) is None


# ── résolution du secondaire ───────────────────────────────────────────────

def test_resolve_secondary_ok():
    res = pm_partner.resolve_secondary(_meta(), _reg(), "redmine-matnat")
    assert res.instance.name == "redmine-matnat" and not res.is_primary


def test_resolve_secondary_refuses_the_primary():
    """Se rattacher à son propre primaire n'a pas de sens : ce serait soi-même."""
    try:
        pm_partner.resolve_secondary(_meta(), _reg(), "redmine-ipro")
        raise AssertionError("attendu PartnerError")
    except PartnerError as e:
        assert "secondaire" in str(e)


def test_resolve_secondary_without_any_declared():
    meta = {"redmine": {"project_id": "x"}}          # projet legacy, aucun secondaire
    try:
        pm_partner.resolve_secondary(meta, _reg(), "redmine-matnat")
        raise AssertionError("attendu PartnerError")
    except PartnerError as e:
        assert "aucun provider secondaire" in str(e)


def test_declared_secondaries():
    got = pm_partner.declared_secondaries(_meta(extra_secondary=True), _reg())
    assert sorted(got) == ["redmine-matnat", "redmine-pisceen"]


# ── construction & validation ──────────────────────────────────────────────

def test_build_ref_defaults_and_url():
    res = pm_partner.resolve_secondary(_meta(), _reg(), "redmine-matnat")
    ref = pm_partner.build_ref(res, "1234", role="mirror", added="2026-08-12")
    assert ref == {"type": "partner_issue", "instance": "redmine-matnat",
                   "issue_id": 1234, "url": "https://tasks.matnat/issues/1234",
                   "role": "mirror", "last_seen_journal_id": None, "added": "2026-08-12"}


def test_build_ref_rejects_bad_role_and_id():
    res = pm_partner.resolve_secondary(_meta(), _reg(), "redmine-matnat")
    for kw, why in (({"role": "clone"}, "role"), ({"issue_id": "abc"}, "issue_id")):
        try:
            pm_partner.build_ref(res, kw.get("issue_id", 1), role=kw.get("role", "related"))
            raise AssertionError(f"attendu PartnerError ({why})")
        except PartnerError:
            pass


def test_check_addition_rejects_duplicate_and_second_mirror():
    res = pm_partner.resolve_secondary(_meta(), _reg(), "redmine-matnat")
    fm = {"refs": [_ref(role="mirror")]}
    try:
        pm_partner.check_addition(fm, pm_partner.build_ref(res, 1234, role="related"))
        raise AssertionError("attendu PartnerError (doublon)")
    except PartnerError as e:
        assert "déjà présent" in str(e)
    try:
        pm_partner.check_addition(fm, pm_partner.build_ref(res, 9999, role="mirror"))
        raise AssertionError("attendu PartnerError (2e miroir)")
    except PartnerError as e:
        assert "miroir" in str(e)
    # un lien 'related' supplémentaire, lui, est légitime
    pm_partner.check_addition(fm, pm_partner.build_ref(res, 9999, role="related"))


def test_validate_refs_form_only():
    fm = {"refs": [
        {"type": "partner_issue", "issue_id": 1},                      # instance absente
        {"type": "partner_issue", "instance": "x", "issue_id": "abc"},  # id non entier
        {"type": "partner_issue", "instance": "y", "issue_id": 2, "role": "clone"},
    ]}
    errs = pm_partner.validate_refs(fm)
    assert len(errs) == 3
    assert any("instance" in e for e in errs) and any("issue_id" in e for e in errs)
    assert any("role invalide" in e for e in errs)


def test_validate_refs_duplicates_and_two_mirrors():
    fm = {"refs": [_ref(), _ref()]}          # même (instance, id) ET deux mirror
    errs = pm_partner.validate_refs(fm)
    assert any("double" in e for e in errs)
    assert any("mirror" in e for e in errs)


def test_validate_refs_checks_declaration_when_registry_given():
    fm = {"refs": [_ref(instance="redmine-inconnue")]}
    assert pm_partner.validate_refs(fm) == []                    # forme seule : OK
    errs = pm_partner.validate_refs(fm, _meta(), _reg())         # avec contexte : refusé
    assert len(errs) == 1 and "secondaire" in errs[0]


def test_validate_refs_accepts_a_valid_link():
    fm = {"refs": [_ref()]}
    assert pm_partner.validate_refs(fm, _meta(), _reg()) == []


# ── note de rattachement (gabarit fermé) ───────────────────────────────────

def test_link_note_is_closed():
    note = pm_partner.link_note(2626, "Gestion multiple de gestionnaires",
                                "https://tasks.example/issues/2626")
    assert note.startswith("Suivi iProspective : RM2626 — Gestion multiple")
    assert "https://tasks.example/issues/2626" in note
    # rien d'interne ne doit fuir : pas de chemin, d'hôte technique ni de branche
    for leak in ("/zfs/", "dev.local", "envs/", "git@", "REDMINE_"):
        assert leak not in note


def test_link_note_without_url_or_title():
    assert pm_partner.link_note(7, "") == "Suivi iProspective : RM7"
    assert "\n" not in pm_partner.link_note(7, "Titre")


def test_post_link_note_dry_run_does_not_touch_network():
    res = pm_partner.resolve_secondary(_meta(), _reg(), "redmine-matnat")
    note = pm_partner.post_link_note(res, 1234, 2626, "Titre", dry_run=True)
    assert note.startswith("Suivi iProspective : RM2626 — Titre")


# ── politique de rattachement ──────────────────────────────────────────────

def test_required_secondaries_and_missing_links():
    meta, reg = _meta(policy="required"), _reg()
    assert [r.instance.name for r in pm_partner.required_secondaries(meta, reg)] \
        == ["redmine-matnat"]
    assert pm_partner.missing_links({}, meta, reg) == ["redmine-matnat"]
    assert pm_partner.missing_links({"refs": [_ref()]}, meta, reg) == []


def test_optional_policy_never_reports_missing():
    meta, reg = _meta(policy="optional"), _reg()
    assert pm_partner.required_secondaries(meta, reg) == []
    assert pm_partner.missing_links({}, meta, reg) == []


def test_legacy_project_has_no_obligation():
    """Un projet sans bloc providers (l'immense majorité) n'est jamais inquiété."""
    meta, reg = {"redmine": {"project_id": "x"}}, _reg()
    assert pm_partner.missing_links({}, meta, reg) == []
    assert pm_partner.declared_secondaries(meta, reg) == {}


# ── pull (N1/RM2655) — lecture seule, journal uniquement ───────────────────

class _FakeProvider:
    """Provider distant en dur : aucun réseau, l'appel est enregistré."""
    def __init__(self, issue):
        self.issue, self.calls = issue, []

    def fetch_issue(self, issue_id, include=None):
        self.calls.append((issue_id, include))
        return self.issue


def _issue(journals=(), status="En cours", subject="Leur ticket"):
    return {"id": 1234, "subject": subject, "status": {"id": 2, "name": status},
            "journals": list(journals)}


def _journal(jid, notes="", author="Alice", details=None):
    return {"id": jid, "notes": notes, "user": {"name": author},
            "created_on": "2026-08-14T09:30:00Z", "details": details or []}


def test_extract_updates_filters_by_pointer():
    issue = _issue([_journal(1, "vieille"), _journal(2, "nouvelle"), _journal(3, "encore")])
    up = extract = pm_partner.extract_updates(issue, since_journal_id=1)
    assert [j["id"] for j in up["notes"]] == [2, 3]
    assert up["last_journal_id"] == 3


def test_extract_updates_ignores_field_only_journals():
    """Un journal sans commentaire (changement de champ) n'apprend rien : ignoré."""
    issue = _issue([_journal(1, ""), _journal(2, "   "),
                    _journal(3, "un vrai commentaire")])
    up = pm_partner.extract_updates(issue)
    assert [j["id"] for j in up["notes"]] == [3]
    # …mais le pointeur avance quand même, sinon on les relirait indéfiniment
    assert up["last_journal_id"] == 3


def test_extract_updates_status_change_detection():
    issue = _issue(status="Résolu")
    assert pm_partner.extract_updates(issue, last_status="En cours")["status_changed"]
    assert not pm_partner.extract_updates(issue, last_status="Résolu")["status_changed"]


def test_extract_updates_on_empty_issue():
    up = pm_partner.extract_updates({"status": {}}, since_journal_id=5)
    assert up["notes"] == [] and up["last_journal_id"] == 5
    assert up["status"] == "" and up["status_changed"] is False


def test_pull_enabled_defaults_and_switches():
    res = pm_partner.resolve_secondary(_meta(), _reg(), "redmine-matnat")
    assert pm_partner.pull_enabled(res) == (True, True)          # sync absent → permissif
    res2 = type(res)(res.instance, res.params, res.source, res.role, res.link,
                     {"pull": {"notes": True, "status": False}})
    assert pm_partner.pull_enabled(res2) == (True, False)
    res3 = type(res)(res.instance, res.params, res.source, res.role, res.link,
                     {"pull": False})
    assert pm_partner.pull_enabled(res3) == (False, False)


def test_pull_ref_respects_switches():
    res = pm_partner.resolve_secondary(_meta(), _reg(), "redmine-matnat")
    res_no_notes = type(res)(res.instance, res.params, res.source, res.role, res.link,
                             {"pull": {"notes": False}})
    prov = _FakeProvider(_issue([_journal(1, "coucou")], status="Résolu"))
    up, title = pm_partner.pull_ref(res_no_notes, _ref(), provider=prov)
    assert up["notes"] == [] and up["status"] == "Résolu"
    assert title == "Leur ticket"
    assert prov.calls == [(1234, "journals")]


def test_format_pull_entry_quotes_foreign_content():
    entry = pm_partner.format_pull_entry(
        _ref(), {"notes": [_journal(9, "ligne A\n\nligne B", author="Bob")],
                 "status": "Résolu", "status_changed": True, "last_journal_id": 9},
        remote_title="Leur ticket")
    assert "redmine-matnat#1234" in entry and "lecture seule" in entry
    assert "**Résolu**" in entry and "non répercuté" in entry
    # tout le contenu venu d'ailleurs est cité — on doit le distinguer d'un coup d'œil
    assert "> ligne A" in entry and "> ligne B" in entry
    assert "Note #9 — Bob" in entry


def test_format_pull_entry_empty_when_nothing_new():
    assert pm_partner.format_pull_entry(
        _ref(), {"notes": [], "status": "En cours", "status_changed": False,
                 "last_journal_id": 3}) == ""


def test_format_pull_entry_truncates_long_notes():
    long_note = "x" * 5000
    entry = pm_partner.format_pull_entry(
        _ref(), {"notes": [_journal(1, long_note)], "status": "", "status_changed": False,
                 "last_journal_id": 1})
    assert "tronqué, 5000 caractères" in entry and len(entry) < 3000


def test_apply_pointers_advances_only_on_change():
    ref = _ref()
    up = {"last_journal_id": 7, "status": "Résolu"}
    assert pm_partner.apply_pointers(ref, up) is True
    assert ref["last_seen_journal_id"] == 7 and ref["last_seen_status"] == "Résolu"
    assert pm_partner.apply_pointers(ref, up) is False           # idempotent


def test_pull_never_touches_task_state():
    """Garde-fou du lot : le pull ne produit RIEN qui ressemble à un état PM."""
    res = pm_partner.resolve_secondary(_meta(), _reg(), "redmine-matnat")
    prov = _FakeProvider(_issue([_journal(1, "note")], status="Fermé"))
    up, _ = pm_partner.pull_ref(res, _ref(), provider=prov)
    assert set(up) == {"notes", "last_journal_id", "status", "status_changed"}
    # le statut distant est un LIBELLÉ brut, jamais un statut NORMS
    assert up["status"] == "Fermé"


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
