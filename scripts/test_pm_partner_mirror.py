#!/usr/bin/env python3
"""Tests offline du miroir d'états partenaire (N3, RM2746).

Lancer : python3 scripts/test_pm_partner_mirror.py
Couvre : inertie par défaut, déclaration projet vs case cochée sur le ticket, table de
correspondance déclarative (forme courte et riche), constat de divergence sans réseau,
propositions entrantes jamais appliquées, refus d'écrire un statut sans id. Aucun réseau.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_partner
from pm_registry import Instance, Registry, Resolution

PartnerError = pm_partner.PartnerError
INST = Instance("redmine-matnat", "task", "redmine", "https://tasks.matnat")

# Table réaliste : leur workflow est plus court que le nôtre — plusieurs de nos
# statuts retombent sur « Résolu », ce qui est justement la source d'ambiguïté.
MAP = {"en_cours": {"label": "En cours", "id": 2},
       "a_tester_demandeur": {"label": "Résolu", "id": 3},
       "a_mep": "Résolu",
       "ferme": {"label": "Fermé", "id": 5}}


def _res(mirror=None, **sync):
    if mirror is not None:
        sync["mirror"] = mirror
    return Resolution(INST, sync=sync, role="secondary")


def _ref(seen=None, issue_id=5576):
    return {"type": "partner_issue", "instance": "redmine-matnat", "issue_id": issue_id,
            "url": f"https://tasks.matnat/issues/{issue_id}", "role": "mirror",
            "last_seen_status": seen, "added": "2026-09-04"}


def _fm(status="en_cours", coched=None):
    fm = {"redmine_id": 2746, "status": status, "refs": [_ref()]}
    if coched is not None:
        fm["state_mirror"] = coched
    return fm


def _reg():
    return Registry.from_config({
        "defaults": {"task": "redmine-ipro"},
        "servers": {
            "redmine-ipro":   {"axis": "task", "type": "redmine", "url": "https://tasks.ipro"},
            "redmine-matnat": {"axis": "task", "type": "redmine", "url": "https://tasks.matnat",
                               "slug": "matnat"},
        }})


def _meta(mirror=None):
    sec = {"instance": "redmine-matnat", "role": "secondary", "project_id": 12}
    if mirror is not None:
        sec["sync"] = {"mirror": mirror}
    return {"providers": {"task": [
        {"instance": "redmine-ipro", "role": "primary", "project_id": "p"}, sec]}}


# ── inertie par défaut ─────────────────────────────────────────────────────

def test_defaut_inerte_aucune_declaration():
    """Un projet qui ne déclare rien ne change pas de comportement."""
    res = _res()
    assert pm_partner.effective_regimes(_fm(), res) == []
    assert pm_partner.state_divergence(_fm(), _ref("Fermé"), res) is None
    assert pm_partner.incoming_proposal(_fm(), _ref("Fermé"), res) is None
    assert pm_partner.outgoing_target(_fm(), _ref("Fermé"), res) is None


def test_defaut_inerte_formes_vides():
    for m in (None, False, {}, [], ""):
        cfg = pm_partner.mirror_config(_res(mirror=m))
        assert cfg == {"regimes": [], "map": {}, "map_in": {}}, m


def test_mirror_true_donne_le_socle_pas_l_ecriture():
    """`mirror: true` n'active jamais une écriture chez un tiers par effet de bord."""
    regimes = pm_partner.effective_regimes(_fm(), _res(mirror=True))
    assert regimes == ["signal"]
    assert "outgoing" not in regimes


# ── déclaration : projet, ticket, cumul ────────────────────────────────────

def test_declaration_projet_liste_et_forme_riche():
    assert pm_partner.mirror_config(_res(mirror=["signal", "outgoing"]))["regimes"] \
        == ["signal", "outgoing"]
    cfg = pm_partner.mirror_config(_res(mirror={"regimes": ["incoming"], "map": MAP}))
    assert cfg["regimes"] == ["incoming"] and cfg["map"]["ferme"]["id"] == 5


def test_signal_est_le_socle_implicite():
    """Piloter un état sans savoir le comparer n'aurait pas de sens."""
    for declared in (["outgoing"], ["incoming"], ["outgoing", "incoming"]):
        assert pm_partner.effective_regimes(_fm(), _res(mirror=declared))[0] == "signal"


