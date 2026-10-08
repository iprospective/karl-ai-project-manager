#!/usr/bin/env python3
"""Tests RM3274 (lot 2) — le hook qui signale et ouvre la rotation tout seul.

Ce qui doit tenir : un tour qui montre un secret déclenche sans geste de l'agent ;
le ticket part bien en `security` / `immediat` ; **rien de ce qui sort ne contient
la valeur** ; un même secret revu ne rouvre pas de ticket ; le plafond de session
empêche l'emballement ; et le hook ne fait jamais échouer le tour, quoi qu'on lui
donne à lire.

Aucun test n'écrit dans Redmine : on vérifie l'argv construit, pas son exécution.
"""
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("pm_secret_watch", HERE / "pm-secret-watch.py")
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)
import pm_secret_scan as S  # noqa: E402

GLPAT = "glpat-" + "a1b2c3d4e5f6g7h8i9j0"
AUTRE = "glpat-" + "z9y8x7w6v5u4t3s2r1q0"


def transcript(tmp, blocs):
    """Écrit un .jsonl minimal : un prompt humain puis des messages assistant."""
    p = pathlib.Path(tmp) / "t.jsonl"
    lignes = [{"type": "user", "message": {"role": "user", "content": "fais le travail"}}]
    for role, texte, typ in blocs:
        lignes.append({"type": role,
                       "message": {"role": role, "content": [{"type": typ, "text": texte}]}})
    p.write_text("\n".join(json.dumps(x) for x in lignes), encoding="utf-8")
    return p


