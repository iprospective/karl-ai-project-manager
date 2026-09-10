"""Id de session court (entier incrémental) + registre des branches/worktrees
ouverts par session (RM2034).

But : nommer branches et worktrees sans collision quand plusieurs sessions /
tickets cohabitent, et « mémoriser les worktrees ouverts » d'une session.

Stockage **machine-local**, dans le repo PM sous `var/sessions/` (`var/` est
gitignoré → ni churn ni conflit de fédération) :
  - `var/sessions/.seq`        : entier courant (façon AUTO_INCREMENT) ;
  - `var/sessions/index.json`  : registre `{ "<seq>": { seq, machine, claude_session_id,
                                  created, branches[], worktrees[] } }`.

Concurrence : **un seul `flock(LOCK_EX)`** couvre check + incrément + écriture du
registre, ce qui garantit (1) deux sessions distinctes → numéros distincts, et
(2) une même session → allocation **une seule fois** (réutilise si déjà inscrite),
même en commandes parallèles. Écriture du compteur atomique (tmp + os.replace).

`PM_MACHINE_ID` (PMid) vient de `<PM>/.env` (chargé par PMConfig), pose l'unicité
cross-machine via le naming `m<PMid>`.

Hors session Claude Code (`$CLAUDE_CODE_SESSION_ID` absent : cron, exécution
manuelle…), `get_session_seq()` renvoie `None` et les `record_*` sont no-op.
"""
import fcntl
import json
import os
from datetime import datetime
from pathlib import Path

from pm_paths import PMConfig


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def sessions_dir() -> Path:
    cfg = PMConfig.load()
    d = cfg.state_dir / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def machine_id() -> str:
    """Id de machine (PMid) depuis `$PM_MACHINE_ID` (.env). '0' par défaut."""
    return os.environ.get("PM_MACHINE_ID", "0").strip() or "0"


def claude_session_id():
    return os.environ.get("CLAUDE_CODE_SESSION_ID")


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


#: RM3085 — l'index croissait sans fin (88 Ko sur ce poste, une entrée par session depuis toujours).
#: Il sert à retrouver les branches et worktrees d'une session VIVANTE ou récente : au-delà, c'est de
#: l'archive que personne ne relit. Bornage par nombre d'entrées (les seq sont croissants).
INDEX_KEEP = int(os.environ.get("PM_SESSIONS_INDEX_KEEP") or 500)


def _trim(idx: dict) -> bool:
    """Ne garde que les `INDEX_KEEP` seq les plus récents. Rend True si l'index a changé. Pure."""
    if INDEX_KEEP <= 0 or len(idx) <= INDEX_KEEP:
        return False
    for k in sorted(idx, key=lambda s: int(s) if str(s).isdigit() else 0)[:-INDEX_KEEP]:
        idx.pop(k, None)
    return True


