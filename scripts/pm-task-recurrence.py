#!/usr/bin/env python3
"""pm-task-recurrence — cycle de vie d'un ticket RÉCURRENT (RM2772).

Certains tickets ne se ferment pas définitivement : ils décrivent une vérification
rejouée à intervalle régulier (ex. RM2771 — mise à jour mensuelle du serveur
Vaultwarden). Le modèle retenu (arbitrage Mathieu 2026-08-21) est **un ticket unique
par sujet, rouvert et retraité à chaque passage** — pas un ticket par run.

Le cycle tient en deux gestes outillés :

    …→ a_tester_demandeur ──park──▶  AU REPOS  ──wake──▶ a_faire → en_cours →…
                                (statut de repos
                                 + `due` au prochain passage)

`park` range le ticket quand le passage est fini ; `wake` le réveille quand
l'échéance est atteinte. Entre les deux, trois champs et eux seuls disent
« récurrent en attente » :

  * le **statut de repos** — `redmine.reference.yml :: recurrence_cf.resting_status`,
    aujourd'hui `en_pause` (l'instance n'a **pas** de statut « Récurrent » dédié,
    vérifié le 2026-09-04 : la REST API ne sait pas en créer un) ;
  * la **périodicité** — CF Redmine « Recurrence » (id 7) ↔ frontmatter `recurrence` ;
  * l'**échéance native `due_date`** ↔ frontmatter `due` — la date du prochain
    passage. Pas de CF maison : Redmine trie, filtre et colore déjà les échus.

Ce triplet est ce qui distingue un récurrent au repos d'un ticket bloqué par un
tiers : une file de relance qui les confondrait deviendrait bruyante, et une file
bruyante finit ignorée.

Sous-commandes :
    set   <RM-id> <quotidienne|hebdomadaire|mensuelle|annuelle>
    clear <RM-id>
    show  <RM-id>
    park  <RM-id> [--from DATE] [--due DATE]   # passage fini → repos + prochaine échéance
    wake  [--apply] [--on DATE] [--entity S]   # récurrents échus → a_faire
    list  [--entity <slug>]                    # récurrents + dernier passage + échéance

⚠ Redmine répond **200/204 et ignore silencieusement** la valeur d'un CF non activé
pour le projet ou le tracker du ticket (piège constaté en RM2657) — et fait de même
sur les attributs natifs quand le compte n'a pas « Edit issues ». On relit donc le
ticket après écriture plutôt que d'annoncer un succès mensonger.

Exemples :
    pm-task-recurrence.py set 2771 mensuelle
    pm-task-recurrence.py park 2771              # rangé jusqu'au mois prochain
    pm-task-recurrence.py wake                   # qui est dû ? (lecture seule)
    pm-task-recurrence.py wake --apply           # les réveiller
"""
import argparse
import calendar
import json
import re
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_git
from pm_lock import atomic_write, ticket_lock
from pm_output import out
from pm_paths import PMConfig
from redmine_utils import (recurrence_cf, recurrence_from_cf,
                           recurrence_resting_status, redmine_creds,
                           update_issue_fields)

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SCRIPTS = Path(__file__).resolve().parent


# ── Calcul de l'échéance ──────────────────────────────────────────────────

def add_months(d, n):
    """`d` décalée de `n` mois, quantième conservé, RABOTÉ sur la fin de mois.

    Un delta en jours ferait dériver la vérification mensuelle d'un mois sur
    l'autre (30 j répétés douze fois = 360, soit cinq jours d'avance par an, et
    « le 21 » finit au 16). Ici le 21 août donne le 21 septembre, et le 31 janvier
    le 28 (ou 29) février faute de 31.

    Le rabot n'est pas rejoué à l'envers : la base de chaque calcul est la date du
    passage RÉELLEMENT effectué, pas le quantième d'origine. Un contrôle du 31
    janvier rangé au 28 février, puis fait le 28, repartira du 28 — le rythme suit
    les passages, il ne poursuit pas une date théorique que personne n'a tenue.
    """
    total = d.month - 1 + n
    year = d.year + total // 12
    month = total % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def next_due(base, recurrence):
    """Date du prochain passage — calcul CALENDAIRE, jamais un delta fixe.

    `base` : date du passage qu'on vient de terminer. Lève ValueError sur une
    périodicité inconnue plutôt que de rendre une date arbitraire.
    """
    if recurrence == "quotidienne":
        return base + timedelta(days=1)
    if recurrence == "hebdomadaire":
        return base + timedelta(days=7)
    if recurrence == "mensuelle":
        return add_months(base, 1)
    if recurrence == "annuelle":
        return add_months(base, 12)
    raise ValueError(f"périodicité inconnue : {recurrence!r}")


