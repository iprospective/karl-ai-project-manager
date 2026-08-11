#!/usr/bin/env python3
"""Suivi par session des tickets/tâches ouverts et de leur avancement.

Store léger keyé par session Claude Code ($CLAUDE_CODE_SESSION_ID) :
  - source de vérité : ~/.claude/session-worklogs/<session-id>.json
  - rendu lisible     : ~/.claude/session-worklogs/<session-id>.md (régénéré à chaque mutation)

But : répondre cheap à « il reste quoi à faire dans cette session » sans rescanner
le contexte. Les scripts PM (`pm-task-add`/`-status-update`/`-link`, hook post-commit)
upsertent au fil de l'eau via `pm_session_hook` ; `show` rapporte.

Deux niveaux de rendu (RM2068) :
  - **snapshot** (mutations) : le `.md` écrit à chaque `add`/`set` reflète l'état STOCKÉ
    — pas de résolution externe, donc effet de bord cheap pour les scripts PM ;
  - **live** (`show`/`refresh`) : résout le statut COURANT de chaque ticket depuis le
    frontmatter de sa tâche (`cfg.find_task`) et **signale la dérive** vs le statut
    d'ouverture — ainsi « il reste quoi » reste fidèle même quand une AUTRE session a
    fait avancer/fermer un ticket entre-temps.

Volets RM1875 (manifest déclaratif) + RM2068 (harvest auto + statut live).
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_output import out as pmout
from pm_lock import atomic_write  # écriture atomique (T7/RM2551)
try:
    import pm_session  # registre seq / branches / worktrees (RM2034)
except Exception:
    pm_session = None

# Surchargeable pour les tests : sans ça, éprouver le canal de notifications
# écrirait dans le worklog RÉEL de la session en cours.
# Transcripts claude — même résolution que le cockpit et pm-decisions.
CLAUDE_STORES = [pathlib.Path(x).expanduser()
                 for x in os.environ.get(
                     "PM_CLAUDE_STORES", os.path.expanduser("~/.claude/projects")).split(":")
                 if x.strip()]

WORKLOG_DIR = os.path.expanduser(
    os.environ.get("PM_SESSION_WORKLOG_DIR") or "~/.claude/session-worklogs")

# statuts considérés comme terminés (filtrés hors du « reste à faire »)
DONE = {"fait", "done", "ferme", "fermé", "livré", "livre", "closed", "résolu", "resolu"}
# statuts considérés bloqués/en attente externe (affichés à part)
WAITING = {"en_attente", "attente", "bloqué", "bloque", "blocked", "waiting",
           "à_valider", "a_valider", "a_tester_demandeur", "a_tester_dev", "en_pause"}

RM_RE = re.compile(r"(?i)^RM(\d+)$")

# ─── canal « notifications importantes » (RM2466 volet 1) ────────────────────
# Un incident notable finissait au mieux dans une phrase de réponse de l'agent,
# et se perdait au premier défilement de la conversation. Ce canal le retient au
# niveau SESSION, à côté des items de travail mais distinct d'eux.
NOTIFY_LEVELS = ("info", "warn", "critical")
NOTIFY_ICON = {"info": "ℹ️", "warn": "⚠️", "critical": "🔴"}
# Typologie issue de RM2466. `kind` reste libre, mais nommer les cas que NORMS
# impose de consigner évite que chaque agent invente son propre vocabulaire.
NOTIFY_KINDS = {
    "secret": "secret exposé (transcript, log, capture) — rotation à envisager",
    "refus": "action refusée / permission manquante",
    "garde-fou": "garde-fou déclenché (branche protégée, périmètre projet, worktree)",
    "outillage": "outillage PM en défaut (un script ne fait pas ce qu'il annonce)",
    "decision": "décision du demandeur attendue — l'avancement est bloqué",
    "autre": "autre événement notable",
}
NOTIFY_KEEP = 100          # garde-fou de taille du canal


# ─── registre des demandes (RM2621) ──────────────────────────────────────────
# Une demande formulée en séance n'existait que dans le fil : non ticketée
# sur-le-champ, elle disparaissait au premier défilement. Le worklog ne
# connaissait que les tickets — c'est-à-dire ce qui avait DÉJÀ été formalisé.
REQUEST_STATES = ("nouveau", "ticketee", "repondu", "annulee", "fusionnee",
                  "non_demande")
# Statuts qui sortent une demande du « reste à traiter » : elle a trouvé sa
# suite. `nouveau` est le seul qui appelle encore une décision.
# RM2635 : `non_demande` en fait partie, mais il ne dit PAS la même chose que
# les autres. Ranger un collage de console dans `annulee` serait un mensonge de
# classement — personne n'a rien annulé. Il lui faut son propre état, sinon le
# tri se fait au prix d'une donnée fausse.
REQUEST_DONE = ("ticketee", "repondu", "annulee", "fusionnee", "non_demande")
REQUEST_ICON = {"nouveau": "🆕", "ticketee": "🎫", "repondu": "💬",
                "annulee": "🚫", "fusionnee": "⛓", "non_demande": "🗒"}


def request_open(requests):
    """Demandes qui appellent encore une décision. Pure."""
    return [r for r in (requests or []) if r.get("status", "nouveau") not in REQUEST_DONE]


def request_count_by_state(requests):
    """Décompte par statut. Pure — sert au worklog à afficher les non-demandes
    à part plutôt que fondues dans « traité »."""
    out = {}
    for r in (requests or []):
        st = r.get("status", "nouveau")
        out[st] = out.get(st, 0) + 1
    return out


def request_apply(requests, ref, status, ticket=None, note=None, merged_into=None):
    """Change le statut d'une demande. Rend (liste, trouvée). Pure.

    `ref` est le numéro d'ordre affiché (1-based) : c'est ce que l'agent a sous
    les yeux dans `show`, pas un identifiant interne qu'il faudrait retenir."""
    out = [dict(r) for r in (requests or [])]
    try:
        i = int(str(ref)) - 1
    except (TypeError, ValueError):
        return out, False
    if i < 0 or i >= len(out):
        return out, False
    if status:
        out[i]["status"] = status
    if ticket:
        out[i]["ticket"] = str(ticket)
    if note is not None:
        out[i]["note"] = note
    if merged_into:
        out[i]["merged_into"] = str(merged_into)
    return out, True


