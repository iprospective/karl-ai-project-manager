"""pm_index — l'index de requêtage de karl-PM : une PROJECTION du Markdown (RM3128).

Le Markdown reste la **source de vérité**. Cette base ne contient rien qui n'en vienne,
et `rebuild()` la reconstruit entièrement : si elle brûle, on la rebâtit ; si elle ment,
on la rebâtit. C'est la seule règle qui évite la double source de vérité, qui est le
vrai risque de ce chantier — bien avant la performance.

**Pourquoi elle existe** (étude RM3129, arbitrage du 2026-09-14). Pas pour la vitesse
d'aujourd'hui : à 1 465 fiches, compter les statuts prend 48 ms. Mais l'outil est destiné
à de **gros environnements**, et le coût est linéaire — 655 ms par refresh à 20 000
fiches, 1,6 s à 50 000. D'où l'exigence qui commande toute la conception :

    **l'alimentation est INCRÉMENTALE.** Un rescan complet est la commande de
    reconstruction, jamais le fonctionnement courant — sinon on n'a fait que déplacer
    le problème d'un cran.

**Deux entrées, pas une.** Une fiche ne change pas que par les scripts PM : une
modification faite dans Redmine arrive par `pm-task-sync`, donc après coup. Un index
greffé sur les seules écritures locales serait périmé entre deux synchros — d'où
`touch()`, que les deux chemins appellent, et `status()` qui dit de quand l'index date.

Aucune dépendance : `sqlite3` est dans la stdlib et expose FTS5 (SQLite ≥ 3.9).
"""
import hashlib
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
DB_NAME = "pm-index.sqlite3"

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FIELD = {k: re.compile(rf"^{k}:\s*(.+)$", re.M)
          for k in ("redmine_id", "status", "type", "priority", "title",
                    "created", "updated", "close_reason", "parent_task")}
_LIST_RE = {k: re.compile(rf"^{k}:\s*\n((?:\s*-\s*.+\n?)*)", re.M)
            for k in ("tags", "relates", "depends_on", "blocks", "sub_tasks")}

DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS tickets (
  rm_id INTEGER PRIMARY KEY, entity TEXT, project TEXT, status TEXT, type TEXT,
  priority TEXT, title TEXT, created TEXT, updated TEXT, close_reason TEXT,
  parent_task INTEGER, path TEXT, mtime REAL, digest TEXT, indexed_at TEXT);
CREATE INDEX IF NOT EXISTS i_tickets_status  ON tickets(status);
CREATE INDEX IF NOT EXISTS i_tickets_project ON tickets(entity, project);
CREATE TABLE IF NOT EXISTS tags (rm_id INTEGER, tag TEXT, PRIMARY KEY (rm_id, tag));
CREATE TABLE IF NOT EXISTS relations (
  rm_id INTEGER, kind TEXT, other INTEGER, PRIMARY KEY (rm_id, kind, other));