def parse_date(value, what):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        out.fail(f"{what} : date attendue au format YYYY-MM-DD (reçu {value!r})")


def is_due(fm, on):
    """Le ticket est-il dû à la date `on` ? (pur — testable sans Redmine)

    Trois conditions, et pas une de moins : une périodicité, une échéance
    atteinte, et le statut de repos. La dernière est ce qui rend `wake`
    idempotent — un ticket déjà réveillé est `a_faire`, donc plus candidat,
    même si son échéance reste dans le passé.
    """
    if not fm.get("recurrence"):
        return False
    if (fm.get("status") or "") != recurrence_resting_status():
        return False
    due = fm.get("due")
    if not due:
        return False
    try:
        return datetime.strptime(str(due), "%Y-%m-%d").date() <= on
    except ValueError:
        return False


# ── I/O tâche ─────────────────────────────────────────────────────────────

def load_task(cfg, rm_id):
    """(path, frontmatter, body) — sys.exit si la fiche est introuvable."""
    path, _ent, _proj = cfg.locate_task(rm_id)
    if not path:
        out.fail(f"RM{rm_id} introuvable parmi les projets PM")
    content = path.read_text(encoding="utf-8")
    m = FM_RE.match(content)
    if not m:
        out.fail(f"pas de frontmatter dans {path}")
    return path, (yaml.safe_load(m.group(1)) or {}), content[m.end():]


def write_task(path, fm, body, expected_updated):
    """Écrit la fiche — optimistic locking sur `updated` (NORMS § locking)."""
    current = path.read_text(encoding="utf-8")
    m = FM_RE.match(current)
    fresh = (yaml.safe_load(m.group(1)) or {}) if m else {}
    if fresh.get("updated") != expected_updated:
        out.fail(f"collision : `updated` a changé pendant l'opération "
                 f"({expected_updated} → {fresh.get('updated')}). Relance la commande.")
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    fm_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                             default_flow_style=False).rstrip()
    atomic_write(path, f"---\n{fm_yaml}\n---\n{body}")   # T7 : atomique


def append_log(path, message):
    log_path = path.parent / path.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {ts} — Récurrence (pm-task-recurrence)\n"
                f"Tokens : 0 | Durée : 0 min\n\n{message}\n")


def autocommit(args, path, message):
    if getattr(args, "no_commit", False):
        return
    pm_git.autocommit([path, path.parent / path.name.replace(".md", ".log.md")],
                      message)


def run_tool(script, *argv):
    """Délègue à un outil PM voisin plutôt que de dupliquer sa logique.

    Le changement de statut porte l'assignation, la note Redmine, le mail et le
    `status_history` : le rejouer ici en dupliquerait les règles, qui divergeraient
    au premier correctif. Le sous-processus prend SON verrou de ticket — d'où
    l'appel HORS de notre `ticket_lock`, sans quoi les deux s'attendraient.
    """
    cmd = [sys.executable, str(SCRIPTS / script), *[str(a) for a in argv]]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


# ── Redmine ───────────────────────────────────────────────────────────────

def fetch_issue(rm_id):
    url, key = redmine_creds()
    req = urllib.request.Request(f"{url.rstrip('/')}/issues/{rm_id}.json?key={key}",
                                 headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r).get("issue") or {}


def read_cf(rm_id, issue=None):
    """Périodicité NORMS portée par le ticket Redmine (ou None)."""
    cf_id, _ = recurrence_cf()
    if not cf_id:
        return None
    issue = issue if issue is not None else fetch_issue(rm_id)
    for c in issue.get("custom_fields") or []:
        if c.get("id") == cf_id:
            return recurrence_from_cf(c.get("value"))
    return None


