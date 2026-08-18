#!/usr/bin/env python3
"""karl-mail-draft — d'un email de la file à un ticket, à la validation (RM2670).

Lot T3 du chantier RM2666 (CDC `docs/cdc-rm2666-emails-vers-tickets.md`), dernier maillon :
proposer un ticket rédigé, puis le créer **quand un humain valide**. L'IA propose,
elle ne décide pas (CDC D1).

Deux gestes, séparés exprès :

    --draft   rédige une proposition (titre, type, priorité, projet, description) et
              l'écrit dans l'entrée de file. RIEN n'est créé.
    --create  crée le ticket depuis la proposition (éventuellement corrigée à la main
              via --title / --type / --project …), journalise le Message-ID d'origine
              et marque l'email traité.

Un email dont le sujet porte `[RM<id>]` n'ouvre JAMAIS de ticket : `--create` y pose une
**note** sur le ticket existant (CDC D6) — c'est une réponse dans un fil, pas une
nouvelle demande.

Garde-fous de la rédaction :
- appel `claude -p` **sans outils**, prompt fermé, sortie **JSON strict** validée ;
- le projet est **choisi dans la liste fournie**, jamais inventé (tripwire NORMS 14) ;
- le type et la priorité viennent des catalogues du PM (`pm-task-add --list-types`) ;
- par défaut, seuls le sujet, l'expéditeur et les premiers caractères du corps sont
  envoyés au modèle (`--body-chars`, `--full-body` pour tout envoyer) — la question
  « le corps complet part-il au LLM ? » est ouverte côté demandeur (CDC § 6).

Usage :
    karl-mail-draft.py --list                       # file + état des propositions
    karl-mail-draft.py --draft <clé>                # propose (n'écrit aucun ticket)
    karl-mail-draft.py --draft all --dry-run        # ce qui serait proposé
    karl-mail-draft.py --show <clé>                 # la proposition en détail
    karl-mail-draft.py --create <clé>               # crée le ticket (ou pose la note)
    karl-mail-draft.py --create <clé> --project calyclay/dolibarr --priority high
    karl-mail-draft.py --dismiss <clé> --reason "pas une demande"
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_output import out                                  # noqa: E402
from pm_paths import PMConfig                              # noqa: E402

PRIORITIES = ["low", "normal", "high", "urgent"]
DEFAULT_MODEL = os.environ.get("KARL_MAIL_DRAFT_MODEL", "claude-opus-5")
DEFAULT_BODY_CHARS = 500          # conservateur tant que la décision D9 n'est pas prise

PROMPT = """Tu prépares un ticket de gestion de projet à partir d'un email reçu par une
agence web. Tu ne t'adresses pas au client : tu rédiges une fiche de travail interne.

Réponds UNIQUEMENT par un objet JSON, sans texte autour ni bloc markdown :
{"actionable": true|false,
 "title": "titre court et factuel, sans 'Re:' ni nom de client",
 "type": "<une valeur de types>",
 "priority": "low|normal|high|urgent",
 "project": "<client/projet pris dans la liste, ou null si aucun ne convient>",
 "description": "contexte reformulé + ce qui est demandé + ce qui reste à clarifier",
 "confidence": 0.0 à 1.0}

Règles :
- "actionable": false si l'email n'appelle aucun travail (remerciement, accusé de
  réception, information sans demande) — dans ce cas, titre et description restent
  courts et le reste peut être null.
- "project" DOIT être une valeur EXACTE de la liste fournie, ou null. N'invente jamais
  un projet, ne déduis pas un nom : hors de la liste, réponds null.
- "type" et "priority" DOIVENT venir des listes fournies.
- Écris en français, au présent, sans formule de politesse.
- La description reprend les faits de l'email (dates, messages d'erreur, URLs) et
  signale explicitement ce qui manque pour agir.
