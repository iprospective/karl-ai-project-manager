#!/usr/bin/env python3
"""pm-task-questions — les questions d'un ticket, dans son CF Redmine 36 « Questions à trancher » (RM3226).

Les questions vivent dans le `.think.md` et gouvernent déjà des choses sérieuses : un ticket ne se ferme
pas avec une question en attente. Mais elles ne se voyaient **nulle part où l'on lit un ticket** — il
fallait savoir qu'un fichier frère existe, et l'ouvrir. RM3116 les avait régénérées dans la description ;
elles ont désormais leur champ, le **CF 36**, comme les critères d'acceptation ont le CF 33. La source
reste le `.think.md` : le CF est une vue, on ne le rapatrie pas.

  pm-task-questions <id>            met le CF à jour (et retire l'ancienne section de la description)
  pm-task-questions <id> --check    le CF est-il à jour ? (exit 1 sinon) — garde de livraison
  pm-task-questions --all           tous les tickets qui ont un `.think.md`
  --local                           n'écrit que le MD (retrait de l'ancienne section), sans Redmine
  --dry-run                         montre ce qui changerait

`pm-task-think` l'appelle de lui-même quand une question est posée, tranchée, ou qu'une décision cite
une question (`Q001 : …`) : le CF suit le think au fil de l'eau.

**Une case cochée à la main n'est pas ignorée.** Si quelqu'un coche une question dans Redmine alors que
le think la dit ouverte, on ne la décoche pas en silence : on le signale. Une coche n'est pas une
réponse — une question se tranche par une décision, et c'est cette décision que le CF affiche.
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

import pm_cf_mirror                                      # noqa: E402

_spec = importlib.util.spec_from_file_location("_desc", HERE / "pm-task-description-update.py")
_DESC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_DESC)


def cf_id():
    return pm_cf_mirror.resolve_cf_id(pm_think.QUESTIONS_CF_ENV, pm_think.QUESTIONS_CF_NAME)


def cf_value(issue: dict, cid) -> str:
    for cf in (issue or {}).get("custom_fields", []):
        if cf.get("id") == cid:
            return cf.get("value") or ""
    return ""


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
    corps_net = pm_think.strip_questions(corps)
    md_perime = corps_net.strip() != corps.strip()
    if local:                                  # le MD ne porte plus rien des questions : seulement le retrait
        if md_perime and not dry:
            ecrit_md(sheet, corps_net)
        return 0

    cid = cf_id()
    if cid is None:
        out.info(f"⚠ RM{rm_id} : CF « {pm_think.QUESTIONS_CF_NAME} » non résolu "
                 f"({pm_think.QUESTIONS_CF_ENV} / redmine.reference.yml) — rien de poussé, description laissée")
        return 0 if check else 1
    try:
        issue = _DESC.fetch_issue(rm_id)       # sys.exit sur erreur réseau : on la rattrape
    except (Exception, SystemExit) as e:       # noqa: BLE001
        out.info(f"⚠ RM{rm_id} : Redmine illisible ({type(e).__name__}) — CF non vérifié")
        if md_perime and not (dry or check):
            ecrit_md(sheet, corps_net)
        return 0
    voulu = pm_think.questions_text(parsed)
    actuel = cf_value(issue, cid)
    desc = issue.get("description") or ""
    desc_net = pm_think.strip_questions(desc)
    cf_ok = pm_cf_mirror.normalize_text(actuel) == pm_cf_mirror.normalize_text(voulu)
    desc_ok = desc_net.strip() == desc.strip()
    a_jour = cf_ok and desc_ok and not md_perime

    alerte = sorted(set(pm_think.cochees_a_la_main(actuel, parsed)) | set(pm_think.cochees_a_la_main(desc, parsed)))
    if alerte:
        out.info(f"⚠ RM{rm_id} : {', '.join(alerte)} cochée(s) à la main mais encore ouverte(s) dans le think. "
                 f"Une coche n'est pas une réponse : tranche-la (`pm-task-think {rm_id} --set {alerte[0]} "
                 f"--state valide`) et pose la décision qui répond.")
        if journal:
            journal.warn("question cochée à la main, non tranchée", rm=rm_id, ids=",".join(alerte))
    if check:
        print(("✓" if a_jour else "✗") + f" RM{rm_id} : questions (CF {cid}) "
              + ("à jour" if a_jour else "périmées → pm-task-questions " + str(rm_id)))
        return 0 if a_jour else 1
    if a_jour:
        out.info(f"RM{rm_id} : déjà à jour")
        return 0
    if dry:
        ouvertes = pm_think.counters(parsed).get("questions_open", 0)
        out.info(f"[dry-run] RM{rm_id} : CF {'à poser' if not cf_ok else 'ok'}"
                 f"{' · section de description à retirer' if not desc_ok else ''} — {ouvertes} ouverte(s)")
        return 0
    if md_perime:
        ecrit_md(sheet, corps_net)
    champs = {}
    if not cf_ok:
        champs["custom_fields"] = [{"id": cid, "value": voulu}]
    if not desc_ok:
        champs["description"] = desc_net
    if champs:
        try:
            ok = _DESC.put_issue(rm_id, champs)
        except (Exception, SystemExit) as e:   # noqa: BLE001 — Redmine indisponible ne doit pas perdre le MD
            ok = False
            if journal:
                journal.warn("questions non poussées vers Redmine", rm=rm_id, err=str(e)[:120])
        if not ok:
            out.info(f"⚠ RM{rm_id} : MD écrit, Redmine non mis à jour")
            return 0
    n = pm_think.counters(parsed).get("questions_open", 0)
    out.op("questions", rm=rm_id, extra=f"CF {cid} posé — {n} ouverte(s)"
           + (" · section retirée de la description" if not desc_ok else ""))
    if journal:
        journal.info("questions posées dans le CF", rm=rm_id, ouvertes=n)
    return 0


def toutes_les_fiches(cfg):
    """Toutes les fiches qui ont un think, tous projets confondus — `cfg.tasks_dir` n'existe pas :
    l'ancienne boucle ne parcourait rien (RM3226)."""
    for ent, proj, _ in cfg.iter_projects():
        for sheet in pm_think.iter_sheets(cfg.path("tasks_dir", entity=ent, project=proj)):
            if pm_think.think_path(sheet).is_file():
                yield sheet


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
        for sheet in toutes_les_fiches(cfg):
            rc |= une(pm_think.rm_id_of(sheet), cfg, a.local, a.dry_run, a.check)
        return rc
    if not a.rm_id:
        ap.print_help(); return 2
    return une(a.rm_id, cfg, a.local, a.dry_run, a.check)


if __name__ == "__main__":
    sys.exit(main())