def notify_trim(notes, keep=NOTIFY_KEEP):
    """Rogne les plus anciennes au-delà de `keep`, mais JAMAIS une `critical` :
    un secret exposé ne doit pas disparaître parce que la session a été bavarde.
    Pure (testable)."""
    notes = list(notes or [])
    if len(notes) <= keep:
        return notes
    crit = [n for n in notes if n.get("level") == "critical"]
    rest = [n for n in notes if n.get("level") != "critical"]
    room = max(0, keep - len(crit))
    kept = crit + (rest[-room:] if room else [])
    # ordre chronologique conservé, quel que soit le tri interne ci-dessus
    return [n for n in notes if n in kept]


# ─── canal « merge requests » (RM2583) ───────────────────────────────────────
# Une session ouvre plusieurs MR au fil du travail (branche → dev, puis promotion
# dev → main). Rien ne les récapitulait : une MR oubliée ne se voyait qu'au
# prochain conflit, ou quand le core update ne contenait pas ce qu'on attendait.
MR_OPEN_STATES = ("opened", "open", "reopened")


def mr_upsert(mrs, entry):
    """Ajoute ou met à jour une MR dans le canal, identifiée par (url) ou (iid,
    repo). Une MR ne se duplique pas quand elle change d'état. Pure."""
    mrs = [dict(m) for m in (mrs or [])]
    for m in mrs:
        same_url = entry.get("url") and m.get("url") == entry["url"]
        same_iid = (entry.get("iid") and m.get("iid") == entry["iid"]
                    and m.get("repo") == entry.get("repo"))
        if same_url or same_iid:
            m.update({k: v for k, v in entry.items() if v is not None})
            return mrs
    mrs.append({k: v for k, v in entry.items() if v is not None})
    return mrs


def mr_pending(mrs):
    """Les MR qui restent à merger. Une MR mergée ou fermée SORT de cette liste
    sans sortir du store : on veut pouvoir dire ce que la session a produit. Pure."""
    return [m for m in (mrs or []) if (m.get("state") or "opened") in MR_OPEN_STATES]


def notify_level_for(kind, level=None):
    """Niveau d'une notification : explicite, sinon déduit du type. Un secret
    exposé est critique par nature — ne pas compter sur l'agent pour y penser."""
    if level:
        return level
    return "critical" if kind == "secret" else "warn"


def now():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")


def session_id(override=None):
    sid = override or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        sid = "default"
    return sid


def paths(sid):
    return (os.path.join(WORKLOG_DIR, sid + ".json"),
            os.path.join(WORKLOG_DIR, sid + ".md"))


def load(sid):
    jpath, _ = paths(sid)
    if os.path.exists(jpath):
        with open(jpath, encoding="utf-8") as f:
            return json.load(f)
    return {"session_id": sid, "title": None, "updated": now(), "items": []}


