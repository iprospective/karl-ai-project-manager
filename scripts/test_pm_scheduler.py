#!/usr/bin/env python3
"""Tests RM2792 — ordonnanceur unique des travaux périodiques (pm-scheduler).

Trois familles de pièges couvertes ici :

  * **les expressions cron.** Le champ `*` en jour-de-semaine s'est fait normaliser
    « 7 % 7 = 0 » lors de l'écriture, ce qui écrasait la borne haute sur la basse et
    ne laissait que le dimanche : tous les jobs seraient partis un jour sur sept, et
    rien dans une exécution ponctuelle ne l'aurait montré. D'où des cas étalés sur
    plusieurs jours, et la règle OU du couple jour-du-mois / jour-de-semaine ;
  * **la fenêtre de déclenchement.** Un job jamais vu doit être ARMÉ, pas exécuté —
    sinon ajouter un job quotidien au registre à 15 h le lancerait aussitôt, au titre
    de l'occurrence de 6 h déjà passée. Et une coupure ne doit produire qu'UNE
    exécution, pas une par occurrence manquée ;
  * **l'isolation.** Un job qui échoue, qui déborde, ou qui tourne encore ne doit rien
    faire aux autres.

Lancer : python3 scripts/test_pm_scheduler.py
"""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timedelta

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_support  # noqa: E402

test_support.hermetic_core()

spec = importlib.util.spec_from_file_location("pms", HERE / "pm-scheduler.py")
pms = importlib.util.module_from_spec(spec)
sys.modules["pms"] = pms
try:
    spec.loader.exec_module(pms)
except SystemExit:
    pass

from pm_paths import PMConfig  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def dt(s):
    return datetime.fromisoformat(s)


# ── Expressions cron ─────────────────────────────────────────────────────
M = pms.cron_match

check("*/15 matche 17:45", M("*/15 * * * *", dt("2026-09-04T17:45")))
check("*/15 ne matche pas 17:46", not M("*/15 * * * *", dt("2026-09-04T17:46")))
check("minute fixe", M("0 * * * *", dt("2026-09-04T18:00")))
check("heure fixe", M("30 8 * * *", dt("2026-09-04T08:30")))
check("heure fixe : autre heure exclue", not M("30 8 * * *", dt("2026-09-04T09:30")))
check("liste de minutes", M("0,30 * * * *", dt("2026-09-04T18:30")))
check("intervalle d'heures", M("0 9-17 * * *", dt("2026-09-04T14:00")))
check("intervalle d'heures : hors bornes", not M("0 9-17 * * *", dt("2026-09-04T18:00")))
check("intervalle avec pas", M("0 0-23/6 * * *", dt("2026-09-04T12:00")))

# RÉGRESSION : `*` en jour-de-semaine couvrait le seul dimanche.
semaine = [dt("2026-09-01T12:00") + timedelta(days=i) for i in range(7)]
check("`*` en jour-de-semaine couvre les 7 jours",
      all(M("0 12 * * *", d) for d in semaine))
check("`*` en jour-du-mois couvre tout le mois",
      all(M("0 12 * * *", dt("2026-09-01T12:00") + timedelta(days=i)) for i in range(30)))

check("lundi = 1 (2026-09-07)", M("0 8 * * 1", dt("2026-09-07T08:00")))
check("mardi ≠ lundi", not M("0 8 * * 1", dt("2026-09-08T08:00")))
check("dimanche = 0 (2026-09-06)", M("0 8 * * 0", dt("2026-09-06T08:00")))
check("dimanche = 7 aussi", M("0 8 * * 7", dt("2026-09-06T08:00")))
check("intervalle de jours ouvrés", M("0 8 * * 1-5", dt("2026-09-04T08:00")))
check("samedi hors 1-5", not M("0 8 * * 1-5", dt("2026-09-05T08:00")))

