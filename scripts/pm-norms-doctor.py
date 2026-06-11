#!/usr/bin/env python3
"""pm-norms-doctor.py — vérifie les invariants de la structure NORMS (cf. MAINTAINING.md §11).

Invariants DURS (font échouer, exit 1) :
  - fraîcheur   : NORMS.md == assemble(src)   (délègue à pm-norms-assemble.py check) ;
                  garantit que les lecteurs voient toujours le build le plus à jour.
  - non-perte   : COUVERTURE — chaque ligne de l'oracle (_original-frozen.md) est
                  présente verbatim (normalisée) dans les sources actives du manifest,
                  SAUF écart inscrit dans dedup-ledger.yml. Tant que l'oracle n'existe
                  pas, on reste en mode « identité (bootstrap) » (assuré par la fraîcheur).
  - manifest    : toute source listée existe ; aucun .md orphelin (hors oracle).

Invariants SOUPLES (avertissent, n'échouent pas en phase d'extraction) :
  - outillage   : tout outil cité (pm-*.py, redmine-*.py, mmi-pm-*, --list-next) existe ;
                  sinon WARN (trou d'outillage à tracer — cf. RM1923).

Checks FUTURS (SKIPPED tant que le KERNEL n'est pas écrit) :
  - couverture des déclencheurs KERNEL ↔ obligations des modules (zéro orpheline)
  - en-tête « quand lire ceci » + triggers de chaque module
"""
import sys
import re
import subprocess
import importlib.util
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "norms" / "src"
SCRIPTS = REPO / "scripts"
SKILLS = REPO / "skills"
ASSEMBLE = SCRIPTS / "pm-norms-assemble.py"
ORACLE = SRC / "_original-frozen.md"
LEDGER = SRC / "dedup-ledger.yml"

KNOWN_GAPS = {"pm-doctor.py", "pm-sync-views.py", "pm-sync-links.py", "--list-next",
              "mmi-pm-git"}

TOOL_RE = re.compile(r"\b((?:pm|redmine)-[a-z0-9-]+\.py)\b")
SKILL_RE = re.compile(r"\b(mmi-pm-[a-z0-9-]+)\b")
LISTNEXT_RE = re.compile(r"--list-next\b")

PASS, WARN, FAIL = "✓", "⚠", "✗"


