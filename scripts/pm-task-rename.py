#!/usr/bin/env python3
"""pm-task-rename — renommer le TITRE d'un ticket (frontmatter + Redmine). RM3242.

Un ticket dont l'objet a changé en cours d'étude garde son titre d'origine, et ce
titre ment : on lit « Déplacer toutes les données dans /data » sur un ticket qui
décide précisément de ne rien déplacer (RM3186). Il manquait l'outil pour le
corriger —

    pm-task-add                  POSE le titre, à la création ;
    pm-task-sync                 RAPATRIE un titre changé dans l'UI Redmine ;
    (rien)                       ne le RENOMMAIT depuis le PM.

Faute de quoi on le laissait mentir, avec un bandeau d'avertissement en tête de
description (RM2783 : « ⚠ Le titre de ce ticket est trompeur »), ou on éditait le
frontmatter et Redmine à la main — ce que le tripwire #1 proscrit (« pas d'outil =
trou à combler, pas une exception manuelle »).

Usage :
    pm-task-rename.py <RM-id>                                # affiche le titre courant
    pm-task-rename.py <RM-id> --title "Nouveau titre" --note "motif"
    pm-task-rename.py <RM-id> --title "…" --dry-run

Ce que l'outil fait :
  · **verrou par ticket** puis relecture avant écriture (optimistic locking NORMS) ;
  · l'**ancien titre au `.log.md`** et dans la note Redmine — un renommage efface
    ce qu'on cherchait, il faut pouvoir retrouver le ticket sous son ancien nom ;
  · le PUT Redmine, puis une **relecture** : Redmine renvoie 204 même quand il
    ignore un attribut faute de permission (cf. knowledge/redmine/api.md).

Ce qu'il ne fait PAS : renommer les fichiers. Le slug de `RM<id>_<slug>.md` reste
celui de la création. Il est référencé ailleurs (ledger `.reporting.yml`, fichier
`.think.md`, chemins cités dans des journaux et des notes), et NORMS n'exige du
nom de fichier que le préfixe `RM<id>_` (tripwire #6). Un slug périmé est
cosmétique ; un lien cassé ne l'est pas.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_lock import ticket_lock
from pm_output import out
from pm_paths import PMConfig
import importlib.util
import re
import pm_git
import redmine_utils

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

HERE = Path(__file__).resolve().parent
FM_RE = re.compile(r"\A(---\n)(.*?)(\n---\n)(.*)\Z", re.S)
#: Limite du champ `subject` de Redmine (colonne varchar(255)).
TITRE_MAX = 255


def _metrics_push():
    """`pm-task-metrics-push.py` importé par chemin : il porte `write_task_fm`,
    l'écriture du frontmatter partagée (pose `updated`, écriture atomique)."""
    spec = importlib.util.spec_from_file_location("mp", HERE / "pm-task-metrics-push.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_task(rm_id):
    cfg = PMConfig.load()
    md_path = cfg.find_task(rm_id)
    if not md_path:
        sys.exit(f"ERREUR : RM{rm_id} introuvable")
    m = FM_RE.match(md_path.read_text(encoding="utf-8"))
    if not m:
        sys.exit(f"ERREUR : pas de frontmatter dans {md_path}")
    return md_path, (yaml.safe_load(m.group(2)) or {}), m


# >>> normalize_title — pure (testée par test_pm_task_rename.py)
def normalize_title(titre: str) -> str:
    """Le titre tel qu'il sera écrit, ou ValueError s'il n'est pas acceptable.

    Les espaces multiples sont réduits : un titre saisi en ligne de commande en
    traîne souvent, et Redmine les conserverait. Un saut de ligne est refusé plutôt
    que corrigé — il trahit presque toujours un collage raté (une description entière
    passée en titre), qu'il vaut mieux voir que tronquer en silence.
    """
    if titre is None:
        raise ValueError("titre absent")
    if "\n" in titre or "\r" in titre:
        raise ValueError("le titre tient sur une ligne (saut de ligne trouvé)")
    t = " ".join(titre.split())
    if not t:
        raise ValueError("titre vide")
    if len(t) > TITRE_MAX:
        raise ValueError(f"titre trop long : {len(t)} caractères, Redmine en accepte {TITRE_MAX}")
    return t
# <<< normalize_title


# >>> redmine_note — pure
def redmine_note(ancien: str, nouveau: str, motif: str = "") -> str:
    """La note Redmine du renommage. L'ancien titre y figure EN ENTIER : c'est sous
    ce nom qu'on cherchera encore le ticket pendant des semaines."""
    note = f"Titre renommé.\n\n* avant : « {ancien} »\n* après : « {nouveau} »"
    if motif:
        note += f"\n\nMotif : {motif}"
    return note
# <<< redmine_note


def log_entry(ancien: str, nouveau: str, motif: str, by: str, now: str) -> str:
    txt = (f"\n## {now} — Titre renommé (pm-task-rename)\n"
           f"Tokens : 0 | Durée : 0 min\n\n"
           f"Par {by}.\n\n- avant : « {ancien} »\n- après : « {nouveau} »\n")
    if motif:
        txt += f"\nMotif : {motif}\n"
    return txt


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--title", help="le nouveau titre (une ligne, ≤ 255 caractères)")
    ap.add_argument("--note", default="", help="motif du renommage — tracé au journal et sur Redmine")
    ap.add_argument("--by", default=None, help="qui renomme (défaut : pm-task-rename)")
    ap.add_argument("--no-push", action="store_true", help="n'écrit que le frontmatter")
    ap.add_argument("--no-commit", action="store_true", help="pas d'auto-commit git (RM1834)")
    ap.add_argument("--dry-run", action="store_true")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    if args.title is not None:
        try:
            nouveau = normalize_title(args.title)
        except ValueError as e:
            sys.exit(f"ERREUR : {e}")
    by = args.by or "pm-task-rename"
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    cfg = PMConfig.load()
    with ticket_lock(cfg.state_dir, args.rm_id):
        md_path, fm, m = read_task(args.rm_id)
        ancien = fm.get("title") or ""

        if args.title is None:
            print(f"RM{args.rm_id} — {ancien}")
            return 0
        if nouveau == ancien:
            out.op("titre inchangé", rm=args.rm_id, extra="même valeur")
            return 0
        if args.dry_run:
            print(f"--dry-run : RM{args.rm_id} « {ancien} » → « {nouveau} »")
            return 0

        fm["title"] = nouveau
        # write_task_fm pose `updated` : la relecture du frontmatter sous verrou
        # (read_task ci-dessus) EST le point de contrôle de l'optimistic locking.
        _metrics_push().write_task_fm(md_path, fm, m)
        log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(log_entry(ancien, nouveau, args.note, by, now))
        out.op("titre renommé", rm=args.rm_id, extra=f"« {nouveau} »")

        if not args.no_push:
            ok, err = redmine_utils.update_issue_fields(
                args.rm_id, subject=nouveau, notes=redmine_note(ancien, nouveau, args.note))
            if not ok:
                out.fail(f"push Redmine : {err} — le frontmatter est renommé, Redmine NON "
                         f"(relancer, ou pm-task-sync pour réaligner)")
                return 1
            # Redmine renvoie 204 même quand il ignore `subject` faute de droit.
            lu = (redmine_utils.fetch_issue(args.rm_id) or {}).get("subject")
            if lu != nouveau:
                out.fail(f"Redmine a répondu OK mais le titre lu est « {lu} » "
                         f"(permission « Edit issues » ?)")
                return 1
            out.op("titre Redmine", rm=args.rm_id, extra="vérifié à la relecture")

    if not args.no_commit:
        pm_git.autocommit([md_path, md_path.parent / md_path.name.replace(".md", ".log.md")],
                          f"pm(rename): RM{args.rm_id} titre renommé")
    return 0


if __name__ == "__main__":
    sys.exit(main())
