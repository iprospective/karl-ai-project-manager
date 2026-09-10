#!/usr/bin/env python3
"""pm-cockpit-remap — où reporter une branche partie de l'ancien index.html.

Pendant la refonte du cockpit (RM2889), un ticket ouvert avant la migration
d'un domaine modifie encore `index.html` là où le code n'est plus. Git ne
sait pas suivre un fragment extrait d'un monolithe ; la carte de migration,
si. Ce script lit le diff de la branche sur `index.html`, rattache chaque
hunk au symbole de premier niveau qui l'englobe DANS LA PRÉ-IMAGE (les
lignes d'aujourd'hui ont dérivé), et imprime pour chacun :

  - le symbole touché, le nombre de hunks ;
  - s'il est encore dans index.html sur `dev` : rien à reporter, merge normal ;
  - sinon : le fichier cible d'après MIGRATION-MAP.tsv, le lot, et l'état
    (domaine migré ou pas encore).

Exemple :
  pm-cockpit-remap.py 2229-fiche-ticket-protocole
  pm-cockpit-remap.py origin/2808-karl-agent-le-prompt-initial-du-cockpit-m1-s79 --base origin/dev
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

PATH = "deploy/karl-agent/cockpit/index.html"
DECL = re.compile(r"^(?:async\s+function|function|class|const|let|var)\s+([A-Za-z_$][\w$]*)")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"git {' '.join(args)} : {r.stderr.strip()}")
    return r.stdout


def symbols(lines):
    return [(i, m.group(1)) for i, l in enumerate(lines, 1) if (m := DECL.match(l))]


def locate(syms, ln):
    best = "«hors symbole (CSS/HTML/en-tête)»"
    for i, name in syms:
        if i <= ln:
            best = name
        else:
            break
    return best


def read_map(repo):
    p = Path(repo) / "deploy/karl-agent/cockpit/MIGRATION-MAP.tsv"
    out = {}
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
        if n == 0 or not line.strip():
            continue
        f = line.split("\t")
        out[f[0]] = {"lot": f[2], "domaine": f[3], "couche": f[4], "cible": f[5]}
    return out


def main():
    ap = argparse.ArgumentParser(description="reporter une branche sur le cockpit migré")
    ap.add_argument("branch", help="branche à reporter (locale ou origin/…)")
    ap.add_argument("--base", default="origin/dev", help="base d'intégration (défaut : origin/dev)")
    ap.add_argument("--repo", default=".", help="dépôt de code (défaut : cwd)")
    args = ap.parse_args()
    branch = args.branch if "/" in args.branch else f"origin/{args.branch}"
    base = git(args.repo, "merge-base", args.base, branch).strip()
    pre = git(args.repo, "show", f"{base}:{PATH}").split("\n")
    syms = symbols(pre)
    diff = git(args.repo, "diff", "-U0", base, branch, "--", PATH)
    if not diff.strip():
        print(f"{args.branch} ne touche pas {PATH} : rien à reporter.")
        return 0
    hunks = {}
    for line in diff.split("\n"):
        m = HUNK.match(line)
        if m:
            s = locate(syms, max(int(m.group(1)), 1))
            hunks[s] = hunks.get(s, 0) + 1
    cur = set(name for _, name in symbols(git(args.repo, "show", f"{args.base}:{PATH}").split("\n")))
    mmap = read_map(args.repo)
    src = Path(args.repo) / "deploy/karl-agent/cockpit/src"
    print(f"{args.branch} — base {base[:8]} — {sum(hunks.values())} hunk(s) sur {len(hunks)} symbole(s)\n")
    print(f"{'symbole':<28}{'hunks':>5}  verdict")
    print("-" * 78)
    todo = 0
    for s, n in sorted(hunks.items(), key=lambda x: -x[1]):
        if s in cur:
            print(f"{s:<28}{n:>5}  toujours dans index.html sur {args.base} → merge git normal")
            continue
        e = mmap.get(s)
        if not e:
            print(f"{s:<28}{n:>5}  ⚠ absent de index.html ET de la carte — chercher à la main")
            todo += 1
            continue
        migrated = (src / e["cible"]).exists() or any(src.glob(f"**/{Path(e['cible']).name}"))
        etat = "domaine MIGRÉ — reporter dans" if migrated else "pas encore migré (sera dans)"
        print(f"{s:<28}{n:>5}  {etat} {e['cible']}  [{e['lot']} · {e['couche']}]")
        todo += 1
    print(f"\n{todo} symbole(s) à reporter à la main, {len(hunks) - todo} qui mergent normalement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
