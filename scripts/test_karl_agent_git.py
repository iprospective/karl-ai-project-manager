#!/usr/bin/env python3
"""Tests RM2602 — lecture des commits et des diffs depuis le cockpit.

Unitaire : parsing pur + validation des refs. Les refs et sha viennent du
navigateur et partent dans une ligne de commande git — c'est la partie qu'il
faut verrouiller, pas l'affichage.

Lancer : python3 scripts/test_karl_agent_git.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


S = ka.GIT_LOG_SEP


def ligne(sha, date, auteur, sujet, parents=""):
    return S.join([sha, date, auteur, sujet, parents])


# — parse_git_log —
raw = "\n".join([
    ligne("a" * 40, "2026-08-09T10:00:00+02:00", "Mathieu", "corrige le parseur"),
    ligne("b" * 40, "2026-08-09T09:00:00+02:00", "Karl", "Merge branch 'dev'", "c" * 40 + " " + "d" * 40),
    "",
    "ligne cassée sans séparateur",
])
items = ka.parse_git_log(raw, unpushed_shas={"a" * 40})
check("les commits sont lus", len(items) == 2)
check("sha court fourni pour l'affichage", items[0]["short"] == "a" * 9)
check("date, auteur et sujet conservés",
      items[0]["author"] == "Mathieu" and items[0]["subject"] == "corrige le parseur"
      and items[0]["date"].startswith("2026-08-09"))
check("un commit à deux parents est un merge",
      items[1]["merge"] is True and items[0]["merge"] is False)
check("le non-poussé est marqué — c'est ce que GitLab ne montre pas",
      items[0]["pushed"] is False and items[1]["pushed"] is True)
check("une ligne malformée est ignorée, pas fatale", len(ka.parse_git_log("nawak")) == 0)
check("journal vide toléré", ka.parse_git_log("") == [] and ka.parse_git_log(None) == [])
check("sans liste de non-poussés, tout est considéré poussé",
      ka.parse_git_log(raw)[0]["pushed"] is True)
# un message contenant le séparateur ne doit pas décaler les champs suivants
check("le séparateur choisi n'apparaît pas dans un sujet ordinaire",
      S not in "corrige le parseur (v2) — 50 % plus rapide")

# — parse_numstat —
st = ka.parse_numstat("3\t1\tsrc/a.py\n0\t7\tsrc/b.py\n-\t-\timg/logo.png")
check("3 fichiers comptés", st["count"] == 3)
check("totaux justes", st["added"] == 3 and st["removed"] == 8)
check("un binaire est marqué comme tel", st["files"][2]["binary"] is True)
check("et ne fausse pas les totaux",
      st["files"][2]["added"] == 0 and st["files"][2]["removed"] == 0)
check("numstat vide toléré", ka.parse_numstat("")["count"] == 0)
check("chemin avec espaces conservé",
      ka.parse_numstat("1\t0\tdocs/mon fichier.md")["files"][0]["path"] == "docs/mon fichier.md")

# — validation : c'est ici que ça compte —
for bon in ("abc1234", "a" * 40, "ABC1234".lower()):
    check(f"sha accepté : {bon[:12]}", ka._valid_sha(bon))
for mauvais in ("", None, "abc", "z" * 8, "a" * 41, "abc1234; rm -rf /", "--upload-pack=x",
                "abc1234\nrm", "$(whoami)"):
    check(f"sha refusé : {str(mauvais)[:22]!r}", not ka._valid_sha(mauvais))

for bon in ("dev", "origin/main", "release/1.2.3", "2602-vue-git"):
    check(f"ref acceptée : {bon}", ka._valid_ref(bon))
for mauvais in ("", None, "--upload-pack=/bin/sh", "-x", "a..b", "a b", "a;b", "refs/x.lock",
                "dev/", "a$(id)", "a\nb", "é" * 3, "x" * 200):
    check(f"ref refusée : {str(mauvais)[:24]!r}", not ka._valid_ref(mauvais))

# — bornes annoncées, pas subies —
check("le plafond de diff est explicite", ka.GIT_DIFF_MAX_BYTES > 0)
check("le nombre de commits listés est borné", ka.GIT_LOG_MAX > 0)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests git RM2602 passent")
