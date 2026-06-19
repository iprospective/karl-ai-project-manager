#!/usr/bin/env python3
"""pm-task-tick — Incrémente tokens/coût/temps sur le frontmatter d'une tâche PM.

Deux modes :

1. **Mode hook Claude Code** (par défaut quand un JSON est lu sur stdin) :
   - Lit l'event Stop sur stdin (session_id, transcript_path, cwd, …)
   - Identifie le RM-id courant (cascade d'heuristiques)
   - Extrait les tokens du dernier message assistant du transcript
   - Calcule le coût USD via pm.pricing.yml
   - Update le frontmatter MD du ticket (atomique, optimistic locking)
   - Append au .log.md si tokens > seuil (1000 par défaut)

2. **Mode CLI** (pour agents non-Claude-Code ou ajout manuel) :
   pm-task-tick.py --rm-id 1717 [--tokens-input N] [--tokens-output N]
                   [--cache-read N] [--cache-creation N] [--model M]
                   [--human-minutes M] [--ai-minutes M]

Si aucun ticket n'est identifié en mode hook, log dans
~/.claude/logs/pm-task-tick-untracked.jsonl et exit propre (jamais d'erreur
côté hook pour ne pas bloquer Claude Code).
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")


FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)
LOG_THRESHOLD_TOKENS = 1000  # n'append au .log.md que si > seuil

UNTRACKED_LOG = Path.home() / ".claude" / "logs" / "pm-task-tick-untracked.jsonl"
TURN_START_DIR = Path.home() / ".claude" / "logs"
# Garde-fou : un tour wall-clock > ce seuil est ignoré (ex: prompt soumis puis
# attente d'une validation de permission pendant des heures). Évite de polluer
# ai_time avec des durées absurdes.
AI_MINUTES_CAP = 240.0
# Note : pas de sentinel global ~/.claude/current_task — il pose un problème
# de collision multi-sessions (plusieurs sessions Claude Code en parallèle
# partagent le même fichier). On utilise uniquement des sentinels par-projet
# (.mmi-pm/CURRENT_TASK) qui sont isolés par cwd. Cf. discussion RM1717.


def load_pricing():
    """Lit pm.pricing.yml. Retourne dict models + human_hourly_rate_eur."""
    cfg_path = Path(__file__).resolve().parent.parent / "pm.pricing.yml"
    if not cfg_path.is_file():
        return {"models": {}, "human_hourly_rate_eur": 80}
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {"models": {}, "human_hourly_rate_eur": 80}
    return {
        "models": cfg.get("models") or {},
        "human_hourly_rate_eur": cfg.get("human_hourly_rate_eur", 80),
    }


def compute_cost_usd(model, input_tk, output_tk, cache_read_tk, cache_creation_tk, pricing):
    """USD à partir des 4 compteurs et du modèle. 0 si modèle inconnu."""
    m = (pricing.get("models") or {}).get(model)
    if not m:
        return 0.0
    return (
        input_tk          * m.get("input_per_mtok_usd", 0)          / 1_000_000
      + output_tk         * m.get("output_per_mtok_usd", 0)         / 1_000_000
      + cache_read_tk     * m.get("cache_read_per_mtok_usd", 0)     / 1_000_000
      + cache_creation_tk * m.get("cache_creation_per_mtok_usd", 0) / 1_000_000
    )


# ── Identification du RM-id courant ─────────────────────────────────────────
#
# Principe (RM1823) : on ne DEVINE PAS le ticket depuis l'état du projet.
# Plusieurs tâches `en_cours` dans un projet est le cas NORMAL ; plusieurs
# sessions en parallèle, voire plusieurs tickets dans une même session, aussi.
# On attribue donc chaque tour au ticket que LE TOUR A RÉELLEMENT TOUCHÉ, lu
# dans le transcript que le hook Stop reçoit déjà (transcript_path). Fallback :
# sentinel projet, sinon untracked. L'ancienne heuristique « seule tâche
# en_cours » est abandonnée (trompeuse).

# Force du signal : 3 = mutation PM explicite (script/skill agissant sur un
# ticket), 2 = édition d'un fichier de ticket, 1 = simple mention textuelle.
_PM_SCRIPT_RE  = re.compile(r"(?:pm-task-[a-z-]+|pm-project-[a-z-]+|redmine-[a-z-]+)\.py\b")
_RMID_FLAG_RE  = re.compile(r"--rm-id[=\s]+(\d{2,6})")
_RMID_POS_RE   = re.compile(r"\.py\s+(\d{2,6})\b")        # id positionnel juste après le script
_RMID_TAG_RE   = re.compile(r"\bRM[-\s]?(\d{2,6})\b")
_RMID_FILE_RE  = re.compile(r"\bRM(\d{2,6})_")
_LEADING_ID_RE = re.compile(r"^\s*(?:RM[-\s]?)?(\d{2,6})\b")


def _ids_in_pm_command(cmd):
    """RM-ids cités dans une commande invoquant un script PM (signal fort)."""
    ids = []
    for rx in (_RMID_FLAG_RE, _RMID_POS_RE, _RMID_TAG_RE, _RMID_FILE_RE):
        ids += [int(m.group(1)) for m in rx.finditer(cmd)]
    return ids


def _blocks(evt):
    """(role, [content blocks]) d'un event de transcript, normalisé."""
    msg = evt.get("message") if isinstance(evt, dict) else None
    if not isinstance(msg, dict):
        return None, []
    content = msg.get("content")
    if isinstance(content, str):
        return msg.get("role"), [{"type": "text", "text": content}]
    if isinstance(content, list):
        return msg.get("role"), content
    return msg.get("role"), []


