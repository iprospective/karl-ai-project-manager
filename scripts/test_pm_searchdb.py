#!/usr/bin/env python3
"""Tests offline de pm_searchdb — l'index de requêtage (RM3128, renommé par RM3143).

Lancer : python3 scripts/test_pm_index.py
L'index est une PROJECTION du Markdown : ces tests vérifient surtout qu'il ne peut pas
devenir une seconde source de vérité — reconstruction fidèle, incrément qui ne retouche
que ce qui a bougé, fiches disparues retirées, et divergence AVOUÉE quand il est en
retard. Un index qui ne sait pas dire qu'il ment est pire qu'un index absent.
Aucun réseau, tout en dossier temporaire.
"""
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_searchdb as pm_index

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis")

from pm_paths import PMConfig

REAL_CONFIG = HERE.parent / "pm.config.yml"

SHEET = """---
schema_version: 1.11.0
redmine_id: {rm}
title: {title}
type: feature
status: {status}
priority: normal
parent_task: {parent}
tags:
- {tag}
relates:
- 9999
created: '2026-09-14'
updated: 2026-09-14T10:00
---

## Contexte

{body}
"""


def _tree(tmp, sheets, think=None):
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
    (proj / "meta.yml").write_text("{}\n", encoding="utf-8")
    for rm, title, status, body, tag, parent in sheets:
        (proj / "tasks" / f"RM{rm}_t.md").write_text(
            SHEET.format(rm=rm, title=title, status=status, body=body, tag=tag,
                         parent=parent), encoding="utf-8")
    for rm, txt in (think or {}).items():
        (proj / "tasks" / f"RM{rm}_t.think.md").write_text(txt, encoding="utf-8")
    return PMConfig.load(pm_dir), proj / "tasks"


S = [(101, "Index sqlite", "nouveau", "une base de requetage", "infra", 100),
     (102, "Cockpit recherche", "ferme", "un champ unique", "front", "null"),
     (103, "Autre sujet", "en_cours", "sans rapport", "infra", "null")]


# ── lecture d'une fiche (pur) ──────────────────────────────────────────────

def test_parse_sheet_lit_champs_listes_et_corps():
    d = pm_index.parse_sheet(SHEET.format(rm=7, title="Un titre", status="a_faire",
                                          body="du corps", tag="infra", parent=6))
    assert d["redmine_id"] == 7 and d["status"] == "a_faire" and d["title"] == "Un titre"
    assert d["tags"] == ["infra"] and d["relates"] == ["9999"] and d["parent_task"] == 6
    assert "du corps" in d["body"]


def test_parse_sheet_refuse_ce_qui_n_est_pas_une_fiche():
    assert pm_index.parse_sheet("pas de frontmatter") is None
    assert pm_index.parse_sheet("---\ntitle: x\n---\n") is None      # pas de redmine_id
    assert pm_index.parse_sheet("") is None and pm_index.parse_sheet(None) is None


def test_digest_stable_et_sensible():
    assert pm_index.digest("abc") == pm_index.digest("abc")
    assert pm_index.digest("abc") != pm_index.digest("abd")


# ── le cœur de l'incrémental (pur) ─────────────────────────────────────────

def test_plan_ne_retouche_que_ce_qui_a_bouge():
    known = {1: "aa", 2: "bb", 3: "cc"}
    found = {1: "aa", 2: "ZZ", 4: "dd"}          # 1 inchangé, 2 modifié, 3 disparu, 4 neuf
    up, rm = pm_index.plan(known, found)
    assert up == [2, 4] and rm == [3]


def test_plan_corpus_vide_supprime_tout():
    assert pm_index.plan({1: "a", 2: "b"}, {}) == ([], [1, 2])


def test_plan_base_vide_indexe_tout():
    assert pm_index.plan({}, {1: "a"}) == ([1], [])


# ── reconstruction ─────────────────────────────────────────────────────────

def test_rebuild_indexe_tout_et_est_idempotent():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _tree(Path(d), S)
        con = pm_index.connect(cfg)
        r1 = pm_index.rebuild(cfg, con)
        assert r1["indexed"] == 3, r1
        r2 = pm_index.rebuild(cfg, con)
        assert r2["indexed"] == 3
        assert con.execute("SELECT COUNT(*) c FROM tickets").fetchone()["c"] == 3
        assert con.execute("SELECT COUNT(*) c FROM fts").fetchone()["c"] == 3
        con.close()


def test_rebuild_range_tags_et_relations():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _tree(Path(d), S)
        con = pm_index.connect(cfg)
        pm_index.rebuild(cfg, con)
        tags = {r["tag"] for r in con.execute("SELECT tag FROM tags")}
        kinds = {r["kind"] for r in con.execute("SELECT kind FROM relations")}
        assert tags == {"infra", "front"} and "relates" in kinds and "parent" in kinds
        con.close()


def test_rebuild_sur_corpus_vide_ne_casse_pas():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _tree(Path(d), [])
        con = pm_index.connect(cfg)
        assert pm_index.rebuild(cfg, con)["indexed"] == 0
        con.close()


