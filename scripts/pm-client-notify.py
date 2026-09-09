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
import json
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


def _parse_ref(ref):
    """`entity/project` → un projet ; `entity` seul → TOUT le client (RM3052 : un
    compte-rendu client couvre plusieurs projets). Renvoie (entity, project|None)."""
    if "/" in ref:
        entity, project = ref.split("/", 1)
        return entity, project
    return ref, None


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


def _queued_tickets(cfg, project_dir, with_protocol=True):
    """[{path, id, title, url, criteria, protocol}] des tickets en file (pending).
    `with_protocol` (RM3052) : inclure ou non le protocole de test dans l'email client."""
    tasks = project_dir / "tasks"
    base = (os.environ.get("REDMINE_URL") or "").rstrip("/")
    out = []
    for md_path in sorted(tasks.glob("RM*.md")):
        text = md_path.read_text(encoding="utf-8")
        # pré-filtre : sans bloc `client_notify:` un ticket n'a jamais été mis en file —
        # inutile de parser son YAML (le balayage tous projets du panneau lit ~1000 fiches).
        if "client_notify:" not in text:
            continue
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
            # RM3052 : le protocole de test est inclus si l'option projet `protocole` est
            # active (défaut oui) — « comment le vérifier » côté client. Coupable par projet
            # quand le protocole est trop interne.
            "protocol": (fm.get("test_protocol") or "") if with_protocol else "",
            "queued_at": pcn.queue_state(fm)[0],
        })
    return out


def _stamp(tickets, fn):
    """Applique `fn(fm)` au frontmatter de chaque ticket et réécrit (atomique)."""
    for t in tickets:
        md_path = t["path"]
        text = md_path.read_text(encoding="utf-8")
        m = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", text, re.DOTALL)
        if not m:
            continue
        fm = fn(yaml.safe_load(m.group(2)) or {})
        new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
        atomic_write(md_path, f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}")


def _mark_all_sent(tickets, now, emails=None):
    """RM3052 : consigne aussi `sent_to` (à QUI le client a été notifié)."""
    _stamp(tickets, lambda fm: pcn.mark_sent(fm, now, emails))


def _mark_all_dismissed(tickets, now):
    """RM3052 : sort les tickets de la file SANS notifier (pas d'email)."""
    _stamp(tickets, lambda fm: pcn.mark_dismissed(fm, now))


# ── périmètre CLIENT (RM3052) : la file de TOUS les projets d'un client ──────
def _client_label(cfg, entity):
    """Nom lisible du client (meta client), à défaut son slug — c'est ce qui part
    dans le sujet de l'email, jamais le slug technique."""
    try:
        return (cfg.client_meta(entity) or {}).get("name") or entity
    except Exception:  # noqa: BLE001 — client sans meta : le slug fait l'affaire
        return entity


def _scan_pending(cfg, entity=None, project=None, rm=None, with_protocol=None):
    """Les projets porteurs d'une file, balayés depuis l'index PM.

    Renvoie [{entity, project, dir, meta, opt, label, tickets}] — un projet sans ticket
    en file n'apparaît pas. `rm` restreint à une sélection d'identifiants (le panneau
    n'envoie QUE les cases cochées) ; `with_protocol` force l'inclusion du protocole,
    None = suivre l'option du projet."""
    want = {str(x) for x in (rm or [])}
    out = []
    for ent, proj, pdir in cfg.iter_projects(entity):
        if project and proj != project:
            continue
        if not (pdir / "meta.yml").is_file():
            continue
        meta = cfg.project_meta(ent, proj) or {}
        opt = pcn.parse_option(meta)
        wp = opt["protocole"] if with_protocol is None else bool(with_protocol)
        try:
            tickets = _queued_tickets(cfg, pdir, wp)
        except OSError:
            continue
        if want:
            tickets = [t for t in tickets if str(t["id"]) in want]
        if not tickets:
            continue
        out.append({"entity": ent, "project": proj, "dir": pdir, "meta": meta, "opt": opt,
                    "label": meta.get("name") or proj, "tickets": tickets})
    return out