def save(data, live=None):
    """Persiste le JSON + régénère le `.md`.

    `live` (optionnel) = map ref→{status,title} : si fourni, le `.md` est rendu
    avec les statuts COURANTS (utilisé par `refresh`). Sinon rendu snapshot (cheap),
    pour que l'effet de bord des scripts PM ne déclenche aucune résolution externe.
    """
    os.makedirs(WORKLOG_DIR, exist_ok=True)
    if live:
        # cache des documents (refs/outputs) pour les rendus snapshot ultérieurs
        docs = {ref: lv["docs"] for ref, lv in live.items() if lv.get("docs")}
        if docs:
            data["docs"] = docs
    data["updated"] = now()
    jpath, mpath = paths(data["session_id"])
    # T7 : écriture atomique (temp + os.replace). Worklog per-session/per-user → pas de
    # concurrence (donc pas de verrou), mais évite un fichier à moitié écrit au crash.
    atomic_write(jpath, json.dumps(data, ensure_ascii=False, indent=2))
    atomic_write(mpath, render_md(data, live=live))


def find(data, ref):
    ref_l = ref.lower()
    for it in data["items"]:
        if it["ref"].lower() == ref_l:
            return it
    # match partiel (ex: "1886" matche "RM1886")
    for it in data["items"]:
        if ref_l in it["ref"].lower():
            return it
    return None


# ─── résolution du statut live (RM2068) ──────────────────────────────────────

def _read_fm_field(path, field):
    """Lit un champ scalaire du frontmatter YAML d'un .md, sans charger PyYAML
    (cheap : lecture ligne à ligne, on s'arrête à la fin du frontmatter)."""
    try:
        with open(path, encoding="utf-8") as f:
            in_fm = False
            for line in f:
                s = line.rstrip("\n")
                if s.strip() == "---":
                    if in_fm:
                        break
                    in_fm = True
                    continue
                if in_fm and s.startswith(field + ":"):
                    return s[len(field) + 1:].strip().strip("'\"")
    except OSError:
        return None
    return None


def _read_fm_lists(path, fields):
    """Lit des champs LISTE du frontmatter (`refs:`, `outputs:`) sans PyYAML.
    Retourne {field: [valeurs]} ; `field: []` ou champ absent → liste vide."""
    res = {f: [] for f in fields}
    cur = None
    try:
        with open(path, encoding="utf-8") as f:
            in_fm = False
            for line in f:
                s = line.rstrip("\n")
                if s.strip() == "---":
                    if in_fm:
                        break
                    in_fm = True
                    continue
                if not in_fm:
                    continue
                if cur is not None and s.startswith("- "):
                    res[cur].append(s[2:].strip().strip("'\""))
                    continue
                cur = None
                for fld in fields:
                    if s == fld + ":":
                        cur = fld
                    elif s.startswith(fld + ":"):  # forme inline `refs: []`
                        cur = None
    except OSError:
        pass
    return res


def resolve_live(items):
    """map ref→{status,title} depuis le frontmatter des tâches (best-effort).

    Ne résout que les refs de forme `RM<id>` ; toute erreur (config illisible,
    tâche introuvable) est silencieuse et l'item retombe sur son statut stocké."""
    live = {}
    rm_refs = [(it["ref"], int(RM_RE.match(it["ref"]).group(1)))
               for it in items if RM_RE.match(it["ref"])]
    if not rm_refs:
        return live
    try:
        from pm_paths import PMConfig
        cfg = PMConfig.load()
    except Exception:
        return live
    for ref, rm_id in rm_refs:
        try:
            p = cfg.find_task(rm_id)
        except Exception:
            p = None
        if not p:
            continue
        st = _read_fm_field(p, "status")
        if st:
            lists = _read_fm_lists(p, ("refs", "outputs"))
            docs = ([[d, "ref"] for d in lists["refs"]]
                    + [[d, "output"] for d in lists["outputs"]])
            live[ref] = {"status": st, "title": _read_fm_field(p, "title"),
                         "docs": docs}
    return live


def is_done(status):
    return (status or "").lower() in DONE


def is_waiting(status):
    return (status or "").lower() in WAITING


def eff_status(it, live):
    """Statut effectif : courant (frontmatter) s'il est résolu, sinon stocké."""
    lv = (live or {}).get(it["ref"])
    return lv["status"] if lv else it.get("status", "à_faire")


# ─── rendu ───────────────────────────────────────────────────────────────────

