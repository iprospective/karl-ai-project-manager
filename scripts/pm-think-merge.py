#!/usr/bin/env python3
"""pm-think-merge — fusionne les `.think.md` des tickets vers les fichiers du projet. RM3015 D004/D009, RM3053.

  docs/cdc-questions.md · cdc-decisions.md · cdc-notes.md · cdc-features.md   ← RÉGÉNÉRÉS (bloc entre marqueurs)
  docs/cdc.md · cdc-roadmap.md · cdc-help.md                                   ← créés s'ils manquent, jamais réécrits

Le bloc régénéré vit entre `<!-- think-merge:begin -->` et `<!-- think-merge:end -->` : tout ce qui est
hors marqueurs (préambule, registre tenu à la main avant les think, boîte de réception des idées
sans ticket dans cdc-notes.md) est conservé. Les ids sont préfixés `RM<id>-`. Les compteurs
(`think:` du frontmatter des fiches, D007) sont posés au passage.

  pm-think-merge [--project <client>/<projet>]     fusionne le projet courant (`.mmi-pm` du cwd)
  pm-think-merge --all                             tous les projets qui ont au moins un think
  pm-think-merge --check                           à jour ? (exit 1 sinon) — garde de livraison
  pm-think-merge --rename-legacy                   renomme `cdc-<prefix>-00-sommaire.md` → `cdc.md`,
                                                   `-10-fonctionnalites` → `cdc-features.md`, `-90-` → `cdc-decisions.md`,
                                                   `-91-` → `cdc-notes.md`, `-99-` → `cdc-questions.md`, `cdc-<prefix>/` → `cdc/`,
                                                   et corrige les liens dans docs/*.md (D008)
  --no-commit · --dry-run · --docs-dir/--tasks-dir (tests)
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_output import out as pmout            # noqa: E402
import pm_git                                 # noqa: E402
import pm_think                               # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
LEGACY = [(r"^cdc-(?!rm\d+)(.+?)-00-.*\.md$", "cdc.md"), (r"^cdc-(?!rm\d+)(.+?)-10-.*\.md$", "cdc-features.md"),
          (r"^cdc-(?!rm\d+)(.+?)-90-.*\.md$", "cdc-decisions.md"), (r"^cdc-(?!rm\d+)(.+?)-91-.*\.md$", "cdc-notes.md"),
          (r"^cdc-(?!rm\d+)(.+?)-99-.*\.md$", "cdc-questions.md")]
STAMP_RE = re.compile(r"régénéré le \d{4}-\d{2}-\d{2} \d{2}:\d{2}")


def _stable(s: str) -> str:
    return STAMP_RE.sub("régénéré le <date>", s or "")


def rename_plan(docs: Path) -> list:
    """[(ancien, nouveau)] fichiers puis dossier registre — pure sur le listing."""
    plan = []
    for f in sorted(docs.glob("cdc-*.md")):
        for rx, new in LEGACY:
            if re.match(rx, f.name):
                plan.append((f, docs / new))
    for d in sorted(p for p in docs.glob("cdc-*") if p.is_dir() and not re.match(r"^cdc-rm\d+", p.name)):
        plan.append((d, docs / "cdc"))
    return plan


def rename_legacy(docs: Path, dry: bool) -> list:
    plan = rename_plan(docs)
    if not plan:
        return []
    repl = {old.name: new.name for old, new in plan}
    for old, new in plan:
        if new.exists() and new.resolve() != old.resolve():
            sys.exit(f"ERREUR : {new.name} existe déjà — renommage de {old.name} refusé")
    if dry:
        for old, new in plan:
            print(f"  {old.name} → {new.name}")
        return plan
    for old, new in plan:
        r = subprocess.run(["git", "-C", str(docs), "mv", str(old), str(new)], capture_output=True, text=True)
        if r.returncode != 0:
            old.rename(new)
    # liens : dans tous les .md du dossier docs (INDEX inclus) et dans le registre yml
    for f in list(docs.glob("*.md")) + list((docs / "cdc").glob("*.yml")):
        t = f.read_text(encoding="utf-8"); t2 = t
        for o, n in repl.items():
            t2 = t2.replace(o, n)
        t2 = re.sub(r"cdc-(?!rm\d+)[a-z0-9_-]+/fonctionnalites\.yml", "cdc/fonctionnalites.yml", t2)
        if t2 != t:
            f.write_text(t2, encoding="utf-8")
    return plan


def ensure_files(docs: Path, projet: str, dry: bool) -> list:
    made = []
    for name in pm_think.PROJECT_FILES:
        p = docs / name
        if p.exists():
            continue
        made.append(p)
        if not dry:
            p.write_text(pm_think.project_file_template(name, projet), encoding="utf-8")
    idx = docs / "INDEX.md"
    if idx.is_file() and not dry:
        t = idx.read_text(encoding="utf-8")
        add = []
        desc = {"cdc.md": "CDC transversal du projet (registres régénérés depuis les tickets, RM3015)",
                "cdc-questions.md": "questions ouvertes fusionnées depuis les `.think.md`",
                "cdc-decisions.md": "registre des décisions et conseils fusionné depuis les `.think.md`",
                "cdc-features.md": "fonctionnalités par domaine et version (registre + détail des tickets)",
                "cdc-notes.md": "notes verbatim fusionnées + boîte de réception des idées sans ticket",
                "cdc-roadmap.md": "roadmap : un rôle par version, sur demande",
                "cdc-help.md": "aide utilisateur, complétée par le LLM"}
        for name in pm_think.PROJECT_FILES:
            if f"({name})" not in t and f"]({name})" not in t:
                add.append(f"- [{name}]({name}) — {desc[name]}")
        if add:
            idx.write_text(t.rstrip("\n") + "\n" + "\n".join(add) + "\n", encoding="utf-8")
            made.append(idx)
    return made


def merge_project(docs: Path, tasks: Path, projet: str, *, check=False, dry=False) -> dict:
    """Retourne {"changed": [paths], "stale": [paths]} ; en --check n'écrit rien."""
    thinks = pm_think.load_all(tasks)
    changed, stale = [], []
    if not check:
        changed += ensure_files(docs, projet, dry)
    # registre des fonctionnalités par ticket (pm-cdc-features) : sa partie générée est AU-DESSUS des marqueurs
    if (docs / "cdc" / "fonctionnalites.yml").is_file() and not check and not dry:
        subprocess.run([sys.executable, str(SCRIPTS / "pm-cdc-features.py"), "--docs-dir", str(docs),
                        "--tasks-dir", str(tasks), "--project", projet, "--sync", "--build"],
                       capture_output=True, text=True)
    for kind, name in pm_think.MERGED_FILES.items():
        p = docs / name
        block = pm_think.render_features_by_version(thinks) if kind == "feature" else pm_think.render_merged(kind, thinks)
        existing = p.read_text(encoding="utf-8") if p.is_file() else pm_think.project_file_template(name, projet)
        new = pm_think.splice(existing, block)
        if _stable(new) == _stable(existing) and p.is_file():
            continue
        if check:
            stale.append(p); continue
        if not dry:
            p.write_text(new, encoding="utf-8")
        changed.append(p)
    for rid, parsed in thinks.items():
        sheet = pm_think.find_sheet(tasks, rid)
        if not sheet:
            continue
        cnt = pm_think.counters(parsed)
        if check:
            txt = sheet.read_text(encoding="utf-8")
            if not all(re.search(rf"^  {k}: {v}$", txt, re.M) for k, v in cnt.items()):
                stale.append(sheet)
        elif not dry and pm_think.set_counters(sheet, cnt):
            changed.append(sheet)
    return {"changed": changed, "stale": stale, "thinks": len(thinks)}