CREATE INDEX IF NOT EXISTS i_rel_other ON relations(other);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(title, body, think);
"""


# ── lecture d'une fiche — pur ────────────────────────────────────────────────

def digest(text):
    """Empreinte du contenu. C'est elle qui décide qu'une fiche a VRAIMENT changé : le
    mtime seul ment (un `touch`, une copie, un checkout git rejouent la même fiche)."""
    return hashlib.sha1(str(text or "").encode("utf-8")).hexdigest()


def _items(block):
    return [ln.strip().lstrip("-").strip().strip("'\"")
            for ln in (block or "").splitlines() if ln.strip().startswith("-")]


def parse_sheet(text):
    """Champs indexables d'une fiche, ou None si ce n'en est pas une.

    Volontairement tolérant : une fiche mal formée ne doit pas faire échouer tout un
    rebuild — elle est ignorée, et `status()` le dit.
    """
    m = FM_RE.match(str(text or ""))
    if not m:
        return None
    fm, body = m.group(1), text[m.end():]
    out = {}
    for k, rx in _FIELD.items():
        g = rx.search(fm)
        out[k] = g.group(1).strip().strip("'\"") if g else None
    if not out.get("redmine_id") or not str(out["redmine_id"]).isdigit():
        return None
    out["redmine_id"] = int(out["redmine_id"])
    out["parent_task"] = (int(out["parent_task"])
                          if out.get("parent_task") and str(out["parent_task"]).isdigit()
                          else None)
    for k, rx in _LIST_RE.items():
        g = rx.search(fm)
        out[k] = _items(g.group(1)) if g else []
    out["body"] = body
    return out


def plan(known, found):
    """(à_réindexer, à_supprimer) — le cœur de l'incrémental, pur et donc testable.

    `known` = {rm_id: digest} déjà en base ; `found` = {rm_id: digest} sur le disque.
    Une fiche dont l'empreinte n'a pas bougé n'est PAS retouchée : c'est tout l'intérêt.
    """
    upsert = [rm for rm, dg in found.items() if known.get(rm) != dg]
    delete = [rm for rm in known if rm not in found]
    return sorted(upsert), sorted(delete)


# ── base ─────────────────────────────────────────────────────────────────────

def db_path(cfg):
    return Path(cfg.state_dir) / DB_NAME


def connect(cfg_or_path):
    p = cfg_or_path if isinstance(cfg_or_path, (str, Path)) else db_path(cfg_or_path)
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(DDL)
    _set_meta(con, "schema_version", str(SCHEMA_VERSION))
    return con


def _set_meta(con, key, value):
    con.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def get_meta(con, key, default=None):
    r = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def upsert_sheet(con, entity, project, path, text=None):
    """Range (ou remet à jour) une fiche. Rend True si elle a été indexée."""
    p = Path(path)
    text = text if text is not None else p.read_text(encoding="utf-8", errors="replace")
    d = parse_sheet(text)
    if not d:
        return False
    rm = d["redmine_id"]
    think = p.with_name(p.name[:-3] + ".think.md")
    think_txt = think.read_text(encoding="utf-8", errors="replace") if think.is_file() else ""
    mtime = _mtime_of(p)
    con.execute("DELETE FROM tags WHERE rm_id=?", (rm,))
    con.execute("DELETE FROM relations WHERE rm_id=?", (rm,))
    con.execute("DELETE FROM fts WHERE rowid=?", (rm,))
    con.execute(
        "INSERT INTO tickets(rm_id,entity,project,status,type,priority,title,created,"
        "updated,close_reason,parent_task,path,mtime,digest,indexed_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(rm_id) DO UPDATE SET "
        "entity=excluded.entity, project=excluded.project, status=excluded.status, "
        "type=excluded.type, priority=excluded.priority, title=excluded.title, "
        "created=excluded.created, updated=excluded.updated, "
        "close_reason=excluded.close_reason, parent_task=excluded.parent_task, "
        "path=excluded.path, mtime=excluded.mtime, digest=excluded.digest, "
        "indexed_at=excluded.indexed_at",
        (rm, entity, project, d["status"], d["type"], d["priority"], d["title"],
         d["created"], d["updated"], d["close_reason"], d["parent_task"],
         str(p), mtime, digest(text + think_txt), _now()))
    con.executemany("INSERT OR IGNORE INTO tags(rm_id,tag) VALUES(?,?)",
                    [(rm, t) for t in d["tags"]])
    rels = [(rm, k, int(v)) for k in ("relates", "depends_on", "blocks", "sub_tasks")
            for v in d[k] if str(v).isdigit()]
    if d["parent_task"]:
        rels.append((rm, "parent", d["parent_task"]))
    con.executemany("INSERT OR IGNORE INTO relations(rm_id,kind,other) VALUES(?,?,?)", rels)
    con.execute("INSERT INTO fts(rowid,title,body,think) VALUES(?,?,?,?)",
                (rm, d["title"] or "", d["body"] or "", think_txt))
    return True


def forget(con, rm_id):
    """Retire une fiche disparue. Sans cela l'index garderait des morts, et une
    recherche rendrait des tickets qui n'existent plus — pire qu'un index absent."""
    for t in ("tickets", "tags", "relations"):
        con.execute(f"DELETE FROM {t} WHERE rm_id=?", (rm_id,))
    con.execute("DELETE FROM fts WHERE rowid=?", (rm_id,))


def known_digests(con):
    return {r["rm_id"]: r["digest"] for r in con.execute("SELECT rm_id,digest FROM tickets")}


# ── parcours des sources ─────────────────────────────────────────────────────

def iter_sheets_of(cfg):
    """(entity, project, chemin) de chaque fiche. Passe par `pm_think.iter_sheets`, la
    seule façon d'énumérer des fiches (RM3085) — refiltrer à la main oublierait un
    suffixe le jour où il s'en ajoute un."""
    from pm_think import iter_sheets
    for ent, proj, _ in cfg.iter_projects():
        d = cfg.path("tasks_dir", entity=ent, project=proj)
        if d.is_dir():
            for f in iter_sheets(d):
                yield ent, proj, f


