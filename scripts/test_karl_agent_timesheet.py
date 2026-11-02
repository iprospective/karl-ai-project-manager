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

# Le calcul rend parfois des journées VOISINES (travail à cheval sur minuit, journée
# ajustée du même mois). Rendre la première affichait une AUTRE journée que celle
# ouverte — ses heures ET sa note (incident du 2026-10-13).
VUE["jours"] = [
    {"date": "2026-06-04", "mesure_min": 0, "proposition": [{"minutes": 45}]},
    {"date": "2026-09-18", "mesure_min": 410, "proposition": []},
]
res_multi = ka.op_timesheet_day({"day": "2026-09-18"})
check("la journée rendue est celle DEMANDÉE, pas la première de la liste",
      res_multi["jour"] and res_multi["jour"]["date"] == "2026-09-18")
check("…et son contenu est bien le sien", res_multi["jour"]["mesure_min"] == 410)
check("une journée absente du calcul rend None, pas une voisine",
      ka.op_timesheet_day({"day": "2026-09-19"})["jour"] is None)
VUE["jours"] = [{"date": "2026-09-18", "mesure_min": 410, "periodes": [["08:51", "09:31"]],
                 "proposition": [{"jour": "2026-09-18", "client": "pisceen", "minutes": 45}],
                 "deja_saisi": [], "regie": [], "ia": [], "surcharge": None, "valide": False}]

refuse("jour malformé refusé", lambda: ka.op_timesheet_day({"day": "18/09/2026"}))
refuse("jour absent refusé", lambda: ka.op_timesheet_day({}))
refuse("injection d'option refusée", lambda: ka.op_timesheet_day({"day": "--apply"}))
refuse("mois malformé refusé", lambda: ka.op_timesheet_month({"month": "2026-9"}))
ka.op_timesheet_month({"month": "2026-09"})
check("le mois passe --month", "--month" in argv and "2026-09" in argv)

# RM3229 L4 : les grilles n'ont besoin que des totaux. Le détail d'un mois pèse 3 Mo
# (commits, traces et tours d'agent de 30 journées) ; le résumé en pèse 9 Ko.
VUE_MOIS = {"periode": "2026-09", "jours": [{
    "date": "2026-09-18", "mesure_min": 415, "valide": False,
    "proposition": [{"client": "pisceen", "minutes": 195},
                    {"client": "calicote", "minutes": 60}],
    "deja_saisi": [{"minutes": 80}], "journal": {"destin": "refacture"},
    "ia": [{}] * 43, "commits": [{"auto": False}] * 14 + [{"auto": True}] * 380,
    "traces": [{}] * 68, "note": {"chemin": "/Notes (2)/2026-09-18.md", "texte": "x" * 900},
    "surcharge": {"debut": "09:00", "fin": "18:00", "lieu": "presentiel", "client": "matnat"},
}]}
_vue_detail = VUE["jours"]
VUE["jours"] = VUE_MOIS["jours"]
VUE["periode"] = "2026-09"
plein = ka.op_timesheet_month({"month": "2026-09"})["jours"][0]
resume = ka.op_timesheet_month({"month": "2026-09", "resume": "1"})["jours"][0]
check("le détail est rendu tel quel sans resume", "traces" in plein and "commits" in plein)
check("le résumé ne porte ni traces ni commits détaillés",
      "traces" not in resume and not isinstance(resume.get("commits"), list))
check("…mais il porte les totaux qui font la grille",
      resume["propose_min"] == 255 and resume["deja_min"] == 80
      and resume["par_client"]["pisceen"] == 195)
check("…le compte des tours d'agent et des commits de travail",
      resume["ia_tours"] == 43 and resume["commits"] == 14)
check("…la présence d'une note, sans son texte",
      resume["note"] == {"fichier": "2026-09-18.md"})
check("…et l'ajustement de la journée",
      resume["ajuste"] is True and resume["lieu"] == "presentiel")
check("le résumé est bien plus léger que le détail",
      len(json.dumps(resume)) * 4 < len(json.dumps(plein)))
VUE["jours"] = _vue_detail


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

ka.op_pm_run({"name": "timesheet-day-adjust",
              "args": {"day": "2026-09-18", "lieu": "distanciel"}})
check("le lieu de travail part avec la journée", "--lieu" in argv and "distanciel" in argv)
refuse("lieu hors des deux valeurs refusé",
       lambda: ka.op_pm_run({"name": "timesheet-day-adjust",
                             "args": {"day": "2026-09-18", "lieu": "bureau"}}))

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

# — la reprise d'une journée : le seul geste destructif, et il est étroit —
rev = cmds.get("timesheet-day-revoke", {})
check("commande de reprise au catalogue", bool(rev))
check("la reprise exige une confirmation", rev.get("confirm") is True and rev.get("mutate") is True)
check("--revoke est imposé par le catalogue",
      any(a.get("const") and a["flag"] == "--revoke" for a in rev.get("args") or []))
check("la reprise ne porte qu'une journée",
      [a["name"] for a in rev.get("args") or [] if a.get("required")] == ["day"])
check("aucune reprise en lot : ni --month, ni --from/--to",
      all(str(a.get("flag")) not in ("--month", "--from", "--to") for a in rev.get("args") or []))

refuse("reprise sans confirmation → refusée",
       lambda: ka.op_pm_run({"name": "timesheet-day-revoke", "args": {"day": "2026-08-26"}}))
ka.op_pm_run({"name": "timesheet-day-revoke", "args": {"day": "2026-08-26"}, "confirm": True})
check("argv de reprise : la journée et --revoke",
      "--day" in argv and "2026-08-26" in argv and "--revoke" in argv)