def read_due(rm_id, issue=None):
    issue = issue if issue is not None else fetch_issue(rm_id)
    return issue.get("due_date") or None


def push_cf(rm_id, recurrence):
    """Pose (ou vide) le CF « Recurrence ». Retourne (posé?, raison si non).

    `recurrence=None` vide le champ côté Redmine. La relecture est le vrai
    contrôle : un CF non activé pour le projet/tracker se fait ignorer en
    silence malgré un HTTP 2xx.
    """
    cf_id, values = recurrence_cf()
    if not cf_id:
        return False, "recurrence_cf absent de redmine.reference.yml"
    if recurrence is not None and recurrence not in values:
        return False, f"périodicité inconnue : {recurrence!r}"
    wanted = str(values[recurrence]) if recurrence else ""
    ok, err = update_issue_fields(rm_id, custom_fields=[{"id": cf_id, "value": wanted}])
    if not ok:
        return False, err
    got = read_cf(rm_id)
    if got != recurrence:
        return False, (f"Redmine a ignoré la valeur (relu : {got!r}) — le CF {cf_id} "
                       "est-il activé pour ce projet et ce tracker ?")
    return True, None


def push_due(rm_id, due, note=None):
    """Pose l'échéance native. Relue après écriture, pour la même raison que le CF :
    sans « Edit issues », Redmine rend 204 et jette l'attribut sans rien dire."""
    wanted = due.isoformat() if due else ""
    ok, err = update_issue_fields(rm_id, due_date=wanted, notes=note)
    if not ok:
        return False, err
    got = read_due(rm_id)
    if (got or None) != (wanted or None):
        return False, (f"Redmine a ignoré l'échéance (relu : {got!r}) — le compte API "
                       "a-t-il le droit « Edit issues » sur ce projet ?")
    return True, None


# ── Sous-commandes ────────────────────────────────────────────────────────

def cmd_set(cfg, args, recurrence):
    rm_id = args.rm_id
    path, fm, body = load_task(cfg, rm_id)
    before = fm.get("recurrence")
    if before == recurrence:
        out.info(f"RM{rm_id} porte déjà recurrence={recurrence or '—'} (rien à faire)")
        return
    with ticket_lock(cfg.state_dir, rm_id):   # sérialise CF + MD + log
        ok, err = push_cf(rm_id, recurrence)
        if not ok:
            out.fail(f"CF Recurrence non posé sur RM{rm_id} : {err}")
        path, fm, body = load_task(cfg, rm_id)   # relecture sous verrou
        expected = fm.get("updated")
        fm["recurrence"] = recurrence
        write_task(path, fm, body, expected)
        label = recurrence or "—"
        append_log(path, f"Récurrence : `{before or '—'}` → `{label}` "
                         f"(CF Redmine 7 « Recurrence » + frontmatter `recurrence`).")
        autocommit(args, path, f"pm(recurrence): RM{rm_id} {before or '—'} → {label}")
    out.op("recurrence", rm_id, recurrence or "—")


def cmd_show(cfg, args):
    rm_id = args.rm_id
    _path, fm, _body = load_task(cfg, rm_id)
    issue = fetch_issue(rm_id)
    local, remote = fm.get("recurrence") or "—", read_cf(rm_id, issue) or "—"
    l_due, r_due = fm.get("due") or "—", read_due(rm_id, issue) or "—"
    flags = []
    if local != remote:
        flags.append("recurrence")
    if str(l_due) != str(r_due):
        flags.append("due")
    tail = f"   ⚠ MD et Redmine divergent ({', '.join(flags)}) → pm-task-sync" if flags else ""
    out.op("recurrence", rm_id,
           f"MD={local} · CF7={remote} | échéance MD={l_due} · Redmine={r_due}"
           f" | statut={fm.get('status') or '?'}{tail}")