def test_ticket_coche_remplace_le_projet():
    """La case cochée sur le ticket ne doit pas se faire recouvrir par le projet."""
    res = _res(mirror={"regimes": ["signal", "outgoing"], "map": MAP})
    assert "outgoing" not in pm_partner.effective_regimes(_fm(coched=["signal"]), res)
    assert "incoming" in pm_partner.effective_regimes(_fm(coched=["incoming"]), res)


def test_ticket_none_desactive_sans_heriter():
    res = _res(mirror={"regimes": ["signal", "outgoing"], "map": MAP})
    assert pm_partner.effective_regimes(_fm(coched=["none"]), res) == []
    assert pm_partner.effective_regimes(_fm(coched="none"), res) == []


def test_ticket_vide_herite_du_projet():
    res = _res(mirror=["signal"])
    for coched in (None, [], ""):
        assert pm_partner.effective_regimes(_fm(coched=coched), res) == ["signal"]


def test_regime_inconnu_ignore_mais_rapporte():
    """Refuser tout le bloc pour une valeur inconnue désactiverait le miroir en silence."""
    res = _res(mirror=["signal", "téléportation"])
    assert pm_partner.effective_regimes(_fm(), res) == ["signal"]
    assert pm_partner.unknown_regimes(["signal", "téléportation"]) == ["téléportation"]
    assert pm_partner.unknown_regimes(["none", "signal"]) == []


def test_mirror_est_l_alias_des_deux_sens():
    """Le CF 35 est mono-valeur : `Mirror` est le seul moyen d'y dire « les deux sens »."""
    res = _res(mirror={"map": MAP})
    assert pm_partner.effective_regimes(_fm(coched=["mirror"]), res) \
        == ["signal", "outgoing", "incoming"]
    assert pm_partner.effective_regimes(_fm(coched=["Mirror"]), res) \
        == ["signal", "outgoing", "incoming"]


def test_mirror_declarable_aussi_au_projet():
    assert pm_partner.mirror_config(_res(mirror=["mirror"]))["regimes"] \
        == ["signal", "outgoing", "incoming"]


def test_mirror_n_est_pas_un_regime_inconnu():
    assert pm_partner.unknown_regimes(["mirror"]) == []


def test_cf_mono_valeur_une_chaine_suffit():
    """`state_mirror` peut arriver en chaîne nue : le CF ne coche qu'une valeur."""
    res = _res(mirror={"map": MAP})
    assert pm_partner.effective_regimes(_fm(coched="mirror"), res) \
        == ["signal", "outgoing", "incoming"]
    assert pm_partner.effective_regimes(_fm(coched="signal"), res) == ["signal"]


def test_saisie_tolerante_casse_et_espaces():
    assert pm_partner.effective_regimes(_fm(coched=[" Signal ", "OUTGOING"]),
                                        _res()) == ["signal", "outgoing"]


# ── table de correspondance ────────────────────────────────────────────────

def test_table_forme_courte_et_riche():
    cfg = pm_partner.mirror_config(_res(mirror={"regimes": ["signal"], "map": MAP}))
    assert pm_partner.remote_status(cfg, "ferme") == ("Fermé", 5)
    assert pm_partner.remote_status(cfg, "a_mep") == ("Résolu", None)
    assert pm_partner.remote_status(cfg, "en_pause") == ("", None)


def test_table_jamais_en_dur_dans_le_code():
    """Aucune correspondance implicite : sans table déclarée, rien n'est mappé."""
    cfg = pm_partner.mirror_config(_res(mirror=["signal"]))
    for status in ("en_cours", "ferme", "a_mep", "a_tester_demandeur"):
        assert pm_partner.remote_status(cfg, status) == ("", None), status


def test_gaps_liste_les_statuts_absents():
    cfg = pm_partner.mirror_config(_res(mirror={"regimes": ["signal"], "map": MAP}))
    assert pm_partner.mirror_gaps(cfg, ("en_cours", "en_pause", "a_corriger")) \
        == ["en_pause", "a_corriger"]


# ── sens inverse : leur libellé → un statut NORMS ──────────────────────────

def test_inversion_univoque():
    cfg = pm_partner.mirror_config(_res(mirror={"regimes": ["incoming"], "map": MAP}))
    assert pm_partner.norms_status(cfg, "Fermé") == "ferme"
    assert pm_partner.norms_status(cfg, "  en   cours ") == "en_cours"