def _mtime_of(f):
    """mtime le plus récent entre la fiche et sa réflexion — le think compte dans
    l'empreinte, donc le modifier doit suffire à rendre la fiche candidate."""
    from pm_think import think_path
    try:
        m = f.stat().st_mtime
    except OSError:
        return 0.0
    th = think_path(f)
    if th.is_file():
        try:
            m = max(m, th.stat().st_mtime)
        except OSError:
            pass
    return m


def scan_digests(cfg, cache=None):
    """{rm_id: (entity, project, path, empreinte)} du disque.

    `cache` = {chemin: (mtime, rm_id, empreinte)} déjà connu : un fichier dont le mtime
    n'a pas bougé n'est PAS RELU — c'est ce qui tient l'exigence « jamais de rescan
    complet en régime nominal ». Sans ce filtre, `update` relisait les 15,5 Mo du corpus
    même quand rien n'avait changé (mesuré : 203 ms à 1 465 fiches, donc ~2,8 s à 20 000).

    Le mtime SEUL ne ferait pas foi — un `touch`, une copie ou un checkout git le
    bougent sans changer le contenu : il sert à choisir QUI relire, l'empreinte tranche.
    """
    from pm_think import think_path
    cache = cache or {}
    out = {}
    for ent, proj, f in iter_sheets_of(cfg):
        key = str(f)
        mt = _mtime_of(f)
        hit = cache.get(key)
        if hit and hit[0] == mt:
            out[hit[1]] = (ent, proj, f, hit[2])
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        d = parse_sheet(txt)
        if not d:
            continue
        th = think_path(f)
        th_txt = th.read_text(encoding="utf-8", errors="replace") if th.is_file() else ""
        out[d["redmine_id"]] = (ent, proj, f, digest(txt + th_txt))
    return out


def mtime_cache(con):
    """{chemin: (mtime, rm_id, empreinte)} — ce que la base sait déjà du disque."""
    return {r["path"]: (r["mtime"], r["rm_id"], r["digest"])
            for r in con.execute("SELECT path, mtime, rm_id, digest FROM tickets")}


def rebuild(cfg, con=None):
    """Reconstruit TOUT depuis les sources. Rend un compte rendu mesuré.

    C'est la commande de secours et d'initialisation — jamais le régime nominal.
    """
    t0 = time.perf_counter()
    con = con or connect(cfg)          # la connexion appartient à l'appelant : il ferme
    for t in ("tickets", "tags", "relations"):
        con.execute(f"DELETE FROM {t}")
    con.execute("DELETE FROM fts")
    n = skipped = 0
    for ent, proj, f in iter_sheets_of(cfg):
        if upsert_sheet(con, ent, proj, f):
            n += 1
        else:
            skipped += 1
    _set_meta(con, "last_rebuild", _now())
    _set_meta(con, "last_update", _now())
    con.commit()
    return {"indexed": n, "skipped": skipped, "seconds": round(time.perf_counter() - t0, 3)}


