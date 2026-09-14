#!/usr/bin/env python3
"""pm-task-estimate — RÉVISER l'estimation d'un ticket (frontmatter + Redmine). RM3155.

Le chiffrage est le **livrable** de la phase `etude_chiffrage_en_cours` : le workflow
NORMS en fait la condition de sortie vers `etude_chiffrage_a_valider` (« CDC +
`estimate.*` complets »). Il manquait pourtant l'outil pour l'écrire —

    pm-task-add --est-*          POSE l'estimation à la création, donc avant l'étude ;
    pm-task-metrics-push         la POUSSE vers Redmine ;
    pm-task-tick                 incrémente le RÉEL consommé, pas la prévision ;
    (rien)                       ne la RÉVISAIT.

Faute de quoi on éditait le frontmatter à la main, en refaisant soi-même le protocole
d'optimistic locking — ce que le tripwire #1 proscrit (« pas d'outil = trou à combler,
pas une exception manuelle »). Constaté sur RM3107 : 60 min posées à la création,
930 min après étude, écrites à la main.

Usage :
    pm-task-estimate.py <RM-id>                        # affiche l'estimation courante
    pm-task-estimate.py <RM-id> --ai-minutes 810 --human-minutes 120 \\
                        --difficulty high --confidence 0.5 --tokens 1200000 \\
                        --note "après étude : 6 lots identifiés"
    pm-task-estimate.py <RM-id> --ai-minutes 90 --no-push   # local seulement

Ce que l'outil fait, et que la main oubliait :
  · **verrou par ticket** puis relecture avant écriture (optimistic locking NORMS) ;
  · `estimated_by` / `estimated_at` remis à la RÉVISION — sans quoi on ne sait plus
    si l'on lit un chiffrage d'étude ou le nombre jeté à la création ;
  · `time_minutes` (legacy) recalculé = humain + IA, au lieu de diverger en silence ;
  · **l'ancienne valeur au `.log.md`**, pour comparer l'avant et l'après ;
  · la poussée Redmine dans la foulée (CF21/22/25 + `estimated_hours`), en
    réutilisant `pm-task-metrics-push` — un seul endroit sait mapper les CF.

Le **coût prévu ne se calcule pas** depuis les tokens seuls, et l'outil ne le devine
donc jamais : le prix dépend de la RÉPARTITION (cache_read 0,50 $/Mtok contre output
25 $/Mtok — un facteur 50), inconnue avant d'avoir travaillé. `--cost-usd` est une
saisie assumée, pas une dérivation.
"""
import argparse
import importlib.util
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_lock import ticket_lock
from pm_output import out
from pm_paths import PMConfig
import pm_git

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

HERE = Path(__file__).resolve().parent
FM_RE = re.compile(r"\A(---\n)(.*?)(\n---\n)(.*)\Z", re.S)
DIFFICULTES = ("low", "medium", "high", "critical")

#: Champs révisables : drapeau CLI → (clé du frontmatter, libellé, conversion).
CHAMPS = {
    "difficulty": ("difficulty", "difficulté", str),
    "human_minutes": ("human_time_minutes", "temps humain (min)", int),
    "ai_minutes": ("ai_time_minutes", "temps IA (min)", int),
    "tokens": ("tokens", "tokens", int),
    "cost_usd": ("cost_usd", "coût USD", float),
    "model": ("estimated_model", "modèle", str),
    "confidence": ("confidence", "confiance", float),
}


def _metrics_push():
    """`pm-task-metrics-push.py` importé par chemin (son nom porte des tirets)."""
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


# >>> apply_estimate — pure (testée par test_pm_task_estimate.py)
def apply_estimate(est: dict, changes: dict, *, by: str, now: str) -> tuple:
    """Applique les changements à un bloc `estimate`. Retourne (nouveau, diffs).

    `diffs` liste (libellé, avant, après) pour les seules valeurs qui CHANGENT —
    c'est ce qui part au journal. Réviser en reposant la même valeur ne produit
    aucune entrée : un journal qui consigne des non-événements ne se lit plus.
    """
    new = dict(est or {})
    diffs = []
    for flag, (cle, libelle, _conv) in CHAMPS.items():
        if changes.get(flag) is None:
            continue
        avant, apres = new.get(cle), changes[flag]
        if avant != apres:
            diffs.append((libelle, avant, apres))
            new[cle] = apres
    if not diffs:
        return new, []
    # `time_minutes` est un champ legacy : le laisser diverger de ses deux
    # composantes en ferait un piège — deux chiffres, aucun moyen de savoir lequel ment.
    h, a = new.get("human_time_minutes"), new.get("ai_time_minutes")
    if h is not None or a is not None:
        total = (h or 0) + (a or 0)
        if new.get("time_minutes") != total:
            diffs.append(("total (min)", new.get("time_minutes"), total))
            new["time_minutes"] = total
    new["estimated_by"] = by
    new["estimated_at"] = now
    return new, diffs