check("1er du mois", M("0 7 1 * *", dt("2026-10-01T07:00")))
check("2 du mois exclu", not M("0 7 1 * *", dt("2026-10-02T07:00")))
check("mois restreint", M("0 7 1 10 *", dt("2026-10-01T07:00")))
check("autre mois exclu", not M("0 7 1 10 *", dt("2026-11-01T07:00")))

# Sémantique cron : jour-du-mois ET jour-de-semaine tous deux restreints ⇒ OU.
check("dom+dow = OU, côté dom", M("0 7 1 * 1", dt("2026-11-01T07:00")))     # dimanche 1er
check("dom+dow = OU, côté dow", M("0 7 1 * 5", dt("2026-09-04T07:00")))     # vendredi 4
check("dom+dow = OU : ni l'un ni l'autre",
      not M("0 7 1 * 1", dt("2026-09-04T07:00")))

for bad in ("* * * *", "* * * * * *", "60 * * * *", "* 24 * * *",
            "*/0 * * * *", "5-2 * * * *", "a * * * *", ""):
    try:
        M(bad, dt("2026-09-04T12:00"))
        check(f"expression invalide refusée : {bad!r}", False)
    except (ValueError, TypeError):
        check(f"expression invalide refusée : {bad!r}", True)


# ── Fenêtre de déclenchement ─────────────────────────────────────────────
NOW = dt("2026-09-04T17:47")

check("jamais exécuté (since=None) → PAS dû (le job est armé, pas lancé)",
      pms.due_since("*/15 * * * *", None, NOW) is False)
check("occurrence dans la fenêtre → dû",
      pms.due_since("*/15 * * * *", dt("2026-09-04T17:40"), NOW) is True)
check("aucune occurrence depuis le dernier passage → pas dû",
      pms.due_since("*/15 * * * *", dt("2026-09-04T17:46"), NOW) is False)
check("le dernier passage lui-même ne recompte pas",
      pms.due_since("0 * * * *", dt("2026-09-04T17:00"),
                    dt("2026-09-04T17:30")) is False)
check("quotidien manqué la nuit → dû",
      pms.due_since("0 7 * * *", dt("2026-09-03T18:00"), NOW) is True)
check("hebdomadaire pas encore tombé → pas dû",
      pms.due_since("0 8 * * 1", dt("2026-09-01T09:00"),
                    dt("2026-09-04T17:47")) is False)
check("coupure au-delà de l'horizon → une seule fois, pas de cascade",
      pms.due_since("0 7 * * *", dt("2026-01-01T00:00"), NOW) is True)

N = pms.next_occurrence
check("prochaine occurrence d'un */15", N("*/15 * * * *", NOW) == dt("2026-09-04T18:00"))
check("prochaine occurrence d'un lundi 8 h",
      N("0 8 * * 1", NOW) == dt("2026-09-07T08:00"))
check("prochaine occurrence d'un mensuel",
      N("0 7 1 * *", NOW) == dt("2026-10-01T07:00"))
check("prochaine occurrence d'un annuel (février)",
      N("0 7 1 2 *", NOW) == dt("2027-02-01T07:00"))


# ── Validation du registre ───────────────────────────────────────────────
def problems(jobs):
    return {jid: msg for jid, msg in pms.validate(jobs)}


ok_job = {"schedule": "0 * * * *", "command": ["true"], "description": "d"}
check("job correct → aucun problème", problems({"a": ok_job}) == {})
check("description manquante détectée",
      "description" in problems({"a": {**ok_job, "description": None}}).get("a", ""))
check("ni command ni shell détecté",
      "command" in problems({"a": {"schedule": "0 * * * *", "description": "d"}}).get("a", ""))
check("command ET shell détecté",
      "command" in problems({"a": {**ok_job, "shell": "true"}}).get("a", ""))
check("command non-liste détecté",
      "liste" in problems({"a": {**ok_job, "command": "true"}}).get("a", ""))
check("schedule invalide détecté",
      "schedule" in problems({"a": {**ok_job, "schedule": "nawak"}}).get("a", ""))