with tempfile.TemporaryDirectory() as tmp:
    import os
    os.environ["PM_SECRET_WATCH_DIR"] = tmp

    print("[RM3274] le tour est relu, le secret est vu")
    t = transcript(tmp, [("assistant", f"voici la sortie : {GLPAT}", "text")])
    tick = W._mod("pm-task-tick.py", "pm_task_tick")
    montre, dit = W.dernier_tour(tick._load_transcript(str(t)))
    check("le texte du tour est relu", GLPAT in montre)
    res = W.traiter(montre, dit, cwd=tmp, sid="s1", rm_courant=1234, dry_run=True)
    check("un incident est levé", res.get("incident") is True)
    check("le libellé nomme la nature du secret",
          "jeton GitLab (glpat-)" in (res.get("labels") or []), str(res.get("labels")))

    print("\n[RM3274] rien de ce qui sort ne contient la valeur")
    check("le message du fil ne porte pas le secret", GLPAT not in res["message"])
    check("ni sa seconde moitié", GLPAT[len(GLPAT) // 2:] not in res["message"])
    inc = S.incident(montre, dit)
    cmd = W.commande_ticket(inc, 1234)
    check("l'argv du ticket ne porte pas le secret", not any(GLPAT in str(a) for a in cmd))
    check("le corps du ticket non plus", GLPAT not in W.corps_ticket(inc, 1234))
    check("mais l'empreinte y est, pour relier deux occurrences",
          any(f in W.corps_ticket(inc, 1234) for f in inc["fingerprints"]))

    print("\n[RM3274] le ticket part en security / immediat — l'arbitrage du 2026-09-21")
    check("type security", "security" in cmd and cmd[cmd.index("--type") + 1] == "security")
    check("priorité immediat", cmd[cmd.index("--priority") + 1] == "immediat")
    check("l'id est capté de --porcelain, jamais prédit (tripwire #13)", "--porcelain" in cmd)
    check("le titre dit de quoi il s'agit",
          "régénérer" in cmd[cmd.index("--title") + 1].lower())

    print("\n[RM3274] le niveau est critical, sans palier")
    check("aucun chemin de code n'émet autre chose que critical",
          '"warn"' not in (HERE / "pm-secret-watch.py").read_text(encoding="utf-8")
          and '"info"' not in (HERE / "pm-secret-watch.py").read_text(encoding="utf-8"))

    print("\n[RM3274] un même secret revu ne rouvre pas de ticket")
    W._etat_ecrire({"incidents": {inc["key"]: {"ts": "x", "labels": inc["labels"],
                                               "rm_rotation": 9999, "msg": "déjà vu"}},
                    "sessions": {"s1": 1}})
    res2 = W.traiter(montre, dit, cwd=tmp, sid="s1", rm_courant=1234, dry_run=True)
    check("l'incident est reconnu comme déjà connu", res2.get("deja_connu") is True)
    check("et renvoie vers le ticket de rotation existant", res2.get("rm_rotation") == 9999)

    print("\n[RM3274] le plafond de session arrête l'ouverture, pas l'alerte")
    W._etat_ecrire({"incidents": {}, "sessions": {"s2": 3}})
    os.environ["PM_SECRET_WATCH_MAX"] = "3"
    montre3, dit3 = f"autre fuite : {AUTRE}", "je le signale"
    res3 = W.traiter(montre3, dit3, cwd=tmp, sid="s2", rm_courant=1234, dry_run=True)
    check("l'incident est toujours levé", res3.get("incident") is True)
    check("mais aucun ticket n'est ouvert", res3.get("plafonne") is True)
    check("et le message le dit, au lieu de se taire",
          "plafond" in res3["message"].lower(), res3["message"][-80:])
    del os.environ["PM_SECRET_WATCH_MAX"]

    print("\n[RM3274] un tour sans secret ne déclenche rien")
    W._etat_ecrire({})
    t2 = transcript(tmp, [("assistant", "j'ai lu trois fichiers et lancé les tests", "text")])
    m2, d2 = W.dernier_tour(tick._load_transcript(str(t2)))
    check("rien à signaler", W.traiter(m2, d2, cwd=tmp, sid="s3", dry_run=True) == {"incident": False})

    print("\n[RM3274] un chemin de fichier ne déclenche rien (faux positif RM2826)")
    t3 = transcript(tmp, [("assistant", "édité /zfs/workspaces/prestashop/modules/customshippingrate", "text")])
    m3, d3 = W.dernier_tour(tick._load_transcript(str(t3)))
    check("pas d'incident sur un chemin", W.traiter(m3, d3, cwd=tmp, sid="s3", dry_run=True).get("incident") is not True)

    print("\n[RM3274] le hook ne fait jamais échouer le tour")
    exe = [sys.executable, str(HERE / "pm-secret-watch.py")]
    for nom, entree in (("payload vide", ""),
                        ("JSON cassé", "{pas du json"),
                        ("transcript inexistant", json.dumps({"transcript_path": "/n/existe/pas"})),
                        ("payload sans transcript", json.dumps({"session_id": "s"}))):
        p = subprocess.run(exe, input=entree, capture_output=True, text=True, timeout=60,
                           env={**os.environ, "PM_SECRET_WATCH_DIR": tmp})
        check(f"{nom} → code 0", p.returncode == 0, f"code {p.returncode} {p.stderr[-120:]}")

    print("\n[RM3274] --text et --dry-run n'écrivent rien")
    W._etat_ecrire({})
    p = subprocess.run(exe + ["--text", f"fuite {AUTRE}", "--dry-run"],
                       capture_output=True, text=True, timeout=60,
                       env={**os.environ, "PM_SECRET_WATCH_DIR": tmp})
    check("la sortie signale l'incident", "SÉCURITÉ" in p.stdout, p.stdout[:120])
    check("sans jamais montrer la valeur", AUTRE not in p.stdout and AUTRE not in p.stderr)
    check("et la mémoire d'incidents reste vide", not W._etat_lire().get("incidents"))

print()
if FAIL:
    print(f"✗ {len(FAIL)} test(s) en échec :")
    for f in FAIL:
        print(f"   · {f}")
    sys.exit(1)
print("✓ tous les tests passent")
