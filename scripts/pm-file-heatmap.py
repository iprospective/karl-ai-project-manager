#!/usr/bin/env python3
"""pm-file-heatmap — carte de chaleur d'un fichier : qui l'a touché, et où.

Avant de refactorer un gros fichier, la question qui décide du plan n'est pas
« combien de lignes ? » mais « **combien de tickets distincts** ont touché
chaque zone ? ». C'est ce nombre qui dit le coût de réintégration des
développements concurrents — donc l'ordre dans lequel découper le chantier :
du plus froid au plus chaud.

Attribution **exacte**, pas heuristique : chaque *hunk* d'un commit est rattaché
à la déclaration de premier niveau qui le précède dans la **pré-image de ce
commit** (et non dans le fichier d'aujourd'hui, dont les lignes ont dérivé).

Zones reconnues, selon l'extension :
  .html   fonctions JS en colonne 0, règles CSS de `<style>`, blocs HTML
          (jusqu'à l'indentation 4) — le cas du cockpit karl-agent ;
  .py     `def` / `async def` / `class` en colonne 0 ;
  .js     `function` / `class` / `const|let|var` en colonne 0 ;
  autre   toute ligne commençant en colonne 0 (repli générique).

Le décompte porte sur les **tickets** (RM-id du sujet de commit), pas sur les
commits : deux commits d'un même ticket sont une seule réintégration.

Exemples :
  pm-file-heatmap.py deploy/karl-agent/cockpit/index.html
  pm-file-heatmap.py scripts/karl-agent.py --since 180.days --top 20
  pm-file-heatmap.py <chemin> --json /tmp/heat.json --bands 0
"""
import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict

JS_DECL = re.compile(r"^(?:async\s+function|function|class|const|let|var)\s+([A-Za-z_$][\w$]*)")
PY_DECL = re.compile(r"^(?:async\s+def|def|class)\s+([A-Za-z_][\w]*)")
CSS_RULE = re.compile(r"^  ([^ /][^{]*)\{")
HTML_TAG = re.compile(r"^ {0,4}<([a-z]+)\b([^>]*)>?$|^ {0,4}<([a-z]+)\b([^>]*)>")
ID_ATTR = re.compile(r'id="([^"]+)"')
CLASS_ATTR = re.compile(r'class="([^"]+)"')
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
RM_ID = re.compile(r"RM\d{3,4}")


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True
    ).stdout


def markers_html(lines):
    """Marqueurs d'un HTML monopage : le mode courant décide de la grammaire.

    Sans ce suivi de mode, la règle CSS `^  sélecteur {` capturerait la moitié
    des blocs indentés du JavaScript.
    """
    out, mode = [], "head"
    for i, line in enumerate(lines, 1):
        s = line.lstrip()
        if s.startswith("<style"):
            mode = "css"
            out.append((i, "<style>"))
            continue
        if s.startswith("</style"):
            mode = "head"
            continue
        if s.startswith("<body"):
            mode = "html"
            out.append((i, "<body>"))
            continue
        if s.startswith("<script") and "src=" not in line:
            mode = "js"
            out.append((i, "<script>"))
            continue
        if s.startswith("</script"):
            mode = "html" if mode == "js" else mode
            continue
        if mode == "js":
            m = JS_DECL.match(line)
            if m:
                out.append((i, m.group(1)))
        elif mode == "css":
            m = CSS_RULE.match(line)
            if m:
                out.append((i, "css:" + " ".join(m.group(1).split())[:44]))
        elif mode == "html":
            m = HTML_TAG.match(line)
            if not m:
                continue
            tag = m.group(1) or m.group(3)
            attrs = m.group(2) or m.group(4) or ""
            mid, mcl = ID_ATTR.search(attrs), CLASS_ATTR.search(attrs)
            if mid:
                out.append((i, f"<{tag}#{mid.group(1)}>"))
            elif mcl:
                out.append((i, f"<{tag}.{mcl.group(1).split()[0]}>"))
            elif tag in ("header", "main", "nav", "footer"):
                out.append((i, f"<{tag}>"))
    return out


def markers_regex(lines, rx):
    return [(i, m.group(1)) for i, l in enumerate(lines, 1) if (m := rx.match(l))]


def markers_flat(lines):
    return [
        (i, l.split("(")[0].strip()[:44])
        for i, l in enumerate(lines, 1)
        if l[:1] not in ("", " ", "\t", "#", "/")
    ]