def test_inversion_ambigue_ne_devine_pas():
    """« Résolu » vise deux de nos statuts : proposer au hasard serait pire que rien."""
    cfg = pm_partner.mirror_config(_res(mirror={"regimes": ["incoming"], "map": MAP}))
    assert pm_partner.norms_status(cfg, "Résolu") is None
    assert pm_partner.mirror_ambiguities(cfg) == {"Résolu": ["a_mep", "a_tester_demandeur"]}


def test_map_in_tranche_l_ambiguite():
    cfg = pm_partner.mirror_config(_res(mirror={
        "regimes": ["incoming"], "map": MAP, "map_in": {"a_mep": "Résolu"}}))
    assert pm_partner.norms_status(cfg, "Résolu") == "a_mep"
    assert pm_partner.mirror_ambiguities(cfg) == {}


def test_libelle_inconnu_ne_correspond_a_rien():
    cfg = pm_partner.mirror_config(_res(mirror={"regimes": ["incoming"], "map": MAP}))
    assert pm_partner.norms_status(cfg, "En attente client") is None


# ── signalement (régime signal) ────────────────────────────────────────────

def test_divergence_constatee_sans_reseau():
    res = _res(mirror={"regimes": ["signal"], "map": MAP})
    div = pm_partner.state_divergence(_fm("ferme"), _ref("En cours"), res)
    assert div["expected"] == "Fermé" and div["seen"] == "En cours"
    assert div["status"] == "ferme" and div["issue_id"] == 5576


def test_aucune_divergence_si_aligne_meme_casse_differente():
    res = _res(mirror={"regimes": ["signal"], "map": MAP})
    assert pm_partner.state_divergence(_fm("ferme"), _ref("fermé"), res) is None
    assert pm_partner.state_divergence(_fm("ferme"), _ref(" Fermé  "), res) is None


def test_aucune_divergence_sans_pull_prealable():
    """Statut distant jamais observé : on ne sait rien, on ne dit rien."""
    res = _res(mirror={"regimes": ["signal"], "map": MAP})
    assert pm_partner.state_divergence(_fm("ferme"), _ref(None), res) is None
    assert pm_partner.state_divergence(_fm("ferme"), _ref(""), res) is None


def test_statut_non_mappe_est_un_trou_pas_une_divergence():
    res = _res(mirror={"regimes": ["signal"], "map": MAP})
    assert pm_partner.state_divergence(_fm("en_pause"), _ref("En cours"), res) is None


def test_pas_de_signalement_si_regime_absent():
    res = _res(mirror={"regimes": [], "map": MAP})
    assert pm_partner.state_divergence(_fm("ferme"), _ref("En cours"), res) is None


# ── entrant : proposer, jamais appliquer ───────────────────────────────────

def test_proposition_entrante_ne_touche_pas_le_statut():
    fm = _fm("en_cours", coched=["incoming"])
    res = _res(mirror={"regimes": ["incoming"], "map": MAP})
    prop = pm_partner.incoming_proposal(fm, _ref("Fermé"), res)
    assert prop["from"] == "en_cours" and prop["to"] == "ferme"
    assert fm["status"] == "en_cours", "la proposition ne doit RIEN appliquer"


def test_aucune_proposition_hors_regime_entrant():
    res = _res(mirror={"regimes": ["signal", "outgoing"], "map": MAP})
    assert pm_partner.incoming_proposal(_fm("en_cours"), _ref("Fermé"), res) is None


def test_aucune_proposition_si_deja_dans_l_etat():
    res = _res(mirror={"regimes": ["incoming"], "map": MAP})
    assert pm_partner.incoming_proposal(_fm("ferme"), _ref("Fermé"), res) is None


def test_aucune_proposition_si_correspondance_ambigue():
    res = _res(mirror={"regimes": ["incoming"], "map": MAP})
    assert pm_partner.incoming_proposal(_fm("en_cours"), _ref("Résolu"), res) is None


# ── sortant : écrire chez le tiers ─────────────────────────────────────────

def test_sortant_cible_le_statut_mappe():
    res = _res(mirror={"regimes": ["outgoing"], "map": MAP})
    assert pm_partner.outgoing_target(_fm("ferme"), _ref("En cours"), res) \
        == {"id": 5, "label": "Fermé"}


