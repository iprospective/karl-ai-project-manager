#!/usr/bin/env python3
"""pm-think-schema — met les `.think.md` existants à la grammaire courante (RM3262).

Les colonnes du carnet ont été enrichies : questions, décisions et fonctionnalités portent
désormais « Date · auteur » comme les notes, et une question porte « Tranchée par ». Les
carnets déjà écrits ont donc une table plus étroite — lisible, mais muette sur qui a posé
quoi et quand.

Ce script réécrit chaque table à la grammaire de `pm_think.KINDS`, en APPARIANT LES COLONNES
PAR LEUR NOM : ce qui existait est reporté dans la colonne de même nom, les colonnes neuves
naissent vides. Deux exceptions, qui sont tout l'intérêt de la migration :

  * la signature d'une DÉCISION était collée à la fin de son libellé — « … (2026-09-14 ·
    Mathieu) ». Elle est extraite vers sa colonne, et le libellé s'en trouve allégé ;
  * une table sans nom de colonne reconnaissable (carnet écrit à la main) est reportée
    POSITION PAR POSITION sur l'ancienne grammaire connue, jamais devinée.

Idempotent : relancé, il ne change plus rien (c'est ce que vérifie `--check`).

Usage :
    pm-think-schema.py --all [--dry-run]        tous les projets de l'arbo PM
    pm-think-schema.py --project client/projet  un projet
    pm-think-schema.py <fichier.think.md>…      des carnets précis
    pm-think-schema.py --all --check            sort 1 si un carnet n'est pas à jour (CI)
"""
import argparse
import pathlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_output import out as pmout            # noqa: E402
from pm_paths import PMConfig                 # noqa: E402
import pm_git                                 # noqa: E402
import pm_think                               # noqa: E402

#: grammaire d'AVANT RM3262, pour les tables dont l'en-tête ne se reconnaît pas
ANCIENNE = {
    "note":     ["#", "Date · auteur", "Verbatim", "État", "Traitée par"],
    "question": ["#", "Question", "Bloque", "Urgence", "État"],
    "decision": ["#", "Objet", "État"],
    "feature":  ["#", "Fonctionnalité", "Domaine", "Version", "Origine", "État", "Lot"],
}
#: « … (2026-09-14 · Mathieu) » en fin de libellé de décision
_SIGNATURE = re.compile(r"\s*\((\d{4}-\d{2}-\d{2}\s·\s[^()]+)\)\s*$")


def cellules_migrees(kind: str, header: list, cells: list) -> list:
    """Les cellules d'une ligne, portées à la grammaire courante. Pure — c'est elle qui est testée."""
    cible = pm_think.KINDS[kind][2]
    source = header if any(pm_think.col_index(header, c) is not None for c in cible) else ANCIENNE[kind]
    par_nom = {}
    for i, nom in enumerate(source):
        par_nom[nom] = cells[i] if i < len(cells) else ""
    sortie = []
    for nom in cible:
        val = ""
        for candidat in (nom, *_SYNONYMES.get(nom, ())):
            j = pm_think.col_index(list(par_nom), candidat)
            if j is not None:
                val = list(par_nom.values())[j]
                break
        sortie.append(val)
    if kind == "decision":
        # la signature quitte le libellé pour sa colonne (si elle n'y est pas déjà)
        i_txt = pm_think.col_index(cible, "Objet")
        i_sig = pm_think.col_index(cible, pm_think.SIGNATURE_COL)
        m = _SIGNATURE.search(sortie[i_txt] or "")
        if m and not (sortie[i_sig] or "").strip():
            sortie[i_sig] = m.group(1)
            sortie[i_txt] = _SIGNATURE.sub("", sortie[i_txt]).strip()
    return sortie


#: une colonne renommée se retrouve sous son ancien nom
_SYNONYMES = {"Tranchée par": ("Traitée par",)}


