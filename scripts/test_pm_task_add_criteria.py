#!/usr/bin/env python3
"""Tests offline de la détection des critères d'acceptation (RM2540).

Lancer : python3 scripts/test_pm_task_add_criteria.py
Le gabarit « ## Critères d'acceptation / - [ ] (à compléter) » ne doit être
ajouté que si la description n'apporte pas déjà sa section : sinon le ticket
porte un critère parasite que personne ne coche, le done_ratio plafonne et
pm-task-deliver refuse la livraison.
"""
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
_spec = importlib.util.spec_from_file_location("pm_task_add", str(_HERE / "pm-task-add.py"))
pm_task_add = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm_task_add)
has = pm_task_add.has_acceptance_criteria


def test_section_simple():
    assert has("Blabla\n\n## Critères d'acceptation\n\n- [ ] un\n")


def test_variantes_de_titre():
    """Niveau de titre, casse, accents et apostrophe typographique indifférents."""
    for titre in ("# Critères d'acceptation",
                  "### Critères d'acceptation",
                  "###### Critères d'acceptation",
                  "## critères d'acceptation",
                  "## CRITÈRES D'ACCEPTATION",
                  "## Criteres d'acceptation",
                  "## Critère d'acceptation",
                  "## Critères d’acceptation",          # apostrophe typographique
                  "##Critères d'acceptation",           # sans espace après les #
                  "  ## Critères d'acceptation",        # jusqu'à 3 espaces
                  "## Critères d'acceptation (DoD)"):   # suffixe
        assert has(f"Contexte\n\n{titre}\n\n- [ ] un\n"), titre


def test_absence():
    assert not has("Juste du contexte, sans section de critères.")
    assert not has("")
    assert not has(None)


def test_mention_en_prose_ne_compte_pas():
    """Seul un TITRE ouvre une section — une phrase qui en parle, non."""
    assert not has("Il faudra définir les critères d'acceptation plus tard.")
    assert not has("- [ ] écrire les critères d'acceptation")


def test_titre_dans_un_bloc_de_code_ignore():
    """Cas vécu : la description CITE le gabarit fautif pour le décrire."""
    desc = ("Le gabarit ajoute toujours :\n\n"
            "```markdown\n## Critères d'acceptation\n\n- [ ] (à compléter)\n```\n\n"
            "Ce qui duplique la section.\n")
    assert not has(desc), "un titre cité dans un bloc de code n'est pas une section"


def test_bloc_de_code_puis_vraie_section():
    desc = ("Exemple :\n\n"
            "```\n## Critères d'acceptation\n```\n\n"
            "## Critères d'acceptation\n\n- [ ] vrai critère\n")
    assert has(desc), "la vraie section après le bloc de code doit être vue"


def test_bloc_de_code_indente_ignore():
    """Un bloc indenté de 4 espaces est du code pour markdown — pas un titre."""
    assert not has("Exemple :\n\n    ## Critères d'acceptation\n\n    - [ ] (à compléter)\n")


def test_fence_tildes():
    assert not has("~~~\n## Critères d'acceptation\n~~~\n")


def test_fence_non_ferme_ne_masque_pas_la_suite():
    """Un fence ouvert sans fermeture ne doit pas faire disparaître le document."""
    assert has("```\ndu code\n\n## Critères d'acceptation\n\n- [ ] un\n")


def test_gabarit_conditionne_dans_la_source():
    """Garde de câblage : les cas ci-dessus ne couvrent que le prédicat. On
    vérifie ici qu'il pilote bien l'ajout du gabarit, et que celui-ci n'est plus
    concaténé inconditionnellement au corps du ticket."""
    src = (_HERE / "pm-task-add.py").read_text(encoding="utf-8")
    assert "if not has_acceptance_criteria(desc):" in src, "prédicat non câblé"
    assert r"{desc}\n\n## Critères d'acceptation" not in src, \
        "le gabarit est encore ajouté sans condition"


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