"""


def kmf():
    """Charge karl-mail-fetch (nom à tirets) pour lire/écrire la file."""
    p = Path(__file__).resolve().parent / "karl-mail-fetch.py"
    spec = importlib.util.spec_from_file_location("karl_mail_fetch", p)
    m = importlib.util.module_from_spec(spec)
    sys.modules["karl_mail_fetch"] = m
    spec.loader.exec_module(m)
    return m


def task_types(repo: Path) -> list:
    """Taxonomie canonique — lue depuis pm-task-add, jamais redupliquée (NORMS)."""
    try:
        p = subprocess.run([sys.executable, str(repo / "scripts" / "pm-task-add.py"),
                            "--list-types"], capture_output=True, text=True, timeout=30)
        return [t["value"] for t in json.loads(p.stdout)]
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        out.warn(f"types indisponibles ({type(e).__name__}) — repli sur une liste courte")
        return ["feature", "bugfix", "assistance", "infrastructure", "maintenance",
                "documentation", "research", "autre"]


def candidate_projects(cfg, entry) -> list:
    """Projets proposables. Le routage (RM2669) a déjà tranché le client dans la
    plupart des cas : on ne propose alors QUE ses projets — moins de choix, moins
    d'hallucination. Sinon, tout le catalogue."""
    routing = entry.get("routing") or {}
    client = routing.get("client")
    if client:
        projs = [f"{c}/{p}" for c, p, _ in cfg.iter_projects(entity=client)]
        if projs:
            return projs
    return [f"{c}/{p}" for c, p, _ in cfg.iter_projects()]


def build_payload(entry, args) -> str:
    body = entry.get("body") or ""
    if not args.full_body:
        body = body[:args.body_chars]
    return "\n".join([
        f"De      : {entry.get('from_name') or ''} <{entry.get('from')}>",
        f"Date    : {entry.get('date') or ''}",
        f"Sujet   : {entry.get('subject') or ''}",
        f"Dossier : {entry.get('folder') or ''}",
        "",
        "Corps :",
        body or "(vide)",
    ])


def run_claude(model, payload, timeout=300) -> dict:
    exe = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
    if not Path(exe).exists():
        out.fail("claude introuvable", remede="installe le CLI claude ou renseigne son chemin")
    proc = subprocess.run([exe, "-p", payload, "--model", model],
                          capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"claude rc={proc.returncode} : {proc.stderr.strip()[:300]}")
    m = re.search(r"\{.*\}", proc.stdout, re.DOTALL)
    if not m:
        raise RuntimeError(f"pas de JSON dans la réponse : {proc.stdout.strip()[:300]}")
    return json.loads(m.group(0))


def validate(draft: dict, types: list, projects: list) -> dict:
    """Normalise et BORNE la proposition. Une valeur hors catalogue est écartée, pas
    corrigée en douce : mieux vaut un champ vide qu'un projet inventé."""
    clean, warnings = {}, []
    clean["actionable"] = bool(draft.get("actionable", True))
    title = str(draft.get("title") or "").strip().replace("\n", " ")
    clean["title"] = title[:120]
    t = str(draft.get("type") or "").strip()
    clean["type"] = t if t in types else "autre"
    if t and t not in types:
        warnings.append(f"type hors catalogue ({t}) → autre")
    p = str(draft.get("priority") or "").strip()
    clean["priority"] = p if p in PRIORITIES else "normal"
    if p and p not in PRIORITIES:
        warnings.append(f"priorité hors catalogue ({p}) → normal")
    proj = draft.get("project")
    proj = str(proj).strip() if proj else ""
    if proj and proj not in projects:
        warnings.append(f"projet hors liste ({proj}) → écarté, à choisir à la main")
        proj = ""
    clean["project"] = proj or None
    clean["description"] = str(draft.get("description") or "").strip()
    try:
        clean["confidence"] = max(0.0, min(1.0, float(draft.get("confidence", 0))))
    except (TypeError, ValueError):
        clean["confidence"] = 0.0
    clean["warnings"] = warnings
    return clean


def write_entry(mail, e):
    f = mail.queue_dir() / f"{e['key']}.json"
    f.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        f.chmod(0o600)
    except OSError:
        pass


