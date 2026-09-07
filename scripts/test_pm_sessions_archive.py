#!/usr/bin/env python3
"""Tests RM2997 — archivage des sessions Claude : automatiser ET surveiller.

Ce qui est protégé ici, dans l'ordre d'importance :

  1. **aucune suppression n'est jamais consignée.** Un transcript effacé par la
     rétention de Claude Code doit garder son blob atteignable ; consigner sa
     disparition le retirerait de l'arbre, et un clone frais ne le ramènerait
     plus. C'est l'invariant qui a permis de récupérer 313 fichiers ;
  2. **un verrou n'est levé que s'il est mort** — trop vieux ET aucun git vivant
     dans le dépôt. Lever le verrou d'un git en cours corromprait l'index ; ne
     jamais le lever, c'est l'incident de juin (75 jours d'échec silencieux) ;
  3. **le contrôle distingue trois pannes** : pas de dépôt, plus de commit
     depuis trop longtemps, commits non poussés. Les confondre rendrait le
     diagnostic inutile — la deuxième est celle qui est passée inaperçue ;
  4. ce qu'on archive en plus (history.jsonl, worklogs) ne doit **pas** être pris
     pour un transcript par le moteur, qui énumère `*/*.jsonl` à profondeur deux.

Lancer : python3 scripts/test_pm_sessions_archive.py
"""
import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("psa", HERE / "pm-sessions-archive.py")
psa = importlib.util.module_from_spec(spec)
sys.modules["psa"] = psa
spec.loader.exec_module(psa)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# ── 1. jamais les suppressions ───────────────────────────────────────────────
st = ["?? -proj/neuf.jsonl", " M -proj/vivant.jsonl", " D -proj/efface.jsonl",
      "D  -proj/efface2.jsonl", "A  -proj/ajoute.jsonl", "AD -proj/ajoute-puis-efface.jsonl"]
got = psa.a_ajouter(st)
check("un fichier neuf est indexé", "-proj/neuf.jsonl" in got)
check("un fichier modifié aussi", "-proj/vivant.jsonl" in got)
check("une suppression en arbre est IGNORÉE", "-proj/efface.jsonl" not in got)
check("une suppression déjà indexée aussi", "-proj/efface2.jsonl" not in got)
check("…y compris ajouté-puis-effacé", "-proj/ajoute-puis-efface.jsonl" not in got)
check("un ajout normal passe", "-proj/ajoute.jsonl" in got)
check("entrée tronquée ignorée sans exception", psa.a_ajouter(["?", ""]) == [])

# ── 2. le verrou : mort, et seulement mort ───────────────────────────────────
now = 1_000_000
vieux, recent = now - 3600, now - 60
check("verrou vieux + aucun git vivant ⇒ levé",
      psa.stale_lock(True, vieux, now, git_vivant=False))
check("verrou vieux MAIS un git tourne ⇒ intouchable",
      not psa.stale_lock(True, vieux, now, git_vivant=True))
check("verrou récent ⇒ intouchable (un git add sur 400 Mo est long)",
      not psa.stale_lock(True, recent, now, git_vivant=False))
check("pas de verrou ⇒ rien à faire",
      not psa.stale_lock(False, vieux, now, git_vivant=False))
check("le seuil est paramétrable",
      psa.stale_lock(True, now - 120, now, False, min_age_s=60))

# ── 3. le contrôle : trois pannes distinctes ─────────────────────────────────
maintenant = 1_000_000
ok, l = psa.etat_check(True, maintenant - 3600, maintenant, 0, False)
check("archivage frais et poussé ⇒ vert", ok and "archivé il y a" in l[0])
ok, l = psa.etat_check(False, None, maintenant, 0, False)
check("aucun dépôt ⇒ rouge, et le dit", not ok and "aucun dépôt" in l[0])
ok, l = psa.etat_check(True, None, maintenant, 0, False)
check("dépôt sans commit ⇒ rouge", not ok and "sans commit" in l[0])
ok, l = psa.etat_check(True, maintenant - 10 * 86400, maintenant, 0, False)
check("archivage vieux de 10 j ⇒ rouge (c'est LA panne de juin)",
      not ok and any("ne tourne plus" in x for x in l))
