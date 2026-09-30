#!/usr/bin/env python3
"""Tests RM3369 — santé du système PM (pm_health).

Ce qui est vérifié ici est la partie PURE : agrégation, comptage, tri,
péremption, comparaison des champs attendus, lecture des sorties de doctor.
Aucun réseau, aucun disque hors tmp.

L'essentiel du fichier tient en un point : **prouver que le détecteur détecte**.
Un rapport tout vert sur le parc du jour ne dit rien — il faut le cas rouge, et
c'est celui de RM3224 (un miroir local rempli, un champ non activé côté projet,
du travail invisible). Un test qui ne sait pas échouer ne protège personne.

Lancer : python3 scripts/test_pm_health.py
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pm_health as H          # noqa: E402

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# ── agrégation ──────────────────────────────────────────────────────────────
G_OK = [{"name": "Champs Redmine", "checks": [H.chk("a", "ok"), H.chk("b", "info")]}]
G_BAD = [
    {"name": "Champs Redmine", "checks": [H.chk("p1", "error", "3 champs", "activer"),
                                          H.chk("p2", "ok")]},
    {"name": "Normes", "checks": [H.chk("n1", "warn", "index vieux")]},
    {"name": "Hors surveillance", "checks": [H.chk("x", "error", "ne compte pas")]},
]

s = H.health_summary(G_BAD)
check("summary compte chaque niveau", s["counts"] == {"ok": 1, "info": 0, "warn": 1, "error": 2})
check("summary rend le pire niveau", s["worst"] == "error")
check("summary d'un rapport vide est ok", H.health_summary([])["worst"] == "ok")

a = H.health_alerts(G_BAD)
check("alerts ignore les familles non surveillées",
      all(i["family"] != "Hors surveillance" for i in a["items"]))
check("alerts ne garde que ce qui demande un geste", a["count"] == 2)
check("alerts compte les MAJEURS seuls dans `major`", a["major"] == 1)
check("alerts met l'erreur avant l'avertissement", a["items"][0]["level"] == "error")
check("alerts porte la remédiation", a["items"][0]["fix"] == "activer")
check("alerts d'un parc sain ne montre rien", H.health_alerts(G_OK)["count"] == 0)
check("alerts d'un parc sain vaut ok", H.health_alerts(G_OK)["worst"] == "ok")

# Un avertissement seul ne doit PAS gonfler le badge : sinon il clignote tous
# les jours et plus personne ne le lit (la leçon d'ENV_ALERT_FAMILIES).
only_warn = [{"name": "Normes", "checks": [H.chk("n", "warn", "d")]}]
check("un avertissement seul ne fait aucun majeur", H.health_alerts(only_warn)["major"] == 0)
check("un avertissement seul reste visible", H.health_alerts(only_warn)["count"] == 1)

# ── péremption du rapport ───────────────────────────────────────────────────
NOW = 1_000_000.0
check("rapport absent = souci MAJEUR", H.report_age(None, NOW)["level"] == "error")
check("rapport absent dit comment le produire", "pm-health" in H.report_age(None, NOW)["fix"])
check("rapport frais = ok", H.report_age(NOW - 60, NOW)["level"] == "ok")
check("rapport de 7 h = avertissement", H.report_age(NOW - 7 * 3600, NOW)["level"] == "warn")
check("rapport de 2 j = erreur", H.report_age(NOW - 48 * 3600, NOW)["level"] == "error")
check("un rapport périmé dit son âge", "h" in H.report_age(NOW - 7 * 3600, NOW)["detail"])
check("l'âge d'un rapport venu du futur ne devient pas négatif",
      H.report_age(NOW + 500, NOW)["level"] == "ok")

# ── champs attendus par projet ──────────────────────────────────────────────
EXPECTED = {3: "GIT Branche", 31: "Proposition d'implémentation", 33: "Critères d'acceptation"}
check("aucun champ manquant sur un projet complet",
      H.missing_fields([3, 31, 33, 99], EXPECTED) == [])
check("les champs manquants sont nommés",
      H.missing_fields([3], EXPECTED) == ["Critères d'acceptation", "Proposition d'implémentation"])
check("un projet sans aucun champ les liste tous", len(H.missing_fields([], EXPECTED)) == 3)
check("les identifiants en texte sont acceptés", H.missing_fields(["3", "31", "33"], EXPECTED) == [])

c_ok = H.project_cf_check("pisceen/dolibarr", [3, 31, 33], EXPECTED)
c_bad = H.project_cf_check("calicote/dolibarr", [3], EXPECTED)
check("projet complet = ok", c_ok["level"] == "ok")
check("champ non activé = souci MAJEUR", c_bad["level"] == "error")
check("le détail nomme ce qui manque", "Critères d'acceptation" in c_bad["detail"])
check("la ligne porte la façon de réparer", "issue_custom_field_ids" in c_bad["fix"])

# Le cas RM3367 rejoué : 20 attendus, 12 présents → on doit le voir.
rm3367 = H.project_cf_check("Dolibarr", list(range(1, 13)), {i: f"CF{i}" for i in range(1, 21)})
check("le cas RM3367 est retrouvé si on le rejoue", rm3367["level"] == "error")
check("le cas RM3367 compte bien 8 manquants", "8 champ(s)" in rm3367["detail"])

# ── miroirs perdus (le cas RM3224) ──────────────────────────────────────────
check("aucun miroir orphelin = ok", H.lost_mirror_check([])["level"] == "ok")
perdu = H.lost_mirror_check([
    {"task": "RM3224", "project": "calicote/dolibarr",
     "field": "Proposition d'implémentation", "chars": 2459},
])
check("un miroir sans champ activé = souci MAJEUR", perdu["level"] == "error")
check("le détail chiffre ce qui est invisible", "2459 caractères" in perdu["detail"])
check("le détail nomme le ticket", "RM3224" in perdu["detail"])

# Ce qui ne doit PAS déclencher : les coquilles vides.
check("None n'est pas du contenu", H.mirror_is_filled(None) is False)
check("une chaîne vide n'est pas du contenu", H.mirror_is_filled("   ") is False)
check("une liste vide n'est pas du contenu", H.mirror_is_filled([]) is False)
check("une liste de vides n'est pas du contenu", H.mirror_is_filled(["", "  "]) is False)
check("False n'est pas du contenu", H.mirror_is_filled(False) is False)
check("0 n'est pas du contenu", H.mirror_is_filled(0) is False)
check("un texte est du contenu", H.mirror_is_filled("- [ ] un critère") is True)
check("une liste non vide est du contenu", H.mirror_is_filled(["étape 1"]) is True)
check("un dict rempli est du contenu", H.mirror_is_filled({"branch": "3369-x"}) is True)
check("un dict de vides ne l'est pas", H.mirror_is_filled({"branch": None, "mr": ""}) is False)
check("mirror_chars compte le texte", H.mirror_chars("  abc  ") == 3)
check("mirror_chars additionne une liste", H.mirror_chars(["ab", "cde"]) == 5)

check("dig suit un chemin pointé", H.dig({"git": {"branch": "b"}}, "git.branch") == "b")
check("dig sur une branche absente rend None", H.dig({"git": {}}, "git.branch") is None)
check("dig sur une feuille non-dict rend None", H.dig({"git": "x"}, "git.branch") is None)

# ── lecture des sorties de doctor ───────────────────────────────────────────
SORTIE = """== pm-doctor — 52 projet(s) scannés ==
  ✗ a/b : provided_by → c/d introuvable
  ⚠ e/f : used_by_clients ∋ 'g' (unilatéral)
  ✓ tout le reste va bien
