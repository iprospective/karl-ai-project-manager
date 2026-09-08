#!/usr/bin/env python3
"""Tests RM2967 — pm-cdc : init/dict/index/check sur un CDC jetable (le harnais du CDC lui-même)."""
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def ecrire(docs, nom, texte):
    (docs / nom).write_text(texte, encoding="utf-8")


with tempfile.TemporaryDirectory() as tmp:
    docs = pathlib.Path(tmp) / "docs"
    docs.mkdir()
    base = [sys.executable, str(HERE / "pm-cdc.py")]
    run = lambda *a: subprocess.run(base + list(a) + ["--docs-dir", str(docs)], capture_output=True, text=True)

    r = run("init", "--prefix", "rm42", "--projet", "Bidule")
    dd = docs / "cdc-rm42" / "dict"
    check("init : chapitres plats numérotés, sources dans cdc-<prefix>/",
          r.returncode == 0 and (docs / "cdc-rm42-00-sommaire.md").exists()
          and (docs / "cdc-rm42" / "grille-360.md").exists() and (dd / "entites.yml").exists(), r.stdout + r.stderr)
    check("init : les marqueurs sont substitués",
          "RM42" in (docs / "cdc-rm42-00-sommaire.md").read_text(encoding="utf-8")
          and "Bidule" in (docs / "cdc-rm42-00-sommaire.md").read_text(encoding="utf-8"))
    check("init : les treize tables du dictionnaire sont posées, vides", len(list(dd.glob("*.yml"))) == 13)
    check("init : refuse d'écraser un CDC existant", run("init", "--prefix", "rm42").returncode != 0)
    check("un CDC neuf passe le harnais", run("check").returncode == 0, run("check").stdout)

    # un CDC qui vit : deux entités, deux fonctionnalités, deux jalons, une décision
    ecrire(docs, "cdc-rm42-90-decisions.md", """# Registre

| # | Objet | État |
|---|---|---|
| D001 | Une décision | ✅ validé |

### D001 — Une décision ✅

Le corps.
""")
    ecrire(docs, "cdc-rm42-99-questions-ouvertes.md", """# Questions

| # | Question | Ce que ça bloque | Urgence |
|---|---|---|---|
| Q001 | Une question | rien | basse |
""")
    (dd / "entites.yml").write_text("- id: truc\n  nom: truc\n  role: un truc\n  domaine: socle\n", encoding="utf-8")
    (dd / "champs.yml").write_text("truc:\n- nom: id\n  type: ref\n", encoding="utf-8")
    (dd / "jalons.yml").write_text("- id: V0\n  titre: le socle\n- id: V1\n  titre: la suite\n", encoding="utf-8")
    (dd / "fonctionnalites.yml").write_text(
        "- id: F001\n  libelle: la base\n  domaine: socle\n  etat: décidé\n  jalon: 0\n  depend_de: []\n"
        "- id: F002\n  libelle: la suite\n  domaine: socle\n  etat: à trancher\n  jalon: 1\n  depend_de: [F001]\n"
        "  decisions: [D001]\n", encoding="utf-8")

    r = run("dict")
    chap = docs / "cdc-rm42-16-dictionnaire.md"
    txt = chap.read_text(encoding="utf-8") if chap.exists() else ""
    check("dict : chapitre généré, entités et champs rendus", r.returncode == 0 and "`truc`" in txt and "| id | ref |" in txt, r.stdout + r.stderr)
    check("dict : la feuille de route est DÉRIVÉE des fonctionnalités (ordre topologique)",
          "V0 — le socle" in txt and "| 1 | F001 |" in txt and txt.index("F001") < txt.index("F002"))
    check("dict : les jalons se lisent V0/V1, jamais le numéro nu", "| V1 |" in txt or "V1 — la suite" in txt)

    r = run("index")
    check("index : décisions et questions extraites des tableaux de synthèse",
          '"id": "D001"' in r.stdout and '"id": "Q001"' in r.stdout and '"etat": "✅ validé"' in r.stdout, r.stdout)

    check("check vert sur un CDC cohérent", run("check").returncode == 0, run("check").stdout)

    # 1. une décision citée qui n'existe pas
    ecrire(docs, "cdc-rm42-02-sujet.md", "# 02\n\nOn s'appuie sur D404.\n")
    r = run("check")
    check("check : référence morte à une décision", r.returncode == 1 and "D404" in r.stdout, r.stdout)
    (docs / "cdc-rm42-02-sujet.md").unlink()

    # 2. une dépendance vers un jalon ultérieur
    (dd / "fonctionnalites.yml").write_text(
        "- id: F001\n  libelle: la base\n  domaine: socle\n  etat: décidé\n  jalon: 0\n  depend_de: [F002]\n"
        "- id: F002\n  libelle: la suite\n  domaine: socle\n  etat: décidé\n  jalon: 1\n  depend_de: []\n", encoding="utf-8")
    r = run("check")
    check("check : un jalon ne peut pas dépendre d'un jalon ultérieur",
          r.returncode == 1 and "jalon ultérieur" in r.stdout, r.stdout)

    # 3. écarter une fonctionnalité est une suppression EN CASCADE
    (dd / "fonctionnalites.yml").write_text(
        "- id: F001\n  libelle: la base\n  domaine: socle\n  etat: écarté\n  depend_de: []\n"
        "- id: F002\n  libelle: la suite\n  domaine: socle\n  etat: décidé\n  jalon: 1\n  depend_de: [F001]\n", encoding="utf-8")
    r = run("check")
    check("check : écarter une F… dont une autre dépend est refusé",
          r.returncode == 1 and "CASCADE" in r.stdout, r.stdout)

    # 4. un cycle
    (dd / "fonctionnalites.yml").write_text(
        "- id: F001\n  libelle: a\n  domaine: socle\n  etat: décidé\n  jalon: 0\n  depend_de: [F002]\n"
        "- id: F002\n  libelle: b\n  domaine: socle\n  etat: décidé\n  jalon: 0\n  depend_de: [F001]\n", encoding="utf-8")
    r = run("check")
    check("check : un cycle de dépendances casse", r.returncode == 1 and "cycle" in r.stdout, r.stdout)

    # 5. un état hors de l'échelle unique
    (dd / "fonctionnalites.yml").write_text(
        "- id: F001\n  libelle: a\n  domaine: socle\n  etat: en cours\n  jalon: 0\n  depend_de: []\n"
        "- id: F002\n  libelle: b\n  domaine: socle\n  etat: décidé\n  jalon: 1\n  depend_de: []\n", encoding="utf-8")
    r = run("check")
    check("check : un état hors de l'échelle unique casse", r.returncode == 1 and "hors de l'échelle" in r.stdout, r.stdout)

    # 6. un jalon sans aucune fonctionnalité
    (dd / "fonctionnalites.yml").write_text(
        "- id: F001\n  libelle: a\n  domaine: socle\n  etat: décidé\n  jalon: 0\n  depend_de: []\n", encoding="utf-8")
    r = run("check")
    check("check : un jalon vide est un jalon qui ment", r.returncode == 1 and "jalon vide" in r.stdout, r.stdout)

    # 7. anonymat : un domaine réel dans un chapitre, un domaine fictif toléré
    (dd / "jalons.yml").write_text("- id: V0\n  titre: le socle\n", encoding="utf-8")
    ecrire(docs, "cdc-rm42-03-exemples.md", "# 03\n\nOn écrit à jean@client.fr pour l'exemple.\n")
    check("check : une adresse d'exemple ne fait pas crier le harnais", run("check").returncode == 0, run("check").stdout)
    ecrire(docs, "cdc-rm42-03-exemples.md", "# 03\n\nOn écrit à jean@vrai-client-bien-reel.fr.\n")
    r = run("check")
    check("check : un domaine réel est refusé (anonymisation)",
          r.returncode == 1 and "vrai-client-bien-reel.fr" in r.stdout, r.stdout)
    (dd / "anonymat.yml").write_text("- vrai-client-bien-reel.fr\n", encoding="utf-8")
    check("check : anonymat.yml admet un domaine déclaré fictif", run("check").returncode == 0, run("check").stdout)

print(("ÉCHEC — " + ", ".join(fails)) if fails else "OK")
sys.exit(1 if fails else 0)
