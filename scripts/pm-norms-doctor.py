#!/usr/bin/env python3
"""pm-norms-doctor.py — vérifie les invariants de la structure NORMS (cf. MAINTAINING.md §11).

Invariants DURS (font échouer, exit 1) :
  - non-perte : NORMS.md == assemble(src)   (délègue à pm-norms-assemble.py check)
  - manifest : toute source listée existe ; aucun .md orphelin dans src/

Invariants SOUPLES (avertissent, n'échouent pas en phase 1) :
  - outillage : tout outil cité (pm-*.py, redmine-*.py, mmi-pm-*, --list-next) existe
    réellement ; sinon WARN (trou d'outillage à tracer — cf. RM1923).

Checks FUTURS (affichés SKIPPED tant que l'extraction kernel/modules n'a pas eu lieu) :
  - couverture des déclencheurs KERNEL ↔ obligations des modules (zéro orpheline)
  - en-tête « quand lire ceci » + triggers de chaque module
  - absence de doublon littéral réintroduit
"""
import sys
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "norms" / "src"
SCRIPTS = REPO / "scripts"
SKILLS = REPO / "skills"
ASSEMBLE = SCRIPTS / "pm-norms-assemble.py"

# Outils intentionnellement absents, suivis dans RM1923 → signalés INFO (pas WARN).
KNOWN_GAPS = {
    "pm-doctor.py", "pm-sync-views.py", "pm-sync-links.py", "--list-next",
}

TOOL_RE = re.compile(r"\b((?:pm|redmine)-[a-z0-9-]+\.py)\b")
SKILL_RE = re.compile(r"\b(mmi-pm-[a-z0-9-]+)\b")
LISTNEXT_RE = re.compile(r"--list-next\b")

PASS, WARN, FAIL = "✓", "⚠", "✗"


def src_md_files():
    return sorted(p for p in SRC.glob("*.md"))


def check_assemble():
    r = subprocess.run([sys.executable, str(ASSEMBLE), "check"],
                       capture_output=True, text=True)
    ok = r.returncode == 0
    msg = (r.stdout or r.stderr).strip().splitlines()
    return ok, (msg[0] if msg else "assemble check"), r.stdout + r.stderr


def check_manifest():
    sys.path.insert(0, str(SCRIPTS))
    import importlib.util
    spec = importlib.util.spec_from_file_location("pna", ASSEMBLE)
    pna = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pna)
    listed = set(pna.read_manifest_sources())
    on_disk = {p.name for p in src_md_files()}
    missing = [s for s in listed if not (SRC / s).exists()]
    orphan = sorted(on_disk - listed)
    return missing, orphan


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
    for f in src_md_files():
        txt = f.read_text()
        for m in TOOL_RE.findall(txt):
            found.setdefault(m, set()).add(f.name)
        for m in SKILL_RE.findall(txt):
            found.setdefault(m, set()).add(f.name)
        if LISTNEXT_RE.search(txt):
            found.setdefault("--list-next", set()).add(f.name)
    return found


def main():
    rc = 0
    print("== pm-norms-doctor ==")

    # DUR 1 — non-perte
    ok, summary, _out = check_assemble()
    print(f"  {PASS if ok else FAIL} non-perte : {summary}")
    if not ok:
        rc = 1

    # DUR 2 — manifest
    missing, orphan = check_manifest()
    if missing:
        print(f"  {FAIL} manifest : sources introuvables : {', '.join(missing)}")
        rc = 1
    elif orphan:
        print(f"  {FAIL} manifest : .md orphelins (hors manifest) : {', '.join(orphan)}")
        rc = 1
    else:
        print(f"  {PASS} manifest : sources cohérentes, pas d'orphelin")

    # SOUPLE — outillage cité
    tools = scan_tools()
    gaps, known = [], []
    for tok in sorted(tools):
        if tool_exists(tok):
            continue
        (known if tok in KNOWN_GAPS else gaps).append(tok)
    if known:
        print(f"  · outils absents connus (suivis RM1923) : {', '.join(known)}")
    if gaps:
        print(f"  {WARN} outils cités INTROUVABLES (trou d'outillage ?) : {', '.join(gaps)}")
    else:
        print(f"  {PASS} outillage : tout outil cité (hors trous connus) existe")

    # FUTURS
    for name in ("couverture déclencheurs KERNEL↔modules",
                 "en-têtes « quand lire ceci » des modules",
                 "absence de doublon littéral"):
        print(f"  · SKIPPED ({name}) — structure non encore extraite")

    print(f"== {'OK' if rc == 0 else 'ÉCHEC'} ==")
    return rc


if __name__ == "__main__":
    sys.exit(main())
