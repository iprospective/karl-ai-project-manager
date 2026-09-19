#!/usr/bin/env python3
"""Tests RM3248 — pm-task-add cherche l'antériorité LUI-MÊME avant de créer.

Pourquoi : le tripwire #19 demandait à l'agent de chercher avant de créer, et l'outil existait
(pm-task-search, RM3130). RM3247 a pourtant été créé sans recherche, juste après une
compaction : une règle qu'il faut se rappeler d'appliquer au moment où l'on crée est oubliée
au moment où l'on crée. La garde est donc dans l'outil de création.

Ce qui est protégé :
  1. une correspondance FORTE dans le même projet ARRÊTE la création — c'est le cas RM3247 ;
  2. elle se lève par un acquittement explicite, `--not-duplicate`, qu'on retrouve au journal ;
  3. hors projet, ou faible, on AFFICHE sans bloquer : sinon la garde serait contournée ;
  4. deux titres datés à des dates différentes sont deux occurrences, pas un doublon —
     c'était la première source de faux positifs sur l'arbre réel (réunions récurrentes) ;
  5. un titre trop court ne permet pas de conclure ;
  6. un moteur de recherche en panne n'empêche JAMAIS la création.

Calibration du seuil sur l'arbre réel (1 578 tickets, 2026-09-19) : à 0,8, 1,7 % des
créations auraient été arrêtées — dont la moitié environ de vrais doublons présents dans
l'arbre (titres identiques) ; le reste, des séries volontaires, qu'un acquittement lève.

Lancer : python3 scripts/test_pm_task_add_prior_art.py
"""
import importlib.util
import io
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _charge(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, HERE / fichier)
    m = importlib.util.module_from_spec(spec)
    sys.modules[nom] = m
    spec.loader.exec_module(m)
    return m


S = _charge("pm_task_search", "pm-task-search.py")
T = _charge("test_pm_task_search", "test_pm_task_search.py")   # son arbre fictif (_tree)
A = _charge("pm_task_add", "pm-task-add.py")

P = "acme/site"


def t(rm, title, status="nouveau", project=P):
    return {"rm_id": rm, "status": status, "title": title, "project": project}


# ── moteur pur ──────────────────────────────────────────────────────────────

def test_titre_identique_dans_le_projet_est_fort():
    f, _ = S.prior_art("pm-env-session : préfixe de vhost paramétrable par repo",
                       [t(1, "pm-env-session : préfixe de vhost paramétrable par repo (runtime.vhost_prefix)")],
                       project=P)
    assert [x["rm_id"] for x in f] == [1], f


def test_titre_reformule_reste_reconnu():
    """Pas besoin d'identité : l'ordre et les mots vides changent, le sujet non."""
    f, _ = S.prior_art("Paramétrer le préfixe du vhost de pm-env-session par repo",
                       [t(1, "pm-env-session : préfixe de vhost paramétrable par repo")], project=P)
    assert f, "une reformulation doit rester une antériorité forte"


def test_hors_projet_affiche_sans_bloquer():
    f, v = S.prior_art("Mettre à jour PrestaShop en 1.7.8.11 sur le site",
                       [t(1, "Mettre à jour PrestaShop en 1.7.8.11 sur le site", project="autre/site")],
                       project=P)
    assert f == [] and [x["rm_id"] for x in v] == [1], (f, v)


def test_reunions_datees_differentes_ne_sont_pas_des_doublons():
    f, v = S.prior_art("Réunion point client-a 16/06/2026", [t(1, "Réunion point client-a 09/06/2026")],
                       project=P)
    assert f == [] and v == [], (f, v)


def test_meme_date_reste_un_doublon():
    f, _ = S.prior_art("Réunion point commercial client-a 09/06/2026",
                       [t(1, "Réunion point commercial client-a 09/06/2026")], project=P)
    assert f, "même réunion, même date : c'est un doublon"


def test_titre_trop_court_ne_bloque_pas():
    f, _ = S.prior_art("Bug panier", [t(1, "Bug panier")], project=P)
    assert f == [], "deux termes ne suffisent pas à conclure"


def test_mots_vides_et_nombres_ne_comptent_pas():
    assert S.signifiants("Le panier de la commande du 12/05") == ["panier", "commande"]


def test_recouvrement_asymetrique():
    """Un titre court entièrement contenu dans un long : antériorité. L'inverse : non."""
    court, long_ = "Export comptable mensuel automatique", \
        "Export comptable mensuel automatique vers le cabinet, avec relance et archivage"
    assert S.title_overlap(court, long_) == 1.0
    assert S.title_overlap(long_, court) < S.SEUIL_FORT, "l'inverse ne doit pas être une correspondance forte"


def test_sujet_voisin_sous_le_seuil_ne_bloque_pas():
    """Partager un sujet n'est pas être un doublon (« CRM pro » : 3 termes sur 4)."""
    f, _ = S.prior_art("Doublon de client dans CRM PRO",
                       [t(1, "CRM pro : tagguer un client à faire en urgence")], project=P)
    assert f == [], f


# ── la garde de pm-task-add, sur un arbre de tickets fictif ──────────────────

def _garde(cfg, titre, acquit=None):
    err = io.StringIO()
    try:
        with redirect_stderr(err), redirect_stdout(err):
            r = A._garde_anteriorite(cfg, titre, P, acquit)
        return r, None, err.getvalue()
    except SystemExit as e:
        return None, str(e.code), err.getvalue()


ARBRE = [(9101, "Export comptable mensuel automatique vers le cabinet", "nouveau", "feature", "x"),
         (9102, "Relance des impayés par courriel", "ferme", "feature", "y")]


def test_garde_refuse_le_doublon_et_dit_comment_passer():
    with tempfile.TemporaryDirectory() as d:
        cfg = T._tree(Path(d), ARBRE)
        r, refus, _ = _garde(cfg, "Export comptable mensuel automatique")
        assert r is None and refus and "RM9101" in refus, refus
        assert "--not-duplicate" in refus, "le refus doit donner la commande pour passer"


def test_garde_acquittee_laisse_passer_et_rend_la_correspondance():
    with tempfile.TemporaryDirectory() as d:
        cfg = T._tree(Path(d), ARBRE)
        r, refus, sortie = _garde(cfg, "Export comptable mensuel automatique", acquit="autre cabinet")
        assert refus is None and [x["rm_id"] for x in r] == [9101], (r, refus)
        assert "acquittée" in sortie


def test_garde_laisse_passer_un_sujet_neuf():
    with tempfile.TemporaryDirectory() as d:
        cfg = T._tree(Path(d), ARBRE)
        r, refus, _ = _garde(cfg, "Horloge atomique pour la machine à café")
        assert r == [] and refus is None


def test_moteur_en_panne_n_empeche_pas_la_creation():
    r, refus, sortie = _garde(object(), "Export comptable mensuel automatique")  # cfg inutilisable
    assert r == [] and refus is None, (r, refus)
    assert "indisponible" in sortie and "pm-task-search" in sortie, sortie


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
