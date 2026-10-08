#!/usr/bin/env python3
"""Tests RM2571 — mettre à jour le code de l'instance DEPUIS le cockpit.

Ce qui doit tenir : le droit sudo exigé est ÉTROIT (une commande nommée, jamais `ALL`) ; le geste est
réservé à un utilisateur `pm` autorisé (toujours en mono-utilisateur, administrateur en multi) ; sans
la règle NOPASSWD le cockpit le dit au lieu d'échouer au clic ; et le suivi relit un FICHIER, pour
survivre au redémarrage de karl-agent que la mise à jour provoque.

Lancer : python3 scripts/test_karl_agent_core_update.py
"""
import importlib.util
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core      # noqa: E402

hermetic_core()
spec = importlib.util.spec_from_file_location("ka", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec); spec.loader.exec_module(ka)
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


LISTE = """User mathieu may run the following commands on dev:
    (mathieu-pm) /opt/core/bin/mmi-pm *
    (root) NOPASSWD: /opt/core/bin/mmi-pm core update*
    (root) /opt/core/scripts/core-lock *
"""

print("[RM2571] la règle sudoers exigée est étroite")
check("la commande nommée est reconnue sans mot de passe",
      ka._nopasswd_cmd(LISTE, "root", "/opt/core/bin/mmi-pm core update"))
check("une AUTRE commande root ne passe pas pour autant",
      not ka._nopasswd_cmd(LISTE, "root", "/opt/core/scripts/core-lock lock"))
check("et on n'exige PAS un sudo général (`ALL`)", not ka._nopasswd_all(LISTE, "root"))
check("une règle sans étiquette (mot de passe) ne compte pas",
      not ka._nopasswd_cmd("""User x may run the following commands on y:
    (root) /opt/core/bin/mmi-pm core update*
""", "root", "/opt/core/bin/mmi-pm core update"))
check("un sudo général, lui, suffirait",
      ka._nopasswd_cmd("""User x may run the following commands on y:
    (ALL) NOPASSWD: ALL
""", "root", "/opt/core/bin/mmi-pm core update"))
check("liste vide (pas de sudo) ⇒ non", not ka._nopasswd_cmd("", "root", "x"))
cmd = ka.core_update_cmd("/opt/core")
check("la commande lancée est le chemin que la règle autorise, en non interactif",
      cmd[:2] == ["sudo", "-n"] and cmd[2:] == ["/opt/core/bin/mmi-pm", "core", "update"], cmd)

print("\n[RM2571] qui a le droit de déclencher")
ka.HOST = "127.0.0.1"
ka._INSTALL_CACHE.update({"at": 9e18, "etat": {"mode": "mono"}})
def gate(ctx):
    try:
        ka._core_update_gate(ctx); return "ok"
    except ka.ApiError as e:
        return e.code
check("mono-utilisateur : l'utilisateur du cockpit peut (il est administrateur de fait)",
      gate({"mode": "login", "user": "mathieu", "admin": False}) == "ok")
check("sans authentification du tout : 401", gate({}) == 401)
check("mode ouvert en écoute LOCALE : autorisé", gate({"mode": "open"}) == "ok")
ka.HOST = "0.0.0.0"
check("mode ouvert en écoute NON locale : refusé (403)", gate({"mode": "open"}) == 403)
ka.HOST = "127.0.0.1"
ka._INSTALL_CACHE.update({"at": 9e18, "etat": {"mode": "multi"}})
check("multi-utilisateur : refusé à un non-administrateur",
      gate({"mode": "login", "user": "paul", "admin": False}) == 403)
check("multi-utilisateur : autorisé à un administrateur",
      gate({"mode": "login", "user": "mathieu", "admin": True}) == "ok")
ka._INSTALL_CACHE.update({"at": 9e18, "etat": {"mode": "mono"}})

print("\n[RM2571] sans la règle NOPASSWD, on le DIT (pas d'échec au clic)")
ka._SUDO_CACHE.update({"at": 9e18, "liste": None, "definitif": True})
check("la sonde répond non quand sudo n'accorde rien", not ka.core_update_sans_mdp())
try:
    ka.op_core_update({"mode": "login", "user": "mathieu", "admin": True})
    check("déclencher sans la règle est refusé en 503 avec la marche à suivre", False)
except ka.ApiError as e:
    check("déclencher sans la règle est refusé en 503 avec la marche à suivre",
          e.code == 503 and "sudoers" in e.msg and "mmi-pm core update" in e.msg, f"{e.code} {e.msg[:60]}")

print("\n[RM2571] le suivi relit un fichier — il survit au redémarrage")
tmp = pathlib.Path(tempfile.mkdtemp(prefix="pm-coreupd-"))
ka._CORE_UPD_RUN = tmp / "core-update.json"
check("aucun run connu : état vide, jamais d'exception",
      ka.op_core_update_log() == {"running": False, "started_at": None, "by": None, "lines": [], "log": None})
log = tmp / "run.log"; log.write_text("étape 1\nétape 2\n", encoding="utf-8")
ka._CORE_UPD_RUN.write_text(json.dumps({"pid": 1, "log": str(log), "by": "mathieu",
                                        "started_at": "2026-10-01T10:00"}), encoding="utf-8")
d = ka.op_core_update_log()
check("les lignes du journal sont rendues, avec qui et quand",
      d["lines"] == ["étape 1", "étape 2"] and d["by"] == "mathieu" and d["started_at"] == "2026-10-01T10:00")
check("pid 1 (init) vivant ⇒ running", d["running"] is True)
ka._CORE_UPD_RUN.write_text(json.dumps({"pid": 999999, "log": str(log)}), encoding="utf-8")
check("pid mort ⇒ run terminé, le journal reste lisible",
      ka.op_core_update_log()["running"] is False and ka.op_core_update_log()["lines"])
ka._CORE_UPD_RUN.write_text(json.dumps({"pid": 1, "log": str(tmp / "absent.log")}), encoding="utf-8")
check("journal disparu : pas d'exception, lignes vides", ka.op_core_update_log()["lines"] == [])
check("pid illisible ⇒ considéré mort, jamais d'exception", not ka._pid_vivant(None) and not ka._pid_vivant("x"))

print("\n[RM2571] le câblage")
src = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("POST /core/update répond 202 (travail détaché)", 'return self._send_json(202, op_core_update(self.auth_ctx))' in src)
check("GET /core/update-log expose l'avancement", 'if path == "/core/update-log":' in src)
check("l'état de MAJ dit au front si le cockpit PEUT appliquer", '"can_update": core_update_sans_mdp()' in src)
check("le travail est détaché (il redémarre karl-agent)", "start_new_session=True" in src.split("def op_core_update(")[1].split("def op_core_update_log")[0])
sudoers = (HERE.parent / "deploy" / "mmi-pm.sudoers.example").read_text(encoding="utf-8")
check("le gabarit sudoers pose NOPASSWD sur la SEULE règle core update",
      "NOPASSWD: <CORE_DIR>/bin/mmi-pm core update*" in sudoers and sudoers.count("NOPASSWD") == 2)
cli = (HERE / "pm-core-update.py").read_text(encoding="utf-8")
check("le CLI passe en `sudo -n` quand la règle est posée, interactif sinon",
      "nopasswd_dispo(entry)" in cli and '["-n"] if sans_mdp else []' in cli)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — core update depuis le cockpit (RM2571)"))
sys.exit(1 if FAIL else 0)
