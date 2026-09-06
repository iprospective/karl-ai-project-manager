#!/usr/bin/env python3
"""pm_log — journal structuré du système PM et de karl-agent (RM3010).

Un enregistrement par ligne (JSON Lines) dans `logs/karl-agent.jsonl` à la racine du
projet, avec une SÉVÉRITÉ (`debug` < `info` < `warn` < `error`) et une CATÉGORIE
contrôlée (`auth`, `issue`, `provider`, `tmux`, `claude`, `worklog`, `files`, `api`,
`mail`, `sets`, `refresh`, `pm`, `session`, `voice`, `env`, `front`, `system`) — plus
des champs libres (rm_id, sid, user, path, status, ms…). Le cockpit (RM3011) et
`mmi-pm log-tail` lisent ce fichier par `tail()`.

Réglages (variables d'environnement) :
  KARL_JOURNAL_DIR        dossier (défaut : <racine du repo>/logs — créé au besoin, ignoré par git)
  KARL_JOURNAL_LEVEL      sévérité minimale écrite (défaut : info ; `debug` pour tout voir)
  KARL_JOURNAL_MAX_MB     rotation par taille (défaut : 20) → karl-agent-<horodatage>.jsonl
  KARL_JOURNAL_KEEP_DAYS  rétention des fichiers tournés (défaut : 14)
  KARL_JOURNAL_STDERR     `0` pour ne plus refléter warn/error sur stderr (journald)

Aucune dépendance ; thread-safe ; jamais une exception ne remonte à l'appelant (un journal
qui plante ce qu'il observe n'aide personne) — un défaut d'écriture est compté dans
`stats()["errors"]`.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import threading
from pathlib import Path

LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}
CATEGORIES = frozenset({"auth", "issue", "provider", "tmux", "claude", "worklog", "files", "api",
                        "mail", "sets", "refresh", "pm", "session", "voice", "env", "front", "system"})
FILE_NAME = "karl-agent.jsonl"

_LOCK = threading.Lock()
_STATE = {"dir": None, "level": None, "max_bytes": None, "keep_days": None, "stderr": None,
          "written": 0, "dropped": 0, "errors": 0, "rotations": 0}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def configure(directory=None, level=None, max_mb=None, keep_days=None, stderr=None) -> dict:
    """Fixe (ou relit depuis l'environnement) les réglages. Appelée paresseusement au premier `log()`."""
    with _LOCK:
        _STATE["dir"] = Path(directory or os.environ.get("KARL_JOURNAL_DIR") or (_repo_root() / "logs"))
        lvl = str(level or os.environ.get("KARL_JOURNAL_LEVEL") or "info").lower()
        _STATE["level"] = LEVELS.get(lvl, LEVELS["info"])
        try:
            _STATE["max_bytes"] = int(float(max_mb if max_mb is not None else os.environ.get("KARL_JOURNAL_MAX_MB", "20")) * 1024 * 1024)
        except ValueError:
            _STATE["max_bytes"] = 20 * 1024 * 1024
        try:
            _STATE["keep_days"] = int(keep_days if keep_days is not None else os.environ.get("KARL_JOURNAL_KEEP_DAYS", "14"))
        except ValueError:
            _STATE["keep_days"] = 14
        _STATE["stderr"] = (stderr if stderr is not None else os.environ.get("KARL_JOURNAL_STDERR", "1")) not in ("0", "", False)
        return dict(_STATE)


def _ensure() -> None:
    if _STATE["dir"] is None:
        configure()


def journal_path() -> Path:
    _ensure()
    return _STATE["dir"] / FILE_NAME


def stats() -> dict:
    _ensure()
    return {k: _STATE[k] for k in ("written", "dropped", "errors", "rotations")} | {"path": str(journal_path()), "level": [k for k, v in LEVELS.items() if v == _STATE["level"]][0]}


def _rotate_if_needed(path: Path) -> None:
    try:
        if not path.exists() or path.stat().st_size < _STATE["max_bytes"]:
            return
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        path.rename(path.with_name(f"karl-agent-{stamp}.jsonl"))
        _STATE["rotations"] += 1
        limit = _dt.datetime.now().timestamp() - _STATE["keep_days"] * 86400
        for old in path.parent.glob("karl-agent-*.jsonl"):
            try:
                if old.stat().st_mtime < limit:
                    old.unlink()
            except OSError:
                pass
    except OSError:
        _STATE["errors"] += 1


def log(category: str, level: str, message: str, *, echo: bool | None = None, **fields) -> dict | None:
    """Écrit un enregistrement. Rend le dict écrit, ou None s'il est sous le seuil ou refusé.
    `echo=False` retient l'écho stderr d'un warn/error quand l'appelant a déjà parlé sur la console (pm_git, RM3013).
    Catégorie inconnue → rangée en `system` avec le champ `bad_category` (rien n'est perdu, et ça se voit)."""
    _ensure()
    lvl = str(level).lower()
    if lvl not in LEVELS:
        lvl = "info"
        fields.setdefault("bad_level", str(level))
    if LEVELS[lvl] < _STATE["level"]:
        _STATE["dropped"] += 1
        return None
    cat = str(category).lower()
    if cat not in CATEGORIES:
        fields.setdefault("bad_category", cat)
        cat = "system"
    rec = {"ts": _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="milliseconds"),
           "level": lvl, "cat": cat, "msg": str(message)}
    for k, v in fields.items():
        if v is None:
            continue
        try:
            json.dumps(v)
            rec[k] = v
        except TypeError:
            rec[k] = str(v)
    line = json.dumps(rec, ensure_ascii=False)
    with _LOCK:
        try:
            path = journal_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            _rotate_if_needed(path)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            _STATE["written"] += 1
        except OSError:
            _STATE["errors"] += 1
        if (_STATE["stderr"] if echo is None else echo) and LEVELS[lvl] >= LEVELS["warn"]:
            try:
                extra = " ".join(f"{k}={v}" for k, v in rec.items() if k not in ("ts", "level", "cat", "msg"))
                sys.stderr.write(f"[{lvl}] {cat}: {rec['msg']}{(' · ' + extra) if extra else ''}\n")
            except (OSError, ValueError):
                pass
    return rec


