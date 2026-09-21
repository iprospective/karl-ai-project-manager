#!/usr/bin/env python3
"""Tests RM2882 — ce que la migration des critères accepte d'écrire.

La règle cardinale du backfill (RM2563) reste entière : jamais de vide à la place
de contenu, jamais d'arbitrage. Les critères ajoutent une nuance, parce qu'ils sont
une LISTE et pas un bloc opaque : quand une source est incluse dans l'autre, prendre
le sur-ensemble n'arbitre rien, ça complète. Dès qu'il y a de l'exclusif des deux
côtés — ou la même ligne cochée d'un seul côté — on ne touche à rien.

S'y ajoute un verrou que rien d'autre ne porte : tant que des cases traînent HORS de
la section de critères, migrer déplacerait la cible de `--check N` (§ 4.2 de l'étude).

Lancer : python3 scripts/test_pm_acceptance_migrate.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("bf", HERE / "pm-cf-mirror-backfill.py")
bf = importlib.util.module_from_spec(spec)
sys.modules["bf"] = bf
spec.loader.exec_module(bf)

fails = []


def chk(label, cond):
    print(("✓ " if cond else "✗ ") + label)
    if not cond:
        fails.append(label)


PROPRE = "## Critères d'acceptation\n\n- [ ] un\n- [ ] deux\n"

chk("les deux vides → rien", bf.decide_acceptance(None, None, PROPRE)[0] == "vide")
chk("identiques → déjà synchrones",
    bf.decide_acceptance("- [ ] un", "- [ ] un", PROPRE)[0] == "sync")
chk("… même enveloppés différemment (Redmine rend en CRLF et ré-enveloppe)",
    bf.decide_acceptance("- [ ] un critère\n      long", "- [ ] un critère long", PROPRE)[0]
    == "sync")

chk("MD seul → PUSH vers Redmine",
    bf.decide_acceptance("- [ ] un", None, PROPRE)[0] == "push")
chk("Redmine seul → PULL vers le frontmatter",
    bf.decide_acceptance(None, "- [ ] un", PROPRE)[0] == "pull")

act, val, motifs = bf.decide_acceptance("- [ ] un", "- [ ] un\n- [ ] deux", PROPRE)
chk("MD inclus dans Redmine → UNION", act == "union")
chk("… l'union porte les deux items", "un" in val and "deux" in val)
chk("… et le rapport dit ce qui a été repris", motifs and "Redmine" in motifs[0])

act, val, _ = bf.decide_acceptance("- [ ] un\n- [ ] deux", "- [ ] un", PROPRE)
chk("Redmine inclus dans le MD → UNION sans rien perdre",
    act == "union" and "deux" in val)

act, _, motifs = bf.decide_acceptance("- [ ] un\n- [ ] MD seul",
                                      "- [ ] un\n- [ ] Redmine seul", PROPRE)
chk("divergence croisée → CONFLIT, rien n'est écrit", act == "conflit")
chk("… et le motif la nomme", motifs and "croisée" in motifs[0])

act, _, motifs = bf.decide_acceptance("- [x] un", "- [ ] un", PROPRE)
chk("même item, coche différente → CONFLIT (personne ne sait qui a raison)",
    act == "conflit")
chk("… et le motif cite l'item en cause", motifs and "un" in motifs[0])

# ── le verrou des cases errantes ─────────────────────────────────────────────
ERRANT = """## Critères d'acceptation

- [ ] un

## Étapes

- [ ] une étape qui n'est pas un critère
"""
act, _, motifs = bf.decide_acceptance("- [ ] un", None, ERRANT)
chk("cases hors section → pas de migration automatique, même sans conflit de contenu",
    act == "conflit")
chk("… et le motif explique le décalage de `--check N`",
    motifs and "check N" in motifs[0])
act, _, _ = bf.decide_acceptance("- [ ] un", "- [ ] un", ERRANT)
chk("cases errantes : le verrou passe AVANT « déjà synchrone » (§ 4.2)", act == "conflit")
chk("le verrou ne se déclenche pas quand tout est dans la section",
    bf.decide_acceptance("- [ ] un", None, PROPRE)[0] == "push")
chk("les deux côtés vides restent 'vide' même avec des cases errantes",
    bf.decide_acceptance(None, None, ERRANT)[0] == "vide")

# ── RM3240 : CF vide, « Redmine » = section de la description ────────────────
F = bf.cf_vide_vers_push
a, v, src, _ = F("sync", None, [], "- [x] un", "- [x] un", "section du corps", True)
chk("CF vide + même section des deux côtés → PUSH vers le CF (et plus « déjà conforme »)",
    (a, v, src) == ("push", "- [x] un", "section du corps"))
a, v, src, _ = F("pull", "- [ ] un", [], None, "- [ ] un", "frontmatter", True)
chk("CF vide + rien en local → PUSH de la section de la description, miroir local écrit",
    (a, v, src) == ("push", "- [ ] un", "description Redmine"))
chk("un CF RÉELLEMENT rempli ne change rien (le pull local reste un pull)",
    F("pull", "- [ ] un", [], None, "- [ ] un", "frontmatter", False)[0] == "pull"
    and F("sync", None, [], "- [ ] un", "- [ ] un", "frontmatter", False)[0] == "sync")
chk("un conflit reste un conflit, même CF vide",
    F("conflit", None, ["x"], "- [ ] a", "- [ ] b", "section du corps", True)[0] == "conflit")
chk("une union reste une union (elle pousse déjà)",
    F("union", "- [ ] a\n- [ ] b", [], "- [ ] a", "- [ ] a\n- [ ] b", "frontmatter", True)[0] == "union")
_src = (HERE / "pm-cf-mirror-backfill.py").read_text(encoding="utf-8")
chk("la boucle sait d'où vient la valeur « Redmine »",
    "remote_de_la_description = remote is not None" in _src and "cf_vide_vers_push(" in _src)

# ── RM3261 : un ticket DÉJÀ migré ne se signale plus à chaque passage ────────
act, _, _ = bf.decide_acceptance("- [ ] un", "- [ ] un", ERRANT, remote_from_cf=True)
chk("cases errantes mais champ dédié rempli et d'accord : plus rien à protéger",
    act == "sync")
act, _, motifs = bf.decide_acceptance("- [ ] un", "- [ ] un", ERRANT, remote_from_cf=False)
chk("… alors que la même valeur venue de la DESCRIPTION reste verrouillée", act == "conflit")
act, _, _ = bf.decide_acceptance("- [x] un", "- [ ] un", ERRANT, remote_from_cf=True)
chk("migré mais en désaccord : le conflit tient", act == "conflit")

# ── le registre ──────────────────────────────────────────────────────────────
chk("`acceptance` est un miroir déclaré", "acceptance" in bf.MIRRORS)
chk("… adossé au CF « Critères d'acceptation »",
    bf.MIRRORS["acceptance"][1] == "Critères d'acceptation")
chk("l'adoption de section n'est plus codée en dur sur implementation",
    set(bf.SECTION_OF) == {"implementation", "acceptance"})

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — migration des critères : union, conflits, verrou des cases errantes, CF vide poussé (RM2882, RM3240)")
