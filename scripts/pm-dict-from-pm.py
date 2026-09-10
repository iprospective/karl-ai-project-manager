#!/usr/bin/env python3
"""pm-dict-from-pm — les tables GÉNÉRÉES du dictionnaire des données du projet PM (RM3061).

Le dictionnaire (`docs/dict/*.yml`, modèle AtomBox) est la source du chapitre `cdc-dict.md`. Pour le
système PM lui-même, une partie du modèle est DÉJÀ écrite ailleurs — gabarits, KERNEL NORMS, carte des
routes, modules du cockpit, scripts. La recopier à la main garantirait qu'elle diverge : ce script
dérive ces tables du code et les réécrit entièrement (en-tête « GÉNÉRÉ »). Les tables CURÉES
(entites, relations, workflows, protocoles, jalons) ne sont jamais touchées.

  champs.yml        frontmatter de templates/task.md, project-overview.md, client-overview.md (commentaires = rôle)
  enumerations.yml  § « Valeurs énumérées » de norms/src/NORMS-KERNEL.md
  normes.yml        les garde-fous (tripwires) du KERNEL
  routes.yml        deploy/karl-agent/cockpit/MIGRATION-ROUTES.tsv (routes cibles /api/<type>/<action>)
  composants.yml    noyau (cockpit/src/core) et modules (cockpit/src/modules), rôle = 1re ligne de commentaire
  actions.yml       les scripts pm-*.py (id = verbe mmi-pm, libellé = docstring)
  templates.yml     templates/*.md, templates/aspects/**, templates/bootstrap-tasks/**

  pm-dict-from-pm.py [--project iprospective/pm-ai-agents] [--docs-dir <docs>] [--repo <racine du repo PM>] [--check]
  --check : les tables générées sont-elles à jour ? (exit 1 sinon) — garde de livraison
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

REPO = Path(__file__).resolve().parent.parent
HEAD = "# {table} — table GÉNÉRÉE par scripts/pm-dict-from-pm.py depuis {source} (RM3061). Ne pas éditer : relancer le script.\n"


def dump(table, source, data):
    return HEAD.format(table=table, source=source) + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=140)


# ---------------------------------------------------------------- champs (gabarits)
TYPE_GUESS = [(r"_id$|^id$|redmine_id", "id"), (r"_at$|^updated$|^created$|^due$|^at$", "horodatage"), (r"_url$|^url$", "court"),
              (r"^(tokens|cost|time|minutes|pct|count|total)|_(tokens|minutes|usd|pct|total)$|_eur$", "entier")]


def champs_de(md: Path, entite: str):
    """Les clés du frontmatter (2 niveaux) d'un gabarit, avec le commentaire de fin de ligne comme rôle."""
    txt = md.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---", txt, re.S)
    if not m:
        return []
    out, parent = [], None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        body, _, comment = line.partition("#")
        key, _, val = body.strip().partition(":")
        if not key or key.startswith("-"):
            continue
        val = val.strip(); comment = comment.strip()
        if indent == 0:
            parent = key
            nom = key
        elif indent <= 2 and parent:
            nom = f"{parent}.{key}"
        else:
            continue
        if val == "" and not comment and indent == 0:
            # bloc parent (team:, roi:, bug: …) : une ligne de structure
            out.append({"nom": nom, "type": "json", "obligatoire": "non", "role": "bloc structuré (voir ses champs)"})
            continue
        typ = "court"
        if val in ("[]",):
            typ = "json"
        elif val in ("null", "") and comment:
            typ = next((t for rx, t in TYPE_GUESS if re.search(rx, key)), "court")
        elif re.fullmatch(r"-?\d+(\.\d+)?", val):
            typ = "decimal" if "." in val else "entier"
        elif val in ("true", "false"):
            typ = "bool"
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", val):
            typ = "date"
        elif "|" in comment:
            typ = "enum"
        else:
            typ = next((t for rx, t in TYPE_GUESS if re.search(rx, key)), "court")
        oblig = "oui" if "OBLIGATOIRE" in comment.upper() else ("non" if val in ("null", "", "[]") else "condition")
        out.append({"nom": nom, "type": typ, "obligatoire": oblig, "role": comment or f"valeur par défaut `{val}`"})
    return out