def render_md(data, live=None):
    out = ["# Worklog session — " + data["session_id"]]
    if data.get("title"):
        out.append("**" + data["title"] + "**")
    suffix = " · live" if live else ""
    out.append("_maj : " + data["updated"] + suffix + "_\n")

    # RM2583 : ce qui reste à merger — juste après les incidents, avant le travail
    pending = mr_pending(data.get("mrs"))
    if pending:
        out.append("## 🔀 MR à merger (%d)" % len(pending))
        for m in pending:
            ref = (" **%s**" % m["ref"]) if m.get("ref") else ""
            cible = (" → `%s`" % m["target"]) if m.get("target") else ""
            url = (" %s" % m["url"]) if m.get("url") else ""
            out.append("- `!%s`%s%s%s" % (m.get("iid", "?"), ref, cible, url))
        out.append("")

    # RM2621 : ce qui n'est pas encore ticketé passe en tête — c'est ce qui se
    # perd, les tickets ont déjà leur existence propre.
    ouvertes = request_open(data.get("requests"))
    if ouvertes:
        # RM2635 : le décompte des écartées reste visible. Sans lui, l'écart
        # entre le registre et cette liste ressemblerait à une perte.
        par_etat = request_count_by_state(data.get("requests"))
        ecartees = par_etat.get("non_demande", 0)
        out.append("## 📥 Demandes à traiter (%d)%s" % (
            len(ouvertes),
            (" _· %d écartée(s) : accusés, collages_" % ecartees) if ecartees else ""))
        for r in ouvertes:
            n = (data.get("requests") or []).index(r) + 1
            out.append("- `#%d` %s _(%s)_" % (n, r.get("text", ""), r.get("ts", "")))
        out.append("")

    # RM2466 : les incidents passent AVANT le travail — c'est ce qu'on perd le
    # plus vite, et ce qui coûte le plus cher quand on l'a perdu.
    notes = data.get("notifications") or []
    if notes:
        out.append("## 🔔 Notifications importantes (%d)" % len(notes))
        for n in notes[-20:]:
            ref = (" **%s**" % n["ref"]) if n.get("ref") else ""
            kind = (" `%s`" % n["kind"]) if n.get("kind") and n["kind"] != "autre" else ""
            out.append("- %s `%s`%s%s — %s _(%s)_" % (
                NOTIFY_ICON.get(n.get("level"), "•"), n.get("level", "?"), kind, ref,
                n.get("message", ""), n.get("ts", "")))
        if len(notes) > 20:
            out.append("_(%d plus anciennes — `pm-session-status.py notify --list`)_"
                       % (len(notes) - 20))
        out.append("")

    # Branches / worktrees ouverts par la session (RM2034). Lecture seule :
    # n'alloue pas de seq (affiché seulement si la session en a déjà un).
    rec = pm_session.current_record() if pm_session else None
    if rec:
        out.append("_session **s%s** (machine %s)_" % (rec.get("seq"), rec.get("machine")))
        if rec.get("branches"):
            out.append("\n## 🌿 Branches")
            out += ["- `%s`" % b for b in rec["branches"]]
        if rec.get("worktrees"):
            out.append("\n## 🗂️ Worktrees")
            out += ["- `%s`" % w for w in rec["worktrees"]]
        out.append("")

    # Documents des tickets de la session (refs[] + outputs[] du frontmatter,
    # RM2352) : résolution live si dispo, sinon cache du dernier rendu live.
    doc_lines, seen = [], set()
    for it in data["items"]:
        lv = (live or {}).get(it["ref"]) or {}
        entries = lv.get("docs")
        if entries is None:
            entries = (data.get("docs") or {}).get(it["ref"]) or []
        for path_, kind in entries:
            if (it["ref"], path_) not in seen:
                seen.add((it["ref"], path_))
                doc_lines.append("- **%s** · `%s` _(%s)_" % (it["ref"], path_, kind))
    if doc_lines:
        out.append("## 📄 Documents")
        out += doc_lines
        out.append("")

    todo, wait, done = [], [], []
    for it in data["items"]:
        st = eff_status(it, live)
        (done if is_done(st) else wait if is_waiting(st) else todo).append(it)

    def line(it):
        st = eff_status(it, live)
        lv = (live or {}).get(it["ref"])
        label = it.get("label") or (lv["title"] if lv and lv.get("title") else it["ref"])
        proj = (" _(%s)_" % it["project"]) if it.get("project") else ""
        # dérive : le statut courant diffère de celui d'ouverture dans la session
        opened = it.get("opened_status") or it.get("status")
        drift = ""
        if lv and opened and lv["status"].lower() != (opened or "").lower():
            drift = " — _ouvert `%s` → `%s` (ailleurs)_" % (opened, lv["status"])
        commit = (" · `%s`" % it["commit"]) if it.get("commit") else ""
        nxt = ("\n  → " + it["next"]) if it.get("next") else ""
        note = ("\n  ↳ " + it["note"]) if it.get("note") else ""
        return "- `[%s]` **%s** — %s%s%s%s%s%s" % (
            st, it["ref"], label, proj, drift, commit, nxt, note)

    out.append("## ⏳ Reste à faire")
    out += [line(i) for i in todo] or ["_(rien)_"]
    if wait:
        out.append("\n## ⏸️ En attente / bloqué")
        out += [line(i) for i in wait]
    out.append("\n## ✅ Fait")
    out += [line(i) for i in done] or ["_(rien)_"]
    return "\n".join(out) + "\n"


