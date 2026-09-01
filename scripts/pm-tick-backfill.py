#!/usr/bin/env python3
"""pm-tick-backfill — reconstitue les ticks de conso manqués depuis les transcripts (RM2311).

Quand le hook Stop `pm-task-tick.py` n'a pas tourné (profil Claude Code sans
hooks — cf. RM2306 et `pm-claude-hooks-sync.py`), la conso des sessions reste
invisible : `tokens_total` = 0 sur les tickets travaillés. Ce script rejoue les
transcripts JSONL (`~/.claude/projects/*/*.jsonl`) avec la MÊME logique
d'attribution que le tick (résolution par tour, forces de signal, retries
dédupliqués par message.id) et ré-agrège la conso par ticket.

Garde-fou anti double-comptage : n'APPLIQUE que sur les tickets **jamais tickés**
(`tokens_total == 0`). Un ticket partiellement tické (p. ex. sessions karl-agent
OK + sessions interactives muettes) est seulement RAPPORTÉ avec le delta
reconstitué : à arbitrer à la main (`pm-task-tick.py --rm-id … --tokens-…`).

Usage :
  pm-tick-backfill.py                     # rapport seul (rien n'est écrit)
  pm-tick-backfill.py --apply             # applique aux tickets à tokens_total=0
  pm-tick-backfill.py --apply --include-closed   # y compris tickets fermés
  pm-tick-backfill.py --projects-dir DIR  # défaut: ~/.claude/projects
  pm-tick-backfill.py --since 2026-07-06  # ignore les transcripts plus vieux (mtime)

Après un --apply : le push Redmine (time entries + CF) se fait par le canal
habituel `pm-task-report.py --all --apply`.

Limites assumées : ai_time reconstitué depuis les timestamps du transcript
(durée du tour, plafonnée à AI_MINUTES_CAP) — les pauses AskUserQuestion ne
sont pas déductibles a posteriori ; les tours sans référence ticket restent
non attribués (comptés dans le rapport).
"""
import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def _load_module(alias, filename):
    spec = importlib.util.spec_from_file_location(alias, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tick = _load_module("pm_task_tick", "pm-task-tick.py")  # logique d'attribution canonique


def _pick_any(events):
    """Comme tick._pick_from_events mais SANS filtre ticket-fermé : au backfill,
    le ticket était ouvert au moment de la conso — on attribue, et le statut
    actuel est arbitré au moment de l'apply (--include-closed)."""
    cands = []
    for pos, evt in enumerate(events):
        for rid, strength in tick._evidence_from_event(evt):
            cands.append((strength, pos, rid))
    if not cands:
        return None
    cands.sort(key=lambda c: (c[0], c[1]))
    return cands[-1][2]


def _ts(evt):
    v = evt.get("timestamp") if isinstance(evt, dict) else None
    if not isinstance(v, str):
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def _turn_minutes(turn):
    stamps = [t for t in (_ts(e) for e in turn) if t is not None]
    if len(stamps) < 2:
        return 0.0
    mins = (max(stamps) - min(stamps)).total_seconds() / 60.0
    if mins < 0:
        return 0.0
    return round(min(mins, tick.AI_MINUTES_CAP), 2)


def replay_transcript(path, pricing, agg, untracked):
    """Rejoue un transcript : découpe en tours, attribue, agrège dans `agg`."""
    events = tick._load_transcript(path)
    if not events:
        return
    humans = [i for i, e in enumerate(events) if tick._is_human_prompt(e)]
    if not humans:
        return
    bounds = list(zip(humans, humans[1:] + [len(events)]))
    seen_msg_ids = set()   # dédup retries + resume à l'échelle de la session
    last_rid = None
    for start, end in bounds:
        turn = events[start:end]
        rid = _pick_any(turn)
        if rid is None:
            rid = last_rid            # continuation, comme le tick
        else:
            last_rid = rid
        per_msg = {}
        for evt in turn:
            msg = evt.get("message") if isinstance(evt, dict) else None
            if isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("usage"):
                mid = msg.get("id")
                if mid and mid in seen_msg_ids:
                    continue
                per_msg[mid or object()] = (msg["usage"], msg.get("model"))
        seen_msg_ids.update(k for k in per_msg if isinstance(k, str))
        if not per_msg:
            continue
        usage = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "cost_usd": 0.0}
        for u, model in per_msg.values():
            i = u.get("input_tokens", 0) or 0
            o = u.get("output_tokens", 0) or 0
            cr = u.get("cache_read_input_tokens", 0) or 0
            cc = u.get("cache_creation_input_tokens", 0) or 0
            usage["input"] += i
            usage["output"] += o
            usage["cache_read"] += cr
            usage["cache_creation"] += cc
            usage["cost_usd"] += tick.compute_cost_usd(model or "unknown", i, o, cr, cc, pricing)
        if rid is None:
            bucket = untracked
        else:
            bucket = agg.setdefault(rid, {"input": 0, "output": 0, "cache_read": 0,
                                          "cache_creation": 0, "cost_usd": 0.0,
                                          "ai_minutes": 0.0, "turns": 0, "sessions": set()})
        for k in ("input", "output", "cache_read", "cache_creation", "cost_usd"):
            bucket[k] += usage[k]
        bucket["ai_minutes"] = round(bucket.get("ai_minutes", 0.0) + _turn_minutes(turn), 2)
        bucket["turns"] = bucket.get("turns", 0) + 1
        bucket.setdefault("sessions", set()).add(path.stem)