def gen_champs(repo):
    src = {"tache": repo / "templates" / "task.md", "projet": repo / "templates" / "project-overview.md",
           "client": repo / "templates" / "client-overview.md"}
    return {k: champs_de(v, k) for k, v in src.items() if v.is_file()}


# ---------------------------------------------------------------- énumérations + normes (KERNEL)
def gen_enums(repo):
    txt = (repo / "norms" / "src" / "NORMS-KERNEL.md").read_text(encoding="utf-8")
    m = re.search(r"^## Valeurs énumérées\n(.*?)(?=^## )", txt, re.S | re.M)
    out = {}
    if not m:
        return out
    for sec in re.split(r"^### ", m.group(1), flags=re.M)[1:]:
        nom, _, corps = sec.partition("\n")
        vals = re.findall(r"`([^`]+)`", corps.split("\n\n")[0])
        role = re.sub(r"\s+", " ", " ".join(l for l in corps.split("\n\n")[1:2])).strip()[:220]
        key = re.sub(r"[^a-z0-9_.]", "_", nom.strip().lower())
        out[key] = {"role": role or f"valeurs admises du champ `{nom.strip()}` (NORMS KERNEL)",
                    "valeurs": [{"id": v, "libelle": v} for v in vals]}
    return out


def gen_normes(repo):
    txt = (repo / "norms" / "src" / "NORMS-KERNEL.md").read_text(encoding="utf-8")
    m = re.search(r"^## Tripwires.*?\n(.*?)(?=^## )", txt, re.S | re.M)
    out = []
    if not m:
        return out
    for num, titre, corps in re.findall(r"^(\d+)\. \*\*(.+?)\*\*\s*(.*?)(?=^\d+\. \*\*|\Z)", m.group(1), re.S | re.M):
        engage = re.sub(r"\s+", " ", corps).strip()
        engage = re.sub(r"\s*→ `[^`]+`\s*$", "", engage)[:300]
        out.append({"id": f"GF{int(num):02d}", "type": "referentiel", "nom": f"Garde-fou {num} — {titre.rstrip('.')}", "engage": engage})
    return out


# ---------------------------------------------------------------- routes (carte)
def gen_routes(repo):
    tsv = repo / "deploy" / "karl-agent" / "cockpit" / "MIGRATION-ROUTES.tsv"
    out = []
    for l in tsv.read_text(encoding="utf-8").splitlines()[1:]:
        cur, lot, dom, tgt, n, ex = (l.split("\t") + [""] * 6)[:6]
        out.append({"methode": "GET/POST", "chemin": tgt, "role": f"domaine `{dom}` — appelée par {ex.replace(';', ', ')}" if ex else f"domaine `{dom}`",
                    "portee": "jeton d'appareil (auth requise) sauf cockpit-config/login", "entites": [dom], "etat": "livrée",
                    "historique": cur})
    return out


# ---------------------------------------------------------------- composants (cockpit)
def premiere_ligne(f: Path):
    for l in f.read_text(encoding="utf-8", errors="replace").splitlines()[:4]:
        if l.startswith("//"):
            return re.sub(r"^//\s*", "", l).strip()
    return ""