# ─── commandes ─────────────────────────────────────────────────────────────

def cmd_show(data, args):
    live = None if args.no_live else resolve_live(data["items"])
    sys.stdout.write(render_md(data, live=live))


def cmd_refresh(data, args):
    """Re-résout les statuts live et réécrit le `.md` (pour SessionStart/PreCompact).

    No-op si la session n'a pas (encore) de worklog : on ne crée pas de fichier vide
    à chaque démarrage de session."""
    jpath, _ = paths(data["session_id"])
    if not os.path.exists(jpath) or not data["items"]:
        return
    live = resolve_live(data["items"])
    save(data, live=live)
    pmout.op("worklog", extra="rafraîchi (%d item(s), statut live)" % len(data["items"]))


def cmd_add(data, args):
    it = find(data, args.ref)
    if it:
        # upsert : met à jour les champs fournis (sans toucher opened_status)
        if args.label:
            it["label"] = args.label
        if args.status:
            it["status"] = args.status
        if args.project:
            it["project"] = args.project
        if args.note is not None:
            it["note"] = args.note
        if args.next is not None:
            it["next"] = args.next
        if getattr(args, "commit", None):
            it["commit"] = args.commit
        it["ts"] = now()
        action = "mis à jour"
    else:
        st = args.status or "à_faire"
        data["items"].append({
            "id": (max([i.get("id", 0) for i in data["items"]], default=0) + 1),
            "ref": args.ref,
            "label": args.label or args.ref,
            "project": args.project,
            "status": st,
            "opened_status": st,          # statut au moment de l'ouverture (RM2068)
            "note": args.note or "",
            "next": args.next or "",
            "commit": getattr(args, "commit", None) or "",
            "ts": now(),
        })
        action = "ajouté"
    save(data)
    pmout.op("worklog", extra="%s %s" % (args.ref, action))
    pmout.info("  · %s" % paths(data["session_id"])[1])


def cmd_set(data, args):
    it = find(data, args.ref)
    if not it:
        pmout.fail("introuvable : %s" % args.ref)
    it["status"] = args.status
    if args.note is not None:
        it["note"] = args.note
    if getattr(args, "next", None) is not None:
        it["next"] = args.next
    it["ts"] = now()
    save(data)
    pmout.op("worklog", extra="%s → %s" % (it["ref"], it["status"]))
    pmout.info("  · %s" % paths(data["session_id"])[1])


def cmd_rm(data, args):
    before = len(data["items"])
    data["items"] = [i for i in data["items"] if i["ref"].lower() != args.ref.lower()]
    if len(data["items"]) == before:
        pmout.fail("introuvable : %s" % args.ref)
    save(data)
    pmout.op("worklog", extra="%s supprimé" % args.ref)


def cmd_title(data, args):
    data["title"] = args.title
    save(data)
    pmout.op("worklog", extra="titre : %s" % args.title)


# Messages qui ne sont pas des demandes : accusés de réception et relances. La
# liste sert UNIQUEMENT au contrôle d'exhaustivité, pour ne pas crier au loup —
# jamais à filtrer ce que l'agent enregistre. Un faux négatif ici ne cache rien :
# il fait juste monter le nombre attendu, donc le bruit de l'audit. C'est le
# faux POSITIF qui coûte : il escamote une vraie demande du décompte. En cas de
# doute, ne pas élargir.
REQUEST_ACK_RE = re.compile(
    r"\A(ok|oui|non|go|vas[- ]?y|continue|enchaine[sz]?|merci|parfait|super|"
    r"c'est bon|ca marche|ça marche|core update fait|fait|teste|/\w+)\b"
    r"[\s!.,…]*(enchaine[sz]?|go|continue|la suite)?[\s!.…]*\Z",
    re.I)

# RM2635 : les verdicts. « ça a l'air bon ! tous les accents passent » n'est pas
# une demande, mais l'expression anchorée ci-dessus ne l'attrape pas — un
# verdict se prolonge presque toujours d'une observation. On tolère donc une
# suite, à condition qu'elle ne demande rien.
REQUEST_VERDICT_RE = re.compile(
    r"\A([cç]?a (a l'air|semble) (bien|bon|ok)|c'est (bien|bon|ok|parfait)|"
    r"nickel|impeccable|bien vu|core update( ?\+ ?reload)? (fait|faits|ok))\b", re.I)
# Signaux qu'un message demande quelque chose. Sert de garde-fou dans les DEUX
# sens : il empêche de prendre un verdict prolongé d'une consigne pour un simple
# accusé, et il empêche de prendre pour un collage technique un message court
# qui cite une erreur en demandant de la corriger.
REQUEST_ASK_RE = re.compile(
    r"\?|\b(fais|fait[- ]le|ajoute|corrige|fix|répare|repare|mets?|change|"
    r"remplace|supprime|refais|relance|il faut|faudrait|ce serait bien|"
    r"peux[- ]tu|pourrais|merge|prends|étudie|etudie|chiffre|regarde|vérifie|"
    r"verifie|explique|montre)\b", re.I)

