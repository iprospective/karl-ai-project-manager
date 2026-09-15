#!/usr/bin/env python3
"""Tests RM3195 — un tripwire perdu par le runtime doit faire ROUGIR le doctor.

RM3194 a résolu le conflit et posé le gate anti-marqueurs (`test_norms_doctor_conflict.py`
le vérifie dans les deux sens). Il restait le dégât que ce conflit avait causé, et que
rien ne détectait : le KERNEL **runtime** — celui qui est réinjecté après compaction,
donc celui qui engage — s'est arrêté au tripwire #17 pendant que la source en comptait
20. Trois garde-fous écrits, validés, commités, et qui n'atteignaient aucun agent.

Les contrôles existants ne pouvaient pas le voir : `pm-norms-runtime` compare des ANCRES
(options, chemins), parce qu'entre un texte et sa réécriture dense rien n'est verbatim.
Un tripwire entier qui disparaît n'est pourtant pas une affaire de densité. Ce qui reste
comparable, c'est la numérotation — et c'est ce qu'on contrôle.

Lancer : python3 scripts/test_norms_conflits.py
"""
import importlib.util
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
spec = importlib.util.spec_from_file_location("doc", HERE / "pm-norms-doctor.py")
doc = importlib.util.module_from_spec(spec)
sys.modules["doc"] = doc
spec.loader.exec_module(doc)

fails = []


def chk(label, cond):
    print(("\u2713 " if cond else "\u2717 ") + label)
    if not cond:
        fails.append(label)


# ── l'état réel du dépôt ─────────────────────────────────────────────────────
chk("aucun tripwire du KERNEL source ne manque au runtime",
    doc.check_runtime_tripwires() == [])

src = (REPO / "norms" / "src" / "NORMS-KERNEL.md").read_text(encoding="utf-8")
rt = (REPO / "norms" / "runtime" / "KERNEL.md").read_text(encoding="utf-8")
titre = lambda t, n: next((x for k, x in re.findall(r"^(\d+)\.\s+\*\*(.+?)\*\*", t, re.M)
                           if k == str(n)), None)  # noqa: E731
for n in (18, 19, 20):
    a, b = titre(src, n), titre(rt, n)
    chk(f"le tripwire #{n} dit la même chose des deux côtés ({str(a)[:34]}…)",
        a is not None and b is not None
        and a.split()[0].lower().strip(".") == b.split()[0].lower().strip("."))

# ── la garde elle-même : elle doit MORDRE, pas seulement se taire ────────────
nums = lambda t: {int(n) for n in doc.TRIPWIRE_RE.findall(t)}  # noqa: E731
chk("la numérotation se lit sur « N. **Titre** »", nums("18. **Grouper.** x\n") == {18})
chk("une simple liste numérotée sans gras n'est pas un tripwire", nums("18. rien\n") == set())
chk("un runtime qui en porte DAVANTAGE reste valide (structurels fusionnés)",
    not (nums("1. **a**\n") - nums("1. **a**\n2. **b**\n")))
chk("un runtime qui en porte MOINS est en faute",
    sorted(nums("1. **a**\n2. **b**\n") - nums("1. **a**\n")) == [2])

# ── le gate anti-marqueurs de RM3194, étendu au runtime et au dépôt entier ───
chk("le runtime entre dans le périmètre du gate anti-marqueurs",
    any("runtime" in str(p) for p in doc.conflict_targets()))

# Le doctor ne connaît que `norms/`. Un conflit non résolu nuit tout autant dans un
# script ou une conf, et ce contrôle-là a sa place ici : ni réseau ni environnement,
# juste git. On ne cherche que `^<<<<<<< ` et `^>>>>>>> ` — `^=======` seul ferait un
# faux positif sur les soulignements de titre Markdown en `===`, qui sont légitimes.
r = subprocess.run(["git", "-C", str(REPO), "grep", "-n", "-E", r"^(<{7} |>{7} )", "--", "."],
                   capture_output=True, text=True)
chk("aucun marqueur de conflit dans TOUT le dépôt suivi",
    r.returncode == 1 and not r.stdout.strip())
for ligne in r.stdout.strip().splitlines()[:10]:
    print("      \u00b7 " + ligne[:120])

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — le runtime porte tous les tripwires du KERNEL (RM3195)")