def test_sortant_muet_si_deja_dans_l_etat():
    res = _res(mirror={"regimes": ["outgoing"], "map": MAP})
    assert pm_partner.outgoing_target(_fm("ferme"), _ref("Fermé"), res) is None


def test_sortant_exige_un_id_et_le_dit():
    """L'API pose un statut par son id : un libellé seul serait un appel sans effet."""
    res = _res(mirror={"regimes": ["outgoing"], "map": MAP})
    try:
        pm_partner.outgoing_target(_fm("a_mep"), _ref("En cours"), res)
    except PartnerError as e:
        assert "id" in str(e) and "a_mep" in str(e)
    else:
        raise AssertionError("un libellé sans id doit être refusé explicitement")


def test_sortant_muet_hors_regime():
    res = _res(mirror={"regimes": ["signal"], "map": MAP})
    assert pm_partner.outgoing_target(_fm("ferme"), _ref("En cours"), res) is None


def test_push_state_dry_run_n_ecrit_pas():
    calls = []

    class P:
        def update_fields(self, issue_id, **kw):
            calls.append((issue_id, kw))

    res = _res(mirror={"regimes": ["outgoing"], "map": MAP})
    got = pm_partner.push_state(res, _ref("En cours"), _fm("ferme"),
                                provider=P(), dry_run=True)
    assert got == {"id": 5, "label": "Fermé"} and calls == []


def test_push_state_pose_le_statut():
    calls = []

    class P:
        def update_fields(self, issue_id, **kw):
            calls.append((issue_id, kw))

    res = _res(mirror={"regimes": ["outgoing"], "map": MAP})
    pm_partner.push_state(res, _ref("En cours"), _fm("ferme"), provider=P())
    assert calls == [(5576, {"status_id": 5})]


def test_push_state_refuse_un_backend_en_lecture_seule():
    class ReadOnly:
        pass

    res = _res(mirror={"regimes": ["outgoing"], "map": MAP})
    try:
        pm_partner.push_state(res, _ref("En cours"), _fm("ferme"), provider=ReadOnly())
    except PartnerError as e:
        assert "écrire" in str(e)
    else:
        raise AssertionError("un backend sans update_fields doit être refusé")


# ── agrégat pour pm-doctor ─────────────────────────────────────────────────

def test_rapport_agrege_divergence_et_proposition():
    fm = {"redmine_id": 2746, "status": "ferme",
          "refs": [dict(_ref("En cours"))], "state_mirror": ["signal", "incoming"]}
    rep = pm_partner.mirror_report(fm, _meta(mirror={"map": MAP}), _reg())
    assert len(rep["divergences"]) == 1
    assert rep["proposals"][0]["to"] == "en_cours"


def test_rapport_vide_si_projet_muet():
    fm = {"redmine_id": 2746, "status": "ferme", "refs": [dict(_ref("En cours"))]}
    rep = pm_partner.mirror_report(fm, _meta(), _reg())
    assert rep["divergences"] == [] and rep["proposals"] == []


def test_rapport_ignore_un_lien_vers_une_instance_non_declaree():
    """validate_refs le signale déjà : le redire ici ferait lire deux problèmes."""
    fm = {"redmine_id": 2746, "status": "ferme", "state_mirror": ["signal"],
          "refs": [{"type": "partner_issue", "instance": "redmine-inconnu",
                    "issue_id": 1, "last_seen_status": "X"}]}
    rep = pm_partner.mirror_report(fm, _meta(mirror={"map": MAP}), _reg())
    assert rep["divergences"] == []


# ── non-régression N0→N2 ───────────────────────────────────────────────────

def test_le_push_de_notes_n2_reste_inerte():
    """Le miroir d'états ne doit pas activer la note de suivi (N2), et inversement."""
    res = _res(mirror={"regimes": ["signal", "outgoing"], "map": MAP})
    assert pm_partner.push_triggers(res) == []
    assert not pm_partner.should_push(res, "ferme")


def test_pull_reste_permissif_sans_declaration_mirror():
    res = _res(mirror={"regimes": ["outgoing"], "map": MAP})
    assert pm_partner.pull_enabled(res) == (True, True)


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
