#!/usr/bin/env python3
"""Tests RM3417 — le budget de contexte notifie, il ne bloque plus.

Ce qui doit tenir : un rôle au-dessus de son plafond **ne fait plus échouer** le
doctor, il produit une **notification** visible au cockpit ; le message reste
stable et les rôles partent en champ, pour qu'une dérive qui dure fasse une
entrée qui remonte au lieu d'une par exécution ; et surtout les **vrais**
invariants (fences, tripwire perdu, outil cité absent) font toujours échouer —
sans quoi on aurait troqué un garde bruyant contre pas de garde du tout.

Le raisonnement : un dépassement de quelques dizaines de tokens sur trente mille
n'est pas une panne, c'est une tendance. Rouge pendant des mois, il n'apprenait
qu'à ignorer les échecs — y compris ceux affichés juste au-dessus.
"""
import importlib.util
import io
import contextlib
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
DOCTOR = HERE / "pm-norms-doctor.py"
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


with tempfile.TemporaryDirectory() as tmp:
    os.environ["PM_NOTIFY_DIR"] = tmp
    sys.path.insert(0, str(HERE))

    spec = importlib.util.spec_from_file_location("nd", DOCTOR)
    nd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nd)
    import pm_notify  # noqa: E402

    print("[RM3417] un rôle au-dessus du plafond ne fait plus échouer le doctor")
    vrai = nd.check_context_budget
    nd.check_context_budget = lambda: ["worker-infra", "orchestrateur"]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = nd.main()
    sortie = buf.getvalue()
    check("le doctor sort en succès", rc == 0, f"rc={rc}")
    check("la ligne budget est informative, pas un échec",
          "· budget contexte" in sortie and "✗ budget contexte" not in sortie,
          [l for l in sortie.splitlines() if "budget" in l])
    check("elle nomme les rôles concernés",
          "worker-infra" in sortie and "orchestrateur" in sortie)
    check("et dit explicitement qu'elle ne bloque pas",
          "PAS bloquant" in sortie, [l for l in sortie.splitlines() if "budget" in l])

    print("\n[RM3417] …mais il le signale au fil, donc au cockpit")
    fil = pm_notify.feed()
    budget = [e for e in fil if e.get("job") == "norms-budget"]
    check("une notification est émise", len(budget) == 1, f"{len(budget)} entrée(s)")
    if budget:
        e = budget[0]
        check("au niveau warn", e["level"] == "warn", e["level"])
        check("les rôles sont en CHAMP, pas dans le texte",
              e.get("roles") == ["orchestrateur", "worker-infra"], str(e.get("roles")))
        check("le message est stable (aucun chiffre ni rôle dedans)",
              "worker-infra" not in e["msg"] and not any(c.isdigit() for c in e["msg"]), e["msg"])

    print("\n[RM3417] une dérive qui dure fait UNE entrée qui remonte")
    for _ in range(4):
        with contextlib.redirect_stdout(io.StringIO()):
            nd.main()
    budget = [e for e in pm_notify.feed() if e.get("job") == "norms-budget"]
    check("toujours une seule entrée", len(budget) == 1, f"{len(budget)}")
    check("mais le compteur dit combien de fois", budget[0]["repeats"] == 5,
          str(budget[0]["repeats"]))

    print("\n[RM3417] un changement de rôles RAFRAÎCHIT l'entrée, il n'en empile pas")
    # C'est l'intérêt d'avoir mis les rôles en champ plutôt que dans le message : la liste
    # peut bouger sans que le fil se remplisse. Si elle était dans le texte, chaque variation
    # écrirait une entrée neuve et l'anti-répétition tomberait — le fil deviendrait le journal
    # qu'il n'est pas. Le risque opposé (une alerte qui garde les chiffres de son premier jour)
    # est couvert par le rafraîchissement des champs, vérifié ici.
    nd.check_context_budget = lambda: ["worker-dev"]
    with contextlib.redirect_stdout(io.StringIO()):
        nd.main()
    budget = [e for e in pm_notify.feed() if e.get("job") == "norms-budget"]
    check("toujours une seule entrée", len(budget) == 1, str(len(budget)))
    check("mais elle dit maintenant le bon rôle",
          budget[0].get("roles") == ["worker-dev"], str(budget[0].get("roles")))
    check("et le compteur a suivi", budget[0]["repeats"] == 6, str(budget[0]["repeats"]))

    print("\n[RM3417] le plafond non configuré reste une info, pas un échec")
    nd.check_context_budget = lambda: None
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = nd.main()
    check("doctor vert", rc == 0)
    check("ligne informative", "· budget contexte : non configuré" in buf.getvalue())

    print("\n[RM3417] les VRAIS invariants bloquent toujours")
    nd.check_context_budget = vrai
    garde = nd.check_runtime_tripwires
    nd.check_runtime_tripwires = lambda: [11, 17]
    with contextlib.redirect_stdout(io.StringIO()) as b2:
        rc = nd.main()
    check("un tripwire perdu par le runtime fait échouer", rc != 0, f"rc={rc}")
    check("et c'est bien un ✗, pas une ligne informative", "✗ tripwires" in b2.getvalue())
    nd.check_runtime_tripwires = garde

    garde2 = nd.check_module_headers
    nd.check_module_headers = lambda: ["un-module.md"]
    with contextlib.redirect_stdout(io.StringIO()):
        rc = nd.main()
    check("un en-tête de module manquant fait échouer", rc != 0, f"rc={rc}")
    nd.check_module_headers = garde2

    print("\n[RM3417] le doctor réel, sur les sources réelles, est vert")
    env = {k: v for k, v in os.environ.items() if k != "PM_CORE_DIR"}
    r = subprocess.run([sys.executable, str(DOCTOR), "--check"],
                       capture_output=True, text=True, env=env)
    check("code de retour 0", r.returncode == 0, (r.stdout or "")[-300:])

    print("\n[RM3417] rien ne crée de ticket sur ce seuil")
    src = DOCTOR.read_text(encoding="utf-8")
    check("le doctor n'appelle pas pm-task-add", "pm-task-add" not in src)
    jobs = (HERE.parent / "jobs.reference.yml").read_text(encoding="utf-8")
    bloc = jobs[jobs.index("norms-budget-watch:"):][:600]
    check("le travail de veille notifie, il ne ticket pas",
          "--notify" in bloc and "task-add" not in bloc)

print()
if FAIL:
    print(f"✗ {len(FAIL)} test(s) en échec :")
    for f in FAIL:
        print(f"   · {f}")
    sys.exit(1)
print("✓ tous les tests passent")
