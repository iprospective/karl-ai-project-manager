#!/usr/bin/env python3
"""pm-task-questions — les questions d'un ticket, dans sa description (RM3116).

Les questions vivent dans le `.think.md` et gouvernent déjà des choses sérieuses : un ticket ne se ferme
pas avec une question en attente. Mais elles ne se voyaient **nulle part où l'on lit un ticket** — il
fallait savoir qu'un fichier frère existe, et l'ouvrir.

Cette commande régénère une section **❓ Questions ouvertes** dans la description, entre marqueurs, comme
les chapitres du CDC le sont du même fichier : deux vues, une donnée. La source reste le `.think.md`.

  pm-task-questions <id>            met la section à jour (MD + Redmine)
  pm-task-questions <id> --check    la section est-elle à jour ? (exit 1 sinon) — garde de livraison
  pm-task-questions --all           tous les tickets qui ont un `.think.md`
  --local                           n'écrit que le MD, sans toucher à Redmine
  --dry-run                         montre ce qui changerait

**Une case cochée à la main n'est pas ignorée.** Si quelqu'un coche une question dans Redmine alors que
le think la dit ouverte, on ne la décoche pas en silence : on le signale. Une coche n'est pas une
réponse — une question se tranche par une décision, et c'est cette décision que la section affiche.
"""
import argparse
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_think                                          # noqa: E402
from pm_paths import PMConfig                            # noqa: E402
from pm_output import out                                # noqa: E402
try:
    import pm_log
    journal = pm_log.journal("pm-task-questions", "issue")
except ImportError:
    journal = None

_spec = importlib.util.spec_from_file_location("_desc", HERE / "pm-task-description-update.py")
_DESC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_DESC)


def sections(sheet: Path):
    """(description locale, think parsé) — le MD porte la description, le think porte les questions."""
    texte = sheet.read_text(encoding="utf-8")
    corps = texte.split("---", 2)[-1] if texte.startswith("---") else texte
    return corps, pm_think.load(pm_think.think_path(sheet))


def ecrit_md(sheet: Path, nouveau_corps: str) -> bool:
    texte = sheet.read_text(encoding="utf-8")
    if not texte.startswith("---"):
        sheet.write_text(nouveau_corps, encoding="utf-8")
        return True
    tete, _, reste = texte.partition("---")
    fm, _, _ancien = reste.partition("---")
    sheet.write_text("---" + fm + "---" + nouveau_corps, encoding="utf-8")
    return True


def une(rm_id: int, cfg, local=False, dry=False, check=False) -> int:
    sheet = cfg.find_task(int(rm_id))
    if not sheet:
        out.fail(f"RM{rm_id} : fiche introuvable")
        return 1
    corps, parsed = sections(sheet)
    if not parsed:
        if check:
            return 0
        out.info(f"RM{rm_id} : pas de .think.md — rien à poser")
        return 0
    nouveau = pm_think.pose_questions(corps, parsed)
    a_jour = nouveau.strip() == corps.strip()
    alerte = pm_think.cochees_a_la_main(corps, parsed)
    if alerte:
        out.info(f"⚠ RM{rm_id} : {', '.join(alerte)} cochée(s) à la main mais encore ouverte(s) dans le think. "
                 f"Une coche n'est pas une réponse : tranche-la (`pm-task-think {rm_id} --set {alerte[0]} "
                 f"--state valide`) et pose la décision qui répond.")
        if journal:
            journal.warn("question cochée à la main, non tranchée", rm=rm_id, ids=",".join(alerte))
    if check:
        print(("✓" if a_jour else "✗") + f" RM{rm_id} : section des questions "
              + ("à jour" if a_jour else "périmée → pm-task-questions " + str(rm_id)))
        return 0 if a_jour else 1
    if a_jour:
        out.info(f"RM{rm_id} : déjà à jour")
        return 0
    if dry:
        ouvertes = pm_think.counters(parsed).get("questions_open", 0)
        out.info(f"[dry-run] RM{rm_id} : section à (re)poser — {ouvertes} question(s) ouverte(s)")
        return 0
    ecrit_md(sheet, nouveau)
    if not local:
        try:
            issue = _DESC.fetch_issue(rm_id)
            dist = issue.get("description") or ""
            _DESC.put_issue(rm_id, {"description": pm_think.pose_questions(dist, parsed)})
        except Exception as e:                            # Redmine indisponible ne doit pas perdre le MD
            out.info(f"⚠ RM{rm_id} : MD écrit, Redmine non mis à jour ({type(e).__name__})")
            if journal:
                journal.warn("section des questions non poussée vers Redmine", rm=rm_id, err=str(e)[:120])
            return 0
    n = pm_think.counters(parsed).get("questions_open", 0)
    out.op("questions", rm=rm_id, extra=f"section posée — {n} ouverte(s)")
    if journal:
        journal.info("section des questions posée", rm=rm_id, ouvertes=n)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", nargs="?", type=int)
    ap.add_argument("--all", action="store_true", help="tous les tickets qui ont un .think.md")
    ap.add_argument("--check", action="store_true"); ap.add_argument("--local", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = PMConfig.load()
    if a.all:
        rc = 0
        for sheet in sorted(cfg.tasks_dir.glob("RM*.md")) if hasattr(cfg, "tasks_dir") else []:
            if not pm_think.is_task_sheet(sheet) or not pm_think.think_path(sheet).is_file():
                continue
            rc |= une(pm_think.rm_id_of(sheet), cfg, a.local, a.dry_run, a.check)
        return rc
    if not a.rm_id:
        ap.print_help(); return 2
    return une(a.rm_id, cfg, a.local, a.dry_run, a.check)


if __name__ == "__main__":
    sys.exit(main())
