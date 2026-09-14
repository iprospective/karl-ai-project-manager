#!/usr/bin/env python3
"""Tests RM3145 (lot 2) — le bus d'événements métier et le drain des abonnements.

Ce qui doit tenir : un nom d'événement est un contrat (un nom inconnu est refusé, pas déposé en
silence), un événement non traité n'est jamais perdu, un abonné qui échoue n'affecte ni l'émetteur ni
les autres, un échec ne rejoue pas indéfiniment, et un module bloqué ou désactivé n'écoute pas.

Lancer : python3 scripts/test_pm_bus.py
"""
import importlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def frais(mod, var, d):
    os.environ[var] = str(d)
    if mod in sys.modules:
        del sys.modules[mod]
    return importlib.import_module(mod)


with tempfile.TemporaryDirectory() as tmp:
    B = frais("pm_bus", "PM_BUS_DIR", tmp)
    print("[RM3145] le nom d'un événement est un contrat")
    e = B.publish("task.status.changed", source="test", rm_id="42", **{"from": "a_faire", "to": "en_cours"})
    check("un événement connu est déposé", e and e["name"] == "task.status.changed")
    check("avec sa charge utile", e["payload"] == {"rm_id": "42", "from": "a_faire", "to": "en_cours"})
    check("et sa source", e["source"] == "test")
    check("un nom INCONNU est refusé, pas déposé en silence", B.publish("pas.un.nom", x=1) is None)
    check("un nom mal orthographié aussi", B.publish("task.status.change") is None)
    check("les noms connus sont documentés un par un",
          all(isinstance(v, str) and v for v in B.EVENEMENTS.values()))

    print("\n[RM3145] rien ne se perd tant que ce n'est pas drainé")
    check("il attend", [x["id"] for x in B.pending()] == [e["id"]])
    check("le filtre par nom marche", len(B.pending(name="task.status.changed")) == 1
          and B.pending(name="mr.merged") == [])
    check("marquer drainé le sort de la file", B.mark_drained(e["id"]) == 1 and B.pending() == [])
    check("…et ne le marque pas deux fois", B.mark_drained(e["id"]) == 0)
    B.publish("mr.merged", url="https://x")
    c = B.counts()
    check("les compteurs disent ce qui attend et par quel nom",
          c["pending"] == 1 and c["by_name"] == {"mr.merged": 1}, str(c))

    print("\n[RM3145] la garde de taille n'oublie JAMAIS ce qui attend")
    B.GARDE = 10
    for i in range(30):
        x = B.publish("task.created", rm_id=str(i), title="t")
        if i % 2 == 0:
            B.mark_drained(x["id"])
    attente = B.pending(limit=1000)
    check("tout ce qui attend a survécu, même au-delà de la garde", len(attente) == 16, str(len(attente)))

with tempfile.TemporaryDirectory() as tmp:
    B = frais("pm_bus", "PM_BUS_DIR", tmp)
    print("\n[RM3145] le bus ne casse pas ce qu'il observe")
    B.publish("task.created", rm_id="1", title="x")
    (pathlib.Path(tmp) / B.FICHIER).write_text('pas du json\n{"id":"ok","name":"mr.merged"}\n', encoding="utf-8")
    check("une ligne illisible est ignorée, pas fatale", [x["id"] for x in B.pending()] == ["ok"])
    M = frais("pm_bus", "PM_BUS_DIR", "/proc/interdit/nulle-part")
    check("un journal inaccessible rend None plutôt que de lever", M.publish("task.created", rm_id="1") is None)
    check("et sa lecture rend une liste vide", M.pending() == [])

# ── les abonnements ───────────────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as mods:
    MOD = frais("pm_modules", "PM_MODULES_DIR", mods)
    print("\n[RM3145] un abonnement se valide, et un module qui n'est pas chargé n'écoute pas")

    def module(nom, manifeste, triggers=None):
        d = pathlib.Path(mods) / nom
        (d / "triggers").mkdir(parents=True, exist_ok=True)
        (d / "module.yml").write_text(manifeste, encoding="utf-8")
        for f, t in (triggers or {}).items():
            (d / "triggers" / f).write_text(t, encoding="utf-8")

    module("actif", 'name: actif\nversion: 1.0.0\ndescription: "x"\n',
           {"on-status.yml": 'event: task.status.changed\nwhen: {to: a_tester_demandeur}\nrun: ["echo", "ok"]\n',
            # `on:` reste accepté — YAML en fait un booléen, et le registre le rattrape
            "tout.yml": 'on: task.created\nrun: ["echo", "cree"]\n',
            "sans-run.yml": 'event: task.closed\n',
            "shell.yml": 'event: task.closed\nrun: "echo danger"\n'})
    module("eteint", 'name: eteint\nversion: 1.0.0\ndescription: "x"\nenabled: false\n',
           {"t.yml": 'event: task.created\nrun: ["echo", "jamais"]\n'})
    module("bloque", 'name: bloque\nversion: 1.0.0\ndescription: "x"\nrequires: ["fantome >= 1.0"]\n',
           {"t.yml": 'event: task.created\nrun: ["echo", "jamais"]\n'})

    ts = MOD.triggers()
    par_module = {}
    for t in ts:
        par_module.setdefault(t.module, []).append(t)
    check("seuls les modules chargés ont des abonnements", set(par_module) == {"actif"}, str(set(par_module)))
    check("un abonnement sans « run » est invalide, et le dit",
          any(not t.ok and any("run" in e for e in t.errors) for t in ts))
    check("une commande en CHAÎNE est refusée — un abonné ne passe pas par un shell",
          any(not t.ok and any("LISTE" in e for e in t.errors) for t in ts))

    valides = [t for t in ts if t.ok]
    ev_ok = {"name": "task.status.changed", "payload": {"to": "a_tester_demandeur", "rm_id": "9"}}
    ev_ko = {"name": "task.status.changed", "payload": {"to": "en_cours"}}
    ev_autre = {"name": "task.created", "payload": {"rm_id": "9"}}
    filtre = next(t for t in valides if t.on == "task.status.changed")
    check("le filtre laisse passer ce qu'il vise", filtre.concerne(ev_ok))
    check("…et retient le reste", not filtre.concerne(ev_ko))
    check("…et ne réagit pas à un autre événement", not filtre.concerne(ev_autre))
    sans_filtre = next(t for t in valides if t.on == "task.created")
    check("sans filtre, tout l'événement passe", sans_filtre.concerne(ev_autre))
    check("« on: » écrit par habitude est rattrapé — YAML en ferait un booléen, donc un abonné muet",
          any(t.on == "task.created" for t in valides))
    check("une liste dans le filtre vaut « l'un de »",
          MOD.Trigger("m", pathlib.Path("x"), {"on": "a", "when": {"to": ["x", "y"]}, "run": ["e"]})
          .concerne({"name": "a", "payload": {"to": "y"}}))

