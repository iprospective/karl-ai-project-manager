#!/usr/bin/env python3
"""Tests des canaux du worklog de session : notifications (RM2466 volet 1)
et merge requests à merger (RM2583).

Unitaire sur les fonctions pures, puis bout en bout sur un store JETABLE
(PM_SESSION_WORKLOG_DIR) : jamais dans le worklog réel de la session courante.
Lancer : python3 scripts/test_pm_session_status_notify.py
"""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "pm-session-status.py"
spec = importlib.util.spec_from_file_location("pm_session_status", SCRIPT)
pss = importlib.util.module_from_spec(spec)
sys.modules["pm_session_status"] = pss
spec.loader.exec_module(pss)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# — niveau déduit du type —
check("un secret exposé est critique sans qu'on ait à le préciser",
      pss.notify_level_for("secret") == "critical")
check("les autres types sont des avertissements par défaut",
      pss.notify_level_for("outillage") == "warn" and pss.notify_level_for("autre") == "warn")
check("un niveau explicite l'emporte toujours",
      pss.notify_level_for("secret", "info") == "info")

# — rognage : jamais au prix d'une critique —
notes = ([{"ts": "t%03d" % i, "level": "warn", "message": str(i)} for i in range(120)]
         + [{"ts": "t999", "level": "critical", "message": "secret"}])
kept = pss.notify_trim(notes, keep=10)
check("le canal est plafonné", len(kept) == 10)
check("une critique survit au rognage, même noyée dans le bruit",
      any(n["level"] == "critical" for n in kept))
check("ce sont les plus récentes qui restent",
      kept[0]["ts"] > "t100" and kept[-1]["ts"] == "t999")
check("ordre chronologique conservé", [n["ts"] for n in kept] == sorted(n["ts"] for n in kept))
check("sous le plafond, rien n'est touché",
      len(pss.notify_trim(notes[:5], keep=10)) == 5)
check("canal vide ou absent toléré",
      pss.notify_trim([]) == [] and pss.notify_trim(None) == [])
# 100 critiques et un plafond de 10 : on ne jette AUCUNE critique, quitte à
# dépasser le plafond — perdre un secret exposé coûte plus cher qu'un fichier long.
only_crit = [{"ts": "t%03d" % i, "level": "critical", "message": str(i)} for i in range(100)]
check("un canal saturé de critiques ne perd rien", len(pss.notify_trim(only_crit, keep=10)) == 100)

# — bout en bout, sur un store jetable —
with tempfile.TemporaryDirectory() as tmp:
    env = dict(os.environ, PM_SESSION_WORKLOG_DIR=tmp)

    def run(*args):
        return subprocess.run([sys.executable, str(SCRIPT), "--session", "t"] + list(args),
                              capture_output=True, text=True, env=env)

    run("notify", "secret vu dans un log", "--kind", "secret", "--ref", "RM1")
    run("notify", "script en défaut", "--kind", "outillage")
    data = json.loads(pathlib.Path(tmp, "t.json").read_text(encoding="utf-8"))
    check("les notifications sont persistées dans le store", len(data["notifications"]) == 2)
    check("horodatage, niveau, type et ticket sont conservés",
          all(k in data["notifications"][0] for k in ("ts", "level", "kind", "ref", "message")))

    md = pathlib.Path(tmp, "t.md").read_text(encoding="utf-8")
    check("le rendu .md porte les notifications", "Notifications importantes (2)" in md)
    check("elles passent AVANT le travail de la session",
          md.index("Notifications importantes") < md.index("Reste à faire"))
    check("le niveau est visible en toutes lettres, pas seulement par l'icône",
          "`critical`" in md and "`warn`" in md)

    out = run("notify", "--list").stdout
    check("--list restitue le canal", "secret vu dans un log" in out and "RM1" in out)

    run("notify", "--clear")
    data = json.loads(pathlib.Path(tmp, "t.json").read_text(encoding="utf-8"))
    check("un acquittement ordinaire épargne les critiques",
          [n["level"] for n in data["notifications"]] == ["critical"])

    run("notify", "--clear", "--all")
    data = json.loads(pathlib.Path(tmp, "t.json").read_text(encoding="utf-8"))
    check("--clear --all vide le canal, y compris les critiques",
          data["notifications"] == [])

    r = run("notify")
    check("un message vide est refusé, pas consigné à blanc", r.returncode != 0)

    # une session sans notification ne doit pas voir surgir une section vide
    run("add", "RM2", "un item")
    md = pathlib.Path(tmp, "t.md").read_text(encoding="utf-8")
    check("aucune notification → aucune section dans le rendu",
          "Notifications importantes" not in md)


# — RM2583 : canal des MR à merger —
mrs = pss.mr_upsert([], {"iid": "400", "url": "u/400", "repo": "g/p", "target": "dev",
                         "ref": "RM1", "state": "opened"})
mrs = pss.mr_upsert(mrs, {"iid": "401", "url": "u/401", "repo": "g/p", "target": "main",
                          "state": "opened"})
check("les MR ouvertes s'accumulent", len(mrs) == 2)
maj = pss.mr_upsert(mrs, {"iid": "400", "url": "u/400", "state": "merged"})
check("changer d'état ne duplique pas la MR", len(maj) == 2)
check("l'état est bien mis à jour",
      [m for m in maj if m["iid"] == "400"][0]["state"] == "merged")
check("les champs non fournis ne sont pas écrasés",
      [m for m in maj if m["iid"] == "400"][0]["ref"] == "RM1")
check("une MR mergée sort des « à merger »",
      [m["iid"] for m in pss.mr_pending(maj)] == ["401"])
check("une MR fermée en sort aussi",
      pss.mr_pending(pss.mr_upsert(maj, {"iid": "401", "url": "u/401", "state": "closed"})) == [])
check("rien n'est perdu : l'historique garde tout",
      len(pss.mr_upsert(maj, {"iid": "401", "url": "u/401", "state": "closed"})) == 2)
check("identification par iid+repo quand l'URL manque",
      len(pss.mr_upsert(mrs, {"iid": "400", "repo": "g/p", "state": "merged"})) == 2)
check("même iid sur un AUTRE dépôt = une autre MR",
      len(pss.mr_upsert(mrs, {"iid": "400", "repo": "autre/p", "state": "opened"})) == 3)
check("état absent = à merger (on ne perd pas une MR mal renseignée)",
      len(pss.mr_pending([{"iid": "9"}])) == 1)
check("canal vide ou absent toléré",
      pss.mr_pending([]) == [] and pss.mr_pending(None) == [] and pss.mr_upsert(None, {"iid": "1"}))

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests canaux worklog (notifications RM2466 + MR RM2583) passent")