# Enveloppes qui ne viennent pas du demandeur : résumé de compaction réinjecté
# dans le fil, collage de console renvoyé à MA demande. Les compter comme des
# demandes fait gonfler le registre de choses qui n'appellent aucune décision —
# et un registre de 41 lignes dont 25 sont du bruit ne protège plus rien.
REQUEST_PASTE_HEAD_RE = re.compile(
    r"\A(this session is being continued|the summary below covers|"
    r"caveat: the messages below|<[a-z-]+>)", re.I)
REQUEST_PASTE_MARK_RE = re.compile(
    r"debugger eval code:|\bat [\w.$<>]+ \([^)]*:\d+:\d+\)|\"keyCode\"|"
    r"\"isComposing\"|console\.(log|error)\(|"
    r"Traceback \(most recent call last\)|npm ERR!|\w+\.(js|py|php):\d+:\d+", re.I)


def looks_like_paste(msg):
    """Vrai si le message est une enveloppe technique et non une demande. Pure.

    Deux marqueurs suffisent, MAIS jamais quand le message demande quelque
    chose : « corrige ce TypeError at boot (app.js:12:3) » en porte deux et
    reste une demande. Le faux négatif coûte une ligne à trier ; le faux
    positif escamote une demande — c'est tout l'inverse de ce qu'on veut."""
    m = str(msg or "")
    if REQUEST_PASTE_HEAD_RE.match(m):
        return True
    if REQUEST_ASK_RE.search(m):
        return False
    return len(REQUEST_PASTE_MARK_RE.findall(m)) >= 2


def request_is_noise(msg):
    """Rend "ack", "paste" ou None. Pure — source unique pour l'audit ET
    l'import, sinon l'audit réclamerait sans fin l'enregistrement de ce que
    l'import refuse de prendre."""
    m = " ".join(str(msg or "").split())
    if not m:
        return "ack"
    if REQUEST_ACK_RE.match(m):
        return "ack"
    if REQUEST_VERDICT_RE.match(m) and not REQUEST_ASK_RE.search(m):
        return "ack"
    if looks_like_paste(m):
        return "paste"
    return None


def transcript_user_messages(path):
    """Messages utilisateur d'un transcript claude (JSONL), hors enveloppes
    techniques. Pure quant au format ; lit un fichier."""
    out = []
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return out
    with fh:
        for line in fh:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if not isinstance(o, dict) or o.get("type") != "user" or o.get("isMeta"):
                continue
            c = (o.get("message") or {}).get("content")
            if isinstance(c, str):
                txt = c
            elif isinstance(c, list):
                txt = "\n".join(b.get("text", "") for b in c
                                 if isinstance(b, dict) and b.get("type") == "text")
            else:
                continue
            txt = " ".join(str(txt).split())
            if not txt or txt.startswith("<") or txt.startswith("Caveat"):
                continue
            out.append(txt)
    return out


def request_audit(messages, requests):
    """RM2621 : compare ce que le demandeur a écrit à ce qui a été enregistré.

    Ne juge PAS le contenu — il compte. Une règle NORMS réduit l'oubli, elle ne
    le supprime pas, et un oubli ne laisse aucune trace : ce comptage est ce qui
    transforme « je crois n'avoir rien oublié » en fait vérifiable. Pure."""
    msgs = [m for m in (messages or [])]
    bruit = [request_is_noise(m) for m in msgs]
    attendus = [m for m, b in zip(msgs, bruit) if not b]
    return {"messages": len(msgs), "acks": bruit.count("ack"),
            "pastes": bruit.count("paste"),
            "expected": len(attendus), "recorded": len(requests or []),
            "gap": max(0, len(attendus) - len(requests or [])),
            "samples": attendus[:40]}