# <<< apply_estimate


# >>> format_estimate — pure
def format_estimate(est: dict) -> list:
    """L'estimation en lignes lisibles. Les champs vides sont DITS, pas masqués :
    une estimation incomplète est une information (le workflow l'exige complète)."""
    est = est or {}
    lignes = []
    for _flag, (cle, libelle, _c) in CHAMPS.items():
        v = est.get(cle)
        lignes.append(f"  {libelle:<20} {'—' if v is None else v}")
    lignes.append(f"  {'total (min)':<20} {est.get('time_minutes') or '—'}")
    qui, quand = est.get("estimated_by"), est.get("estimated_at")
    if qui or quand:
        lignes.append(f"  {'estimé par':<20} {qui or '—'} le {quand or '—'}")
    return lignes
# <<< format_estimate


def log_entry(rm_id: int, diffs: list, note: str, by: str, now: str) -> str:
    corps = "\n".join(f"- {lib} : {'—' if av is None else av} → {ap}" for lib, av, ap in diffs)
    txt = (f"\n## {now} — Estimation révisée (pm-task-estimate)\n"
           f"Tokens : 0 | Durée : 0 min\n\n"
           f"Révisée par {by}.\n\n{corps}\n")
    if note:
        txt += f"\nMotif : {note}\n"
    return txt


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--difficulty", choices=DIFFICULTES)
    ap.add_argument("--human-minutes", type=int, help="temps HUMAIN prévu (revue, décisions, tests)")
    ap.add_argument("--ai-minutes", type=int, help="temps IA wall-clock prévu")
    ap.add_argument("--tokens", type=int)
    ap.add_argument("--cost-usd", type=float, help="saisi, jamais dérivé des tokens (cf. docstring)")
    ap.add_argument("--model", help="modèle prévu, ex. claude-opus-5")
    ap.add_argument("--confidence", type=float, help="0.0 → 1.0")
    ap.add_argument("--by", default=None, help="qui révise (défaut : pm-task-estimate)")
    ap.add_argument("--note", default="", help="motif de la révision — tracé au journal")
    ap.add_argument("--no-push", action="store_true", help="n'écrit que le frontmatter")
    ap.add_argument("--no-commit", action="store_true", help="pas d'auto-commit git (RM1834)")
    ap.add_argument("--dry-run", action="store_true")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    if args.confidence is not None and not 0.0 <= args.confidence <= 1.0:
        sys.exit("ERREUR : --confidence attend une valeur entre 0.0 et 1.0")
    for f in ("human_minutes", "ai_minutes", "tokens"):
        v = getattr(args, f)
        if v is not None and v < 0:
            sys.exit(f"ERREUR : --{f.replace('_', '-')} ne peut pas être négatif")

    changes = {f: getattr(args, f) for f in CHAMPS}
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    cfg = PMConfig.load()
    with ticket_lock(cfg.state_dir, args.rm_id):
        md_path, fm, m = read_task(args.rm_id)

        if not any(v is not None for v in changes.values()):
            print(f"RM{args.rm_id} — estimation courante :")
            for l in format_estimate(fm.get("estimate")):
                print(l)
            return 0

        new_est, diffs = apply_estimate(fm.get("estimate"), changes,
                                        by=args.by or "pm-task-estimate", now=now)
        if not diffs:
            out.op("estimation inchangée", rm=args.rm_id, extra="mêmes valeurs")
            return 0
        if args.dry_run:
            print(f"--dry-run : RM{args.rm_id} " + " ; ".join(
                f"{lib} {'—' if av is None else av}→{ap}" for lib, av, ap in diffs))
            return 0

        fm["estimate"] = new_est
        # write_task_fm pose `updated` : la relecture du frontmatter sous verrou
        # (read_task ci-dessus) EST le point de contrôle de l'optimistic locking.
        mp = _metrics_push()
        mp.write_task_fm(md_path, fm, m)
        log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(log_entry(args.rm_id, diffs, args.note,
                              args.by or "pm-task-estimate", now))
        out.op("estimation révisée", rm=args.rm_id, extra=" ".join(
            f"{lib}={ap}" for lib, _av, ap in diffs))

        if not args.no_push:
            md_path2, fm2, m2 = read_task(args.rm_id)
            mp.do_estimate(args.rm_id, fm2, md_path2, m2, False)

    if not args.no_commit:
        pm_git.autocommit([md_path, md_path.parent / md_path.name.replace(".md", ".log.md")],
                          f"pm(estimate): RM{args.rm_id} estimation révisée")
    return 0


if __name__ == "__main__":
    sys.exit(main())