def tail(category: str | None = None, level: str | None = None, since: str | None = None,
         limit: int = 200, q: str | None = None) -> list[dict]:
    """Les `limit` derniers enregistrements (du plus ancien au plus récent) filtrés par catégorie
    (csv accepté), sévérité MINIMALE, horodatage `since` (ISO, exclusif) et texte `q` (dans msg et champs)."""
    _ensure()
    path = journal_path()
    if not path.exists():
        return []
    cats = {c.strip().lower() for c in str(category).split(",") if c.strip()} if category else None
    min_lvl = LEVELS.get(str(level or "debug").lower(), LEVELS["debug"])
    needle = str(q).lower() if q else None
    limit = max(1, min(int(limit or 200), 5000))
    out: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if cats and rec.get("cat") not in cats:
            continue
        if LEVELS.get(rec.get("level", "info"), 20) < min_lvl:
            continue
        if since and str(rec.get("ts", "")) <= since:
            break
        if needle and needle not in raw.lower():
            continue
        out.append(rec)
        if len(out) >= limit:
            break
    out.reverse()
    return out


def category_for_path(path: str) -> str:
    """Catégorie d'une réponse HTTP d'après son chemin (chemin historique de karl-agent)."""
    p = str(path or "")
    if p.startswith("/auth"):
        return "auth"
    if p.startswith(("/session-set", "/session-sets")):
        return "sets"
    if p.startswith(("/spawn", "/kill", "/resume", "/sessions", "/attach", "/capture", "/stream")):
        return "tmux"
    if p.startswith(("/send", "/approve", "/auto-yes", "/monitor", "/unmonitor", "/layout", "/disposition")):
        return "session"
    if p.startswith(("/resolve", "/tickets", "/triage", "/mergecheck", "/usage", "/workspace-status", "/ticket-sessions", "/task")):
        return "issue"
    if p.startswith(("/worklog", "/pending", "/outline")):
        return "worklog"
    if p.startswith(("/file", "/fs")):
        return "files"
    if p.startswith("/mail"):
        return "mail"
    if p.startswith("/pm"):
        return "pm"
    if p.startswith(("/tts", "/stt", "/voice")):
        return "voice"
    if p.startswith(("/env", "/vault", "/health", "/core")):
        return "env"
    if p.startswith("/refresh"):
        return "refresh"
    return "api"


def exception_brief(exc: BaseException | None, limit: int = 600) -> str | None:
    """Traceback COURT (type, message, deux derniers cadres) — assez pour retrouver le site, pas de quoi noyer le journal."""
    if exc is None:
        return None
    import traceback
    frames = traceback.extract_tb(exc.__traceback__)[-2:]
    where = " ← ".join(f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in frames)
    return f"{type(exc).__name__}: {exc}"[:limit - len(where) - 3] + (" @ " + where if where else "")
