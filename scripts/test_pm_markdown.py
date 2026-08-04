#!/usr/bin/env python3
"""Tests de pm_markdown + du cochage qui s'appuie dessus (RM2540).

Lancer : python3 scripts/test_pm_markdown.py
Défaut d'origine : `--check-all` cochait les cases citées dans un bloc de code
de la description — la citation devenait fausse — et le contrôle de livraison
les comptait comme des critères impossibles à cocher.
"""
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import pm_markdown  # noqa: E402
from pm_markdown import checklist_lines  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "pm_task_description_update", str(_HERE / "pm-task-description-update.py"))
ptdu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ptdu)


def texts(md):
    return [m.group(3)[1:].strip() for _, m in checklist_lines(md)]


def test_checklist_simple():
    assert texts("- [ ] un\n- [x] deux\n") == ["un", "deux"]


def test_case_dans_un_bloc_fence_ignoree():
    md = "Exemple :\n\n```markdown\n- [ ] (à compléter)\n```\n\n- [ ] vrai critère\n"
    assert texts(md) == ["vrai critère"]


def test_case_dans_un_bloc_indente_ignoree():
    """Le cas vécu : la description cite le gabarit fautif, indenté de 4 espaces."""
    md = ("Le gabarit ajoute :\n\n"
          "    ## Critères d'acceptation\n\n"
          "    - [ ] (à compléter)\n\n"
          "Ce qui duplique la section.\n\n"
          "## Critères d'acceptation\n\n"
          "- [ ] vrai critère\n")
    assert texts(md) == ["vrai critère"]


def test_sous_liste_indentee_reste_un_critere():
    """Sous un item de liste, 4 espaces font une sous-liste — PAS du code.
    Sans cette distinction, des critères imbriqués deviendraient invisibles."""
    md = "- [ ] parent\n    - [ ] enfant\n        - [ ] petit-enfant\n"
    assert texts(md) == ["parent", "enfant", "petit-enfant"]


def test_fence_non_ferme_vaut_jusqua_la_fin():
    md = "```\n- [ ] dans le code\n\n- [ ] encore dans le code\n"
    assert texts(md) == []


def test_fence_tildes_et_fence_imbrique():
    """Un ``` à l'intérieur d'un bloc ~~~ ne le ferme pas."""
    md = "~~~\n```\n- [ ] cité\n```\n~~~\n\n- [ ] réel\n"
    assert texts(md) == ["réel"]


def test_retour_a_la_marge_ferme_le_bloc_indente():
    md = "Texte :\n\n    - [ ] cité\n\n- [ ] réel\n"
    assert texts(md) == ["réel"]


def test_astérisque_et_indices_de_ligne():
    md = "intro\n* [ ] un\n\n* [x] deux\n"
    idx = [i for i, _ in checklist_lines(md)]
    assert idx == [1, 3], idx


# — le cochage lui-même —
def test_check_all_ne_touche_pas_les_citations():
    md = ("Gabarit fautif :\n\n"
          "```markdown\n- [ ] (à compléter)\n```\n\n"
          "- [ ] critère A\n- [ ] critère B\n")
    new, total, checked, changed = ptdu.apply_checks(md, set(), set(), True)
    assert total == 2 and checked == 2, (total, checked)
    assert "- [ ] (à compléter)" in new, "la citation a été réécrite"
    assert new.count("- [x]") == 2


def test_numerotation_ignore_les_citations():
    """`--check 1` doit viser le premier VRAI critère, pas la case citée."""
    md = "```\n- [ ] cité\n```\n\n- [ ] premier\n- [ ] second\n"
    new, total, checked, changed = ptdu.apply_checks(md, {1}, set(), False)
    assert total == 2 and checked == 1, (total, checked)
    assert "- [x] premier" in new and "- [ ] second" in new
    assert "- [ ] cité" in new


def test_uncheck_symetrique():
    md = "```\n- [x] cité\n```\n\n- [x] a\n- [x] b\n"
    new, _, checked, _ = ptdu.apply_checks(md, set(), {2}, False)
    assert checked == 1 and "- [ ] b" in new and "- [x] cité" in new


def test_deliver_ignore_les_citations():
    """Garde de câblage : le contrôle de livraison passe par la même source."""
    src = (_HERE / "pm-task-deliver.py").read_text(encoding="utf-8")
    assert "checklist_lines(body)" in src, "pm-task-deliver n'utilise pas pm_markdown"
    assert "CHECK_RE" not in src, "ancienne regex encore présente dans pm-task-deliver"


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