ok, l = psa.etat_check(True, maintenant - 3600, maintenant, 4, False)
check("commits non poussés ⇒ rouge, distinct de l'âge",
      not ok and any("ne quitte pas la machine" in x for x in l))
ok, l = psa.etat_check(True, maintenant - 3600, maintenant, 0, True)
check("verrou périmé ⇒ rouge, et annonce l'échec à venir",
      not ok and any("index.lock" in x for x in l))
ok, _ = psa.etat_check(True, maintenant - 10 * 86400, maintenant, 0, False, max_age_days=30)
check("le seuil d'âge est paramétrable", ok)

# ── 4. bout en bout, sur un vrai dépôt ───────────────────────────────────────
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2997-"))
repo = tmp / "projects"
(repo / "-un-projet").mkdir(parents=True)
G = ["git", "-C", str(repo)]
subprocess.run(["git", "init", "-q", "-b", "dev", str(repo)], check=True, capture_output=True)
for k, v in (("user.email", "t@t"), ("user.name", "t")):
    subprocess.run(G + ["config", k, v], check=True, capture_output=True)
(repo / "-un-projet" / "aaa.jsonl").write_text('{"a":1}\n')
(repo / "-un-projet" / "bbb.jsonl").write_text('{"b":2}\n')
subprocess.run(G + ["add", "-A"], check=True, capture_output=True)
subprocess.run(G + ["commit", "-qm", "base"], check=True, capture_output=True)

hist = tmp / "history.jsonl"; hist.write_text('{"sessionId":"x"}\n')
wl = tmp / "worklogs"; wl.mkdir(); (wl / "x.json").write_text("{}")
psa.STORE, psa.HISTORY, psa.WORKLOGS = repo, hist, wl
psa.LOG = tmp / "archive.log"

(repo / "-un-projet" / "bbb.jsonl").unlink()          # effacé « par la rétention »
(repo / "-un-projet" / "ccc.jsonl").write_text('{"c":3}\n')   # session neuve


class A:
    dry_run = False; no_push = True; verbose = False; max_age_days = 2


rc = psa.archiver(A())
check("l'archivage réussit", rc == 0)
suivis = subprocess.run(G + ["ls-files"], capture_output=True, text=True).stdout.split()
check("le fichier neuf est archivé", "-un-projet/ccc.jsonl" in suivis)
check("le fichier EFFACÉ reste dans l'arbre (blob atteignable)",
      "-un-projet/bbb.jsonl" in suivis)
blob = subprocess.run(G + ["cat-file", "blob", "HEAD:-un-projet/bbb.jsonl"],
                      capture_output=True, text=True)
check("…et son contenu est bien récupérable", blob.stdout.strip() == '{"b":2}')
check("history.jsonl est archivé", "_meta/history/history.jsonl" in suivis)
check("les worklogs aussi", "_meta/worklogs/x.json" in suivis)
# Le piège : le moteur énumère `*/*.jsonl` (profondeur DEUX). Rien de ce qu'on
# ajoute ne doit y ressembler, sinon history.jsonl passe pour une conversation.
faux = [p for p in repo.glob("*/*.jsonl") if p.parts[-2] == psa.EXTRA_DIR]
check("aucun faux transcript créé par les extras", faux == [])

rc2 = psa.archiver(A())
check("relancé sans changement, l'archivage ne casse rien", rc2 == 0)

# verrou périmé : levé, et l'archivage repart
lock = repo / ".git" / "index.lock"
lock.write_text("")
import os
os.utime(lock, (time.time() - 7200, time.time() - 7200))
(repo / "-un-projet" / "ddd.jsonl").write_text('{"d":4}\n')
rc3 = psa.archiver(A())
check("un verrou périmé est levé et l'archivage repart", rc3 == 0)
check("…et le fichier bloqué est bien passé",
      "-un-projet/ddd.jsonl" in
      subprocess.run(G + ["ls-files"], capture_output=True, text=True).stdout)
check("le verrou n'est pas détruit mais mis de côté",
      any(p.name.startswith("index.lock.perime-") for p in (repo / ".git").iterdir()))

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
