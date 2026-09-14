#!/usr/bin/env python3
"""Tests RM3095 — le journal écrit quelque part, le dit quand il ne peut pas, et s'utilise partout.

Le défaut d'origine : le journal visait la racine du CODE, qui appartient à root sur une instance
verrouillée. Chaque écriture échouait, l'échec était compté et jamais dit, et le panneau « journal » du
cockpit ne montrait que le navigateur. Personne ne l'a su pendant des semaines.
"""
import importlib
import os
import pathlib
import stat
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core            # noqa: E402  RM3119 : un test se donne
hermetic_core()                                   # sa config, il ne compte pas sur celle du dépôt
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def frais(**env):
    """Recharge pm_log avec un environnement neuf : l'emplacement est choisi à la configuration."""
    for k in ("KARL_JOURNAL_DIR", "XDG_STATE_HOME", "KARL_JOURNAL_LEVEL", "KARL_JOURNAL_STDERR", "PM_LOG_DIR"):
        os.environ.pop(k, None)
    os.environ.update({k: str(v) for k, v in env.items() if v is not None})
    if "pm_log" in sys.modules:
        del sys.modules["pm_log"]
    return importlib.import_module("pm_log")


print("[RM3095] où le journal écrit")
with tempfile.TemporaryDirectory() as tmp:
    d = pathlib.Path(tmp) / "impose"
    L = frais(KARL_JOURNAL_DIR=d, KARL_JOURNAL_STDERR="0")
    L.log("system", "info", "essai")
    check("un dossier imposé est respecté", (d / L.FILE_NAME).is_file())
    check("et la santé le dit", L.stats()["healthy"] and L.stats()["errors"] == 0)

with tempfile.TemporaryDirectory() as tmp:
    # la cascade a trois niveaux : imposé → racine déclarée de la conf → état de l'utilisateur.
    interdit = pathlib.Path(tmp) / "interdit"
    interdit.mkdir(); interdit.chmod(stat.S_IRUSR | stat.S_IXUSR)      # lecture seule
    declare = pathlib.Path(tmp) / "declare"
    L = frais(KARL_JOURNAL_DIR=interdit, PM_LOG_DIR=declare, KARL_JOURNAL_STDERR="0")
    chemin = L.journal_path()
    check("un emplacement non inscriptible est ÉCARTÉ, pas subi", str(interdit) not in str(chemin), str(chemin))
    check("on tombe sur la racine DÉCLARÉE de la conf", str(declare) in str(chemin), str(chemin))
    check("et ce qui a été refusé est nommé", any(str(interdit) in r for r in L.stats()["refused"]))
    L.log("system", "info", "après repli")
    check("le journal écrit vraiment après le repli", L.stats()["written"] == 1 and L.stats()["errors"] == 0)

    # dernier niveau : même la racine déclarée refuse → l'état de l'utilisateur, qui marche toujours
    declare2 = pathlib.Path(tmp) / "declare2"
    declare2.mkdir(); declare2.chmod(stat.S_IRUSR | stat.S_IXUSR)
    xdg = pathlib.Path(tmp) / "xdg"
    L = frais(KARL_JOURNAL_DIR=interdit, PM_LOG_DIR=declare2, XDG_STATE_HOME=xdg, KARL_JOURNAL_STDERR="0")
    check("tout refusé sauf l'état de l'utilisateur : c'est là qu'on écrit",
          str(xdg) in str(L.journal_path()), str(L.journal_path()))
    L.log("system", "info", "dernier repli")
    check("et ça écrit pour de vrai", L.stats()["written"] == 1 and L.stats()["errors"] == 0)
    declare2.chmod(stat.S_IRWXU); interdit.chmod(stat.S_IRWXU)

print("\n[RM3095] la racine du code n'est plus une cible")
src = (HERE / "pm_log.py").read_text(encoding="utf-8")
check("le défaut historique <repo>/logs a disparu du code", '_repo_root() / "logs"' not in src)
check("la racine déclarée de la conf est consultée", "log_dir" in src and "PMConfig" in src)

print("\n[RM3095] un journal muet le DIT")
with tempfile.TemporaryDirectory() as tmp:
    L = frais(KARL_JOURNAL_DIR=pathlib.Path(tmp) / "ok", KARL_JOURNAL_STDERR="0")
    L.log("system", "info", "une")
    L._STATE["dir"] = pathlib.Path("/proc/inexistant/interdit")        # casse APRÈS configuration
    import io
    err = io.StringIO(); vrai, sys.stderr = sys.stderr, err
    L.log("system", "info", "deux"); L.log("system", "info", "trois")
    sys.stderr = vrai
    check("l'échec d'écriture est compté", L.stats()["errors"] == 2)
    check("la santé bascule", not L.stats()["healthy"])
    check("il est signalé sur la sortie d'erreur", "INACCESSIBLE" in err.getvalue(), err.getvalue()[:120])
    check("mais une seule fois, pas à chaque ligne", err.getvalue().count("INACCESSIBLE") == 1)

