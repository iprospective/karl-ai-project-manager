#!/usr/bin/env python3
"""norms-runtime-fidelity — contrôle mécanique de la réécriture runtime (RM3037, essai).

Chaque identifiant en backticks et chaque nombre significatif d une source norms/src doit se
retrouver dans son module norms/runtime (RM-ids, versions, dates exclus). Liste les manquants ;
exit 0 toujours : c est une aide à la relecture, la décision reste éditoriale.
Lancer depuis la racine du repo PM : python3 scripts/norms-runtime-fidelity.py
"""
import re, sys, pathlib
R = pathlib.Path("norms/runtime"); SRC = pathlib.Path("norms/src")
pairs = [("NORMS-KERNEL.md", ["KERNEL.md", "schema.md"]), ("modules/git-mep.md", ["git-mep.md", "KERNEL.md"]), ("modules/status-workflow.md", ["status-workflow.md", "KERNEL.md"]),
         ("modules/environments.md", ["environments.md", "KERNEL.md"]), ("modules/session-tooling.md", ["session-tooling.md", "KERNEL.md"]), ("modules/redmine-hygiene.md", ["redmine-hygiene.md", "KERNEL.md"])]
skip = re.compile(r"^(RM\d+|v?\d+\.\d+(\.\d+)?|\d{4}-\d{2}-\d{2}.*|…|-|\.\.\.)$")
norm = lambda s: s.strip().strip("`").rstrip(".,;:")
tot_src = tot_rt = 0
for src, rts in pairs:
    st = (SRC / src).read_text(); rt = "".join((R / r).read_text() for r in rts); rt_main = (R / rts[0]).read_text()
    tot_src += len(st.encode()) / 3.6; tot_rt += len(rt_main.encode()) / 3.6
    idents = {norm(m) for m in re.findall(r"`([^`\n]+)`", st)}
    idents = {i for i in idents if i and not skip.match(i)}
    # nombres significatifs (ids, valeurs) hors dates/versions/RM
    nums = set(re.findall(r"(?<![\w.\-])(\d{1,4})(?![\w.\-])", re.sub(r"RM\d+|v?\d+\.\d+(\.\d+)?|\d{4}-\d{2}-\d{2}[T\d:]*", " ", st)))
    miss_i = sorted(i for i in idents if i not in rt and i.split("(")[0].split(" ")[0] not in rt)
    miss_n = sorted(n for n in nums if not re.search(r"(?<![\w.\-])" + re.escape(n) + r"(?![\w.\-])", rt))
    print(f"== {src} → {rts[0]} : {len(idents)} identifiants, manquants {len(miss_i)} ; nombres {len(nums)}, manquants {len(miss_n)}")
    for m in miss_i: print("   ident:", m)
    if miss_n: print("   nums :", ", ".join(miss_n))
print(f"\nTOTAL préchargé source ≈ {tot_src:.0f} tokens ; runtime équivalents ≈ {tot_rt:.0f}")