check("timeout invalide détecté",
      "timeout" in problems({"a": {**ok_job, "timeout": 0}}).get("a", ""))


# ── Registre livré ───────────────────────────────────────────────────────
import yaml  # noqa: E402

shipped = yaml.safe_load((HERE.parent / "jobs.reference.yml").read_text(encoding="utf-8"))
shipped_jobs = shipped.get("jobs") or {}
check("le registre livré est valide", pms.validate(shipped_jobs) == [])
check("le registre livré n'est pas vide", len(shipped_jobs) >= 5)
check("le réveil des récurrents y figure (RM2772 lot 4)",
      "recurrent-wake" in shipped_jobs)


# ── Exécution de bout en bout ────────────────────────────────────────────
work = tempfile.TemporaryDirectory(prefix="pm-sched-test-")
root = pathlib.Path(work.name)
witness = root / "temoin.txt"

(root / "jobs.reference.yml").write_text(yaml.safe_dump({"jobs": {
    "temoin":   {"schedule": "* * * * *", "description": "écrit un témoin",
                 "command": ["bash", "-c", f"echo passage >> {witness}"]},
    "casse":    {"schedule": "* * * * *", "description": "sort en erreur",
                 "command": ["bash", "-c", "echo bruit >&2; exit 3"]},
    "lambine":  {"schedule": "* * * * *", "description": "dépasse son temps",
                 "timeout": 1, "command": ["bash", "-c", "sleep 30"]},
    "eteint":   {"schedule": "* * * * *", "description": "désactivé",
                 "enabled": False,
                 "command": ["bash", "-c", f"echo NON >> {witness}"]},
}}), encoding="utf-8")
pms.REPO_ROOT = root

cfg = PMConfig.load()
cfg.state_dir = root / "var"
cfg.log_dir = root / "var" / "log"


class Args:
    only = None
    force = False
    dry_run = False
    json = False


# 1er passage : tout est armé, rien ne tourne.
pms.cmd_run(cfg, Args())
state = json.loads((root / "var" / "scheduler" / "state.json").read_text())
check("1er passage : les jobs actifs sont armés",
      {k for k, v in state.items() if v.get("status") == "armé"} == {"temoin", "casse", "lambine"})
check("1er passage : rien n'a été exécuté", not witness.exists())
check("1er passage : un job désactivé n'est même pas armé", "eteint" not in state)

# On antidate l'armement pour rendre les jobs dus, puis on repasse.
for jid in ("temoin", "casse", "lambine"):
    state[jid]["last_start"] = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
pms.save_state(cfg, state)
try:
    pms.cmd_run(cfg, Args())
except SystemExit as e:
    check("un passage avec échec sort en code ≠ 0", e.code == 1)

state = json.loads((root / "var" / "scheduler" / "state.json").read_text())
check("le job sain a tourné", witness.exists() and "passage" in witness.read_text())
check("le job sain est noté ok", state["temoin"]["status"] == "ok")
check("le job en échec est noté échec", state["casse"]["status"] == "échec")
check("le code retour est conservé", state["casse"]["rc"] == 3)
check("le job qui déborde est tué", state["lambine"]["status"] == "timeout")
check("un job qui casse n'empêche pas les autres",
      state["temoin"]["status"] == "ok" and state["lambine"]["status"] == "timeout")
check("les échecs consécutifs sont comptés",
      state["casse"]["consecutive_failures"] == 1 and state["temoin"]["consecutive_failures"] == 0)
check("un job désactivé n'a pas tourné", "NON" not in witness.read_text())

hist = [json.loads(l) for l in
        (root / "var" / "scheduler" / "history.jsonl").read_text().splitlines()]
check("chaque exécution laisse une trace", {h["job"] for h in hist} == {"temoin", "casse", "lambine"})
check("la trace conserve la sortie", any("bruit" in (h.get("tail") or "") for h in hist))
check("la sortie complète est journalisée par job",
      (root / "var" / "scheduler" / "log" / "casse.log").is_file())

