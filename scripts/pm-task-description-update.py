#!/usr/bin/env python3
"""pm-task-description-update — Met à jour la DESCRIPTION d'un ticket Redmine + sync MD.

La description est un document vivant (NORMS § « Mise à jour de la description du
ticket Redmine »). Ce wrapper couvre le cas le plus courant : cocher/décocher des
items de checklist Markdown au fil de l'eau, et mettre à jour le % réalisé
(done_ratio Redmine / completion_pct MD) — dérivé du ratio de cases cochées par
défaut, conformément à NORMS.

Usage :
    # Cocher les items 1 et 2 de la checklist (1-based), recalcule le % auto
    pm-task-description-update.py 1796 --check 1,2

    # Cocher tout + clore le ratio à 100 %
    pm-task-description-update.py 1796 --check-all

    # Décocher un item (re-ouverture d'un sous-point)
    pm-task-description-update.py 1796 --uncheck 3

    # Forcer un % explicite (sans checklist, selon évaluation de l'agent)
    pm-task-description-update.py 1796 --done-ratio 70 --note "Back terminé, reste l'UI"

    # Remplacer entièrement la description (re-cadrage substantiel)
    pm-task-description-update.py 1796 --set-from-file nouvelle_desc.md --note "Re-cadrage périmètre"

Note de journal : une note Redmine accompagnante est TOUJOURS postée (auto +
texte --note éventuel), car Redmine ne diff pas les descriptions dans l'UI.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
import pm_git  # auto-commit scopé des écritures (RM2095)

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)
# Ligne de checklist Markdown : "- [ ] ...", "* [x] ...", indentée ou non.
CHECK_LINE_RE = re.compile(r"^(\s*[-*]\s*\[)([ xX])(\].*)$")


def redmine_creds():
    url = os.environ.get("REDMINE_URL", "").rstrip("/")
    key = os.environ.get("REDMINE_USER_MAIN_API_KEY") or os.environ.get("REDMINE_API_KEY")
    if not (url and key):
        sys.exit("ERREUR : $REDMINE_URL et $REDMINE_USER_MAIN_API_KEY requis (.env)")
    return url, key


def fetch_issue(rm_id):
    url, key = redmine_creds()
    req = urllib.request.Request(
        f"{url}/issues/{rm_id}.json",
        headers={"X-Redmine-API-Key": key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("issue")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        sys.exit(f"ERREUR : lecture ticket RM{rm_id} impossible : {e}")


def put_issue(rm_id, fields):
    url, key = redmine_creds()
    body = json.dumps({"issue": fields}).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/issues/{rm_id}.json", data=body, method="PUT",
        headers={"X-Redmine-API-Key": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status in (200, 204)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        detail = ""
        if isinstance(e, urllib.error.HTTPError):
            try:
                detail = " — " + e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
        sys.exit(f"ERREUR : PUT RM{rm_id} échoué : {e}{detail}")


def apply_checks(text, check_idx, uncheck_idx, check_all):
    """Applique coche/décoche aux lignes de checklist. Retourne (texte, total, checked, changed).

    check_idx / uncheck_idx : ensembles d'index 1-based parmi les lignes de checklist.
    """
    lines = text.split("\n")
    item_no = 0
    total = 0
    changed = []
    for i, line in enumerate(lines):
        m = CHECK_LINE_RE.match(line)
        if not m:
            continue
        item_no += 1
        total += 1
        cur = m.group(2).lower() == "x"
        new = cur
        if check_all or item_no in check_idx:
            new = True
        if item_no in uncheck_idx:
            new = False
        if new != cur:
            lines[i] = m.group(1) + ("x" if new else " ") + m.group(3)
            changed.append((item_no, new))
    checked = 0
    item_no = 0
    for line in lines:
        m = CHECK_LINE_RE.match(line)
        if m:
            checked += 1 if m.group(2).lower() == "x" else 0
    return "\n".join(lines), total, checked, changed


def parse_idx(spec):
    if not spec:
        return set()
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--check", help="Index(s) 1-based d'items de checklist à cocher (ex: 1,2)")
    ap.add_argument("--uncheck", help="Index(s) 1-based d'items à décocher")
    ap.add_argument("--check-all", action="store_true", help="Coche tous les items de la checklist")
    ap.add_argument("--done-ratio", help="'auto' (depuis la checklist) ou entier 0-100")
    ap.add_argument("--set-from-file", help="Remplace toute la description par le contenu du fichier")
    ap.add_argument("--note", help="Texte de note additionnel (en plus de la note auto)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = PMConfig.load()  # charge aussi .env
    md_path = cfg.find_task(args.rm_id)
    if not md_path:
        sys.exit(f"ERREUR : fichier RM{args.rm_id}_*.md introuvable")

    issue = fetch_issue(args.rm_id)
    desc = issue.get("description") or ""

    check_idx = parse_idx(args.check)
    uncheck_idx = parse_idx(args.uncheck)

    note_bits = []   # ne décrit QUE les changements de description (Redmine ne les diff pas).
    done_ratio = None
    desc_changed = False

    if args.set_from_file:
        p = Path(args.set_from_file)
        if not p.is_file():
            sys.exit(f"ERREUR : fichier introuvable : {p}")
        new_desc = p.read_text(encoding="utf-8")
        _, total, checked, _ = apply_checks(new_desc, set(), set(), False)
        desc_changed = (new_desc != desc)
        if desc_changed:
            note_bits.append("description remplacée intégralement")
    else:
        new_desc, total, checked, changed = apply_checks(desc, check_idx, uncheck_idx, args.check_all)
        if not changed and not args.done_ratio and not args.note:
            sys.exit("Rien à faire : aucun item modifié (vérifie les index --check/--uncheck) "
                     "et pas de --done-ratio/--note.")
        desc_changed = bool(changed)
        if changed:
            cocheds = [str(n) for n, v in changed if v]
            unchecks = [str(n) for n, v in changed if not v]
            if cocheds:
                note_bits.append("coché item(s) " + ",".join(cocheds))
            if unchecks:
                note_bits.append("décoché item(s) " + ",".join(unchecks))

    # done_ratio : explicite, ou auto depuis la checklist. NB : le changement de
    # done_ratio est journalisé nativement par Redmine → on ne le met PAS dans la note.
    if args.done_ratio:
        if args.done_ratio == "auto":
            if total > 0:
                done_ratio = round(100 * checked / total)
        else:
            try:
                done_ratio = max(0, min(100, int(args.done_ratio)))
            except ValueError:
                sys.exit("ERREUR : --done-ratio attend 'auto' ou un entier 0-100")
    elif not args.set_from_file and total > 0:
        # Par défaut, si on a touché une checklist, on synchronise le % auto.
        done_ratio = round(100 * checked / total)

    # Note Redmine : seulement si la description change (Redmine ne diff pas les
    # descriptions) ou si l'agent ajoute un commentaire. Pas de note pour un simple % .
    note_parts = []
    if desc_changed and note_bits:
        note_parts.append("Description : " + "; ".join(note_bits))
    if args.note:
        note_parts.append(args.note)
    redmine_note = "\n\n".join(note_parts) if note_parts else None

    if args.dry_run:
        print(f"--dry-run RM{args.rm_id}")
        print(f"  note     : {redmine_note or '(aucune — done_ratio natif)'}")
        if done_ratio is not None:
            print(f"  done_ratio → {done_ratio}")
        print("  --- nouvelle description ---")
        print(new_desc)
        return

    # 1. PUT Redmine : description si changée, done_ratio si défini, note si pertinente.
    fields = {}
    if desc_changed:
        fields["description"] = new_desc
    if done_ratio is not None:
        fields["done_ratio"] = done_ratio
    if redmine_note:
        fields["notes"] = redmine_note
    if not fields:
        sys.exit("Rien à pousser (ni description, ni done_ratio, ni note).")
    put_issue(args.rm_id, fields)
    bits = []
    if desc_changed:
        bits.append("description")
    if done_ratio is not None:
        bits.append(f"done_ratio={done_ratio}")
    print(f"✓ RM{args.rm_id} mis à jour ({', '.join(bits)})")

    # 2. Sync MD : applique la même transfo à la checklist du corps + completion_pct
    content = md_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if m:
        fm = yaml.safe_load(m.group(2)) or {}
        body = m.group(4)
        if args.set_from_file:
            new_body = body  # on ne réécrit pas le corps MD sur un remplacement libre
        else:
            new_body, _, _, _ = apply_checks(body, check_idx, uncheck_idx, args.check_all)
        if done_ratio is not None:
            fm["completion_pct"] = done_ratio
        fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
        new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
        md_path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{new_body}", encoding="utf-8")
        print(f"✓ MD synchronisé : {md_path.relative_to(cfg.projects_root)}")

    # 3. Append log local (notre historique ; peut mentionner le % même si Redmine le journalise nativement).
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    summary_bits = list(note_bits)
    if done_ratio is not None:
        summary_bits.append(f"done_ratio → {done_ratio}%")
    summary = "; ".join(summary_bits) if summary_bits else "mise à jour description"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {now} — Description : {summary}\n\n" + (args.note + "\n" if args.note else ""))
    print(f"✓ Log appendé : {log_path.name}")

    # Auto-commit scopé (RM2095) : la MAJ de description modifiait le MD sans committer.
    pm_git.autocommit([md_path, log_path], f"pm(desc): RM{args.rm_id} description/done_ratio")


if __name__ == "__main__":
    main()