def pick(items, key):
    key = (key or "").strip().lower()
    for e in items:
        if e.get("key", "").lower() == key:
            return e
    matches = [e for e in items if e.get("key", "").lower().startswith(key)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        out.fail(f"clé ambiguë : {key}", remede="donne la clé complète (--list)")
    out.fail(f"entrée inconnue dans la file : {key}")


def status_of(e) -> str:
    if e.get("created_rm"):
        return f"→ RM{e['created_rm']}"
    if e.get("dismissed"):
        return "écarté"
    if e.get("draft"):
        return "proposé"
    return "à rédiger"


def cmd_list(mail, items):
    for e in items:
        r = e.get("routing") or {}
        target = (r.get("client") or "?") + ("/" + r["project"] if r.get("project") else "")
        d = e.get("draft") or {}
        print(f"  {e['key']}  {status_of(e):10} {target:22.22} "
              f"{(d.get('title') or e.get('subject') or '')[:56]}")
    out.op("file", extra=f"{len(items)} email(s)")


def cmd_show(e):
    d = e.get("draft") or {}
    r = e.get("routing") or {}
    print(f"  email    {e['key']} — {e.get('from_name')} <{e.get('from')}>")
    print(f"  sujet    {(e.get('subject') or '')[:80]}")
    print(f"  routage  {r.get('client') or '(à classer)'}"
          f"{'/' + r['project'] if r.get('project') else ''} ({r.get('source', '—')})")
    if not d:
        print("  (aucune proposition — lance --draft)")
        return
    print(f"  → titre       {d.get('title')}")
    print(f"  → type        {d.get('type')} · priorité {d.get('priority')}")
    print(f"  → projet      {d.get('project') or '(à choisir)'}")
    print(f"  → actionnable {'oui' if d.get('actionable') else 'NON'} "
          f"· confiance {d.get('confidence', 0):.0%}")
    for w in d.get("warnings") or []:
        print(f"  ⚠ {w}")
    print("  → description")
    for line in (d.get("description") or "").splitlines():
        print(f"      {line}")


def cmd_draft(cfg, mail, entries, args, repo):
    types = task_types(repo)
    done = 0
    for e in entries:
        if e.get("created_rm") or e.get("dismissed"):
            continue
        if e.get("draft") and not args.force:
            out.info(f"{e['key']} : proposition déjà présente (--force pour refaire)")
            continue
        projects = candidate_projects(cfg, e)
        payload = build_payload(e, args) + "\n\nProjets possibles :\n" + \
            "\n".join(f"- {p}" for p in projects) + \
            "\n\nTypes possibles :\n" + ", ".join(types) + \
            "\n\nPriorités possibles :\n" + ", ".join(PRIORITIES)
        try:
            raw = run_claude(args.model, PROMPT + "\n\n" + payload)
        except (RuntimeError, ValueError, subprocess.SubprocessError) as err:
            out.warn(f"{e['key']} : rédaction impossible ({err}) — email laissé en file")
            continue
        draft = validate(raw, types, projects)
        draft["model"] = args.model
        draft["at"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
        draft["body_sent"] = "complet" if args.full_body else f"{args.body_chars} car."
        e["draft"] = draft
        if not args.dry_run:
            write_entry(mail, e)
        done += 1
        for w in draft["warnings"]:
            out.warn(f"{e['key']} : {w}")
    out.op("rédaction", extra=(f"{done} proposition(s)" + (" [dry-run]" if args.dry_run else "")))


def cmd_create(cfg, mail, e, args, repo):
    """Crée le ticket — ou pose une note si l'email répond à un ticket existant."""
    if e.get("created_rm"):
        out.fail(f"{e['key']} a déjà donné RM{e['created_rm']}")
    d = e.get("draft") or {}
    # — réponse dans un fil : une NOTE, jamais un doublon de ticket (CDC D6) —
    # `--note-on` couvre le cas fréquent où le client répond dans un fil qui a PERDU
    # le marqueur [RM<id>] (client mail qui réécrit le sujet, transfert…) : le
    # rattachement est alors humain, mais le geste reste le même.
    if args.note_on and not e.get("rm_id"):
        e["rm_id"] = int(args.note_on)
    if e.get("rm_id"):
        note = (f"Email de {e.get('from_name') or ''} <{e.get('from')}> "
                f"({(e.get('date') or '')[:16]}) — sujet « {e.get('subject')} » :\n\n"
                + (e.get("body") or "").strip()[:2000]
                + f"\n\n(Message-ID: {e.get('message_id')})")
        cmd = [sys.executable, str(repo / "scripts" / "pm-task-comment.py"),
               str(e["rm_id"]), "--note", note]
        if args.dry_run:
            out.op("note", extra=f"RM{e['rm_id']} [dry-run] ({len(note)} car.)")
            return
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            out.fail(f"note RM{e['rm_id']} refusée : {(p.stderr or p.stdout).strip()[:300]}")
        e["created_rm"] = e["rm_id"]
        e["outcome"] = "note"
        write_entry(mail, e)
        out.op("note", rm=e["rm_id"], extra=f"depuis l'email {e['key']}")
        return

    title = args.title or d.get("title")
    project = args.project or d.get("project")
    ttype = args.type or d.get("type") or "autre"
    priority = args.priority or d.get("priority") or "normal"
    if not title:
        out.fail("pas de titre", remede=f"--draft {e['key']} d'abord, ou --title « … »")
    if not project or "/" not in project:
        out.fail("projet non déterminé",
                 remede="passe --project client/projet (le routage ne l'a pas tranché)")
    known = [f"{c}/{p}" for c, p, _ in cfg.iter_projects()]
    if project not in known:
        out.fail(f"projet inconnu : {project}", remede="format client/projet, cf. mmi-pm task-list")

    desc = (d.get("description") or "").rstrip() + "\n\n---\n" + "\n".join([
        "Origine : email reçu sur la boîte de karl.",
        f"- De : {e.get('from_name') or ''} <{e.get('from')}>",
        f"- Date : {(e.get('date') or '')[:16]}",
        f"- Sujet : {e.get('subject')}",
        f"- Message-ID : {e.get('message_id')}",
        f"- Rédaction assistée ({d.get('model', '—')}), validée par un humain avant création.",
    ])
    desc_file = mail.state_dir() / f"draft-{e['key']}.md"
    desc_file.write_text(desc, encoding="utf-8")
    cmd = [sys.executable, str(repo / "scripts" / "pm-task-add.py"),
           "--title", title, "--type", ttype, "--priority", priority,
           "--project", project, "--description-file", str(desc_file),
           "--tags", "email", "--porcelain"]
    if args.dry_run:
        out.op("ticket", extra=f"[dry-run] {project} · {ttype}/{priority} · « {title} »")
        return
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(repo))
    rm_id = (p.stdout or "").strip().splitlines()[0] if (p.stdout or "").strip() else ""
    if p.returncode != 0 or not rm_id.isdigit():
        out.fail(f"pm-task-add a échoué : {(p.stderr or p.stdout).strip()[-400:]}")
    desc_file.unlink(missing_ok=True)
    e["created_rm"] = int(rm_id)
    e["outcome"] = "ticket"
    write_entry(mail, e)
    out.op("ticket", rm=rm_id, extra=f"{project} · depuis l'email {e['key']}")


def cmd_dismiss(mail, e, args):
    e["dismissed"] = {"reason": args.reason or "écarté à la main",
                      "at": datetime.now().strftime("%Y-%m-%dT%H:%M")}
    if not args.dry_run:
        write_entry(mail, e)
    out.op("écarté", extra=f"{e['key']} — {e['dismissed']['reason']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    out.add_args(ap)
    ap.add_argument("--list", action="store_true", help="File + état des propositions")
    ap.add_argument("--draft", metavar="CLÉ|all", help="Rédige une proposition")
    ap.add_argument("--show", metavar="CLÉ", help="Détaille une proposition")
    ap.add_argument("--create", metavar="CLÉ", help="Crée le ticket (ou pose la note)")
    ap.add_argument("--dismiss", metavar="CLÉ", help="Écarte cet email")
    ap.add_argument("--reason", help="Motif, avec --dismiss")
    ap.add_argument("--title", help="Corrige le titre à la création")
    ap.add_argument("--type", help="Corrige le type à la création")
    ap.add_argument("--priority", choices=PRIORITIES, help="Corrige la priorité")
    ap.add_argument("--project", help="Impose le projet (client/projet)")
    ap.add_argument("--note-on", metavar="RM_ID",
                    help="Rattache l'email à ce ticket : pose une NOTE au lieu de créer "
                         "(fil dont le sujet a perdu le marqueur [RM<id>])")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Modèle (défaut {DEFAULT_MODEL})")
    ap.add_argument("--body-chars", type=int, default=DEFAULT_BODY_CHARS,
                    help=f"Caractères du corps envoyés au modèle (défaut {DEFAULT_BODY_CHARS})")
    ap.add_argument("--full-body", action="store_true",
                    help="Envoie le corps ENTIER au modèle (décision demandeur, CDC § 6)")
    ap.add_argument("--force", action="store_true", help="Refait une proposition existante")
    ap.add_argument("--dry-run", action="store_true", help="N'écrit rien, ne crée rien")
    args = ap.parse_args()
    out.configure(args)

    cfg = PMConfig.load()
    repo = Path(__file__).resolve().parent.parent
    mail = kmf()
    items = mail.read_queue()
    if not items:
        out.op("file", extra="vide — lance d'abord karl-mail-fetch.py")
        return

    if args.list:
        return cmd_list(mail, items)
    if args.show:
        return cmd_show(pick(items, args.show))
    if args.draft:
        targets = items if args.draft == "all" else [pick(items, args.draft)]
        return cmd_draft(cfg, mail, targets, args, repo)
    if args.create:
        return cmd_create(cfg, mail, pick(items, args.create), args, repo)
    if args.dismiss:
        return cmd_dismiss(mail, pick(items, args.dismiss), args)
    cmd_list(mail, items)


if __name__ == "__main__":
    main()
