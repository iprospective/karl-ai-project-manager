#!/usr/bin/env python3
"""Tests offline de pm-task-search — recherche d'antériorité (RM3130).

Lancer : python3 scripts/test_pm_task_search.py
Couvre les fonctions pures (repli d'accents, frontière de mot, pertinence, extrait) et
le chemin réel de `search()` sur une arborescence PM temporaire. Aucun réseau.

Le test qui compte le plus est `test_frontiere_de_mot_*` : à la première exécution
réelle, « rag » se trouvait dans « chiff**rag**e » et « f**rag**ment », et la recherche
rendait des tickets sans rapport — le plus sûr moyen de faire ignorer l'outil.
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

spec = importlib.util.spec_from_file_location("pm_task_search", HERE / "pm-task-search.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis")

from pm_paths import PMConfig

REAL_CONFIG = HERE.parent / "pm.config.yml"

TASK = """---
schema_version: 1.11.0
redmine_id: {rm}
title: {title}
type: {type}
status: {status}
priority: normal
created: '2026-09-13'
updated: 2026-09-13T10:00
---

{body}
"""


# ── repli et découpe ───────────────────────────────────────────────────────

def test_fold_retire_les_accents():
    assert S.fold("Déploiement") == "deploiement"
    assert S.fold("SÉMANTIQUE") == "semantique"


def test_tokenize_ignore_ponctuation_et_mots_d_une_lettre():
    assert S.tokenize("le RAG, à quoi ça sert ?") == ["le", "rag", "quoi", "ca", "sert"]
    assert S.tokenize(["recherche", "sémantique"]) == ["recherche", "semantique"]
    assert S.tokenize("") == []


# ── frontière de mot : le défaut trouvé à l'essai réel ─────────────────────

def test_frontiere_de_mot_pas_de_sous_chaine():
    """« rag » ne doit PAS se trouver dans « chiffrage » ni « fragment »."""
    assert S.count_terms("etude de chiffrage du fragment", ["rag"]) == {"rag": 0}
    assert S.count_terms("orage et barrage", ["rag"]) == {"rag": 0}


def test_frontiere_de_mot_debut_de_mot_suffit():
    """Mais « deploi » doit continuer de trouver « déploiement » : la FIN reste libre."""
    assert S.count_terms(S.fold("le déploiement"), ["deploi"])["deploi"] == 1
    assert S.count_terms("rag et ragondin", ["rag"])["rag"] == 2


# ── pertinence ─────────────────────────────────────────────────────────────

def test_aucun_terme_donne_zero():
    """Sinon une recherche sans réponse rendrait le corpus entier trié au hasard."""
    assert S.score("Titre", "corps", ["introuvable"]) == 0.0
    assert S.score("Titre", "corps", []) == 0.0


def test_titre_pese_plus_que_corps():
    t = S.score("index sqlite", "rien", ["sqlite"])
    c = S.score("autre chose", "index sqlite ici", ["sqlite"])
    assert t > c, (t, c)


def test_tous_les_termes_presents_passent_devant():
    deux = S.score("index sqlite", "", ["index", "sqlite"])
    un = S.score("index index index", "", ["index", "sqlite"])
    assert deux > un, (deux, un)


def test_un_long_document_ne_gagne_pas_en_radotant():
    court = S.score("", "sqlite sqlite", ["sqlite"])
    long_ = S.score("", "sqlite " * 200, ["sqlite"])
    assert long_ <= court * 2, (court, long_)


def test_a_egalite_un_ticket_vivant_passe_devant_un_clos():
    ouvert = S.score("sqlite", "", ["sqlite"], closed=False)
    clos = S.score("sqlite", "", ["sqlite"], closed=True)
    assert ouvert > clos


# ── extrait ────────────────────────────────────────────────────────────────

def test_extrait_centre_sur_le_terme_et_borne():
    txt = "bla " * 60 + "le mot sqlite ici " + "bla " * 60
    s = S.snippet(txt, ["sqlite"], width=80)
    assert "sqlite" in s and len(s) <= 90, (len(s), s)
    assert s.startswith("…") and s.endswith("…")


def test_extrait_sans_terme_prend_le_debut():
    s = S.snippet("un texte quelconque", ["absent"], width=40)
    assert s.startswith("un texte")


def test_extrait_vide_ne_casse_pas():
    assert S.snippet("", ["x"]) == "" and S.snippet(None, ["x"]) == ""


def test_extrait_aplatit_les_retours_ligne():
    assert "\n" not in S.snippet("a\n\nb\nc", ["b"], width=40)


# ── lecture d'une fiche ────────────────────────────────────────────────────

def test_parse_task_lit_le_frontmatter():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "RM42_x.md"
        f.write_text(TASK.format(rm=42, title="Un titre", type="feature",
                                 status="nouveau", body="du corps"), encoding="utf-8")
        rm, st, ty, ti, body = S.parse_task(f)
        assert (rm, st, ty, ti) == (42, "nouveau", "feature", "Un titre")
        assert "du corps" in body


def test_parse_task_ignore_ce_qui_n_est_pas_une_fiche():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "RM43_x.md"
        f.write_text("pas de frontmatter", encoding="utf-8")
        assert S.parse_task(f) is None


# ── search() sur une arborescence réelle ───────────────────────────────────

def _tree(tmp, tasks, think=None):
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
    for rm, title, status, typ, body in tasks:
        (proj / "tasks" / f"RM{rm}_t.md").write_text(
            TASK.format(rm=rm, title=title, type=typ, status=status, body=body),
            encoding="utf-8")
    for rm, txt in (think or {}).items():
        (proj / "tasks" / f"RM{rm}_t.think.md").write_text(txt, encoding="utf-8")
    return PMConfig.load(pm_dir)


TASKS = [
    (9001, "Index SQLite de karl-pm", "nouveau", "feature", "une base de requetage"),
    (9002, "Etude de chiffrage du fragment", "ferme", "research", "rien a voir"),
    (9003, "Cockpit : recherche globale", "ferme", "feature", "un champ unique, sqlite derriere"),
]


def test_search_classe_par_pertinence():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tree(Path(d), TASKS)
        res = S.search(cfg, ["sqlite"])
        assert [r["rm_id"] for r in res] == [9001, 9003], res
        assert res[0]["match"] == "titre" and res[1]["match"] == "corps"


def test_search_ne_rend_pas_le_faux_positif_du_debut():
    """RM9002 « chiffrage du fragment » ne doit JAMAIS sortir sur « rag »."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tree(Path(d), TASKS)
        assert S.search(cfg, ["rag"]) == []