def _pna():
    spec = importlib.util.spec_from_file_location("pna", ASSEMBLE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def norm(line):
    return " ".join(line.split())


def active_source_files():
    """Fichiers réellement assemblés dans NORMS.md (ordre du manifest)."""
    return [SRC / name for name in _pna().read_manifest_sources()]


def check_freshness():
    r = subprocess.run([sys.executable, str(ASSEMBLE), "check"],
                       capture_output=True, text=True)
    return r.returncode == 0, (r.stdout or r.stderr).strip().splitlines()[-1:]


def check_coverage():
    """Retourne (mode, uncovered_lines). mode='identité' si pas encore d'oracle."""
    if not ORACLE.exists():
        return "identité (bootstrap)", []
    oracle = {norm(l) for l in ORACLE.read_text().splitlines() if norm(l)}
    active = set()
    for f in active_source_files():
        active |= {norm(l) for l in f.read_text().splitlines() if norm(l)}
    covered = set()
    if LEDGER.exists():
        data = yaml.safe_load(LEDGER.read_text()) or {}
        blocks = list(data.get("removed") or [])
        blocks += [e["old"] for e in (data.get("rewritten") or [])
                   if isinstance(e, dict) and e.get("old")]
        for blk in blocks:                          # une entrée peut être un bloc multi-lignes
            for ol in str(blk).splitlines():
                if norm(ol):
                    covered.add(norm(ol))
    uncovered = sorted(oracle - active - covered)
    return "couverture", uncovered


def check_manifest():
    listed = set(_pna().read_manifest_sources())
    on_disk = {str(p.relative_to(SRC)) for p in SRC.rglob("*.md")
               if not p.name.startswith("_original")}
    missing = [s for s in listed if not (SRC / s).exists()]
    orphan = sorted(on_disk - listed)
    return missing, orphan


def check_kernel():
    """Tout module référencé par le KERNEL (modules/X.md) doit exister. None si pas de KERNEL."""
    kernel = SRC / "NORMS-KERNEL.md"
    if not kernel.exists():
        return None
    refs = set(re.findall(r"modules/[a-z0-9-]+\.md", kernel.read_text()))
    return sorted(r for r in refs if not (SRC / r).exists())


def check_module_headers():
    """Chaque module doit porter son en-tête « quand lire ceci » (point d'entrée lisible)."""
    return [f.name for f in sorted(SRC.glob("modules/*.md"))
            if "quand lire ceci" not in f.read_text()]


def check_fences():
    """Chaque source doit avoir un nombre PAIR de ``` (sinon un bloc de code a été
    coupé entre deux fichiers — invisible à la couverture qui ne voit que les lignes)."""
    bad = []
    for f in active_source_files():
        n = sum(1 for l in f.read_text().splitlines() if l.lstrip().startswith("```"))
        if n % 2:
            bad.append(f"{f.relative_to(SRC)} ({n})")
    return bad


def tool_exists(token):
    if token == "--list-next":
        return False
    if token.endswith(".py"):
        return (SCRIPTS / token).exists()
    if token.startswith("mmi-pm-"):
        return (SKILLS / token / "SKILL.md").exists() or (SKILLS / token).exists()
    return True


def scan_tools():
    found = {}
    for f in active_source_files():
        txt = f.read_text()
        for m in TOOL_RE.findall(txt) + SKILL_RE.findall(txt):
            found.setdefault(m, set()).add(f.name)
        if LISTNEXT_RE.search(txt):
            found.setdefault("--list-next", set()).add(f.name)
    return found


def main():
    rc = 0
    print("== pm-norms-doctor ==")

    ok, tail = check_freshness()
    print(f"  {PASS if ok else FAIL} fraîcheur : {tail[0] if tail else 'assemble check'}")
    rc |= 0 if ok else 1

    mode, uncovered = check_coverage()
    if uncovered:
        print(f"  {FAIL} non-perte ({mode}) : {len(uncovered)} ligne(s) de l'oracle "
              f"absentes des sources et hors registre :")
        for s in uncovered[:10]:
            print(f"        · {s[:100]}")
        if len(uncovered) > 10:
            print(f"        … (+{len(uncovered) - 10})")
        rc |= 1
    else:
        print(f"  {PASS} non-perte ({mode}) : oracle entièrement couvert")

    missing, orphan = check_manifest()
    if missing:
        print(f"  {FAIL} manifest : sources introuvables : {', '.join(missing)}")
        rc |= 1
    elif orphan:
        print(f"  {FAIL} manifest : .md orphelins (hors manifest) : {', '.join(orphan)}")
        rc |= 1
    else:
        print(f"  {PASS} manifest : sources cohérentes, pas d'orphelin")

    bad_fences = check_fences()
    if bad_fences:
        print(f"  {FAIL} fences : bloc(s) de code coupé(s) (``` impair) : {', '.join(bad_fences)}")
        rc |= 1
    else:
        print(f"  {PASS} fences : tous les blocs de code équilibrés")

    tools = scan_tools()
    gaps = sorted(t for t in tools if not tool_exists(t) and t not in KNOWN_GAPS)
    known = sorted(t for t in tools if not tool_exists(t) and t in KNOWN_GAPS)
    if known:
        print(f"  · outils absents connus (suivis RM1923) : {', '.join(known)}")
    if gaps:
        print(f"  {WARN} outils cités INTROUVABLES (trou d'outillage ?) : {', '.join(gaps)}")
    else:
        print(f"  {PASS} outillage : tout outil cité (hors trous connus) existe")

    kmiss = check_kernel()
    if kmiss is None:
        print(f"  · SKIPPED (déclencheurs KERNEL) — pas de KERNEL")
    elif kmiss:
        print(f"  {FAIL} déclencheurs KERNEL : modules référencés introuvables : {', '.join(kmiss)}")
        rc |= 1
    else:
        print(f"  {PASS} déclencheurs KERNEL : tous les modules référencés existent")
    hmiss = check_module_headers()
    if hmiss:
        print(f"  {FAIL} en-têtes modules : « quand lire ceci » manquant : {', '.join(hmiss)}")
        rc |= 1
    else:
        print(f"  {PASS} en-têtes : tous les modules ont leur « quand lire ceci »")

    print(f"== {'OK' if rc == 0 else 'ÉCHEC'} ==")
    return rc


if __name__ == "__main__":
    sys.exit(main())
