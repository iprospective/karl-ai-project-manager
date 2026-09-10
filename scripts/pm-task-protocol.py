#!/usr/bin/env python3
"""pm-task-protocol — Protocole de test d'un ticket : CF Redmine + frontmatter (RM2229).

Le protocole de test se rédige AU FIL DE L'EAU pendant l'avancement du ticket
(décision Mathieu 2026-07-11) — pas seulement à la livraison. Champ canonique :
le CF Redmine « Protocole de test » (texte long), avec miroir local dans le
frontmatter `test_protocol` de la tâche (c'est le miroir que lit la fiche de
revue du cockpit — karl-agent ne lit que le local).

Usage :
    pm-task-protocol.py <RM-id>                    # affiche le protocole courant
    pm-task-protocol.py <RM-id> --set "Texte"      # remplace (ou '-' pour stdin)
    echo "1. ..." | pm-task-protocol.py <RM-id> --set -
    pm-task-protocol.py <RM-id> --append -         # ajoute un bloc à la suite

Config : id du CF dans `.env` → REDMINE_CF_TEST_PROTOCOL_ID (créé via l'UI admin
Redmine — l'API ne sait pas créer une définition de CF). Sans cette variable,
l'id est résolu par nom depuis `redmine.reference.yml` ; à défaut, seul le miroir
frontmatter est écrit (warning) : le cockpit fonctionne quand même, Redmine
n'affiche juste pas le champ.

Le miroir lui-même vit dans `pm_cf_mirror` — même contrat pour `implementation`
(CF 31) et `deploy_actions` (CF 8), cf. RM2563.
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
import pm_cf_mirror
import pm_git
import pm_scope

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)


ENV_VAR = "REDMINE_CF_TEST_PROTOCOL_ID"
CF_NAME = "Protocole de test"


# ── RM3041 : ajouter UNE ligne de test sans réécrire tout le protocole ────────
#
# Un protocole de recette est un tableau qu'on complète au fil de l'eau, cas par cas.
# Jusqu'ici il fallait le réécrire en entier (--set) ou coller un bloc à la suite
# (--append), ce qui cassait le tableau. `--add-test` insère la ligne DANS le tableau.

TEST_ROW_RE = re.compile(r"^\s*\|")


def add_test_row(protocole, section, libelle, mode="AUTO", envs=("Dev", "Préprod", "Prod")):
    """Ajoute `| <id> | <libellé> | [ ] | [ ] | [ ] |` à la fin du tableau de `section`.

    Le tableau est créé s'il n'existe pas, avec ses en-têtes. L'identifiant est déduit du
    dernier de la section (A1 → A2) : un protocole se lit par ses repères, pas par l'ordre
    des lignes. Idempotent sur le libellé.
    Renvoie (nouveau_protocole, ajouté:bool, id_ligne)."""
    protocole = protocole or ""
    libelle = (libelle or "").strip()
    if not libelle:
        return protocole, False, ""
    lines = protocole.split("\n")

    # bornes de la section (titre ## ou ### portant `section`)
    start = end = None
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{2,3})\s+(.+?)\s*$", ln)
        if not m:
            continue
        if start is None and section.strip().lower() in m.group(2).strip().lower():
            start, level = i + 1, len(m.group(1))
            continue
        if start is not None and len(m.group(1)) <= level:
            end = i
            break
    if start is None:
        entetes = "| # | Test | " + " | ".join(envs) + " |"
        sep = "|---|---|" + "---|" * len(envs)
        bloc = "## {}\n\n{}\n{}\n| A1 | {} | {} |\n".format(
            section, entetes, sep, libelle, " | ".join(["[ ]"] * len(envs)))
        base = protocole.rstrip("\n")
        return ((base + "\n\n" + bloc) if base else bloc), True, "A1"
    if end is None:
        end = len(lines)

    corps = lines[start:end]
    norm = lambda x: re.sub(r"\s+", " ", x).strip().lower()  # noqa: E731
    dernier_id, dernier_idx = None, None
    for k, ln in enumerate(corps):
        if not TEST_ROW_RE.match(ln):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= set("-: "):
            continue                                  # séparateur ou ligne vide
        if norm(cells[1]) == norm(libelle):
            return protocole, False, cells[0]         # déjà présent
        if re.match(r"^[A-Za-z]*\d+$", cells[0]):
            dernier_id, dernier_idx = cells[0], k

    if dernier_id:
        pref = re.match(r"^([A-Za-z]*)(\d+)$", dernier_id)
        nid = "{}{}".format(pref.group(1), int(pref.group(2)) + 1)
        ncols = len([c for c in corps[dernier_idx].strip().strip("|").split("|")]) - 2
        cases = " | ".join(["[ ]"] * max(1, ncols))
        ligne = "| {} | {} | {} |".format(nid, libelle, cases)
        corps = corps[:dernier_idx + 1] + [ligne] + corps[dernier_idx + 1:]
    else:                                             # section sans tableau : on le crée
        nid = "A1"
        entetes = "| # | Test | " + " | ".join(envs) + " |"
        sep = "|---|---|" + "---|" * len(envs)
        ligne = "| A1 | {} | {} |".format(libelle, " | ".join(["[ ]"] * len(envs)))
        k = len(corps)
        while k > 0 and not corps[k - 1].strip():
            k -= 1
        corps = corps[:k] + ["", entetes, sep, ligne] + corps[k:]

    return "\n".join(lines[:start] + corps + lines[end:]), True, nid


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--set", dest="set_", metavar="TXT", help="Remplace le protocole ('-' = stdin)")
    g.add_argument("--append", metavar="TXT", help="Ajoute un bloc à la suite ('-' = stdin)")
    g.add_argument("--add-test", metavar="SECTION|LIBELLÉ", action="append",
                   help="RM3041 : ajoute UNE ligne au tableau de tests de la section "
                        "(créée si absente), avec ses cases d'environnement à [ ]. Répétable.")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git (RM1834)")
    ap.add_argument("--cross-project", action="store_true", help="Autorise consciemment une écriture sur un ticket d'un AUTRE projet (garde RM2274).")
    args = ap.parse_args()

    cfg = PMConfig.load()
    md_path = cfg.find_task(args.rm_id)
    if not md_path:
        sys.exit(f"ERREUR : aucun fichier RM{args.rm_id}_*.md")
    if args.set_ is not None or args.append is not None or args.add_test:
        pm_scope.assert_task_scope(args.rm_id, md_path, args.cross_project, "pm-task-protocol")
    content = md_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : frontmatter illisible dans {md_path.name}")
    fm = yaml.safe_load(m.group(2)) or {}
    current = str(fm.get("test_protocol") or "").strip()

    if args.set_ is None and args.append is None and not args.add_test:
        print(current if current else f"(pas de protocole de test sur RM{args.rm_id} — "
                                      f"pm-task-protocol.py {args.rm_id} --set -)")
        return

    if args.add_test:                       # RM3041 : ajout ligne à ligne, dans le tableau
        new = current
        ajouts = []
        for spec in args.add_test:
            part = [x.strip() for x in str(spec).split("|")]
            section = part[0] if part and part[0] else "Recette"
            libelle = part[1] if len(part) > 1 else ""
            if not libelle:
                sys.exit(f"ERREUR : --add-test attend « SECTION|LIBELLÉ » (reçu : {spec})")
            new, ok, nid = add_test_row(new, section, libelle)
            if ok:
                ajouts.append(f"{nid} {libelle}")
            else:
                print(f"  = déjà présent, ignoré : {libelle}")
        if not ajouts:
            print("Rien à ajouter : toutes les lignes existaient déjà.")
            return
        print("  + " + "\n  + ".join(ajouts))
    else:
        txt = args.set_ if args.set_ is not None else args.append
        txt = (sys.stdin.read() if txt == "-" else txt).strip()
        if not txt:
            sys.exit("ERREUR : protocole vide")
        new = (current + "\n\n" + txt).strip() if (args.append is not None and current) else txt

    # 1. Miroir frontmatter (bloc littéral multiligne via safe_dump)
    fm["test_protocol"] = new
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    md_path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}", encoding="utf-8")
    print(f"✓ frontmatter test_protocol : {md_path.relative_to(cfg.projects_root)}")

    # 2. CF Redmine (champ canonique visible web)
    if pm_cf_mirror.push_text_cf(args.rm_id, new, env_var=ENV_VAR, cf_name=CF_NAME):
        print(f"✓ CF Redmine « {CF_NAME} » poussé")

    # 3. Log + auto-commit
    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    verb = "remplacé" if args.set_ is not None else ("complété" if args.append is not None else "enrichi (add-test)")
    # `txt` n'existe que dans les modes --set/--append ; en --add-test on journalise les
    # lignes ajoutées. Sans ça, le script plantait APRÈS avoir écrit le protocole et poussé
    # le CF — l'opération réussie passait pour un échec.
    detail = txt if args.add_test is None else "\n".join("+ " + a for a in ajouts)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {ts} — Protocole de test {verb} (pm-task-protocol)\n"
                f"Tokens : 0 | Durée : 0 min\n\n{detail}\n")
    if not args.no_commit:
        pm_git.autocommit([md_path, log_path],
                          f"pm(protocol): RM{args.rm_id} protocole de test {verb}")


if __name__ == "__main__":
    main()
