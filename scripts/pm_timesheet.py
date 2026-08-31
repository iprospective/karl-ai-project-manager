#!/usr/bin/env python3
"""pm_timesheet — reconstitution du temps de travail HUMAIN à partir des traces d'agents (RM2890).

Bibliothèque de la feuille de temps : collecte des traces, modèle temporel, règles métier,
rendu. Le CLI est `pm-timesheet.py` (→ `mmi-pm timesheet`). Analyse et arbitrages :
`docs/cdc-rm2890-timesheet-heures-humaines.md` du projet `pm-ai-agents`.

Chaîne de traitement (chaque étape est une fonction pure, testable hors ligne) :

  collecte → attribution → intervalles → union → répartition → règles métier
  → déduction des saisies existantes → arrondi → rapport

**Aucune assistance IA n'intervient** : lecture de fichiers, SQL, arithmétique et
API Redmine. Un run mensuel ne consomme pas de tokens.

Deux invariants, tenus par des tests :

1. **Non-double-comptage** — le total d'une journée est la mesure de l'UNION des
   intervalles de présence : deux demandes simultanées sur deux projets ne
   comptent jamais double. La somme des lignes attribuées égale exactement cette
   mesure.
2. **Conservation** — refacturation, clé multi-clients et arrondi déplacent du
   temps, ils n'en créent ni n'en détruisent.
"""
import bisect
import collections
import json
import re
import sqlite3
import sys
import tarfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

try:
    import yaml
except ImportError:  # laissé à l'appelant
    yaml = None


# ── Configuration ────────────────────────────────────────────────────────────

#: Réglages par défaut. Tous surchargeables (config projet ou options CLI) ;
#: les valeurs sont celles calibrées sur août 2026 (CDC § 6).
DEFAULTS = {
    # temps de rédaction/réflexion qui PRÉCÈDE l'envoi d'un prompt, en minutes :
    # clamp(write_base + longueur / chars_per_min, write_min, write_max)
    "write_base": 1.0,
    "chars_per_min": 45.0,
    "write_min": 1.5,
    "write_max": 30.0,
    # temps de supervision APRÈS l'envoi : min(écart au prochain événement, ce plafond).
    # C'est LE réglage sensible (±20 % sur le mois) : il borne le temps compté
    # quand l'agent travaille seul et que l'humain revient bien plus tard.
    "follow_cap": 10.0,
    # plage ouvrée (lundi→vendredi) : seule fenêtre où le temps transversal se refacture
    "work_start_hour": 8,
    "work_end_hour": 19,
    # en deçà de ce temps client dans la journée, la journée n'est pas « cliente » :
    # le transversal du jour est proposé NON COMPTÉ
    "client_threshold_min": 60.0,
    # tranche d'arrondi des lignes finales
    "quantum_min": 15,
    # forfait de longueur quand la source ne donne pas le texte (opencode : table `part`)
    "default_prompt_chars": 120,
}

#: Messages de rôle `user` qui ne sont PAS un humain qui tape (CDC § 3quater).
#: Sans ce filtre, août serait surévalué de 39,3 h au lieu de 19,8 — les trois
#: quarts du gain seraient du bruit système.
BRUIT_RE = re.compile(
    r"^\s*(?:"
    r"Base directory for this skill"
    r"|Continue from where you left off"
    r"|Caveat:"
    r"|This session is being continued"
    r"|\[Request interrupted"
    r"|The user sent a new message"
    r"|<(?:command|local-command|user-prompt|bash|system-reminder)"
    r")",
    re.I,
)


def est_prompt_humain(texte):
    """Un texte soumis par un humain, par opposition au bruit système."""
    t = (texte or "").strip()
    if not t or BRUIT_RE.match(t):
        return False
    return "system-reminder" not in t[:300]


# ── Événements ───────────────────────────────────────────────────────────────

@dataclass
class Event:
    """Une trace horodatée d'implication humaine.

    `extends` distingue les deux natures : les traces HUMAINES créent du temps,
    les traces d'AGENT n'en créent pas — elles servent seulement à attribuer le
    temps déjà créé. Sans cette distinction, une nuit de travail autonome de
    l'agent deviendrait du temps facturable.
    """
    ts: datetime
    chars: int = 0
    source: str = ""          # claude-transcript | claude-history | opencode | …
    cwd: str = None
    session: str = None
    text: str = ""
    extends: bool = True
    scores: dict = field(default_factory=dict)   # {(entity, project, rm_id): poids}

    def key(self):
        """Clé de déduplication inter-sources : la minute + le début du texte."""
        return (self.ts.strftime("%Y-%m-%dT%H:%M"), (self.text or "")[:60])


