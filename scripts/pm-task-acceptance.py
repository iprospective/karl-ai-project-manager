#!/usr/bin/env python3
"""pm-task-acceptance — Critères d'acceptation d'un ticket : CF Redmine + frontmatter (RM2882).

Les critères **dérivent** du CDC, mais n'en suivent pas le rythme : la description
change quand la demande change (renégociation), les critères changent quand on
apprend en faisant. Deux rythmes dans un même contenant ⇒ on sort les critères,
comme l'a été le protocole de test (CF 30, RM2229).

Champ canonique : CF Redmine **33 « Critères d'acceptation »**, miroir local dans
le frontmatter `acceptance` (c'est le miroir que lit le cockpit — karl-agent ne
lit jamais l'API). Contrat commun : `pm_cf_mirror`. Lecture : `pm_acceptance`.

Usage :
    pm-task-acceptance.py <RM-id>                     # affiche les critères et leur source
    pm-task-acceptance.py <RM-id> --set "- [ ] …"     # remplace ('-' = stdin)
    pm-task-acceptance.py <RM-id> --append -          # ajoute des items à la suite
    pm-task-acceptance.py <RM-id> --from-description  # initialise depuis la section du MD
    pm-task-acceptance.py <RM-id> --check 2           # coche le 2ᵉ critère (répétable)
    pm-task-acceptance.py <RM-id> --pull              # rapatrie une saisie faite dans l'UI web

Deux gardes, toutes deux apprises en réel :

1. **Jamais de valeur vide poussée.** Vérifié sur RM2882 : un PUT du CF avec
   `value: ""` **efface** le champ. Un bug qui produit une chaîne vide (section
   introuvable, parsing raté) détruirait donc le contenu au lieu de ne rien faire.
   Même garde que `pm-task-protocol` sur le CF 30.
2. **`--check N` ne s'applique qu'au champ**, jamais à la description. Les index
   de `pm-task-description-update --check` sont positionnels dans le DOCUMENT :
   tant qu'un ticket n'est pas migré, le Nᵉ item du document n'est pas le Nᵉ
   critère, et cocher « le 2 » ne désigne pas la même ligne des deux côtés.
   Champ vide ⇒ ce script refuse et renvoie vers l'outil de la description.
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
import pm_acceptance
import pm_cf_mirror
import pm_git
import pm_markdown
import pm_scope

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)

ENV_VAR = pm_acceptance.ENV_VAR
CF_NAME = pm_acceptance.CF_NAME


def set_check(text, indexes, value):
    """Coche (ou décoche) les items désignés, 1-based, dans l'ordre du texte.

    Rend `(texte, touchés, hors_bornes)`. On ne compte QUE les items réels (gabarits
    exclus), pour que le numéro affiché par ce script soit celui qu'on peut lui repasser.
    """
    lines = text.split("\n")
    reels = pm_markdown.real_checklist_lines(text)
    touches, hors = [], []
    for n in indexes:
        if n < 1 or n > len(reels):
            hors.append(n)
            continue
        i, m = reels[n - 1]
        lines[i] = m.group(1) + ("x" if value else " ") + m.group(3)
        touches.append((n, m.group(3)[1:].strip()))
    return "\n".join(lines), touches, hors


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--set", dest="set_", metavar="TXT", help="Remplace les critères ('-' = stdin)")
    g.add_argument("--append", metavar="TXT", help="Ajoute des items à la suite ('-' = stdin)")
    g.add_argument("--from-description", action="store_true",
                   help="Initialise le champ depuis la section « Critères d'acceptation » du MD "
                        "(refuse si le champ est déjà rempli, sauf --force)")
    g.add_argument("--pull", action="store_true",
                   help="Rapatrie la valeur du CF Redmine dans le frontmatter (saisie UI web)")
    ap.add_argument("--check", type=int, action="append", metavar="N",
                    help="Coche le Nᵉ critère du CHAMP (répétable)")
    ap.add_argument("--uncheck", type=int, action="append", metavar="N",
                    help="Décoche le Nᵉ critère du champ (répétable)")
    ap.add_argument("--force", action="store_true",
                    help="Autorise --from-description à écraser un champ déjà rempli")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git (RM1834)")
    ap.add_argument("--cross-project", action="store_true",
                    help="Autorise consciemment une écriture sur un ticket d'un AUTRE projet "
                         "(garde RM2274).")
    args = ap.parse_args()

    ecrit = (args.set_ is not None or args.append is not None or args.from_description
             or args.pull or args.check or args.uncheck)

    cfg = PMConfig.load()
    md_path = cfg.find_task(args.rm_id)
    if not md_path:
        sys.exit(f"ERREUR : aucun fichier RM{args.rm_id}_*.md")
    if ecrit:
        pm_scope.assert_task_scope(args.rm_id, md_path, args.cross_project, "pm-task-acceptance")
    content = md_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : frontmatter illisible dans {md_path.name}")
    fm = yaml.safe_load(m.group(2)) or {}
    body = m.group(4)
    current = str(fm.get(pm_acceptance.FM_KEY) or "").strip()

    # ── lecture seule : dire AUSSI d'où vient ce qu'on affiche ───────────────
    if not ecrit:
        txt, src = pm_acceptance.criteria_text(fm, body)
        if not src:
            print(f"(aucun critère sur RM{args.rm_id} — "
                  f"pm-task-acceptance.py {args.rm_id} --set -)")
            return
        items = pm_acceptance.parse_items(txt)
        coches = sum(1 for ok, _ in items if ok)
        origine = ("champ dédié (CF 33)" if src == pm_acceptance.FM_KEY
                   else "section de la description — ticket non migré")
        print(f"— {coches}/{len(items)} coché(s) · source : {origine}")
        for n, (ok, lab) in enumerate(items, 1):
            # Les libellés sont enveloppés à ~95 colonnes dans les descriptions :
            # on réaligne les continuations sous le texte, sinon la liste numérotée
            # devient illisible dès qu'un critère fait deux lignes.
            first, *rest = lab.split("\n")
            print(f"{n:>3}. [{'x' if ok else ' '}] {first}")
            for r in rest:
                print(f"        {r}")
        return

    # ── --pull : le sens Redmine → PM (un humain a saisi dans l'UI) ──────────
    if args.pull:
        distant = pm_cf_mirror.pull_text_cf(args.rm_id, env_var=ENV_VAR, cf_name=CF_NAME)
        distant = pm_cf_mirror.normalize_text(distant)
        if not distant:
            print(f"Rien à rapatrier : le CF « {CF_NAME} » de RM{args.rm_id} est vide.")
            return
        if distant == current:
            print("Déjà à jour : le miroir frontmatter est identique au CF.")
            return
        new = distant
    elif args.from_description:
        if current and not args.force:
            sys.exit(f"ERREUR : RM{args.rm_id} a déjà des critères dans le champ. "
                     f"--force pour les remplacer par ceux de la description "
                     f"(ou --append pour compléter).")
        section = pm_acceptance.extract_section(body)
        items = pm_acceptance.parse_items(section or "")
        if not items:
            # Refuser plutôt qu'écrire du vide : c'est le § 1 de l'étude — un PUT vide EFFACE.
            sys.exit(f"ERREUR : aucun critère réel dans la section « Critères d'acceptation » "
                     f"de RM{args.rm_id} (section absente, vide ou réduite à un gabarit).")
        errantes = pm_acceptance.stray_checkboxes(body)
        if errantes:
            print(f"⚠ {len(errantes)} case(s) à cocher hors de la section de critères : "
                  f"les index de `pm-task-description-update --check N` ne désigneront plus "
                  f"les mêmes lignes que `--check N` ici.", file=sys.stderr)
        new = pm_acceptance.render_items(items)
    elif args.check or args.uncheck:
        if not current:
            sys.exit(f"ERREUR : le champ de RM{args.rm_id} est vide — ses critères vivent encore "
                     f"dans la description. Cocher : pm-task-description-update.py {args.rm_id} "
                     f"--check N (ou migrer d'abord : --from-description).")
        new, touches, hors = current, [], []
        for idx, val in ((args.check or [], True), (args.uncheck or [], False)):
            new, t, h = set_check(new, idx, val)
            touches += t
            hors += h
        if hors:
            total = len(pm_acceptance.parse_items(current))
            sys.exit(f"ERREUR : critère(s) {', '.join(map(str, hors))} hors bornes "
                     f"(RM{args.rm_id} en compte {total}) — rien n'a été écrit.")
        for n, lab in touches:
            print(f"  {n}. {lab}")
    else:
        txt = args.set_ if args.set_ is not None else args.append
        txt = (sys.stdin.read() if txt == "-" else txt).strip()
        if not txt:
            sys.exit("ERREUR : critères vides — un PUT vide EFFACE le champ (garde RM2882).")
        new = (current + "\n" + txt).strip() if (args.append is not None and current) else txt

    new = pm_cf_mirror.normalize_text(new)
    if not new:
        sys.exit("ERREUR : critères vides — un PUT vide EFFACE le champ (garde RM2882).")
    if new == current:
        print("Rien à écrire : les critères sont inchangés.")
        return

    # 1. Miroir frontmatter (bloc littéral multiligne via safe_dump)
    fm[pm_acceptance.FM_KEY] = new
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    md_path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}", encoding="utf-8")
    print(f"✓ frontmatter acceptance : {md_path.relative_to(cfg.projects_root)}")

    # 2. CF Redmine (champ canonique visible web) — sauf en --pull, il en vient
    if args.pull:
        print(f"✓ CF Redmine « {CF_NAME} » rapatrié dans le miroir local")
    elif pm_cf_mirror.push_text_cf(args.rm_id, new, env_var=ENV_VAR, cf_name=CF_NAME):
        print(f"✓ CF Redmine « {CF_NAME} » poussé")

    # 3. Log + auto-commit
    verb = ("remplacés" if args.set_ is not None else
            "complétés" if args.append is not None else
            "repris de la description" if args.from_description else
            "rapatriés depuis Redmine" if args.pull else "cochés")
    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    if args.check or args.uncheck:
        detail = "\n".join(f"- {n}. {lab}" for n, lab in touches)
    else:
        detail = new
    items = pm_acceptance.parse_items(new)
    compte = f"{sum(1 for ok, _ in items if ok)}/{len(items)} coché(s)"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {ts} — Critères d'acceptation {verb} (pm-task-acceptance)\n"
                f"Tokens : 0 | Durée : 0 min\n\n{compte}\n\n{detail}\n")
    if not args.no_commit:
        pm_git.autocommit([md_path, log_path],
                          f"pm(acceptance): RM{args.rm_id} critères {verb} ({compte})")


if __name__ == "__main__":
    main()
