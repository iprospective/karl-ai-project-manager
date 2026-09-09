#!/usr/bin/env python3
"""pm-cdc — outillage du CDC complet : ouvrir, générer, vérifier (RM2967).

La méthode est dans la norme (`norms/src/modules/cdc.md`) ; ce script en porte la part
mécanique — celle qu'on ne doit pas faire à la main sous peine de divergence :

  pm-cdc.py init  --prefix rm2881 [--projet "<nom>"]   copie les gabarits dans docs/, renommés
  pm-cdc.py dict  [--chapitre 16]                      (re)génère le chapitre dictionnaire
  pm-cdc.py index [--out <fichier.json>]               le registre décisions+questions en JSON
  pm-cdc.py check                                      le harnais : cohérence du CDC lui-même

Options communes : --project <client>/<projet> (défaut : le workspace courant, via .mmi-pm),
--docs-dir (surcharge), --prefix (défaut : déduit du seul CDC présent).

Le dictionnaire vit dans `docs/cdc-<prefix>/dict/*.yml` (ou `docs/dict/*.yml`, forme
historique) ; il est la SOURCE, le chapitre est une VUE. Forme GÉNÉRIQUE (RM3015-D017, RM3061) :
un projet dont le CDC est `docs/cdc.md` + `cdc-<donnée>.md` a son dictionnaire dans `docs/dict/`
et son chapitre généré dans `docs/cdc-dict.md` (préfixe implicite `cdc`) ; `check` y lit les
identifiants fusionnés par pm-think-merge (`RM<id>-D001`). Voisin : `pm-cdc-features.py`
(RM3043) tient le registre d'un CDC *rétrospectif*, dérivé des tickets — voir la norme,
§ « Deux registres de fonctionnalités ».
"""
import argparse
import datetime
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

TABLES = ["entites", "champs", "relations", "enumerations", "workflows", "actions", "templates",
          "composants", "protocoles", "normes", "routes", "fonctionnalites", "jalons"]
ECHELLE = ["à trancher", "décidé", "maquetté", "codé", "éprouvé"]
HORS_CHAINE = ["en pause", "écarté"]


# ---------------------------------------------------------------- chemins

def resoudre(args):
    """docs/ du projet : --docs-dir, sinon --project, sinon le .mmi-pm du workspace courant."""
    if args.docs_dir:
        return Path(args.docs_dir)
    from pm_paths import PMConfig
    cfg = PMConfig.load()
    ref = args.project
    if not ref:
        mm = Path.cwd() / ".mmi-pm"
        if mm.exists():
            p = mm.resolve()
            ref = f"{p.parent.parent.name}/{p.name}"
    if not ref or "/" not in ref:
        sys.exit("--project <client>/<projet> requis (ou un workspace portant .mmi-pm)")
    c, p = ref.split("/", 1)
    return cfg.path("docs_dir", entity=c, project=p)


GENERIC = "cdc"          # RM3061 : la forme générique (docs/cdc.md + cdc-<donnée>.md, dict dans docs/dict/)
GENERIC_NUM = {"00": "cdc.md", "10": "cdc-features.md", "16": "cdc-dict.md", "90": "cdc-decisions.md",
               "91": "cdc-notes.md", "99": "cdc-questions.md"}
ID_RE = r"(?:RM\d+-)?"   # ids fusionnés par pm-think-merge : RM3044-D001 (forme générique) ; D001 (forme numérotée)


def prefixe(docs, demande):
    if demande:
        return demande.lower().lstrip("#")
    if (docs / "cdc.md").is_file():   # forme générique (D017) : les cdc-rm<id>-* à côté sont des CDC PAR TICKET (D015), pas le CDC projet
        return GENERIC
    vus = sorted({m.group(1) for f in docs.glob("cdc-*-*.md")
                  for m in [re.match(r"cdc-(.+?)-(?:\d\d|0N|1N)-", f.name)] if m})
    if len(vus) == 1:
        return vus[0]
    if not vus:
        if (docs / "cdc.md").is_file():
            return GENERIC
        sys.exit(f"aucun cdc-<prefix>-NN-*.md ni cdc.md sous {docs} — `pm-cdc.py init --prefix <p>` (ou pm-think-merge)")
    sys.exit("plusieurs CDC ici (%s) — préciser --prefix" % ", ".join(vus))