def _is_human_prompt(evt):
    """True si l'event est un vrai prompt humain (≠ message porteur de tool_result)."""
    role, blocks = _blocks(evt)
    if role != "user":
        return False
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "tool_result":
            return False
    return True


def _evidence_from_event(evt):
    """Liste de (rm_id, strength) trouvés dans un event."""
    _role, blocks = _blocks(evt)
    out = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "tool_use":
            name = b.get("name") or ""
            inp = b.get("input") if isinstance(b.get("input"), dict) else {}
            if name == "Bash":
                cmd = str(inp.get("command", ""))
                if _PM_SCRIPT_RE.search(cmd):
                    out += [(rid, 3) for rid in _ids_in_pm_command(cmd)]
                out += [(int(m.group(1)), 2) for m in _RMID_FILE_RE.finditer(cmd)]
                out += [(int(m.group(1)), 1) for m in _RMID_TAG_RE.finditer(cmd)]
            elif name in ("Edit", "Write", "NotebookEdit", "Read"):
                m = _RMID_FILE_RE.search(str(inp.get("file_path", "")))
                if m:
                    strong = name in ("Edit", "Write", "NotebookEdit")
                    out.append((int(m.group(1)), 2 if strong else 1))
            elif name == "Skill":
                if str(inp.get("skill", "")).startswith("mmi-pm-"):
                    m = _LEADING_ID_RE.match(str(inp.get("args", "")))
                    if m:
                        out.append((int(m.group(1)), 3))
        elif t == "text":
            txt = str(b.get("text", ""))
            out += [(int(m.group(1)), 1) for m in _RMID_TAG_RE.finditer(txt)]
            out += [(int(m.group(1)), 1) for m in _RMID_FILE_RE.finditer(txt)]
    return out


_CLOSED_CACHE = {}


def _is_closed(rm_id):
    """True si RM<id> est au statut terminal `ferme`. Fail-safe : ticket introuvable
    ou statut illisible → False (on préfère ticker que perdre la conso). Caché par
    exécution. (`ferme`/18 seul statut terminal ; `a_mep`/3 reste tickable.) RM2053."""
    if rm_id in _CLOSED_CACHE:
        return _CLOSED_CACHE[rm_id]
    closed = False
    try:
        md = PMConfig.load().find_task(rm_id)
        if md:
            m = FM_RE.match(md.read_text(encoding="utf-8"))
            if m:
                closed = ((yaml.safe_load(m.group(2)) or {}).get("status") == "ferme")
    except Exception:
        closed = False
    _CLOSED_CACHE[rm_id] = closed
    return closed