def markers_for(path, lines):
    if path.endswith(".html") or path.endswith(".htm"):
        return markers_html(lines)
    if path.endswith(".py"):
        return markers_regex(lines, PY_DECL)
    if path.endswith((".js", ".mjs")):
        return markers_regex(lines, JS_DECL)
    return markers_flat(lines)


def locate(syms, lineno):
    """Dernier marqueur déclaré avant `lineno` (dichotomie)."""
    lo, hi, best = 0, len(syms) - 1, "«en-tête»"
    while lo <= hi:
        mid = (lo + hi) // 2
        if syms[mid][0] <= lineno:
            best = syms[mid][1]
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def collect(repo, path, branch, since):
    log = git(repo, "log", "--no-merges", f"--since={since}",
              "--format=%H\x01%s", branch, "--", path)
    commits = [l for l in log.splitlines() if l]
    tickets, ncommits, nlines = defaultdict(set), defaultdict(int), defaultdict(int)
    for entry in commits:
        sha, subject = entry.split("\x01", 1)
        rms = set(RM_ID.findall(subject))
        pre = git(repo, "show", f"{sha}^:{path}")
        if not pre:
            continue
        syms = markers_for(path, pre.split("\n"))
        seen = set()
        for line in git(repo, "show", "-U0", "--format=", sha, "--", path).split("\n"):
            m = HUNK.match(line)
            if not m:
                continue
            start = max(int(m.group(1)), 1)
            sym = locate(syms, start)
            nlines[sym] += int(m.group(2) or 1) + int(m.group(4) or 1)
            seen.add(sym)
        for sym in seen:
            ncommits[sym] += 1
            tickets[sym] |= rms
    return commits, tickets, ncommits, nlines


def main():
    ap = argparse.ArgumentParser(description="carte de chaleur d'un fichier")
    ap.add_argument("path", help="chemin du fichier, relatif à la racine du dépôt")
    ap.add_argument("--repo", default=".", help="dépôt (défaut : cwd)")
    ap.add_argument("--branch", default="origin/dev", help="branche analysée")
    ap.add_argument("--since", default="90.days", help="fenêtre (défaut : 90.days)")
    ap.add_argument("--top", type=int, default=25, help="zones affichées")
    ap.add_argument("--bands", type=int, default=400,
                    help="hauteur des bandes de la topographie (0 : pas de topographie)")
    ap.add_argument("--json", help="écrit le détail complet dans ce fichier")
    args = ap.parse_args()

    commits, tickets, ncommits, nlines = collect(
        args.repo, args.path, args.branch, args.since)
    if not commits:
        print(f"aucun commit sur {args.path} depuis {args.since} ({args.branch})")
        return 0

    cur = git(args.repo, "show", f"{args.branch}:{args.path}").split("\n")
    pos = {name: ln for ln, name in markers_for(args.path, cur)}

    rows = [
        {"zone": s, "tickets": len(tickets[s]), "commits": ncommits[s],
         "lignes": nlines[s], "ligne": pos.get(s, 0), "rm": sorted(tickets[s])}
        for s in ncommits
    ]
    rows.sort(key=lambda r: (-r["tickets"], -r["commits"]))

    total_rm = len({rm for s in tickets for rm in tickets[s]})
    froides = sum(1 for r in rows if r["tickets"] <= 1)
    print(f"{args.path} — {len(cur)} lignes, {args.branch}, depuis {args.since}")
    print(f"{len(commits)} commits non-merge · {total_rm} tickets distincts · "
          f"{len(rows)} zones touchées, dont {froides} froides (≤ 1 ticket)\n")
    print(f"{'zone':<44}{'tickets':>8}{'commits':>9}{'lignes':>8}{'ligne':>8}")
    print("-" * 77)
    for r in rows[: args.top]:
        print(f"{r['zone']:<44}{r['tickets']:>8}{r['commits']:>9}"
              f"{r['lignes']:>8}{r['ligne'] or '-':>8}")

    if args.bands:
        print(f"\ntopographie — tickets distincts par bande de {args.bands} lignes")
        per = defaultdict(set)
        for r in rows:
            if r["ligne"]:
                per[(r["ligne"] - 1) // args.bands] |= set(r["rm"])
        for b in range(len(cur) // args.bands + 1):
            lo, hi = b * args.bands + 1, min((b + 1) * args.bands, len(cur))
            n = len(per.get(b, ()))
            print(f"{lo:>6}-{hi:<7}{n:>5}  " + "█" * min(n, 48))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
        print(f"\ndétail complet : {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