check("la reprise n'emporte ni --apply ni une autre journée",
      "--apply" not in argv and sum(1 for a in argv if a.startswith("2026-")) == 1)
ka.op_pm_run({"name": "timesheet-day-revoke",
              "args": {"day": "2026-08-26", "dry_run": True}, "confirm": True})
check("simulation possible avant de supprimer", "--dry-run" in argv)

# — la LECTURE ne peut jamais déclencher une reprise (garde-fou du 2026-09-21) —
ka.op_timesheet_day({"day": "2026-08-26"})
check("lire une journée ne supprime rien", "--revoke" not in argv and "--apply" not in argv)
ka.op_timesheet_day({"day": "2026-08-26", "refresh": "1"})
check("rafraîchir une journée ne supprime rien", "--revoke" not in argv)
ka.op_pm_run({"name": "timesheet-day-apply", "args": {"day": "2026-08-26"}, "confirm": True})
check("valider une journée ne supprime rien", "--revoke" not in argv)

# — écrire et corriger UNE ligne (RM3229, 2026-10-14) —
ka.op_pm_run({"name": "timesheet-line-adjust",
              "args": {"day": "2026-08-26", "ligne": "calicote/dolibarr#1855@13",
                       "set_client": "pisceen"}})
check("corriger une ligne vise la journée ET la ligne",
      "--ligne" in argv and "calicote/dolibarr#1855@13" in argv and "--set-client" in argv)
check("corriger un rattachement n'écrit RIEN dans Redmine", "--apply" not in argv)

ka.op_pm_run({"name": "timesheet-line-apply",
              "args": {"day": "2026-08-26", "ligne": "calicote/dolibarr#1855@13"},
              "confirm": True})
check("écrire une ligne porte --apply et la clé de la ligne",
      "--apply" in argv and "calicote/dolibarr#1855@13" in argv)
check("écrire une ligne ne vise qu'une journée",
      sum(1 for a in argv if a.startswith("2026-")) == 1)
check("écrire une ligne ne supprime rien", "--revoke" not in argv)

try:
    ka.op_pm_run({"name": "timesheet-line-apply",
                  "args": {"day": "2026-08-26", "ligne": "x/y#1@1"}})
    _refuse = False
except ka.ApiError as _e:
    _refuse = "confirmation" in str(_e)
check("écrire une ligne sans confirmation est refusé", _refuse)

# — scinder, retirer, ajouter (RM3229, 2026-10-20) —
ka.op_pm_run({"name": "timesheet-line-adjust",
              "args": {"day": "2026-08-26", "ligne": "matnat/infra#-@9", "split": 300}})
check("scinder porte la coupure et la ligne visée",
      "--split" in argv and "300" in argv and "matnat/infra#-@9" in argv)
check("scinder n'écrit rien dans Redmine", "--apply" not in argv)

ka.op_pm_run({"name": "timesheet-line-adjust",
              "args": {"day": "2026-08-26", "ligne": "matnat/infra#-@9", "delete_ligne": True}})
check("retirer une ligne passe par son drapeau", "--delete-ligne" in argv)

ka.op_pm_run({"name": "timesheet-line-add",
              "args": {"day": "2026-08-26", "set_client": "pisceen", "set_minutes": 45,
                       "commentaire": "appel client"}})
check("ajouter une ligne impose --add-ligne et porte ses champs",
      "--add-ligne" in argv and "--set-client" in argv and "pisceen" in argv
      and "45" in argv and "appel client" in argv)
check("ajouter une ligne n'écrit rien dans Redmine", "--apply" not in argv)

# — l'écran et le catalogue parlent la même langue (RM3229, 2026-10-14) —
#
# « args inconnus pour timesheet-day-adjust : ['pause_debut', 'pause_fin'] » : les
# bornes de pause avaient été ajoutées au CLI et au service du cockpit, mais pas
# déclarées au catalogue — la commande partait et était refusée. Aucun test ne
# regardait les deux côtés, alors c'est le seul endroit où le désaccord se voit.
import re

_svc = (HERE.parent / "deploy" / "karl-agent" / "cockpit" / "src" / "modules"
        / "billing" / "billing.service.js")
if _svc.is_file():
    _js = _svc.read_text(encoding="utf-8")
    _cat = {c["name"]: {a["name"] for a in c.get("args", [])}
            for c in ka._PM_COMMANDS_DEFAULT}
    # Options du runner, pas de la commande.
    _runner = {"confirm", "dry_run"}
    _manque = {}
    # 1. les clés passées en objet littéral : run("cmd", { day: …, dry_run: true })
    for _m in re.finditer(r'run\(\s*"([a-z0-9-]+)"\s*,\s*\{([^{}]*)\}', _js):
        _nom, _corps = _m.group(1), _m.group(2)
        if _nom not in _cat:
            continue
        for _k in re.findall(r'(\w+)\s*:', _corps):
            if _k not in _runner and _k not in _cat[_nom]:
                _manque.setdefault(_nom, set()).add(_k)
    # 2. les paires construites en boucle : [["start", f.debut], ["end", …], …]
    _bloc_adjust = re.search(r'async adjust\(\)\s*\{(.*?)\n  \}', _js, re.S)
    if _bloc_adjust:
        for _k in re.findall(r'\[\s*"(\w+)"\s*,', _bloc_adjust.group(1)):
            if _k not in _cat.get("timesheet-day-adjust", set()):
                _manque.setdefault("timesheet-day-adjust", set()).add(_k)
    check("tout ce que l'écran envoie est déclaré au catalogue",
          not _manque or print(f"    manquants : {_manque}"))
    check("les bornes de pause sont déclarées",
          {"pause_debut", "pause_fin"} <= _cat.get("timesheet-day-adjust", set()))

print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("✓ tous les tests passent")
