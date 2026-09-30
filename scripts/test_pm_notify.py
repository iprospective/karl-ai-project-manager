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

with tempfile.TemporaryDirectory() as tmp:
    N = frais(tmp)
    print("\n[RM2792 lot 3] le fil par utilisateur")
    g = N.add("system", "info", "sauvegarde nocturne terminée")
    m = N.add("session", "warn", "ta session attend une réponse", user="Mathieu")
    s1 = N.add("agent", "critical", "clé d'API à renouveler", user="mathieu", private=True)
    autre = N.add("agent", "warn", "revue en attente", user="claire", private=True)
    check("l'identifiant du destinataire est normalisé", m["user"] == "mathieu")
    check("une entrée sans destinataire ne porte pas de user", "user" not in g)
    check("une entrée privée sans destinataire est REFUSÉE",
          N.add("system", "warn", "confidentiel sans personne", private=True) is None)

    vus = [e["id"] for e in N.feed(etat=None, limit=50)]
    check("sans lecteur déclaré, aucune entrée privée n'est rendue",
          g["id"] in vus and m["id"] in vus and s1["id"] not in vus and autre["id"] not in vus)
    vus = [e["id"] for e in N.feed(etat=None, limit=50, viewer="mathieu")]
    check("le lecteur voit SA notification privée", s1["id"] in vus)
    check("et pas celle d'un autre", autre["id"] not in vus)
    vus = [e["id"] for e in N.feed(etat=None, limit=50, viewer="claire")]
    check("réciproquement", autre["id"] in vus and s1["id"] not in vus)

    vus = [e["id"] for e in N.feed(etat=None, limit=50, viewer="mathieu", user="mathieu")]
    check("filtrer par utilisateur rend ce qui le CONCERNE — l'instance comprise",
          g["id"] in vus and m["id"] in vus and s1["id"] in vus)
    check("mais pas ce qui vise quelqu'un d'autre", autre["id"] not in vus)

    check("on ne marque pas le privé d'autrui", N.mark(autre["id"], "traite", viewer="mathieu") == 0)
    check("on marque bien le sien", N.mark(s1["id"], "lu", viewer="mathieu") == 1)
    check("la pastille compte dans la vue du lecteur",
          N.counts(viewer="claire")["open"] < N.counts(viewer="mathieu")["open"] + 1)
    check("les destinataires du fil sont énumérables", N.users() == ["claire", "mathieu"])

    print("\n[RM2792 lot 3] deux destinataires, deux fils")
    a = N.add("session", "warn", "même phrase", user="mathieu")
    b = N.add("session", "warn", "même phrase", user="claire")
    check("le même message à deux personnes fait deux entrées", a["id"] != b["id"])

with tempfile.TemporaryDirectory() as tmp:
    N = frais(tmp)
    print("\n[RM2792 lot 3] le canal mail n'envoie pas deux fois la même chose")
    info = N.add("system", "info", "routine")
    w = N.add("scheduler", "warn", "travail « backup » : échec", job="backup")
    check("ce qui est sous le seuil ne part pas",
          [e["id"] for e in N.pending_mail("warn")] == [w["id"]], str(N.pending_mail("warn")))
    check("marquer l'envoi rend le nombre d'entrées notées", N.mark_mailed([w["id"]]) == 1)
    check("une entrée déjà envoyée ne repart pas", N.pending_mail("warn") == [])
    N.add("scheduler", "warn", "travail « backup » : échec", job="backup")
    check("même répétée à l'identique, elle ne repart pas", N.pending_mail("warn") == [])
    N.add("scheduler", "critical", "travail « backup » : échec", job="backup")
    check("mais si elle EMPIRE, elle repart",
          [e["id"] for e in N.pending_mail("warn")] == [w["id"]])
    N.mark_mailed([w["id"]])
    check("et une fois repartie au nouveau niveau, elle se tait de nouveau", N.pending_mail("warn") == [])
    N.mark(w["id"], "traite")
    N.add("scheduler", "critical", "travail « backup » : échec", job="backup")
    check("une entrée traitée n'est jamais dans la file d'envoi",
          all(e["id"] != w["id"] or e.get("etat") != "traite" for e in N.pending_mail("warn")))
    check("le canal mail ne voit pas non plus le privé d'autrui",
          N.add("agent", "critical", "secret", user="claire", private=True)
          and [e["id"] for e in N.pending_mail("warn", viewer="mathieu")
               if e.get("private")] == [])
    check("une notification d'information ne part jamais par mail",
          info["id"] not in [e["id"] for e in N.pending_mail("warn")])