def _pick_from_events(events):
    """(rm_id, strength) du signal le plus fort puis le plus récent **parmi les tickets
    OUVERTS**, ou None si aucun candidat ouvert. On n'attribue JAMAIS une tick à un
    ticket fermé (RM2053) : un tour touchant un ticket ouvert + un fermé ticke l'ouvert ;
    un tour ne touchant que du fermé ne ticke rien."""
    cands = []
    for pos, evt in enumerate(events):
        for rid, strength in _evidence_from_event(evt):
            cands.append((strength, pos, rid))
    if not cands:
        return None
    cands.sort(key=lambda c: (c[0], c[1]))   # faible→fort, ancien→récent
    for strength, _pos, rid in reversed(cands):   # du plus fort/récent au plus faible
        if not _is_closed(rid):
            return rid, strength
    return None   # tous les candidats touchés sont fermés


def _load_transcript(transcript_path):
    p = Path(transcript_path)
    if not p.is_file():
        return None
    events = []
    try:
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return None
    return events


def _resolve_from_transcript(transcript_path):
    events = _load_transcript(transcript_path)
    if not events:
        return None, "transcript absent/vide"
    # Tour courant = events depuis le dernier prompt humain (inclus, pour
    # capter une mention RM explicite dans la demande de l'utilisateur).
    last_human = max((i for i, e in enumerate(events) if _is_human_prompt(e)), default=-1)
    turn = events[last_human:] if last_human >= 0 else events
    pick = _pick_from_events(turn)
    if pick is not None:
        return pick[0], f"transcript:tour (signal={pick[1]})"
    # Le tour n'a touché aucun ticket → continuation : dernier ticket de la session.
    pick = _pick_from_events(events)
    if pick is not None:
        return pick[0], f"transcript:continuation (signal={pick[1]})"
    return None, "transcript sans référence ticket"


def _resolve_from_sentinel(cwd):
    cwd = Path(cwd).resolve() if cwd else Path.cwd()
    for d in [cwd] + list(cwd.parents):
        link = d / ".mmi-pm"
        sentinel = link / "CURRENT_TASK"
        if sentinel.is_file():
            try:
                v = sentinel.read_text(encoding="utf-8").strip()
                if v.isdigit():
                    rid = int(v)
                    if _is_closed(rid):   # sentinel périmé sur un ticket clos → ignoré (RM2053)
                        return None, f"sentinel {sentinel} pointe un ticket fermé (ignoré)"
                    return rid, f"sentinel {sentinel}"
            except OSError:
                pass
        if link.exists():
            break  # workspace PM trouvé, inutile de remonter
    return None, "pas de sentinel"


def resolve_current_rm_id(cwd, transcript_path=None):
    """Retourne (rm_id, source_reason) ou (None, reason_skip).

    Priorité :
      1. ce que le TOUR a réellement touché, lu dans le transcript
         (mutation PM > édition de fichier ticket > mention textuelle) ;
      2. fallback : sentinel projet `<workspace>/.mmi-pm/CURRENT_TASK`.
    """
    last_reason = "pas de transcript"
    if transcript_path:
        rid, last_reason = _resolve_from_transcript(transcript_path)
        if rid is not None:
            return rid, last_reason
    rid, sreason = _resolve_from_sentinel(cwd)
    if rid is not None:
        return rid, sreason
    return None, f"{last_reason}; {sreason}"


# ── Update du frontmatter ───────────────────────────────────────────────────