def reparer(f: pathlib.Path) -> list:
    """RM3356 — remet en place les lignes dont le texte a glissé d'une colonne (écriture au nouveau
    format dans un carnet pas encore migré, puis migration). Délègue à `pm_think`, qui porte la
    règle ; ici on ne fait que parcourir les carnets."""
    return pm_think.reparer_decalage(f)


def migrer_texte(texte: str) -> str:
    """Le contenu d'un `.think.md` à la grammaire courante. Pure, idempotente."""
    parsed = pm_think.parse(texte)
    lignes = texte.splitlines()
    for kind, sec in parsed.items():
        if kind not in pm_think.KINDS or sec.get("header") is None:
            continue
        cible = pm_think.KINDS[kind][2]
        neuf = {}
        for r in sec["rows"]:
            cells = cellules_migrees(kind, sec["header"], list(r["cells"]))
            cells[0] = r["cells"][0] if r["cells"] else cells[0]   # l'id garde sa forme (~~barré~~)
            neuf[r["line"]] = "| " + " | ".join(cells) + " |"
        neuf[sec["line_start"]] = "| " + " | ".join(cible) + " |"
        neuf[sec["line_start"] + 1] = "|" + "---|" * len(cible)
        for i, l in neuf.items():
            lignes[i] = l
    return "\n".join(lignes) + ("\n" if texte.endswith("\n") else "")


def carnets(args, cfg) -> list:
    """Les carnets visés : des fichiers nommés, un projet, ou toute l'arbo — par les chemins
    déclarés de la config, jamais par un motif écrit en dur (les instances diffèrent)."""
    if args.fichiers:
        return [Path(f) for f in args.fichiers]
    cible = tuple(args.project.split("/", 1)) if args.project else None
    out = []
    for ent, proj, _ in cfg.iter_projects():
        if cible and (ent, proj) != cible:
            continue
        tasks = Path(cfg.path("tasks_dir", entity=ent, project=proj))
        if tasks.is_dir():
            out += sorted(tasks.glob("*.think.md"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    pmout.add_args(ap)
    ap.add_argument("fichiers", nargs="*", help="carnets à migrer (défaut : --all / --project)")
    ap.add_argument("--all", action="store_true", help="tous les projets de l'arbo PM")
    ap.add_argument("--project", metavar="client/projet")
    ap.add_argument("--check", action="store_true", help="ne rien écrire ; sort 1 si un carnet n'est pas à jour")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-commit", action="store_true")
    a = ap.parse_args()
    pmout.configure(a)
    if not (a.fichiers or a.all or a.project):
        ap.print_help(); sys.exit(2)

    cfg = PMConfig.load()
    touches, vus = [], 0
    for f in carnets(a, cfg):
        try:
            avant = f.read_text(encoding="utf-8")
        except OSError as e:
            pmout.warn(f"{f.name} illisible : {e}"); continue
        vus += 1
        # RM3356 : la réparation d'abord — une ligne décalée doit être remise d'aplomb AVANT que la
        # migration ne la reporte fidèlement, décalage compris.
        if not (a.check or a.dry_run):
            for rid in reparer(f):
                pmout.info(f"  {f.name} : {rid} remise en place (décalage RM3356)")
            avant = f.read_text(encoding="utf-8")
        apres = migrer_texte(avant)
        if apres == avant:
            continue
        touches.append(f)
        if not (a.check or a.dry_run):
            f.write_text(apres, encoding="utf-8")
    quoi = "à migrer" if (a.check or a.dry_run) else "migré(s)"
    pmout.op("think-schema", extra=f"{len(touches)} carnet(s) {quoi} sur {vus}")
    for f in touches:
        pmout.info(f"  {f.name}")
    if a.check:
        sys.exit(1 if touches else 0)
    if touches and not (a.dry_run or a.no_commit):
        pm_git.autocommit(touches, f"pm(think): grammaire du carnet à jour — {len(touches)} carnet(s) (RM3262)")


if __name__ == "__main__":
    main()
