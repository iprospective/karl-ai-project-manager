#!/usr/bin/env python3
"""Tests RM2882 — critères d'acceptation : extraction, union, double source.

Ce que ces tests protègent, ce sont les cinq pièges relevés par l'audit de migration :

  · la section court jusqu'au prochain titre de niveau ≤, pas au prochain titre (RM2560) ;
  · 90 tickets sur 93 portent une DEUXIÈME section qui n'est qu'un squelette fantôme
    (séquelle de RM2540) — c'est la section qui a de la matière qui fait foi ;
  · un titre qui *parle* des critères n'est pas une section de critères ;
  · aucune source n'est la bonne : l'union, jamais l'écrasement ;
  · tant que des cases traînent hors de la section, `--check N` ne peut pas basculer.

Lancer : python3 scripts/test_pm_acceptance.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_acceptance as A

fails = []


def chk(label, cond):
    print(("✓ " if cond else "✗ ") + label)
    if not cond:
        fails.append(label)


# ── extraction de la section ─────────────────────────────────────────────────
SOUS_PARTIES = """## Contexte

bla

## Critères d'acceptation

- [ ] premier

### Détail

- [x] second

## Suite

- [ ] hors section
"""
sec = A.extract_section(SOUS_PARTIES)
chk("la section embarque ses sous-parties (### ne la ferme pas)",
    "premier" in sec and "second" in sec)
chk("… et s'arrête au titre de même niveau", "hors section" not in sec)

FANTOME = """## Critères d'acceptation

- [ ] le vrai critère

## Autre chose

texte

## Critères d'acceptation

- [ ] (à compléter)
"""
chk("deux sections : celle qui porte la matière gagne (RM2540)",
    "le vrai critère" in A.extract_section(FANTOME))
chk("extract_sections les voit toutes les deux", len(A.extract_sections(FANTOME)) == 2)

FAUX_POSITIF = """## Génération de tests depuis critères d'acceptation

- [ ] pas une section de critères
"""
chk("un titre qui PARLE des critères n'est pas une section",
    A.extract_section(FAUX_POSITIF) is None)

CITE = """## Contexte

```markdown
## Critères d'acceptation
- [ ] exemple cité
```
"""
chk("une section citée dans un bloc de code est ignorée",
    A.extract_section(CITE) is None)

chk("pas de section du tout → None", A.extract_section("## Contexte\n\ntexte\n") is None)
chk("section présente mais vide → chaîne vide, pas None",
    A.extract_section("## Critères d'acceptation\n\n") == "")

chk("variante de libellé tolérée (« Critère d'acceptation (étude) »)",
    A.extract_section("## Critère d'acceptation (étude)\n\n- [ ] x\n") is not None)
chk("apostrophe typographique tolérée",
    A.extract_section("## Critères d’acceptation\n\n- [ ] x\n") is not None)

# ── items ────────────────────────────────────────────────────────────────────
items = A.parse_items("- [ ] un\n- [x] deux\n- [ ] (à compléter)\n")
chk("parse_items rend (coché, libellé) et écarte les gabarits",
    items == [(False, "un"), (True, "deux")])

# ── libellés enveloppés : l'outillage écrit à ~95 colonnes ───────────────────
ENVELOPPE = """- [ ] `pm-task-acceptance` écrit le frontmatter puis le CF, **refuse le vide**,
      logue et committe (modèle `pm-task-protocol`).
- [x] deuxième critère
"""
env_items = A.parse_items(ENVELOPPE)
chk("un libellé enveloppé n'est pas tronqué à sa première ligne",
    len(env_items) == 2 and "logue et committe" in env_items[0][1])
chk("… et la coche du critère suivant reste la sienne", env_items[1] == (True, "deuxième critère"))
chk("aller-retour render → parse stable (une migration rejouée ne diffère pas)",
    A.parse_items(A.render_items(env_items)) == env_items)

MULTI_MD = """## Critères d'acceptation

- [ ] un critère long
      qui continue ici

## Suite
"""
chk("la continuation s'arrête au titre suivant",
    A.parse_items(A.extract_section(MULTI_MD))[0][1] == "un critère long\nqui continue ici")
chk("deux libellés qui ne diffèrent que par l'enveloppe sont le même item",
    A.norm_label("un critère long\nqui continue") == A.norm_label("un critère long qui continue"))
u4, d4 = A.union([(False, "un critère\nlong")], [(False, "un critère long")])
chk("… donc l'union ne les duplique pas", len(u4) == 1 and not d4)

# ── union ────────────────────────────────────────────────────────────────────
md = [(False, "commun"), (True, "seulement MD")]
rm = [(False, "commun"), (False, "seulement Redmine")]
u, diffs = A.union(md, rm)
chk("l'union garde l'ossature du MD puis ajoute ce que Redmine seul porte",
    [l for _, l in u] == ["commun", "seulement MD", "seulement Redmine"])
types = sorted(d["type"] for d in diffs)
chk("les deux exclusivités sortent en divergences",
    types == ["only_md", "only_redmine"])

u2, d2 = A.union([(True, "même item")], [(False, "même item")])
chk("même libellé, coche différente → divergence signalée, pas d'écrasement",
    len(u2) == 1 and d2 and d2[0]["type"] == "check_differs")
chk("… et la coche gardée est celle du MD", u2[0][0] is True)

u3, d3 = A.union([(False, "Le  port  est   alloué")], [(False, "le port est alloué")])
chk("la comparaison ignore casse et espaces surnuméraires", len(u3) == 1 and not d3)

chk("deux sources identiques → aucune divergence",
    A.union(md, md)[1] == [])

# ── double source, sans bascule ──────────────────────────────────────────────
BODY = "## Critères d'acceptation\n\n- [ ] depuis la description\n"
txt, src = A.criteria_text({}, BODY)
chk("champ vide → on lit la description (ticket non migré)",
    src == "description" and "depuis la description" in txt)

txt, src = A.criteria_text({"acceptance": "- [ ] depuis le champ"}, BODY)
chk("champ rempli → le champ fait foi", src == "acceptance" and "champ" in txt)

txt, src = A.criteria_text({"acceptance": "   \n  "}, BODY)
chk("champ blanc = champ vide (on ne bascule pas sur du vide)", src == "description")

chk("ni champ ni section → (\"\", None)", A.criteria_text({}, "## Contexte\n") == ("", None))

# ── cases hors section : le verrou de --check N ──────────────────────────────
HORS = """## Critères d'acceptation

- [ ] dans la section

## Étapes

- [ ] dehors 1
- [x] dehors 2
"""
chk("les cases hors section sont listées", A.stray_checkboxes(HORS) == ["dehors 1", "dehors 2"])
chk("aucune case hors section → liste vide", A.stray_checkboxes(BODY) == [])

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — critères d'acceptation : extraction, union, double source (RM2882)")
