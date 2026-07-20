#!/usr/bin/env python3
"""pm-norms-assemble.py — génère norms/NORMS.md par concaténation des sources norms/src/.

Source de vérité = norms/src/ (manifest.yml + _frontmatter.txt + fichiers ordonnés).
NORMS.md est un ARTEFACT généré — ne pas l'éditer à la main (cf. norms/MAINTAINING.md).

Sous-commandes :
  init    bootstrap : découpe le NORMS.md courant en src/_frontmatter.txt +
          src/_full-body.md + manifest.yml (identité — contenu préservé).
  build   (re)génère NORMS.md depuis src/.
  check   vérifie que NORMS.md sur disque == build() (preuve de non-perte) ;
          exit 1 + diff si divergence.

L'extraction (RM1922) carvera _full-body.md en kernel + modules ; `check` garde la
non-perte verte à chaque étape.
"""
import sys
import argparse
import difflib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NORMS = REPO / "norms" / "NORMS.md"
SRC = REPO / "norms" / "src"
MANIFEST = SRC / "manifest.yml"
FM_FILE = SRC / "_frontmatter.txt"
VERSION_FILE = REPO / "norms" / "VERSION"   # version NORMS seule (RM2033) — généré depuis le frontmatter
BANNER = ("<!-- ⚠ FICHIER GÉNÉRÉ par scripts/pm-norms-assemble.py depuis norms/src/ — "
          "NE PAS ÉDITER À LA MAIN (voir norms/MAINTAINING.md) -->")


def read_manifest_sources():
    """Liste ordonnée des fichiers sources (mini-parseur : lignes '  - <fichier>')."""
    sources = []
    for line in MANIFEST.read_text().splitlines():
        s = line.strip()
        if s.startswith("#") or not s:
            continue
        if s.startswith("- "):
            name = s[2:].split("#", 1)[0].strip()   # retire un commentaire inline
            if name:
                sources.append(name)
    return sources


def build_text():
    fm = FM_FILE.read_text()
    body = "".join((SRC / name).read_text() for name in read_manifest_sources())
    return "---\n" + fm + "---\n" + BANNER + "\n" + body


def norms_version():
    """Version NORMS = `schema_version` du frontmatter (source unique). RM2033.

    Vérifie au passage la cohérence avec le titre `— vX.Y.Z` du corps (anti-drift).
    """
    m = re.search(r'schema_version:\s*"?(\d+\.\d+\.\d+)"?', FM_FILE.read_text())
    if not m:
        sys.exit("✗ schema_version introuvable dans _frontmatter.txt")
    ver = m.group(1)
    title = (SRC / "_full-body.md").read_text()
    tm = re.search(r"—\s*v(\d+\.\d+\.\d+)", title)
    if tm and tm.group(1) != ver:
        sys.exit(f"✗ drift de version : frontmatter {ver} ≠ titre _full-body.md v{tm.group(1)}")
    return ver


def cmd_init(_args):
    if SRC.exists():
        print(f"✗ {SRC} existe déjà — init refusé (déjà bootstrappé)", file=sys.stderr)
        return 1
    text = NORMS.read_text()
    if not text.startswith("---\n"):
        print("✗ NORMS.md ne commence pas par un frontmatter '---'", file=sys.stderr)
        return 1
    rest = text[4:]
    end = rest.index("---\n")           # premier '---' = fermeture du frontmatter
    fm, body = rest[:end], rest[end + 4:]
    SRC.mkdir()
    FM_FILE.write_text(fm)
    (SRC / "_full-body.md").write_text(body)
    MANIFEST.write_text(
        "# Manifest d'assemblage de NORMS.md (ordre des sources).\n"
        "# Bootstrap identité : une seule source = le corps complet courant.\n"
        "# L'extraction (RM1922) carvera _full-body.md en kernel + modules,\n"
        "# en gardant `pm-norms-assemble.py check` vert à chaque étape.\n"
        "sources:\n"
        "  - _full-body.md\n"
    )
    print(f"✓ bootstrap écrit dans {SRC.relative_to(REPO)} "
          f"(_frontmatter.txt, _full-body.md, manifest.yml)")
    print("  → lancer ensuite : pm-norms-assemble.py build  puis  check")
    return 0


def cmd_build(_args):
    out = build_text()
    NORMS.write_text(out)
    ver = norms_version()
    VERSION_FILE.write_text(ver + "\n")
    print(f"✓ NORMS.md généré ({len(out.splitlines())} lignes) "
          f"depuis {len(read_manifest_sources())} source(s)")
    print(f"✓ norms/VERSION = {ver}")
    return 0