== ÉCHEC — 1 erreur(s), 1 avertissement(s) ==
"""
check("les lignes en erreur sont extraites", H.marker_lines(SORTIE, "✗") ==
      ["a/b : provided_by → c/d introuvable"])
check("les avertissements aussi", len(H.marker_lines(SORTIE, "⚠")) == 1)
check("les lignes vertes ne sont pas extraites", "tout le reste" not in
      " ".join(H.marker_lines(SORTIE, "✗") + H.marker_lines(SORTIE, "⚠")))
check("une sortie vide ne casse rien", H.marker_lines("", "✗") == [])
check("une sortie None ne casse rien", H.marker_lines(None, "✗") == [])

# ── le fichier de rapport ───────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "sous" / "pm-health.json"
    rep = {"generated_at": NOW, "groups": G_BAD, "summary": H.health_summary(G_BAD)}
    H.write_report(rep, p)
    check("le rapport est écrit, dossier créé au besoin", p.is_file())
    check("le rapport se relit à l'identique", H.read_report(p)["generated_at"] == NOW)
    check("aucun fichier temporaire ne survit",
          not any(x.name.endswith(".tmp") for x in p.parent.iterdir()))
    check("le rapport est lisible par un humain", "Champs Redmine" in p.read_text(encoding="utf-8"))
    check("un rapport absent rend None", H.read_report(Path(td) / "rien.json") is None)
    corrompu = Path(td) / "casse.json"
    corrompu.write_text("{ pas du json", encoding="utf-8")
    check("un rapport corrompu rend None, pas une exception", H.read_report(corrompu) is None)

# ── cohérence du module ─────────────────────────────────────────────────────
check("chaque famille surveillée existe bien",
      set(H.ALERT_FAMILIES) <= {n for n, _ in H.FAMILIES})
check("chaque famille a un collecteur appelable", all(callable(f) for _, f in H.FAMILIES))
check("les miroirs surveillés portent un nom de champ et un chemin",
      all(isinstance(a, str) and isinstance(b, str) and a and b for a, b in H.MIRROR_FIELDS))
check("chk rend les quatre clés attendues",
      set(H.chk("l", "ok")) == {"label", "level", "detail", "fix"})
check("chk n'ajoute `section` que si elle existe", "section" in H.chk("l", "ok", section="s"))

# ── assistances portant du code (RM3368) ────────────────────────────────────
check("aucune assistance suspecte = ok", H.assistance_check([])["level"] == "ok")
susp = H.assistance_check([{"task": "RM3224", "project": "calicote/dolibarr",
                            "markers": ["branche", "MR"]}])
check("une assistance avec branche et MR est signalée", susp["level"] == "warn")
check("elle n'est PAS un souci majeur : c'est un arbitrage, pas une perte en cours",
      susp["level"] != "error")
check("le détail nomme le ticket et ses marqueurs",
      "RM3224" in susp["detail"] and "branche" in susp["detail"])
check("la ligne donne les DEUX issues de la norme",
      "pm-task-type-update" in susp["fix"] and "--parent" in susp["fix"])
beaucoup = H.assistance_check([{"task": f"RM{i}", "project": "p", "markers": ["branche"]}
                               for i in range(9)])
check("une longue liste reste lisible", "(+4)" in beaucoup["detail"])

with tempfile.TemporaryDirectory() as td:
    proj = Path(td) / "clients" / "x" / "projects" / "y"
    (proj / "tasks").mkdir(parents=True)
    (proj / "tasks" / "RM100_aide.md").write_text(
        "---\ntype: assistance\ngit:\n  branch: 100-truc\n  mr_url: null\n---\n", encoding="utf-8")
    (proj / "tasks" / "RM101_aide.md").write_text(
        "---\ntype: assistance\ngit:\n  branch: null\n  mr_url: null\n---\n", encoding="utf-8")
    (proj / "tasks" / "RM102_dev.md").write_text(
        "---\ntype: feature\ngit:\n  branch: 102-truc\n---\n", encoding="utf-8")
    vrai = H.pm_projects
    H.pm_projects = lambda: [("x", "y", proj, "x-y")]
    try:
        c = H.family_assistances()[0]
        check("le collecteur TROUVE l'assistance qui porte une branche", c["level"] == "warn")
        check("et ne nomme qu'elle", "RM100" in c["detail"] and "RM101" not in c["detail"])
        check("une tâche avec branche n'est pas concernée", "RM102" not in c["detail"])
    finally:
        H.pm_projects = vrai

# ── le COLLECTEUR, pas seulement la fonction pure ───────────────────────────
# La fonction pure prouve qu'on sait classer ; ce bloc prouve qu'on sait
# TROUVER. Sans lui, un collecteur qui ne lirait rien du tout resterait vert.
def _faux_parc(td, acceptance="- [ ] un critère rédigé"):
    """Un projet PM avec une fiche de tâche : le strict nécessaire pour la lecture."""
    proj = Path(td) / "clients" / "calicote" / "projects" / "dolibarr"
    (proj / "tasks").mkdir(parents=True)
    (proj / "tasks" / "RM3224_etude.md").write_text(
        "---\nredmine_id: 3224\nacceptance: |\n  " + acceptance + "\n---\n\ncorps\n",
        encoding="utf-8")
    return proj


with tempfile.TemporaryDirectory() as td:
    proj = _faux_parc(td)
    vrai_projects, vrai_cfs, vrai_expected = H.pm_projects, H.redmine_projects_cfs, H.expected_issue_cfs
    H.pm_projects = lambda: [("calicote", "dolibarr", proj, "calicote-dolibarr")]
    H.expected_issue_cfs = lambda *a, **k: {33: "Critères d'acceptation"}
    try:
        # Champ ABSENT du projet : le contenu local est invisible côté Redmine.
        H.redmine_projects_cfs = lambda **k: {"calicote-dolibarr": ("Calicote", [3, 31])}
        rouge = H.family_cf_mirrors()[0]
        check("le collecteur TROUVE un miroir sans champ activé", rouge["level"] == "error")
        check("le collecteur nomme le ticket trouvé", "RM3224" in rouge["detail"])

        # Même parc, champ activé : plus rien à signaler.
        H.redmine_projects_cfs = lambda **k: {"calicote-dolibarr": ("Calicote", [3, 31, 33])}
        check("champ activé : le collecteur ne crie pas", H.family_cf_mirrors()[0]["level"] == "ok")

        # Miroir vide et champ absent : ce n'est pas une perte.
        (proj / "tasks" / "RM3224_etude.md").write_text(
            "---\nredmine_id: 3224\nacceptance: null\n---\n", encoding="utf-8")
        H.redmine_projects_cfs = lambda **k: {"calicote-dolibarr": ("Calicote", [3, 31])}
        check("un miroir vide ne compte pas pour une perte",
              H.family_cf_mirrors()[0]["level"] == "ok")

        # Une fiche au YAML cassé ne doit pas faire tomber la famille entière.
        (proj / "tasks" / "RM9999_casse.md").write_text(
            "---\nacceptance: [non fermé\n---\n", encoding="utf-8")
        check("une fiche illisible n'arrête pas le balayage",
              H.family_cf_mirrors()[0]["level"] == "ok")
    finally:
        H.pm_projects, H.redmine_projects_cfs, H.expected_issue_cfs = vrai_projects, vrai_cfs, vrai_expected


# Une famille qui explose devient une LIGNE, jamais une panne de rapport.
_vraies = H.FAMILIES
try:
    def _casse():
        raise RuntimeError("sonde en vrac")
    H.FAMILIES = [("Normes", _casse)]
    rep = H.build_report()
    check("une famille qui lève ne casse pas le rapport", len(rep["groups"]) == 1)
    check("la panne d'une famille devient une ligne", rep["groups"][0]["checks"][0]["level"] == "warn")
    check("la panne dit ce qui a levé", "sonde en vrac" in rep["groups"][0]["checks"][0]["detail"])
    check("le rapport porte toujours son résumé et ses alertes",
          "summary" in rep and "alerts" in rep)
    check("le rapport est daté", rep.get("generated_at", 0) > 0)
    check("une famille en panne ne fabrique pas un souci majeur", rep["alerts"]["major"] == 0)
    check("build_report --only ne joue que la famille demandée",
          len(H.build_report(only={"Normes"})["groups"]) == 1)
    check("build_report --only inconnue ne joue rien",
          H.build_report(only={"Inexistante"})["groups"] == [])
finally:
    H.FAMILIES = _vraies


print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("✓ tous les contrôles passent")
