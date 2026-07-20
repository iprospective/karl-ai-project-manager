#!/usr/bin/env python3
"""pm-bench-overhead — Benchmark de la surconsommation de la couche PM (RM2275).

Parse les transcripts Claude Code (`~/.claude/projects/*/*.jsonl`), attribue
chaque session à son ticket RM (mêmes heuristiques que pm-task-tick, sans le
filtre « ticket fermé » : le benchmark est historique) et ventile la dépense
en trois catégories :

  pm-onboarding : lecture du contexte PM (NORMS/KERNEL, modules, agents/*,
                  CLAUDE.md/AGENTS.md, cascade .mmi-pm project/docs/meta)
  pm-ceremony   : cérémonie d'outillage PM — exécution de scripts pm-*/redmine-*,
                  skills mmi-pm-*, lectures/écritures des fichiers de ticket
                  (.mmi-pm/tasks, .log.md), commits de fichiers PM
  work          : tout le reste (le travail utile du ticket)

Unité de mesure : l'appel API (messages assistant dédupliqués par message.id,
les retries écrasent). Pour chaque appel :
  - les output_tokens sont ventilés au prorata des tool_use par catégorie
    (appel sans tool_use = work) ;
  - les tool_result sont mesurés (octets/3.6 ≈ tokens) et rattachés à la
    catégorie de leur tool_use → « contexte injecté » par catégorie.

Coût marginal attribuable (modèle documenté dans le rapport RM2275) : un token
injecté (tool_result ou output) coûte son écriture en cache puis R relectures :
    cache_creation + R × cache_read            [+ output s'il est généré]
où R est calibré par session sur l'usage réel :
    R = Σ cache_read_input_tokens / Σ cache_creation_input_tokens
(nombre moyen de relectures d'un token créé, compaction/éviction incluses de
fait — un modèle positionnel (n-i) surcompte dès que la session est longue).

Limites assumées (v1) :
  - estimation octets/3.6 pour le contexte injecté (pas de tokenizer offline) ;
  - attribution session→ticket globale (pas par tour) ;
  - sur le projet pm-ai-agents, développer l'outillage PM EST le travail :
    l'édition de scripts/*.py reste classée work, seule l'EXÉCUTION des
    outils PM et la manipulation des fichiers PM comptent en cérémonie —
    comparer avec un workspace non-PM pour contrôler le biais.

Usage :
    pm-bench-overhead.py                          # tous les workspaces
    pm-bench-overhead.py --workspace iprospective-ai-project-management
    pm-bench-overhead.py --since 2026-07-01 --top 15
    pm-bench-overhead.py --json                   # sortie machine
"""
import argparse
import importlib.util
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

_spec = importlib.util.spec_from_file_location("pm_task_tick", _HERE / "pm-task-tick.py")
_tick = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tick)

BYTES_PER_TOKEN = 3.6  # même convention que pm-context-budget (RM1943)

# ── Classification ──────────────────────────────────────────────────────────

# Exécution d'outillage PM (Bash) — cérémonie.
_CEREMONY_CMD_RE = re.compile(
    r"(?:pm|redmine|karl)-[a-z-]+\.py\b"        # scripts pm-*/redmine-*/karl-*
    r"|\bpm-mr\b|\bpm-pre-push\b"
    r"|git-credential-pm"
    r"|/\.mmi-pm/|\.mmi-pm/tasks|CURRENT_TASK"
    r"|\.log\.md\b"
)
# Contexte PM (Read/Bash cat) — onboarding.
_ONBOARDING_PATH_RE = re.compile(
    r"/norms/|/agents/(?:worker|reviewer|orchestrateur|summarizer)"
    r"|(?:CLAUDE|AGENTS|NORMS(?:-KERNEL)?)\.md\b"
    r"|\.mmi-pm/(?:project|docs|meta\.yml|memory)"
    r"|knowledge/INDEX\.md"
)
# Fichiers de ticket (.mmi-pm/tasks, RM<id>_*.md) — cérémonie.
_TICKET_FILE_RE = re.compile(r"\.mmi-pm/tasks/|RM\d{2,6}_[^/]*\.(?:log\.)?md\b")
# Code (le développement d'outillage PM reste du travail).
_CODE_PATH_RE = re.compile(r"\.(?:py|js|ts|php|sh|ya?ml|sql|css|html)\b")

CATEGORIES = ("pm-onboarding", "pm-ceremony", "work")


