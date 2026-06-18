#!/usr/bin/env python3
"""pm-norms-changes — sais-je si ma connaissance de NORMS est à jour ? (RM2033)

Lit `norms/VERSION` (version NORMS courante, générée par pm-norms-assemble) et
parse `norms/CHANGELOG.md` (Keep a Changelog : entêtes `## [X.Y.Z] - date`) pour :

  --current              imprime la version NORMS courante
  --check <version>      compare une version CONNUE à la courante :
                         « à jour » (exit 0) ou « en retard de N » + liste (exit 1)
  --since <version>      imprime les entrées CHANGELOG des versions > <version>
                         jusqu'à la courante (le DELTA à lire pour se mettre à jour)
  --between <A> <B>      imprime les entrées de l'intervalle (A, B]

Usage type (agent) : au démarrage, comparer sa version NORMS apprise à la courante
→ si en retard, `--since <connue>` donne juste les évolutions à intégrer (au lieu de
relire tout NORMS — esprit KERNEL/modules-à-la-demande, RM1922).
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO / "norms" / "VERSION"
CHANGELOG = REPO / "norms" / "CHANGELOG.md"

HEADER_RE = re.compile(r"^##\s*\[(\d+\.\d+\.\d+)\]\s*-\s*(\S+)", re.M)


def die(msg):
    sys.exit(f"pm-norms-changes: {msg}")


def parse_semver(s):
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", s.strip())
    if not m:
        die(f"version invalide : '{s}' (attendu X.Y.Z)")
    return tuple(int(x) for x in m.groups())


def current_version():
    if not VERSION_FILE.is_file():
        die(f"{VERSION_FILE} absent — lancer `pm-norms-assemble.py build`")
    return VERSION_FILE.read_text().strip()


def parse_changelog():
    """Retourne [(semver_tuple, version_str, date, corps)] trié ASCENDANT."""
    if not CHANGELOG.is_file():
        die(f"{CHANGELOG} absent")
    text = CHANGELOG.read_text(encoding="utf-8")
    matches = list(HEADER_RE.finditer(text))
    entries = []
    for i, m in enumerate(matches):
        ver, date = m.group(1), m.group(2)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip("\n")
        entries.append((parse_semver(ver), ver, date, body))
    entries.sort(key=lambda e: e[0])
    return entries


def entries_in_range(low_excl=None, high_incl=None):
    """Entrées de version dans (low_excl, high_incl] (bornes = tuples semver)."""
    out = []
    for sv, ver, date, body in parse_changelog():
        if low_excl is not None and sv <= low_excl:
            continue
        if high_incl is not None and sv > high_incl:
            continue
        out.append((sv, ver, date, body))
    return out


def print_entries(entries):
    if not entries:
        print("(aucune entrée dans l'intervalle)")
        return
    for _sv, ver, date, body in entries:
        print(f"## [{ver}] - {date}")
        if body:
            print(body)
        print()


def main():
    ap = argparse.ArgumentParser(prog="pm-norms-changes",
                                 description="Diff de versions NORMS (RM2033).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--current", action="store_true", help="version NORMS courante")
    g.add_argument("--check", metavar="VERSION", help="ma version connue est-elle à jour ?")
    g.add_argument("--since", metavar="VERSION", help="delta CHANGELOG depuis cette version")
    g.add_argument("--between", nargs=2, metavar=("A", "B"), help="entrées dans (A, B]")
    args = ap.parse_args()

    cur = current_version()
    cur_sv = parse_semver(cur)

    if args.between:
        a, b = parse_semver(args.between[0]), parse_semver(args.between[1])
        lo, hi = min(a, b), max(a, b)
        print_entries(entries_in_range(lo, hi))
        return 0

    if args.since:
        known = parse_semver(args.since)
        delta = entries_in_range(known, cur_sv)
        if not delta:
            print(f"À jour : version connue {args.since} ≥ courante {cur} — rien à lire.")
            return 0
        print(f"# {len(delta)} version(s) de NORMS depuis {args.since} → {cur} :\n")
        print_entries(delta)
        return 0

    if args.check:
        known = parse_semver(args.check)
        if known == cur_sv:
            print(f"✓ à jour — NORMS v{cur}")
            return 0
        if known > cur_sv:
            print(f"⚠ version connue v{args.check} > courante v{cur} (?) — rien à relire")
            return 0
        behind = entries_in_range(known, cur_sv)
        vers = ", ".join(e[1] for e in behind)
        print(f"✗ EN RETARD de {len(behind)} version(s) : v{args.check} → v{cur}")
        print(f"  versions manquantes : {vers}")
        print(f"  → lire le delta : pm-norms-changes.py --since {args.check}")
        return 1

    # défaut : --current
    print(cur)
    return 0


if __name__ == "__main__":
    sys.exit(main())