def _iter_jsonl(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return


def _blocks(evt):
    """(role, blocs de contenu) d'un événement de transcript, normalisé."""
    msg = evt.get("message") if isinstance(evt, dict) else None
    if not isinstance(msg, dict):
        return None, []
    content = msg.get("content")
    if isinstance(content, str):
        return msg.get("role"), [{"type": "text", "text": content}]
    if isinstance(content, list):
        return msg.get("role"), content
    return msg.get("role"), []


def _texte_utilisateur(evt):
    """Texte d'un message `user`, ou None si ce n'en est pas un (tool_result…)."""
    role, blocks = _blocks(evt)
    if role != "user":
        return None
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "tool_result":
            return None
    return " ".join(b.get("text", "") for b in blocks if isinstance(b, dict))


def collect_claude_transcripts(projects_dir, depuis=None, jusqu_a=None):
    """Prompts humains des transcripts Claude Code — la source PRIMAIRE.

    `~/.claude/projects` est partagé entre l'hôte et le conteneur (bind mount
    LXC) : ces fichiers portent donc les sessions des DEUX, là où
    `history.jsonl` n'en voit qu'une (CDC § 3quater). Ils donnent en prime le
    `cwd` et la branche git à l'instant du prompt.
    """
    out = []
    for p in sorted(Path(projects_dir).glob("*/*.jsonl")):
        for evt in _iter_jsonl(p):
            ts = evt.get("timestamp")
            if not ts:
                continue
            txt = _texte_utilisateur(evt)
            if txt is None or not est_prompt_humain(txt):
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
            except ValueError:
                continue
            dt = dt.replace(tzinfo=None)
            if not _dans_periode(dt, depuis, jusqu_a):
                continue
            out.append(Event(ts=dt, chars=len(txt), source="claude-transcript",
                             cwd=evt.get("cwd"), session=evt.get("sessionId"),
                             text=txt))
    return out


def collect_claude_history(path, depuis=None, jusqu_a=None):
    """Prompts de `~/.claude/history.jsonl` — complément DURABLE.

    Limité aux sessions de cette machine (le fichier n'est pas partagé), mais il
    remonte plus loin que les transcripts, qui sont purgés au bout de quelques
    semaines.
    """
    out = []
    for d in _iter_jsonl(path):
        ts = d.get("timestamp")
        if not ts:
            continue
        dt = datetime.fromtimestamp(ts / 1000)
        if not _dans_periode(dt, depuis, jusqu_a):
            continue
        txt = d.get("display") or ""
        if not est_prompt_humain(txt):
            continue
        colle = sum(len(str(v)) for v in (d.get("pastedContents") or {}).values())
        out.append(Event(ts=dt, chars=len(txt) + min(colle, 2000),
                         source="claude-history", cwd=d.get("project"),
                         session=d.get("sessionId"), text=txt))
    return out


def collect_opencode(db_path, depuis=None, jusqu_a=None, defaut_chars=None):
    """Messages humains d'une base opencode (SQLite).

    Table `session` (dont `directory` et le `title`, souvent porteur du nom du
    client) et table `message` (rôle dans la colonne JSON `data`). Le texte vit
    dans la table `part` ; à défaut, une longueur forfaitaire est utilisée.
    """
    p = Path(db_path)
    if not p.is_file():
        return []
    defaut_chars = defaut_chars or DEFAULTS["default_prompt_chars"]
    out = []
    try:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        sessions = {sid: (d, t) for sid, d, t
                    in con.execute("select id, directory, title from session")}
        textes = {}
        try:
            for mid, data in con.execute("select message_id, data from part"):
                try:
                    j = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    continue
                if j.get("type") == "text" and j.get("text"):
                    textes[mid] = (textes.get(mid, "") + " " + j["text"])[:4000]
        except sqlite3.Error:
            pass   # schéma sans table `part` exploitable : forfait
        for mid, sid, tc, data in con.execute(
                "select id, session_id, time_created, data from message"):
            try:
                j = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                continue
            if j.get("role") != "user":
                continue
            dt = datetime.fromtimestamp(tc / 1000)
            if not _dans_periode(dt, depuis, jusqu_a):
                continue
            txt = textes.get(mid, "")
            if txt and not est_prompt_humain(txt):
                continue
            directory, title = sessions.get(sid, (None, None))
            out.append(Event(ts=dt, chars=len(txt) or defaut_chars, source="opencode",
                             cwd=directory, session=sid, text=txt or (title or "")))
    except sqlite3.Error:
        return out
    finally:
        con.close()
    return out


def _dans_periode(dt, depuis, jusqu_a):
    if depuis and dt < depuis:
        return False
    if jusqu_a and dt >= jusqu_a:
        return False
    return True


def dedupe(events, tolerance_min=1):
    """Fusionne les événements vus par plusieurs sources (transcript + history).

    Même minute et même début de texte ⇒ même prompt. La tolérance rattrape les
    horodatages qui diffèrent d'une minute entre les deux fichiers.
    """
    vus = {}
    for e in sorted(events, key=lambda x: (x.ts, x.source)):
        k = e.key()
        if k in vus:
            continue
        proche = any(
            ((e.ts + timedelta(minutes=o)).strftime("%Y-%m-%dT%H:%M"), k[1]) in vus
            for o in range(-tolerance_min, tolerance_min + 1) if o
        )
        if proche and k[1]:
            continue
        vus[k] = e
    return sorted(vus.values(), key=lambda x: x.ts)


# ── Sources distantes ────────────────────────────────────────────────────────

def rapatrier(host, chemin, cache_dir, kind, verbose=False):
    """Copie une source distante dans un cache local, et rend le chemin local.

    Le travail ne se fait pas que sur un poste : un compte distant
    (`dercya-www@dev`) porte ses propres traces. Plutôt que de lire à travers
    SSH à chaque calcul, on rapatrie une fois par run — c'est plus rapide, et le
    cache garde la matière quand la machine distante n'est pas joignable.

    Rendu `None` si le rapatriement échoue : une source injoignable ne doit pas
    faire tomber le calcul des autres, elle doit se signaler.
    """
    import subprocess
    cache = Path(cache_dir) / re.sub(r"[^A-Za-z0-9_.@-]", "_", f"{host}")
    cache.mkdir(parents=True, exist_ok=True)
    cible = cache / (Path(chemin).name or "source")
    base_ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host]
    try:
        if kind == "claude-transcripts":
            cible = cache / "projects"
            cible.mkdir(parents=True, exist_ok=True)
            flux = subprocess.run(base_ssh + [f"tar czf - -C {chemin} ."],
                                  capture_output=True, timeout=900)
            if flux.returncode != 0 or not flux.stdout:
                return None
            import io
            import tarfile
            with tarfile.open(fileobj=io.BytesIO(flux.stdout), mode="r:gz") as tar:
                tar.extractall(cible)
        else:
            flux = subprocess.run(base_ssh + [f"cat {chemin}"],
                                  capture_output=True, timeout=600)
            if flux.returncode != 0:
                return None
            cible.write_bytes(flux.stdout)
    except (subprocess.SubprocessError, OSError, tarfile.TarError):
        return None
    if verbose:
        print(f"  rapatrié {host}:{chemin} → {cible}", file=sys.stderr)
    return str(cible)


