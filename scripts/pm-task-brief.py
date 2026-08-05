#!/usr/bin/env python3
"""pm-task-brief — le « pack contexte » d'un ticket en ≤ 30 lignes (RM2363, CDC RM2316 § S2).

Remplace, pour l'onboarding d'un agent sur un ticket, la lecture du MD entier
+ du .log.md entier (+ fetch Redmine) : ~2 000 tokens → ~300. Les fichiers
restent la référence — le brief est un résumé d'accès, pas un nouveau stockage.

Contenu : titre/type/priorité/statut/assigné · estimé vs réel · git/env ·
liens (avec statut live) · critères d'acceptation (cochés/restants) ·
dernières entrées du journal (1 ligne chacune) · journaux Redmine non lus.

Usage :
    pm-task-brief.py <RM-id>            # brief ≤ 30 lignes
    pm-task-brief.py <RM-id> --json     # même contenu, machine
    pm-task-brief.py <RM-id> --redmine  # + compte réel des journaux non lus (1 GET)
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from pm_output import out

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)
LOG_HDR_RE = re.compile(r"^## (\S+) — (.+)$")
CHECK_RE = re.compile(r"^- \[( |x)\] (.+)$", re.M)


def load_task(cfg, rm_id):
    p = cfg.find_task(rm_id)
    if not p:
        out.fail(f"fichier RM{rm_id}_*.md introuvable")
    m = FM_RE.match(p.read_text(encoding="utf-8"))
    if not m:
        out.fail(f"pas de frontmatter dans {p}")
    return p, (yaml.safe_load(m.group(2)) or {}), m.group(4)


def fmt_tokens(n):
    n = n or 0
    return f"{n/1e6:.1f}M" if n >= 1e6 else (f"{n/1e3:.0f}k" if n >= 1000 else str(int(n)))


def fmt_minutes(mn):
    mn = mn or 0
    return f"{mn/60:.0f}h{mn%60:02.0f}" if mn >= 60 else f"{mn:.0f}min"


def link_status(cfg, rid):
    """Statut live d'un ticket lié (best-effort, cheap)."""
    try:
        p = cfg.find_task(rid)
        if p:
            with p.open(encoding="utf-8") as f:
                in_fm = False
                for line in f:
                    s = line.rstrip()
                    if s == "---":
                        if in_fm:
                            break
                        in_fm = True
                    elif in_fm and s.startswith("status:"):
                        return s.split(":", 1)[1].strip()
    except Exception:
        pass
    return "?"


def criteria(body):
    items = [(st == "x", txt.strip()) for st, txt in CHECK_RE.findall(body)]
    return items


def log_entries(md_path, n):
    """Dernières n entrées du .log.md : (horodatage, auteur, 1re ligne du corps)."""
    log = md_path.parent / md_path.name.replace(".md", ".log.md")
    if not log.is_file():
        return []
    entries = []
    cur = None
    for line in log.read_text(encoding="utf-8").splitlines():
        m = LOG_HDR_RE.match(line)
        if m:
            cur = {"at": m.group(1), "by": m.group(2), "first": ""}
            entries.append(cur)
        elif cur is not None and not cur["first"]:
            s = line.strip()
            if s and not s.startswith("Tokens :"):
                cur["first"] = s
    return entries[-n:]


