#!/usr/bin/env python3
"""pm-task-partner — rattache un ticket PM à un ticket d'un gestionnaire PARTENAIRE.

Niveau **N0** du chantier RM2626 ([[Cdc-rm2626-tickets-partenaires]], lot L1/RM2654) :
poser, retirer et consulter le lien. Aucune synchro de contenu ici — le pull des notes
est L2, le push L3.

Sous-commandes :
    link   <RM-id> --instance <inst> --issue <id> [--role mirror|upstream|related]
    unlink <RM-id> --instance <inst> [--issue <id>]
    show   <RM-id>
    pull   <RM-id> | --all        # N1 : importe notes + statut distants (lecture seule)

L'instance doit être un provider **secondaire déclaré du projet** (bloc `providers.task[]`
de son `meta.yml`, cf. RM2653) : un lien vers une instance inconnue serait un lien
qu'aucun outil ne saurait ensuite lire ni synchroniser.

Le `pull` (N1/RM2655) est de la **lecture seule** chez le partenaire et n'écrit que dans
le `.log.md` : notes nouvelles (citées, en-tête nommant l'instance) et statut brut de
leur côté. Il n'y a **aucune** répercussion sur le statut, la priorité ou l'assignation —
le provider primaire reste la seule source de vérité. Le pointeur de lecture
(`last_seen_journal_id`) vit dans le lien, pas dans `redmine_last_journal_id` qui suit
l'instance primaire.

Ce que la commande écrit :
  * `refs[]` du frontmatter (type `partner_issue`) + `updated` ;
  * le CF Redmine « Ticket partenaire » (URL cliquable) — si `REDMINE_CF_PARTNER_ISSUE_ID`
    est configuré ; sans lui, on saute proprement (le lien local reste posé) ;
  * une entrée `.log.md` ;
  * au `link`, une **note de rattachement** chez le partenaire si son `link.note_on_link`
    n'est pas désactivé — best-effort : un partenaire injoignable n'empêche pas de poser
    le lien de notre côté.

Exemples :
    pm-task-partner.py link 2626 --instance redmine-matnat --issue 1234 --role mirror
    pm-task-partner.py show 2626
    pm-task-partner.py unlink 2626 --instance redmine-matnat
"""
import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_git
import pm_partner
from pm_lock import atomic_write, ticket_lock
from pm_output import out
from pm_paths import PMConfig
from pm_registry import Registry, RegistryError
from pm_task import get_task_provider

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# ── I/O tâche ─────────────────────────────────────────────────────────────

def load_task(cfg, rm_id):
    """(path, entity, project, frontmatter, body) — sys.exit si introuvable."""
    path, ent, proj = cfg.locate_task(rm_id)
    if not path:
        out.fail(f"RM{rm_id} introuvable parmi les projets PM")
    content = path.read_text(encoding="utf-8")
    m = FM_RE.match(content)
    if not m:
        out.fail(f"pas de frontmatter dans {path}")
    return path, ent, proj, (yaml.safe_load(m.group(1)) or {}), content[m.end():]


def write_task(path, fm, body):
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    fm_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                             default_flow_style=False).rstrip()
    atomic_write(path, f"---\n{fm_yaml}\n---\n{body}")   # T7 : atomique


def append_log(path, message):
    log_path = path.parent / path.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {ts} — Ticket partenaire (pm-task-partner)\n"
                f"Tokens : 0 | Durée : 0 min\n\n{message}\n")


def autocommit(args, path, message):
    if getattr(args, "no_commit", False):
        return
    pm_git.autocommit([path, path.parent / path.name.replace(".md", ".log.md")], message)


# ── CF Redmine « Ticket partenaire » ──────────────────────────────────────

def partner_cf_id():
    """Id du CF « Ticket partenaire » (`.env :: REDMINE_CF_PARTNER_ISSUE_ID`), ou None.

    Comme pour le protocole de test (RM2229), la **définition** du CF se crée par l'UI
    admin Redmine (l'API ne sait pas le faire) : tant que la variable est absente, le
    lien vit dans le frontmatter et rien n'est poussé — pas d'échec bloquant.
    """
    val = (os.environ.get("REDMINE_CF_PARTNER_ISSUE_ID") or "").strip()
    return int(val) if val.isdigit() else None