# ── Attribution : à quel client / projet / ticket ? ──────────────────────────

_RM_TEXTE_RE = re.compile(r"(?:\bRM[\s#-]?|\B#)(\d{3,5})\b|^\s*(\d{4})\b", re.I)
_LOG_ENTREE_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}) —", re.M)

#: Poids relatifs des indices d'attribution (CDC § 5.3). Un prompt ne « choisit »
#: pas un ticket : il répartit son poids entre les candidats. Sur 2 328 tours
#: d'août, deux tickets ou plus étaient actifs simultanément dans plus de la
#: moitié des fenêtres : viser la vérité prompt par prompt est illusoire, viser
#: la justesse des proportions sur la journée ne l'est pas.
POIDS = {"tick": 3.0, "texte": 3.0, "log": 2.0, "projet": 1.0}


def _titre_ticket(chemin):
    """`title:` du frontmatter d'un ticket — sans charger tout le YAML."""
    try:
        with open(chemin, encoding="utf-8", errors="replace") as f:
            for i, ligne in enumerate(f):
                if i > 40:
                    break
                if ligne.startswith("title:"):
                    v = ligne.split(":", 1)[1].strip()
                    if v[:1] in ("'", '"'):
                        q, v = v[0], v[1:]
                        v = v[:v.rfind(q)] if q in v[1:] else v
                        if q == "'":
                            v = v.replace("''", "'")     # dé-échappement YAML
                    return v
    except OSError:
        pass
    return ""