def unread_redmine(fm, rm_id, live):
    last = fm.get("redmine_last_journal_id")
    if not live:
        return None if last is None else {"since": last}
    try:
        from pm_task import get_task_provider  # seam TaskProvider (P1/RM2543)
        issue = get_task_provider().fetch_issue(rm_id, include="journals")
        journals = issue.get("journals") or []
        new = [j for j in journals if last is None or j["id"] > last]
        return {"since": last, "unread": len(new)}
    except Exception as e:
        out.warn(f"fetch Redmine impossible : {e}")
        return None if last is None else {"since": last}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--log", type=int, default=5, metavar="N",
                    help="Nombre d'entrées de journal résumées (défaut 5)")
    ap.add_argument("--redmine", action="store_true",
                    help="Compter réellement les journaux Redmine non lus (1 GET)")
    ap.add_argument("--json", action="store_true")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    cfg = PMConfig.load()
    md_path, fm, body = load_task(cfg, args.rm_id)

    est, git = fm.get("estimate") or {}, fm.get("git") or {}
    crit = criteria(body)
    n_done = sum(1 for done, _ in crit if done)
    links = []
    for kind, key in (("relates", "relates"), ("dep", "depends_on"), ("blocks", "blocks")):
        for rid in fm.get(key) or []:
            links.append({"kind": kind, "rm_id": rid, "status": link_status(cfg, rid)})
    subs = [{"rm_id": rid, "status": link_status(cfg, rid)}
            for rid in fm.get("sub_tasks") or []]
    entries = log_entries(md_path, args.log)
    unread = unread_redmine(fm, args.rm_id, args.redmine)

    data = {
        "rm_id": args.rm_id, "title": fm.get("title"), "type": fm.get("type"),
        "priority": fm.get("priority"), "status": fm.get("status"),
        "assigned_to": fm.get("assigned_to"), "completion_pct": fm.get("completion_pct"),
        "estimate": {k: est.get(k) for k in
                     ("difficulty", "ai_time_minutes", "human_time_minutes", "tokens",
                      "cost_usd", "confidence")},
        "actual": {"tokens": fm.get("tokens_total"), "cost_usd": fm.get("cost_total_usd"),
                   "ai_minutes": fm.get("ai_time_total_minutes"),
                   "human_minutes": fm.get("human_time_total_minutes")},
        "git": {"branch": git.get("branch"), "mr_url": git.get("mr_url")},
        "test_url": fm.get("test_url"),
        "links": links,
        "sub_tasks": subs,
        "parent_task": fm.get("parent_task"),
        "criteria": {"done": n_done, "total": len(crit),
                     "next": [t for d, t in crit if not d][:4]},
        "log": entries,
        "redmine_unread": unread,
        "task_file": str(md_path),
    }
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=1, default=str))
        return

    L = []
    L.append(f"RM{args.rm_id} {fm.get('title')} — {fm.get('type')}/{fm.get('priority')} — "
             f"{fm.get('status')}"
             + (f" (assigné : {fm.get('assigned_to')})" if fm.get("assigned_to") else ""))
    L.append(f"estimé : {est.get('difficulty')} · {fmt_minutes(est.get('ai_time_minutes'))} IA"
             f" + {fmt_minutes(est.get('human_time_minutes'))} H · {fmt_tokens(est.get('tokens'))} tok"
             + (f" ≈ {est.get('cost_usd')}$" if est.get("cost_usd") else "")
             + (f" (conf {est.get('confidence')})" if est.get("confidence") else "")
             + f" | réel : {fmt_tokens(fm.get('tokens_total'))} tok · "
             f"{fm.get('cost_total_usd') or 0:.2f}$ · {fmt_minutes(fm.get('ai_time_total_minutes'))} IA")
    L.append(f"git : branche={git.get('branch') or '—'} MR={git.get('mr_url') or '—'}"
             + (f" test={fm.get('test_url')}" if fm.get("test_url") else ""))
    if links:
        L.append("liens : " + " ".join(f"{l['kind']}:RM{l['rm_id']}({l['status']})" for l in links[:8]))
    if subs:
        open_ = [s for s in subs if s["status"] not in ("ferme",)]
        L.append(f"sous-tâches ({len(subs) - len(open_)}/{len(subs)} fermées) : "
                 + " ".join(f"RM{s['rm_id']}({s['status']})" for s in open_[:8]))
    if fm.get("parent_task"):
        L.append(f"parent : RM{fm['parent_task']}")
    if crit:
        nxt = " ; ".join(t[:60] for t in data["criteria"]["next"][:3])
        L.append(f"critères ({n_done}/{len(crit)})" + (f" : → {nxt}" if nxt else " : tous cochés"))
    if entries:
        L.append(f"log ({len(entries)} dernières) :")
        for e in entries:
            L.append(f"  {e['at'][:16]} {e['by'][:40]} · {e['first'][:90]}")
    if unread and unread.get("unread"):
        L.append(f"redmine : {unread['unread']} journal(aux) non lu(s) → redmine-fetch-updates --issue {args.rm_id}")
    L.append(f"fichier : {md_path.relative_to(cfg.projects_root)}")
    print("\n".join(L[:30]))


if __name__ == "__main__":
    main()