def _last_activity(path, cutoff):
    """Vrai si le dernier event horodaté du transcript est ≥ cutoff. Lu depuis la
    fin du fichier (les mtimes du repo git projects sont trompeurs)."""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 65536))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return False
    for line in reversed(tail.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            t = _ts(json.loads(line))
        except json.JSONDecodeError:
            continue
        if t is not None:
            return t.astimezone() >= cutoff
    return False


def task_state(rm_id):
    """(tokens_total, status, trouvé) du ticket."""
    md = tick.PMConfig.load().find_task(rm_id)
    if not md:
        return None, None, False
    m = tick.FM_RE.match(md.read_text(encoding="utf-8"))
    fm = (tick.yaml.safe_load(m.group(2)) or {}) if m else {}
    return int(fm.get("tokens_total") or 0), fm.get("status"), True


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill des ticks manqués depuis les transcripts.")
    ap.add_argument("--projects-dir", type=Path, default=Path.home() / ".claude" / "projects")
    ap.add_argument("--since", type=str, default=None,
                    help="Ignore les sessions dont la DERNIÈRE activité (timestamp du transcript, "
                         "pas le mtime — ~/.claude/projects est un repo git synchronisé, les mtimes "
                         "sont réécrits par les pull) est avant cette date (YYYY-MM-DD)")
    ap.add_argument("--apply", action="store_true",
                    help="Applique aux tickets jamais tickés (tokens_total=0). Sinon : rapport seul.")
    ap.add_argument("--include-closed", action="store_true",
                    help="Avec --apply : applique aussi aux tickets au statut ferme.")
    ap.add_argument("--only", type=str, default=None,
                    help="CSV de RM-ids : restreint l'apply (et le rapport) à ces tickets — "
                         "l'agrégation rejoue quand même tout (continuité des tours).")
    args = ap.parse_args()

    root = args.projects_dir.expanduser()
    cutoff = datetime.strptime(args.since, "%Y-%m-%d").astimezone() if args.since else None
    only = {int(x) for x in args.only.split(",")} if args.only else None
    transcripts = sorted(p for p in root.glob("*/*.jsonl")
                         if cutoff is None or _last_activity(p, cutoff))
    if not transcripts:
        print(f"Aucun transcript dans {root}" + (f" (since {args.since})" if args.since else ""))
        return 0

    pricing = tick.load_pricing()
    agg, untracked = {}, {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0,
                          "cost_usd": 0.0, "ai_minutes": 0.0, "turns": 0, "sessions": set()}
    for p in transcripts:
        replay_transcript(p, pricing, agg, untracked)

    print(f"== pm-tick-backfill — {len(transcripts)} transcript(s), "
          f"{len(agg)} ticket(s) référencé(s) ==")
    applied = 0
    for rid in sorted(agg):
        if only is not None and rid not in only:
            continue
        b = agg[rid]
        total = b["input"] + b["output"] + b["cache_read"] + b["cache_creation"]
        tokens_total, status, found = task_state(rid)
        line = (f"RM{rid} [{status or '?'}] : {total} tk reconstitués "
                f"(out={b['output']}, {b['turns']} tour(s), {len(b['sessions'])} session(s), "
                f"${b['cost_usd']:.2f}, IA {b['ai_minutes']} min)")
        if not found:
            print(f"  ? {line} — ticket introuvable, ignoré")
            continue
        if tokens_total > 0:
            print(f"  = {line} — déjà tické ({tokens_total} tk au compteur), NON appliqué "
                  f"(arbitrage manuel : pm-task-tick.py --rm-id {rid} …)")
            continue
        if status == "ferme" and not args.include_closed:
            print(f"  ✗ {line} — jamais tické mais FERMÉ : utiliser --include-closed")
            continue
        if not args.apply:
            print(f"  → {line} — appliquable (tokens_total=0)")
            continue
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
        log_entry = (
            f"\n## {ts} — Backfill ticks (RM2311)\n"
            f"Tokens : {total} | Coût : ${b['cost_usd']:.4f} | IA : {b['ai_minutes']} min\n\n"
            f"Détail : input={b['input']}, output={b['output']}, "
            f"cache_read={b['cache_read']}, cache_creation={b['cache_creation']}\n"
            f"Source : pm-tick-backfill ({b['turns']} tour(s) rejoué(s) depuis "
            f"{len(b['sessions'])} session(s) — hooks absents, cf. RM2306)\n"
        )
        ok, msg = tick.update_task_fm(rid, {
            "input": b["input"], "output": b["output"],
            "cache_read": b["cache_read"], "cache_creation": b["cache_creation"],
            "cost_usd": b["cost_usd"], "ai_minutes": b["ai_minutes"],
        }, None, log_entry=log_entry)
        print(f"  ✓ {line} — appliqué ({msg})" if ok else f"  ✗ {line} — échec : {msg}")
        applied += ok
    if untracked["turns"]:
        u_total = sum(untracked[k] for k in ("input", "output", "cache_read", "cache_creation"))
        print(f"  · non attribuable : {u_total} tk sur {untracked['turns']} tour(s) "
              f"({len(untracked['sessions'])} session(s) sans référence ticket)")
    if args.apply:
        print(f"\n✓ {applied} ticket(s) backfillé(s). Push Redmine : pm-task-report.py --all --apply")
    else:
        print("\n[rapport seul — rien n'a été écrit ; utiliser --apply]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