class TargetResolver:
    """Résout (client, projet, ticket) pour un événement.

    Le rattachement au PROJET est fiable (98 % via le `cwd`) ; celui au TICKET ne
    l'est pas au cas par cas — d'où une distribution de poids plutôt qu'un choix.
    """

    def __init__(self, cfg, path_map=None, log_window=(2, 12)):
        self.cfg = cfg
        self.path_map = dict(path_map or {})
        self.log_window = log_window
        self._cache_projet = {}
        self._timeline = None
        self._timeline_ts = None
        self._index_tickets = None

    # -- projet --------------------------------------------------------------
    def projet(self, cwd):
        """(entity, project) depuis un répertoire de travail, ou None.

        Trois chances : la table de correspondance déclarée (indispensable pour
        les chemins d'un autre hôte ou disparus depuis), puis le mécanisme PM
        standard (`.mmi-pm`), puis les préfixes déclarés.
        """
        if not cwd:
            return None
        if cwd in self._cache_projet:
            return self._cache_projet[cwd]
        res = None
        if cwd in self.path_map:
            res = tuple(self.path_map[cwd])
        else:
            for prefixe, cible in sorted(self.path_map.items(), key=lambda kv: -len(kv[0])):
                if cwd.startswith(prefixe.rstrip("/") + "/"):
                    res = tuple(cible)
                    break
        if res is None:
            p = Path(cwd)
            if p.exists():
                try:
                    got = self.cfg.detect_project_from_cwd(p)
                except Exception:
                    got = None
                res = tuple(got) if got else None
        self._cache_projet[cwd] = res
        return res

    def index_tickets(self):
        """{rm_id : (entity, project)} — tous les tickets connus du PM.

        Sert deux fois : écarter les identifiants qui ne correspondent à aucun
        ticket (RM9999 et autres restes de test cités dans une conversation), et
        rattacher un ticket à SON projet plutôt qu'à celui du répertoire courant
        — un ticket appartient à un seul projet, et il le sait mieux que le `cwd`.
        """
        if self._index_tickets is not None:
            return self._index_tickets
        idx = {}
        for ent, proj, _ in self.cfg.iter_projects():
            try:
                tasks_dir = self.cfg.path("tasks_dir", entity=ent, project=proj)
            except Exception:
                continue
            if not tasks_dir.is_dir():
                continue
            for f in tasks_dir.glob("RM*_*.md"):
                if f.name.endswith(".log.md"):
                    continue
                rm = f.name[2:].split("_")[0]
                if rm.isdigit():
                    idx.setdefault(rm, (ent, proj, _titre_ticket(f)))
        self._index_tickets = idx
        return idx

    def cible_ticket(self, rm, defaut):
        """(entity, project, rm) validé — ou None si le ticket n'existe pas."""
        if not rm:
            return None
        rm = str(rm)
        place = self.index_tickets().get(rm)
        if place is None:
            return None
        return (place[0], place[1], rm)

    def titre(self, rm):
        """Titre d'un ticket, pour le compte rendu. '' si inconnu."""
        place = self.index_tickets().get(str(rm)) if rm else None
        return place[2] if place and len(place) > 2 else ""

    # -- timeline des .log.md ------------------------------------------------
    def timeline(self):
        """[(ts, rm_id, entity, project)] — les entrées horodatées des journaux.

        9 763 entrées sur le seul mois d'août : c'est la trace la plus dense de
        ce sur quoi les agents travaillaient, ticket par ticket, et elle survit
        à la purge des transcripts.
        """
        if self._timeline is not None:
            return self._timeline
        tl = []
        for ent, proj, _ in self.cfg.iter_projects():
            try:
                tasks_dir = self.cfg.path("tasks_dir", entity=ent, project=proj)
            except Exception:
                continue
            if not tasks_dir.is_dir():
                continue
            for f in tasks_dir.glob("RM*_*.log.md"):
                rm = f.name[2:].split("_")[0]
                if not rm.isdigit():
                    continue
                try:
                    txt = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for m in _LOG_ENTREE_RE.finditer(txt):
                    try:
                        ts = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M")
                    except ValueError:
                        continue
                    tl.append((ts, rm, ent, proj))
        tl.sort()
        self._timeline = tl
        self._timeline_ts = [x[0] for x in tl]
        return tl

    def logs_proches(self, ts, projet):
        """Entrées de journal du MÊME projet dans la fenêtre autour de `ts`."""
        tl = self.timeline()
        avant, apres = self.log_window
        lo = bisect.bisect_left(self._timeline_ts, ts - timedelta(minutes=avant))
        hi = bisect.bisect_right(self._timeline_ts, ts + timedelta(minutes=apres))
        return [x for x in tl[lo:hi] if projet and (x[2], x[3]) == tuple(projet)]

    # -- attribution complète ------------------------------------------------
    def resolve(self, event, rm_du_tour=None):
        """Remplit `event.scores` : {(entity, project, rm_id): poids}."""
        proj = self.projet(event.cwd)
        ent, pr = proj if proj else (None, None)
        scores = collections.Counter()

        cible = self.cible_ticket(rm_du_tour, (ent, pr))
        if cible:
            scores[cible] += POIDS["tick"]

        m = _RM_TEXTE_RE.search(event.text or "")
        if m:
            rid = m.group(1) or m.group(2)
            cible = self.cible_ticket(rid, (ent, pr)) if rid else None
            if cible:
                scores[cible] += POIDS["texte"]

        proches = self.logs_proches(event.ts, proj) if proj else []
        if proches:
            freq = collections.Counter(x[1] for x in proches)
            total = sum(freq.values())
            for rm, n in freq.items():
                cible = self.cible_ticket(rm, (ent, pr))
                if cible:
                    scores[cible] += POIDS["log"] * n / total

        if not scores:
            scores[(ent, pr, None)] += POIDS["projet"]
        event.scores = dict(scores)
        return event


