#!/usr/bin/env python3
"""pm-task-think — consigner dans le fichier de réflexion d'un ticket (`RM<id>_<slug>.think.md`). RM3015/RM3053.

Une ligne normée par appel (id auto, date, auteur, session), dans la rubrique voulue :
  pm-task-think <id> --note "verbatim du demandeur"          → N  (état 🕐, à trier)
  pm-task-think <id> --question "…" [--bloque X] [--urgence haute|moyenne|basse]   → Q  (🕐)
  pm-task-think <id> --decide "…" [--state valide]           → D  (🟡 par défaut : proposé, à arbitrer)
  pm-task-think <id> --advise "…"                            → C  (conseil de l'agent, 🟡)
  pm-task-think <id> --feature "…" [--domaine D] [--version V1] [--origine N003] [--lot L1]  → F
  pm-task-think <id> --set N003 --state valide [--dest "D002"]   change l'état d'une ligne
  pm-task-think <id> --show                                  résumé : Q ouvertes, D récentes, F
  pm-task-think <id> --counters                              compteurs → frontmatter de la fiche (D007)

Options communes : --by M|A|<nom> (défaut : A = agent), --sid <session> (défaut : $CLAUDE_CODE_SESSION_ID),
--when AAAA-MM-JJ, --dedupe (ne rien écrire si le texte est déjà consigné), --no-commit, --dry-run.

Le think est la matière de travail du ticket (hors wiki) ; `pm-think-merge` la fusionne vers les fichiers
du projet (`docs/cdc-*.md`). Les scripts et hooks appellent cet outil AVANT l'agent (D005) : l'agent
n'écrit à la main que le conseil et l'arbitrage.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_output import out as pmout            # noqa: E402
from pm_paths import PMConfig                 # noqa: E402
import pm_git                                 # noqa: E402
import pm_think                               # noqa: E402

KIND_FLAGS = (("note", "note"), ("question", "question"), ("decide", "decision"),
              ("advise", "decision"), ("feature", "feature"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    pmout.add_args(ap)
    ap.add_argument("rm_id", type=int)
    for flag, _ in KIND_FLAGS:
        ap.add_argument(f"--{flag}", metavar="TEXTE")
    ap.add_argument("--set", metavar="ID", help="ligne dont on change l'état (avec --state)")
    ap.add_argument("--state", choices=sorted(pm_think.STATES.values()))
    ap.add_argument("--dest", default="", help="« traitée par » d'une note (avec --set), ou renseigné à l'ajout")
    ap.add_argument("--by", default="A"); ap.add_argument("--sid", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    ap.add_argument("--when"); ap.add_argument("--bloque", default=""); ap.add_argument("--urgence", default="")
    ap.add_argument("--domaine", default=""); ap.add_argument("--version", default=""); ap.add_argument("--origine", default="")
    ap.add_argument("--lot", default="")
    ap.add_argument("--dedupe", action="store_true"); ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", action="store_true"); ap.add_argument("--counters", action="store_true")
    ap.add_argument("--path", action="store_true", help="imprime le chemin du think et sort")
    ap.add_argument("--cross-project", action="store_true", help="autorise l'écriture sur un ticket d'un autre projet (garde RM2274)")
    a = ap.parse_args()
    pmout.configure(a)

    cfg = PMConfig.load()
    sheet = cfg.find_task(a.rm_id)
    if not sheet:
        sys.exit(f"ERREUR : ticket RM{a.rm_id} introuvable dans l'arbo PM.")
    think = pm_think.think_path(sheet)
    if a.path:
        print(think); return
    parsed = pm_think.load(think)
    if a.show:
        if not think.is_file():
            pmout.info(f"RM{a.rm_id} : pas de fichier de réflexion ({think.name}) — `pm-task-think {a.rm_id} --note …` le crée")
            return
        print("\n".join(pm_think.summary(parsed, limit=8))); return
    if a.counters:
        changed = pm_think.set_counters(sheet, pm_think.counters(parsed)) if think.is_file() else False
        pmout.op("think", extra=f"RM{a.rm_id} compteurs {'posés' if changed else 'inchangés'}")
        if changed and not a.no_commit:
            pm_git.autocommit([sheet], f"pm(think): RM{a.rm_id} compteurs")
        return
    if a.set:
        if not a.state:
            sys.exit("ERREUR : --set exige --state")
        if a.dry_run:
            print(f"{think.name} : {a.set} → {a.state}"); return
        ok = pm_think.set_state(think, a.set, a.state, dest=a.dest)
        if not ok:
            sys.exit(f"ERREUR : ligne {a.set} introuvable dans {think.name}")
        pm_think.set_counters(sheet, pm_think.counters(pm_think.load(think)))
        pmout.op("think", extra=f"RM{a.rm_id} {a.set} → {pm_think.STATE_ICON[a.state]}")
        if not a.no_commit:
            pm_git.autocommit([think, sheet], f"pm(think): RM{a.rm_id} {a.set} {a.state}")
        return

    kind, text, prefix = None, None, None
    for flag, k in KIND_FLAGS:
        v = getattr(a, flag)
        if v:
            kind, text = k, v
            prefix = "C" if flag == "advise" else None
    if not kind:
        ap.print_help(); sys.exit(2)
    if text == "-":
        text = sys.stdin.read().strip()
    if a.dedupe and pm_think.has_text(parsed, kind, text):
        pmout.info(f"RM{a.rm_id} : déjà consigné, rien à écrire")
        return
    if a.dry_run:
        rid = pm_think.next_id(parsed, kind, prefix or pm_think.KINDS[kind][0])
        print(f"{think.name} +{rid} [{kind}] {text[:100]}"); return
    title = ""
    try:
        import re
        m = re.search(r"^title:\s*(.+)$", sheet.read_text(encoding="utf-8"), re.M)
        title = m.group(1).strip().strip("'\"") if m else ""
    except OSError:
        pass
    rid = pm_think.append(think, kind, text, prefix=prefix, rm_id=a.rm_id, title=title, by=a.by, state=a.state,
                          when=a.when, sid=a.sid, bloque=a.bloque, urgence=a.urgence, domaine=a.domaine,
                          version=a.version, origine=a.origine, lot=a.lot, dest=a.dest)
    pm_think.set_counters(sheet, pm_think.counters(pm_think.load(think)))
    pmout.op("think", extra=f"RM{a.rm_id} +{rid} [{kind}] {text[:80]}")
    if not a.no_commit:
        pm_git.autocommit([think, sheet], f"pm(think): RM{a.rm_id} +{rid}")


if __name__ == "__main__":
    main()
