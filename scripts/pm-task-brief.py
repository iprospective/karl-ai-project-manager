#!/usr/bin/env python3
"""pm-task-brief — le « pack contexte » d'un ticket en ≤ 30 lignes (RM2363, CDC RM2316 § S2).

Remplace, pour l'onboarding d'un agent sur un ticket, la lecture du MD entier
+ du .log.md entier (+ fetch Redmine) : ~2 000 tokens → ~300. Les fichiers
restent la référence — le brief est un résumé d'accès, pas un nouveau stockage.

Contenu : titre/type/priorité/statut/assigné · estimé vs réel · git/env ·
liens (avec statut live) · critères d'acceptation (cochés/restants) ·
dernières entrées du journal (1 ligne chacune) · journaux Redmine non lus.

Mode reprise (RM2998) : `--reprise` ne résume plus, il RASSEMBLE — séances qui
ont touché le ticket (avec la prochaine étape qui y était notée), demandes
retrouvées, état constaté du code, journal complet. Reprendre un ticket ne doit
pas dépendre de la survie d'une conversation (RM2997 : 42 sessions effacées).

Usage :
    pm-task-brief.py <RM-id>            # brief ≤ 30 lignes
    pm-task-brief.py <RM-id> --json     # même contenu, machine
    pm-task-brief.py <RM-id> --redmine  # + compte réel des journaux non lus (1 GET)
    pm-task-brief.py <RM-id> --reprise  # dossier de reprise, non plafonné
"""
import argparse
import json
import os
import re
import subprocess
import sys
import pathlib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
import pm_roles
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
    # RM2699 : heures TRONQUÉES, jamais arrondies. `{mn/60:.0f}` arrondissait la
    # partie heures alors que les minutes se calculent à part (`mn % 60`) : toute
    # durée à plus de 30 minutes gagnait une heure (90 min → « 2h30 »), et
    # l'arrondi au pair de Python en faisait tomber juste une sur deux (150 →
    # « 2h30 » correct, 210 → « 4h30 » faux). 47 % des durées d'une journée
    # étaient fausses — et c'est cet affichage qui sert à arbitrer.
    mn = mn or 0
    return f"{int(mn // 60)}h{int(mn % 60):02d}" if mn >= 60 else f"{mn:.0f}min"


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


# ── RM2998 : le dossier de reprise ───────────────────────────────────────────
# Le brief d'onboarding RÉSUME (≤ 30 lignes, ~300 tokens) ; le mode reprise
# RASSEMBLE. La différence vient d'une expérience coûteuse : 42 sessions ont été
# effacées avec « toute la réflexion » qu'elles portaient (RM2997), et 87 tickets
# ouverts en dépendaient. Reprendre un ticket ne peut donc pas supposer qu'une
# conversation a survécu — seulement ce qui a été écrit ailleurs et subsiste :
# le worklog de séance, l'historique des demandes, le journal, le dépôt.

WORKLOG_DIR = Path(os.environ.get("PM_SESSION_WORKLOG_DIR")
                   or "~/.claude/session-worklogs").expanduser()
# `history.jsonl` n'est PAS dans le périmètre du nettoyage de Claude Code :
# c'est ce qui reste quand le transcript a disparu.
HISTORY_FILE = Path(os.environ.get("PM_CLAUDE_HISTORY")
                    or "~/.claude/history.jsonl").expanduser()
CLAUDE_STORES = [Path(x).expanduser() for x in
                 (os.environ.get("PM_CLAUDE_STORES") or "~/.claude/projects").split(":")
                 if x.strip()]


def mentions_ticket(text, rm_id):
    """Un texte parle-t-il de CE ticket ?

    « RM2703 » comme « 2703 » — les deux formes se tapent. Mais bornées : sans
    cela un numéro court mord dans « 127030 », dans une taille de fichier, dans
    un horodatage, et le dossier se remplit de bruit."""
    return re.search(rf"(?<![0-9])(?:RM\s*)?{int(rm_id)}(?![0-9])",
                     str(text or ""), re.I) is not None