def cmd_check(_args):
    want, have = build_text(), NORMS.read_text()
    if want != have:
        print("✗ DIVERGENCE : NORMS.md (disque) ≠ assemble(src)", file=sys.stderr)
        sys.stderr.writelines(difflib.unified_diff(
            have.splitlines(True), want.splitlines(True),
            "NORMS.md(disque)", "assemble(src)"))
        return 1
    # garde de cohérence VERSION (RM2033)
    ver = norms_version()
    have_ver = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else None
    if have_ver != ver:
        print(f"✗ norms/VERSION ({have_ver}) ≠ version frontmatter ({ver}) — lancer `build`",
              file=sys.stderr)
        return 1
    print(f"✓ check OK — NORMS.md == assemble(src) ; norms/VERSION = {ver} (cohérent)")
    return 0


CHEATSHEET_FILE = Path(__file__).resolve().parent.parent / "norms" / "CHEATSHEET.md"
CHEATSHEET_BUDGET_TOKENS = 1200

_FLOWS = """## Flux nominaux

- **prendre un ticket** : `pm-task-take.py <id> [--no-branch]` → affiche le brief
- **livrer** : `pm-task-deliver.py <id> --summary -` (résumé rédigé sur stdin)
- **créer un ticket** : `ID=$(pm-task-add.py --title … --porcelain)` — jamais d'id prédit
- **MR** : `pm-mr.py create <RMid>` puis `pm-mr.py merge <iid> --expect-rm <RMid>`
- **lire** : `pm-task-brief.py <id>` · `pm-task-log.py <id> --tail N [--grep RX]` ·
  `pm-task-show.py <id> --field a,b.c`
- partout : sortie dense par défaut, `--verbose` = détail, `--help-full` = aide complète
"""


def cmd_cheatsheet(_args):
    """Génère norms/CHEATSHEET.md : 1 ligne par outil (docstring), + flux nominaux."""
    lines = ["# CHEATSHEET outillage PM — généré, ne pas éditer",
             "", "> `pm-norms-assemble.py cheatsheet` (RM2367, CDC RM2316 § S6). "
             "Détail d'un outil : `<script> --help` (court) / `--help-full`.", "",
             _FLOWS, "## Outils", ""]
    scripts_dir = Path(__file__).resolve().parent
    # outils du QUOTIDIEN agent uniquement — l'infra/migrations/one-shots restent
    # accessibles via --help, pas besoin d'occuper le contexte de chaque session
    exclude = re.compile(
        r"^karl-|-migrate|-backfill|-recable|-rename|-coloc|-flip|test|"
        r"^pm-(norms|meta|docs|turn|pre|post|zfs|hooks|protect|provision|env-init)")
    for p in sorted(scripts_dir.glob("*.py")):
        if not re.match(r"(pm|redmine|karl)-", p.name) or exclude.search(p.name):
            continue
        first = ""
        m = re.search(r'"""(.+?)(?:\n|""")', p.read_text(encoding="utf-8"))
        if m:
            first = m.group(1).strip()
            first = re.sub(r"^[\w.-]+\s+—\s+", "", first)  # retire le préfixe « nom — »
            first = re.sub(r"\s*\((?:RM|CDC)[^)]*\)\.?$", "", first)  # réfs tickets
            if len(first) > 48:
                first = first[:45].rstrip() + "…"
        lines.append(f"- `{p.name[:-3]}` — {first}")
    text = "\n".join(lines) + "\n"
    CHEATSHEET_FILE.write_text(text, encoding="utf-8")
    tokens = int(len(text.encode("utf-8")) / 3.6)
    status = "✓" if tokens <= CHEATSHEET_BUDGET_TOKENS else "✗ BUDGET DÉPASSÉ"
    print(f"{status} CHEATSHEET.md généré : {len(lines)} lignes, ≈{tokens} tokens "
          f"(budget {CHEATSHEET_BUDGET_TOKENS})")
    return 0 if tokens <= CHEATSHEET_BUDGET_TOKENS else 1


def main():
    p = argparse.ArgumentParser(description="Assemble NORMS.md depuis norms/src/")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("init", "build", "check", "cheatsheet"):
        sub.add_parser(name)
    args = p.parse_args()
    return {"init": cmd_init, "build": cmd_build, "check": cmd_check,
            "cheatsheet": cmd_cheatsheet}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