def cmd_request(data, args):
    """RM2621 : enregistrer une demande, ou faire évoluer son statut."""
    reqs = data.get("requests") or []
    if args.list:
        if not reqs:
            pmout.info("aucune demande enregistrée dans cette session")
            return
        for i, r in enumerate(reqs, 1):
            st = r.get("status", "nouveau")
            sys.stdout.write("#%d [%s] %s%s — %s\n" % (
                i, st, REQUEST_ICON.get(st, ""),
                (" " + r["ticket"]) if r.get("ticket") else "", r.get("text", "")))
        return
    if args.audit:
        sid = data["session_id"]
        path = next((p for root in CLAUDE_STORES for p in root.glob(f"*/{sid}.jsonl")), None)
        if not path:
            pmout.fail("transcript introuvable pour la session %s" % sid)
        rep = request_audit(transcript_user_messages(path), reqs)
        sys.stdout.write(
            "messages du demandeur : %d (dont %d accusés de réception, "
            "%d collages/résumés)\n"
            "demandes enregistrées  : %d\n" % (rep["messages"], rep["acks"],
                                               rep["pastes"], rep["recorded"]))
        if rep["gap"]:
            sys.stdout.write("\n⚠ écart de %d : des demandes n'ont probablement pas été "
                             "enregistrées.\n  Messages à vérifier :\n" % rep["gap"])
            enregistres = {r.get("text", "")[:60] for r in reqs}
            for m in rep["samples"]:
                if m[:60] not in enregistres:
                    sys.stdout.write("   · %s\n" % m[:110])
        else:
            sys.stdout.write("\n✓ aucun écart détecté.\n")
        return
    if args.import_missing:
        # RATTRAPAGE, pas le mode normal : reprend du transcript les messages
        # absents du registre et les pose en « nouveau », à trier. Sert quand la
        # règle n'était pas encore en place — la capture courante reste
        # explicite, message par message.
        sid = data["session_id"]
        path = next((p for root in CLAUDE_STORES for p in root.glob(f"*/{sid}.jsonl")), None)
        if not path:
            pmout.fail("transcript introuvable pour la session %s" % sid)
        connus = {r.get("text", "")[:60] for r in reqs}
        ajout = 0
        for m in transcript_user_messages(path):
            if request_is_noise(m) or m[:60] in connus:
                continue
            reqs.append({"ts": now(), "text": " ".join(m.split())[:400],
                         "status": "nouveau", "note": "importée du transcript (rattrapage)"})
            connus.add(m[:60])
            ajout += 1
        data["requests"] = reqs
        save(data)
        pmout.op("worklog", extra="%d demande(s) importée(s) du transcript" % ajout)
        return
    if args.set:
        # `--set` porte le numéro affiché par `show` / `--list`
        reqs, ok = request_apply(reqs, args.set, args.status, args.ticket,
                                 args.note, args.merged_into)
        if not ok:
            pmout.fail("demande #%s introuvable (voir `request --list`)" % args.set)
        data["requests"] = reqs
        save(data)
        pmout.op("worklog", extra="demande #%s → %s" % (args.set, args.status or "màj"))
        return
    if not args.text:
        pmout.fail("texte requis (ou --list / --set)")
    reqs.append({"ts": now(), "text": " ".join(str(args.text).split())[:400],
                 "status": args.status or "nouveau",
                 **({"ticket": str(args.ticket)} if args.ticket else {}),
                 **({"note": args.note} if args.note else {})})
    data["requests"] = reqs
    save(data)
    pmout.op("worklog", extra="demande #%d enregistrée" % len(reqs))


def cmd_notify(data, args):
    """RM2466 volet 1 : consigner un événement notable au niveau session."""
    notes = data.get("notifications") or []
    if args.list:
        if not notes:
            pmout.info("aucune notification dans cette session")
            return
        for n in notes:
            tags = " ".join(x for x in (n.get("kind"), n.get("ref")) if x)
            sys.stdout.write("%s [%s] %s — %s\n" % (
                n.get("ts", ""), n.get("level", "?"), tags, n.get("message", "")))
        return
    if args.clear:
        # les `critical` ne partent qu'à la demande explicite : un secret exposé
        # ne s'acquitte pas d'un revers de main en vidant le canal.
        kept = [] if args.all else [n for n in notes if n.get("level") == "critical"]
        removed = len(notes) - len(kept)
        data["notifications"] = kept
        save(data)
        pmout.op("worklog", extra="%d notification(s) acquittée(s)%s" % (
            removed, "" if args.all else ", %d critique(s) conservée(s)" % len(kept)))
        return
    if not args.message:
        pmout.fail("message requis (ou --list / --clear)")
    kind = args.kind or "autre"
    note = {"ts": now(), "level": notify_level_for(kind, args.level), "kind": kind,
            "ref": args.ref, "message": args.message}
    data["notifications"] = notify_trim(notes + [note])
    save(data)
    pmout.op("worklog", extra="notification %s [%s] %s" % (
        NOTIFY_ICON.get(note["level"], "•"), note["level"], args.message[:60]))
    pmout.info("  · %s" % paths(data["session_id"])[1])


