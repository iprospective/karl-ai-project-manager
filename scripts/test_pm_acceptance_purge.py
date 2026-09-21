#!/usr/bin/env python3
"""Tests RM3241 — retrait de la section « Critères d'acceptation » une fois reprise dans le CF 33.

Ce que ces tests protègent :

  · la règle est ORIENTÉE : un CF en avance (plus de coches) autorise le retrait — c'est
    précisément le cas des descriptions périmées (RM3173 : 4/4 dans le CF, 0/4 dans la
    description) ; une description en avance, un item absent du CF ou de la prose dans la
    section l'interdisent ;
  · on retire exactement ce qu'on a comparé : le reste du corps est intact, blocs de code
    compris ;
  · les chemins qui RECRÉAIENT le doublon : `pm-task-add` (critères dans la description à la
    création), `render_md` (bandeau « À définir » sur un ticket dont les critères sont dans
    le champ), `redmine-fetch-task` (squelette ajouté par-dessus), `pm-task-description-update`.

Lancer : python3 scripts/test_pm_acceptance_purge.py
"""
import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("REDMINE_CF_ACCEPTANCE_ID", "33")
import pm_acceptance as A
import pm_task_md

fails = []


def chk(label, cond):
    print(("✓ " if cond else "✗ ") + label)
    if not cond:
        fails.append(label)


BODY = """## Contexte

Bla.

## Critères d'acceptation

- [ ] Un
- [x] Deux
  sur deux lignes

## Notes

fin
"""

# ── purge_decision : la règle orientée ───────────────────────────────────────
chk("CF identique → retire",
    A.purge_decision("- [ ] Un\n- [x] Deux sur deux lignes", BODY)[0] == "retire")
act, mot = A.purge_decision("- [x] Un\n- [x] Deux sur deux lignes\n- [ ] Trois", BODY)
chk("CF en avance (coche + item en plus) → retire", act == "retire")
chk("… et le motif dit de combien il est en avance", mot and "1 coche" in mot[0])
act, mot = A.purge_decision("- [ ] Un\n- [ ] Deux sur deux lignes", BODY)
chk("description en avance d'une coche → garde", act == "garde" and "coché" in mot[0])
act, mot = A.purge_decision("- [ ] Un", BODY)
chk("item absent du CF → garde", act == "garde" and "absent du CF" in mot[0])
chk("CF vide + vrais critères → garde", A.purge_decision("", BODY)[0] == "garde")
chk("CF vide + seulement le bandeau « À définir » → rien (pas un conflit)",
    A.purge_decision("", "## Critères d'acceptation\n\n> ⚠ **À définir** — aucun.\n")[0] == "rien")
chk("pas de section → rien", A.purge_decision("- [ ] Un", "## Contexte\n\nx\n")[0] == "rien")
act, mot = A.purge_decision("- [ ] Un\n- [x] Deux sur deux lignes",
                            BODY.replace("- [ ] Un\n", "- [ ] Un\n\nVoir parent RM1724.\n"))
chk("prose dans la section → garde (elle serait perdue)",
    act == "garde" and "hors cases" in mot[0])
chk("markup ignoré à la comparaison (saisie web sans gras)",
    A.purge_decision("- [ ] Un\n- [x] Deux sur deux lignes",
                     BODY.replace("- [ ] Un", "- [ ] **Un**"))[0] == "retire")
chk("bandeau « À définir » à côté de vrais critères : pas de la matière",
    A.purge_decision("- [ ] Un", "## Critères d'acceptation\n\n> ⚠ **À définir**\n- [ ] Un\n")[0]
    == "retire")
CODE = "## Critères d'acceptation\n```\n- [ ] cité en exemple\n```\n- [ ] Un\n"
chk("case citée dans un bloc de code → garde (prudence)",
    A.purge_decision("- [ ] Un", CODE)[0] == "garde")

# ── strip_sections : on retire ce qu'on a comparé, rien d'autre ─────────────
chk("strip : le reste du corps intact", A.strip_sections(BODY) == "## Contexte\n\nBla.\n\n## Notes\n\nfin\n")
FANTOME = "## Critères d'acceptation\n- [ ] (à compléter)\n\n## Suite\nx\n\n## Critères d'acceptation\n- [ ] Un\n"
chk("strip : sections multiples (fantôme RM2540) toutes retirées",
    A.strip_sections(FANTOME) == "## Suite\nx\n")
SOUS = "## Critères d'acceptation\n- [ ] Un\n\n### Détail\n- [ ] Deux\n\n## Après\nz\n"
chk("strip : une sous-partie ### reste DANS la section retirée", A.strip_sections(SOUS) == "## Après\nz\n")
chk("strip : une sous-partie ### compte comme matière → garde",
    A.purge_decision("- [ ] Un\n- [ ] Deux", SOUS)[0] == "garde")