# ── le drain, bout en bout ────────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as mods:
    print("\n[RM3145] le drain : un abonné qui échoue n'emporte pas les autres")
    d = pathlib.Path(mods) / "temoin"
    (d / "triggers").mkdir(parents=True)
    (d / "module.yml").write_text('name: temoin\nversion: 1.0.0\ndescription: "x"\n', encoding="utf-8")
    trace = pathlib.Path(tmp) / "trace.txt"
    (d / "triggers" / "ok.yml").write_text(
        f'event: task.created\nrun: ["python3", "-c", "open({str(trace)!r}, \'a\').write(\'ok\\\\n\')"]\n', encoding="utf-8")
    (d / "triggers" / "ko.yml").write_text('event: task.created\nrun: ["python3", "-c", "raise SystemExit(3)"]\n', encoding="utf-8")

    env = dict(os.environ, PM_BUS_DIR=tmp, PM_MODULES_DIR=mods, PM_NOTIFY_DIR=tmp)
    B = frais("pm_bus", "PM_BUS_DIR", tmp)
    ev = B.publish("task.created", rm_id="7", title="t")

    r = subprocess.run([sys.executable, str(HERE / "pm-bus-drain.py"), "--dry-run", "--json"],
                       capture_output=True, text=True, env=env)
    dry = json.loads(r.stdout or "{}")
    check("--dry-run dit ce qui serait lancé", len(dry.get("runs") or []) == 2, r.stdout[:200])
    check("…et ne lance rien", not trace.exists())
    check("…et ne draine rien", len(B.pending()) == 1)

    r = subprocess.run([sys.executable, str(HERE / "pm-bus-drain.py"), "--json"],
                       capture_output=True, text=True, env=env)
    res = json.loads(r.stdout or "{}")
    check("les deux abonnés sont lancés", len(res.get("runs") or []) == 2, r.stdout[:300])
    check("celui qui marche a marché", trace.exists() and "ok" in trace.read_text())
    check("l'échec de l'autre est rapporté", any(not x["ok"] for x in res["runs"]))
    reste = B.pending()
    check("l'événement est drainé malgré l'échec — il ne rejoue pas en boucle", reste == [], str(reste))
    tout = [x for x in B._lire() if x["id"] == ev["id"]]
    check("…et l'erreur est retenue sur l'événement", tout and tout[0].get("error"), str(tout))
    notifs = (pathlib.Path(tmp) / "notifications.jsonl")
    check("le fil est prévenu de l'abonné en échec",
          notifs.is_file() and "échec" in notifs.read_text(encoding="utf-8"))

    B.publish("mr.merged", url="https://x")
    r = subprocess.run([sys.executable, str(HERE / "pm-bus-drain.py"), "--json"],
                       capture_output=True, text=True, env=env)
    res = json.loads(r.stdout or "{}")
    check("un événement que personne n'écoute est drainé quand même",
          not res.get("runs") and B.pending() == [])

print("\n[RM3145] le travail est déclaré et l'émission est câblée")
jobs = (HERE.parent / "jobs.reference.yml").read_text(encoding="utf-8")
check("le drain est un travail de l'ordonnanceur", "bus-drain:" in jobs)
src = (HERE / "pm-task-status-update.py").read_text(encoding="utf-8")
check("un changement de statut publie le fait", 'pm_bus.publish("task.status.changed"' in src)
check("…sans jamais pouvoir bloquer le changement", "except Exception" in src.split("pm_bus.publish")[1][:400])
check("le canal de push vers le cockpit (RM3006) est INTACT et distinct",
      "prévenir le cockpit" in (HERE / "pm_events.py").read_text(encoding="utf-8")
      and 'pm_events.publish(["tickets"' in src)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — bus d'événements et drain (RM3145 lot 2)"))
sys.exit(1 if FAIL else 0)