def gen_composants(repo):
    ck = repo / "deploy" / "karl-agent" / "cockpit" / "src"
    noyau = [{"id": f.stem, "nom": f.stem, "role": premiere_ligne(f), "contrat": f"import « ../core/{f.name} »", "poc": f"src/core/{f.name}"}
             for f in sorted((ck / "core").glob("*.js"))]
    modules = []
    for d in sorted(p for p in (ck / "modules").iterdir() if p.is_dir()):
        ctrl = next(iter(sorted(d.glob("*.controller.js"))), None) or next(iter(sorted(d.glob("*.js"))), None)
        modules.append({"id": d.name, "nom": d.name, "role": premiere_ligne(ctrl) if ctrl else "", "contrat": f"{len(list(d.glob('*.js')))} fichier(s) : service / repository / ViewModel / vue / contrôleur", "poc": f"src/modules/{d.name}/"})
    return {"noyau": noyau, "module": modules}


# ---------------------------------------------------------------- actions (scripts pm-*)
def gen_actions(repo):
    out = []
    for f in sorted((repo / "scripts").glob("pm-*.py")):
        doc = ""
        for l in f.read_text(encoding="utf-8", errors="replace").splitlines()[1:6]:
            if '"""' in l:
                doc = l.replace('"""', "").strip(); break
        lib = re.sub(r"^pm-[a-z0-9-]+(\.py)?\s*[—-]\s*", "", doc).strip() or doc
        out.append({"id": f.stem[3:], "libelle": lib[:160], "contexte": "cli", "portee": "données PM (core), Redmine, forge selon le verbe",
                    "effet": f"`mmi-pm {f.stem[3:]}` → `scripts/{f.name}`", "trace": "oui" if re.search(r"task|status|comment|link|deliver|take|mr|promote", f.stem) else "non"})
    return out


# ---------------------------------------------------------------- templates (gabarits)
def gen_templates(repo):
    out = []
    for f in sorted((repo / "templates").rglob("*.md")):
        rel = f.relative_to(repo / "templates").as_posix()
        titre = ""
        for l in f.read_text(encoding="utf-8", errors="replace").splitlines()[:40]:
            m = re.match(r"^(?:title:\s*|# )(.+)$", l)
            if m:
                titre = m.group(1).strip().strip('"'); break
        ctx = rel.split("/")[0] if "/" in rel else "racine"
        out.append({"nom": rel, "contexte": ctx, "role": titre or rel, "surchargeable": "oui" if ctx == "aspects" else "non", "appelle": []})
    return out


GEN = {"champs": ("gabarits templates/*.md", gen_champs), "enumerations": ("norms/src/NORMS-KERNEL.md § Valeurs énumérées", gen_enums),
       "normes": ("norms/src/NORMS-KERNEL.md § Tripwires", gen_normes), "routes": ("deploy/karl-agent/cockpit/MIGRATION-ROUTES.tsv", gen_routes),
       "composants": ("deploy/karl-agent/cockpit/src", gen_composants), "actions": ("scripts/pm-*.py", gen_actions), "templates": ("templates/", gen_templates)}


def resoudre(a):
    if a.docs_dir:
        return Path(a.docs_dir)
    from pm_paths import PMConfig
    cfg = PMConfig.load()
    ref = a.project or "iprospective/pm-ai-agents"
    c, p = ref.split("/", 1)
    return cfg.path("docs_dir", entity=c, project=p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project"); ap.add_argument("--docs-dir"); ap.add_argument("--repo"); ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    repo = Path(a.repo) if a.repo else REPO
    dd = resoudre(a) / "dict"; dd.mkdir(parents=True, exist_ok=True)
    stale = []
    for table, (source, fn) in GEN.items():
        txt = dump(table, source, fn(repo)); f = dd / f"{table}.yml"
        if a.check:
            if not f.is_file() or f.read_text(encoding="utf-8") != txt:
                stale.append(table)
        else:
            f.write_text(txt, encoding="utf-8")
    if a.check:
        if stale:
            print("✗ tables générées périmées : " + ", ".join(stale) + " — relancer pm-dict-from-pm"); return 1
        print(f"✓ tables générées à jour ({dd})"); return 0
    print(f"✓ {len(GEN)} table(s) générée(s) dans {dd} : " + ", ".join(GEN))
    return 0


if __name__ == "__main__":
    sys.exit(main())