def push_cf(rm_id, url):
    """Pousse l'URL du lien principal sur le CF. Retourne True si poussé."""
    cf_id = partner_cf_id()
    if cf_id is None:
        return False
    get_task_provider().update_fields(
        rm_id, custom_fields=[{"id": cf_id, "value": url or ""}])
    return True


# ── contexte projet (registre + secondaires) ──────────────────────────────

def project_context(cfg, ent, proj):
    """(project_meta, registry) — sys.exit si le registre est incohérent."""
    try:
        return cfg.project_meta(ent, proj), Registry.from_config(cfg.providers)
    except RegistryError as e:
        out.fail(f"registre providers invalide (pm.config.yml) : {e}")


# ── Sous-commandes ────────────────────────────────────────────────────────

def cmd_link(cfg, args):
    rm_id = args.rm_id
    with ticket_lock(cfg.state_dir, rm_id):                     # T7 : sérialise le triplet
        path, ent, proj, fm, body = load_task(cfg, rm_id)
        meta, reg = project_context(cfg, ent, proj)
        try:
            res = pm_partner.resolve_secondary(meta, reg, args.instance)
            issue_id = args.issue
            if getattr(args, "create_remote", False):
                # Cas MatNat : le ticket n'existe pas encore chez eux, on le crée puis
                # on rattache dans la foulée. Le titre part tel quel : c'est le sujet
                # commun, pas un contenu interne.
                if issue_id:
                    out.fail("--create-remote et --issue sont exclusifs "
                             "(soit on crée le ticket, soit on en cible un existant)")
                if args.dry_run:
                    out.op("création distante (dry-run)", rm=rm_id,
                           extra=f"{args.instance} ← « {fm.get('title', '')} »")
                    return
                issue_id = pm_partner.create_remote_issue(
                    res, fm.get("title", ""), description=args.remote_description or "")
                if not issue_id:
                    out.fail(f"création chez {args.instance} : aucun id retourné")
                out.info(f"  ticket créé chez {args.instance} : #{issue_id}")
            elif not issue_id:
                out.fail("préciser --issue <id> (ou --create-remote pour le créer)")
            ref = pm_partner.build_ref(res, issue_id, role=args.role, url=args.url)
            pm_partner.check_addition(fm, ref)
        except (pm_partner.PartnerError, RegistryError) as e:
            out.fail(str(e), remede="pm-providers resolve task pour voir les secondaires "
                                    "déclarés du projet")
        if args.dry_run:
            out.op("lien partenaire (dry-run)", rm=rm_id,
                   extra=f"{ref['instance']}#{ref['issue_id']} role={ref['role']}")
            out.info(f"  url  : {ref['url']}")
            out.info(f"  note : {pm_partner.link_note(rm_id, fm.get('title', ''), '')}")
            return
        fm.setdefault("refs", [])
        fm["refs"].append(ref)
        write_task(path, fm, body)

    # Effets distants — hors verrou (I/O réseau), non bloquants.
    note_posted, cf_pushed, warnings = False, False, []
    if not args.no_remote_note and (res.link or {}).get("note_on_link", True):
        try:
            pm_partner.post_link_note(res, ref["issue_id"], rm_id, fm.get("title", ""))
            note_posted = True
        except Exception as e:                                   # noqa: BLE001
            warnings.append(f"note de rattachement non postée chez {res.instance.name} : {e}")
    try:
        cf_pushed = push_cf(rm_id, ref["url"])
    except Exception as e:                                       # noqa: BLE001
        warnings.append(f"CF « Ticket partenaire » non poussé : {e}")

    append_log(path, f"Rattaché à **{ref['instance']}#{ref['issue_id']}** "
                     f"(role={ref['role']}) — {ref['url']}\n"
                     f"note distante : {'oui' if note_posted else 'non'} · "
                     f"CF Redmine : {'oui' if cf_pushed else 'non configuré'}")
    autocommit(args, path, f"pm(partner): RM{rm_id} ↔ {ref['instance']}#{ref['issue_id']}")
    for w in warnings:
        out.warn(w)
    out.op("lien partenaire", rm=rm_id,
           extra=f"{ref['instance']}#{ref['issue_id']} role={ref['role']}"
                 + ("" if cf_pushed else " (CF non configuré)"))


