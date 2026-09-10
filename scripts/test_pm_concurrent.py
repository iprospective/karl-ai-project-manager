#!/usr/bin/env python3
"""Tests RM3086 — jonctions ticket ↔ session, et l'avertissement quand deux sessions se croisent.

Ce que ces tests protègent : RM2818 n'alertait qu'au bouton « nouvelle session » du cockpit. Une
prise depuis un terminal (`pm-task-take`, passage en `en_cours`) ne disait rien, et deux agents se
disputaient la fiche, la branche et le statut du même ticket sans le savoir.

Deux pièges cadrent la règle, et les tests les nomment :
  - une session MORTE ne doit rien déclencher (sinon le signal crie tout le temps et cesse d'être lu) ;
  - l'avertissement n'INTERDIT pas : reprendre un ticket dont la session est finie est le cas normal.

Lancer : python3 scripts/test_pm_concurrent.py
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core                       # noqa: E402
hermetic_core()
import pm_concurrent                                          # noqa: E402
import pm_session                                             # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


REG = {
    "7": {"seq": 7, "claude_session_id": "aaa", "machine": "dev", "tickets": [3086, 12],
          "branches": ["3086-jonctions"], "worktrees": ["/w/env-rm3086"]},
    "8": {"seq": 8, "claude_session_id": "bbb", "machine": "dev", "tickets": [3086]},
    "9": {"seq": 9, "claude_session_id": "ccc", "machine": "autre", "tickets": [999]},
    "10": {"seq": 10, "claude_session_id": "ddd", "tickets": [3086]},        # éteinte
}
VIVANTES = {"aaa", "bbb"}
live = lambda sid: sid in VIVANTES        # noqa: E731

# ── le registre répond enfin à « qui porte ce ticket ? » ────────────────────
sess = pm_session.sessions_of_ticket(3086, REG)
check("les sessions d'un ticket, la plus récente d'abord", [s["seq"] for s in sess] == [10, 8, 7], str([s["seq"] for s in sess]))
check("un ticket d'une autre session n'y est pas", [s["seq"] for s in pm_session.sessions_of_ticket(999, REG)] == [9])
check("« RM3086 » comme « 3086 »", len(pm_session.sessions_of_ticket("RM3086", REG)) == 3)
check("ticket inconnu : liste vide", pm_session.sessions_of_ticket(4242, REG) == [])
check("id invalide : liste vide, pas d'exception", pm_session.sessions_of_ticket("pas-un-id", REG) == [])

# ── les concurrentes : vivantes, et jamais soi-même ────────────────────────
a = pm_concurrent.concurrentes(3086, me="bbb", records=REG, live=live)
check("moi-même exclue", [s["seq"] for s in a] == [7], str([s["seq"] for s in a]))
check("la session ÉTEINTE ne compte pas — un signal qui crie toujours cesse d'être lu",
      10 not in [s["seq"] for s in a])
check("la branche voyage avec (c'est ce qu'on va regarder)", a[0]["branches"] == ["3086-jonctions"])
tout = pm_concurrent.concurrentes(3086, me=None, records=REG, live=live)
check("hors session : les deux vivantes", [s["seq"] for s in tout] == [8, 7])
check("aucune session vivante : rien", pm_concurrent.concurrentes(3086, records=REG, live=lambda s: False) == [])

# ── l'avertissement : il nomme, il propose, il n'interdit pas ──────────────
txt = pm_concurrent.avertissement(3086, a)
check("il nomme la session et sa branche", "#7" in txt and "3086-jonctions" in txt)
check("il dit POURQUOI (fiche, branche, statut disputés)", "fiche" in txt and "statut" in txt)
check("il propose de rejoindre plutôt que d'ouvrir", "Rejoins" in txt)
check("il n'interdit rien — c'est écrit noir sur blanc", "rien n'est bloqué" in txt)
check("aucune concurrente : silence total", pm_concurrent.avertissement(3086, []) == "")

# ── les points d'appel ─────────────────────────────────────────────────────
take = (HERE / "pm-task-take.py").read_text(encoding="utf-8")
statut = (HERE / "pm-task-status-update.py").read_text(encoding="utf-8")
check("pm-task-take avertit à la prise", "pm_concurrent" in take and "avertissement" in take)
check("…et un passage en_cours à la main aussi", "pm_concurrent" in statut and 'args.status == "en_cours"' in statut)
bloc = take[take.index("import pm_concurrent"):]
check("l'avertissement ne bloque jamais la prise (best-effort)", "except Exception" in bloc[:700])
hook = (HERE / "pm_session_hook.py").read_text(encoding="utf-8")
check("le ticket est enregistré au registre partagé dès qu'une opération PM le touche",
      "pm_session.record_ticket" in hook)
ka = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("le cockpit lit la MÊME source (raison « jonction »)",
      '"jonction"' in ka and '"tickets": [str(x) for x in (rec.get("tickets") or [])]' in ka)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — jonctions ticket ↔ session et avertissement (RM3086)")