print("\n[RM2792] les sources sont câblées")
for f, msg in (("pm-scheduler.py", "pm_notify.add(\"scheduler\""), ("pm-session-status.py", "pm_notify.add(\"session\"")):
    src = (HERE / f).read_text(encoding="utf-8")
    check(f"{f} alimente le fil", msg in src)
    check(f"{f} survit à son absence", "except Exception" in src)
ka = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("le serveur sert le fil", "def op_notifications(" in ka and '"/notifications"' in ka)
check("et sait le marquer", "def op_notifications_mark(" in ka and '"/notifications/mark"' in ka)
check("marquer exige un état connu", 'raise ApiError(400, "état inconnu' in ka)
check("le serveur lit le fil AU NOM de celui qui regarde", "viewer=" in ka.split("def op_notifications(")[1][:1200])
check("et ne laisse pas marquer le privé d'autrui", "viewer=" in ka.split("def op_notifications_mark(")[1][:1400])
# RM3300 : deux gestes de lot distincts. « tout lire » ne doit porter QUE sur le non-lu —
# sinon le compte rendu annonce des entrées qu'il n'a pas changées.
_mark = ka.split("def op_notifications_mark(")[1][:1800]
check("« tout lire » ne vise que les entrées neuves",
      'source = "neuf" if etat == "lu" else "ouvert"' in _mark)
check("un lot de marquage respecte le filtre de personne de la vue", "user=str(payload.get(" in _mark)
check("un lot vide n'est pas une erreur", '"marked": 0' in _mark)

# et le geste existe bien des deux côtés du fil
_feed_vue = (HERE.parent / "deploy/karl-agent/cockpit/src/modules/feed/Feed.view.js").read_text(encoding="utf-8")
_feed_ctl = (HERE.parent / "deploy/karl-agent/cockpit/src/modules/feed/feed.controller.js").read_text(encoding="utf-8")
check("le cockpit propose « tout lire »", 'data-action="lu-all"' in _feed_vue and '"lu-all"' in _feed_ctl)
check("et ne l'affiche que s'il y a du non-lu", "vm.counts.neuf ?" in _feed_vue)
check("les deux boutons de lot disent leur effet",
      "tout lire" in _feed_vue and "tout traiter" in _feed_vue)
mailer = HERE / "pm-notify-mail.py"
check("le canal mail existe", mailer.is_file())
if mailer.is_file():
    src = mailer.read_text(encoding="utf-8")
    check("il passe le corps par l'entrée standard, jamais en argument", '"--body", "-"' in src)
    check("il note l'envoi pour ne pas recommencer", "mark_mailed(" in src)
jobs = (HERE.parent / "jobs.reference.yml").read_text(encoding="utf-8")
check("le canal mail est un travail déclaré", "notify-mail:" in jobs)
check("la veille de publication est un travail déclaré", "release-watch:" in jobs)
watch = HERE.parent / "releases.watch.yml"
check("les veilles se déclarent, elles ne se codent pas", watch.is_file()
      and "dani-garcia/vaultwarden" in watch.read_text(encoding="utf-8"))
rw = (HERE / "pm-release-watch.py")
check("la veille alimente le fil", rw.is_file() and 'N.add("forge"' in rw.read_text(encoding="utf-8"))

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm_notify (RM2792 lots 2 et 3)"))
sys.exit(1 if FAIL else 0)