DANS_CODE = "## Doc\n```\n## Critères d'acceptation\n- [ ] exemple\n```\n"
chk("strip : un titre cité dans un bloc de code n'est pas une section",
    A.strip_sections(DANS_CODE) == DANS_CODE)
chk("strip : sans section, texte rendu tel quel", A.strip_sections("a\n\nb\n") == "a\n\nb\n")

# ── split_for_creation : pm-task-add ─────────────────────────────────────────
desc, crit = A.split_for_creation("## Demande\nx\n\n## Critères d'acceptation\n- [ ] Un\n- [ ] Deux\n")
chk("création : critères sortis vers le champ", crit == "- [ ] Un\n- [ ] Deux")
chk("création : description sans la section", "Critères" not in desc and desc.startswith("## Demande"))
GAB = "## Demande\nx\n\n## Critères d'acceptation\n- [ ] (à compléter)\n"
chk("création : gabarit seul → description inchangée, pas de champ",
    A.split_for_creation(GAB) == (GAB, None))
PROSE = "## Critères d'acceptation\n- [ ] Un\n\nDépend de la sous-tâche 1.\n"
chk("création : prose dans la section → description inchangée (rien ne se perd)",
    A.split_for_creation(PROSE) == (PROSE, None))

# ── render_md : pas de bandeau « À définir » quand le champ est rempli ───────
chk("render_md : bandeau présent sans critères",
    "À définir" in pm_task_md.render_md({"redmine_id": 1}, "x"))
chk("render_md : pas de bandeau quand `acceptance` est rempli",
    "Critères d'acceptation" not in pm_task_md.render_md({"redmine_id": 1, "acceptance": "- [ ] Un"}, "x"))

# ── redmine-fetch-task : plus de squelette par-dessus des critères existants ──
_s = importlib.util.spec_from_file_location("_fetch", HERE / "redmine-fetch-task.py")
F = importlib.util.module_from_spec(_s); _s.loader.exec_module(F)
chk("fetch : squelette si aucun critère nulle part",
    "## Critères d'acceptation\n- [ ]" in F.render_md({}, "x", "http://r", 1))
chk("fetch : pas de squelette quand le champ est rempli",
    "Critères d'acceptation" not in F.render_md({"acceptance": "- [ ] Un"}, "x", "http://r", 1))
chk("fetch : pas de squelette par-dessus une section existante (fantôme RM2540)",
    F.render_md({}, "## Critères d'acceptation\n- [ ] Un", "http://r", 1).count("Critères d'acceptation") == 1)

# ── cf_text_of_issue ─────────────────────────────────────────────────────────
chk("CF lu depuis le dict Redmine",
    A.cf_text_of_issue({"custom_fields": [{"id": 33, "value": "- [ ] Un\r\n"}]}) == "- [ ] Un")
chk("CF absent → chaîne vide", A.cf_text_of_issue({"custom_fields": []}) == "")

# ── plan_ticket (pm-acceptance-purge) ────────────────────────────────────────
_s = importlib.util.spec_from_file_location("_purge", HERE / "pm-acceptance-purge.py")
P = importlib.util.module_from_spec(_s); _s.loader.exec_module(P)
ISSUE = {"description": BODY, "custom_fields": [{"id": 33, "value": "- [x] Un\n- [x] Deux sur deux lignes"}]}
pl = P.plan_ticket(ISSUE, {"acceptance": "- [x] Un\n- [x] Deux sur deux lignes"}, BODY)
chk("plan : description et MD retirés", pl["redmine"] == "retire" and pl["md"] == "retire")
chk("plan : nouvelle description sans la section", "Critères" not in pl["new_desc"])
pl = P.plan_ticket(ISSUE, {}, BODY)
chk("plan : miroir local vide → rempli depuis le CF avant retrait",
    pl["md"] == "retire" and pl["fill_mirror"] == "- [x] Un\n- [x] Deux sur deux lignes")
pl = P.plan_ticket(ISSUE, {"acceptance": "- [ ] Autre chose"}, BODY)
chk("plan : miroir local ≠ CF → corps MD gardé", pl["md"] == "garde" and pl["fill_mirror"] is None)
pl = P.plan_ticket({"description": BODY, "custom_fields": []}, {}, BODY)
chk("plan : CF vide → rien n'est retiré nulle part", pl["redmine"] == "garde" and pl["md"] == "garde")

# ── câblage des chemins qui recréaient le doublon (lecture du source) ────────
add = (HERE / "pm-task-add.py").read_text(encoding="utf-8")
chk("pm-task-add : POST avec la description SANS section",
    "description=description," in add and "split_for_creation" in add)
chk("pm-task-add : miroir local posé", "fm[pm_acceptance.FM_KEY] = criteres" in add)
upd = (HERE / "pm-task-description-update.py").read_text(encoding="utf-8")
chk("description-update : --add-criterion refusé sur ticket migré → --append",
    "if args.add_criterion:" in upd and "--append" in upd)
