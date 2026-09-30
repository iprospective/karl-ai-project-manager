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

    # Remplacer ET cocher dans le même appel : les index s'appliquent à la
    # checklist de la NOUVELLE description (RM2281 — ils étaient ignorés avant)
    pm-task-description-update.py 1796 --set-from-file nouvelle_desc.md --check 1,2

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
from pm_output import out
import pm_markdown
from pm_markdown import checklist_lines
import pm_git  # auto-commit scopé des écritures (RM2095)
import pm_scope
from pm_lock import ticket_lock, atomic_write  # verrou par ticket + écriture atomique (T7/RM2551)

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)
# Clés qui signent un frontmatter de FICHE PM — et pas un simple `---` de
# séparation Markdown ouvrant un document (RM2820).
TASK_FM_KEYS_RE = re.compile(r"^(schema_version|redmine_id):", re.M)
# Ligne de checklist Markdown : "- [ ] ...", "* [x] ...", indentée ou non.
# Source unique de vérité pour « qu'est-ce qu'une ligne de checklist » : les
# cases citées dans un bloc de code n'en sont pas (RM2540).
CHECK_LINE_RE = pm_markdown.CHECK_LINE_RE


def redmine_creds():
    url = os.environ.get("REDMINE_URL", "").rstrip("/")
    key = os.environ.get("REDMINE_API_KEY") or os.environ.get("REDMINE_USER_MAIN_API_KEY")
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

    Les cases situées dans un bloc de code sont ignorées (RM2540) : une
    description qui CITE du markdown en exemple ne doit pas voir sa citation
    réécrite — et ces cases ne sont pas des critères.
    """
    lines = text.split("\n")
    items = checklist_lines(text)
    total = len(items)
    changed = []
    for item_no, (i, m) in enumerate(items, start=1):
        cur = m.group(2).lower() == "x"
        new = cur
        if check_all or item_no in check_idx:
            new = True
        if item_no in uncheck_idx:
            new = False
        if new != cur:
            lines[i] = m.group(1) + ("x" if new else " ") + m.group(3)
            changed.append((item_no, new))
    text = "\n".join(lines)
    checked = sum(1 for _, m in checklist_lines(text) if m.group(2).lower() == "x")
    return text, total, checked, changed


def strip_task_frontmatter(text):
    """Retire un frontmatter de fiche PM en tête de `text`. Pure (RM2820).

    Un `--set-from-file` recevant la fiche `RM<id>.md` COMPLÈTE poussait son
    frontmatter YAML (schema_version, tokens_total, reporting…) dans la
    description Redmine, où il n'a aucun sens — et, depuis RM2578, le recopiait
    dans le CORPS du MD, qui se retrouvait avec deux blocs frontmatter. Constaté
    sur RM2426 : posé le 2026-07-30, réparé le jour même, rejoué le 07-31 et
    resté en place un mois. Rien n'empêchait la récidive.

    L'intention de l'appelant est toujours « pousser le corps » : on nettoie et
    on avertit, plutôt que de refuser. Ne matche qu'en TÊTE de texte et
    seulement si le bloc porte une clé de fiche — un corps qui cite du YAML plus
    bas, ou qui s'ouvre sur un `---` de séparation, reste intact.

    Retourne (texte, stripped: bool).
    """
    m = FRONTMATTER_RE.match(text or "")
    if not m or not TASK_FM_KEYS_RE.search(m.group(2)):
        return text, False
    return m.group(4).lstrip("\n"), True


# ── RM3041 : ajout INCRÉMENTAL dans une section (sans réécrire la description) ──
#
# Jusqu'ici, ajouter une anomalie ou un critère imposait `--set-from-file`, donc de
# reconstruire toute la description : fragile, et impossible à scripter proprement. Le
# déclencheur est concret (RM3025) — trois anomalies signalées l'une après l'autre, trois
# réécritures intégrales.
#
# Les deux fonctions ci-dessous sont PURES : elles prennent un texte, rendent un texte.

# Titres reconnus pour chaque rubrique, dans l'ordre de préférence. Le premier est celui
# qu'on CRÉE si aucun n'existe ; les suivants sont des variantes déjà rencontrées.
SECTIONS = {
    "item": ["Anomalies / À faire", "Anomalies", "À faire", "A faire"],
    "criterion": ["Critères d'acceptation", "Criteres d'acceptation", "Critères d’acceptation"],
}


def _section_bounds(text, titles):
    """(début_contenu, fin_contenu, titre_trouvé) de la 1re section portant un de ces titres.
    Rend (None, None, None) si aucune. La fin est le début du titre suivant de MÊME niveau."""
    lines = text.split("\n")
    wanted = [t.strip().lower() for t in titles]
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{2,3})\s+(.+?)\s*$", ln)
        if not m or m.group(2).strip().lower() not in wanted:
            continue
        level = len(m.group(1))
        j = i + 1
        while j < len(lines):
            m2 = re.match(r"^(#{1,6})\s+", lines[j])
            if m2 and len(m2.group(1)) <= level:
                break
            j += 1
        return i + 1, j, m.group(2).strip()
    return None, None, None


def add_checklist_item(desc, kind, texte, checked=False):
    """Ajoute `- [ ] texte` à la fin de la section voulue, en la créant si besoin.

    Idempotent : un item au texte identique (à la casse et aux espaces près) n'est pas
    ajouté deux fois — un script qu'on rejoue ne doit pas empiler des doublons.
    Renvoie (nouveau_texte, ajouté:bool)."""
    texte = (texte or "").strip()
    if not texte:
        return desc, False
    titles = SECTIONS.get(kind) or SECTIONS["item"]
    ligne = "- [{}] {}".format("x" if checked else " ", texte)
    desc = desc or ""

    start, end, _ = _section_bounds(desc, titles)
    if start is None:
        # section absente : on l'ajoute à la fin, précédée d'une ligne vide
        bloc = "## {}\n\n{}\n".format(titles[0], ligne)
        sep = "" if desc.endswith("\n\n") or not desc.strip() else ("\n" if desc.endswith("\n") else "\n\n")
        return (desc.rstrip("\n") + "\n\n" + bloc if desc.strip() else bloc), True

    lines = desc.split("\n")
    corps = lines[start:end]
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()  # noqa: E731
    for ln in corps:
        m = CHECK_LINE_RE.match(ln)
        if m and norm(m.group(3)[1:]) == norm(texte):
            return desc, False                      # déjà présent : ne pas doublonner

    # Le gabarit « ⚠ À définir — aucun critère posé » n'a plus lieu d'être dès qu'un vrai
    # item arrive : le laisser au-dessus de la liste donne une section qui se contredit.
    corps = [ln for ln in corps
             if not re.match(r"^\s*>?\s*⚠?\s*\*{0,2}À définir\*{0,2}", ln)
             and not re.match(r"^\s*>\s*⚠", ln)]

    if not any(ln.strip() for ln in corps):
        corps = ["", ligne]              # section vidée de son gabarit : titre, ligne vide, item
    else:
        # insérer après la DERNIÈRE ligne non vide de la section (donc après le dernier item)
        k = len(corps)
        while k > 0 and not corps[k - 1].strip():
            k -= 1
        corps = corps[:k] + [ligne] + corps[k:]
    return "\n".join(lines[:start] + corps + lines[end:]), True


def build_new_description(desc, file_text, check_idx, uncheck_idx, check_all, adds=None):
    """Calcule la nouvelle description (pure, testable — RM2281).

    `file_text` non-None = mode --set-from-file : le fichier devient la
    description, ET les coches demandées s'y appliquent — elles étaient
    silencieusement ignorées quand les deux options voyageaient dans le même
    appel (le MD comme Redmine perdaient les coches).
    Retourne (new_desc, total, checked, changed, note_bits, desc_changed).
    """
    note_bits = []
    # RM3041 : les ajouts s'appliquent AVANT les coches, pour qu'un `--add-item` suivi d'un
    # `--check` dans le même appel porte sur la liste réelle (leçon RM2281 sur --set-from-file).
    added = []
    for kind, texte in (adds or []):
        base = file_text if file_text is not None else desc
        nouveau, ok = add_checklist_item(base, kind, texte)
        if ok:
            added.append(texte)
            if file_text is not None:
                file_text = nouveau
            else:
                desc = nouveau
    if added:
        note_bits.append("ajouté : " + " · ".join(added))

    if file_text is not None:
        new_desc, total, checked, changed = apply_checks(
            file_text, check_idx, uncheck_idx, check_all)
        desc_changed = (new_desc != desc)
        if desc_changed:
            note_bits.append("description remplacée intégralement")
    else:
        new_desc, total, checked, changed = apply_checks(
            desc, check_idx, uncheck_idx, check_all)
        desc_changed = bool(changed) or bool(added)
    if changed:
        cocheds = [str(n) for n, v in changed if v]
        unchecks = [str(n) for n, v in changed if not v]
        if cocheds:
            note_bits.append("coché item(s) " + ",".join(cocheds))
        if unchecks:
            note_bits.append("décoché item(s) " + ",".join(unchecks))
    return new_desc, total, checked, changed, note_bits, desc_changed


def _acceptance_of(md_path):
    """Le champ `acceptance` de la fiche (miroir du CF 33), "" si vide ou illisible."""
    try:
        import pm_acceptance
        from pm_markdown import read_frontmatter
        return str((read_frontmatter(md_path) or {}).get(pm_acceptance.FM_KEY) or "").strip()
    except Exception:  # noqa: BLE001 — sans lecture possible, on garde le comportement d'avant
        return ""


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
    # RM3041 : ajout INCRÉMENTAL — ajouter une ligne sans réécrire la description entière
    ap.add_argument("--add-item", action="append", metavar="TEXTE",
                    help="Ajoute une ligne à « Anomalies / À faire » (section créée si absente ; répétable ; idempotent)")
    ap.add_argument("--add-criterion", action="append", metavar="TEXTE",
                    help="Ajoute un critère d'acceptation (répétable ; idempotent)")
    ap.add_argument("--drop-placeholders", action="store_true",
                    help="Retire les items de checklist qui ne sont que des GABARITS "
                         "(« (à compléter) », « à définir », « TBD ») — le chemin de sortie "
                         "EXPLICITE quand le ticket n'a pas de critères à définir (RM2789)")
    ap.add_argument("--note", help="Texte de note additionnel (en plus de la note auto)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cross-project", action="store_true",
                    help="Autorise consciemment une écriture sur un ticket d'un AUTRE projet (garde RM2274).")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    cfg = PMConfig.load()  # charge aussi .env
    md_path = cfg.find_task(args.rm_id)
    if not md_path:
        sys.exit(f"ERREUR : fichier RM{args.rm_id}_*.md introuvable")
    if not args.dry_run:
        pm_scope.assert_task_scope(args.rm_id, md_path, args.cross_project, "pm-task-description-update")

    issue = fetch_issue(args.rm_id)
    desc = issue.get("description") or ""

    check_idx = parse_idx(args.check)
    uncheck_idx = parse_idx(args.uncheck)

    done_ratio = None
    file_text = None
    if args.set_from_file:
        p = Path(args.set_from_file)
        if not p.is_file():
            sys.exit(f"ERREUR : fichier introuvable : {p}")
        file_text = p.read_text(encoding="utf-8")
        file_text, _stripped = strip_task_frontmatter(file_text)
        if _stripped:
            out.warn(f"frontmatter de fiche PM retiré de {p.name} — seul le corps "
                     "est poussé (une description Redmine n'a pas de frontmatter).")

    # RM2882 — sur un ticket migré, cocher ICI ne change rien : le garde-fou de statut,
    # la livraison et le cockpit lisent le champ dédié. On ne l'interdit pas (la
    # description reste éditable), on dit juste où va vraiment le cochage.
    if check_idx or uncheck_idx or args.check_all:
        try:
            import pm_acceptance
            from pm_markdown import read_frontmatter
            if str((read_frontmatter(md_path) or {}).get(pm_acceptance.FM_KEY) or "").strip():
                out.warn(f"RM{args.rm_id} a ses critères dans le champ dédié : ce cochage "
                         f"n'y sera pas lu. → pm-task-acceptance.py {args.rm_id} --check N")
        except Exception as e:  # noqa: BLE001 — un avertissement ne fait jamais échouer
            out.warn(f"lecture du champ `acceptance` impossible ({e}) — avertissement omis")

    # RM3241 — un ticket migré a ses critères dans le CF 33. Les réécrire dans la
    # description, c'est recréer le doublon que la purge retire : deux copies, dont
    # une que plus rien ne lit ni ne coche. Deux chemins y menaient.
    _acc = _acceptance_of(md_path)
    if _acc:
        import pm_acceptance
        if args.add_criterion:
            sys.exit(f"ERREUR : RM{args.rm_id} a ses critères dans le champ dédié — un critère "
                     f"ajouté à la description n'y serait lu par personne.\n"
                     f"  → pm-task-acceptance.py {args.rm_id} --append \"- [ ] …\"")
        if file_text is not None and pm_acceptance.extract_sections(file_text):
            action, motifs = pm_acceptance.purge_decision(_acc, file_text)
            if action == "retire":
                file_text = pm_acceptance.strip_sections(file_text)
                out.info(f"  · section « Critères d'acceptation » retirée du fichier : le champ "
                         f"dédié la couvre déjà (pm-task-acceptance {args.rm_id})")
            else:
                sys.exit(f"ERREUR : RM{args.rm_id} a ses critères dans le champ dédié, et la "
                         f"section de ce fichier en diffère :\n    · "
                         + "\n    · ".join(motifs)
                         + f"\n  Les critères se modifient dans leur champ, pas dans la description :\n"
                         f"  → pm-task-acceptance.py {args.rm_id} --set - < critères.md   (ou --append)\n"
                         f"  puis retire la section « Critères d'acceptation » du fichier.")

    # RM2789 — le retrait des gabarits s'applique AVANT le reste, et se compose avec
    # --set-from-file (sur le nouveau texte) comme sans lui (sur la description courante).
    n_drop = 0
    if args.drop_placeholders:
        from pm_markdown import drop_placeholders
        base = file_text if file_text is not None else desc
        base, n_drop = drop_placeholders(base)
        if not n_drop:
            sys.exit(f"Rien à faire : RM{args.rm_id} ne porte aucun gabarit de critère "
                     "« à compléter ».")
        file_text = base

    # note_bits ne décrit QUE les changements de description (Redmine ne les diff pas).
    adds = ([("item", t) for t in (args.add_item or [])]
            + [("criterion", t) for t in (args.add_criterion or [])])
    new_desc, total, checked, changed, note_bits, desc_changed = build_new_description(
        desc, file_text, check_idx, uncheck_idx, args.check_all, adds)
    if n_drop:
        note_bits.append(f"retiré {n_drop} gabarit(s) de critère « à compléter »")
    if file_text is None and not changed and not adds and not args.done_ratio and not args.note \
            and not args.drop_placeholders:
        sys.exit("Rien à faire : aucun item modifié (vérifie les index --check/--uncheck) "
                 "et pas de --done-ratio/--note.")

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
    elif total > 0 and (changed or not args.set_from_file):
        # Par défaut, si on a touché une checklist, on synchronise le % auto —
        # y compris quand les coches voyagent avec --set-from-file (RM2281).
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
    # ligne dense unique (contrat T1, CDC RM2316) : ✓ desc RM<id> [check=<n,…>|set] done=<pct>%
    parts = []
    if args.set_from_file and desc_changed:
        parts.append("set")
    if adds:
        parts.append("add={}".format(len(adds)))
    cocheds = [str(n) for n, v in changed if v]
    unchecks = [str(n) for n, v in changed if not v]
    if cocheds:
        parts.append("check=" + ",".join(cocheds))
    if unchecks:
        parts.append("uncheck=" + ",".join(unchecks))
    extra = " ".join(parts)
    if done_ratio is not None:
        extra = (extra + " " if extra else "") + f"done={done_ratio}%"
    out.op("desc", rm=args.rm_id, extra=extra)

    # 2. Sync MD sous VERROU par ticket (T7) : RMW du .md (read→write), libéré avant
    # le log/commit qui suivent. Pas de return dans le bloc if m: → libération unique.
    _lk = ticket_lock(cfg.state_dir, args.rm_id)
    _lk.__enter__()
    content = md_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if m:
        fm = yaml.safe_load(m.group(2)) or {}
        body = m.group(4)
        if args.set_from_file:
            # RM2578 : le fichier fourni EST la nouvelle description — donc la
            # nouvelle source de vérité. Laisser le corps MD en arrière faisait
            # diverger les deux checklists : un `--check n` suivant appliquait
            # ses index sur l'ANCIENNE liste locale (mauvaises lignes cochées),
            # et `pm-task-deliver`, qui lit le MD, refusait des livraisons sur
            # une checklist périmée. Constaté deux fois (RM2573, RM2305).
            new_body = "\n" + new_desc.strip("\n") + "\n"
        else:
            # RM3041 : les ajouts s'appliquent AUSSI au corps local. Sans cela, la
            # description Redmine était enrichie et le MD restait en arrière — constaté en
            # jouant le verbe pour de vrai sur RM3041 : Redmine à jour, fiche inchangée.
            # On enrichit chacun de son côté plutôt que d'écraser l'un par l'autre : les
            # deux peuvent avoir divergé, et écraser ferait perdre le travail local.
            for _kind, _texte in adds:
                body, _ = add_checklist_item(body, _kind, _texte)
            new_body, _, _, _ = apply_checks(body, check_idx, uncheck_idx, args.check_all)
        if done_ratio is not None:
            fm["completion_pct"] = done_ratio
        fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
        new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
        atomic_write(md_path, f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{new_body}")
        out.info(f"✓ MD synchronisé : {md_path.relative_to(cfg.projects_root)}")

    _lk.__exit__(None, None, None)  # T7 : libère après le RMW du .md (avant log/commit)

    # 3. Append log local (notre historique ; peut mentionner le % même si Redmine le journalise nativement).
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    summary_bits = list(note_bits)
    if done_ratio is not None:
        summary_bits.append(f"done_ratio → {done_ratio}%")
    summary = "; ".join(summary_bits) if summary_bits else "mise à jour description"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {now} — Description : {summary}\n\n" + (args.note + "\n" if args.note else ""))
    out.info(f"✓ Log appendé : {log_path.name}")

    # Auto-commit scopé (RM2095) : la MAJ de description modifiait le MD sans committer.
    pm_git.autocommit([md_path, log_path], f"pm(desc): RM{args.rm_id} description/done_ratio")


if __name__ == "__main__":
    main()