def classify_tool_use(name, inp):
    """Catégorie d'un bloc tool_use."""
    if name == "Bash":
        cmd = str(inp.get("command", ""))
        if _ONBOARDING_PATH_RE.search(cmd) and not _CEREMONY_CMD_RE.search(cmd):
            return "pm-onboarding"
        if _CEREMONY_CMD_RE.search(cmd):
            return "pm-ceremony"
        return "work"
    if name in ("Read", "Edit", "Write", "NotebookEdit"):
        path = str(inp.get("file_path", ""))
        if _TICKET_FILE_RE.search(path):
            return "pm-ceremony"
        if _ONBOARDING_PATH_RE.search(path) and not (
            name in ("Edit", "Write") and _CODE_PATH_RE.search(path)
        ):
            return "pm-onboarding"
        return "work"
    if name == "Skill":
        return "pm-ceremony" if str(inp.get("skill", "")).startswith("mmi-pm-") else "work"
    return "work"


# ── Parcours d'une session ──────────────────────────────────────────────────

def _usage_tokens(usage):
    return {
        "input": usage.get("input_tokens", 0) or 0,
        "output": usage.get("output_tokens", 0) or 0,
        "cache_read": usage.get("cache_read_input_tokens", 0) or 0,
        "cache_creation": usage.get("cache_creation_input_tokens", 0) or 0,
    }


def _result_text_len(block):
    """Taille texte d'un bloc tool_result (str ou liste de blocs texte)."""
    content = block.get("content")
    if isinstance(content, str):
        return len(content)
    n = 0
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                n += len(str(c.get("text", "")))
    return n


_SCRIPT_NAME_RE = re.compile(r"((?:pm|redmine|karl)-[a-z][a-z-]*)\.py\b")


def op_label(name, inp, cat):
    """Étiquette d'opération PM pour le breakdown par script (RM2361/S0)."""
    if name == "Bash":
        m = _SCRIPT_NAME_RE.search(str(inp.get("command", "")))
        if m:
            return "bash:" + m.group(1)
        return "bash:manip-fichiers-pm" if cat == "pm-ceremony" else "bash:contexte-pm"
    if name == "Skill":
        return "skill:" + str(inp.get("skill", ""))
    path = str(inp.get("file_path", ""))
    kind = "ticket-md" if _TICKET_FILE_RE.search(path) else "contexte-pm"
    return "%s:%s" % (name.lower(), kind)


def _sentinel_rm_id(cwd):
    """RM-id du sentinel .mmi-pm/CURRENT_TASK le plus proche de cwd (≤ 6 niveaux)."""
    p = Path(cwd)
    for _ in range(6):
        f = p / ".mmi-pm" / "CURRENT_TASK"
        try:
            if f.is_file():
                m = re.search(r"(\d{2,6})", f.read_text(encoding="utf-8"))
                return int(m.group(1)) if m else None
        except OSError:
            return None
        if p.parent == p:
            break
        p = p.parent
    return None


