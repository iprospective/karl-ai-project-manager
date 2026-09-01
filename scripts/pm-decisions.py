#!/usr/bin/env python3
"""pm-decisions — extrait les questions/réponses d'une session et les consigne
au niveau TICKET, où elles survivent à la session. RM2305.

Le transcript claude (`~/.claude/projects/*/<session-id>.jsonl`) porte déjà les
questions posées et les réponses retenues, typées par RM2549. Mais il est
local à une machine, hors du repo PM, et rattaché à une session — pas à un
ticket. Quand la session est finie, plus personne ne sait pourquoi on a tranché
comme ça.

Ce script fait le pont : il lit le transcript, ne garde que ce qui a été
DÉCIDÉ (question posée + réponse retenue) ou LAISSÉ EN PLAN (question sans
réponse), et l'append au `.log.md` du ticket — versionné, partagé, à côté du
reste de l'histoire de la tâche.

Ce qu'il ne fait PAS : rejouer le direct (RM2466 volet 2 s'en charge), ni
deviner une décision dans de la prose (RM2549 : une question est un fait
déclaré par l'agent, jamais une devinette).

Usage :
  pm-decisions.py list [--session <id>]              # ce que porte la session
  pm-decisions.py persist <rm_id> [--session <id>]   # → .log.md du ticket
  pm-decisions.py persist <rm_id> --dry-run          # sans écrire
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_output import out as pmout          # noqa: E402
from pm_paths import PMConfig               # noqa: E402
from pm_transcript import transcript_outline  # noqa: E402

CLAUDE_STORES = [
    Path(p).expanduser()
    for p in os.environ.get(
        "PM_CLAUDE_STORES", str(Path.home() / ".claude" / "projects")).split(":")
    if p.strip()
]


def transcript_path(session_id):
    """Fichier JSONL d'une session claude — même résolution que le cockpit."""
    if not session_id:
        return None
    return next((p for root in CLAUDE_STORES
                 for p in root.glob(f"*/{session_id}.jsonl")), None)


def _questions_only(full, fallback):
    """La ou les questions, sans les options proposées. `question_parts` rend un
    détail « question / puis ses options indentées » : pour un journal on garde
    ce qui a été DEMANDÉ, pas le menu — les options sont du bruit six mois après."""
    lignes = [l.strip() for l in str(full or "").splitlines()
              if l.strip() and not l.startswith("  - ")]
    return " / ".join(lignes) or fallback


def session_decisions(lines):
    """[(question, réponse|None)] dans l'ordre du fil. `None` = restée sans
    réponse. Pure — c'est elle qui est testée, pas la lecture de fichier."""
    items = transcript_outline(lines, max_items=1000000)
    return [(_questions_only(it.get("full"), it["text"]), it.get("answer"))
            for it in items if it.get("kind") == "question"]


def render_entry(decisions, session_id, when):
    """Bloc markdown append au `.log.md`. Pure.

    Les questions sans réponse sont marquées comme telles plutôt qu'omises :
    « on n'a jamais tranché » est une information, souvent plus utile que la
    décision elle-même quand on relit six mois plus tard."""
    tranchees = [(q, a) for q, a in decisions if a]
    ouvertes = [q for q, a in decisions if not a]
    out = [f"\n\n## {when} — Décisions de session (pm-decisions)",
           f"\nSession `{session_id}` — {len(tranchees)} tranchée(s), "
           f"{len(ouvertes)} restée(s) sans réponse.\n"]
    for q, a in tranchees:
        out.append(f"- **{_one_line(q)}**\n  → {_one_line(a)}")
    for q in ouvertes:
        out.append(f"- ⚠ **{_one_line(q)}**\n  → _restée sans réponse_")
    return "\n".join(out) + "\n"


def _one_line(text, limit=300):
    s = " ".join(str(text or "").split())
    return s[:limit] + ("…" if len(s) > limit else "")


def resolve_session(explicit):
    sid = explicit or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        sys.exit("ERREUR : aucune session (ni --session ni $CLAUDE_CODE_SESSION_ID).")
    return sid


def read_decisions(session_id):
    path = transcript_path(session_id)
    if not path:
        sys.exit(f"ERREUR : transcript introuvable pour la session {session_id}.")
    with path.open(encoding="utf-8", errors="replace") as fh:
        return session_decisions(fh)


def cmd_list(args):
    decisions = read_decisions(resolve_session(args.session))
    if not decisions:
        pmout.info("aucune question posée dans cette session")
        return
    for q, a in decisions:
        marque = "✓" if a else "⚠"
        sys.stdout.write(f"{marque} {_one_line(q, 120)}\n"
                         f"   → {_one_line(a, 120) if a else '(sans réponse)'}\n")


def cmd_persist(args):
    from datetime import datetime
    session_id = resolve_session(args.session)
    decisions = read_decisions(session_id)
    if not decisions:
        pmout.info("aucune question posée dans cette session — rien à consigner")
        return
    cfg = PMConfig.load()
    task = cfg.find_task(int(args.rm_id))
    if not task:
        sys.exit(f"ERREUR : ticket RM{args.rm_id} introuvable dans l'arbo PM.")
    log = task.with_name(task.name[:-3] + ".log.md")
    if not log.exists():
        sys.exit(f"ERREUR : journal absent pour RM{args.rm_id} ({log.name}).")
    entry = render_entry(decisions, session_id,
                         datetime.now().strftime("%Y-%m-%dT%H:%M"))
    if args.dry_run:
        sys.stdout.write(entry)
        return
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(entry)
    pmout.op("decisions", extra=f"RM{args.rm_id} ← {len(decisions)} question(s) "
                                f"({sum(1 for _, a in decisions if a)} tranchée(s))")
    pmout.info(f"  · {log}")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    pmout.add_args(p)
    sub = p.add_subparsers(dest="cmd")

    ls = sub.add_parser("list", help="lister les questions/réponses de la session")
    ls.add_argument("--session", help="id de session (défaut : $CLAUDE_CODE_SESSION_ID)")

    ps = sub.add_parser("persist", help="consigner dans le .log.md d'un ticket")
    ps.add_argument("rm_id")
    ps.add_argument("--session")
    ps.add_argument("--dry-run", action="store_true", help="afficher sans écrire")

    args = p.parse_args()
    pmout.configure(args)
    if not args.cmd:
        p.print_help()
        sys.exit(2)
    {"list": cmd_list, "persist": cmd_persist}[args.cmd](args)


if __name__ == "__main__":
    main()
