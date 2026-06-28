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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import pm_session  # registre seq / branches / worktrees (RM2034)
except Exception:
    pm_session = None

WORKLOG_DIR = os.path.expanduser("~/.claude/session-worklogs")

# statuts considérés comme terminés (filtrés hors du « reste à faire »)
DONE = {"fait", "done", "ferme", "fermé", "livré", "livre", "closed", "résolu", "resolu"}
# statuts considérés bloqués/en attente externe (affichés à part)
WAITING = {"en_attente", "attente", "bloqué", "bloque", "blocked", "waiting",
           "à_valider", "a_valider", "a_tester_demandeur", "a_tester_dev", "en_pause"}

RM_RE = re.compile(r"(?i)^RM(\d+)$")


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
    data["updated"] = now()
    jpath, mpath = paths(data["session_id"])
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(mpath, "w", encoding="utf-8") as f:
        f.write(render_md(data, live=live))


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
            live[ref] = {"status": st, "title": _read_fm_field(p, "title")}
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
    print("✓ worklog rafraîchi (%d item(s), statut live)" % len(data["items"]))


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
    print("✓ %s : %s" % (action, args.ref))


def cmd_set(data, args):
    it = find(data, args.ref)
    if not it:
        sys.exit("✗ introuvable : %s" % args.ref)
    it["status"] = args.status
    if args.note is not None:
        it["note"] = args.note
    if getattr(args, "next", None) is not None:
        it["next"] = args.next
    it["ts"] = now()
    save(data)
    print("✓ %s → %s" % (it["ref"], it["status"]))


def cmd_rm(data, args):
    before = len(data["items"])
    data["items"] = [i for i in data["items"] if i["ref"].lower() != args.ref.lower()]
    if len(data["items"]) == before:
        sys.exit("✗ introuvable : %s" % args.ref)
    save(data)
    print("✓ supprimé : %s" % args.ref)


def cmd_title(data, args):
    data["title"] = args.title
    save(data)
    print("✓ titre : %s" % args.title)


def main():
    p = argparse.ArgumentParser(description="Suivi d'avancement par session")
    p.add_argument("--session", help="override session id (défaut: $CLAUDE_CODE_SESSION_ID)")
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

    args = p.parse_args()
    data = load(session_id(args.session))

    cmd = args.cmd or "show"
    if cmd == "show" and not hasattr(args, "no_live"):
        args.no_live = False
    {"show": cmd_show, "refresh": cmd_refresh, "add": cmd_add, "set": cmd_set,
     "rm": cmd_rm, "title": cmd_title}[cmd](data, args)


if __name__ == "__main__":
    main()
