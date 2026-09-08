#!/usr/bin/env python3
"""pm-client-notify — notification client à la MEP (RM3026).

Sous-commandes :
    config  <entity/project> [--actif true|false] [--add-contact <ref>] [--remove-contact <ref>]
                administre l'option `notif_client_mep` du meta PROJET (destinataires =
                `ref` d'annuaire du client). Point d'écriture unique de l'option.
    list    <entity/project>          tickets en file de notification (queued, non envoyés).
    preview <entity/project>          aperçu de l'email récap (n'envoie rien).
    send    <entity/project> [--yes]  envoie UN email récap au(x) contact(s) du client,
                puis vide la file (pose sent_at). Sans --yes : aperçu + demande de confirmer.

La file est portée par le frontmatter des tickets (`client_notify`), alimentée à l'entrée
en `en_mep` par pm-task-status-update. Logique pure : pm_client_notify (testée).
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import yaml  # noqa: E402
import pm_client_notify as pcn  # noqa: E402
import pm_markdown as pmd  # noqa: E402
from pm_paths import PMConfig  # noqa: E402
import pm_git  # noqa: E402
from pm_lock import atomic_write  # noqa: E402


# ── résolution projet ────────────────────────────────────────────────────────
def _split_ref(ref):
    if "/" not in ref:
        raise SystemExit(f"pm-client-notify: référence projet attendue `entity/project` (reçu : {ref})")
    entity, project = ref.split("/", 1)
    return entity, project


def _project_dir(cfg, entity, project):
    d = cfg.path("project", entity=entity, project=project)
    if not (d / "meta.yml").is_file():
        raise SystemExit(f"pm-client-notify: projet introuvable : {entity}/{project}")
    return d


def _annuaire(cfg):
    """{ref → fiche} de l'annuaire (RM2703), ou {} s'il n'existe pas encore."""
    try:
        d = cfg.path("contacts_dir")
    except Exception:  # noqa: BLE001
        return {}
    if not d.is_dir():
        return {}
    ann = {}
    for f in sorted(d.glob("*.yml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        ann[data.get("ref") or f.stem] = data
    return ann


# ── file : tickets en attente ────────────────────────────────────────────────
def _clean_criteria(body):
    """Critères d'acceptation en texte propre (checkbox retirée), pour l'email client.
    real_checklist_lines -> [(index, match)] ; CHECK_LINE_RE group(3) = "]<texte>"."""
    out = []
    for _i, m in pmd.real_checklist_lines(body):
        out.append(m.group(3)[1:].strip())
    return [c for c in out if c]


def _queued_tickets(cfg, project_dir):
    """[{path, id, title, url, criteria, protocol}] des tickets en file (pending)."""
    tasks = project_dir / "tasks"
    base = (os.environ.get("REDMINE_URL") or "").rstrip("/")
    out = []
    for md_path in sorted(tasks.glob("RM*.md")):
        text = md_path.read_text(encoding="utf-8")
        fm, body, _ = pmd.split_frontmatter(text)   # split_frontmatter -> (fm, body, end)
        fm = fm or {}
        if not pcn.is_pending(fm):
            continue
        rid = fm.get("redmine_id")
        if rid is None:
            m = re.match(r"RM(\d+)_", md_path.name)
            rid = int(m.group(1)) if m else None
        out.append({
            "path": md_path,
            "id": rid,
            "title": fm.get("title") or "",
            "url": f"{base}/issues/{rid}" if base and rid else "",
            "criteria": _clean_criteria(body),
            # RM3026 : PAS le test_protocol interne (jargon recette : Dolibarr, ids produits…)
            # dans un email CLIENT. Le « quoi » (critères) suffit ; le détail est sur le ticket.
            "protocol": "",
            "queued_at": pcn.queue_state(fm)[0],
        })
    return out


def _mark_all_sent(tickets, now):
    for t in tickets:
        md_path = t["path"]
        text = md_path.read_text(encoding="utf-8")
        m = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", text, re.DOTALL)
        if not m:
            continue
        fm = yaml.safe_load(m.group(2)) or {}
        fm = pcn.mark_sent(fm, now)
        new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
        atomic_write(md_path, f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}")


# ── option projet (écriture du bloc notif_client_mep) ────────────────────────
def _set_notify_block(text, actif, contacts):
    """Remplace (ou ajoute) le bloc top-level `notif_client_mep:` — actif + contacts —
    en préservant le reste du fichier (commentaires inclus)."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"notif_client_mep:\s*$", ln):
            start = i
            break
    block = ["notif_client_mep:", f"  actif: {'true' if actif else 'false'}"]
    if contacts:
        block.append("  contacts:")
        block.extend(f"  - {c}" for c in contacts)
    else:
        block.append("  contacts: []")
    if start is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        return "\n".join(lines + block) + "\n"
    # remplacer l'ancien bloc (clé + lignes indentées suivantes)
    end = start + 1
    while end < len(lines) and (lines[end].startswith((" ", "\t")) or lines[end].strip() == ""):
        if lines[end].strip() == "" and end + 1 < len(lines) and not lines[end + 1].startswith((" ", "\t")):
            break
        end += 1
    return "\n".join(lines[:start] + block + lines[end:]) + ("\n" if text.endswith("\n") else "")


# ── commandes ────────────────────────────────────────────────────────────────
def cmd_config(cfg, args):
    entity, project = _split_ref(args.ref)
    meta_path = _project_dir(cfg, entity, project) / "meta.yml"
    pmeta = cfg.project_meta(entity, project) or {}
    opt = pcn.parse_option(pmeta)
    actif = opt["actif"]
    contacts = list(opt["contacts"])
    if args.actif is not None:
        actif = args.actif.lower() in ("1", "true", "oui", "on", "yes")
    for c in args.add_contact or []:
        if c not in contacts:
            contacts.append(c)
    for c in args.remove_contact or []:
        contacts = [x for x in contacts if x != c]
    new = _set_notify_block(meta_path.read_text(encoding="utf-8"), actif, contacts)
    meta_path.write_text(new, encoding="utf-8")
    pm_git.autocommit([meta_path], f"pm(conf): {entity}/{project} notif_client_mep (RM3026)")
    print(f"✓ notif_client_mep {entity}/{project} : actif={actif} contacts={contacts or '[]'}")


def cmd_list(cfg, args):
    entity, project = _split_ref(args.ref)
    tickets = _queued_tickets(cfg, _project_dir(cfg, entity, project))
    if not tickets:
        print(f"  {entity}/{project} : aucun ticket en file de notification client")
        return
    print(f"  {entity}/{project} : {len(tickets)} ticket(s) à notifier au client :")
    for t in tickets:
        print(f"    RM{t['id']}  {t['title']}  (en file depuis {t['queued_at']})")


def _recipients(cfg, entity, project):
    opt = pcn.parse_option(cfg.project_meta(entity, project) or {})
    if not opt["actif"]:
        raise SystemExit(f"pm-client-notify: option notif_client_mep INACTIVE sur {entity}/{project}")
    recs = pcn.resolve_recipients(_annuaire(cfg), opt["contacts"])
    orphans = [r["ref"] for r in recs if r["orphan"]]
    if orphans:
        print(f"  ⚠ ref(s) d'annuaire inconnue(s), ignorée(s) : {', '.join(orphans)}", file=sys.stderr)
    emails = pcn.recipient_emails(recs)
    if not emails:
        raise SystemExit("pm-client-notify: aucun destinataire résolu (contacts sans email ?)")
    return recs, emails


def _render(cfg, entity, project):
    tickets = _queued_tickets(cfg, _project_dir(cfg, entity, project))
    # nom LISIBLE du projet (meta.name), pas le slug technique, pour l'email client
    name = (cfg.project_meta(entity, project) or {}).get("name") or project
    subject, body = pcn.compose_email(name, tickets)
    return tickets, subject, body


def cmd_preview(cfg, args):
    entity, project = _split_ref(args.ref)
    tickets, subject, body = _render(cfg, entity, project)
    if not tickets:
        print(f"  {entity}/{project} : file vide — rien à envoyer.")
        return
    recs, emails = _recipients(cfg, entity, project)
    print(f"— À : {', '.join(emails)}")
    print(f"— Sujet : {subject}")
    print("— Corps :\n")
    print(body)


def cmd_send(cfg, args):
    from datetime import datetime
    entity, project = _split_ref(args.ref)
    tickets, subject, body = _render(cfg, entity, project)
    if not tickets:
        print(f"  {entity}/{project} : file vide — rien à envoyer.")
        return
    recs, emails = _recipients(cfg, entity, project)
    if not args.yes:
        print(f"— À : {', '.join(emails)}\n— Sujet : {subject}\n— Corps :\n\n{body}\n")
        print(f"→ {len(tickets)} ticket(s). Relance avec --yes pour ENVOYER (email client externe).")
        return
    cmd = [sys.executable, str(HERE / "karl-mail-send.py"), "--subject", subject, "--body", "-"]
    for e in emails:
        cmd += ["--to", e]
    if args.dry_run:
        cmd.append("--dry-run")
    r = subprocess.run(cmd, input=body, text=True)
    if r.returncode != 0:
        raise SystemExit(f"pm-client-notify: envoi échoué (exit {r.returncode})")
    if not args.dry_run:
        _mark_all_sent(tickets, datetime.now().strftime("%Y-%m-%dT%H:%M"))
        pm_git.autocommit([t["path"] for t in tickets],
                          f"pm(notif): {entity}/{project} {len(tickets)} ticket(s) notifiés client (RM3026)")
    print(f"✓ email récap {'(dry-run) ' if args.dry_run else ''}envoyé à {', '.join(emails)} "
          f"— {len(tickets)} ticket(s){'' if args.dry_run else ' (file vidée)'}")


def main():
    ap = argparse.ArgumentParser(description="Notification client à la MEP (RM3026).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("config", help="administrer l'option notif_client_mep du projet")
    p.add_argument("ref", help="entity/project")
    p.add_argument("--actif", help="true|false")
    p.add_argument("--add-contact", action="append", metavar="REF", help="ref d'annuaire à notifier (répétable)")
    p.add_argument("--remove-contact", action="append", metavar="REF", help="retirer une ref (répétable)")

    for name, help_ in (("list", "lister la file"), ("preview", "aperçu de l'email"),
                        ("send", "envoyer l'email récap")):
        q = sub.add_parser(name, help=help_)
        q.add_argument("ref", help="entity/project")
        if name == "send":
            q.add_argument("--yes", action="store_true", help="confirmer l'envoi réel")
            q.add_argument("--dry-run", action="store_true", help="passe --dry-run à karl-mail-send (n'envoie pas, ne vide pas)")

    args = ap.parse_args()
    cfg = PMConfig.load()
    {"config": cmd_config, "list": cmd_list, "preview": cmd_preview, "send": cmd_send}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