# Non-recouvrement : le verrou du job est déjà pris.
before = witness.read_text()
with pms.resource_lock(pms.sched_dir(cfg) / "temoin.lock", timeout=0):
    entry = pms.run_job(cfg, "temoin", {"schedule": "* * * * *", "description": "d",
                                        "command": ["bash", "-c", f"echo DOUBLON >> {witness}"]})
check("un job déjà en cours n'est pas relancé", entry["status"] == "déjà en cours")
check("et il n'a produit aucun effet", witness.read_text() == before)

# Le passage lui-même ne se recouvre pas non plus.
with pms.resource_lock(pms.sched_dir(cfg) / "scheduler.lock", timeout=0):
    pms.cmd_run(cfg, Args())
check("un passage concurrent ne double pas le travail",
      witness.read_text().count("passage") == 1)

print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)

# ── RM3151 : le DÉCLENCHEUR — un timer systemd user, idempotent ──────────────
print("\n[RM3151] le déclencheur de l'ordonnanceur")
import tempfile as _tf
u = pms.unites("/opt/pm/scripts/pm-scheduler.py", "/usr/bin/python3")
check("deux unités : le service et le timer", set(u) == {"pm-scheduler.service", "pm-scheduler.timer"}, str(list(u)))
check("le service lance bien un PASSAGE d'ordonnancement, pas le script nu",
      u["pm-scheduler.service"].rstrip().endswith("/opt/pm/scripts/pm-scheduler.py run"), u["pm-scheduler.service"])
check("il patiente si le script n'est pas encore déployé, au lieu d'échouer en rouge",
      "ConditionPathExists=/opt/pm/scripts/pm-scheduler.py" in u["pm-scheduler.service"])
check("toutes les 5 minutes", "OnUnitActiveSec=5min" in u["pm-scheduler.timer"])
check("PAS de rattrapage systemd : c'est l'ordonnanceur qui décide de ce qui est dû",
      "Persistent=false" in u["pm-scheduler.timer"])

d = pathlib.Path(_tf.mkdtemp(prefix="pm-timer-"))
check("dossier vide : les deux unités sont à écrire", set(pms.a_ecrire(d, u)) == set(u))
for nom, contenu in u.items():
    (d / nom).write_text(contenu, encoding="utf-8")
check("contenu identique : RIEN à écrire — c'est ça, l'idempotence", pms.a_ecrire(d, u) == [])
(d / "pm-scheduler.timer").write_text("OnUnitActiveSec=1min\n", encoding="utf-8")
check("un contenu qui a changé est repéré, et lui seul", pms.a_ecrire(d, u) == ["pm-scheduler.timer"])

# l'unité vise le RUNTIME, jamais un worktree de ticket (qui sera détruit)
import os as _os
from pm_paths import runtime_script
_av = _os.environ.get("PM_CORE_DIR")
_os.environ["PM_CORE_DIR"] = "/zfs/workspaces/.mmi-pm-core"
chemin, err = runtime_script("pm-scheduler.py")
check("PM_CORE_DIR posé : l'unité vise le runtime canonique", err is None and str(chemin).startswith("/zfs/workspaces/.mmi-pm-core"), str(chemin))
_os.environ.pop("PM_CORE_DIR", None)
_, err2 = runtime_script("pm-scheduler.py", depuis=pathlib.Path("/w/envs/repo-rm42/scripts/x.py"))
check("depuis un worktree, sans repère : REFUS explicite plutôt qu'un timer mort dans six mois",
      err2 and "worktree" in err2, str(err2))
if _av:
    _os.environ["PM_CORE_DIR"] = _av

src = (pathlib.Path(__file__).resolve().parent / "pm-core-update.py").read_text(encoding="utf-8")
check("`core update` pose le timer, en tant que l'utilisateur de l'instance (un timer user posé par root ne sert personne)",
      "install_scheduler_timer" in src and "runuser" in src.split("def install_scheduler_timer")[1][:900])

print("✓ tous les tests passent")
