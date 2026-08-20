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
            "redmine-matnat": {"axis": "task", "type": "redmine", "url": "https://tasks.matnat",
                               "slug": "matnat"},
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


# ── push (N2/RM2656) — écriture pauvre, inerte par défaut ──────────────────

def _with_sync(res, sync):
    return type(res)(res.instance, res.params, res.source, res.role, res.link, sync)


def _sec(sync=None, params=None):
    res = pm_partner.resolve_secondary(_meta(), _reg(), "redmine-matnat")
    if params is not None:
        res = type(res)(res.instance, params, res.source, res.role, res.link, res.sync)
    return _with_sync(res, sync) if sync is not None else res


def test_push_is_inert_without_configuration():
    """Sans `sync.push.on`, le PM n'écrit JAMAIS chez un tiers. C'est le défaut."""
    assert pm_partner.push_triggers(_sec()) == []
    assert pm_partner.should_push(_sec(), "ferme") is False
    assert pm_partner.push_triggers(_sec({"push": True})) == []   # conf floue ≠ tout pousser


def test_push_triggers_declared():
    res = _sec({"push": {"on": ["a_tester_demandeur", "ferme"]}})
    assert pm_partner.should_push(res, "ferme") is True
    assert pm_partner.should_push(res, "en_cours") is False
    assert pm_partner.should_push(res, "") is False


def test_status_label_is_readable_by_a_third_party():
    """Le partenaire ne connaît pas notre machine d'états : pas de jargon NORMS."""
    assert pm_partner.status_label("a_tester_demandeur") == "livré, en attente de validation"
    assert pm_partner.status_label("ferme") == "terminé"
    assert pm_partner.status_label("ferme", "abandonne") == "abandonné"
    assert pm_partner.status_label("ferme", "wont_fix") == "clos sans suite"
    # statut inconnu : on rend la valeur brute plutôt que d'inventer
    assert pm_partner.status_label("bidon") == "bidon"


def test_status_note_is_closed():
    note = pm_partner.status_note(2626, "Gestion multiple de gestionnaires",
                                  "a_tester_demandeur")
    assert note.startswith("Suivi iProspective : RM2626 — Gestion multiple")
    assert "livré, en attente de validation" in note
    # aucune fuite interne, et surtout PAS d'URL de notre Redmine (inaccessible pour eux)
    for leak in ("/zfs/", "dev.local", "envs/", "git@", "REDMINE_", "http://", "https://",
                 "a_tester_demandeur"):
        assert leak not in note, leak


def test_status_note_with_human_message():
    note = pm_partner.status_note(7, "Titre", "ferme", "resolu",
                                  message="Livré en prod ce matin.")
    assert "État : terminé." in note and note.endswith("Livré en prod ce matin.")


def test_push_status_note_dry_run_does_not_touch_network():
    note = pm_partner.push_status_note(_sec(), _ref(), 2626, "Titre", "ferme",
                                       dry_run=True)
    assert "Suivi iProspective : RM2626" in note


def test_push_status_note_posts_only_a_note():
    """Écriture pauvre : add_note et rien d'autre (ni statut, ni CF, ni time entry)."""
    class _P:
        def __init__(self): self.calls = []
        def add_note(self, issue_id, note): self.calls.append(("add_note", issue_id, note))
        def __getattr__(self, name):
            raise AssertionError(f"le push ne doit appeler que add_note (vu : {name})")
    p = _P()
    pm_partner.push_status_note(_sec(), _ref(), 2626, "Titre", "ferme", provider=p)
    assert len(p.calls) == 1 and p.calls[0][0] == "add_note" and p.calls[0][1] == 1234


def test_create_remote_requires_explicit_tracker():
    """Les ids de tracker ne sont pas portables : pas de devinette silencieuse."""
    try:
        pm_partner.create_remote_issue(_sec(params={"project_id": 12}), "Sujet")
        raise AssertionError("attendu PartnerError (tracker_id absent)")
    except PartnerError as e:
        assert "tracker_id" in str(e)