def worklog_item(wl, rm_id):
    """L'entrée d'un worklog concernant ce ticket, ou None.

    La DERNIÈRE si le worklog en porte plusieurs : c'est l'état atteint en fin
    de séance qui renseigne sur la reprise, pas celui du début."""
    hit = None
    for it in (wl or {}).get("items") or []:
        if str(it.get("ref") or "").strip().upper() == f"RM{int(rm_id)}":
            hit = it
    return hit


def _transcript_of(sid):
    for root in CLAUDE_STORES:
        if not root.is_dir():
            continue
        for pth in root.glob(f"*/{sid}.jsonl"):
            return pth
    return None


def sessions_of_ticket(rm_id):
    """Séances ayant travaillé ce ticket, la plus récente d'abord.

    Chaque ligne dit si son transcript existe encore : c'est ce qui départage
    « tu peux la reprendre » de « il ne reste que ce qui est écrit ici »."""
    found = []
    if not WORKLOG_DIR.is_dir():
        return found
    for f in sorted(WORKLOG_DIR.glob("*.json")):
        try:
            wl = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        it = worklog_item(wl, rm_id)
        if not it:
            continue
        tp = _transcript_of(f.stem)
        try:
            mtime = int(f.stat().st_mtime)
        except OSError:
            mtime = 0
        found.append({
            "session_id": f.stem, "updated": wl.get("updated"), "mtime": mtime,
            "status": it.get("status"), "opened_status": it.get("opened_status"),
            "project": it.get("project"),
            "note": (it.get("note") or "").strip(),
            "next": (it.get("next") or "").strip(),
            "commit": it.get("commit"),
            "transcript": str(tp) if tp else None,
            "notifications": [n.get("message") for n in (wl.get("notifications") or [])
                              if mentions_ticket(n.get("message"), rm_id)],
        })
    found.sort(key=lambda e: e["mtime"], reverse=True)
    return found


def reconstitution_of(sid, projects_root):
    """Fiche de reconstitution d'une séance perdue, si elle existe.

    Quand un transcript a été effacé (RM2997), ce qui a pu être sauvé — demandes
    et worklog — a été déposé dans `docs/sessions-perdues-<date>/<sid>.md`. Le
    dossier de reprise doit y renvoyer : c'est le seul endroit où la séance
    existe encore."""
    if not projects_root:
        return None
    try:
        for pth in pathlib.Path(projects_root).glob(
                f"*/projects/*/docs/sessions-perdues-*/{sid}.md"):
            return str(pth)
    except OSError:
        pass
    return None


def prompts_of(sids, rm_id, limit=60, tous=False):
    """Les demandes de ces séances, dans l'ordre — et leur compte par séance.

    Filtrées sur le ticket par défaut, car une séance en couvre plusieurs. Mais
    une demande parle du SUJET, rarement du numéro : quand le filtre ne rend
    rien, le compte permet de dire qu'il y en a, et `tous=True` les rend toutes.
    Retourne (demandes, {session_id: total de la séance})."""
    if not HISTORY_FILE.is_file() or not sids:
        return [], {}
    keep, wanted, total = [], set(sids), {}
    try:
        with HISTORY_FILE.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                sid = o.get("sessionId")
                if sid not in wanted:
                    continue
                total[sid] = total.get(sid, 0) + 1
                if tous or mentions_ticket(o.get("display"), rm_id):
                    keep.append({"session_id": sid, "ts": o.get("timestamp") or 0,
                                 "text": (o.get("display") or "").strip()})
    except OSError:
        return [], {}
    keep.sort(key=lambda e: e["ts"])
    return keep[-limit:], total


