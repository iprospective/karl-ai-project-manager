#!/usr/bin/env python3
"""Tests RM2773 — l'état d'une MR est DÉRIVÉ, il ne se stocke pas impunément.

Le worklog figeait `mrs[].state` à l'écriture : seul `pm-mr merge` le remettait à
jour. Toute MR mergée ailleurs — interface de la forge, fermeture automatique parce
que ses commits sont arrivés dans la cible par une autre MR, autre session — restait
affichée « à merger » indéfiniment. Mesuré au signalement : 6 des 14 MR listées
« à merger » étaient déjà mergées.

Les deux directions d'erreur ne se valent pas, et les tests le disent :
afficher une MR déjà mergée use la liste jusqu'à ce qu'on cesse de la lire ; faire
disparaître une MR encore ouverte fait perdre le travail de vue. On verrouille donc
surtout le second cas — une forge injoignable ne doit JAMAIS effacer une ligne.

Lancer : python3 scripts/test_pm_session_status_mr_reconcile.py
"""
import importlib.util
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pss", HERE / "pm-session-status.py")
pss = importlib.util.module_from_spec(spec)
sys.modules["pss"] = pss
spec.loader.exec_module(pss)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


MRS = [
    {"iid": 492, "state": "opened", "url": "https://gl/x/-/merge_requests/492"},
    {"iid": 589, "state": "merged", "url": "https://gl/x/-/merge_requests/589"},
    {"iid": 600, "state": "opened", "url": "https://gl/x/-/merge_requests/600"},
    {"iid": 42,  "state": "closed", "url": "https://gl/x/-/merge_requests/42"},
]

# ── le cas signalé : mergée ailleurs, jamais répercutée ────────────────────
mrs, changed = pss.mr_reconcile(MRS, lambda m: "merged" if m["iid"] == 492 else m["state"])
check("une MR mergée hors pm-mr merge passe à merged",
      [m["state"] for m in mrs if m["iid"] == 492] == ["merged"])
check("le changement est rapporté (iid, avant, après)",
      changed == [(492, "opened", "merged")])
check("elle sort de « à merger »",
      [m["iid"] for m in pss.mr_pending(mrs)] == [600])
check("la réconciliation est datée, pour qu'on sache d'où vient l'état",
      all(m.get("reconciled_ts") for m in mrs if m["iid"] == 492))

# ── ce qu'il ne faut SURTOUT pas casser ────────────────────────────────────
mrs, changed = pss.mr_reconcile(MRS, lambda m: None)
check("forge injoignable (None) : l'état connu est conservé",
      [m["state"] for m in mrs] == ["opened", "merged", "opened", "closed"])
check("forge injoignable : aucun changement annoncé", changed == [])
check("une MR encore ouverte le reste — jamais d'effacement à l'aveugle",
      [m["iid"] for m in pss.mr_pending(mrs)] == [492, 600])

seen = []
pss.mr_reconcile(MRS, lambda m: seen.append(m["iid"]) or m["state"])
check("seules les MR OUVERTES sont réinterrogées (pas d'appel inutile)",
      seen == [492, 600])

mrs, changed = pss.mr_reconcile(MRS, lambda m: "closed" if m["iid"] == 600 else m["state"])
check("une MR fermée sans merge sort aussi de la liste",
      [m["iid"] for m in pss.mr_pending(mrs)] == [492])

mrs, _ = pss.mr_reconcile(MRS, lambda m: m["state"])
check("état inchangé : rien n'est réécrit, pas de reconciled_ts parasite",
      not any(m.get("reconciled_ts") for m in mrs))
check("l'entrée d'origine n'est pas mutée (fonction pure)",
      MRS[0]["state"] == "opened")
check("liste vide ou absente tolérée",
      pss.mr_reconcile([], lambda m: "merged") == ([], [])
      and pss.mr_reconcile(None, lambda m: "merged") == ([], []))

# ── le resolver réel ne lève jamais ────────────────────────────────────────
check("sans URL, l'état est indéterminé plutôt qu'une erreur",
      pss.mr_state_from_forge({"iid": 1}) is None)
check("URL inexploitable : indéterminé, jamais d'exception",
      pss.mr_state_from_forge({"iid": 1, "url": "pas-une-url"}) is None)

# ── bout en bout : la commande écrit le store ──────────────────────────────
with tempfile.TemporaryDirectory() as d:
    store = pathlib.Path(d) / "sess.json"
    store.write_text(json.dumps({"session_id": "sess", "mrs": MRS}), encoding="utf-8")
    data = json.loads(store.read_text(encoding="utf-8"))
    saved = {}
    pss.save = lambda dd: saved.update(dd)          # isole l'écriture disque
    pss.mr_state_from_forge = lambda m: "merged"    # forge simulée

    class A:
        reconcile, list = True, False
    pss.cmd_mr(data, A())
    check("la commande PERSISTE l'état réconcilié (pas seulement l'affichage)",
          [m["state"] for m in saved.get("mrs", [])] == ["merged", "merged",
                                                         "merged", "closed"])

# ── côté cockpit : déclenché, mais jamais bloquant ─────────────────────────
kspec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(kspec)
sys.modules["karl_agent"] = ka
kspec.loader.exec_module(ka)

lancements = []


class _Popen:
    def __init__(self, argv, **kw):
        lancements.append(argv)


ka.subprocess.Popen = _Popen
ka._worklog_mr_checked.clear()

ka._worklog_reconcile_mrs("sess-1", MRS)
check("le rendu du worklog déclenche la réconciliation", len(lancements) == 1)
check("elle vise la bonne session, en sous-processus détaché",
      "--session" in lancements[0] and "sess-1" in lancements[0]
      and "--reconcile" in lancements[0])

ka._worklog_reconcile_mrs("sess-1", MRS)
check("garde de fraîcheur : pas un appel forge par rafraîchissement du cockpit",
      len(lancements) == 1)

ka._worklog_reconcile_mrs("sess-1", MRS, force=True)
check("le ⟳ manuel force la réconciliation", len(lancements) == 2)

ka._worklog_reconcile_mrs("sess-1", [])
check("aucune MR ouverte : aucun appel", len(lancements) == 2)
ka._worklog_reconcile_mrs("", MRS, force=True)
check("sans session_id : aucun appel", len(lancements) == 2)


def _boom(argv, **kw):
    raise OSError("fork impossible")


ka.subprocess.Popen = _boom
ka._worklog_mr_checked.clear()
try:
    ka._worklog_reconcile_mrs("sess-1", MRS)
    check("un lancement qui échoue ne fait pas tomber le worklog", True)
except Exception as e:  # noqa: BLE001
    check("un lancement qui échoue ne fait pas tomber le worklog (%s)" % e, False)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests réconciliation des MR RM2773 passent")