def cmd_mr(data, args):
    """RM2583 : refléter une MR ouverte / mergée / fermée dans le worklog."""
    if args.list:
        for m in (data.get("mrs") or []):
            sys.stdout.write("!%s [%s] %s %s %s\n" % (
                m.get("iid", "?"), m.get("state", "?"), m.get("ref") or "",
                ("→ " + m["target"]) if m.get("target") else "", m.get("url") or ""))
        return
    entry = {"iid": args.iid, "url": args.url, "repo": args.repo,
             "source": args.source, "target": args.target, "ref": args.ref,
             "state": args.state or "opened", "ts": now()}
    data["mrs"] = mr_upsert(data.get("mrs"), entry)
    save(data)
    pmout.op("worklog", extra="MR !%s %s" % (args.iid, entry["state"]))


def main():
    p = argparse.ArgumentParser(description="Suivi d'avancement par session")
    p.add_argument("--session", help="override session id (défaut: $CLAUDE_CODE_SESSION_ID)")
    pmout.add_args(p)
    sub = p.add_subparsers(dest="cmd")

    sh = sub.add_parser("show", help="afficher l'état (statut live + dérive)")
    sh.add_argument("--no-live", action="store_true",
                    help="ne pas résoudre le statut courant (rendu snapshot, plus rapide)")

    sub.add_parser("refresh", help="re-résoudre le statut live et réécrire le .md")

    a = sub.add_parser("add", help="ajouter ou upsert un item")
    a.add_argument("ref", help="référence (ex: RM1886, pisceen-facettes)")
    a.add_argument("label", nargs="?", help="libellé court")
    a.add_argument("--status", help="à_faire|en_cours|en_attente|fait|...")
    a.add_argument("--project", help="projet PM (ex: pm-ai-agents)")
    a.add_argument("--note", help="note courte")
    a.add_argument("--next", help="prochaine action")
    a.add_argument("--commit", help="dernier commit (sha court)")

    s = sub.add_parser("set", help="changer le statut d'un item")
    s.add_argument("ref")
    s.add_argument("status")
    s.add_argument("--note")
    s.add_argument("--next")

    r = sub.add_parser("rm", help="supprimer un item")
    r.add_argument("ref")

    t = sub.add_parser("title", help="définir un titre de session")
    t.add_argument("title")

    m = sub.add_parser("mr", help="refléter une MR dans le worklog (RM2583)")
    m.add_argument("iid", nargs="?", help="numéro de la MR")
    m.add_argument("--url")
    m.add_argument("--repo", help="projet forge (path_with_namespace)")
    m.add_argument("--source")
    m.add_argument("--target")
    m.add_argument("--ref", help="ticket concerné (ex: RM2583)")
    m.add_argument("--state", choices=["opened", "merged", "closed"])
    m.add_argument("--list", action="store_true")

    rq = sub.add_parser("request", help="registre des demandes du demandeur (RM2621)")
    rq.add_argument("text", nargs="?", help="la demande, telle qu'elle a été formulée")
    rq.add_argument("--status", choices=REQUEST_STATES, help="défaut : nouveau")
    rq.add_argument("--ticket", help="ticket qui la porte (ex: RM2621)")
    rq.add_argument("--merged-into", dest="merged_into", help="numéro de la demande qui l'absorbe")
    rq.add_argument("--note")
    rq.add_argument("--set", help="numéro de la demande à faire évoluer (voir --list)")
    rq.add_argument("--list", action="store_true", help="lister toutes les demandes")
    rq.add_argument("--import-missing", dest="import_missing", action="store_true",
                    help="RATTRAPAGE : importer du transcript les demandes absentes du registre")
    rq.add_argument("--audit", action="store_true",
                    help="comparer le registre au transcript (contrôle d'exhaustivité)")

    n = sub.add_parser("notify", help="consigner un événement notable (RM2466)")
    n.add_argument("message", nargs="?", help="texte court, factuel")
    n.add_argument("--kind", choices=sorted(NOTIFY_KINDS),
                   help="; ".join("%s = %s" % kv for kv in sorted(NOTIFY_KINDS.items())))
    n.add_argument("--level", choices=NOTIFY_LEVELS,
                   help="défaut : critical pour --kind secret, warn sinon")
    n.add_argument("--ref", help="ticket concerné (ex: RM2466)")
    n.add_argument("--list", action="store_true", help="lister les notifications")
    n.add_argument("--clear", action="store_true",
                   help="acquitter (les critiques sont conservées sauf --all)")
    n.add_argument("--all", action="store_true",
                   help="avec --clear : acquitter AUSSI les critiques")

    args = p.parse_args()
    pmout.configure(args)
    data = load(session_id(args.session))

    cmd = args.cmd or "show"
    if cmd == "show" and not hasattr(args, "no_live"):
        args.no_live = False
    {"show": cmd_show, "refresh": cmd_refresh, "add": cmd_add, "set": cmd_set,
     "rm": cmd_rm, "title": cmd_title, "notify": cmd_notify,
     "mr": cmd_mr, "request": cmd_request}[cmd](data, args)


if __name__ == "__main__":
    main()
