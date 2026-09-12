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


def cmd_cheatsheet(args):
    """Génère norms/CHEATSHEET.md : 1 ligne par outil (docstring), + flux nominaux."""
    lines = ["# CHEATSHEET outillage PM — généré, ne pas éditer",
             "", "> `pm-norms-assemble.py cheatsheet` (RM2367, CDC RM2316 § S6). "
             "Détail d'un outil : `<script> --help` (court) / `--help-full`.", "",
             "> Ce condensé ne porte que les outils du QUOTIDIEN. La liste **exhaustive** "
             "(tous les scripts, groupés par domaine, + les bibliothèques) est dans "
             "[`scripts/INDEX.md`](../scripts/INDEX.md) — à ouvrir quand l'outil cherché "
             "n'est pas ici.", "",
             _FLOWS, "## Outils", ""]
    scripts_dir = Path(__file__).resolve().parent
    # Liste BLANCHE, et non une liste noire d'exclusions (RM3110). Une liste noire
    # se périme par construction : chaque script ajouté au dépôt y entre par défaut,
    # la cheatsheet enfle en silence et finit par crever son budget — constaté le
    # 2026-09-12, 47 outils listés contre 95 après régénération, 2 170 tokens pour
    # un plafond de 1 200. Ce qui n'est pas ici n'est pas perdu : c'est dans
    # scripts/INDEX.md, exhaustif et ouvert à la demande.
    KEEP = {
        # le ticket, de bout en bout
        "pm-task-add", "pm-task-take", "pm-task-brief", "pm-task-show", "pm-task-list",
        "pm-task-log", "pm-task-status-update", "pm-task-comment", "pm-task-deliver",
        "pm-task-protocol", "pm-task-link", "pm-task-sync", "pm-task-think",
        "pm-task-blockers", "pm-task-description-update", "pm-task-deploy",
        "pm-task-implementation", "pm-task-cd",
        # code, branche, livraison
        "pm-branch-start", "pm-mr", "pm-promote", "pm-worktree", "pm-test",
        # environnements de travail
        "pm-env-session", "pm-env-deploy", "pm-env-expose",
        # séance
        "pm-session-status", "pm-think-merge",
        # Redmine, quand l'outil de tâche ne suffit pas
        "redmine-post-note", "redmine-fetch-updates",
    }
    for p in sorted(scripts_dir.glob("*.py")):
        if p.name[:-3] not in KEEP:
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
    if getattr(args, "check", False):
        cur = CHEATSHEET_FILE.read_text(encoding="utf-8") if CHEATSHEET_FILE.exists() else ""
        if cur != text:
            print("✗ CHEATSHEET.md PÉRIMÉ — régénère : pm-norms-assemble.py cheatsheet")
            return 1
        print("✓ CHEATSHEET.md à jour")
        return 0
    CHEATSHEET_FILE.write_text(text, encoding="utf-8")
    tokens = int(len(text.encode("utf-8")) / 3.6)
    status = "✓" if tokens <= CHEATSHEET_BUDGET_TOKENS else "✗ BUDGET DÉPASSÉ"
    print(f"{status} CHEATSHEET.md généré : {len(lines)} lignes, ≈{tokens} tokens "
          f"(budget {CHEATSHEET_BUDGET_TOKENS})")
    return 0 if tokens <= CHEATSHEET_BUDGET_TOKENS else 1


INDEX_FILE = Path(__file__).resolve().parent.parent / "scripts" / "INDEX.md"

# Domaines, dans l'ordre d'évaluation : le PREMIER motif qui accroche gagne.
# L'ordre n'est pas alphabétique mais décroissant en spécificité — `pm-task-think`
# doit tomber dans « Tâches », pas dans un « think » à part.
_DOMAINS = [
    ("Tâches & tickets", r"^(pm-task|pm-think|pm-tick|validate-task|priority|pm-cf-)"),
    ("Projets, clients & contacts", r"^(pm-project|pm-client|pm-contact|pm-index|pm-partner)"),
    ("Git, MR & MEP", r"^(pm-branch|pm-mr|pm-promote|pm-git|pm-gitlab|pm-protect|pm-repo|"
                     r"pm-worktree|pm-workspace|pm-sync-push|pm-pre-|pm-post-)"),
    ("Environnements", r"^pm-env"),
    ("Sessions, cockpit & agents", r"^(karl|pm-session|pm-turn|pm-proclive|session-mark|pm-transcript)"),
    ("Redmine", r"^redmine"),
    ("NORMS, CDC & documentation", r"^(pm-norms|pm-cdc|pm-docs|pm-wiki|pm-glossaire|pm-dict|"
                                   r"pm-decisions|pm-task-doc|pm-skills)"),
    ("Mesure, coût & reporting", r"^(pm-stats|pm-conso|pm-context|pm-bench|pm-timesheet|"
                                 r"pm-file-heatmap|pm-dashboard|pm-pricing|pm-reporting|pm-log)"),
    ("Secrets & coffres", r"(vault|secret|provider)"),
    ("Ordonnancement & notifications", r"^(pm-scheduler|pm-notify|pm-client-notify|pm-lock|pm-events)"),
    ("Installation, migration & maintenance", r"^(install|provision|pm-core-update|pm-doctor|pm-perms|"
                                              r"pm-hooks|pm-claude-hooks|pm-engine|pm-meta|pm-zfs|"
                                              r"pm-resolver|pm-tags|pm-registry|pm-license|pm-roles|"
                                              r"pm-cockpit|pm-site-test|pm-test|mmi-pm|core-lock|cron)"),
]
_FALLBACK = "Divers"