def cmd_park(cfg, args):
    """Passage terminé : on range le ticket jusqu'au prochain."""
    rm_id = args.rm_id
    path, fm, _body = load_task(cfg, rm_id)
    rec = fm.get("recurrence")
    if not rec:
        out.fail(f"RM{rm_id} n'est pas récurrent",
                 remede=f"pm-task-recurrence.py set {rm_id} mensuelle")

    base = parse_date(args.from_date, "--from") or date.today()
    due = parse_date(args.due, "--due") or next_due(base, rec)
    if due <= date.today():
        out.fail(f"échéance {due} déjà atteinte — le ticket serait réveillé aussitôt",
                 remede="donne un --from postérieur, ou une --due explicite dans le futur")

    resting = recurrence_resting_status()
    cur = fm.get("status")
    if args.dry_run:
        out.op("park", rm_id, f"[dry-run] {cur} → {resting} · échéance {due} ({rec})")
        return

    # 1. Statut — délégué, et HORS verrou (le sous-processus prend le sien).
    if cur != resting:
        note = (f"Passage récurrent terminé ({rec}). Rangé jusqu'au prochain, "
                f"prévu le {due}.")
        rc, output = run_tool("pm-task-status-update.py", rm_id, resting, "--note", note)
        if rc != 0:
            out.fail(f"statut non posé sur RM{rm_id} : {output.strip()[:400]}")

    # 2. Échéance + frontmatter, sous verrou.
    with ticket_lock(cfg.state_dir, rm_id):
        ok, err = push_due(rm_id, due)
        if not ok:
            out.fail(f"échéance non posée sur RM{rm_id} : {err}")
        path, fm, body = load_task(cfg, rm_id)   # relecture : le statut vient de bouger
        expected = fm.get("updated")
        before_due = fm.get("due")
        fm["due"] = due.isoformat()
        write_task(path, fm, body, expected)
        append_log(path, f"Passage récurrent rangé : statut `{cur}` → `{resting}`, "
                         f"échéance `{before_due or '—'}` → `{due}` "
                         f"(périodicité {rec}, base {base}).")
        autocommit(args, path, f"pm(recurrence): RM{rm_id} rangé jusqu'au {due} ({rec})")
    out.op("park", rm_id, f"{resting} · prochain passage {due} ({rec})")


def scan_recurrents(cfg, entity=None):
    """[(fm, path)] de toutes les fiches portant une `recurrence`."""
    rows = []
    for ent, proj, _p in cfg.iter_projects(entity=entity):
        tasks_dir = cfg.path("tasks_dir", entity=ent, project=proj)
        if not tasks_dir.is_dir():
            continue
        for f in sorted(tasks_dir.glob("RM*.md")):
            if f.name.endswith(".log.md"):
                continue
            m = FM_RE.match(f.read_text(encoding="utf-8"))
            if not m:
                continue
            fm = yaml.safe_load(m.group(1)) or {}
            if fm.get("recurrence"):
                rows.append((fm, f, f"{ent}/{proj}"))
    return rows


def cmd_wake(cfg, args):
    """Réveille les récurrents dont l'échéance est atteinte. Lecture seule par défaut."""
    on = parse_date(args.on, "--on") or date.today()
    due_rows = [(fm, f, proj) for fm, f, proj in scan_recurrents(cfg, args.entity)
                if is_due(fm, on)]
    if not due_rows:
        out.op("wake", extra=f"aucun récurrent dû au {on}")
        return
    out.op("wake", extra=f"{len(due_rows)} récurrent(s) dû(s) au {on}"
                         f"{'' if args.apply else ' — lecture seule, ajoute --apply'}")
    for fm, _f, proj in sorted(due_rows, key=lambda r: str(r[0].get("due"))):
        print(f"RM{fm.get('redmine_id'):<6} échéance {fm.get('due'):<12} "
              f"{str(fm.get('recurrence')):<13} {proj:<28} {str(fm.get('title'))[:50]}")
    if not args.apply:
        return

    for fm, path, _proj in sorted(due_rows, key=lambda r: str(r[0].get("due"))):
        rm_id = fm.get("redmine_id")
        note = (f"Réveil du ticket récurrent : échéance {fm.get('due')} atteinte "
                f"(périodicité {fm.get('recurrence')}). Nouveau passage à réaliser.")
        rc, output = run_tool("pm-task-status-update.py", rm_id, "a_faire", "--note", note)
        if rc != 0:
            out.warn(f"RM{rm_id} : statut non posé — {output.strip()[:200]}")
            continue
        # La checklist décrit LE PASSAGE À FAIRE, pas l'historique : la laisser cochée
        # afficherait 100 % sur un contrôle qui n'a pas eu lieu. L'historique des
        # passages reste dans le `.log.md` et le journal Redmine, tous deux append-only.
        rc, output = run_tool("pm-task-description-update.py", rm_id,
                              "--uncheck-all", "--done-ratio", "auto")
        if rc != 0:
            out.warn(f"RM{rm_id} : checklist non remise à zéro — {output.strip()[:200]}")
        append_log(path, f"Réveil : échéance `{fm.get('due')}` atteinte au {on} → "
                         f"`a_faire`, checklist et done_ratio remis à zéro pour ce passage.")
        autocommit(args, path, f"pm(recurrence): RM{rm_id} réveillé (échéance {fm.get('due')})")
        out.op("wake", rm_id, "a_faire")


