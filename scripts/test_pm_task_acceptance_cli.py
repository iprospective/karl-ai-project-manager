#!/usr/bin/env python3
"""Tests RM2882 — le cochage du champ de critères (`pm-task-acceptance --check`).

`--check N` vise le Nᵉ critère **du champ**, dans l'ordre où le script les numérote
à l'affichage. Deux choses doivent rester vraies, sans quoi on coche à l'aveugle :
le numéro affiché est celui qu'on peut repasser au script (donc les gabarits ne
consomment pas de numéro), et un index hors bornes n'écrit RIEN — plutôt qu'écrire
la moitié d'un lot et laisser deviner laquelle.

Lancer : python3 scripts/test_pm_task_acceptance_cli.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("acc", HERE / "pm-task-acceptance.py")
acc = importlib.util.module_from_spec(spec)
sys.modules["acc"] = acc
spec.loader.exec_module(acc)
import pm_acceptance as A

fails = []


def chk(label, cond):
    print(("✓ " if cond else "✗ ") + label)
    if not cond:
        fails.append(label)


TXT = "- [ ] un\n- [ ] deux\n- [x] trois\n"

new, touches, hors = acc.set_check(TXT, [2], True)
chk("--check 2 coche le deuxième critère", "- [x] deux" in new)
chk("… et ne touche pas les autres", "- [ ] un" in new and "- [x] trois" in new)
chk("… et le rapport nomme l'item coché", touches == [(2, "deux")])
chk("… sans index hors bornes", hors == [])

new, _, _ = acc.set_check(TXT, [3], False)
chk("--uncheck décoche", "- [ ] trois" in new)

_, _, hors = acc.set_check(TXT, [9], True)
chk("un index hors bornes est signalé, pas appliqué", hors == [9])
_, _, hors = acc.set_check(TXT, [0], True)
chk("l'index 0 aussi (la numérotation est 1-based)", hors == [0])

# Le numéro affiché doit être celui qu'on peut repasser : les gabarits n'en consomment pas.
AVEC_GABARIT = "- [ ] vrai critère\n- [ ] (à compléter)\n- [ ] autre vrai\n"
new, touches, _ = acc.set_check(AVEC_GABARIT, [2], True)
chk("un gabarit ne consomme pas de numéro", touches == [(2, "autre vrai")])
chk("… et le gabarit reste intact", "- [ ] (à compléter)" in new)

ENVELOPPE = "- [ ] un critère long\n      qui continue\n- [ ] second\n"
new, touches, _ = acc.set_check(ENVELOPPE, [2], True)
chk("une continuation ne compte pas comme un item", touches and touches[0][1] == "second")
chk("… et la continuation n'est pas déplacée", "      qui continue" in new)

chk("cocher tout rend autant d'items que le champ en compte",
    len(acc.set_check(TXT, [1, 2, 3], True)[1]) == len(A.parse_items(TXT)))

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — cochage du champ de critères (RM2882)")