def dict_dir(docs, prefix):
    if prefix == GENERIC:
        return docs / "dict"
    for c in (docs / f"cdc-{prefix}" / "dict", docs / "dict"):
        if c.is_dir():
            return c
    return docs / f"cdc-{prefix}" / "dict"


def charge(dd, nom, defaut=None):
    f = dd / f"{nom}.yml"
    if not f.is_file():
        return defaut if defaut is not None else []
    v = yaml.safe_load(f.read_text(encoding="utf-8"))
    return v if v is not None else (defaut if defaut is not None else [])


def chapitres(docs, prefix):
    if prefix == GENERIC:   # cdc.md + cdc-<donnée>.md ; ni les CDC par ticket (cdc-rm<id>-*), ni les numérotés
        return sorted(f for f in docs.glob("cdc*.md") if f.name == "cdc.md"
                      or (re.match(r"^cdc-[a-z][a-z-]*\.md$", f.name) and not re.match(r"^cdc-rm\d+", f.name)))
    return sorted(docs.glob(f"cdc-{prefix}-*.md"))


def fichier(docs, prefix, num):
    if prefix == GENERIC:
        f = docs / GENERIC_NUM.get(str(num), f"cdc-{num}.md")
        return f if f.is_file() else None
    for f in chapitres(docs, prefix):
        if re.match(rf"cdc-{re.escape(prefix)}-{num}\b", f.name):
            return f
    return None


# ---------------------------------------------------------------- init

def init(docs, prefix, projet):
    src = Path(__file__).resolve().parent.parent / "templates" / "cdc"
    if not src.is_dir():
        sys.exit(f"gabarits introuvables : {src}")
    if chapitres(docs, prefix):
        sys.exit(f"un CDC cdc-{prefix}-* existe déjà sous {docs} — rien touché")
    docs.mkdir(parents=True, exist_ok=True)
    dd = docs / f"cdc-{prefix}" / "dict"
    dd.mkdir(parents=True, exist_ok=True)
    ecrits = []
    for f in sorted(src.glob("*.md")):
        if f.name == "README.md":
            continue
        # les chapitres sont des pages du wiki (plats, numérotés) ; la grille et la trame
        # d'entretien sont des OUTILS de travail : elles vivent avec les sources, pas au wiki.
        chapitre = bool(re.match(r"(?:\d\d|0N|1N)-", f.name))
        cible = (docs / f"cdc-{prefix}-{f.name}") if chapitre else (dd.parent / f.name)
        t = f.read_text(encoding="utf-8").replace("RMXXXX", prefix.upper()).replace("<projet>", projet or "<projet>")
        cible.write_text(t, encoding="utf-8")
        ecrits.append(cible.name)
    for f in sorted((src / "dict").glob("*.yml")):
        (dd / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        ecrits.append(f"dict/{f.name}")
    print(f"✓ CDC cdc-{prefix} ouvert sous {docs} — {len(ecrits)} fichier(s)")
    print("  gabarits 0N-/1N- : à DUPLIQUER par chapitre (le N n'est pas un numéro)")
    return ecrits


# ---------------------------------------------------------------- dictionnaire

def cel(v):
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "oui" if v else "non"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) if v else "—"
    return str(v).replace("|", "\\|").replace("\n", " ").strip()


def refs(v):
    return ", ".join("**%s**" % x for x in v) if v else "—"


def table(cols, lignes):
    out = ["| " + " | ".join(c[0] for c in cols) + " |", "|" + "---|" * len(cols)]
    for l in lignes:
        out.append("| " + " | ".join(cel(c[1](l)) for c in cols) + " |")
    return "\n".join(out)


def g(k):
    return lambda d: d.get(k)


def jal(v):
    """Un jalon se lit `V0`, `V1` — le numéro nu se confond avec un rang."""
    return "—" if v is None else ("V%d" % v if isinstance(v, int) else str(v))


