#!/usr/bin/env python3
"""pm-task-doc — adosser une doc partagée (aspect) à un ticket (RM1890 / RM1856).

Un ticket **costaud** — un CDC, ou un sujet découpé en plusieurs tickets qui partagent
un socle — mérite une doc **factorisée** : elle vit **une** fois dans `docs/<slug>.md`
et les N tickets la référencent, au lieu que le contexte soit recopié dans chaque
description. C'est la convention `ticket-doc-convention.md` (RM1856) ; cet outil la
rend applicable sans geste manuel.

Ce que l'outil garantit (§ 3.2-3.4 de la convention) :

  - **emplacement canonique** `{docs_dir}/<slug>.md`. Pas `project/` : depuis RM2043
    (privsep), `pm-wiki-sync::collect_aspects()` énumère **`docs/*.md`** — poser un
    fichier là, c'est créer un aspect, et il est publié au wiki au passage suivant ;
  - **slug stable, SANS RM-id** : le slug devient l'URL de la page wiki, un rename la
    casse. Un slug qui contient un RM-id est **refusé** ;
  - **liaison bidirectionnelle** : `related_tickets[]` côté aspect, référence
    « Doc partagée » côté description du ticket ;
  - **idempotence** : rejouer ne duplique rien.

Usage :
    pm-task-doc.py <rm_id> --slug <slug> [--title "…"]   # scaffold OU rattache
    pm-task-doc.py <rm_id> --slug <slug> --detach        # délie le ticket de l'aspect
    pm-task-doc.py <rm_id> --list                        # aspects liés à ce ticket
    pm-task-doc.py --check [<projet>]                    # audit de conformité
    pm-task-doc.py <rm_id> --slug <slug> --sync          # publie au wiki dans la foulée

⚠ Le **CF link** ticket→page wiki (prévu §3.3) n'est PAS posé : l'instance Redmine n'a
  pas encore de champ dédié (les CF `link` existants sont « GIT PR » et « Environnement
  de test »). L'outil le signale et pose la référence en description, qui suffit à
  l'agent comme à l'humain. Créer le CF est une opération d'instance (parité RM2043).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig                      # noqa: E402
from pm_markdown import split_frontmatter          # noqa: E402
from pm_doc import wiki_title_for_slug             # noqa: E402  (règle partagée, RM1890)
from pm_output import out                          # noqa: E402

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "templates" / "aspects" / "common" / "shared-doc.md"
REF_PREFIX = "Doc partagée :"
# Un slug ne doit pas porter de RM-id : il devient l'URL wiki, un rename la casse.
RM_IN_SLUG = re.compile(r"(^|[-_])rm?\d{3,}([-_]|$)", re.I)
SKIP = {"overview", "INDEX", "index"}


# ── slug ─────────────────────────────────────────────────────────────────────
def check_slug(slug: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", slug):
        out.fail(f"slug invalide : {slug!r}",
                 "minuscules, chiffres et tirets ; 2 à 61 caractères")
    if RM_IN_SLUG.search(slug):
        out.fail(f"slug avec RM-id : {slug!r}",
                 "le slug devient l'URL de la page wiki et doit SURVIVRE au ticket "
                 "(convention §3.2) — préférer un nom de sujet, ex. « cockpit-architecture »")


# ── frontmatter : édition TEXTUELLE de related_tickets[] ─────────────────────
# On n'écrit pas le YAML par round-trip : il perdrait les commentaires de fin de ligne
# (« # ticket porteur »), qui sont la moitié de l'intérêt de la liste.
def related_ids(fm_text: str) -> list[int]:
    m = re.search(r"^related_tickets:\s*\n((?:\s*-\s*\d+.*\n)*)", fm_text, re.M)
    return [int(x) for x in re.findall(r"^\s*-\s*(\d+)", m.group(1), re.M)] if m else []


def add_related(fm_text: str, rm_id: int, note: str = "") -> tuple[str, bool]:
    """Ajoute `rm_id` à `related_tickets[]`. Retourne (texte, modifié)."""
    if rm_id in related_ids(fm_text):
        return fm_text, False
    line = f"  - {rm_id}" + (f"   # {note}" if note else "") + "\n"
    m = re.search(r"^related_tickets:\s*\n((?:\s*-\s*\d+.*\n)*)", fm_text, re.M)
    if m:
        return fm_text[:m.end()] + line + fm_text[m.end():], True
    if re.search(r"^related_tickets:\s*(\[\s*\])?\s*$", fm_text, re.M):
        return re.sub(r"^related_tickets:\s*(\[\s*\])?\s*$",
                      "related_tickets:\n" + line.rstrip("\n"), fm_text, count=1, flags=re.M), True
    return fm_text.rstrip("\n") + "\nrelated_tickets:\n" + line, True


def rm_related(fm_text: str, rm_id: int) -> tuple[str, bool]:
    new = re.sub(rf"^\s*-\s*{rm_id}\s*(#.*)?\n", "", fm_text, count=1, flags=re.M)
    return new, new != fm_text


# ── aspect ───────────────────────────────────────────────────────────────────
def scaffold(path: Path, slug: str, title: str, rm_id: int) -> None:
    if not TEMPLATE.is_file():
        out.fail(f"template absent : {TEMPLATE}", "livré par RM1891")
    body = TEMPLATE.read_text(encoding="utf-8")
    for k, v in (("{{slug}}", slug), ("{{title}}", title), ("{{rm_ticket}}", str(rm_id)),
                 ("{{author}}", "karl"), ("{{date}}", date.today().isoformat())):
        body = body.replace(k, v)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def attach(path: Path, rm_id: int) -> bool:
    text = path.read_text(encoding="utf-8")
    fm, body, _ = split_frontmatter(text)
    if not isinstance(fm, dict):
        out.fail(f"aspect sans frontmatter : {path.name}",
                 "ajouter au minimum `aspect:` et `title:` (convention §3.2) — "
                 "cf. `pm-task-doc.py --check`")
    raw_fm = text.split("---", 2)[1]
    new_fm, changed = add_related(raw_fm, rm_id)
    if changed:
        path.write_text("---" + new_fm + "---" + text.split("---", 2)[2], encoding="utf-8")
    return changed


def detach(path: Path, rm_id: int) -> bool:
    text = path.read_text(encoding="utf-8")
    raw_fm = text.split("---", 2)[1]
    new_fm, changed = rm_related(raw_fm, rm_id)
    if changed:
        path.write_text("---" + new_fm + "---" + text.split("---", 2)[2], encoding="utf-8")
    return changed


# ── description du ticket ────────────────────────────────────────────────────
def ref_line(slug: str) -> str:
    return f"{REF_PREFIX} `docs/{slug}.md` (aspect projet, publié en page wiki `[[{wiki_title_for_slug(slug)}]]`)."


def ensure_ref(task_file: Path, slug: str, dry: bool) -> bool:
    """Insère la référence dans la description, via l'outil canonique. Idempotent."""
    text = task_file.read_text(encoding="utf-8")
    _, body, _ = split_frontmatter(text)
    if f"docs/{slug}.md" in body:
        return False
    line = ref_line(slug)
    if re.search(r"^## Contexte\s*$", body, re.M):
        new_body = re.sub(r"^(## Contexte\s*\n)", r"\1\n" + line.replace("\\", "\\\\") + "\n",
                          body, count=1, flags=re.M)
    else:
        new_body = line + "\n\n" + body.lstrip("\n")
    if dry:
        return True
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(new_body.strip() + "\n")
        tmp = fh.name
    rm_id = int(re.match(r"RM(\d+)_", task_file.name).group(1))
    r = subprocess.run([sys.executable, str(HERE / "pm-task-description-update.py"), str(rm_id),
                        "--set-from-file", tmp, "--note",
                        f"Doc partagée adossée : docs/{slug}.md (pm-task-doc)."],
                       capture_output=True, text=True)
    Path(tmp).unlink(missing_ok=True)
    if r.returncode != 0:
        out.fail("échec de la mise à jour de description", (r.stderr or r.stdout).strip()[:400])
    return True