def _emails_for(cfg, rows):
    """(emails, orphans) — UNION des contacts des projets ACTIFS de la sélection : un
    compte-rendu client couvrant deux projets part à l'union de leurs destinataires,
    dédoublonnée. Un projet dont l'option est inactive n'apporte aucun destinataire."""
    ann = _annuaire(cfg)
    recs, orphans = [], []
    for r in rows:
        if not r["opt"]["actif"]:
            continue
        for rec in pcn.resolve_recipients(ann, r["opt"]["contacts"]):
            if rec["orphan"]:
                if rec["ref"] not in orphans:
                    orphans.append(rec["ref"])
                continue
            recs.append(rec)
    return pcn.recipient_emails(recs), orphans


def _render_selection(cfg, entity, project, rm, with_protocol):
    """(rows, subject, body, emails, orphans) pour un périmètre + une sélection.

    Périmètre PROJET (`entity/project`) → récap projet, inchangé depuis RM3026.
    Périmètre CLIENT (`entity`) → compte-rendu client, groupé par projet."""
    rows = _scan_pending(cfg, entity, project, rm, with_protocol)
    emails, orphans = _emails_for(cfg, rows)
    if project:
        tickets = rows[0]["tickets"] if rows else []
        name = rows[0]["label"] if rows else project
        subject, body = pcn.compose_email(name, tickets)
    else:
        subject, body = pcn.compose_client_email(
            _client_label(cfg, entity),
            [{"project": r["label"], "tickets": r["tickets"]} for r in rows])
    return rows, subject, body, emails, orphans


def cmd_pending(cfg, args):
    """La file de notification, groupée par CLIENT puis par projet — ce que le panneau
    du cockpit affiche (menu `Calicote (5)`, puis les tickets cochables)."""
    rows = _scan_pending(cfg, args.entity or None)
    by_client = {}
    for r in rows:
        by_client.setdefault(r["entity"], []).append(r)
    data = {"clients": []}
    for ent in sorted(by_client):
        rs = by_client[ent]
        emails, orphans = _emails_for(cfg, rs)
        data["clients"].append({
            "client": ent, "label": _client_label(cfg, ent),
            "count": sum(len(r["tickets"]) for r in rs),
            "recipients": emails, "orphans": orphans,
            "projects": [{
                "project": r["project"], "label": r["label"],
                "actif": r["opt"]["actif"], "protocole": r["opt"]["protocole"],
                "tickets": [{"id": t["id"], "title": t["title"], "url": t["url"],
                             "queued_at": t["queued_at"]} for t in r["tickets"]],
            } for r in rs],
        })
    data["total"] = sum(c["count"] for c in data["clients"])
    data["ok"] = True
    if args.json:
        print(json.dumps(data, ensure_ascii=False))
        return
    if not data["clients"]:
        print("  aucun ticket en file de notification client")
        return
    for c in data["clients"]:
        print(f"  {c['label']} ({c['count']}) — {', '.join(c['recipients']) or 'aucun destinataire'}")
        for p in c["projects"]:
            print(f"    {p['label']}{'' if p['actif'] else '  ⚠ option inactive'}")
            for t in p["tickets"]:
                print(f"      RM{t['id']}  {t['title']}  (en file depuis {t['queued_at']})")


# ── option projet (écriture du bloc notif_client_mep) ────────────────────────
def _set_notify_block(text, actif, contacts, protocole=True):
    """Remplace (ou ajoute) le bloc top-level `notif_client_mep:` — actif + contacts +
    protocole (RM3052) — en préservant le reste du fichier (commentaires inclus)."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"notif_client_mep:\s*$", ln):
            start = i
            break
    block = ["notif_client_mep:", f"  actif: {'true' if actif else 'false'}",
             f"  protocole: {'true' if protocole else 'false'}"]
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
    protocole = opt["protocole"]
    if args.actif is not None:
        actif = args.actif.lower() in ("1", "true", "oui", "on", "yes")
    if getattr(args, "protocole", None) is not None:
        protocole = args.protocole.lower() in ("1", "true", "oui", "on", "yes")
    for c in args.add_contact or []:
        if c not in contacts:
            contacts.append(c)
    for c in args.remove_contact or []:
        contacts = [x for x in contacts if x != c]
    new = _set_notify_block(meta_path.read_text(encoding="utf-8"), actif, contacts, protocole)
    meta_path.write_text(new, encoding="utf-8")
    pm_git.autocommit([meta_path], f"pm(conf): {entity}/{project} notif_client_mep (RM3026)")
    print(f"✓ notif_client_mep {entity}/{project} : actif={actif} protocole={protocole} contacts={contacts or '[]'}")


def cmd_list(cfg, args):
    entity, project, label = _scope(args.ref)
    rows = _scan_pending(cfg, entity, project)
    tickets = [t for r in rows for t in r["tickets"]]
    if not tickets:
        print(f"  {label} : aucun ticket en file de notification client")
        return
    print(f"  {label} : {len(tickets)} ticket(s) à notifier au client :")
    for r in rows:
        if not project:
            print(f"    {r['label']} :")
        for t in r["tickets"]:
            print(f"    {'  ' if not project else ''}RM{t['id']}  {t['title']}  (en file depuis {t['queued_at']})")


def _proto_override(args):
    """RM3052 — override ponctuel du protocole pour CET envoi : None = suivre l'option projet."""
    if getattr(args, "sans_protocole", False):
        return False
    if getattr(args, "avec_protocole", False):
        return True
    return None