def _locked(fn):
    """Exécute `fn(idx)` sous flock exclusif ; persiste l'index si fn renvoie
    (valeur, True). Renvoie la valeur. Le lock couvre lecture + écriture."""
    d = sessions_dir()
    index = d / "index.json"
    with open(d / ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        idx = _read_json(index, {})
        value, dirty = fn(idx)
        trimmed = _trim(idx) if dirty else False   # RM3085 : bornage à l'écriture, jamais en lecture
        if dirty or trimmed:
            _write_json(index, idx)
        return value
    # flock relâché à la fermeture du with


def get_session_seq():
    """Seq de la session courante, alloué **une seule fois**. None hors session."""
    csid = claude_session_id()
    if not csid:
        return None
    d = sessions_dir()
    seqfile = d / ".seq"

    def alloc(idx):
        for s, rec in idx.items():
            if rec.get("claude_session_id") == csid:
                return int(s), False  # déjà alloué pour cette session
        n = (int(seqfile.read_text()) if seqfile.exists() else 0) + 1
        tmp = seqfile.with_suffix(".tmp")
        tmp.write_text(str(n))
        os.replace(tmp, seqfile)
        idx[str(n)] = {
            "seq": n,
            "machine": machine_id(),
            "claude_session_id": csid,
            "created": _now(),
            "branches": [],
            "worktrees": [],
        }
        return n, True

    return _locked(alloc)


def _record(field, entry):
    """Ajoute `entry` (dédupliqué) à idx[<seq>][field] pour la session courante."""
    seq = get_session_seq()
    if seq is None:
        return None

    def add(idx):
        rec = idx.get(str(seq))
        if rec is None:
            return None, False
        lst = rec.setdefault(field, [])
        if entry not in lst:
            lst.append(entry)
            return seq, True
        return seq, False

    return _locked(add)


def record_ticket(rm_id):
    """RM3086 — enregistre qu'un ticket est travaillé par la session courante.

    Le lien ticket ↔ session existait en TROIS exemplaires qui s'ignoraient (inventaire RM3015) :
    `worklog.items[].ref` (hors git, maille session), les jonctions `karl-agent/tasks/*.json`
    (locales à la machine, jamais partagées) et le `.log.md` (versionné, maille ticket). Aucun ne
    connaissait les deux autres, si bien que « qui travaille sur ce ticket ? » n'avait pas de
    réponse fiable — et qu'une seconde session s'ouvrait sur un ticket déjà pris sans un mot.

    Ce registre-ci est celui qui survit (D020) : partagé, sous verrou, dans le repo. No-op hors session."""
    try:
        rid = int(str(rm_id).lstrip("Rm").lstrip("M") or 0)
    except (TypeError, ValueError):
        return None
    return _record("tickets", rid) if rid else None


def sessions_of_ticket(rm_id, idx=None) -> list:
    """[{seq, claude_session_id, machine, branches, worktrees}] des sessions qui ont travaillé ce
    ticket, la plus récente d'abord. Pure vis-à-vis du registre passé (testable sans disque)."""
    try:
        rid = int(str(rm_id).lstrip("Rm").lstrip("M"))
    except (TypeError, ValueError):
        return []
    idx = all_records() if idx is None else idx
    out = [dict(rec, seq=int(s)) for s, rec in (idx or {}).items()
           if rid in [int(x) for x in (rec.get("tickets") or []) if str(x).isdigit()]]
    out.sort(key=lambda r: r.get("seq", 0), reverse=True)
    return out


def record_branch(branch: str):
    """Enregistre une branche créée par la session courante. No-op hors session."""
    return _record("branches", branch)


def record_worktree(path: str):
    """Enregistre un worktree créé par la session courante. No-op hors session."""
    return _record("worktrees", str(path))


def forget_worktree(path: str):
    """Retire un worktree du registre de la session courante (après suppression
    git). No-op hors session / si absent."""
    seq = get_session_seq()
    if seq is None:
        return

    def rm(idx):
        rec = idx.get(str(seq))
        if rec and str(path) in rec.get("worktrees", []):
            rec["worktrees"].remove(str(path))
            return None, True
        return None, False

    _locked(rm)


def all_records():
    """Tous les enregistrements de session (registre complet)."""
    return _read_json(sessions_dir() / "index.json", {})


def current_record():
    """Registre de la session courante (dict) ou None. **N'alloue pas** de seq
    (lecture seule) : sûr à appeler depuis un simple affichage de statut."""
    csid = claude_session_id()
    if not csid:
        return None
    idx = _read_json(sessions_dir() / "index.json", {})
    for rec in idx.values():
        if rec.get("claude_session_id") == csid:
            return rec
    return None


def branch_suffix() -> str:
    """Suffixe de discrimination `-m<PMid>-s<seq>` (concurrence). '' hors session."""
    seq = get_session_seq()
    if seq is None:
        return ""
    return f"-m{machine_id()}-s{seq}"
