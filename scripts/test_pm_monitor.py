#!/usr/bin/env python3
"""Tests RM3112 — l'observateur du parc et l'association hôte → client/projet.

Ce qui doit tenir : plusieurs outils d'observation possibles (Zabbix n'est pas codé en dur), le jeton ne
sort jamais, et une association se PROPOSE en disant sa source — jamais en silence, parce qu'une
association devinée envoie un ticket chez le mauvais client.
"""
import importlib
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core            # noqa: E402  RM3119 : un test se donne
hermetic_core()                                   # sa config, il ne compte pas sur celle du dépôt
import pm_monitor as M                                   # noqa: E402
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


print("[RM3112] plusieurs observateurs possibles, aucun codé en dur")
check("Zabbix est un backend parmi d'autres", set(M.BACKENDS) >= {"zabbix", "uptime-kuma"})
check("chacun descend de la même interface", all(issubclass(c, M.Observateur) for c in M.BACKENDS.values()))
check("l'interface tient en trois questions",
      all(hasattr(M.Observateur, m) for m in ("problemes", "hotes", "version")))
try:
    M.UptimeKuma("http://x", "t").problemes(); check("un backend déclaré mais non branché le DIT", False)
except M.MonitorError as e:
    check("un backend déclaré mais non branché le DIT", "pas encore branché" in str(e))

print("\n[RM3112] le jeton ne sort pas (garde-fou 11)")
src = (HERE / "pm_monitor.py").read_text(encoding="utf-8")
check("il part en en-tête, jamais dans l'URL", "Authorization" in src and "?token=" not in src and "&token=" not in src)
check("aucune fonction ne le rend", "def jeton(" not in src and "return self.jeton" not in src)
check("il est lu du .env par pm_secrets", "pm_secrets" in src and "creds_for" in src)
check("aucune écriture vers l'observateur n'est exposée",
      not any(m in src for m in ("event.acknowledge", "def acquitte", "def ack(")))

print("\n[RM3112] Zabbix : ce que son API impose")
appels = []


class FauxZabbix(M.Zabbix):
    def _rpc(self, methode, params):
        appels.append((methode, params))
        if methode == "problem.get":
            return [{"eventid": "1", "objectid": "t1", "name": "disk", "severity": "4", "clock": "1", "acknowledged": "0"},
                    {"eventid": "2", "objectid": "t2", "name": "info", "severity": "1", "clock": "1", "acknowledged": "1"}]
        if methode == "trigger.get":
            return [{"triggerid": "t1", "hosts": [{"host": "srv.cliente.example", "name": "Cliente"}]},
                    {"triggerid": "t2", "hosts": [{"host": "autre.tld", "name": ""}]}]
        return "7.4.11"


z = FauxZabbix("https://z.example", "jeton-factice", "zbx")
pb = z.problemes()
check("les sévérités sont NOMMÉES, pas laissées en chiffres",
      pb[0]["severity_label"] == M.SEVERITES[4] and pb[1]["severity_label"] == M.SEVERITES[1])
check("l'alerte est recollée à son hôte", pb[0]["host"] == "srv.cliente.example" and pb[1]["host"] == "autre.tld")
check("le seuil de gravité est marqué", pb[0]["grave"] and not pb[1]["grave"])
check("un acquittement déjà posé se voit", pb[1]["acknowledged"] and not pb[0]["acknowledged"])
check("filtrer par sévérité minimale", len(z.problemes(severite_min=4)) == 1)
check("apiinfo.version se demande SANS en-tête d'autorisation (Zabbix le refuse)",
      "apiinfo.version" in M.Zabbix.SANS_AUTH)

print("\n[RM3112] l'association se propose, elle ne se devine pas en silence")
connus = {"cliente": ["cliente.example"], "clientd": ["gogs.clientd.example"], "clientb": []}
p = M.proposition("srv-prd.cliente.example", connus)
check("le slug du client dans le nom d'hôte suffit", p["client"] == "cliente" and p["source"] == M.PAR_SLUG)
check("et la confiance le dit", 0 < p["confiance"] < 1)
p = M.proposition("prd.clientd.example", connus)
check("un domaine cité dans les fiches marche aussi", p["client"] == "clientd")
check("la comparaison se fait sur le domaine ENREGISTRABLE, pas sur un suffixe",
      M._racine("a.b.clientd.example") == M._racine("gogs.clientd.example") == "clientd.example")
p = M.proposition("machine.inconnue.tld", connus)
check("rien de sûr : on rend vide plutôt que de choisir au hasard",
      p["client"] == "" and p["confiance"] == 0 and p["source"] == "")
check("« clientd.example » n'est pas coupé au tiret", M._racine("clientd.example") == "clientd.example")

print("\n[RM3112] une association confirmée fait autorité")
with tempfile.TemporaryDirectory() as tmp:
    faux = pathlib.Path(tmp) / "pm.config.local.yml"
    M._local_path = lambda: faux
    check("poser une association l'écrit", M.associe("srv-prd.cliente.example", "clientf", "erp"))
    p = M.proposition("srv-prd.cliente.example", connus)
    check("elle l'emporte sur la proposition par slug",
          p["client"] == "clientf" and p["project"] == "erp" and p["source"] == M.CONFIRME and p["confiance"] == 1.0)
    check("elle est dans la surcharge LOCALE, pas dans le fichier de référence",
          "pm.config.local.yml" in str(faux) and "monitoring" in faux.read_text(encoding="utf-8"))
    check("la retirer rend la main à la proposition",
          M.associe("srv-prd.cliente.example", None, None)
          and M.proposition("srv-prd.cliente.example", connus)["source"] == M.PAR_SLUG)

print("\n[RM3112] le serveur ne crée un ticket que là où il sait le faire")
ka = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("les routes de lecture existent", '"/monitor/alerts"' in ka and '"/monitor/hosts"' in ka)
check("l'association et la création aussi", '"/monitor/assign"' in ka and '"/monitor/ticket"' in ka)
check("créer un ticket EXIGE client et projet, il ne les devine pas",
      "client et projet requis pour créer le ticket" in ka)
check("le ticket passe par le chemin normal de création", "return op_create_ticket({" in ka)
check("et rappelle de ne pas conclure depuis l'alerte seule (garde-fou 16)", "garde-fou 16" in ka)

print("\n[RM3112] l'axe « Observateurs » est déclaré comme les autres")
import pm_provider_types as T                            # noqa: E402
check("l'axe existe", "monitoring" in T.AXES and T.AXE_LABEL.get("monitoring"))
z = T.type_de("zabbix")
check("Zabbix y est, avec sa clé en écriture seule",
      z.get("axis") == "monitoring" and [s[0] for s in z.get("secrets", [])] == ["API_TOKEN"])
check("son préfixe de variable lui est propre", z.get("prefix") == "ZABBIX")

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm_monitor (RM3112)"))
sys.exit(1 if FAIL else 0)