# ── audit ────────────────────────────────────────────────────────────────────
def check(cfg: PMConfig, ref: str | None) -> int:
    projects = ([cfg.resolve_project_ref(ref)[:2]] if ref
                else [(e, p) for e, p, _ in cfg.iter_projects()])
    bad = 0
    for ent, proj in projects:
        docs = Path(cfg.path("docs_dir", entity=ent, project=proj))
        if not docs.is_dir():
            continue
        for f in sorted(docs.glob("*.md")):
            if f.stem in SKIP:
                continue
            fm, _, _ = split_frontmatter(f.read_text(encoding="utf-8"))
            fm = fm if isinstance(fm, dict) else {}
            pbs = []
            if not fm:
                pbs.append("aucun frontmatter")
            else:
                if not fm.get("aspect"):
                    pbs.append("`aspect:` manquant")
                if not fm.get("title"):
                    pbs.append("`title:` manquant")
                if not fm.get("rm_ticket") and not fm.get("related_tickets"):
                    pbs.append("aucun ticket lié")
            if RM_IN_SLUG.search(f.stem):
                pbs.append("slug avec RM-id (URL wiki périssable)")
            if pbs:
                bad += 1
                out.warn(f"{ent}/{proj} : {f.name} — " + " · ".join(pbs))
    out.op("aspects non conformes", extra=str(bad)) if bad else out.op("aspects conformes")
    return bad


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Adosser une doc partagée (aspect) à un ticket")
    ap.add_argument("rm_id", nargs="?", type=int)
    ap.add_argument("--slug", help="slug de l'aspect (stable, sans RM-id)")
    ap.add_argument("--title", help="titre humain (H1) — défaut : dérivé du slug")
    ap.add_argument("--detach", action="store_true", help="délier le ticket de l'aspect")
    ap.add_argument("--list", action="store_true", help="aspects liés à ce ticket")
    ap.add_argument("--check", nargs="?", const="", metavar="PROJET",
                    help="audit de conformité des aspects (tous les projets par défaut)")
    ap.add_argument("--sync", action="store_true", help="publier au wiki dans la foulée")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--porcelain", action="store_true", help="n'imprime que le chemin de l'aspect")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)
    cfg = PMConfig.load()

    if args.check is not None:
        sys.exit(1 if check(cfg, args.check or None) else 0)

    if not args.rm_id:
        ap.error("rm_id requis (ou --check)")
    task_file, ent, proj = cfg.locate_task(args.rm_id)
    if not task_file:
        out.fail(f"ticket RM{args.rm_id} introuvable", "vérifier l'id, ou `mmi-pm task-sync`")
    docs = Path(cfg.path("docs_dir", entity=ent, project=proj))

    if args.list:
        for f in sorted(docs.glob("*.md")):
            if f.stem in SKIP:
                continue
            fm, _, _ = split_frontmatter(f.read_text(encoding="utf-8"))
            if isinstance(fm, dict) and args.rm_id in (fm.get("related_tickets") or []):
                out.value(f"docs/{f.name}") if args.porcelain else out.op("aspect", args.rm_id, f.name)
        return

    if not args.slug:
        ap.error("--slug requis")
    check_slug(args.slug)
    path = docs / f"{args.slug}.md"

    if args.detach:
        if not path.is_file():
            out.fail(f"aspect absent : docs/{args.slug}.md")
        if args.dry_run:
            out.op("délierait", args.rm_id, f"docs/{args.slug}.md"); return
        out.op("délié" if detach(path, args.rm_id) else "déjà délié", args.rm_id, f"docs/{args.slug}.md")
        return

    created = not path.is_file()
    title = args.title or args.slug.replace("-", " ").capitalize()
    if args.dry_run:
        out.op("créerait" if created else "rattacherait", args.rm_id, f"docs/{args.slug}.md")
        return
    if created:
        scaffold(path, args.slug, title, args.rm_id)
        out.op("aspect créé", args.rm_id, f"docs/{args.slug}.md")
    else:
        out.op("aspect rattaché" if attach(path, args.rm_id) else "aspect déjà lié",
               args.rm_id, f"docs/{args.slug}.md")

    if ensure_ref(task_file, args.slug, args.dry_run):
        out.op("référence en description", args.rm_id, f"docs/{args.slug}.md")
    else:
        out.info("référence déjà présente en description")
    out.info("CF link ticket→wiki non posé : aucun champ dédié sur l'instance (cf. docstring)")

    if args.sync:
        r = subprocess.run([sys.executable, str(HERE / "pm-wiki-sync.py"), f"{ent}/{proj}",
                            "--aspect", args.slug], capture_output=True, text=True)
        (out.op("publié au wiki", extra=f"[[{wiki_title_for_slug(args.slug)}]]") if r.returncode == 0
         else out.warn("publication wiki en échec : " + (r.stderr or r.stdout).strip()[:200]))

    if args.porcelain:
        out.value(str(path))


if __name__ == "__main__":
    main()
