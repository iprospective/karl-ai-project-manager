#!/usr/bin/env python3
"""Tests RM2662 — la surcharge du coffre par client et par projet, enfin CONSULTÉE.

Le critère resté ouvert : « deux projets, deux instances de vault distinctes ». Le registre savait
résoudre la cascade projet → client → défaut (RM2682), mais un secret à instance implicite
(`secret:<chemin>`) partait à vault-agentd, qui prenait toujours son instance par défaut.

Lancer : python3 scripts/test_pm_secret_instance.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pm_registry import Registry                                  # noqa: E402

spec = importlib.util.spec_from_file_location("psi", HERE / "pm-secret-instance.py")
PSI = importlib.util.module_from_spec(spec); spec.loader.exec_module(PSI)
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


# Un registre à TROIS coffres : le Vaultwarden de l'agence, le KeePass d'un client qui l'impose,
# et un fichier age propre à un seul projet.
REG = Registry.from_config({
    "servers": {
        "vw-ipro": {"axis": "secret", "type": "vaultwarden", "url": "https://vault.example"},
        "kp-acme": {"axis": "secret", "type": "keepass"},
        "age-shop": {"axis": "secret", "type": "age"},
    },
    "defaults": {"secret": "vw-ipro"},
})


class FausseConfig:
    """Ce que PMConfig rend, sans disque : deux clients, trois projets."""
    PROJETS = {
        ("agence", "site"): {},                                          # rien : défaut d'instance
        ("acme", "crm"): {},                                             # hérite du CLIENT
        ("acme", "shop"): {"providers": {"secret": {"instance": "age-shop"}}},   # surcharge PROJET
    }
    CLIENTS = {"agence": {}, "acme": {"providers": {"secret": {"instance": "kp-acme"}}}}

    def __init__(self, ici):
        self.ici = ici

    def detect_project_from_cwd(self, start=None):
        return self.ici

    def project_meta(self, e, p):
        return self.PROJETS.get((e, p), {})

    def client_meta(self, e):
        return self.CLIENTS.get(e, {})


print("[RM2662] deux projets, deux coffres — et la cascade dans le bon ordre")
inst, src = PSI.instance_pour(FausseConfig(("agence", "site")), REG)
check("un projet sans surcharge prend le coffre par DÉFAUT", inst == "vw-ipro", f"{inst} ({src})")
inst, src = PSI.instance_pour(FausseConfig(("acme", "crm")), REG)
check("un projet d'un client qui impose son coffre prend CELUI DU CLIENT", inst == "kp-acme", f"{inst} ({src})")
inst, src = PSI.instance_pour(FausseConfig(("acme", "shop")), REG)
check("la surcharge du PROJET passe avant celle de son client", inst == "age-shop", f"{inst} ({src})")
inst, src = PSI.instance_pour(FausseConfig(None), REG)
check("hors projet : aucune instance imposée, et le motif le dit", inst is None and "hors projet" in src)

print("\n[RM2662] la réécriture ne touche QUE l'instance implicite")
check("secret:<chemin> reçoit l'instance du projet",
      PSI.reecrit("secret:prod/db", "kp-acme") == "secret://kp-acme/prod/db")
check("…champ compris", PSI.reecrit("secret:prod/db#password", "kp-acme") == "secret://kp-acme/prod/db#password")
check("secret://<instance>/… n'est JAMAIS réécrit — l'appelant a choisi",
      PSI.reecrit("secret://vw-ipro/prod/db", "kp-acme") == "secret://vw-ipro/prod/db")
check("vaultwarden://… non plus — la forme historique désigne le défaut, par contrat",
      PSI.reecrit("vaultwarden://o/c/i", "kp-acme") == "vaultwarden://o/c/i")
check("sans instance résolue, l'URI repart inchangée — jamais pire qu'avant",
      PSI.reecrit("secret:prod/db", None) == "secret:prod/db")

print("\n[RM2662] le résolveur ne casse jamais le secret qu'il sert")
sh = (HERE / "resolve-secret.sh").read_text(encoding="utf-8")
check("resolve-secret.sh passe par le résolveur pour secret:", "pm-secret-instance.py" in sh)
check("…et retombe sur l'URI d'origine s'il échoue", "|| printf '%s' \"$URI\"" in sh)
check("…sans toucher secret:// ni vaultwarden://", "secret://*|vaultwarden://*) ;;" in sh)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — coffre par client/projet (RM2662)"))
sys.exit(1 if FAIL else 0)