def _fail(args, msg):
    """Échec exploitable par l'appelant : en `--json` le message voyage DANS la sortie
    (le panneau l'affiche), sinon sur stderr. Code de retour 1 dans les deux cas."""
    if getattr(args, "json", False):
        print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
        raise SystemExit(1)
    raise SystemExit(f"pm-client-notify: {msg}")


def _scope(ref):
    entity, project = _parse_ref(ref)
    return entity, project, (f"{entity}/{project}" if project else entity)


def cmd_preview(cfg, args):
    entity, project, label = _scope(args.ref)
    rows, subject, body, emails, orphans = _render_selection(
        cfg, entity, project, getattr(args, "rm", None), _proto_override(args))
    n = sum(len(r["tickets"]) for r in rows)
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "to": emails, "subject": subject, "body": body,
                          "count": n, "orphans": orphans}, ensure_ascii=False))
        return
    if not n:
        print(f"  {label} : file vide — rien à envoyer.")
        return
    if orphans:
        print(f"  ⚠ ref(s) d'annuaire inconnue(s), ignorée(s) : {', '.join(orphans)}", file=sys.stderr)
    print(f"— À : {', '.join(emails) or '(aucun destinataire résolu)'}")
    print(f"— Sujet : {subject}")
    print("— Corps :\n")
    print(body)


def cmd_send(cfg, args):
    from datetime import datetime
    entity, project, label = _scope(args.ref)
    rows, subject, body, emails, orphans = _render_selection(
        cfg, entity, project, getattr(args, "rm", None), _proto_override(args))
    tickets = [t for r in rows for t in r["tickets"]]
    if orphans:
        print(f"  ⚠ ref(s) d'annuaire inconnue(s), ignorée(s) : {', '.join(orphans)}", file=sys.stderr)
    if not tickets:
        return _fail(args, f"{label} : file vide (ou sélection hors file) — rien à envoyer")
    if not emails:
        return _fail(args, f"{label} : aucun destinataire résolu "
                           "(option notif_client_mep inactive, ou contacts sans email)")
    if not args.yes:
        print(f"— À : {', '.join(emails)}\n— Sujet : {subject}\n— Corps :\n\n{body}\n")
        print(f"→ {len(tickets)} ticket(s). Relance avec --yes pour ENVOYER (email client externe).")
        return
    cmd = [sys.executable, str(HERE / "karl-mail-send.py"), "--subject", subject, "--body", "-"]
    for e in emails:
        cmd += ["--to", e]
    if args.dry_run:
        cmd.append("--dry-run")
    r = subprocess.run(cmd, input=body, text=True, capture_output=bool(getattr(args, "json", False)))
    if r.returncode != 0:
        return _fail(args, f"envoi échoué (exit {r.returncode}) {((r.stderr or '')[-300:]) if getattr(args, 'json', False) else ''}".strip())
    if not args.dry_run:
        _mark_all_sent(tickets, datetime.now().strftime("%Y-%m-%dT%H:%M"), emails)   # RM3052 : + sent_to
        pm_git.autocommit([t["path"] for t in tickets],
                          f"pm(notif): {label} {len(tickets)} ticket(s) notifiés client (RM3026)")
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "sent": len(tickets), "to": emails, "subject": subject,
                          "rm": [t["id"] for t in tickets], "dry_run": bool(args.dry_run)},
                         ensure_ascii=False))
        return
    print(f"✓ email récap {'(dry-run) ' if args.dry_run else ''}envoyé à {', '.join(emails)} "
          f"— {len(tickets)} ticket(s){'' if args.dry_run else ' (file vidée)'}")


