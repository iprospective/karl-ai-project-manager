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

# — RM2715 : backlog vs archive (fonctions pures) —
mixte = [{"ts": "t1", "level": "warn", "message": "ouverte"},
         {"ts": "t2", "level": "warn", "message": "traitée", "resolved_at": "t3",
          "ticket": "RM2691"}]
check("le backlog ne retient que ce qui appelle encore quelque chose",
      [n["message"] for n in pss.notify_open(mixte)] == ["ouverte"])
check("l'archive retient ce qui a été traité",
      [n["ticket"] for n in pss.notify_done(mixte)] == ["RM2691"])
check("une notification sans champ de résolution est ouverte (rétrocompat)",
      pss.notify_open([{"ts": "t", "message": "ancienne"}]) != [])

resolues, ok = pss.notify_resolve(mixte, 1, ticket="RM2715", note="pris en compte")
check("résoudre marque, ne supprime pas",
      ok and len(resolues) == 2 and resolues[0]["ticket"] == "RM2715"
      and resolues[0]["resolution"] == "pris en compte" and resolues[0]["resolved_at"])
check("l'entrée d'origine n'est pas mutée (fonction pure)",
      "resolved_at" not in mixte[0])
check("un numéro hors bornes ou illisible ne casse rien",
      pss.notify_resolve(mixte, 0)[1] is False
      and pss.notify_resolve(mixte, "x")[1] is False
      and pss.notify_resolve(mixte, 99)[1] is False)

# à l'étroit, c'est l'ARCHIVE qui saute avant les ouvertes
serre = ([{"ts": "a%02d" % i, "level": "warn", "message": "traitée",
           "resolved_at": "r"} for i in range(20)]
         + [{"ts": "o%02d" % i, "level": "warn", "message": "ouverte"} for i in range(5)])
kept = pss.notify_trim(serre, keep=6)
check("le rognage sacrifie l'archive avant les notifications ouvertes",
      len([n for n in kept if not n.get("resolved_at")]) == 5 and len(kept) == 6)

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

    # — RM2715 : résoudre ≠ supprimer —
    run("notify", "--resolve", "2", "--ticket", "RM2691", "--note", "corrigé et livré")
    data = json.loads(pathlib.Path(tmp, "t.json").read_text(encoding="utf-8"))
    n2 = data["notifications"][1]
    check("une notification résolue garde sa place dans le store",
          len(data["notifications"]) == 2 and n2.get("ticket") == "RM2691"
          and n2.get("resolution") == "corrigé et livré" and n2.get("resolved_at"))

    md = pathlib.Path(tmp, "t.md").read_text(encoding="utf-8")
    check("le backlog ne compte plus que les ouvertes",
          "Notifications importantes (1)" in md and "_· 1 traitée(s)_" in md)
    check("la traitée n'est plus dans le backlog mais dans l'archive",
          "Notifications traitées (1)" in md
          and md.index("Notifications importantes") < md.index("Notifications traitées"))
    check("l'archive dit PAR QUOI la notification a été traitée",
          "**RM2691**" in md.split("Notifications traitées")[1])
    check("l'archive passe après le travail, elle ne réclame rien",
          md.index("Reste à faire") < md.index("Notifications traitées"))

    out = run("notify", "--list").stdout
    check("--list numérote et distingue ouverte / traitée",
          "#1 " in out and "ouverte" in out and "✓ traitée RM2691" in out)
    check("résoudre un numéro inconnu échoue proprement",
          run("notify", "--resolve", "99").returncode != 0)
    run("notify", "--resolve", "2", "--ticket", "RM9999")
    data = json.loads(pathlib.Path(tmp, "t.json").read_text(encoding="utf-8"))
    check("re-résoudre corrige la résolution au lieu d'échouer",
          data["notifications"][1]["ticket"] == "RM9999")

    run("notify", "--clear")
    data = json.loads(pathlib.Path(tmp, "t.json").read_text(encoding="utf-8"))
    check("--clear ne vide que l'archive : une notification OUVERTE survit",
          [n["level"] for n in data["notifications"]] == ["critical"]
          and not data["notifications"][0].get("resolved_at"))

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


# — RM2621 : registre des demandes —
R = [{"text": "a", "status": "nouveau"}, {"text": "b", "status": "ticketee", "ticket": "RM1"},
     {"text": "c", "status": "annulee"}, {"text": "d"}]
check("seules les demandes sans suite restent « à traiter »",
      [r["text"] for r in pss.request_open(R)] == ["a", "d"])
check("un statut absent vaut « nouveau » (on ne perd pas une demande mal saisie)",
      any(r.get("text") == "d" for r in pss.request_open(R)))
check("registre vide ou absent toléré",
      pss.request_open([]) == [] and pss.request_open(None) == [])

maj, ok = pss.request_apply(R, "2", "repondu")
check("le numéro AFFICHÉ sert de référence (1-based)", ok and maj[1]["status"] == "repondu")
check("les autres demandes ne bougent pas", maj[0]["status"] == "nouveau")
check("le ticket déjà attaché est conservé", maj[1].get("ticket") == "RM1")
maj2, _ = pss.request_apply(R, "1", "ticketee", ticket="RM2621")
check("attacher un ticket", maj2[0]["ticket"] == "RM2621" and maj2[0]["status"] == "ticketee")
maj3, _ = pss.request_apply(R, "1", "fusionnee", merged_into="2")
check("fusionner garde la trace de la cible", maj3[0].get("merged_into") == "2")
for mauvais in ("0", "99", "abc", None):
    _, ok2 = pss.request_apply(R, mauvais, "repondu")
    check(f"référence invalide refusée : {mauvais!r}", ok2 is False)

# — contrôle d'exhaustivité : il compte, il ne devine pas —
msgs = ["ajoute un onglet git", "ok", "go", "core update fait",
        "au survol, montre le libellé", "/compact", "merci"]
a = pss.request_audit(msgs, [{"text": "ajoute un onglet git"}])
check("les accusés de réception ne comptent pas comme des demandes", a["acks"] == 5)
check("l'écart est calculé sur les vraies demandes", a["expected"] == 2 and a["recorded"] == 1
      and a["gap"] == 1)
check("registre complet → aucun écart",
      pss.request_audit(msgs, [{"text": "x"}, {"text": "y"}])["gap"] == 0)
check("plus d'enregistrements que de messages → pas d'écart négatif",
      pss.request_audit(msgs, [{"text": str(i)} for i in range(9)])["gap"] == 0)
check("transcript vide toléré", pss.request_audit([], [])["gap"] == 0)
# le filtre d'accusés ne doit JAMAIS masquer une vraie demande : il ne sert qu'à
# fixer le nombre attendu, et une demande courte reste une demande
check("une demande courte n'est pas prise pour un accusé",
      pss.request_audit(["fais une sous-tâche"], [])["expected"] == 1)
check("« core update fait » est bien un accusé, pas une demande",
      pss.request_audit(["core update fait"], [])["expected"] == 0)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests canaux worklog (notifications RM2466 + MR RM2583) passent")