def ordre_realisation(feats):
    """Tri topologique stable de `depend_de` : l'ordre de codage est un calcul, pas un avis."""
    par = {f["id"]: f for f in feats}
    deps = {f["id"]: [d for d in (f.get("depend_de") or []) if d in par] for f in feats}
    entrants = {k: len(v) for k, v in deps.items()}
    suiv = {}
    for k, v in deps.items():
        for d in v:
            suiv.setdefault(d, []).append(k)
    rang = lambda k: (par[k].get("jalon") if par[k].get("jalon") is not None else 99, k)
    prets = sorted([k for k, n in entrants.items() if n == 0], key=rang)
    ordre = []
    while prets:
        k = prets.pop(0)
        ordre.append(k)
        for s in suiv.get(k, []):
            entrants[s] -= 1
            if entrants[s] == 0:
                prets.append(s)
                prets.sort(key=rang)
    return ordre, [k for k, n in entrants.items() if n > 0], par


def avancement(feats):
    n = {}
    for f in feats:
        n[f.get("etat")] = n.get(f.get("etat"), 0) + 1
    return " · ".join("**%s** %d" % (k, n[k]) for k in (ECHELLE[::-1] + HORS_CHAINE) if n.get(k))


def build_dict(dd, chapitre, prefix):
    d = {t: charge(dd, t, {} if t in ("champs", "composants", "enumerations") else []) for t in TABLES}
    E, CH, REL, EN = d["entites"], d["champs"], d["relations"], d["enumerations"]
    WF, ACT, TPL, CMP = d["workflows"], d["actions"], d["templates"], d["composants"]
    PRO, NOR, ROU, FEA, JAL = d["protocoles"], d["normes"], d["routes"], d["fonctionnalites"], d["jalons"]
    md = []
    w = md.append
    n = chapitre
    w(f"# {n} — Dictionnaire des données\n" if prefix != GENERIC else "# Dictionnaire des données\n")
    w("> **Fichier généré** le %s par `pm-cdc.py dict` depuis `dict/*.yml`. Ne pas éditer à la main : "
      "modifier les YAML, qui sont la source — du CDC, du POC, et plus tard du schéma, des classes et de "
      "la spécification d'API dans le langage et le SGBD retenus.\n" % datetime.date.today().isoformat())
    w("Ce chapitre fait autorité sur **ce qui existe** ; le registre des décisions fait autorité sur "
      "**pourquoi**. Les types sont **logiques**, jamais SQL tant que le SGBD n'est pas statué.\n")
    w("| Table | Lignes |\n|---|---|")
    for lib, v in (("Entités", E), ("Relations", REL), ("Énumérations", EN), ("Workflows", WF),
                   ("Actions", ACT), ("Templates", TPL), ("Protocoles", PRO), ("Normes", NOR),
                   ("Routes", ROU), ("Fonctionnalités", FEA), ("Jalons", JAL)):
        w("| %s | %d |" % (lib, len(v)))
    w("| Champs | %d |" % sum(len(v) for v in CH.values()))
    w("| Composants | %d |" % sum(len(v) for v in CMP.values()))
    s = 0

    def sec(titre):
        nonlocal s
        s += 1
        w(f"\n---\n\n## {n}.{s} — {titre}\n")

    if E:
        sec("Entités")
        doms = []
        for e in E:
            if e.get("domaine") not in doms:
                doms.append(e.get("domaine"))
        for dom in doms:
            if dom:
                w("\n### %s\n" % str(dom).capitalize())
            for e in [x for x in E if x.get("domaine") == dom]:
                w("#### `%s` %s\n" % (e["nom"], e.get("etat", "")))
                w(cel(e.get("role")) + "\n")
                extra = []
                if e.get("partition") is not None:
                    extra.append("**Partition** : %s" % e["partition"])
                if e.get("jalon") is not None:
                    extra.append("**Jalon** : %s" % jal(e["jalon"]))
                extra.append("**Décisions** : %s" % refs(e.get("decisions")))
                if e.get("notes"):
                    extra.append("*%s*" % e["notes"])
                w("  \n".join(extra) + "\n")
                champs = CH.get(e.get("id"))
                if champs:
                    w(table([("Champ", g("nom")), ("Type", g("type")), ("Oblig.", g("obligatoire")),
                             ("Nature", g("nature")), ("Rôle", g("role"))], champs) + "\n")
    if REL:
        sec("Relations")
        w(table([("De", g("de")), ("Vers", g("vers")), ("Card.", g("cardinalite")), ("Datée", g("datee")),
                 ("Rôle", g("role")), ("Décision", g("decision"))], REL))
    if EN:
        sec("Énumérations")
        for nom, en in EN.items():
            w("\n### `%s`\n\n%s\n" % (nom, cel(en.get("role"))))
            vals = en.get("valeurs", [])
            cols = [("Valeur", g("id")), ("Libellé", g("libelle"))]
            for k in sorted({k for v in vals for k in v} - {"id", "libelle", "note"}):
                cols.append((k, g(k)))
            cols.append(("Note", g("note")))
            w(table(cols, vals))
            if en.get("questions"):
                w("\n*Questions ouvertes : %s*" % refs(en["questions"]))
    if WF:
        sec("Workflows")
        for wf in WF:
            w("\n### %s\n" % wf["nom"])
            w("Entité `%s`%s — décisions %s\n" % (wf.get("entite"),
              (", champ `%s`" % wf["champ"]) if wf.get("champ") else "", refs(wf.get("decisions"))))
            if wf.get("etats"):
                w("États : %s\n" % " → ".join("`%s`" % x for x in wf["etats"]))
            if wf.get("regles"):
                w("\n".join("- %s" % r for r in wf["regles"]) + "\n")
            if wf.get("transitions"):
                w(table([("De", g("de")), ("Vers", g("vers")), ("Geste", g("geste")), ("Qui", g("qui")),
                         ("Effet", g("effet"))], wf["transitions"]))
            if wf.get("garde_fous"):
                w("\n**Garde-fous** :\n" + "\n".join("- %s" % r for r in wf["garde_fous"]))
            w("")
    if ACT:
        sec("Actions")
        w("Chaque geste que l'interface ou l'API permet. *Portée* : ce que le geste modifie.\n")
        w(table([("Action", g("libelle")), ("Contexte", g("contexte")), ("Portée", g("portee")),
                 ("Effet", g("effet")), ("Trace", g("trace")),
                 ("Décisions", lambda a: refs(a.get("decisions")))], ACT))
    if TPL:
        sec("Templates (vues partielles)")
        w(table([("Partielle", lambda t: "`%s`" % t["nom"]), ("Contexte", g("contexte")), ("Rôle", g("role")),
                 ("Surchargeable", g("surchargeable")), ("Variantes", g("variantes")), ("Appelle", g("appelle"))], TPL))
    if CMP:
        sec("Composants réutilisables")
        for fam, lignes in CMP.items():
            w("\n### %s\n" % str(fam).capitalize())
            cols = [("Composant", g("nom")), ("Rôle", g("role"))]
            for k in ("contrat", "fournisseurs", "exigences"):
                if any(k in c for c in lignes):
                    cols.append((k.capitalize(), g(k)))
            cols.append(("Décisions", lambda c: refs(c.get("decisions"))))
            w(table(cols, lignes))
    if PRO:
        sec("Protocoles")
        w(table([("Protocole", g("nom")), ("Sens", g("sens")), ("Jalon", lambda p: jal(p.get("jalon"))), ("Rôle", g("role")),
                 ("Normes", g("normes")), ("Décisions", lambda p: refs(p.get("decisions")))], PRO))
    if NOR:
        sec("Normes à respecter")
        w("Une norme par ligne, avec le point précis qui engage le projet.\n")
        w(table([("Référence", g("id")), ("Type", g("type")), ("Nom", g("nom")),
                 ("Ce que ça engage", g("engage"))], NOR))
    if ROU:
        sec("Routes d'API")
        w(table([("Méthode", g("methode")), ("Chemin", lambda r: "`%s`" % r["chemin"]), ("Rôle", g("role")),
                 ("Portée", g("portee")), ("Entités", g("entites")), ("État", g("etat")),
                 ("Décisions", lambda r: refs(r.get("decisions")))], ROU))
    if FEA:
        sec("L'état d'une fonctionnalité")
        w("**Une seule échelle**, ordonnée : on ne code pas ce qui n'est pas décidé, et une "
          "fonctionnalité ne recule pas. Deux champs auraient été deux vérités à tenir d'accord.\n")
        w("| État | ce que ça veut dire |\n|---|---|")
        for v, sens in (("à trancher", "une question ouverte la bloque — elle est dans `questions`"),
                        ("décidé", "tranché au CDC : la règle est écrite, rien n'est construit"),
                        ("maquetté", "l'interface le montre, aucun serveur derrière"),
                        ("codé", "écrit et testé des deux côtés, jamais confronté au réel"),
                        ("éprouvé", "a tourné **pour de vrai** — le seul état qui vaille une promesse à un client"),
                        ("en pause", "*hors chaîne* : écarté pour l'instant, avec sa condition de reprise (⏸)"),
                        ("écarté", "*hors chaîne* : abandon ou doublon ; la ligne reste, jalon `null`, l'identifiant jamais réattribué")):
            w("| **%s** | %s |" % (v, sens))
        w("\nTous jalons confondus : " + (avancement(FEA) or "—") + ".\n")
        _ordre, _cycle, _par = ordre_realisation(FEA)
        _rang = {k: i for i, k in enumerate(_ordre)}
        if JAL:
            sec("Feuille de route")
            w("Chaque jalon liste **toutes** ses fonctionnalités, **dans l'ordre de réalisation**. "
              "C'est la même donnée que la liste par domaine, organisée autrement.\n")
            for j in JAL:
                v = j["id"]
                num = int(re.sub(r"\D", "", str(v)) or 0)
                feats = sorted([f for f in FEA if f.get("jalon") == num],
                               key=lambda f: (_rang.get(f["id"], 10 ** 6), f["id"]))
                w("\n### %s — %s *(%s)* — %d fonctionnalités\n" % (v, j.get("titre", ""), j.get("etat", ""), len(feats)))
                if feats:
                    w("**Avancement** : " + avancement(feats) + ".\n")
                if j.get("note"):
                    w("> %s\n" % j["note"])
                if j.get("contenu"):
                    w("*Intention :* " + " · ".join(j["contenu"]) + "\n")
                if feats:
                    w(table([("Ordre", lambda f: (_rang[f["id"]] + 1) if f["id"] in _rang else "—"), ("#", g("id")),
                             ("Fonctionnalité", g("libelle")), ("Domaine", g("domaine")), ("État", g("etat")),
                             ("Ticket", lambda f: ("RM%s" % f["ticket"]) if f.get("ticket") else "—"),
                             ("Dépend de", lambda f: f.get("depend_de") if f.get("depend_de") is not None else "à renseigner")],
                            feats))
            ecartees = [f for f in FEA if f.get("jalon") is None]
            if ecartees:
                w("\n### Écartées volontairement — %d\n" % len(ecartees))
                w(table([("#", g("id")), ("Fonctionnalité", g("libelle")), ("État", g("etat")),
                         ("Questions", lambda f: refs(f.get("questions")))], ecartees))
        sec("Ordre de réalisation")
        w("Calculé depuis `depend_de` (tri topologique, stable par jalon puis identifiant). **C'est "
          "l'ordre dans lequel coder** : une fonctionnalité n'apparaît qu'après tout ce dont elle "
          "dépend. Les identifiants sont stables — on n'en réattribue jamais un.\n")
        ren = [f for f in FEA if f.get("depend_de") is not None]
        w("| Renseignées | Racines | À renseigner (`null`) | Cycle |\n|---|---|---|---|")
        w("| %d / %d | %d | %d | %s |" % (len(ren), len(FEA), sum(1 for f in ren if not f["depend_de"]),
                                          len(FEA) - len(ren), ("⚠ " + ", ".join(_cycle)) if _cycle else "aucun"))
        w("")
        w(table([("Rang", lambda k: _ordre.index(k) + 1), ("#", lambda k: k),
                 ("Fonctionnalité", lambda k: _par[k].get("libelle")),
                 ("Jalon", lambda k: jal(_par[k].get("jalon"))),
                 ("Dépend de", lambda k: _par[k].get("depend_de") or "—")],
                [k for k in _ordre if _par[k].get("depend_de") is not None]))
        sec("Fonctionnalités")
        doms = []
        for f in FEA:
            if f.get("domaine") not in doms:
                doms.append(f.get("domaine"))
        for dom in doms:
            w("\n### %s\n" % (dom or "—"))
            w(table([("#", g("id")), ("Fonctionnalité", g("libelle")),
                     ("Jalon", lambda f: jal(f.get("jalon"))), ("État", g("etat")),
                     ("Ticket", lambda f: ("RM%s" % f["ticket"]) if f.get("ticket") else "—"),
                     ("Dépend de", lambda f: f.get("depend_de") if f.get("depend_de") is not None else "à renseigner"),
                     ("Décisions", lambda f: refs(f.get("decisions"))),
                     ("Questions", lambda f: refs(f.get("questions")))],
                    [f for f in FEA if f.get("domaine") == dom]))
    return "\n".join(md) + "\n"