def scan_session(path):
    """Analyse un transcript JSONL → dict session, ou None si vide/sans usage."""
    events = _tick._load_transcript(path)
    if not events:
        return None

    calls = {}        # message.id → appel API (retries écrasés)
    order = []        # ids dans l'ordre de première apparition
    tooluse_cat = {}  # tool_use id → (catégorie, message.id, label d'opération)
    evidence = defaultdict(int)   # rm_id → poids cumulé
    ops = defaultdict(lambda: [0, 0])   # label → [appels, octets injectés]
    ts_first = ts_last = None
    last_cwd = None

    for evt in events:
        ts = evt.get("timestamp")
        if ts:
            ts_first = ts_first or ts
            ts_last = ts
        if evt.get("cwd"):
            last_cwd = evt["cwd"]
        for rid, strength in _tick._evidence_from_event(evt):
            evidence[rid] += strength
        etype = evt.get("type")
        msg = evt.get("message") or {}
        if etype == "assistant" and isinstance(msg, dict):
            mid = msg.get("id")
            usage = msg.get("usage")
            if not mid or not isinstance(usage, dict):
                continue
            call = calls.get(mid)
            if call is None:
                call = {"usage": None, "model": msg.get("model"), "blocks": []}
                calls[mid] = call
                order.append(mid)
            call["usage"] = _usage_tokens(usage)   # retry : le dernier gagne
            for b in msg.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    name, inp = b.get("name") or "", b.get("input") or {}
                    cat = classify_tool_use(name, inp)
                    call["blocks"].append(cat)
                    label = op_label(name, inp, cat) if cat != "work" else None
                    if label:
                        ops[label][0] += 1
                    tooluse_cat[b.get("id")] = (cat, mid, label)
        elif etype == "user" and isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        ref = tooluse_cat.get(b.get("tool_use_id"))
                        if ref:
                            cat, mid, label = ref
                            nbytes = _result_text_len(b)
                            calls[mid].setdefault("injected", defaultdict(int))[cat] += nbytes
                            if label:
                                ops[label][1] += nbytes

    if not order:
        return None

    n = len(order)
    created = sum(c["usage"]["cache_creation"] for c in calls.values())
    reread = sum(c["usage"]["cache_read"] for c in calls.values())
    r_factor = (reread / created) if created else 0.0
    out_by_cat = defaultdict(int)
    inj_by_cat = defaultdict(float)
    marginal = defaultdict(float)   # catégorie → coût USD marginal attribuable
    totals = defaultdict(int)
    cost_total = 0.0
    models = defaultdict(int)
    pricing = _tick.load_pricing()

    for mid in order:
        call = calls[mid]
        u = call["usage"]
        for k, v in u.items():
            totals[k] += v
        model = call["model"] or ""
        models[model] += u["output"]
        cost_total += _tick.compute_cost_usd(
            model, u["input"], u["output"], u["cache_read"], u["cache_creation"], pricing)

        m = (pricing.get("models") or {}).get(model) or {}
        p_out = m.get("output_per_mtok_usd", 0) / 1e6
        p_cc = m.get("cache_creation_per_mtok_usd", 0) / 1e6
        p_cr = m.get("cache_read_per_mtok_usd", 0) / 1e6
        persist = p_cc + r_factor * p_cr   # coût d'un token injecté (écriture + R relectures)

        # output ventilé au prorata des tool_use ; sans tool_use → work
        blocks = call["blocks"] or ["work"]
        share = 1.0 / len(blocks)
        for cat in blocks:
            tk = u["output"] * share
            out_by_cat[cat] += tk
            marginal[cat] += tk * (p_out + persist)
        for cat, nbytes in (call.get("injected") or {}).items():
            tk = nbytes / BYTES_PER_TOKEN
            inj_by_cat[cat] += tk
            marginal[cat] += tk * persist

    attribution = "transcript"
    rm_id = max(evidence.items(), key=lambda kv: kv[1])[0] if evidence else None
    if rm_id is None and last_cwd:
        # signal FAIBLE (RM2361/S0) : sentinel projet du workspace de la session
        rm_id = _sentinel_rm_id(last_cwd)
        attribution = "sentinel" if rm_id is not None else "aucune"
    first = calls[order[0]]["usage"]
    return {
        "session": Path(path).stem,
        "rm_id": rm_id,
        "attribution": attribution,
        "n_calls": n,
        "r_factor": round(r_factor, 1),
        "ts_first": ts_first,
        "ts_last": ts_last,
        "totals": dict(totals),
        "cost_usd": round(cost_total, 4),
        "first_call": first,
        "output_by_cat": {c: round(out_by_cat.get(c, 0)) for c in CATEGORIES},
        "injected_by_cat": {c: round(inj_by_cat.get(c, 0)) for c in CATEGORIES},
        "marginal_cost_by_cat": {c: round(marginal.get(c, 0), 4) for c in CATEGORIES},
        "ops": {k: {"calls": v[0], "injected_tokens": round(v[1] / BYTES_PER_TOKEN)}
                for k, v in ops.items()},
        "models": dict(models),
    }


# ── Agrégation & rendu ──────────────────────────────────────────────────────

def aggregate(sessions):
    by_ticket = defaultdict(lambda: {
        "sessions": 0, "n_calls": 0, "tokens": 0, "cost_usd": 0.0,
        "output_by_cat": defaultdict(int), "injected_by_cat": defaultdict(int),
        "marginal_cost_by_cat": defaultdict(float),
    })
    for s in sessions:
        key = f"RM{s['rm_id']}" if s["rm_id"] else "(untracked)"
        t = by_ticket[key]
        t["sessions"] += 1
        t["n_calls"] += s["n_calls"]
        t["tokens"] += sum(s["totals"].values())
        t["cost_usd"] += s["cost_usd"]
        for c in CATEGORIES:
            t["output_by_cat"][c] += s["output_by_cat"][c]
            t["injected_by_cat"][c] += s["injected_by_cat"][c]
            t["marginal_cost_by_cat"][c] += s["marginal_cost_by_cat"][c]
    return by_ticket


