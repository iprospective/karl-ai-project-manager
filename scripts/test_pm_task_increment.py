#!/usr/bin/env python3
"""Tests RM3041 — ajout INCRÉMENTAL dans une description et un protocole de test.

Pourquoi ces verbes existent : jusqu'ici, ajouter une anomalie ou un critère imposait de
réécrire TOUTE la description (`--set-from-file`). Le déclencheur est concret — trois
anomalies signalées coup sur coup sur RM3025, trois réécritures intégrales, avec à chaque
fois le risque de perdre ce qu'on n'avait pas relu.

Ce qui est protégé ici :
  1. on ajoute AU BON ENDROIT — dans la section visée, pas à la fin du document ;
  2. on ne touche à RIEN d'autre : le reste de la description est intact, au caractère près ;
  3. c'est IDEMPOTENT — rejouer un script n'empile pas des doublons (à la casse et aux
     espaces près), sinon l'automatisation devient dangereuse ;
  4. la section absente est CRÉÉE plutôt que de faire échouer l'appel ;
  5. côté protocole, la ligne entre DANS le tableau, avec un identifiant qui suit le
     précédent et les cases d'environnement vides — un protocole se lit par ses repères.

Lancer : python3 scripts/test_pm_task_increment.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


D = _load("pm_task_description_update", "pm-task-description-update.py")
P = _load("pm_task_protocol", "pm-task-protocol.py")

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# ── description : add-item / add-criterion ───────────────────────────────────
DESC = """## Contexte

Le panier ne plafonne pas.

## Anomalies / À faire

- [x] Prix barré absent
- [ ] Popup muette

## Critères d'acceptation

- [ ] La quantité est plafonnée

## Notes

Rien à signaler.
"""

out, ok = D.add_checklist_item(DESC, "item", "Le paiement n'est pas bloqué")
check("item ajouté", ok)
check("…dans la section « Anomalies », pas ailleurs",
      out.index("Le paiement n'est pas bloqué") < out.index("## Critères"))
check("…après le dernier item de la section",
      out.index("Popup muette") < out.index("Le paiement n'est pas bloqué"))
check("le reste du document est INTACT",
      "Rien à signaler." in out and "## Notes" in out and "Le panier ne plafonne pas." in out)
check("les coches existantes ne bougent pas", "- [x] Prix barré absent" in out)

out2, ok2 = D.add_checklist_item(out, "item", "le PAIEMENT   n'est pas bloqué")
check("idempotent : même texte à la casse et aux espaces près => pas de doublon", not ok2)
check("…et le document est rendu inchangé", out2 == out)

outc, okc = D.add_checklist_item(DESC, "criterion", "Le paiement est refusé en dépassement")
check("critère ajouté dans SA section",
      okc and outc.index("Le paiement est refusé") > outc.index("## Critères")
      and outc.index("Le paiement est refusé") < outc.index("## Notes"))

vide, okv = D.add_checklist_item("## Contexte\n\nUn ticket sans section.\n", "item", "Première anomalie")
check("section absente => créée", okv and "## Anomalies / À faire" in vide)
check("…sans écraser le contexte", "Un ticket sans section." in vide)
check("texte vide refusé", D.add_checklist_item(DESC, "item", "   ")[1] is False)
check("description vide tolérée", D.add_checklist_item("", "item", "X")[1] is True)

# une variante de titre déjà en usage doit être RECONNUE, pas dupliquée
alt = "## Anomalies\n\n- [ ] Une\n"
outa, oka = D.add_checklist_item(alt, "item", "Deux")
check("titre variant (« Anomalies ») reconnu, pas de section en double",
      oka and outa.count("## Anomalies") == 1)

# ── protocole : add-test ─────────────────────────────────────────────────────
PROTO = """Recette après déploiement.

## A. Seuils de bande

| Cas | Test | Dev | Préprod | Prod |
|---|---|---|---|---|
| A1 | Date courte -10 % | — | [x] | [ ] |
| A2 | Antigaspi -25 % | — | [ ] | [ ] |

## B. Panier

| Cas | Test | Dev | Préprod | Prod |
|---|---|---|---|---|
| B1 | Le prix suit la bande | — | [x] | [ ] |
"""

np, okp, nid = P.add_test_row(PROTO, "A. Seuils", "Dernière minute -70 %")
check("ligne ajoutée au tableau de la BONNE section",
      okp and np.index("Dernière minute") < np.index("## B. Panier"))
check("identifiant qui suit le précédent (A2 → A3)", nid == "A3", nid)
check("…et les cases d'environnement sont vides",
      "| A3 | Dernière minute -70 % | [ ] | [ ] | [ ] |" in np, np[np.index("| A3"):][:70] if "| A3" in np else "absente")
check("la section B est intacte", "| B1 | Le prix suit la bande | — | [x] | [ ] |" in np)
check("les coches déjà posées ne bougent pas", "| A1 | Date courte -10 % | — | [x] | [ ] |" in np)

np2, okp2, _ = P.add_test_row(np, "A. Seuils", "  dernière   MINUTE -70 %  ")
check("idempotent sur le libellé", not okp2 and np2 == np)

np3, okp3, nid3 = P.add_test_row(PROTO, "C. Paiement", "Commande refusée en dépassement")
check("section absente => créée avec ses en-têtes",
      okp3 and "## C. Paiement" in np3 and "| # | Test | Dev | Préprod | Prod |" in np3)
check("…première ligne numérotée A1", nid3 == "A1")
check("protocole vide toléré", P.add_test_row("", "A. Recette", "Un test")[1] is True)
check("libellé vide refusé", P.add_test_row(PROTO, "A. Seuils", "")[1] is False)

# ── le gabarit « À définir » cède la place au premier vrai critère ───────────
# Sinon la section se contredit : « aucun critère posé » suivi de six critères. Constaté
# en jouant le verbe pour de vrai sur RM3041.
GAB = "## Critères d'acceptation\n\n> ⚠ **À définir** — aucun critère n'a été posé à la création.\n"
og, okg = D.add_checklist_item(GAB, "criterion", "Premier vrai critère")
check("le gabarit « À définir » est retiré à la première insertion", okg and "À définir" not in og)
check("…et la mise en forme reste propre (titre, ligne vide, item)",
      og == "## Critères d'acceptation\n\n- [ ] Premier vrai critère", repr(og))
og2, _ = D.add_checklist_item(og, "criterion", "Deuxième")
check("…les suivants s'empilent normalement", og2.endswith("- [ ] Premier vrai critère\n- [ ] Deuxième"))

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