def update_task_fm(rm_id, deltas, model_used, log_entry=None):
    """Update atomique : lit + modifie + écrit le MD d'un ticket.

    `deltas` : dict avec clés possibles input, output, cache_read,
    cache_creation, cost_usd, ai_minutes, human_minutes.
    """
    cfg = PMConfig.load()
    md_path = cfg.find_task(rm_id)
    if not md_path:
        return False, f"RM{rm_id} introuvable"

    content = md_path.read_text(encoding="utf-8")
    m = FM_RE.match(content)
    if not m:
        return False, f"pas de frontmatter dans {md_path}"

    fm = yaml.safe_load(m.group(2)) or {}

    # Incrémenter
    br = fm.get("tokens_breakdown") or {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    for k in ("input", "output", "cache_read", "cache_creation"):
        br[k] = (br.get(k) or 0) + int(deltas.get(k, 0) or 0)
    fm["tokens_breakdown"] = br
    fm["tokens_total"] = sum(br.values())
    fm["cost_total_usd"] = round((fm.get("cost_total_usd") or 0) + float(deltas.get("cost_usd", 0) or 0), 6)
    fm["ai_time_total_minutes"] = (fm.get("ai_time_total_minutes") or 0) + float(deltas.get("ai_minutes", 0) or 0)
    fm["human_time_total_minutes"] = (fm.get("human_time_total_minutes") or 0) + float(deltas.get("human_minutes", 0) or 0)
    fm["time_total_minutes"] = fm["ai_time_total_minutes"] + fm["human_time_total_minutes"]
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")

    new_fm_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    new_content = f"{m.group(1)}{new_fm_yaml.rstrip()}{m.group(3)}{m.group(4)}"
    md_path.write_text(new_content, encoding="utf-8")

    # Log si seuil dépassé
    total_new = sum(int(deltas.get(k, 0) or 0) for k in ("input", "output", "cache_read", "cache_creation"))
    if log_entry and total_new >= LOG_THRESHOLD_TOKENS:
        log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(log_entry)

    return True, str(md_path.name)


# ── Mode hook ───────────────────────────────────────────────────────────────

def extract_last_response_usage(transcript_path):
    """Lit le transcript JSONL et somme l'usage du dernier message assistant.

    Retourne dict {input, output, cache_read, cache_creation, model} ou None.
    """
    p = Path(transcript_path)
    if not p.is_file():
        return None
    last = None
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Format Claude Code : message avec role=assistant
                msg = evt.get("message") if isinstance(evt, dict) else None
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    usage = msg.get("usage")
                    model = msg.get("model")
                    if usage:
                        last = (usage, model)
    except OSError:
        return None
    if last is None:
        return None
    usage, model = last
    return {
        "input": usage.get("input_tokens", 0) or 0,
        "output": usage.get("output_tokens", 0) or 0,
        "cache_read": usage.get("cache_read_input_tokens", 0) or 0,
        "cache_creation": usage.get("cache_creation_input_tokens", 0) or 0,
        "model": model or "unknown",
    }


def consume_turn_minutes(session_id):
    """Lit + efface le fichier de départ du tour (posé par pm-turn-start).

    Retourne le temps IA wall-clock du tour en minutes (0.0 si absent/invalide).
    Toujours appelé, même si le tour n'est pas attribuable à un ticket, pour ne
    pas laisser traîner le fichier de départ.
    """
    if not session_id:
        return 0.0
    sid = re.sub(r"[^A-Za-z0-9_-]", "_", str(session_id))[:80]
    p = TURN_START_DIR / f"turn-start-{sid}.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        p.unlink()
    except (OSError, json.JSONDecodeError, ValueError):
        return 0.0
    start = data.get("start_epoch")
    if not start:
        return 0.0
    now = time.time()
    # Attente HUMAINE à exclure (délibération sur AskUserQuestion/ExitPlanMode,
    # encadrée par pm-turn-wait via PreToolUse/PostToolUse).
    human_wait = float(data.get("human_wait_seconds", 0) or 0)
    ws = data.get("wait_start")  # attente encore ouverte au Stop (PostToolUse non vu) → la compter
    if ws:
        human_wait += now - float(ws)
    mins = (now - float(start)) / 60.0 - human_wait / 60.0
    if mins < 0 or mins > 2 * AI_MINUTES_CAP:
        return 0.0                                  # aberrant (fichier obsolète) → jeté
    return round(min(mins, AI_MINUTES_CAP), 2)      # plafonne un tour légitimement long


def run_hook_mode():
    """Lit l'event JSON sur stdin et update le ticket courant."""
    try:
        evt = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return  # pas de JSON valide → exit silencieux

    cwd = evt.get("cwd") or os.getcwd()
    transcript_path = evt.get("transcript_path")
    # Toujours consommer le départ de tour (nettoie le fichier même si non-tracké)
    ai_minutes = consume_turn_minutes(evt.get("session_id"))

    rm_id, reason = resolve_current_rm_id(cwd, transcript_path)
    usage = extract_last_response_usage(transcript_path) if transcript_path else None

    # Log silencieusement les cas non-trackés (pour analyse a posteriori)
    if rm_id is None:
        try:
            UNTRACKED_LOG.parent.mkdir(parents=True, exist_ok=True)
            with UNTRACKED_LOG.open("a", encoding="utf-8") as f:
                json.dump({
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "reason": reason,
                    "cwd": str(cwd),
                    "session_id": evt.get("session_id"),
                    "usage": usage,
                    "ai_minutes": ai_minutes,
                }, f)
                f.write("\n")
        except OSError:
            pass
        return

    if usage is None:
        return  # rien à compter

    pricing = load_pricing()
    cost = compute_cost_usd(
        usage["model"], usage["input"], usage["output"],
        usage["cache_read"], usage["cache_creation"], pricing,
    )

    # Entrée log concise (uniquement si seuil dépassé)
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    total = usage["input"] + usage["output"] + usage["cache_read"] + usage["cache_creation"]
    log_entry = (
        f"\n## {ts} — Tick IA ({usage['model']})\n"
        f"Tokens : {total} | Coût : ${cost:.4f} | IA : {ai_minutes} min\n\n"
        f"Détail : input={usage['input']}, output={usage['output']}, "
        f"cache_read={usage['cache_read']}, cache_creation={usage['cache_creation']}\n"
        f"Source : hook Stop ({reason})\n"
    )

    ok, msg = update_task_fm(rm_id, {
        "input": usage["input"], "output": usage["output"],
        "cache_read": usage["cache_read"], "cache_creation": usage["cache_creation"],
        "cost_usd": cost, "ai_minutes": ai_minutes,
    }, usage["model"], log_entry=log_entry)
    # Hook : pas de stdout (silencieux). Erreurs → stderr (Claude les ignore).
    if not ok:
        print(f"pm-task-tick: {msg}", file=sys.stderr)


# ── Mode CLI ────────────────────────────────────────────────────────────────

def run_cli_mode(args):
    pricing = load_pricing()
    cost = compute_cost_usd(
        args.model or "unknown",
        args.tokens_input, args.tokens_output,
        args.cache_read, args.cache_creation, pricing,
    )
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    total = args.tokens_input + args.tokens_output + args.cache_read + args.cache_creation
    log_entry = (
        f"\n## {ts} — Tick manuel\n"
        f"Tokens : {total} | Coût : ${cost:.4f} | Humain : {args.human_minutes}min | IA : {args.ai_minutes}min\n\n"
        f"Source : pm-task-tick CLI (model={args.model})\n"
    ) if (total > 0 or args.human_minutes or args.ai_minutes) else None

    ok, msg = update_task_fm(args.rm_id, {
        "input": args.tokens_input, "output": args.tokens_output,
        "cache_read": args.cache_read, "cache_creation": args.cache_creation,
        "cost_usd": cost,
        "human_minutes": args.human_minutes, "ai_minutes": args.ai_minutes,
    }, args.model, log_entry=log_entry)
    if ok:
        print(f"✓ RM{args.rm_id} : +{total} tokens, +${cost:.4f}, +{args.human_minutes}min humain, +{args.ai_minutes}min IA")
    else:
        sys.exit(f"ERREUR : {msg}")


def main():
    # Mode hook : si stdin est un pipe et qu'on n'a pas d'args CLI
    if not sys.stdin.isatty() and len(sys.argv) == 1:
        run_hook_mode()
        return

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rm-id", type=int, required=True, help="RM-id du ticket à ticker")
    ap.add_argument("--tokens-input", type=int, default=0)
    ap.add_argument("--tokens-output", type=int, default=0)
    ap.add_argument("--cache-read", type=int, default=0)
    ap.add_argument("--cache-creation", type=int, default=0)
    ap.add_argument("--model", help="ex: claude-opus-4-7 (sinon coût=0)")
    ap.add_argument("--human-minutes", type=float, default=0)
    ap.add_argument("--ai-minutes", type=float, default=0)
    args = ap.parse_args()
    run_cli_mode(args)


if __name__ == "__main__":
    main()