def cmd_dismiss(cfg, args):
    """RM3052 — retire des tickets de la file SANS notifier le client (pas d'email) :
    tout n'a pas à être annoncé. Périmètre projet (`entity/project`) ou client (`entity`) ;
    sans `--rm`, vise TOUTE la file du périmètre."""
    from datetime import datetime
    entity, project, label = _scope(args.ref)
    rows = _scan_pending(cfg, entity, project, args.rm)
    tickets = [t for r in rows for t in r["tickets"]]
    want = {str(x) for x in (args.rm or [])}
    if not tickets:
        msg = (f"{label} : aucun ticket en file à écarter"
               + (f" (rm : {', '.join(sorted(want))})" if want else ""))
        if getattr(args, "json", False):
            print(json.dumps({"ok": True, "dismissed": 0, "note": msg}, ensure_ascii=False))
            return
        print("  " + msg)
        return
    if not args.yes:
        print("À écarter de la notification client (AUCUN email ne partira) :")
        for t in tickets:
            print(f"    RM{t['id']}  {t['title']}")
        print("→ relance avec --yes pour confirmer.")
        return
    _mark_all_dismissed(tickets, datetime.now().strftime("%Y-%m-%dT%H:%M"))
    pm_git.autocommit([t["path"] for t in tickets],
                      f"pm(notif): {label} {len(tickets)} ticket(s) écartés de la notif client (RM3052)")
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "dismissed": len(tickets),
                          "rm": [t["id"] for t in tickets]}, ensure_ascii=False))
        return
    print(f"✓ {len(tickets)} ticket(s) écarté(s) de la file — aucun email envoyé")


def main():
    ap = argparse.ArgumentParser(description="Notification client à la MEP (RM3026).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("config", help="administrer l'option notif_client_mep du projet")
    p.add_argument("ref", help="entity/project")
    p.add_argument("--actif", help="true|false")
    p.add_argument("--protocole", help="true|false — inclure le protocole de test de chaque ticket dans l'email client (défaut : true)")
    p.add_argument("--add-contact", action="append", metavar="REF", help="ref d'annuaire à notifier (répétable)")
    p.add_argument("--remove-contact", action="append", metavar="REF", help="retirer une ref (répétable)")

    # RM3052 — la file de TOUS les clients, groupée : ce que sert le panneau du cockpit
    p = sub.add_parser("pending", help="file de notification groupée par client (panneau cockpit)")
    p.add_argument("entity", nargs="?", help="restreindre à un client (défaut : tous)")
    p.add_argument("--json", action="store_true", help="sortie machine")

    for name, help_ in (("list", "lister la file"), ("preview", "aperçu de l'email"),
                        ("send", "envoyer l'email récap"),
                        ("dismiss", "écarter des tickets SANS notifier (RM3052)")):
        q = sub.add_parser(name, help=help_)
        q.add_argument("ref", help="entity/project (un projet) ou entity (tout le client)")
        if name == "send":
            q.add_argument("--yes", action="store_true", help="confirmer l'envoi réel")
            q.add_argument("--dry-run", action="store_true", help="passe --dry-run à karl-mail-send (n'envoie pas, ne vide pas)")
        if name == "dismiss":
            q.add_argument("--yes", action="store_true", help="confirmer (sans quoi : aperçu de ce qui serait écarté)")
        if name in ("preview", "send", "dismiss"):
            # RM3052 : le panneau n'agit QUE sur les cases cochées — la sélection peut couvrir
            # plusieurs projets du même client (périmètre `entity`).
            q.add_argument("--rm", action="append", metavar="ID",
                           help="ticket visé (répétable ; défaut : toute la file du périmètre)")
            q.add_argument("--json", action="store_true", help="sortie machine")
        if name in ("preview", "send"):   # RM3052 : override ponctuel de l'option projet
            q.add_argument("--avec-protocole", action="store_true", help="forcer l'INCLUSION du protocole de test")
            q.add_argument("--sans-protocole", action="store_true", help="forcer l'EXCLUSION du protocole de test")

    args = ap.parse_args()
    cfg = PMConfig.load()
    {"config": cmd_config, "list": cmd_list, "pending": cmd_pending, "preview": cmd_preview,
     "send": cmd_send, "dismiss": cmd_dismiss}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
