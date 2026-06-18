#!/usr/bin/env python3
"""Suivi par session des tickets/tâches ouverts et de leur avancement.

Store léger keyé par session Claude Code ($CLAUDE_CODE_SESSION_ID) :
  - source de vérité : ~/.claude/session-worklogs/<session-id>.json
  - rendu lisible     : ~/.claude/session-worklogs/<session-id>.md (régénéré à chaque mutation)

But : répondre cheap à « il reste quoi à faire dans cette session » sans rescanner
le contexte. L'agent appelle `add`/`set` au fil de l'eau, et `show` pour rapporter.

Implémente le volet « manifest déclaratif » de RM1875 (suivi par session).
"""
import argparse
import datetime
import json
import os
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
WAITING = {"en_attente", "attente", "bloqué", "bloque", "blocked", "waiting", "à_valider", "a_valider"}


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


def save(data):
    os.makedirs(WORKLOG_DIR, exist_ok=True)
    data["updated"] = now()
    jpath, mpath = paths(data["session_id"])
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(mpath, "w", encoding="utf-8") as f:
        f.write(render_md(data))


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


def is_done(it):
    return it["status"].lower() in DONE


def is_waiting(it):
    return it["status"].lower() in WAITING


def render_md(data):
    out = ["# Worklog session — " + data["session_id"]]
    if data.get("title"):
        out.append("**" + data["title"] + "**")
    out.append("_maj : " + data["updated"] + "_\n")

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
    todo = [i for i in data["items"] if not is_done(i) and not is_waiting(i)]
    wait = [i for i in data["items"] if is_waiting(i)]
    done = [i for i in data["items"] if is_done(i)]

    def line(it):
        ref = it["ref"]
        proj = (" _(%s)_" % it["project"]) if it.get("project") else ""
        note = ("\n  ↳ " + it["note"]) if it.get("note") else ""
        return "- `[%s]` **%s** — %s%s%s" % (it["status"], ref, it["label"], proj, note)

    out.append("## ⏳ Reste à faire")
    out += [line(i) for i in todo] or ["_(rien)_"]
    if wait:
        out.append("\n## ⏸️ En attente / bloqué")
        out += [line(i) for i in wait]
    out.append("\n## ✅ Fait")
    out += [line(i) for i in done] or ["_(rien)_"]
    return "\n".join(out) + "\n"


def cmd_show(data, args):
    sys.stdout.write(render_md(data))


def cmd_add(data, args):
    it = find(data, args.ref)
    if it:
        # upsert : met à jour les champs fournis
        if args.label:
            it["label"] = args.label
        if args.status:
            it["status"] = args.status
        if args.project:
            it["project"] = args.project
        if args.note is not None:
            it["note"] = args.note
        it["ts"] = now()
        action = "mis à jour"
    else:
        data["items"].append({
            "id": (max([i.get("id", 0) for i in data["items"]], default=0) + 1),
            "ref": args.ref,
            "label": args.label or args.ref,
            "project": args.project,
            "status": args.status or "à_faire",
            "note": args.note or "",
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

    sub.add_parser("show", help="afficher l'état (reste à faire / en attente / fait)")

    a = sub.add_parser("add", help="ajouter ou upsert un item")
    a.add_argument("ref", help="référence (ex: RM1886, pisceen-facettes)")
    a.add_argument("label", nargs="?", help="libellé court")
    a.add_argument("--status", help="à_faire|en_cours|en_attente|fait|...")
    a.add_argument("--project", help="projet PM (ex: pm-ai-agents)")
    a.add_argument("--note", help="note courte")

    s = sub.add_parser("set", help="changer le statut d'un item")
    s.add_argument("ref")
    s.add_argument("status")
    s.add_argument("--note")

    r = sub.add_parser("rm", help="supprimer un item")
    r.add_argument("ref")

    t = sub.add_parser("title", help="définir un titre de session")
    t.add_argument("title")

    args = p.parse_args()
    data = load(session_id(args.session))

    cmd = args.cmd or "show"
    {"show": cmd_show, "add": cmd_add, "set": cmd_set,
     "rm": cmd_rm, "title": cmd_title}[cmd](data, args)


if __name__ == "__main__":
    main()