# ---------------------------------------------------------------- index

def propre(t):
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = t.replace("~~", "").replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", t).strip()


def lignes_table(texte):
    """Les lignes des tableaux markdown, découpées en cellules propres."""
    out = []
    for l in texte.splitlines():
        l = l.strip()
        if l.startswith("|") and not re.match(r"^\|[\s:|-]+\|$", l):
            cells = [propre(c) for c in l.strip("|").split("|")]
            if len(cells) >= 2:
                out.append(cells)
    return out


def index(docs, prefix):
    """Le registre (90) et les questions (99), lus dans leurs tableaux de synthèse."""
    dec, que = [], []
    f90 = fichier(docs, prefix, "90")
    if f90:
        for c in lignes_table(f90.read_text(encoding="utf-8")):
            if re.fullmatch(ID_RE + r"D\d{3}[a-z]?", c[0]):
                dec.append({"id": c[0], "objet": c[1] if len(c) > 1 else "", "etat": c[2] if len(c) > 2 else ""})
    f99 = fichier(docs, prefix, "99")
    if f99:
        for c in lignes_table(f99.read_text(encoding="utf-8")):
            if re.fullmatch(ID_RE + r"Q\d{3}", c[0]):
                que.append({"id": c[0], "objet": c[1] if len(c) > 1 else "",
                            "urgence": c[-1] if len(c) > 2 else ""})
    return {"prefix": prefix, "genere_le": datetime.date.today().isoformat(),
            "decisions": dec, "questions": que}


