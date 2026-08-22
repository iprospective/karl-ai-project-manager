#!/usr/bin/env python3
"""Tests RM2789 — lisibilité du texte des tickets.

Deux volets, un principe commun : « ce qui ressemble à X n'est pas X ».

  · un gabarit « (à compléter) » n'est pas un critère d'acceptation. Le compter bloquait
    la livraison sans recours proportionné : le seul contournement désactivait le
    garde-fou pour les VRAIS critères aussi ;
  · un retour à la ligne d'enveloppe n'est pas un saut de ligne voulu. Redmine rendait
    les deux pareil, d'où des paragraphes hachés.

Ce qu'on protège surtout, c'est ce que le dé-enveloppement NE DOIT PAS toucher : code,
listes, tableaux, titres, sauts durs. Une fonction qui aplatit tout serait pire que le mal.

Lancer : python3 scripts/test_pm_lisibilite.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_markdown import is_placeholder, real_checklist_lines, unwrap, checklist_lines

fails = []


def chk(label, cond):
    print(("✓ " if cond else "✗ ") + label)
    if not cond:
        fails.append(label)


# ── volet 1 : le gabarit n'est pas un critère ────────────────────────────────
chk("« (à compléter) » est un gabarit", is_placeholder("(à compléter)"))
chk("« à définir » aussi", is_placeholder("à définir"))
chk("« TBD » aussi", is_placeholder("TBD"))
chk("un vrai critère n'en est pas un", not is_placeholder("Le port est alloué au registre"))
chk("un critère CONTENANT le mot n'en est pas un",
    not is_placeholder("La doc à compléter est publiée"))

DESC = ("## Critères d'acceptation\n\n"
        "- [ ] (à compléter)\n"
        "- [ ] un vrai critère\n"
        "- [x] un critère fait\n")
reels = real_checklist_lines(DESC)
chk("le gabarit est écarté, les vrais restent", len(reels) == 2)
chk("…et le comptage des non cochés tombe à 1",
    sum(1 for _, m in reels if m.group(2).strip() == "") == 1)

CITE = ("Exemple de gabarit fautif :\n\n```markdown\n- [ ] (à compléter)\n- [ ] autre\n```\n\n"
        "- [ ] le seul vrai critère\n")
chk("une checklist CITÉE dans un bloc de code ne compte pas",
    len(real_checklist_lines(CITE)) == 1)
chk("…alors que checklist_lines seule les voyait déjà exclues (RM2540)",
    len(checklist_lines(CITE)) == 1)

# ── volet 2 : dé-enveloppement ───────────────────────────────────────────────
chk("un paragraphe enveloppé est rejoint",
    unwrap("Le bloc runtime du manifeste\nne sait décrire qu'un PHP-FPM.")
    == "Le bloc runtime du manifeste ne sait décrire qu'un PHP-FPM.")
chk("les paragraphes restent séparés",
    unwrap("un\ndeux\n\ntrois\nquatre") == "un deux\n\ntrois quatre")
chk("idempotent", unwrap(unwrap("a\nb\n\nc")) == unwrap("a\nb\n\nc"))
chk("texte vide toléré", unwrap("") == "" and unwrap(None) is None)

CODE = "avant\ntexte\n\n```bash\nligne 1\nligne 2\n```\n\napres\ntexte"
chk("un bloc de code n'est PAS aplati", "ligne 1\nligne 2" in unwrap(CODE))
chk("…et le texte autour l'est", "avant texte" in unwrap(CODE))
chk("un bloc INDENTÉ n'est pas aplati",
    "    code un\n    code deux" in unwrap("para\n\n    code un\n    code deux\n"))

chk("une liste garde ses items",
    unwrap("- un\n- deux\n- trois") == "- un\n- deux\n- trois")
chk("une liste numérotée aussi", unwrap("1. un\n2. deux") == "1. un\n2. deux")
chk("un tableau garde ses lignes",
    unwrap("| a | b |\n|---|---|\n| 1 | 2 |") == "| a | b |\n|---|---|\n| 1 | 2 |")
chk("les titres restent seuls", unwrap("## Titre\ntexte") == "## Titre\ntexte")
chk("une citation reste ligne à ligne", unwrap("> une\n> deux") == "> une\n> deux")
chk("une règle horizontale survit", "---" in unwrap("a\n\n---\n\nb"))
chk("une checklist n'est pas rejointe",
    unwrap("- [ ] un\n- [ ] deux") == "- [ ] un\n- [ ] deux")
chk("un saut DUR (deux espaces) est respecté",
    unwrap("ligne une  \nligne deux") == "ligne une  \nligne deux")

# ── le câblage : dé-enveloppement au point de passage unique ─────────────────
import redmine_utils as ru
p = ru._unwrap_payload({"issue": {"description": "une\nphrase", "notes": "autre\nphrase",
                                  "subject": "titre\nnon touché"}})
chk("la description est dé-enveloppée", p["issue"]["description"] == "une phrase")
chk("la note aussi", p["issue"]["notes"] == "autre phrase")
chk("le sujet n'est PAS touché", p["issue"]["subject"] == "titre\nnon touché")
chk("un payload non-dict passe tel quel", ru._unwrap_payload(None) is None)
chk("un payload sans champ texte est intact",
    ru._unwrap_payload({"issue": {"status_id": 3}}) == {"issue": {"status_id": 3}})

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — lisibilité du texte des tickets (RM2789)")