def rm_par_tour(projects_dir, depuis=None, jusqu_a=None):
    """{(session, minute) → rm_id} en rejouant la cascade officielle du tick PM.

    On ne réinvente pas la résolution : `pm-task-tick.resolve_current_rm_id()`
    tourne en production et regarde ce que le tour a réellement TOUCHÉ (mutation
    PM > édition d'un fichier de ticket > mention), en excluant les tickets
    fermés. Son journal d'échecs ne compte que dix lignes depuis sa mise en
    service ; rejouée sur les 2 328 tours d'août, elle attribue 94,2 % des tours.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pm_task_tick", str(Path(__file__).resolve().parent / "pm-task-tick.py"))
    if spec is None or spec.loader is None:
        return {}
    tick = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(tick)
    except Exception:
        return {}

    ferme = {}
    origine = tick._is_closed

    def _is_closed_cache(rid):
        if rid not in ferme:
            try:
                ferme[rid] = origine(rid)
            except Exception:
                ferme[rid] = False
        return ferme[rid]

    tick._is_closed = _is_closed_cache
    out = {}
    for p in sorted(Path(projects_dir).glob("*/*.jsonl")):
        events = tick._load_transcript(p) or []
        humains = [i for i, e in enumerate(events) if tick._is_human_prompt(e)]
        for n, i in enumerate(humains):
            ts = events[i].get("timestamp")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
            except ValueError:
                continue
            dt = dt.replace(tzinfo=None)
            if not _dans_periode(dt, depuis, jusqu_a):
                continue
            fin = humains[n + 1] if n + 1 < len(humains) else len(events)
            pick = tick._pick_from_events(events[i:fin])          # ce que le tour a touché
            if pick is None:
                pick = tick._pick_from_events(events[:fin])        # continuation de session
            if pick:
                sid = events[i].get("sessionId")
                out[(sid, dt.strftime("%Y-%m-%dT%H:%M"))] = pick[0]
    return out


# ── Modèle temporel : intervalles, union, répartition ────────────────────────

@dataclass
class Interval:
    debut: datetime
    fin: datetime
    scores: dict
    extends: bool = True


def build_intervals(events, params=None):
    """Un intervalle de présence par événement : [t − rédaction ; t + suivi].

    La rédaction PRÉCÈDE l'envoi (comprendre la question, formuler la demande) ;
    le suivi le suit (lire, superviser) et il est PLAFONNÉ. C'est ce plafond qui
    règle le cas « je pose une question, l'agent travaille 15 mn, je reviens
    une heure après » : l'absence n'est jamais facturée.
    """
    p = {**DEFAULTS, **(params or {})}
    evs = sorted(events, key=lambda e: e.ts)
    suivants = [e.ts for e in evs]
    out = []
    for i, e in enumerate(evs):
        redaction = min(max(p["write_base"] + e.chars / p["chars_per_min"],
                            p["write_min"]), p["write_max"])
        if i + 1 < len(evs):
            ecart = (suivants[i + 1] - e.ts).total_seconds() / 60
        else:
            ecart = p["follow_cap"]
        suivi = min(max(ecart, 0.0), p["follow_cap"])
        if not e.extends:
            redaction = suivi = 0.0
        out.append(Interval(e.ts - timedelta(minutes=redaction),
                            e.ts + timedelta(minutes=suivi),
                            e.scores or {(None, None, None): 1.0}, e.extends))
    return out


def _bornes(intervals, params):
    """Points de découpe : extrémités des intervalles + frontières jour/plage ouvrée."""
    pts = set()
    for iv in intervals:
        pts.add(iv.debut)
        pts.add(iv.fin)
    if not pts:
        return []
    lo, hi = min(pts), max(pts)
    jour = lo.replace(hour=0, minute=0, second=0, microsecond=0)
    while jour <= hi:
        for h in (0, params["work_start_hour"], params["work_end_hour"]):
            pts.add(jour.replace(hour=h))
        jour += timedelta(days=1)
    return sorted(p for p in pts if lo <= p <= hi)


def est_ouvre(ts, params):
    """Plage refacturable : lundi→vendredi, dans les heures ouvrées déclarées."""
    return (ts.weekday() < 5
            and params["work_start_hour"] <= ts.hour < params["work_end_hour"])


def allocate(intervals, params=None):
    """Répartit le temps réel sur les cibles. Retourne (alloc, periodes, totaux).

    - `alloc`   : {(jour, ouvre, (entity, project, rm)) : minutes}
    - `periodes`: {jour : [(debut, fin), …]} — les périodes de travail effectives
    - `totaux`  : {jour : minutes} — la MESURE DE L'UNION

    Invariant : `sum(alloc) == sum(totaux)`. Le temps d'un instant couvert par
    plusieurs intervalles est réparti entre eux, jamais additionné — c'est ce qui
    interdit structurellement de compter deux fois le même moment.

    Les intervalles `extends=False` (traces d'agent) ne créent pas de temps : ils
    ne participent qu'à la répartition des segments déjà couverts par une trace
    humaine.
    """
    p = {**DEFAULTS, **(params or {})}
    alloc = collections.defaultdict(float)
    totaux = collections.Counter()
    periodes = collections.defaultdict(list)
    if not intervals:
        return dict(alloc), dict(periodes), dict(totaux)

    ivs = sorted(intervals, key=lambda x: x.debut)
    debuts = [iv.debut for iv in ivs]
    bornes = _bornes(ivs, p)
    for a, b in zip(bornes, bornes[1:]):
        duree = (b - a).total_seconds() / 60
        if duree <= 0:
            continue
        actifs = [iv for iv in ivs[:bisect.bisect_right(debuts, a)] if iv.fin > a]
        if not actifs or not any(iv.extends for iv in actifs):
            continue                      # hors période de travail : rien à compter
        jour = a.strftime("%Y-%m-%d")
        ouvre = est_ouvre(a, p)
        totaux[jour] += duree
        if periodes[jour] and periodes[jour][-1][1] == a:
            periodes[jour][-1] = (periodes[jour][-1][0], b)
        else:
            periodes[jour].append((a, b))
        poids_total = sum(sum(iv.scores.values()) for iv in actifs)
        if poids_total <= 0:
            continue
        for iv in actifs:
            for cible, poids in iv.scores.items():
                alloc[(jour, ouvre, cible)] += duree * poids / poids_total
    return dict(alloc), dict(periodes), dict(totaux)


# ── Règles métier ────────────────────────────────────────────────────────────

@dataclass
class Regles:
    """Paramètres métier — arbitrages du CDC § 5bis, 5quater et 11."""
    types: dict = field(default_factory=dict)        # entité → client | self | product
    perso: set = field(default_factory=set)          # entités perso : jamais refacturées
    absences: list = field(default_factory=list)     # [(date_debut, date_fin, motif)]
    cles_multi: dict = field(default_factory=dict)   # entité/projet → [(client, poids)]
    seuil_client_min: float = DEFAULTS["client_threshold_min"]

    def est_client(self, entity):
        return self.types.get(entity) == "client"

    def dans_le_pot(self, entity):
        """Transversal refacturable : ni client, ni perso (PM, infra, produits)."""
        return entity not in self.perso and not self.est_client(entity)

    def absence(self, jour):
        d = date.fromisoformat(jour)
        for debut, fin, motif in self.absences:
            if debut <= d <= fin:
                return motif
        return None


def eclater_cles_multi(alloc, regles):
    """Applique les clés multi-clients (SFY : pisceen 70 / calicote 30).

    Un travail qui sert plusieurs clients se répartit selon la clé déclarée sur
    le projet (`used_by_clients[]`), au lieu de rester sur une entité qui ne
    correspond à aucune facture. Conservatif : le total est inchangé.
    """
    out = collections.defaultdict(float)
    for (jour, ouvre, cible), minutes in alloc.items():
        ent, proj, rm = cible
        cle = regles.cles_multi.get(f"{ent}/{proj}") or regles.cles_multi.get(ent)
        if not cle:
            out[(jour, ouvre, cible)] += minutes
            continue
        total = sum(poids for _c, poids in cle) or 1
        for client, poids in cle:
            out[(jour, ouvre, (client, proj, rm))] += minutes * poids / total
    return dict(out)


#: Les trois destins possibles du temps transversal (CDC § 5bis).
REFACTURE, INTERNE, NON_COMPTE = "refacture", "interne", "non_compte"


def repartir_transversal(alloc, regles, params=None):
    """Décide, jour par jour, du sort du temps transversal (PM, infra, produits).

    Trois destins, jamais un seul :

    - **refacturé** aux clients du jour, au prorata de leur poids — mais
      seulement en semaine, en heures ouvrées, et si la journée compte assez de
      travail client ;
    - **interne** — le soir, la nuit, le week-end d'une journée cliente : à la
      charge d'iProspective ;
    - **non compté** — une journée passée surtout sur du perso ou de l'interne :
      ce temps n'a de raison d'être ni facturé, ni même noté. C'est une
      PROPOSITION, réintégrable ; jamais une suppression silencieuse.

    Le total est conservé : ce qui sort du pot arrive chez les clients ou dans
    l'écarté, jamais dans le vide.
    """
    p = {**DEFAULTS, **(params or {})}
    par_jour = collections.defaultdict(lambda: {"pot_ouvre": 0.0, "pot_hors": 0.0,
                                                "clients": collections.Counter(),
                                                "lignes": []})
    for (jour, ouvre, cible), minutes in alloc.items():
        ent = cible[0]
        d = par_jour[jour]
        d["lignes"].append((ouvre, cible, minutes))
        if regles.est_client(ent):
            d["clients"][ent] += minutes
        elif regles.dans_le_pot(ent):
            d["pot_ouvre" if ouvre else "pot_hors"] += minutes

    final = collections.defaultdict(float)
    ecarte = collections.defaultdict(float)
    journal = {}
    for jour, d in par_jour.items():
        client_total = sum(d["clients"].values())
        motif_absence = regles.absence(jour)
        journee_cliente = client_total >= regles.seuil_client_min
        pot_total = d["pot_ouvre"] + d["pot_hors"]

        if motif_absence:
            # Absence déclarée : TOUT est proposé non compté — y compris le temps
            # client, qui est signalé à part (`alerte_absence`) au lieu d'être
            # supprimé en silence. « Je n'étais pas là » et « rien n'a été fait »
            # ne sont pas la même chose : c'est à l'humain de trancher.
            for _ouvre, cible, minutes in d["lignes"]:
                ecarte[(jour, cible)] += minutes
            journal[jour] = {
                "destin": NON_COMPTE, "cle": {}, "absence": motif_absence,
                "client_h": client_total / 60, "pot_ouvre_h": d["pot_ouvre"] / 60,
                "pot_hors_h": d["pot_hors"] / 60,
                "alerte_absence": client_total > 0,
            }
            continue
        if not journee_cliente:
            destin, cle = NON_COMPTE, {}
        elif d["pot_ouvre"] > 0:
            destin = REFACTURE
            cle = {c: m / client_total for c, m in d["clients"].items()}
        else:
            destin, cle = INTERNE, {}

        # Les lignes CLIENTES portent les bons couples projet/ticket : le temps
        # transversal refacturé les GONFLE au prorata, au lieu de créer des
        # lignes bâtardes (un ticket du projet PM crédité à un client n'existe
        # pas dans Redmine — un ticket appartient à un seul projet).
        lignes_clientes = [(cible, m) for ouvre, cible, m in d["lignes"]
                           if regles.est_client(cible[0])]
        pot_a_repartir = 0.0
        for ouvre, cible, minutes in d["lignes"]:
            ent = cible[0]
            if regles.est_client(ent) or not regles.dans_le_pot(ent):
                final[(jour, cible)] += minutes          # client et perso : intouchés
                continue
            if destin == NON_COMPTE:
                ecarte[(jour, cible)] += minutes
            elif ouvre and destin == REFACTURE:
                pot_a_repartir += minutes
            else:
                final[(jour, cible)] += minutes          # soir/nuit/week-end : interne
        if pot_a_repartir and client_total > 0:
            for cible, m in lignes_clientes:
                final[(jour, cible)] += pot_a_repartir * m / client_total
        journal[jour] = {
            "destin": destin, "cle": cle, "absence": motif_absence,
            "client_h": client_total / 60, "pot_ouvre_h": d["pot_ouvre"] / 60,
            "pot_hors_h": d["pot_hors"] / 60,
            "alerte_absence": bool(motif_absence and client_total > 0),
        }
    return dict(final), dict(ecarte), journal


def deduire_saisies(final, saisies, cle_ticket=True):
    """Retranche ce qui est DÉJÀ noté à la main dans Redmine.

    Le hors-agent (réunions, téléphone) est invisible aux traces mais présent
    dans les saisies manuelles : sans cette déduction, il serait compté deux
    fois. Les « Tick IA » de l'agent ne sont pas concernés — ce sont des heures
    machine, pas humaines : l'appelant ne passe ici que les saisies humaines.

    `saisies` : [{"jour": "2026-07-01", "minutes": 45, "rm": "2304"|None,
                  "entity": "matnat"|None}]
    """
    reste = dict(final)
    deduit = []
    for s in saisies:
        jour, minutes = s["jour"], float(s["minutes"])
        if minutes <= 0:
            continue
        # Ordre de priorité, sans jamais exclure : le ticket exact d'abord, puis
        # la même entité, puis le reste de la journée. Une saisie manuelle plus
        # grosse que la ligne visée DOIT déborder — sinon le temps déjà noté
        # serait re-proposé ailleurs le même jour, et compté deux fois.
        jour_lignes = [k for k in reste if k[0] == jour]

        def priorite(k):
            exact = cle_ticket and s.get("rm") and k[1][2] == str(s["rm"])
            meme_entite = s.get("entity") and k[1][0] == s["entity"]
            return (0 if exact else (1 if meme_entite else 2), -reste[k])

        candidats = sorted(jour_lignes, key=priorite)
        for k in candidats:
            if minutes <= 0:
                break
            pris = min(reste[k], minutes)
            reste[k] -= pris
            minutes -= pris
            deduit.append((k, pris, s))
        if reste:
            reste = {k: v for k, v in reste.items() if v > 1e-9}
    return reste, deduit


def quantifier(lignes, quantum=None):
    """Arrondit à la tranche, sans dérive : méthode des plus forts restes.

    La somme des lignes arrondies égale l'arrondi du total — on ne gagne ni ne
    perd de minutes en arrondissant.
    """
    quantum = quantum or DEFAULTS["quantum_min"]
    total = sum(lignes.values())
    if total <= 0:
        return {}
    cible = round(total / quantum)
    if cible <= 0:
        return {}
    parts = {k: v / total * cible for k, v in lignes.items()}
    base = {k: int(v) for k, v in parts.items()}
    restant = cible - sum(base.values())
    for k, _ in sorted(parts.items(), key=lambda kv: -(kv[1] - int(kv[1]))):
        if restant <= 0:
            break
        base[k] += 1
        restant -= 1
    return {k: v * quantum for k, v in base.items() if v > 0}


# ── Configuration déclarée ───────────────────────────────────────────────────

def charger_config(chemin=None, cfg=None):
    """Lit `timesheet.yml` (sources, correspondances de chemins, absences, clés).

    Les sources sont DÉCLARÉES : le travail ne se fait pas que sur un poste
    (hôte et conteneur partagent les transcripts, un compte distant en porte
    d'autres). Rien n'est deviné — un gisement non déclaré reste invisible, et
    c'est assumé.
    """
    if yaml is None:
        return {}
    if chemin is None and cfg is not None:
        chemin = Path(cfg.pm_dir) / "timesheet.yml"
    p = Path(chemin) if chemin else None
    if not p or not p.is_file():
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def regles_depuis_config(conf, cfg):
    """Construit les `Regles` : typologie PM + arbitrages déclarés."""
    types = {}
    for ent, _ in cfg.iter_entities():
        try:
            types[ent] = (cfg.client_meta(ent) or {}).get("type")
        except Exception:
            types[ent] = None
    absences = []
    for a in conf.get("absences", []) or []:
        try:
            absences.append((date.fromisoformat(str(a["du"])),
                             date.fromisoformat(str(a["au"])),
                             a.get("motif", "absence")))
        except (KeyError, ValueError):
            continue
    cles = {}
    for cible, parts in (conf.get("multi_client") or {}).items():
        norm = []
        for item in parts:
            if isinstance(item, dict):
                norm.append((item.get("client"), float(item.get("weight", 1))))
            else:
                norm.append((item[0], float(item[1])))
        cles[cible] = [x for x in norm if x[0]]
    return Regles(
        types=types,
        perso=set(conf.get("perso", []) or []),
        absences=absences,
        cles_multi=cles,
        seuil_client_min=float(conf.get("client_threshold_min",
                                        DEFAULTS["client_threshold_min"])),
    )


# ── Rendu ────────────────────────────────────────────────────────────────────

def _hm(minutes):
    """45.0 → '0h45'."""
    m = int(round(minutes))
    return f"{m // 60}h{m % 60:02d}"


def rendre_markdown(final, ecarte, journal, periodes, totaux, regles, mois,
                    deduit=None, quantum=None, resolver=None):
    """Compte rendu lisible — c'est la pièce que l'humain relit et amende."""
    quantum = quantum or DEFAULTS["quantum_min"]
    L = [f"# Feuille de temps {mois}", ""]
    total_final = sum(final.values())
    total_ecarte = sum(ecarte.values())
    L += [f"- temps mesuré : **{_hm(sum(totaux.values()))}** sur {len(totaux)} journées",
          f"- temps proposé à la saisie : **{_hm(total_final)}**",
          f"- écarté (journées non clientes, absences) : {_hm(total_ecarte)}", ""]

    par_client = collections.Counter()
    for (jour, cible), m in final.items():
        par_client[cible[0] or "(non rattaché)"] += m
    L += ["## Répartition par client", "", "| client | temps | part |", "|---|---|---|"]
    for ent, m in par_client.most_common():
        part = 100 * m / total_final if total_final else 0
        L.append(f"| {ent} | {_hm(m)} | {part:.1f} % |")
    L.append("")

    # ── Synthèse par projet : ce qui a été fait, et pour qui ────────────────
    par_projet = collections.defaultdict(lambda: {"total": 0.0,
                                                  "tickets": collections.Counter()})
    for (jour, cible), m in final.items():
        ent, proj, rm = cible
        bloc = par_projet[(ent or "(non rattaché)", proj or "—")]
        bloc["total"] += m
        bloc["tickets"][rm] += m
    L += ["## Synthèse par projet", ""]
    dernier_client = None
    poids_client = collections.Counter()
    for (e, _p), b in par_projet.items():
        poids_client[e] += b["total"]
    # clients par poids décroissant, le non-rattaché en dernier
    ordre = sorted(par_projet.items(),
                   key=lambda kv: (kv[0][0] == "(non rattaché)",
                                   -poids_client[kv[0][0]], kv[0][0], -kv[1]["total"]))
    for (ent, proj), bloc in ordre:
        if bloc["total"] < 1:
            continue
        if ent != dernier_client:
            L += ["", f"### {ent} — {_hm(poids_client[ent])}", ""]
            dernier_client = ent
        L.append(f"**{proj}** — {_hm(bloc['total'])}")
        L.append("")
        principaux = [(rm, v) for rm, v in bloc["tickets"].most_common() if rm]
        for rm, v in principaux[:8]:
            titre = resolver.titre(rm) if resolver else ""
            if len(titre) > 88:
                titre = titre[:87].rstrip() + "…"
            L.append(f"- RM{rm} — {_hm(v)}" + (f" — {titre}" if titre else ""))
        divers = sum(v for rm, v in bloc["tickets"].items() if not rm)
        reste = sum(v for rm, v in principaux[8:])
        n_autres = len(principaux[8:]) + (1 if divers else 0)
        if n_autres:
            quoi = "tickets secondaires" if len(principaux) > 8 else "travail non ticketé"
            if len(principaux) > 8 and divers:
                quoi = "tickets secondaires et travail non ticketé"
            L.append(f"- *{_hm(divers + reste)} sur {n_autres} autre"
                     f"{'s' if n_autres > 1 else ''} poste"
                     f"{'s' if n_autres > 1 else ''} — {quoi}*")
        L.append("")

    alertes = [j for j, d in sorted(journal.items()) if d.get("alerte_absence")]
    if alertes:
        L += ["## ⚠ À trancher — activité cliente pendant une absence", ""]
        for j in alertes:
            d = journal[j]
            L.append(f"- **{j}** ({d['absence']}) : {_hm(d['client_h'] * 60)} de travail "
                     f"client détecté — écarté par défaut, à réintégrer si c'est du réel.")
        L.append("")

    L += ["## Journées", ""]
    for jour in sorted(totaux):
        d = journal.get(jour, {})
        per = " · ".join(f"{a:%H:%M}–{b:%H:%M}" for a, b in periodes.get(jour, []))
        etiquette = {REFACTURE: "transversal refacturé",
                     INTERNE: "transversal interne",
                     NON_COMPTE: "journée non cliente → transversal écarté"}.get(
                         d.get("destin"), "")
        L.append(f"### {jour} — {_hm(totaux[jour])}")
        if d.get("absence"):
            L.append(f"*{d['absence']}*")
        L.append(f"périodes : {per}" if per else "")
        if d.get("destin") == REFACTURE and d.get("cle"):
            cle = ", ".join(f"{c} {100*v:.0f} %" for c, v in
                            sorted(d["cle"].items(), key=lambda kv: -kv[1]))
            L.append(f"clé du jour : {cle}")
        elif etiquette:
            L.append(etiquette)
        lignes = {k: v for k, v in final.items() if k[0] == jour}
        arrondi = quantifier({k: v for k, v in lignes.items()}, quantum)
        L += ["", "| client | projet | ticket | calculé | à noter |", "|---|---|---|---|---|"]
        for k, v in sorted(lignes.items(), key=lambda kv: -kv[1]):
            ent, proj, rm = k[1]
            note = arrondi.get(k, 0)
            L.append(f"| {ent or '—'} | {proj or '—'} | "
                     f"{'RM' + rm if rm else '—'} | {_hm(v)} | "
                     f"{_hm(note) if note else '—'} |")
        L.append("")
    return "\n".join(L)


def proposition(final, journal, quantum=None, meta=None):
    """Structure YAML amendable : la source de vérité de l'étape de validation.

    Elle est relue telle quelle par `--apply` : ce que l'humain a corrigé est ce
    qui part dans Redmine, sans recalcul.
    """
    quantum = quantum or DEFAULTS["quantum_min"]
    par_jour = collections.defaultdict(dict)
    for (jour, cible), m in final.items():
        par_jour[jour][cible] = m
    lignes = []
    for jour in sorted(par_jour):
        arrondi = quantifier({(jour, k): v for k, v in par_jour[jour].items()}, quantum)
        for (j, cible), minutes in sorted(arrondi.items(), key=lambda kv: -kv[1]):
            ent, proj, rm = cible
            lignes.append({
                "jour": j, "client": ent, "projet": proj,
                "ticket": int(rm) if rm and str(rm).isdigit() else None,
                "minutes": int(minutes), "valide": True,
            })
    return {"meta": meta or {}, "quantum_min": quantum,
            "journees": {j: {"destin": d.get("destin"), "absence": d.get("absence"),
                             "alerte": bool(d.get("alerte_absence"))}
                         for j, d in sorted(journal.items())},
            "lignes": lignes}
