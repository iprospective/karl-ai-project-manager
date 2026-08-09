#!/usr/bin/env python3
"""Tests RM2589 — le dépôt cible d'un `pm-task-take` ne dépend plus du cwd.

La recherche partait du répertoire courant : lancé ailleurs qu'à la racine du
workspace, `take` ne trouvait pas l'env de session pourtant créé juste avant,
retombait sur `.` sans le dire, et la branche partait sur le mauvais dépôt.

Lancer : python3 scripts/test_pm_task_take_repo.py
"""
import importlib.util
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("ptt", HERE / "pm-task-take.py")
ptt = importlib.util.module_from_spec(spec)
sys.modules["ptt"] = ptt
try:
    spec.loader.exec_module(ptt)
except SystemExit:
    pass

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def make_ws(tmp, with_env=True):
    ws = pathlib.Path(tmp) / "ws"
    (ws / ".mmi-pm" / "tasks").mkdir(parents=True)
    md = ws / ".mmi-pm" / "tasks" / "RM42_x.md"
    md.write_text("---\n---\n", encoding="utf-8")
    if with_env:
        (ws / "envs" / "proj-rm42").mkdir(parents=True)
    return ws, md


with tempfile.TemporaryDirectory() as tmp:
    ws, md = make_ws(tmp)
    attendu = str(ws / "envs" / "proj-rm42")

    # le cœur du bug : le résultat ne doit plus dépendre d'où l'on se trouve
    resultats = {cwd: ptt.resolve_session_repo(md, 42, [], cwd)
                 for cwd in (str(ws), "/tmp", str(ws / ".mmi-pm"), str(ws / "envs"))}
    check("même dépôt quel que soit le répertoire de lancement",
          {r[0] for r in resultats.values()} == {attendu})
    check("l'origine annoncée est le workspace de la tâche",
          all(r[1] == "env de session du workspace" for r in resultats.values()))

    # le registre de session reste prioritaire (source la plus sûre)
    r, org = ptt.resolve_session_repo(md, 42, ["/ailleurs/x-rm42"], str(ws))
    check("le registre de session prime sur la recherche disque", r == "/ailleurs/x-rm42")
    check("et l'origine le dit", org == "registre de session")

    # un worktree d'un AUTRE ticket ne doit pas être capté
    r, _ = ptt.resolve_session_repo(md, 42, ["/ailleurs/x-rm99"], str(ws))
    check("un env d'un autre ticket n'est pas confondu", r == attendu)

with tempfile.TemporaryDirectory() as tmp:
    ws, md = make_ws(tmp, with_env=False)
    r, org = ptt.resolve_session_repo(md, 42, [], "/tmp")
    check("sans env de session : repli sur le cwd, comme avant", r == ".")
    check("mais le repli est NOMMÉ (plus de retombée silencieuse)",
          "aucun env de session" in org)

    # repli cwd : si l'env existe là où l'on est, on le prend — et on le dit
    (pathlib.Path(tmp) / "ailleurs" / "envs" / "autre-rm42").mkdir(parents=True)
    r, org = ptt.resolve_session_repo(md, 42, [], str(pathlib.Path(tmp) / "ailleurs"))
    check("env trouvé depuis le cwd : retenu, et annoncé comme tel",
          r.endswith("autre-rm42") and org == "env trouvé depuis le cwd")

check("chaque résolution rend une origine non vide (le take doit pouvoir la dire)",
      all(bool(ptt.resolve_session_repo(md, 42, w, c)[1])
          for w in ([], ["/x-rm42"]) for c in ("/tmp", str(ws))))

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests résolution du dépôt RM2589 passent")