print("\n[RM3095] l'objet de journal, pour l'utiliser partout")
with tempfile.TemporaryDirectory() as tmp:
    L = frais(KARL_JOURNAL_DIR=pathlib.Path(tmp) / "j", KARL_JOURNAL_STDERR="0")
    j = L.journal("mon-script", "pm", rm=42)
    j.info("une action", cible="x")
    rec = L.tail(limit=1)[0]
    check("la source et le contexte suivent chaque entrée",
          rec["tool"] == "mon-script" and rec["rm"] == 42 and rec["cible"] == "x")
    j.info("avec un champ métier nommé src", src="une-branche")
    check("un champ métier « src » ne heurte plus la source de l'entrée",
          L.tail(limit=1)[0]["src"] == "une-branche" and L.tail(limit=1)[0]["tool"] == "mon-script")
    k = j.bind(sid="s1")
    k.warn("un souci")
    check("bind ajoute du contexte sans toucher à l'original",
          L.tail(limit=1)[0]["sid"] == "s1" and "sid" not in (j.ctx or {}))
    try:
        with j.step("une étape", cible="y"):
            raise ValueError("boum")
    except ValueError:
        pass
    else:
        check("step relance l'exception : le journal observe, il n'arbitre pas", False)
    rec = L.tail(limit=1)[0]
    check("une étape qui casse est journalisée en erreur, avec sa durée",
          rec["level"] == "error" and "ms" in rec and rec["cible"] == "y")
    check("et avec un traceback court, pour retrouver le site",
          "ValueError: boum" in rec.get("exc", "") and "@" in rec.get("exc", ""))
    with j.step("une étape qui passe"):
        pass
    check("une étape qui passe est journalisée en info", L.tail(limit=1)[0]["level"] == "info")
    j.error("échec net", exc=RuntimeError("x"))
    check("error accepte une exception sans contexte de bloc", "RuntimeError" in L.tail(limit=1)[0].get("exc", ""))

print("\n[RM3095] les scripts qui changent un état journalisent")
attendu = {"pm-mr.py": "MR créée", "pm-task-status-update.py": "statut changé",
           "pm-branch-start.py": "branche de ticket créée", "pm-task-add.py": "ticket créé",
           "pm-scheduler.py": "travail périodique"}
for f, msg in attendu.items():
    src = (HERE / f).read_text(encoding="utf-8")
    check(f"{f} journalise son geste", "pm_log.journal(" in src and msg in src)
    check(f"{f} survit à l'absence de pm_log", "except ImportError" in src and "journal = None" in src)
ka = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("la santé du journal est exposée par /health", '"journal": jsante' in ka)

# Un appel de journal vit sur un chemin RAREMENT emprunté (l'échec, le cas limite) : une variable qui
# n'existe pas à cet endroit ne se voit qu'au pire moment. C'est arrivé (`rm_id` pour `args.rm_id` dans
# pm-task-status-update, découvert en changeant un statut). Ce contrôle statique l'attrape à froid.
import ast                                               # noqa: E402


def _noms_visibles(tree, lineno):
    glob = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    glob |= {t.id for n in tree.body if isinstance(n, ast.Assign) for t in ast.walk(n) if isinstance(t, ast.Name)}
    glob |= {a.asname or a.name.split(".")[0] for n in ast.walk(tree)
             if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    # RM3119 : `except X as e` lie `e` par un CHAMP de l'ExceptHandler, pas par un ast.Name en Store —
    # l'oublier faisait crier au nom inexistant sur `journal.warn(..., err=str(e))`, le motif le plus
    # courant qui soit. Un contrôle statique qui se trompe finit par être ignoré.
    glob |= {h.name for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler) and h.name}
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        fin = max((getattr(x, "lineno", fn.lineno) for x in ast.walk(fn)), default=fn.lineno)
        if fn.lineno <= lineno <= fin:
            loc = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
            loc |= {t.id for x in ast.walk(fn) for t in ast.walk(x)
                    if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store)}
            loc |= {h.name for h in ast.walk(fn) if isinstance(h, ast.ExceptHandler) and h.name}
            return glob | loc
    return glob


mauvais = []
for f in sorted(HERE.glob("pm-*.py")):
    try:
        arbre = ast.parse(f.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    for n in ast.walk(arbre):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id in ("journal", "pm_notify")):
            continue
        vis = _noms_visibles(arbre, n.lineno) | set(__builtins__.__dict__)
        used = {x.id for k in n.keywords if k.value is not None for x in ast.walk(k.value) if isinstance(x, ast.Name)}
        used |= {x.id for a in n.args for x in ast.walk(a) if isinstance(x, ast.Name)}
        absents = sorted(u for u in used if u not in vis)
        if absents:
            mauvais.append(f"{f.name}:{n.lineno} → {', '.join(absents)}")
check("aucun appel de journal n'utilise un nom qui n'existe pas là où il est écrit",
      not mauvais, " · ".join(mauvais[:4]))

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm_log (RM3095)"))
sys.exit(1 if FAIL else 0)
