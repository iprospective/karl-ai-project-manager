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

  pm-task-think <id> --delete Dnnn                 supprime une ligne incohérente (RM3064)
  pm-task-think <id> --move Qnnn --to <autre-id>   déplace l'entrée vers le carnet d'un autre ticket (RM3258)
Options communes : --by M|A|<nom> (défaut : A = agent), --sid <session> (défaut : $CLAUDE_CODE_SESSION_ID),
--when AAAA-MM-JJ, --dedupe (ne rien écrire si le texte est déjà consigné), --no-commit, --dry-run.

Le think est la matière de travail du ticket (hors wiki) ; `pm-think-merge` la fusionne vers les fichiers
du projet (`docs/cdc-*.md`). Les scripts et hooks appellent cet outil AVANT l'agent (D005) : l'agent
n'écrit à la main que le conseil et l'arbitrage.
"""
import argparse
import os
import getpass
import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_output import out as pmout            # noqa: E402
from pm_paths import PMConfig                 # noqa: E402
import pm_git                                 # noqa: E402
import pm_think                               # noqa: E402

KIND_FLAGS = (("note", "note"), ("question", "question"), ("decide", "decision"),
              ("advise", "decision"), ("feature", "feature"))


def _resync_questions(rm_id, sheet, kind=None):
    """Le CF 36 « Questions à trancher » suit le think au fil de l'eau (RM3116 → RM3226).

    Poser une question, la trancher, ou poser la décision qui y répond change ce qu'un lecteur du
    ticket doit voir — attendre une commande de plus, c'est accepter que Redmine mente entre-temps.
    RM3116 s'en tenait au MD local, par économie d'appels ; mais la vue EST désormais côté Redmine, et
    l'appel n'a lieu que sur ces gestes-là (pas sur chaque note), un GET puis un PUT seulement si le
    champ a changé. `PM_THINK_LOCAL=1` revient au local seul (hors ligne, rafales scriptées).
    Muet, et jamais bloquant : une vue ne doit pas casser une consignation."""
    try:
        import contextlib
        import importlib.util
        import io
        spec = importlib.util.spec_from_file_location(
            "_qs", pathlib.Path(__file__).resolve().parent / "pm-task-questions.py")
        Q = importlib.util.module_from_spec(spec); spec.loader.exec_module(Q)
        from pm_paths import PMConfig
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            Q.une(int(rm_id), PMConfig.load(), local=bool(os.environ.get("PM_THINK_LOCAL")))
    except (Exception, SystemExit):     # noqa: BLE001 — fetch_issue sort en sys.exit sur erreur réseau
        pass                    # une vue des questions ne doit jamais casser une consignation


def _titre(sheet) -> str:
    """Le titre du ticket, pour le gabarit d'un carnet créé à l'arrivée d'une entrée déplacée."""
    import re
    try:
        m = re.search(r"^title:\s*(.+)$", Path(sheet).read_text(encoding="utf-8"), re.M)
        return m.group(1).strip().strip("'\"") if m else ""
    except OSError:
        return ""


def _log_path(sheet):
    """Le journal du ticket, à côté de sa fiche."""
    return Path(str(sheet).replace(".md", ".log.md"))


def _log_amendement(rm_id, sheet, rid, ancien, nouveau, par=None):
    """Consigne l'amendement au journal : qui, quand, et surtout CE QUE ÇA DISAIT AVANT."""
    from datetime import datetime
    log = _log_path(sheet)
    qui = str(par or os.environ.get("PM_AUTHOR") or getpass.getuser() or "?")
    bloc = (f"\n## {datetime.now().strftime('%Y-%m-%dT%H:%M')} — Amendement du carnet ({rid})\n"
            f"Tokens : 0 | Durée : 0 min\n\n"
            f"Par {qui}.\n\n"
            f"Avant : {ancien}\n\n"
            f"Après : {nouveau}\n")
    try:
        with open(log, "a", encoding="utf-8") as f:
            f.write(bloc)
    except OSError:
        pass                      # un journal non écrivable ne doit pas empêcher l'amendement