def cmd_unlink(cfg, args):
    rm_id = args.rm_id
    with ticket_lock(cfg.state_dir, rm_id):
        path, ent, proj, fm, body = load_task(cfg, rm_id)
        ref = pm_partner.find_ref(fm, instance=args.instance, issue_id=args.issue)
        if not ref:
            cible = f"{args.instance}" + (f"#{args.issue}" if args.issue else "")
            out.fail(f"RM{rm_id} n'a pas de lien partenaire {cible}",
                     remede=f"pm-task-partner.py show {rm_id}")
        if args.dry_run:
            out.op("délien partenaire (dry-run)", rm=rm_id,
                   extra=f"{ref['instance']}#{ref['issue_id']}")
            return
        fm["refs"] = [r for r in (fm.get("refs") or []) if r is not ref]
        write_task(path, fm, body)

    remaining = pm_partner.partner_refs(fm)
    warnings = []
    try:  # le CF porte le lien principal : on le recale sur ce qui reste (ou on le vide)
        push_cf(rm_id, remaining[0]["url"] if remaining else "")
    except Exception as e:                                       # noqa: BLE001
        warnings.append(f"CF « Ticket partenaire » non mis à jour : {e}")
    append_log(path, f"Délié de **{ref['instance']}#{ref['issue_id']}** "
                     f"(role={ref.get('role')}). Le ticket distant n'est pas modifié.")
    autocommit(args, path, f"pm(partner): RM{rm_id} ⊘ {ref['instance']}#{ref['issue_id']}")
    for w in warnings:
        out.warn(w)
    out.op("délien partenaire", rm=rm_id, extra=f"{ref['instance']}#{ref['issue_id']}")


def _pull_one(cfg, rm_id, args, quiet=False):
    """Pull des liens d'UN ticket. Retourne (nb_liens_avec_nouveautés, nb_erreurs)."""
    path, ent, proj, fm, body = load_task(cfg, rm_id)
    meta, reg = project_context(cfg, ent, proj)
    refs = pm_partner.partner_refs(fm)
    if not refs:
        if not quiet:
            out.warn(f"RM{rm_id} : aucun lien partenaire à synchroniser")
        return 0, 0

    fresh, errors, entries = 0, 0, []
    for ref in refs:
        try:
            res = pm_partner.resolve_secondary(meta, reg, ref.get("instance"))
            updates, remote_title = pm_partner.pull_ref(res, ref)
        except Exception as e:                                   # noqa: BLE001
            # Réseau, accès révoqué, conf incohérente : on signale et on continue —
            # un partenaire en panne ne doit bloquer ni les autres liens ni le PM.
            errors += 1
            out.warn(f"RM{rm_id} · {ref.get('instance')}#{ref.get('issue_id')} : {e}")
            continue
        entry = pm_partner.format_pull_entry(ref, updates, remote_title)
        if entry:
            entries.append((ref, updates, entry))
            fresh += 1

    if not entries:
        if not quiet:
            out.op("pull partenaire", rm=rm_id, extra="rien de neuf")
        return 0, errors
    if args.dry_run:
        for _, _, entry in entries:
            print(entry)
        out.op("pull partenaire (dry-run)", rm=rm_id, extra=f"{fresh} lien(s) avec du neuf")
        return fresh, errors

    # Écriture : journal d'abord (append-only, jamais perdu), puis pointeurs du lien.
    with ticket_lock(cfg.state_dir, rm_id):
        path, ent, proj, fm, body = load_task(cfg, rm_id)      # relecture sous verrou
        for ref, updates, entry in entries:
            append_log(path, entry)
            live = pm_partner.find_ref(fm, instance=ref.get("instance"),
                                       issue_id=ref.get("issue_id"))
            if live is not None:
                pm_partner.apply_pointers(live, updates)
        write_task(path, fm, body)
    autocommit(args, path, f"pm(partner): RM{rm_id} pull ({fresh} lien(s))")
    out.op("pull partenaire", rm=rm_id,
           extra=f"{fresh} lien(s) avec du neuf" + (f", {errors} en échec" if errors else ""))
    return fresh, errors


