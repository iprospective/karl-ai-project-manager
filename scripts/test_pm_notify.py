#!/usr/bin/env python3
"""Tests RM2792 (lot 2) — le fil de notifications de l'instance.

Ce qui doit tenir : une file, pas une trace. Chaque entrée attend d'être lue puis traitée ; une
notification ré-émise remonte au lieu de se dupliquer ; les sources connues sont nommées ; et la garde de
taille n'oublie jamais ce qui attend encore.
"""
import importlib
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def frais(d):
    os.environ["PM_NOTIFY_DIR"] = str(d)
    if "pm_notify" in sys.modules:
        del sys.modules["pm_notify"]
    return importlib.import_module("pm_notify")


with tempfile.TemporaryDirectory() as tmp:
    N = frais(tmp)
    print("[RM2792] une file, pas une trace")
    e = N.add("scheduler", "warn", "travail « x » : échec", job="x", rc=3)
    check("une notification entre à l'état « neuf »", e and e["etat"] == "neuf" and e["repeats"] == 1)
    check("elle porte son origine, son niveau, son horodatage", e["origin"] == "scheduler" and e["level"] == "warn" and e["ts"])
    check("et ses références", e["job"] == "x" and e["rc"] == 3)

    print("\n[RM2792] anti-répétition : la même notification remonte, elle ne se duplique pas")
    for _ in range(5):
        N.add("scheduler", "warn", "travail « x » : échec", job="x", rc=3)
    fil = N.feed()
    check("cinq ré-émissions, une seule entrée", len(fil) == 1, str(len(fil)))
    check("mais le compteur dit combien de fois", fil[0]["repeats"] == 6)
    check("et la date de dernière occurrence suit", fil[0]["last"] >= fil[0]["ts"])
    N.add("scheduler", "critical", "travail « x » : échec", job="x", rc=3)
    check("un niveau plus grave fait monter l'entrée, jamais redescendre", N.feed()[0]["level"] == "critical")
    N.add("scheduler", "warn", "travail « x » : échec", job="y", rc=3)
    check("une référence différente est une AUTRE notification", len(N.feed()) == 2)

    print("\n[RM2792] lu, traité, et ce qui reste à faire")
    ids = [x["id"] for x in N.feed()]
    check("marquer « lu » ne sort pas de la file", N.mark(ids[0], "lu") == 1 and len(N.feed(etat="ouvert")) == 2)
    check("marquer « traité » sort de la file", N.mark(ids[0], "traite") == 1 and len(N.feed(etat="ouvert")) == 1)
    check("mais l'entrée existe toujours", len(N.feed(etat=None)) == 2)
    check("re-marquer ce qui l'est déjà ne change rien", N.mark(ids[0], "traite") == 0)
    check("un état inventé est refusé", N.mark(ids[1], "archivé") == 0)
    c = N.counts()
    check("le compte dit ce qui attend et au pire niveau", c["open"] == 1 and c["worst"] in N.NIVEAUX)

    print("\n[RM2792] une notification traitée peut revenir")
    N.add("scheduler", "critical", "travail « x » : échec", job="x", rc=3)
    check("ré-émise après traitement, elle rentre comme neuve",
          len([e for e in N.feed(etat="ouvert") if e.get("job") == "x"]) == 1)

    print("\n[RM2792] filtres et bornes")
    N.add("session", "info", "quelque chose de bénin", sid="s1")
    check("filtre par origine", {e["origin"] for e in N.feed(origine="session")} == {"session"})
    check("filtre par niveau MINIMAL", all(N.NIVEAUX.index(e["level"]) >= 1 for e in N.feed(niveau="warn")))
    check("origine inconnue → rangée dans « system »", N.add("inventée", "info", "z")["origin"] == "system")
    check("niveau inconnu → « info »", N.add("system", "urgentissime", "z2")["level"] == "info")

    print("\n[RM2792] la garde de taille est MOLLE, par conception")
    # Un fil qui jette ce qui attend pour tenir une taille est pire qu'un fil trop long : il fait
    # disparaître du travail. La garde n'oublie donc que des entrées TRAITÉES, quitte à dépasser.
    N.GARDE = 12
    avant_ouverts = len([e for e in N.feed(etat="ouvert", limit=1000)])
    for i in range(30):
        e = N.add("system", "info", f"bruit {i}")
        if i % 2 == 0:
            N.mark(e["id"], "traite")
    tout = N.feed(etat=None, limit=1000)
    ouverts = [e for e in tout if e["etat"] != "traite"]
    traitees = [e for e in tout if e["etat"] == "traite"]
    check("les entrées traitées sont oubliées en premier", len(traitees) <= 2, str(len(traitees)))
    check("TOUT ce qui attend a survécu, même au-delà de la garde",
          len(ouverts) == avant_ouverts + 15, f"{len(ouverts)} vs {avant_ouverts + 15}")
    check("le fil ne dépasse donc que de ce qu'il ne pouvait pas jeter", len(tout) == len(ouverts) + len(traitees))

with tempfile.TemporaryDirectory() as tmp:
    N = frais(tmp)
    print("\n[RM2792] le fil ne casse pas ce qu'il observe")
    N.add("system", "info", "avant")
    (pathlib.Path(tmp) / N.FICHIER).write_text("ceci n'est pas du JSON\n{\"id\":\"ok\"}\n", encoding="utf-8")
    check("une ligne illisible est ignorée, pas fatale", [e.get("id") for e in N.feed(etat=None)] == ["ok"])
    os.environ["PM_NOTIFY_DIR"] = "/proc/interdit/nulle-part"
    if "pm_notify" in sys.modules:
        del sys.modules["pm_notify"]
    M = importlib.import_module("pm_notify")
    check("un fil inaccessible rend None plutôt que de lever", M.add("system", "info", "x") is None)
    check("et sa lecture rend une liste vide", M.feed() == [])

print("\n[RM2792] les sources sont câblées")
for f, msg in (("pm-scheduler.py", "pm_notify.add(\"scheduler\""), ("pm-session-status.py", "pm_notify.add(\"session\"")):
    src = (HERE / f).read_text(encoding="utf-8")
    check(f"{f} alimente le fil", msg in src)
    check(f"{f} survit à son absence", "except Exception" in src)
ka = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("le serveur sert le fil", "def op_notifications(" in ka and '"/notifications"' in ka)
check("et sait le marquer", "def op_notifications_mark(" in ka and '"/notifications/mark"' in ka)
check("marquer exige un état connu", 'raise ApiError(400, "état inconnu' in ka)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm_notify (RM2792 lot 2)"))
sys.exit(1 if FAIL else 0)