chk("description-update : --set-from-file passe par purge_decision", "purge_decision(_acc, file_text)" in upd)
notify = (HERE / "pm-client-notify.py").read_text(encoding="utf-8")
chk("email client : critères par la lecture unique", "pm_acceptance.criteria_text(fm, body)" in notify)

# ── RM3285 : replier la section dans le champ ────────────────────────────────
chk("convert : une puce devient une case cochée",
    A.convert_bullets("- le service répond", True) == "- [x] le service répond")
chk("convert : une liste numérotée aussi",
    A.convert_bullets("1. la base migre", False) == "- [ ] la base migre")
chk("convert : une case existante n'est pas retouchée",
    A.convert_bullets("- [ ] déjà une case", True) == "- [ ] déjà une case")
chk("convert : une phrase de contexte reste de la prose (on ne fabrique pas un critère)",
    A.convert_bullets("Lié à RM2028.", True) == "Lié à RM2028.")
chk("convert : rien dans un bloc de code",
    A.convert_bullets("```\n- exemple\n```", True) == "```\n- exemple\n```")

SEC = "### Étape 1\n- [x] un\n- [ ] deux\n\n### Étape 2\n- [ ] trois"
CF = "- [x] deux\n- [x] quatre"
fold = A.fold_into_field(CF, SEC)
chk("fold : les sous-titres de la section sont conservés", "### Étape 1" in fold and "### Étape 2" in fold)
chk("fold : une coche du champ gagne sur la section (le champ est en avance)", "- [x] deux" in fold)
chk("fold : un critère que seul le champ portait est conservé", "- [x] quatre" in fold)
chk("fold : l'ordre de la section est préservé", fold.index("un") < fold.index("trois"))
chk("fold : idempotent — replier deux fois ne duplique rien",
    A.fold_into_field(fold, SEC) == fold or A.parse_items(A.fold_into_field(fold, SEC)) == A.parse_items(fold))
chk("fold : section vide → None (jamais de valeur vide poussée)", A.fold_into_field(CF, "   ") is None)
chk("fold : conversion appliquée seulement si la section n'a AUCUNE case",
    "- [x] un" in A.fold_into_field("", "- un", convert=True)
    and A.fold_into_field("", SEC, convert=True).count("- [x] un") == 1)

BODY_PROSE = "## Critères d'acceptation\n\n### Étape 1\n- [x] un\n\nDépend de la sous-tâche 1.\n"
chk("purge : la prose que le champ porte AUSSI ne bloque plus le retrait",
    A.purge_decision("### Étape 1\n- [x] un\n\nDépend de la sous-tâche 1.", BODY_PROSE)[0] == "retire")
chk("purge : la prose absente du champ bloque toujours",
    A.purge_decision("- [x] un", BODY_PROSE)[0] == "garde")
chk("purge : une puce convertie en case est reconnue comme la même ligne",
    A.purge_decision("- [x] le service répond", "## Critères d'acceptation\n- le service répond\n")[0] == "retire")

ISSUE_F = {"description": BODY_PROSE, "custom_fields": [{"id": 33, "value": "- [x] un"}]}
val, motif = P.fold_plan(ISSUE_F, {}, BODY_PROSE)
chk("fold_plan : rend la valeur à écrire", val and "Dépend de la sous-tâche 1." in val)
CROISE_MD = "## Critères d'acceptation\n- [ ] seulement local\n"
ISSUE_X = {"description": "## Critères d'acceptation\n- [ ] seulement redmine\n", "custom_fields": []}
val, motif = P.fold_plan(ISSUE_X, {}, CROISE_MD)
chk("fold_plan : divergence croisée NON repliée", val is None and "croisée" in motif)
ISSUE_C = {"description": "## Critères d'acceptation\n- [x] un\n", "custom_fields": [{"id": 33, "value": "- [ ] un"}]}
val, motif = P.fold_plan(ISSUE_C, {}, "## Critères d'acceptation\n- [x] un\n")
chk("fold_plan : coche présente dans la section mais pas dans le champ → arbitrage",
    val is None and "arbitrage" in motif)
val, motif = P.fold_plan({"description": "## Critères d'acceptation\nUn paragraphe sans puce.\n",
                          "custom_fields": []}, {}, "")
chk("fold_plan : des critères en paragraphes ne se replient pas (le champ resterait sans critère)",
    val is None)
src = (HERE / "pm-acceptance-purge.py").read_text(encoding="utf-8")
chk("purge : le champ est poussé AVANT le retrait de la section",
    src.index("Le champ d'abord") < src.index("frais = redmine_utils.fetch_issue"))
chk("purge : --fold et --convert-bullets existent, dry-run toujours par défaut",
    '"--fold"' in src and '"--convert-bullets"' in src and "if not args.go:" in src)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — retrait de la section de critères (RM3241) et repliement dans le champ (RM3285)")