def cmd_pull(cfg, args):
    if not args.all:
        _pull_one(cfg, args.rm_id, args)
        return
    # Mode balayage (cron) : uniquement les tickets OUVERTS portant un lien — inutile
    # de réveiller un partenaire pour un ticket clos.
    total_fresh, total_err, scanned = 0, 0, 0
    for ent, proj, _ in cfg.iter_projects():
        tasks_dir = cfg.path("tasks_dir", entity=ent, project=proj)
        if not tasks_dir.is_dir():
            continue
        for f in sorted(tasks_dir.glob("RM*.md")):
            if f.name.endswith(".log.md"):
                continue
            m = FM_RE.match(f.read_text(encoding="utf-8"))
            if not m:
                continue
            try:
                fm = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError:
                continue
            if fm.get("status") == "ferme" or not pm_partner.partner_refs(fm):
                continue
            scanned += 1
            fresh, err = _pull_one(cfg, fm.get("redmine_id"), args, quiet=True)
            total_fresh += fresh
            total_err += err
    out.op("pull partenaire --all",
           extra=f"{scanned} ticket(s) scanné(s), {total_fresh} avec du neuf"
                 + (f", {total_err} lien(s) en échec" if total_err else ""))


def cmd_push(cfg, args):
    """Annonce l'état du ticket chez ses partenaires (N2/RM2656)."""
    rm_id = args.rm_id
    path, ent, proj, fm, body = load_task(cfg, rm_id)
    meta, reg = project_context(cfg, ent, proj)
    status = args.status or fm.get("status")
    refs = pm_partner.partner_refs(fm)

    targets = []
    for ref in refs:
        try:
            res = pm_partner.resolve_secondary(meta, reg, ref.get("instance"))
        except (pm_partner.PartnerError, RegistryError) as e:
            out.warn(f"{ref.get('instance')} : {e}")
            continue
        # `--force` sert au push manuel ponctuel ; le hook, lui, respecte sync.push.on
        if args.force or pm_partner.should_push(res, status):
            targets.append((res, ref))

    if not targets:
        if not args.quiet:
            why = ("aucun lien partenaire" if not refs else
                   f"aucun secondaire n'annonce le statut '{status}' "
                   f"(sync.push.on) — --force pour forcer")
            out.op("push partenaire", rm=rm_id, extra=why)
        return

    posted, warnings = [], []
    for res, ref in targets:
        try:
            note = pm_partner.push_status_note(
                res, ref, rm_id, fm.get("title", ""), status,
                close_reason=fm.get("close_reason"), message=args.message or "",
                dry_run=args.dry_run)
        except Exception as e:                                   # noqa: BLE001
            warnings.append(f"{ref.get('instance')}#{ref.get('issue_id')} : {e}")
            continue
        posted.append((ref, note))

    if args.dry_run:
        for ref, note in posted:
            print(f"— vers {ref.get('instance')}#{ref.get('issue_id')} :\n{note}\n")
        out.op("push partenaire (dry-run)", rm=rm_id, extra=f"{len(posted)} destinataire(s)")
        return
    if posted:
        append_log(path, "Note de suivi poussée chez : "
                   + ", ".join(f"**{r.get('instance')}#{r.get('issue_id')}**"
                               for r, _ in posted)
                   + f" (statut `{status}`)\n\n"
                   + "\n".join(f"> {l}" for l in posted[0][1].splitlines()))
        autocommit(args, path, f"pm(partner): RM{rm_id} push statut {status}")
    for w in warnings:
        out.warn(f"note de suivi non postée — {w}")
    if posted or not args.quiet:
        out.op("push partenaire", rm=rm_id,
               extra=f"{len(posted)} note(s) postée(s)"
                     + (f", {len(warnings)} en échec" if warnings else ""))


