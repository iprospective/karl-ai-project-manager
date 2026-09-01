#!/usr/bin/env python3
"""karl-move-session — déplace une session Claude Code d'un projet à un autre.

Pendant CLI de l'endpoint `POST /move-session` de karl-agent (RM2418). Corrige les
TROIS emplacements qui, ensemble, ancrent une session à un projet (leçon RM2391 :
n'en corriger qu'un ou deux ne suffit pas) :

  1. Le transcript          ~/.claude/projects/<slug>/<sid>.jsonl   -> déplacé
  2. Les `cwd` internes     dans le transcript                     -> réécrits
  3. Le store karl-agent    ~/.local/state/karl-agent/sessions/<engine>/<sid>.json
                            (champ `cwd`)                          -> réécrit  ← le CRITIQUE

Le point 3 est celui que `op_resume` lit pour relancer `claude --resume` au bon
cwd. Le point 2 pilote le regroupement d'affichage (`op_resumable`, lecture de la
queue). Le point 1 est ce que `claude --resume` cherche depuis le cwd de relance.

⚠  À lancer DANS le conteneur où tourne karl-agent (`hostname` = dev.local) :
   `~/.claude/projects` est partagé hôte↔conteneur, mais `~/.local/state` NON
   → depuis l'hôte, le point 3 viserait le mauvais store.

⚠  Session à l'ARRÊT : ne pas déplacer une session dont un `claude`/tmux est
   encore vivant (le process ré-estampille la queue et peut recréer le transcript).

Cf. knowledge/karl-agent/sessions.md.

Usage :
  karl-move-session.py --session <sid> --to /zfs/workspaces/<client>/<projet> [--dry-run]
  karl-move-session.py --session <sid> --to <path> --engine claude
"""
import argparse, json, os, re, socket, sys
from pathlib import Path

# RM2810 : la garde « session vivante » vit dans pm_proclive, partagée avec
# karl-agent. Deux copies donneraient deux verdicts sur la seule question qui
# compte avant de déplacer une session. sys.path explicite : le script est
# appelé depuis un cwd quelconque.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_proclive import live_session_pids  # noqa: E402

SID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
PROJECTS = Path.home() / ".claude" / "projects"
STATE = Path(os.environ.get("KARL_AGENT_STATE_DIR")
             or (Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local/state")) / "karl-agent"))


def slug_of(path: str) -> str:
    """Nom de dossier projet claude pour un cwd (schéma observé : '/' et '.' -> '-')."""
    return re.sub(r"[/.]", "-", path.rstrip("/") or path)


def find_transcript(sid: str) -> Path | None:
    return next((p for p in PROJECTS.glob(f"*/{sid}.jsonl")), None)


def session_is_live(sid: str, engine: str = "claude") -> list:
    """PIDs vivants portant ce sid (liste vide = déplaçable). Cf. pm_proclive."""
    return live_session_pids(sid, engine)


def main() -> int:
    ap = argparse.ArgumentParser(description="Déplace une session Claude Code vers un autre projet.")
    ap.add_argument("--session", required=True, help="session_id (UUID)")
    ap.add_argument("--to", required=True, help="cwd cible, ex. /zfs/workspaces/calicote/prestashop")
    ap.add_argument("--engine", default="claude")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="passer outre la garde 'session vivante'")
    a = ap.parse_args()

    sid = a.session.strip()
    if not SID_RE.match(sid):
        print(f"✗ session_id invalide : {sid}", file=sys.stderr); return 2

    target = Path(a.to).resolve()
    if not target.is_dir():
        print(f"✗ cwd cible inexistant : {target}", file=sys.stderr); return 2

    host = socket.gethostname()
    if host != "dev.local":
        print(f"⚠  hostname={host} (pas 'dev.local'). Le store karl (~/.local/state) est "
              f"local au conteneur — lance-moi DANS le conteneur dev, sinon le point 3 "
              f"visera le mauvais fichier.", file=sys.stderr)

    live = session_is_live(sid, a.engine)
    if live and not a.force:
        print(f"✗ {a.engine} vit encore sur ce sid (pid {', '.join(str(p) for p in live)}) — "
              f"ferme la session d'abord (ou --force).", file=sys.stderr); return 3

    jf = find_transcript(sid)
    if not jf:
        print(f"✗ transcript introuvable sous {PROJECTS}/*/{sid}.jsonl", file=sys.stderr); return 4
    old_slug = jf.parent.name
    new_slug = slug_of(str(target))
    new_dir = PROJECTS / new_slug
    new_jf = new_dir / f"{sid}.jsonl"
    store = STATE / "sessions" / a.engine / f"{sid}.json"

    # cwd d'origine : le plus fréquent dans le transcript (transcripts claude = compacts,
    # mais on tolère l'espace après ':' par prudence)
    cwds = re.findall(r'"cwd"\s*:\s*"([^"]*)"', jf.read_text(errors="replace"))
    old_cwd = max(set(cwds), key=cwds.count) if cwds else None

    print(f"session   : {sid}")
    print(f"transcript: {jf}")
    print(f"  slug     {old_slug}  ->  {new_slug}")
    print(f"cwd interne: {old_cwd}  ->  {target}")
    print(f"store karl : {store}  (existe={store.exists()})")
    if a.dry_run:
        print("\n(dry-run — rien écrit)"); return 0

    # 1+2. déplacer le transcript et réécrire ses cwd
    new_dir.mkdir(parents=True, exist_ok=True)
    text = jf.read_text(errors="replace")
    if old_cwd:
        text = re.sub(r'("cwd"\s*:\s*")' + re.escape(old_cwd) + r'(")',
                      lambda m: m.group(1) + str(target) + m.group(2), text)
    new_jf.write_text(text)
    if jf != new_jf:
        jf.unlink()
    # nettoyer d'éventuels doublons du sid dans d'autres dossiers projet
    for dup in PROJECTS.glob(f"*/{sid}.jsonl"):
        if dup != new_jf:
            dup.unlink()
    print(f"✓ transcript -> {new_jf} (cwd réécrits)")

    # 3. store karl-agent
    meta = {}
    if store.exists():
        try: meta = json.loads(store.read_text())
        except ValueError: meta = {}
    meta.update({"engine": a.engine, "session_id": sid, "cwd": str(target)})
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(meta, indent=1))
    print(f"✓ store karl cwd -> {target}")

    print(f"\n✅ Session déplacée vers {new_slug}. Reprends-la depuis le cockpit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
