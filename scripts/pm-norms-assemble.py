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
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NORMS = REPO / "norms" / "NORMS.md"
SRC = REPO / "norms" / "src"
MANIFEST = SRC / "manifest.yml"
FM_FILE = SRC / "_frontmatter.txt"
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
    print(f"✓ NORMS.md généré ({len(out.splitlines())} lignes) "
          f"depuis {len(read_manifest_sources())} source(s)")
    return 0


def cmd_check(_args):
    want, have = build_text(), NORMS.read_text()
    if want == have:
        print("✓ check OK — NORMS.md == assemble(src) (non-perte vérifiée)")
        return 0
    print("✗ DIVERGENCE : NORMS.md (disque) ≠ assemble(src)", file=sys.stderr)
    sys.stderr.writelines(difflib.unified_diff(
        have.splitlines(True), want.splitlines(True),
        "NORMS.md(disque)", "assemble(src)"))
    return 1


def main():
    p = argparse.ArgumentParser(description="Assemble NORMS.md depuis norms/src/")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("init", "build", "check"):
        sub.add_parser(name)
    args = p.parse_args()
    return {"init": cmd_init, "build": cmd_build, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