def cmd_list(cfg, args):
    today = date.today()
    rows = []
    for fm, _f, proj in scan_recurrents(cfg, args.entity):
        due = str(fm.get("due") or "")
        overdue = bool(due) and due <= today.isoformat()
        rows.append((str(fm.get("recurrence")), str(fm.get("updated") or "?"),
                     f"RM{fm.get('redmine_id')}", str(fm.get("status") or "?"),
                     due or "—", "ÉCHU" if overdue else "", proj,
                     str(fm.get("title") or "")))
    if not rows:
        out.op("recurrents", extra="aucun")
        return
    # Le plus ancien passage en tête : c'est celui qui est le plus probablement dû.
    out.op("recurrents", extra=f"{len(rows)} ticket(s), "
                               f"{sum(1 for r in rows if r[5])} échu(s)")
    for rec, upd, rm, status, due, flag, proj, title in sorted(rows, key=lambda r: r[1]):
        print(f"{rm:<8} {rec:<13} maj {upd:<16} échéance {due:<12} {flag:<5} "
              f"{status:<20} {proj:<28} {title[:50]}")


def main():
    ap = argparse.ArgumentParser(
        description="Cycle de vie d'un ticket récurrent (périodicité, rangement, réveil).")
    ap.add_argument("--no-commit", action="store_true",
                    help="Pas d'auto-commit git des fichiers PM modifiés")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set", help="Pose la périodicité")
    p_set.add_argument("rm_id", type=int)
    p_set.add_argument("recurrence", choices=["quotidienne", "hebdomadaire",
                                              "mensuelle", "annuelle"])

    p_clear = sub.add_parser("clear", help="Retire la périodicité (ticket non récurrent)")
    p_clear.add_argument("rm_id", type=int)

    p_show = sub.add_parser("show", help="Affiche périodicité et échéance (MD + Redmine)")
    p_show.add_argument("rm_id", type=int)

    p_park = sub.add_parser("park", help="Passage terminé → repos + échéance du prochain")
    p_park.add_argument("rm_id", type=int)
    p_park.add_argument("--from", dest="from_date", metavar="YYYY-MM-DD",
                        help="Date du passage qu'on vient de terminer (défaut : aujourd'hui)")
    p_park.add_argument("--due", metavar="YYYY-MM-DD",
                        help="Échéance explicite, court-circuite le calcul calendaire")
    p_park.add_argument("--dry-run", action="store_true")

    p_wake = sub.add_parser("wake", help="Récurrents échus → a_faire (lecture seule par défaut)")
    p_wake.add_argument("--apply", action="store_true", help="Applique le réveil")
    p_wake.add_argument("--on", metavar="YYYY-MM-DD",
                        help="Date de référence (défaut : aujourd'hui)")
    p_wake.add_argument("--entity", help="Limiter à un client / entité")

    p_list = sub.add_parser("list", help="Liste les tickets récurrents")
    p_list.add_argument("--entity", help="Limiter à un client / entité")

    args = ap.parse_args()
    cfg = PMConfig.load()
    if args.cmd == "set":
        cmd_set(cfg, args, args.recurrence)
    elif args.cmd == "clear":
        cmd_set(cfg, args, None)
    elif args.cmd == "show":
        cmd_show(cfg, args)
    elif args.cmd == "park":
        cmd_park(cfg, args)
    elif args.cmd == "wake":
        cmd_wake(cfg, args)
    elif args.cmd == "list":
        cmd_list(cfg, args)


if __name__ == "__main__":
    main()