def _git(repo, *a):
    try:
        r = subprocess.run(["git", "-C", str(repo)] + list(a),
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _repo_candidates(fm, md_path):
    """Dépôts où la branche du ticket peut vivre : le worktree noté, puis le
    workspace du projet (lien canonique `<projet PM>/workspace`) et ses envs."""
    cands = []
    wt = (fm.get("git") or {}).get("worktree")
    if wt:
        cands.append(Path(wt))
    ws = md_path.parent.parent / "workspace"
    try:
        if ws.is_symlink() and ws.resolve().is_dir():
            root = ws.resolve()
            cands.append(root)
            if (root / "envs").is_dir():
                cands += sorted(d for d in (root / "envs").iterdir() if d.is_dir())
    except OSError:
        pass
    return [c for c in cands if (c / ".git").exists()]


def code_state(fm, md_path):
    """État CONSTATÉ du code, et non celui que le frontmatter raconte.

    Le frontmatter fige la branche à la prise du ticket ; depuis, elle a pu être
    fusionnée, supprimée, ou n'avoir jamais reçu un seul commit. Pour reprendre,
    la seule chose qui compte est ce que le dépôt dit aujourd'hui."""
    git = fm.get("git") or {}
    br, wt = git.get("branch"), git.get("worktree")
    st = {"branch": br, "mr_url": git.get("mr_url"), "worktree": wt,
          "worktree_exists": bool(wt and Path(wt).is_dir()),
          "repo": None, "branch_exists": False, "base": None,
          "unmerged": [], "merged": None, "dirty": None}
    if not br:
        return st
    for repo in _repo_candidates(fm, md_path):
        local = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{br}")
        remote = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{br}")
        if not (local or remote):
            continue
        ref = br if local else f"origin/{br}"
        base = "origin/dev" if _git(repo, "rev-parse", "--verify", "--quiet",
                                    "refs/remotes/origin/dev") else "origin/main"
        log = _git(repo, "log", "--oneline", "--no-decorate", f"{base}..{ref}") or ""
        st.update(repo=str(repo), branch_exists=True, base=base,
                  unmerged=[x for x in log.splitlines() if x][:20])
        st["merged"] = not st["unmerged"]
        if st["worktree_exists"]:
            d = _git(Path(wt), "status", "--porcelain") or ""
            st["dirty"] = len([x for x in d.splitlines() if x])
        break
    return st


# Entrées de journal qui ne renseignent RIEN sur la reprise : comptabilité de
# tokens et accusés de synchronisation. Sur RM2392, 38 des 49 entrées. Les
# laisser noierait les cinq lignes qu'on est venu lire.
LOG_PLOMBERIE = ("Tick IA", "report → Redmine", "report -> Redmine")


def log_signal(entries):
    """(entrées porteuses, nombre d'entrées de plomberie écartées)."""
    gardees = [e for e in entries or []
               if not str(e.get("by") or "").startswith(LOG_PLOMBERIE)]
    return gardees, len(entries or []) - len(gardees)


def _ts(ms):
    if not ms:
        return "?"
    try:
        return datetime.fromtimestamp(ms / 1000 if ms > 1e11 else ms).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return "?"


def reprise_lines(data):
    """Rendu du dossier de reprise. Pur : prend le dict, rend des lignes."""
    L, rid = [], data["rm_id"]
    ses, code = data.get("sessions") or [], data.get("code") or {}
    L.append("")
    L.append(f"══ REPRISE RM{rid} ══")

    # 1. la prochaine étape la plus récente — la première chose qu'on veut lire
    nxt = next((s for s in ses if s.get("next")), None)
    if nxt:
        L.append("")
        L.append(f"▶ prochaine étape notée le {(nxt.get('updated') or '')[:16]} :")
        for line in nxt["next"].splitlines():
            L.append(f"    {line}")

    # 2. les séances
    L.append("")
    if not ses:
        L.append("séances : aucune séance enregistrée n'a touché ce ticket")
    else:
        L.append(f"séances ({len(ses)}) :")
        for s in ses:
            tag = "transcript présent" if s["transcript"] else "TRANSCRIPT PERDU"
            L.append(f"  {(s.get('updated') or '')[:16]}  {s['session_id'][:8]}  "
                     f"[{s.get('status') or '?'}]  {tag}")
            if s.get("note"):
                L.append(f"      note : {s['note'][:150]}")
            if s.get("commit"):
                L.append(f"      commit : {s['commit']}")
            for m in s.get("notifications") or []:
                L.append(f"      ⚠ {str(m)[:150]}")
            if s["transcript"]:
                L.append(f"      → reprendre : claude --resume {s['session_id']}")
            else:
                n = (data.get("prompts_total") or {}).get(s["session_id"])
                L.append("      → conversation perdue"
                         + (f" ; {n} demande(s) subsistent (voir plus bas)" if n
                            else " ; aucune demande retrouvée non plus"))
                if s.get("reconstitution"):
                    L.append(f"      → reconstitution : {s['reconstitution']}")

    # 3. les demandes retrouvées
    pr = data.get("prompts") or []
    tot = sum((data.get("prompts_total") or {}).values())
    L.append("")
    if pr:
        L.append(f"demandes retrouvées ({len(pr)}"
                 + (f" sur {tot} dans ces séances" if data.get("prompts_filtres") and tot > len(pr)
                    else "") + ") :")
        for e in pr:
            L.append(f"  {_ts(e['ts'])}  {e['session_id'][:8]}")
            txt = e["text"]
            if len(txt) > 900:      # une demande peut être un pavé collé
                txt = txt[:900] + f"\n… (+{len(e['text']) - 900} caractères)"
            for line in txt.splitlines():
                L.append(f"    | {line}")
    elif tot:
        L.append(f"demandes retrouvées : aucune ne NOMME le ticket, mais ces séances en "
                 f"comptent {tot} — une demande parle du sujet, rarement du numéro.")
        L.append(f"    → les voir toutes : pm-task-brief {rid} --reprise --prompts-all")
    else:
        L.append("demandes retrouvées : aucune (history.jsonl muet sur ces séances)")

    # 4. l'état du code, constaté
    L.append("")
    if not code.get("branch"):
        L.append("code : aucune branche notée sur le ticket")
    elif not code.get("branch_exists"):
        L.append(f"code : branche {code['branch']} INTROUVABLE dans les dépôts examinés "
                 "(supprimée après fusion, ou jamais poussée)")
    else:
        etat = "déjà fusionnée" if code.get("merged") else                f"{len(code['unmerged'])} commit(s) NON fusionné(s) sur {code.get('base')}"
        L.append(f"code : {code['branch']} — {etat}")
        for c in code.get("unmerged") or []:
            L.append(f"      {c}")
        if code.get("worktree_exists"):
            d = code.get("dirty")
            L.append(f"      worktree : {code['worktree']}"
                     + (f" ({d} fichier(s) non commité(s))" if d else " (propre)"))
        elif code.get("worktree"):
            L.append(f"      worktree {code['worktree']} : absent")
        if code.get("mr_url"):
            L.append(f"      MR : {code['mr_url']}")

    # 5. le journal, débarrassé de sa plomberie
    lg = data.get("log_full") or []
    gardees, ecartees = log_signal(lg)
    L.append("")
    L.append(f"journal ({len(gardees)} entrées porteuses"
             + (f", {ecartees} de plomberie écartées" if ecartees else "") + ") :")
    for e in gardees:
        L.append(f"  {e['at'][:16]} {e['by'][:48]}")
        if e.get("first"):
            L.append(f"      {e['first'][:180]}")
    return L


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--log", type=int, default=5, metavar="N",
                    help="Nombre d'entrées de journal résumées (défaut 5)")
    ap.add_argument("--redmine", action="store_true",
                    help="Compter réellement les journaux Redmine non lus (1 GET)")
    ap.add_argument("--prompts-all", action="store_true", dest="prompts_all",
                    help="Avec --reprise : TOUTES les demandes des séances concernées, "
                         "pas seulement celles qui nomment le ticket.")
    ap.add_argument("--reprise", action="store_true",
                    help="Dossier de reprise (RM2998) : séances, prochaine étape, "
                         "demandes retrouvées, état constaté du code, journal complet. "
                         "Non plafonné — c'est un dossier, pas un résumé.")
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
    # RM2833 : rôle d'agent SUGGÉRÉ par les étiquettes du ticket (cascade
    # client → projet). Une suggestion, pas une assignation : changer le
    # propriétaire d'un ticket, c'est changer le verrou d'écriture.
    tags = [t for t in (fm.get("tags") or []) if isinstance(t, str)]
    role, role_why = None, ""
    try:
        ent, proj = cfg.entity_project_of_task(md_path) if hasattr(cfg, "entity_project_of_task") \
            else (None, None)
    except Exception:  # noqa: BLE001 — la suggestion ne doit jamais casser un brief
        ent = proj = None
    if ent is None:
        # chemin : …/clients/<entity>/projects/<project>/tasks/RM….md
        parts = md_path.resolve().parts
        if "projects" in parts:
            i = len(parts) - 1 - parts[::-1].index("projects")
            proj = parts[i + 1] if i + 1 < len(parts) else None
            if "clients" in parts:
                j = parts.index("clients")
                ent = parts[j + 1] if j + 1 < len(parts) else None
    if tags and ent and proj:
        try:
            table = pm_roles.merge_table(cfg.client_meta(ent), cfg.project_meta(ent, proj))
            role, role_why = pm_roles.suggest(tags, table)
        except Exception:  # noqa: BLE001
            role, role_why = None, ""

    entries = log_entries(md_path, args.log)
    # RM2998 : le mode reprise n'est pas un brief plus long, c'est une autre
    # question — « avec quoi je repars ? » plutôt que « de quoi s'agit-il ? ».
    reprise = None
    if args.reprise:
        ses = sessions_of_ticket(args.rm_id)
        for _s in ses:
            _s["reconstitution"] = (None if _s["transcript"]
                                    else reconstitution_of(_s["session_id"], cfg.projects_root))
        pr, tot = prompts_of([x["session_id"] for x in ses], args.rm_id,
                             tous=args.prompts_all)
        reprise = {
            "sessions": ses, "prompts_filtres": not args.prompts_all,
            "prompts": None, "prompts_total": None,
            "code": code_state(fm, md_path),
            "log_full": log_entries(md_path, 10000),
        }
        reprise["prompts"], reprise["prompts_total"] = pr, tot
    unread = unread_redmine(fm, args.rm_id, args.redmine)
    # RM3053 : la réflexion du ticket (questions ouvertes, décisions) — ce qui manquait le plus à une reprise
    import pm_think
    _tp = pm_think.think_path(md_path)
    _tparsed = pm_think.load(_tp) if _tp.is_file() else None
    think = {"file": str(_tp), **pm_think.counters(_tparsed)} if _tparsed else None

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
        "tags": tags,
        "think": think,
        "role_hint": {"role": role, "why": role_why} if role else None,
    }
    if reprise:
        data.update(reprise)
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
    if tags:
        L.append("étiquettes : " + ", ".join(tags)
                 + (f" · rôle suggéré : {role} ({pm_roles.agent_file(role)})" if role else ""))
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
    if think:
        L += pm_think.summary(_tparsed, limit=3)[:4]
    if entries:
        L.append(f"log ({len(entries)} dernières) :")
        for e in entries:
            L.append(f"  {e['at'][:16]} {e['by'][:40]} · {e['first'][:90]}")
    if unread and unread.get("unread"):
        L.append(f"redmine : {unread['unread']} journal(aux) non lu(s) → redmine-fetch-updates --issue {args.rm_id}")
    L.append(f"fichier : {md_path.relative_to(cfg.projects_root)}")
    # Le brief reste plafonné à 30 lignes ; le dossier de reprise, jamais — le
    # tronquer reviendrait à couper précisément ce qu'on est venu chercher.
    print("\n".join(L[:30]))
    if reprise:
        print("\n".join(reprise_lines(data)))
        if _tparsed:
            print("\n── réflexion du ticket (" + _tp.name + ") ──")
            print("\n".join(pm_think.summary(_tparsed, limit=12)))


if __name__ == "__main__":
    main()