def pm_share(entry):
    """Part PM (%) du coût marginal attribuable."""
    m = entry["marginal_cost_by_cat"]
    pm = m["pm-onboarding"] + m["pm-ceremony"]
    tot = pm + m["work"]
    return 100.0 * pm / tot if tot > 0 else 0.0


def fmt_tk(n):
    return f"{n/1e6:.1f}M" if n >= 1e6 else (f"{n/1e3:.0f}k" if n >= 1000 else str(int(n)))


def global_stats(sessions):
    """Agrégats globaux d'une liste de sessions (part PM, catégories, ops)."""
    marg = {c: sum(s["marginal_cost_by_cat"].get(c, 0) for s in sessions) for c in CATEGORIES}
    pm = marg["pm-onboarding"] + marg["pm-ceremony"]
    tot = pm + marg["work"]
    ops = defaultdict(lambda: [0, 0])
    for s in sessions:
        for k, v in (s.get("ops") or {}).items():
            ops[k][0] += v.get("calls", 0)
            ops[k][1] += v.get("injected_tokens", 0)
    return {
        "sessions": len(sessions),
        "billed_usd": round(sum(s["cost_usd"] for s in sessions), 2),
        "pm_share_pct": round(100 * pm / tot, 1) if tot else 0.0,
        "marginal_by_cat": {k: round(v, 2) for k, v in marg.items()},
        "ops": {k: {"calls": v[0], "injected_tokens": v[1]} for k, v in ops.items()},
    }


COMPARE_ALERT_PTS = 2.0


def render_compare(base, cur, base_name):
    """Comparaison vs baseline (RM2361/S0). Retourne (texte, dérive_bool)."""
    d = cur["pm_share_pct"] - base["pm_share_pct"]
    lines = [
        "== pm-bench-overhead --compare vs %s ==" % base_name,
        "part PM : %.1f %% → %.1f %% (%+.1f pts)  [alerte : > +%.0f pts]"
        % (base["pm_share_pct"], cur["pm_share_pct"], d, COMPARE_ALERT_PTS),
        "coût marginal $ : onboarding %.2f→%.2f · cérémonie %.2f→%.2f · work %.2f→%.2f"
        % (base["marginal_by_cat"]["pm-onboarding"], cur["marginal_by_cat"]["pm-onboarding"],
           base["marginal_by_cat"]["pm-ceremony"], cur["marginal_by_cat"]["pm-ceremony"],
           base["marginal_by_cat"]["work"], cur["marginal_by_cat"]["work"]),
    ]
    movers = []
    for k in set(base["ops"]) | set(cur["ops"]):
        b = (base["ops"].get(k) or {}).get("injected_tokens", 0)
        c = (cur["ops"].get(k) or {}).get("injected_tokens", 0)
        if b or c:
            movers.append((abs(c - b), k, b, c))
    movers.sort(reverse=True)
    if movers:
        lines.append("top mouvements (tokens injectés) : " + " · ".join(
            "%s %s→%s" % (k, fmt_tk(b), fmt_tk(c)) for _, k, b, c in movers[:5]))
    drift = d > COMPARE_ALERT_PTS
    lines.append("⚠ DÉRIVE au-dessus du seuil" if drift else "✓ sous le seuil")
    return "\n".join(lines), drift