# ── incrément ──────────────────────────────────────────────────────────────

def test_update_ne_touche_rien_si_rien_ne_change():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _tree(Path(d), S)
        con = pm_index.connect(cfg)
        pm_index.rebuild(cfg, con)
        r = pm_index.update(cfg, con)
        assert (r["updated"], r["removed"], r["unchanged"]) == (0, 0, 3), r
        con.close()


def test_update_ne_reindexe_que_la_fiche_modifiee():
    with tempfile.TemporaryDirectory() as d:
        cfg, tasks = _tree(Path(d), S)
        con = pm_index.connect(cfg)
        pm_index.rebuild(cfg, con)
        p = tasks / "RM101_t.md"
        p.write_text(p.read_text(encoding="utf-8").replace("nouveau", "en_cours"),
                     encoding="utf-8")
        r = pm_index.update(cfg, con)
        assert (r["updated"], r["unchanged"]) == (1, 2), r
        assert con.execute("SELECT status FROM tickets WHERE rm_id=101").fetchone()[0] \
            == "en_cours"
        con.close()


def test_un_touch_sans_changement_ne_reindexe_pas():
    """Le mtime ment (touch, copie, checkout git) : c'est l'empreinte qui tranche."""
    with tempfile.TemporaryDirectory() as d:
        cfg, tasks = _tree(Path(d), S)
        con = pm_index.connect(cfg)
        pm_index.rebuild(cfg, con)
        p = tasks / "RM101_t.md"
        p.touch()
        time.sleep(0.01)
        r = pm_index.update(cfg, con)
        assert r["updated"] == 0, r
        con.close()


def test_update_retire_une_fiche_disparue():
    """Sinon l'index garderait des morts, et une recherche rendrait des tickets qui
    n'existent plus — pire qu'un index absent."""
    with tempfile.TemporaryDirectory() as d:
        cfg, tasks = _tree(Path(d), S)
        con = pm_index.connect(cfg)
        pm_index.rebuild(cfg, con)
        (tasks / "RM102_t.md").unlink()
        r = pm_index.update(cfg, con)
        assert r["removed"] == 1, r
        assert con.execute("SELECT COUNT(*) c FROM tickets WHERE rm_id=102").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) c FROM tags WHERE rm_id=102").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) c FROM fts WHERE rowid=102").fetchone()[0] == 0
        con.close()


def test_le_think_compte_dans_l_empreinte():
    with tempfile.TemporaryDirectory() as d:
        cfg, tasks = _tree(Path(d), S)
        con = pm_index.connect(cfg)
        pm_index.rebuild(cfg, con)
        (tasks / "RM101_t.think.md").write_text("| F001 | un moteur vectoriel |",
                                                encoding="utf-8")
        r = pm_index.update(cfg, con)
        assert r["updated"] == 1, r
        assert pm_index.query(cfg, text="vectoriel", con=con)[0]["rm_id"] == 101
        con.close()


# ── touch : le point d'accroche des deux entrées ───────────────────────────

def test_touch_indexe_une_fiche_seule():
    with tempfile.TemporaryDirectory() as d:
        cfg, tasks = _tree(Path(d), S)
        con = pm_index.connect(cfg); pm_index.rebuild(cfg, con); con.close()
        p = tasks / "RM101_t.md"
        p.write_text(p.read_text(encoding="utf-8").replace("nouveau", "a_mep"),
                     encoding="utf-8")
        assert pm_index.touch(cfg, p, "acme", "site") is True
        con = pm_index.connect(cfg)
        assert con.execute("SELECT status FROM tickets WHERE rm_id=101").fetchone()[0] == "a_mep"
        con.close()


def test_touch_retire_une_fiche_effacee():
    with tempfile.TemporaryDirectory() as d:
        cfg, tasks = _tree(Path(d), S)
        con = pm_index.connect(cfg); pm_index.rebuild(cfg, con); con.close()
        p = tasks / "RM102_t.md"; p.unlink()
        assert pm_index.touch(cfg, p) is True
        con = pm_index.connect(cfg)
        assert con.execute("SELECT COUNT(*) c FROM tickets WHERE rm_id=102").fetchone()[0] == 0
        con.close()


def test_touch_ne_leve_jamais():
    """Un index en échec ne doit pas faire échouer l'écriture d'un ticket : c'est une
    projection, pas la source."""
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _tree(Path(d), S)
        assert pm_index.touch(cfg, "/chemin/inexistant/RM1_x.md") in (True, False)
        assert pm_index.touch(None, "/x") is False


# ── la greffe sur l'écriture locale (pm_git.autocommit) ────────────────────

