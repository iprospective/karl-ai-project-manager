#!/usr/bin/env python3
"""pm-glossaire — le vocabulaire métier d'un projet (RM2675).

Chaque projet accumule un jargon — acronymes, unités, noms de pièces — dont la maîtrise
conditionne toute intervention. Il vivait dispersé dans les CDC, les docs et les logs de
tickets : il fallait le reconstituer à chaque fois.

Emplacement canonique : **`{docs_dir}/glossaire.md`**. Ce n'est pas un choix arbitraire — ce
dossier donne les DEUX branches de l'alternative posée au ticket :
  - il **est** `docs/glossaire.md` vu depuis le repo de code (symlink posé par `pm-project-new`),
    donc il suit le code et se relit en MR ;
  - il est **lisible sans checkout** : `pm-wiki-sync` publie tout `docs/*.md` au wiki Redmine, et
    `karl-agent` l'expose déjà au cockpit, rendu en markdown.

Format : un tableau à 4 colonnes trié alphabétiquement. L'outil garantit le tri, l'unicité du
terme et le format — tripwire NORMS #1 : une donnée PM ne s'édite pas à la main.

Usage :
    pm-glossaire.py <projet> list
    pm-glossaire.py <projet> add "odométrie" "Mesure de l'avance par les encodeurs de roues."
                                  --contexte "Dérivante ; recalée par la vision." --alias "odo"
    pm-glossaire.py <projet> rm "odométrie"
    pm-glossaire.py <projet> inject [--budget 1500]     # ce qu'un agent reçoit au contexte

`<projet>` est une référence NON AMBIGUË (`client/slug` ou `redmine.project_id`) — tripwire #14.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

FICHIER = "glossaire.md"
ENTETE = "| Terme | Définition | Contexte d'usage | Alias |"
SEP = "|---|---|---|---|"
# Plafond d'injection au contexte des agents `[ARBITRÉ — étude RM2675]`. 1 500 tokens ≈ 70 termes,
# soit 7,5 % du budget `context.budget_tokens.project_docs` (20 000). Au-delà, un glossaire de
# projet cesse d'être un glossaire — et la troncature est SIGNALÉE, jamais muette.
BUDGET_DEFAUT = 1500
TOKENS_PAR_CAR = 0.27          # approximation usuelle pour du français


def entete_fichier(projet: str) -> str:
    return (f"---\nwiki_sync: true\ntitle: Glossaire\n---\n\n# Glossaire — {projet}\n\n"
            f"{ENTETE}\n{SEP}\n")


def chemin(cfg: PMConfig, ref: str) -> tuple[str, str, Path]:
    ent, proj, _ = cfg.resolve_project_ref(ref)
    docs = Path(cfg.path("docs_dir", entity=ent, project=proj))
    return ent, proj, docs / FICHIER


def _echappe(v: str) -> str:
    """Un `|` dans une cellule casserait le tableau ; on l'échappe plutôt que de le refuser."""
    return v.replace("|", "\\|").replace("\n", " ").strip()


def lire(f: Path) -> list[dict]:
    """Les entrées du tableau, dans l'ordre du fichier."""
    if not f.exists():
        return []
    out = []
    for ligne in f.read_text(encoding="utf-8").splitlines():
        l = ligne.strip()
        if not l.startswith("|") or l.startswith(("|---", "| Terme")):
            continue
        cells = [c.strip() for c in l.strip("|").split("|")]
        if len(cells) < 2 or not cells[0]:
            continue
        cells += [""] * (4 - len(cells))
        out.append({"terme": cells[0], "definition": cells[1],
                    "contexte": cells[2], "alias": cells[3]})
    return out


def ecrire(f: Path, projet: str, entrees: list[dict]) -> None:
    """Réécrit le fichier, entrées TRIÉES — l'ordre alphabétique est la moitié de l'utilité."""
    f.parent.mkdir(parents=True, exist_ok=True)
    entrees = sorted(entrees, key=lambda e: _cle(e["terme"]))
    corps = "".join(
        f"| {e['terme']} | {e['definition']} | {e['contexte'] or '—'} | {e['alias'] or '—'} |\n"
        for e in entrees)
    f.write_text(entete_fichier(projet) + corps, encoding="utf-8")


def _cle(terme: str) -> str:
    """Tri insensible à la casse, aux accents et au gras markdown."""
    t = re.sub(r"[*_`]", "", terme).lower()
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for c in a:
            t = t.replace(c, b)
    return t


def cmd_list(f: Path, projet: str, args) -> int:
    entrees = lire(f)
    if not entrees:
        print(f"glossaire vide ou absent : {f}")
        return 0
    print(f"Glossaire — {projet} ({len(entrees)} terme(s))\n")
    larg = max(len(e["terme"]) for e in entrees)
    for e in entrees:
        alias = f"  [{e['alias']}]" if e["alias"] and e["alias"] != "—" else ""
        print(f"  {e['terme']:<{larg}}  {e['definition']}{alias}")
    print(f"\n→ {f}")
    return 0