def cmd_show(cfg, args):
    rm_id = args.rm_id
    path, ent, proj, fm, _ = load_task(cfg, rm_id)
    meta, reg = project_context(cfg, ent, proj)
    refs = pm_partner.partner_refs(fm)
    declared = pm_partner.declared_secondaries(meta, reg)

    print(f"RM{rm_id} — {fm.get('title', '')}")
    print(f"projet : {ent}/{proj}")
    if declared:
        print("secondaires déclarés :")
        for name, r in sorted(declared.items()):
            policy = (r.link or {}).get("policy", "optional")
            print(f"  · {name:16} {r.instance.url or '—':40} policy={policy}")
    else:
        print("secondaires déclarés : aucun "
              "(providers.task[] du meta.yml projet — cf. RM2653)")
    if not refs:
        print("liens partenaires : aucun")
    else:
        print("liens partenaires :")
        for r in refs:
            seen = r.get("last_seen_journal_id")
            print(f"  · {r.get('instance')}#{r.get('issue_id')} "
                  f"role={r.get('role')} depuis {r.get('added')} — {r.get('url')}"
                  + (f" (dernier journal vu : {seen})" if seen else ""))
    missing = pm_partner.missing_links(fm, meta, reg)
    if missing:
        out.warn(f"rattachement OBLIGATOIRE manquant : {', '.join(missing)} "
                 f"(link.policy: required)")
    errs = pm_partner.validate_refs(fm, meta, reg)
    for e in errs:
        out.warn(e)


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    out.add_args(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("link", help="rattache le ticket à un ticket partenaire")
    p.add_argument("rm_id", type=int)
    p.add_argument("--instance", required=True, help="secondaire déclaré du projet")
    p.add_argument("--issue", help="id du ticket chez le partenaire")
    p.add_argument("--create-remote", action="store_true",
                   help="crée le ticket chez le partenaire puis le rattache "
                        "(exige `create.tracker_id` sur le provider secondaire)")
    p.add_argument("--remote-description", default="",
                   help="description du ticket créé chez le partenaire")
    p.add_argument("--role", default="related", choices=list(pm_partner.ROLES))
    p.add_argument("--url", help="URL du ticket distant (défaut : déduite de l'instance)")
    p.add_argument("--no-remote-note", action="store_true",
                   help="ne pas poster la note de rattachement chez le partenaire")
    p.add_argument("--no-commit", action="store_true")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("unlink", help="retire un lien partenaire (n'écrit rien chez eux)")
    p.add_argument("rm_id", type=int)
    p.add_argument("--instance", required=True)
    p.add_argument("--issue", help="précise le ticket si plusieurs liens sur l'instance")
    p.add_argument("--no-commit", action="store_true")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("show", help="liens partenaires + secondaires déclarés")
    p.add_argument("rm_id", type=int)

    p = sub.add_parser("pull", help="importe notes + statut distants dans le .log.md")
    p.add_argument("rm_id", type=int, nargs="?",
                   help="ticket à synchroniser (omis avec --all)")
    p.add_argument("--all", action="store_true",
                   help="balaie tous les tickets OUVERTS portant un lien (cron)")
    p.add_argument("--no-commit", action="store_true")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("push", help="annonce l'état du ticket chez ses partenaires")
    p.add_argument("rm_id", type=int)
    p.add_argument("--status", help="statut annoncé (défaut : celui du ticket)")
    p.add_argument("--message", help="phrase libre ajoutée à la note (revue humaine)")
    p.add_argument("--force", action="store_true",
                   help="poste même si le statut n'est pas dans sync.push.on")
    p.add_argument("--quiet", action="store_true", help="silencieux s'il n'y a rien à faire")
    p.add_argument("--no-commit", action="store_true")
    p.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()
    out.configure(args)
    if args.cmd == "pull" and not args.all and args.rm_id is None:
        ap.error("pull : préciser un <RM-id> ou --all")
    cfg = PMConfig.load()
    {"link": cmd_link, "unlink": cmd_unlink, "show": cmd_show,
     "pull": cmd_pull, "push": cmd_push}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
