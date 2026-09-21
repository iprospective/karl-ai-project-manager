#!/usr/bin/env python3
"""Tests RM3229 — la journée de travail servie au cockpit, et sa validation.

Unitaire, sans réseau ni Redmine : le sous-processus `pm-timesheet.py` est remplacé.
Ce qui est vérifié tient en une phrase : l'écran ne peut demander QUE la journée
qu'il affiche, et il ne peut pas la faire écrire sans confirmation.

Lancer : python3 scripts/test_karl_agent_timesheet.py
"""
import importlib.util
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def refuse(name, fn, code=400):
    try:
        fn()
        check(name, False)
    except ka.ApiError as e:
        check(name, e.code == code)


VUE = {"periode": "2026-09-18", "jours": [{
    "date": "2026-09-18", "mesure_min": 410, "periodes": [["08:51", "09:31"]],
    "proposition": [{"jour": "2026-09-18", "client": "pisceen", "minutes": 45}],
    "deja_saisi": [], "regie": [], "ia": [], "surcharge": None, "valide": False,
}]}

argv = []


def fake_run(cmd, **kw):
    argv.clear()
    argv.extend(cmd)

    class R:
        returncode = 0
        stdout = json.dumps(VUE, ensure_ascii=False)
        stderr = ""
    return R()


ka.subprocess.run = fake_run

# — lecture d'une journée —
res = ka.op_timesheet_day({"day": "2026-09-18"})
check("la journée est rendue seule (pas l'enveloppe du mois)",
      res["day"] == "2026-09-18" and res["jour"]["mesure_min"] == 410)
check("argv : --day et --json", "--day" in argv and "2026-09-18" in argv and "--json" in argv)
check("pas de rejeu par défaut (le cache du jour sert l'écran)", "--refresh" not in argv)
ka.op_timesheet_day({"day": "2026-09-18", "refresh": "1"})
check("refresh=1 rejoue les traces", "--refresh" in argv)

refuse("jour malformé refusé", lambda: ka.op_timesheet_day({"day": "18/09/2026"}))
refuse("jour absent refusé", lambda: ka.op_timesheet_day({}))
refuse("injection d'option refusée", lambda: ka.op_timesheet_day({"day": "--apply"}))
refuse("mois malformé refusé", lambda: ka.op_timesheet_month({"month": "2026-9"}))
ka.op_timesheet_month({"month": "2026-09"})
check("le mois passe --month", "--month" in argv and "2026-09" in argv)


class Casse:
    returncode, stdout, stderr = 1, "", "Aucune trace sur la période"


ka.subprocess.run = lambda *a, **k: Casse()
refuse("un script en échec devient une erreur lisible, pas un 500 muet",
       lambda: ka.op_timesheet_day({"day": "2026-09-18"}))
ka.subprocess.run = fake_run

# — le catalogue : ajuster et valider —
cmds = {c["name"]: c for c in ka._PM_COMMANDS_DEFAULT}
adj, app = cmds.get("timesheet-day-adjust", {}), cmds.get("timesheet-day-apply", {})
check("commande d'ajustement au catalogue", bool(adj))
check("commande de validation au catalogue", bool(app))
check("les deux sont annoncées mutantes (donc journalisées)",
      adj.get("mutate") is True and app.get("mutate") is True)
check("la VALIDATION exige une confirmation explicite", app.get("confirm") is True)
check("l'ajustement n'en exige pas (il n'écrit que la surcharge locale)",
      not adj.get("confirm"))
check("script réel et conforme à l'allowlist",
      (HERE / app["script"]).is_file() and ka._PM_SCRIPT_RE.match(app["script"]))
check("--apply est imposé par le catalogue, jamais par le client",
      any(a.get("const") and a["flag"] == "--apply" for a in app.get("args") or []))
check("la journée est requise à la validation",
      any(a["name"] == "day" and a.get("required") for a in app.get("args") or []))
check("aucun --month exposé : on ne valide pas un mois en bloc",
      all("--month" not in str(a.get("flag")) for c in (adj, app) for a in c.get("args") or []))

refuse("validation sans confirmation → refusée",
       lambda: ka.op_pm_run({"name": "timesheet-day-apply", "args": {"day": "2026-09-18"}}))

ka.op_pm_run({"name": "timesheet-day-apply", "args": {"day": "2026-09-18"}, "confirm": True})
check("argv de validation : la journée et --apply",
      "--day" in argv and "2026-09-18" in argv and "--apply" in argv)
check("aucune autre journée ne se glisse dans l'argv",
      sum(1 for a in argv if a.startswith("2026-")) == 1)

refuse("date invalide à la validation",
       lambda: ka.op_pm_run({"name": "timesheet-day-apply",
                             "args": {"day": "2026-13-45"}, "confirm": True}))

ka.op_pm_run({"name": "timesheet-day-adjust",
              "args": {"day": "2026-09-18", "start": "09:00", "end": "18:00",
                       "client": "pisceen", "exclusif": True}})
check("argv d'ajustement : heures, client, exclusivité",
      "--start" in argv and "09:00" in argv and "--end" in argv
      and "--client" in argv and "pisceen" in argv and "--exclusif" in argv)

refuse("heure invalide refusée",
       lambda: ka.op_pm_run({"name": "timesheet-day-adjust",
                             "args": {"day": "2026-09-18", "start": "25:00"}}))
refuse("heure sans minutes refusée",
       lambda: ka.op_pm_run({"name": "timesheet-day-adjust",
                             "args": {"day": "2026-09-18", "start": "9h"}}))

# — les nouveaux types de validation, isolément —
check("type date accepte AAAA-MM-JJ",
      ka._pm_validate_arg({"name": "d", "type": "date"}, "2026-09-18") == "2026-09-18")
refuse("type date refuse le reste",
       lambda: ka._pm_validate_arg({"name": "d", "type": "date"}, "2026-9-8"))
check("type time accepte HH:MM",
      ka._pm_validate_arg({"name": "t", "type": "time"}, "08:05") == "08:05")
refuse("type time refuse 61 minutes",
       lambda: ka._pm_validate_arg({"name": "t", "type": "time"}, "08:61"))

print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("✓ tous les tests passent")