def update(cfg, con=None):
    """Met à jour l'index — INCRÉMENTAL : seules les fiches dont l'empreinte a bougé
    sont retouchées, et les disparues sont retirées."""
    t0 = time.perf_counter()
    con = con or connect(cfg)
    found = scan_digests(cfg, mtime_cache(con))
    up, rm = plan(known_digests(con), {k: v[3] for k, v in found.items()})
    for rid in up:
        ent, proj, f, _ = found[rid]
        upsert_sheet(con, ent, proj, f)
    for rid in rm:
        forget(con, rid)
    _set_meta(con, "last_update", _now())
    con.commit()
    return {"updated": len(up), "removed": len(rm), "unchanged": len(found) - len(up),
            "seconds": round(time.perf_counter() - t0, 3)}


def touch(cfg, path, entity=None, project=None):
    """Réindexe UNE fiche — le point d'accroche des deux entrées d'alimentation :
    l'écriture locale et le rapatriement `pm-task-sync`. Ne lève jamais : un index en
    échec ne doit pas faire échouer l'écriture d'un ticket, c'est une projection."""
    try:
        p = Path(path)
        con = connect(cfg)
        try:
            if not p.is_file():
                d = con.execute("SELECT rm_id FROM tickets WHERE path=?",
                                (str(p),)).fetchone()
                if d:
                    forget(con, d["rm_id"])
            else:
                ent, proj = entity, project
                if not (ent and proj):
                    r = con.execute("SELECT entity,project FROM tickets WHERE path=?",
                                    (str(p),)).fetchone()
                    ent, proj = (r["entity"], r["project"]) if r else (ent, proj)
                upsert_sheet(con, ent, proj, p)
            _set_meta(con, "last_update", _now())
            con.commit()
            return True
        finally:
            con.close()
    except Exception:                     # noqa: BLE001 — jamais fatal, c'est un miroir
        return False


def status(cfg, con=None):
    """Ce que l'index sait de lui-même : volume, fraîcheur, et DIVERGENCE éventuelle.

    La divergence est la seule chose qui compte vraiment pour un miroir : un index qui
    ne sait pas dire qu'il est en retard est pire qu'un index absent, parce qu'on le croit.
    """
    con = con or connect(cfg)
    n = con.execute("SELECT COUNT(*) c FROM tickets").fetchone()["c"]
    by = {r["status"]: r["c"] for r in con.execute(
        "SELECT status, COUNT(*) c FROM tickets GROUP BY status ORDER BY c DESC")}
    found = scan_digests(cfg, mtime_cache(con))
    up, rm = plan(known_digests(con), {k: v[3] for k, v in found.items()})
    return {"tickets": n, "by_status": by, "on_disk": len(found),
            "stale": len(up), "orphans": len(rm),
            "last_rebuild": get_meta(con, "last_rebuild"),
            "last_update": get_meta(con, "last_update"),
            "db": str(db_path(cfg))}


def count_by_status(cfg, con=None):
    """Le compteur que le cockpit rafraîchit — la raison d'être immédiate de l'index."""
    con = con or connect(cfg)
    return {r["status"]: r["c"] for r in con.execute(
        "SELECT status, COUNT(*) c FROM tickets GROUP BY status")}


def query(cfg, text=None, status_=None, project=None, limit=20, con=None):
    """Recherche : FTS5 (BM25) quand il y a du texte, filtres SQL sinon."""
    con = con or connect(cfg)
    where, args = [], []
    if status_:
        where.append("t.status = ?"); args.append(status_)
    if project:
        ent, _, proj = str(project).partition("/")
        where.append("t.entity = ?"); args.append(ent)
        if proj:
            where.append("t.project = ?"); args.append(proj)
    if text:
        sql = ("SELECT t.*, bm25(fts) AS rank FROM fts JOIN tickets t ON t.rm_id = fts.rowid "
               "WHERE fts MATCH ?")
        args = [text] + args
        if where:
            sql += " AND " + " AND ".join(where)
        sql += " ORDER BY rank LIMIT ?"
    else:
        sql = "SELECT t.* FROM tickets t"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY t.rm_id DESC LIMIT ?"
    args.append(int(limit))
    return [dict(r) for r in con.execute(sql, args)]