def resolve(args):
    """[(docs, tasks, projet)]"""
    if args.docs_dir and args.tasks_dir:
        return [(Path(args.docs_dir), Path(args.tasks_dir), args.project or "?")]
    from pm_paths import PMConfig
    cfg = PMConfig.load()
    refs = []
    if args.all:
        for ent, proj, _ in cfg.iter_projects():
            t = cfg.path("tasks_dir", entity=ent, project=proj)
            if t.is_dir() and any(pm_think.is_think(f) for f in t.glob("RM*" + pm_think.THINK_SUFFIX)):
                refs.append(f"{ent}/{proj}")
    else:
        ref = args.project
        if not ref:
            mm = Path.cwd() / ".mmi-pm"
            if mm.exists():
                p = mm.resolve(); ref = f"{p.parent.parent.name}/{p.name}"
        if not ref or "/" not in ref:
            sys.exit("--project <client>/<projet> requis (ou un workspace avec .mmi-pm), ou --all")
        refs = [ref]
    out = []
    for ref in refs:
        c, p = ref.split("/", 1)
        out.append((cfg.path("docs_dir", entity=c, project=p), cfg.path("tasks_dir", entity=c, project=p), ref))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    pmout.add_args(ap)
    ap.add_argument("--project"); ap.add_argument("--all", action="store_true")
    ap.add_argument("--docs-dir"); ap.add_argument("--tasks-dir")
    ap.add_argument("--check", action="store_true"); ap.add_argument("--rename-legacy", action="store_true")
    ap.add_argument("--no-commit", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    pmout.configure(a)
    rc = 0
    for docs, tasks, projet in resolve(a):
        docs.mkdir(parents=True, exist_ok=True)
        touched = []
        if a.rename_legacy:
            plan = rename_legacy(docs, a.dry_run)
            if plan:
                pmout.op("think-merge", extra=f"{projet} : {len(plan)} renommage(s) (D008)")
                touched += [n for _, n in plan] + [docs / "INDEX.md"] if not a.dry_run else []
        res = merge_project(docs, tasks, projet, check=a.check, dry=a.dry_run)
        if a.check:
            if res["stale"]:
                rc = 1
                print(f"✗ {projet} : {len(res['stale'])} fichier(s) à régénérer — pm-think-merge --project {projet}")
                for p in res["stale"]:
                    print(f"    {p.name}")
            else:
                print(f"✓ {projet} : fichiers projet et compteurs à jour ({res['thinks']} think)")
            continue
        touched += res["changed"]
        pmout.op("think-merge", extra=f"{projet} : {res['thinks']} think fusionné(s), {len(res['changed'])} fichier(s) écrit(s)")
        if touched and not a.no_commit and not a.dry_run:
            paths = [p for p in dict.fromkeys(touched) if Path(p).exists()]
            pm_git.autocommit(paths, f"pm(think-merge): {projet} fusion des think ({res['thinks']} ticket(s))", allow_missing=True)
    sys.exit(rc)


if __name__ == "__main__":
    main()
