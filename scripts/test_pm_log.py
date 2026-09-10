#!/usr/bin/env python3
"""Tests RM3010 — pm_log : journal structuré (sévérité, catégories contrôlées, JSON Lines, seuil, rotation, rétention, tail filtré,
catégorie par chemin, traceback court). Lancer : python3 scripts/test_pm_log.py"""
import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_log", HERE / "pm_log.py")
pl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pl)

fails = []


def check(cond, what):
    (print("✓", what) if cond else fails.append(what) or print("✗", what))


with tempfile.TemporaryDirectory() as tmp:
    err = io.StringIO(); real_stderr = sys.stderr; sys.stderr = err
    pl.configure(directory=tmp, level="info", max_mb=1, keep_days=0, stderr="1")
    check(pl.stats()["level"] == "info" and pl.journal_path() == pathlib.Path(tmp) / "karl-agent.jsonl", "configuration : dossier, niveau, chemin")
    # seuil et validation
    check(pl.log("api", "debug", "trop bas") is None and pl.stats()["dropped"] == 1, "un enregistrement sous le seuil est écarté (compté)")
    r = pl.log("auth", "warn", "identifiants invalides", user="bob", ip="1.2.3.4", nope=None)
    check(r and r["cat"] == "auth" and r["level"] == "warn" and r["user"] == "bob" and "nope" not in r and r["ts"].count(":") >= 2, "un enregistrement porte ts, level, cat, msg et ses champs (None omis)")
    r = pl.log("inconnue", "grave", "?")
    check(r["cat"] == "system" and r["bad_category"] == "inconnue" and r["level"] == "info" and r["bad_level"] == "grave", "catégorie / sévérité inconnues : rangées, signalées, jamais perdues")
    r = pl.log("tmux", "error", "kill-session a échoué", obj={"a": 1}, weird=object())
    check(isinstance(r["weird"], str) and r["obj"] == {"a": 1}, "un champ non sérialisable est converti en chaîne")
    lines = pl.journal_path().read_text(encoding="utf-8").splitlines()
    check(len(lines) == 3 and all(json.loads(l)["msg"] for l in lines), "JSON Lines : une ligne par enregistrement")
    check("[warn] auth: identifiants invalides" in err.getvalue() and "[error] tmux:" in err.getvalue() and "kill-session" in err.getvalue(), "warn/error reflétés sur stderr (journald)")
    # tail : filtres
    for i in range(5):
        pl.log("api", "info", f"GET /x{i}", status=200, ms=i)
    t = pl.tail(category="api", limit=2)
    check([x["msg"] for x in t] == ["GET /x3", "GET /x4"], "tail : les N derniers, du plus ancien au plus récent")
    check(all(x["cat"] in ("auth", "tmux", "system") for x in pl.tail(category="auth,tmux,system")), "tail : filtre multi-catégories")
    check([x["level"] for x in pl.tail(level="warn")] == ["warn", "error"], "tail : sévérité minimale")
    since = pl.tail(category="api", limit=5)[1]["ts"]
    check(len(pl.tail(category="api", since=since)) <= 3 and all(x["ts"] > since for x in pl.tail(category="api", since=since)), "tail : since exclusif")
    check([x["msg"] for x in pl.tail(q="x4")] == ["GET /x4"], "tail : recherche texte")
    # rotation par taille + rétention
    before = pl.stats()["rotations"]; pl.configure(directory=tmp, level="info", max_mb=0.0005, keep_days=0, stderr="0")   # rotation à ~500 octets
    for i in range(30):
        pl.log("worklog", "info", "x" * 40, i=i)
    rotated = sorted(pathlib.Path(tmp).glob("karl-agent-*.jsonl"))
    check(pl.stats()["rotations"] > before and pl.journal_path().stat().st_size < 600, "rotation par taille : le journal courant repart, l'ancien est horodaté")
    old = pathlib.Path(tmp) / "karl-agent-20200101-000000.jsonl"; old.write_text("{}\n"); os.utime(old, (time.time() - 10 * 86400, time.time() - 10 * 86400))
    for i in range(30):
        pl.log("worklog", "info", "y" * 40, i=i)
    check(not old.exists(), "rétention : un fichier tourné plus vieux que KEEP_DAYS est supprimé")
    # jamais d'exception vers l'appelant
    pl.configure(directory=str(pathlib.Path(tmp) / "fichier-pas-dossier"), level="info", stderr="0")
    (pathlib.Path(tmp) / "fichier-pas-dossier").write_text("x")
    check(pl.log("api", "info", "…") is not None and pl.stats()["errors"] >= 1, "dossier inaccessible : compté, pas levé")
    sys.stderr = real_stderr

# catégorie par chemin, traceback court
check(pl.category_for_path("/auth/login") == "auth" and pl.category_for_path("/session-set?group=a") == "sets" and pl.category_for_path("/spawn") == "tmux"
      and pl.category_for_path("/resolve/12") == "issue" and pl.category_for_path("/worklog/12") == "worklog" and pl.category_for_path("/fs/ls") == "files"
      and pl.category_for_path("/mail/queue") == "mail" and pl.category_for_path("/pm/run") == "pm" and pl.category_for_path("/tts") == "voice"
      and pl.category_for_path("/health") == "env" and pl.category_for_path("/refresh") == "refresh" and pl.category_for_path("/zzz") == "api" and pl.category_for_path("/approve") == "session",
      "catégorie déduite du chemin historique")
try:
    def inner(): raise ValueError("boum")
    inner()
except ValueError as e:
    b = pl.exception_brief(e)
check(b.startswith("ValueError: boum") and "inner" in b and "test_pm_log.py" in b and len(b) <= 600, "traceback court : type, message, derniers cadres")
check(pl.exception_brief(None) is None, "pas d'exception → None")
check(pl.LEVELS["debug"] < pl.LEVELS["info"] < pl.LEVELS["warn"] < pl.LEVELS["error"] and {"auth", "issue", "provider", "tmux", "claude", "worklog", "files"} <= pl.CATEGORIES, "sévérités ordonnées, catégories demandées présentes")

if fails:
    print("\nÉCHECS :", *fails, sep="\n  "); sys.exit(1)
print("\nOK — pm_log")