def main():
    ap = argparse.ArgumentParser(
        description="Benchmark de la surconsommation de la couche PM (RM2275).")
    ap.add_argument("--projects-dir", default=str(Path.home() / ".claude" / "projects"))
    ap.add_argument("--workspace", action="append", default=[],
                    help="Filtre sur le nom de dossier workspace (substring, cumulable)")
    ap.add_argument("--since", help="Ignore les sessions terminées avant cette date (YYYY-MM-DD)")
    ap.add_argument("--top", type=int, default=20, help="Top N tickets affichés")
    ap.add_argument("--min-tokens", type=int, default=100_000,
                    help="Ignore les sessions plus petites (bruit)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--compare", metavar="BASELINE_JSON",
                    help="Compare à une baseline (sortie --json) ; exit 1 si part PM > +2 pts")
    ap.add_argument("--notify-rm", type=int, metavar="RM_ID",
                    help="Avec --compare : poste le résumé en note Redmine sur ce ticket (cron)")
    args = ap.parse_args()

    root = Path(args.projects_dir)
    files = sorted(root.glob("*/*.jsonl"))
    if args.workspace:
        files = [f for f in files if any(w in f.parent.name for w in args.workspace)]

    sessions = []
    for f in files:
        s = scan_session(f)
        if not s:
            continue
        if args.since and (s["ts_last"] or "")[:10] < args.since:
            continue
        if sum(s["totals"].values()) < args.min_tokens:
            continue
        s["workspace"] = f.parent.name
        sessions.append(s)

    by_ticket = aggregate(sessions)

    if args.compare:
        with open(args.compare, encoding="utf-8") as f:
            baseline = json.load(f)
        base = global_stats(baseline.get("sessions") or [])
        cur = global_stats(sessions)
        text, drift = render_compare(base, cur, Path(args.compare).name)
        print(text)
        if args.notify_rm:
            try:
                sys.path.insert(0, str(_HERE))
                import redmine_utils as ru
                ru.add_issue_note(args.notify_rm, "**pm-bench-overhead (cron)**\n\n" + text)
                print("✓ note postée sur #%d" % args.notify_rm)
            except Exception as e:
                print("⚠ note Redmine non postée : %s" % e)
        sys.exit(1 if drift else 0)

    if args.json:
        print(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "params": vars(args),
            "global": global_stats(sessions),
            "sessions": sessions,
            "by_ticket": {k: {
                **{kk: (dict(vv) if isinstance(vv, defaultdict) else vv)
                   for kk, vv in v.items()},
                "pm_share_pct": round(pm_share(v), 1),
            } for k, v in by_ticket.items()},
        }, ensure_ascii=False, indent=1, default=str))
        return

    print(f"pm-bench-overhead — {len(sessions)} session(s), "
          f"{len([k for k in by_ticket if k != '(untracked)'])} ticket(s)")
    print()
    hdr = (f"{'ticket':<14}{'sess':>5}{'appels':>8}{'tokens':>9}{'coût $':>9}"
           f"{'out PM':>9}{'inj PM':>9}{'$ marg.PM':>11}{'part PM':>9}")
    print(hdr)
    print("-" * len(hdr))
    rows = sorted(by_ticket.items(), key=lambda kv: -kv[1]["cost_usd"])
    for key, t in rows[: args.top]:
        m = t["marginal_cost_by_cat"]
        pm_out = t["output_by_cat"]["pm-onboarding"] + t["output_by_cat"]["pm-ceremony"]
        pm_inj = t["injected_by_cat"]["pm-onboarding"] + t["injected_by_cat"]["pm-ceremony"]
        print(f"{key:<14}{t['sessions']:>5}{t['n_calls']:>8}{fmt_tk(t['tokens']):>9}"
              f"{t['cost_usd']:>9.2f}{fmt_tk(pm_out):>9}{fmt_tk(pm_inj):>9}"
              f"{m['pm-onboarding'] + m['pm-ceremony']:>11.2f}{pm_share(t):>8.1f}%")
    tot = {
        "sessions": len(sessions),
        "cost": sum(s["cost_usd"] for s in sessions),
        "out": {c: sum(s["output_by_cat"][c] for s in sessions) for c in CATEGORIES},
        "inj": {c: sum(s["injected_by_cat"][c] for s in sessions) for c in CATEGORIES},
        "marg": {c: sum(s["marginal_cost_by_cat"][c] for s in sessions) for c in CATEGORIES},
    }
    pm_marg = tot["marg"]["pm-onboarding"] + tot["marg"]["pm-ceremony"]
    all_marg = pm_marg + tot["marg"]["work"]
    print("-" * len(hdr))
    print(f"TOTAL : {tot['sessions']} sessions, {tot['cost']:.2f} $ facturés — "
          f"coût marginal attribuable : {all_marg:.2f} $ dont PM {pm_marg:.2f} $ "
          f"({100 * pm_marg / all_marg if all_marg else 0:.1f} %)")
    print(f"  output    : onboarding {fmt_tk(tot['out']['pm-onboarding'])}, "
          f"cérémonie {fmt_tk(tot['out']['pm-ceremony'])}, work {fmt_tk(tot['out']['work'])}")
    print(f"  injecté   : onboarding {fmt_tk(tot['inj']['pm-onboarding'])}, "
          f"cérémonie {fmt_tk(tot['inj']['pm-ceremony'])}, work {fmt_tk(tot['inj']['work'])}")
    if sessions:
        fc = [s["first_call"] for s in sessions]
        avg_cc = sum(u["cache_creation"] + u["input"] for u in fc) / len(fc)
        print(f"  1er appel : contexte initial moyen {fmt_tk(avg_cc)} "
              f"(system prompt + CLAUDE.md/AGENTS.md — volet A, à comparer à pm-context-budget)")


if __name__ == "__main__":
    main()