def test_la_greffe_reindexe_apres_une_ecriture_pm():
    """RM3128 : toute écriture PM passe par pm_git.autocommit — c'est là qu'est greffée
    la première des deux entrées de l'index (la seconde étant pm-task-sync, qui y passe
    aussi). Greffé sur un process existant, jamais sur un timer dédié."""
    import os
    import pm_git
    with tempfile.TemporaryDirectory() as d:
        cfg, tasks = _tree(Path(d), S)
        con = pm_index.connect(cfg); pm_index.rebuild(cfg, con); con.close()
        p = tasks / "RM101_t.md"
        p.write_text(p.read_text(encoding="utf-8").replace("nouveau", "a_corriger"),
                     encoding="utf-8")
        old = os.environ.get("PM_CORE_DIR")
        os.environ["PM_CORE_DIR"] = str(Path(d) / "pm")
        try:
            pm_git._index_touch([p])
        finally:
            if old is None: os.environ.pop("PM_CORE_DIR", None)
            else: os.environ["PM_CORE_DIR"] = old
        con = pm_index.connect(cfg)
        assert con.execute("SELECT status FROM tickets WHERE rm_id=101").fetchone()[0] \
            == "a_corriger"
        con.close()


def test_la_greffe_ne_cree_pas_la_base_en_douce():
    """Sans index construit, un commit ne doit pas en fabriquer un au passage : on ne
    crée pas un artefact persistant au détour d'une opération qui ne le demande pas."""
    import os
    import pm_git
    with tempfile.TemporaryDirectory() as d:
        cfg, tasks = _tree(Path(d), S)
        assert not pm_index.db_path(cfg).exists()
        old = os.environ.get("PM_CORE_DIR")
        os.environ["PM_CORE_DIR"] = str(Path(d) / "pm")
        try:
            pm_git._index_touch([tasks / "RM101_t.md"])
        finally:
            if old is None: os.environ.pop("PM_CORE_DIR", None)
            else: os.environ["PM_CORE_DIR"] = old
        assert not pm_index.db_path(cfg).exists()


def test_la_greffe_ne_leve_jamais():
    import pm_git
    assert pm_git._index_touch([Path("/inexistant/RM1_x.md")]) is None
    assert pm_git._index_touch([]) is None


# ── requêtes ───────────────────────────────────────────────────────────────

def test_compteur_par_statut():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _tree(Path(d), S)
        con = pm_index.connect(cfg); pm_index.rebuild(cfg, con)
        assert pm_index.count_by_status(cfg, con) == {"nouveau": 1, "ferme": 1, "en_cours": 1}
        con.close()


def test_query_fts_et_filtres():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _tree(Path(d), S)
        con = pm_index.connect(cfg); pm_index.rebuild(cfg, con)
        assert [t["rm_id"] for t in pm_index.query(cfg, text="sqlite", con=con)] == [101]
        assert [t["rm_id"] for t in pm_index.query(cfg, status_="ferme", con=con)] == [102]
        assert pm_index.query(cfg, text="introuvable", con=con) == []
        assert len(pm_index.query(cfg, project="acme/site", con=con)) == 3
        con.close()


# ── l'index doit AVOUER son retard ─────────────────────────────────────────

def test_status_avoue_la_divergence():
    with tempfile.TemporaryDirectory() as d:
        cfg, tasks = _tree(Path(d), S)
        con = pm_index.connect(cfg); pm_index.rebuild(cfg, con)
        assert pm_index.status(cfg, con)["stale"] == 0
        p = tasks / "RM101_t.md"
        p.write_text(p.read_text(encoding="utf-8").replace("nouveau", "ferme"),
                     encoding="utf-8")
        (tasks / "RM103_t.md").unlink()
        st = pm_index.status(cfg, con)
        assert st["stale"] == 1 and st["orphans"] == 1, st
        con.close()


def test_status_donne_volume_et_fraicheur():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _tree(Path(d), S)
        con = pm_index.connect(cfg); pm_index.rebuild(cfg, con)
        st = pm_index.status(cfg, con)
        assert st["tickets"] == 3 and st["on_disk"] == 3
        assert st["last_rebuild"] and st["last_update"]
        con.close()


def test_la_base_vit_dans_l_etat_local_jamais_dans_les_sources():
    with tempfile.TemporaryDirectory() as d:
        cfg, _ = _tree(Path(d), S)
        p = pm_index.db_path(cfg)
        assert "var" in str(p) and "projects" not in str(p), p


# ── la collision de noms qui a cassé la prod (RM3143) ──────────────────────

def test_le_module_des_symlinks_de_projets_est_intact():
    """RM3143 : `pm_index` (index des SYMLINKS de projets, RM3033) et `pm_searchdb` (index de
    requêtage, RM3128) sont deux modules distincts. Le second s'appelait `pm_index` à sa
    livraison et a ÉCRASÉ le premier, cassant les quatre `pm-index-*` en production."""
    import importlib
    import pm_index
    for fn in ("listing", "format_listing"):
        assert hasattr(pm_index, fn), f"pm_index.{fn} manque — le module des projets est écrasé"
    assert not hasattr(pm_index, "rebuild") or pm_index.__doc__.startswith("pm_index — l'INDEX"), \
        "pm_index ne doit PAS être l'index de requêtage"


def test_les_deux_modules_ne_partagent_pas_leur_base():
    """Deux index, deux fichiers : un nom de base partagé serait la même collision d'un cran plus bas."""
    import pm_searchdb
    assert "searchdb" in pm_searchdb.DB_NAME, pm_searchdb.DB_NAME


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