def _log_deplacement(sheet, rid, sens, autre_rm, autre_id, par=None):
    """Trace le déplacement dans le journal du ticket — des DEUX côtés. Le carnet ne garde
    que la ligne ; c'est le journal qu'on relit pour savoir d'où elle vient, ou où elle est partie."""
    from datetime import datetime
    qui = str(par or os.environ.get("PM_AUTHOR") or getpass.getuser() or "?")
    fleche = (f"{rid} → RM{autre_rm}-{autre_id}" if sens == "sortie"
              else f"RM{autre_rm}-{autre_id} → {rid}")
    bloc = (f"\n## {datetime.now().strftime('%Y-%m-%dT%H:%M')} — Entrée du carnet déplacée ({fleche})\n"
            f"Tokens : 0 | Durée : 0 min\n\nPar {qui}.\n")
    try:
        with open(_log_path(sheet), "a", encoding="utf-8") as f:
            f.write(bloc)
    except OSError:
        pass                      # un journal non écrivable n'empêche pas le déplacement


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    pmout.add_args(ap)
    ap.add_argument("rm_id", type=int)
    for flag, _ in KIND_FLAGS:
        ap.add_argument(f"--{flag}", metavar="TEXTE")
    ap.add_argument("--set", metavar="ID", help="ligne dont on change l'état (avec --state)")
    ap.add_argument("--delete", metavar="ID", help="supprime la ligne pour de bon (entrée incohérente, RM3064)")
    ap.add_argument("--move", metavar="ID", help="RM3258 : déplace la ligne vers le ticket --to")
    ap.add_argument("--to", metavar="RM-ID", type=int, help="ticket destinataire du --move")
    ap.add_argument("--text", metavar="TEXTE",
                    help="RM3161 : AMENDER le texte de la ligne --set, sans toucher à son état")
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
    if a.move:
        if not a.to:
            sys.exit("ERREUR : --move exige --to <rm-id> (le ticket destinataire)")
        if a.to == a.rm_id:
            sys.exit(f"ERREUR : RM{a.rm_id} est déjà le ticket de cette entrée")
        cible = cfg.find_task(a.to)
        if not cible:
            sys.exit(f"ERREUR : ticket RM{a.to} introuvable dans l'arbo PM.")
        # RM2274 : écrire dans le carnet d'un AUTRE projet se dit — `--cross-project`. Le drapeau
        # était déclaré ici sans garde derrière ; le déplacement est la première écriture qui vise
        # une fiche que l'appelant n'a pas nommée en argument principal.
        import pm_scope
        pm_scope.assert_task_scope(a.to, cible, a.cross_project, "pm-task-think --move")
        think_cible = pm_think.think_path(cible)
        kind, row = pm_think.find_row(parsed, a.move)
        if not kind:
            sys.exit(f"ERREUR : ligne {a.move} introuvable dans {think.name}")
        if a.dry_run:
            print(f"{think.name} : {a.move} [{kind}] → {think_cible.name}"); return
        res = pm_think.move_row(think, a.move, think_cible, rm_id=a.to, title=_titre(cible))
        kind, ancien, neuf = res
        for feuille, chemin in ((sheet, think), (cible, think_cible)):
            pm_think.set_counters(feuille, pm_think.counters(pm_think.load(chemin)))
        _log_deplacement(sheet, ancien, "sortie", a.to, neuf, a.by)
        _log_deplacement(cible, neuf, "entrée", a.rm_id, ancien, a.by)
        if kind in ("question", "decision"):     # la vue Redmine des questions change des deux côtés
            _resync_questions(a.rm_id, sheet)
            _resync_questions(a.to, cible)
        pmout.op("think", extra=f"RM{a.rm_id} {ancien} [{kind}] → RM{a.to} {neuf}")
        if not a.no_commit:
            pm_git.autocommit([think, sheet, _log_path(sheet), think_cible, cible, _log_path(cible)],
                              f"pm(think): RM{a.rm_id} {ancien} déplacée vers RM{a.to} {neuf}")
        return
    if a.delete:
        if a.dry_run:
            print(f"{think.name} : {a.delete} supprimée"); return
        n = pm_think.remove_rows(think, [a.delete]) if think.is_file() else 0
        if not n:
            sys.exit(f"ERREUR : ligne {a.delete} introuvable dans {think.name}")
        pm_think.set_counters(sheet, pm_think.counters(pm_think.load(think)))
        pmout.op("think", extra=f"RM{a.rm_id} {a.delete} supprimée")
        if not a.no_commit:
            pm_git.autocommit([think, sheet], f"pm(think): RM{a.rm_id} {a.delete} supprimée")
        return
    if a.set:
        if not a.state and a.text is None:
            sys.exit("ERREUR : --set exige --state ou --text")
        if a.dry_run:
            print(f"{think.name} : {a.set}" + (f" → {a.state}" if a.state else "")
                  + (" (texte amendé)" if a.text is not None else "")); return
        # RM3161 : AMENDER d'abord, changer l'état ensuite — les deux se combinent, et l'amendement
        # seul ne touche pas l'état : corriger le texte d'une décision validée la laisse validée.
        ancien = None
        if a.text is not None:
            ok, ancien = pm_think.set_text(think, a.set, a.text)
            if not ok:
                sys.exit(f"ERREUR : ligne {a.set} introuvable dans {think.name}")
            # L'ancien texte va au JOURNAL du ticket : git garde l'historique du fichier, mais le
            # .log.md est ce qu'on relit — y retrouver « elle disait ceci, elle dit cela » évite
            # d'aller fouiller un diff.
            _log_amendement(a.rm_id, sheet, a.set, ancien, a.text, a.by)
        ok = pm_think.set_state(think, a.set, a.state, dest=a.dest) if a.state else True
        if not ok:
            sys.exit(f"ERREUR : ligne {a.set} introuvable dans {think.name}")
        pm_think.set_counters(sheet, pm_think.counters(pm_think.load(think)))
        if a.set[:1].upper() in ("Q", "D"):          # une question, ou une décision qui peut y répondre
            _resync_questions(a.rm_id, sheet)
        pmout.op("think", extra=f"RM{a.rm_id} {a.set}"
                 + (f" → {pm_think.STATE_ICON[a.state]}" if a.state else "")
                 + (" amendée" if a.text is not None else ""))
        if not a.no_commit:
            quoi = (a.state or "") + (" amendée" if a.text is not None else "")
            pm_git.autocommit([think, sheet, _log_path(sheet)],
                              f"pm(think): RM{a.rm_id} {a.set} {quoi}".rstrip())
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
    title = _titre(sheet)
    rid = pm_think.append(think, kind, text, prefix=prefix, rm_id=a.rm_id, title=title, by=a.by, state=a.state,
                          when=a.when, sid=a.sid, bloque=a.bloque, urgence=a.urgence, domaine=a.domaine,
                          version=a.version, origine=a.origine, lot=a.lot, dest=a.dest)
    pm_think.set_counters(sheet, pm_think.counters(pm_think.load(think)))
    if kind == "question" or (kind == "decision" and pm_think.cite_question(text)):
        _resync_questions(a.rm_id, sheet, kind)      # une question posée, ou sa réponse, se voit tout de suite
    pmout.op("think", extra=f"RM{a.rm_id} +{rid} [{kind}] {text[:80]}")
    if not a.no_commit:
        pm_git.autocommit([think, sheet], f"pm(think): RM{a.rm_id} +{rid}")


if __name__ == "__main__":
    main()