def test_search_inclut_les_fermes_par_defaut():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tree(Path(d), TASKS)
        assert 9003 in [r["rm_id"] for r in S.search(cfg, ["sqlite"])]
        assert 9003 not in [r["rm_id"] for r in S.search(cfg, ["sqlite"], open_only=True)]


def test_search_respecte_la_limite():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tree(Path(d), TASKS)
        assert len(S.search(cfg, ["sqlite"], limit=1)) == 1
        assert len(S.search(cfg, ["sqlite"], limit=0)) == 2


def test_search_filtre_par_type():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tree(Path(d), TASKS)
        assert S.search(cfg, ["sqlite"], types=("research",)) == []
        assert len(S.search(cfg, ["sqlite"], types=("feature",))) == 2


def test_search_lit_aussi_le_think():
    """Une demande peut n'exister que sous forme de F dans le .think.md."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tree(Path(d), TASKS, think={9002: "| F001 | feature | un moteur vectoriel |"})
        assert 9002 in [r["rm_id"] for r in S.search(cfg, ["vectoriel"])]
        assert S.search(cfg, ["vectoriel"], with_think=False) == []


def test_search_sans_resultat_rend_une_liste_vide():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tree(Path(d), TASKS)
        assert S.search(cfg, ["introuvable"]) == []


def test_sortie_reste_economique():
    """La raison d'être de l'outil : un agent doit pouvoir l'appeler sans se ruiner."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tree(Path(d), TASKS)
        res = S.search(cfg, ["sqlite"])
        rendu = sum(len(r["title"]) + len(r["snippet"]) + len(r["project"]) for r in res)
        assert rendu < 1200, rendu          # ~300 tokens pour 8 résultats au pire


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