def cmd_add(f: Path, projet: str, args) -> int:
    entrees = lire(f)
    cle = _cle(args.terme)
    existant = next((e for e in entrees if _cle(e["terme"]) == cle), None)
    if existant and not args.force:
        print(f"⚠ « {existant['terme']} » existe déjà : {existant['definition']}")
        print("  → --force pour le remplacer")
        return 1
    if existant:
        entrees.remove(existant)
    entrees.append({"terme": _echappe(args.terme), "definition": _echappe(args.definition),
                    "contexte": _echappe(args.contexte or ""), "alias": _echappe(args.alias or "")})
    ecrire(f, projet, entrees)
    print(f"✓ glossaire {projet} : {'remplacé' if existant else 'ajouté'} « {args.terme} » "
          f"({len(entrees)} terme(s))")
    return 0


def cmd_rm(f: Path, projet: str, args) -> int:
    entrees = lire(f)
    cle = _cle(args.terme)
    reste = [e for e in entrees if _cle(e["terme"]) != cle]
    if len(reste) == len(entrees):
        print(f"⚠ « {args.terme} » absent du glossaire")
        return 1
    ecrire(f, projet, reste)
    print(f"✓ glossaire {projet} : retiré « {args.terme} » ({len(reste)} terme(s))")
    return 0


def bloc_contexte(entrees: list[dict], budget: int = BUDGET_DEFAUT) -> str:
    """Le glossaire tel qu'un agent le reçoit à l'onboarding — PLAFONNÉ, troncature signalée.

    C'est la raison d'être du ticket : laisser le glossaire en consultation à la demande, c'est
    compter sur l'agent pour savoir qu'il ne sait pas. Un agent qui lit « rampe » sans connaître
    le terme n'ouvrira pas le glossaire — il supposera, et se trompera silencieusement.
    """
    if not entrees:
        return ""
    lignes, total, pris = [], 0, 0
    for e in sorted(entrees, key=lambda x: _cle(x["terme"])):
        alias = f" (alias : {e['alias']})" if e["alias"] and e["alias"] != "—" else ""
        l = f"- **{e['terme']}** — {e['definition']}{alias}"
        cout = len(l) * TOKENS_PAR_CAR
        if total + cout > budget:
            break
        lignes.append(l)
        total += cout
        pris += 1
    reste = len(entrees) - pris
    txt = "## Vocabulaire du projet\n\n" + "\n".join(lignes)
    if reste:
        txt += (f"\n- … **+{reste} terme(s) non repris ici** (plafond de contexte atteint) : "
                f"`docs/glossaire.md`")
    return txt + "\n"


def cmd_inject(f: Path, projet: str, args) -> int:
    entrees = lire(f)
    if not entrees:
        print(f"glossaire vide ou absent : {f}")
        return 0
    bloc = bloc_contexte(entrees, args.budget)
    print(bloc)
    approx = int(len(bloc) * TOKENS_PAR_CAR)
    print(f"— {approx} tokens estimés sur un plafond de {args.budget} "
          f"({len(entrees)} terme(s) au glossaire)", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Glossaire métier d'un projet (RM2675)")
    ap.add_argument("projet", help="référence NON AMBIGUË : client/slug ou redmine.project_id")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="affiche le glossaire")
    a = sub.add_parser("add", help="ajoute (ou remplace avec --force) un terme")
    a.add_argument("terme")
    a.add_argument("definition", help="2 lignes maximum — au-delà, faire un doc et le référencer")
    a.add_argument("--contexte", default="", help="où/comment le terme sert, valeurs, renvois")
    a.add_argument("--alias", default="", help="acronymes et synonymes (séparés par des virgules)")
    a.add_argument("--force", action="store_true")
    r = sub.add_parser("rm", help="retire un terme")
    r.add_argument("terme")
    i = sub.add_parser("inject", help="le bloc injecté au contexte des agents (plafonné)")
    i.add_argument("--budget", type=int, default=BUDGET_DEFAUT)
    args = ap.parse_args()

    cfg = PMConfig.load()
    try:
        ent, proj, f = chemin(cfg, args.projet)
    except ValueError as exc:                     # tripwire #14 : jamais de choix silencieux
        print(f"ERREUR : {exc}", file=sys.stderr)
        return 2
    projet = f"{ent}/{proj}"
    return {"list": cmd_list, "add": cmd_add, "rm": cmd_rm,
            "inject": cmd_inject}[args.cmd](f, projet, args)


if __name__ == "__main__":
    raise SystemExit(main())