def test_create_remote_passes_declared_ids_and_no_ia_tag():
    class _P:
        def __init__(self): self.kw = None
        def create_issue(self, **kw):
            self.kw = kw
            return {"id": 4242}
    p = _P()
    res = _sec(params={"project_id": 12, "create": {"tracker_id": 3, "priority_id": 4}})
    assert pm_partner.create_remote_issue(res, "Sujet", "Desc", provider=p) == 4242
    assert p.kw["project_id"] == 12 and p.kw["tracker_id"] == 3
    assert p.kw["priority_id"] == 4 and p.kw["subject"] == "Sujet"
    # le CF « IA » est une notion iProspective — ne pas l'imposer chez un tiers
    assert p.kw["tag_ia"] is False


# ── slug du gestionnaire + référence compacte (RM2657) ─────────────────────

def test_slug_declared_wins():
    """`slug:` déclaré dans le registre — stable si l'instance est renommée."""
    inst = _reg().get("redmine-matnat")
    assert pm_partner.instance_slug(inst) == "matnat"


def test_slug_falls_back_to_deduction():
    """Sans `slug:` déclaré, on retire le préfixe de type — rien à configurer."""
    inst = _reg().get("redmine-pisceen")
    assert not inst.options.get("slug")
    assert pm_partner.instance_slug(inst) == "pisceen"
    assert pm_partner.instance_slug("redmine-pisceen") == "pisceen"
    assert pm_partner.instance_slug("jira-acme") == "acme"
    assert pm_partner.instance_slug("interne") == "interne"


def test_slug_by_name_needs_the_registry():
    """Un nom seul ne porte pas la déclaration : le registre la retrouve."""
    reg = _reg()
    assert pm_partner.instance_slug("redmine-matnat") == "matnat"       # déduit, ici identique
    assert pm_partner.instance_slug("redmine-matnat", reg) == "matnat"  # déclaré


def test_slug_declared_differs_from_deduction():
    """Cas qui prouve que la déclaration prime réellement sur la déduction."""
    reg = Registry.from_config({
        "defaults": {"task": "redmine-ipro"},
        "servers": {
            "redmine-ipro": {"axis": "task", "type": "redmine", "url": "https://x"},
            "redmine-vieux-nom": {"axis": "task", "type": "redmine", "url": "https://y",
                                  "slug": "mn"},
        },
    })
    assert pm_partner.instance_slug("redmine-vieux-nom") == "vieux-nom"      # sans registre
    assert pm_partner.instance_slug("redmine-vieux-nom", reg) == "mn"        # déclaré
    assert pm_partner.cf_ref(_ref(instance="redmine-vieux-nom", issue_id=42), reg) == "mn#42"


def test_slug_unknown_instance_does_not_raise():
    """Une instance absente du registre ne doit pas casser un recalage de CF."""
    assert pm_partner.cf_ref(_ref(instance="redmine-parti", issue_id=7), _reg()) == "parti#7"


def test_cf_ref_is_capped():
    reg = _reg()
    long_ref = _ref(instance="redmine-un-nom-de-partenaire-tres-long", issue_id=123456)
    assert len(pm_partner.cf_ref(long_ref, reg)) <= pm_partner.CF_REF_MAX


def test_cf_ref_without_registry_is_unchanged():
    """Rétro-compat : les appelants qui ne passent pas le registre gardent l'ancien rendu."""
    assert pm_partner.cf_ref(_ref(issue_id=5576)) == "matnat#5576"


# ── URL de NOTRE ticket dans la note au partenaire (RM2657) ────────────────

def test_local_issue_url_uses_the_primary():
    url = pm_partner.local_issue_url(2618, _meta(), _reg())
    assert url == "https://tasks.example/issues/2618"


def test_local_issue_url_empty_without_registry():
    """Non résoluble → note postée sans lien, jamais d'échec."""
    assert pm_partner.local_issue_url(2618, _meta(), None) == ""


def test_link_note_carries_the_url():
    note = pm_partner.link_note(2618, "Titre du ticket",
                                "https://tasks.example/issues/2618")
    assert note.splitlines() == ["Suivi iProspective : RM2618 — Titre du ticket",
                                 "https://tasks.example/issues/2618"]


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