# ---------------------------------------------------------------- check

ADRESSE = re.compile(r"[\w.+-]+@([\w-]+\.[a-z]{2,})", re.I)
# Domaines admis comme fictifs. Un CDC illustre avec des adresses : les interdire toutes
# ferait crier le contrôle à chaque exemple, et « une alerte qui se déclenche une fois sur
# deux n'est plus lue ». Surchargeable par `anonymat: [domaines]` dans dict/… ou un
# `anonymat.yml` à côté du dictionnaire — ce qui reste signalé est ce qui est RÉEL.
FICTIFS = ("exemple.fr", "exemple.com", "example.com", "example.org", "example.net", "test.fr",
           "invalid", "localhost", "domain.tld", "client.fr", "fournisseur.fr", "societe.fr",
           "nous.fr", "x.fr", "y.fr", "monentreprise.fr", "acme.fr", "acme.com")


def groupe(ids, maxi=6):
    """Une famille d'avertissements tient sur une ligne : crier soixante fois, c'est ne plus être lu."""
    ids = list(ids)
    return ", ".join(ids[:maxi]) + (f"… (+{len(ids) - maxi})" if len(ids) > maxi else "")


def check(docs, prefix):
    """Le harnais du CDC : ce qui casse au commit plutôt que six mois après."""
    dd = dict_dir(docs, prefix)
    d = {t: charge(dd, t, {} if t in ("champs", "composants", "enumerations") else []) for t in TABLES}
    idx = index(docs, prefix)
    dec_ids = {x["id"] for x in idx["decisions"]}
    que_ids = {x["id"] for x in idx["questions"]}
    err, avert = [], []
    textes = {f.name: f.read_text(encoding="utf-8") for f in chapitres(docs, prefix)}

    # 1. décisions rédigées mais absentes du tableau de synthèse (et réciproquement)
    f90 = fichier(docs, prefix, "90")
    if f90:
        redigees = set(re.findall(r"^#{2,4}\s+(D\d{3}[a-z]?)\b", textes[f90.name], re.M))
        for x in sorted(redigees - dec_ids):
            err.append(f"{x} : rédigée en section, absente du tableau de synthèse — invisible de tout ce qui lit l'index")
        orphelines = sorted(dec_ids - redigees)
        if orphelines:
            avert.append("au tableau de synthèse sans section rédigée (%d) : %s"
                         % (len(orphelines), groupe(orphelines)))

    # 2. références mortes dans les chapitres et le dictionnaire
    corpus = re.sub(r"`[^`]*`", " ", "\n".join(textes.values())) + "\n" + yaml.safe_dump(d, allow_unicode=True)
    for x in sorted(set(re.findall(r"\b" + ID_RE + r"D\d{3}[a-z]?\b", corpus)) - dec_ids):
        if prefix == GENERIC and not x.startswith("RM"):
            continue   # forme générique : un D001 nu est un id LOCAL d'un think (RM<id>-D001 au registre), pas une référence
        err.append(f"{x} : citée, absente du registre")
    for x in sorted(set(re.findall(r"\b" + ID_RE + r"Q\d{3}\b", corpus)) - que_ids):
        if prefix == GENERIC and not x.startswith("RM"):
            continue
        err.append(f"{x} : citée, absente des questions ouvertes")

    # 3. identifiants à trois chiffres
    courts = sorted(set(re.findall(r"\b[DQCFNU]\d{1,2}\b", corpus)))
    if courts:
        avert.append("identifiants à moins de trois chiffres (%d) : %s — le tri lexical cesse de "
                     "suivre le tri numérique" % (len(courts), groupe(courts)))

    # 4. dictionnaire : relations et champs pointent des entités déclarées
    ents = {e.get("id") for e in d["entites"]}
    for r in d["relations"]:
        for cote in ("de", "vers"):
            v = str(r.get(cote, "")).split(".")[0]
            if v and v not in ents:
                err.append(f"relation {r.get('de')} → {r.get('vers')} : `{v}` n'est pas une entité déclarée")
    for k in d["champs"]:
        if k not in ents:
            err.append(f"champs.yml : `{k}` n'est pas une entité déclarée")

    # 5. fonctionnalités : états, cycles, dépendances, jalon ultérieur, écartées en cascade
    FEA = d["fonctionnalites"]
    par = {f["id"]: f for f in FEA}
    sans_dep = []
    for f in FEA:
        if f.get("etat") not in ECHELLE + HORS_CHAINE:
            err.append(f"{f['id']} : état « {f.get('etat')} » hors de l'échelle ({' → '.join(ECHELLE)})")
        for x in (f.get("depend_de") or []):
            if x not in par:
                err.append(f"{f['id']} : dépend de `{x}`, qui n'existe pas")
        if f.get("depend_de") is None:
            sans_dep.append(f["id"])
    if sans_dep:
        avert.append("`depend_de` non renseigné (%d) : %s — `null` (pas encore renseigné) et `[]` "
                     "(aucune dépendance) ne doivent jamais se confondre" % (len(sans_dep), groupe(sans_dep)))
    _, cycle, _ = ordre_realisation(FEA)
    if cycle:
        err.append("cycle de dépendances : " + ", ".join(sorted(cycle)))
    for f in FEA:
        if f.get("jalon") is None:
            for autre in FEA:
                if f["id"] in (autre.get("depend_de") or []) and autre.get("jalon") is not None:
                    err.append(f"{autre['id']} (jalon {autre['jalon']}) dépend de {f['id']}, écartée — "
                               "écarter est une suppression EN CASCADE")
            continue
        for x in (f.get("depend_de") or []):
            j = par.get(x, {}).get("jalon")
            if j is not None and j > f["jalon"]:
                err.append(f"{f['id']} (jalon {f['jalon']}) dépend de {x} (jalon {j}) — un jalon ne peut "
                           "pas dépendre d'un jalon ultérieur")

    # 6. jalons vides
    jalons_utilises = {f.get("jalon") for f in FEA}
    for j in (d["jalons"] if FEA else []):   # forme générique : les fonctionnalités vivent dans docs/cdc/ (pm-cdc-features), pas ici
        num = int(re.sub(r"\D", "", str(j.get("id"))) or 0)
        if num not in jalons_utilises:
            err.append(f"jalon {j.get('id')} : aucune fonctionnalité — un jalon vide est un jalon qui ment")

    # 7. vrac : chaque note tracée jusqu'à sa résolution
    f91 = fichier(docs, prefix, "91")
    if f91:
        suspens = [c[0] for c in lignes_table(textes[f91.name])
                   if re.fullmatch(r"[NU]\d{3}", c[0]) and (len(c) < 3 or not c[-1] or c[-1] in ("—", "🕐", "en suspens"))]
        if suspens:
            avert.append("vrac en suspens : " + ", ".join(suspens))

    # 8. anonymisation : ni adresse ni domaine réels dans un CDC
    fictifs = set(FICTIFS) | set(charge(dd, "anonymat", []) or [])
    reels = {}
    for nom, t in textes.items():
        for dom in ADRESSE.findall(t):
            if dom.lower() not in fictifs:
                reels.setdefault(dom.lower(), set()).add(nom)
    for dom, ou in sorted(reels.items()):
        err.append("domaine réel « %s » dans %s — un CDC ne porte ni nom de client, ni adresse, ni "
                   "domaine réel (ajouter à `anonymat.yml` s'il est fictif)" % (dom, ", ".join(sorted(ou))))

    # 9. questions tranchées encore listées comme ouvertes
    for q in idx["questions"]:
        if "tranch" in q["urgence"].lower() and "haute" in q["urgence"].lower():
            avert.append(f"{q['id']} : marquée tranchée ET urgente")

    for x in avert:
        print("  ~ " + x)
    for x in err:
        print("  ✗ " + x)
    print("%s CDC %s : %d décision(s), %d question(s), %d fonctionnalité(s) — %d erreur(s), %d avertissement(s)"
          % ("✗" if err else "✓", ("cdc.md" if prefix == GENERIC else "cdc-" + prefix), len(dec_ids), len(que_ids), len(FEA), len(err), len(avert)))
    return 1 if err else 0


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("commande", choices=["init", "dict", "index", "check"])
    ap.add_argument("--project")
    ap.add_argument("--docs-dir")
    ap.add_argument("--prefix")
    ap.add_argument("--projet", help="init : le nom du projet, substitué à <projet>")
    ap.add_argument("--chapitre", default="16", help="dict : le numéro du chapitre (défaut 16)")
    ap.add_argument("--out", help="index : fichier JSON de sortie (défaut : stdout)")
    a = ap.parse_args()
    docs = resoudre(a)

    if a.commande == "init":
        if not a.prefix:
            sys.exit("init exige --prefix <p> (ex. rm2881)")
        init(docs, a.prefix.lower(), a.projet)
        return 0

    prefix = prefixe(docs, a.prefix)
    if a.commande == "dict":
        dd = dict_dir(docs, prefix)
        if not dd.is_dir():
            sys.exit(f"aucun dictionnaire sous {dd}")
        cible = (docs / "cdc-dict.md") if prefix == GENERIC else (fichier(docs, prefix, a.chapitre) or docs / f"cdc-{prefix}-{a.chapitre}-dictionnaire.md")
        cible.write_text(build_dict(dd, a.chapitre, prefix), encoding="utf-8")
        print(f"✓ {cible.name} régénéré depuis {dd}")
        return 0
    if a.commande == "index":
        idx = index(docs, prefix)
        txt = json.dumps(idx, ensure_ascii=False, indent=1)
        if a.out:
            Path(a.out).write_text(txt + "\n", encoding="utf-8")
            print(f"✓ {a.out} : {len(idx['decisions'])} décision(s), {len(idx['questions'])} question(s)")
        else:
            print(txt)
        return 0
    return check(docs, prefix)


if __name__ == "__main__":
    sys.exit(main())