def _summary(path: Path, limit: int = 72) -> str:
    """Première phrase de la docstring de module, débarrassée de ses scories.

    Le nom du script en préfixe (« pm-truc — fait ceci ») et les références de
    ticket (« (RM1234) ») sont retirés : ils sont déjà connus du lecteur ou sans
    valeur pour choisir un outil.
    """
    try:
        txt = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r'"""(.+?)(?:\n|""")', txt)
    if not m:
        return ""
    s = m.group(1).strip()
    s = re.sub(r"^[\w.-]+\s+[—-]\s+", "", s)
    s = re.sub(r"\s*\((?:RM|CDC)[^)]*\)\.?$", "", s).strip()
    if len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return s


def _domain_of(name: str) -> str:
    for label, pattern in _DOMAINS:
        if re.search(pattern, name):
            return label
    return _FALLBACK


def build_index_text() -> tuple:
    """Construit scripts/INDEX.md. Retourne (texte, liste des scripts sans docstring).

    Deux populations, qu'un agent n'invoque PAS de la même façon :
      * les **exécutables** (`pm-*.py`, `redmine-*.py`, `karl-*.py`) — ce qu'on lance ;
      * les **bibliothèques** (`pm_*.py`, avec un souligné) — ce qu'on importe.
    Les mélanger produit un index où l'on cherche en vain la ligne de commande de
    `pm_paths`. Les tests (`test_*`) sont hors sujet ici.
    """
    scripts_dir = Path(__file__).resolve().parent
    execs, libs, mutes = {}, [], []
    for p in sorted(scripts_dir.glob("*.py")):
        n = p.name[:-3]
        if n.startswith("test_") or n.startswith("test-"):
            continue
        summary = _summary(p)
        if not summary:
            mutes.append(n)
        if re.match(r"^pm_", n):
            libs.append((n, summary))
        elif re.match(r"^(pm|redmine|karl|mmi)-", n):
            execs.setdefault(_domain_of(n), []).append((n, summary))
    lines = [
        "# INDEX des scripts PM — généré, ne pas éditer",
        "",
        "> `pm-norms-assemble.py index`. Vérifié par `pm-norms-doctor` (fraîcheur).",
        "> Détail d'un outil : `<script> --help` (court) · `--help-full` (docstring entière).",
        "> Tout `pm-<verbe>.py` s'invoque aussi `mmi-pm <verbe>` (verbe en UN token tiret).",
        "> Condensé des outils du quotidien, préchargé par tous : `norms/CHEATSHEET.md`.",
        "",
        "## Exécutables",
        "",
    ]
    for label, _ in _DOMAINS + [(_FALLBACK, "")]:
        rows = execs.get(label)
        if not rows:
            continue
        lines += [f"### {label}", ""]
        lines += [f"- `{n}` — {s}" if s else f"- `{n}`" for n, s in rows]
        lines.append("")
    lines += ["## Bibliothèques (importées, pas lancées)", ""]
    lines += [f"- `{n}` — {s}" if s else f"- `{n}`" for n, s in libs]
    lines.append("")
    return "\n".join(lines), mutes


def cmd_index(args):
    """Génère scripts/INDEX.md : tous les scripts, groupés par domaine."""
    text, mutes = build_index_text()
    if getattr(args, "check", False):
        cur = INDEX_FILE.read_text(encoding="utf-8") if INDEX_FILE.exists() else ""
        if cur != text:
            print("✗ scripts/INDEX.md PÉRIMÉ — régénère : pm-norms-assemble.py index")
            return 1
        print("✓ scripts/INDEX.md à jour")
        return 0
    INDEX_FILE.write_text(text, encoding="utf-8")
    tokens = int(len(text.encode("utf-8")) / 3.6)
    n = text.count("\n- `")
    print(f"✓ INDEX.md généré : {n} script(s), ≈{tokens} tokens")
    if mutes:
        # Pas une erreur : un trou à combler, nommé. Un script sans docstring est
        # invisible à l'index — donc introuvable par qui cherche un outil.
        print(f"  ⚠ {len(mutes)} sans docstring de module : {', '.join(mutes[:8])}"
              + (" …" if len(mutes) > 8 else ""))
    return 0


def main():
    p = argparse.ArgumentParser(description="Assemble NORMS.md depuis norms/src/")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("init", "build", "check"):
        sub.add_parser(name)
    for name in ("cheatsheet", "index"):
        sp = sub.add_parser(name)
        sp.add_argument("--check", action="store_true",
                        help="ne réécrit rien : échoue si le fichier sur disque est périmé")
    args = p.parse_args()
    return {"init": cmd_init, "build": cmd_build, "check": cmd_check,
            "cheatsheet": cmd_cheatsheet, "index": cmd_index}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
