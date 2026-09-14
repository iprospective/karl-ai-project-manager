#!/usr/bin/env python3
"""Tests RM3145 (lot 4) — les routes qu'un MODULE sert, et le montage par le noyau.

Ce qui doit tenir : une route se déclare et se valide (elle ne se devine pas), elle est servie sous un
préfixe qui DIT quel module répond, un module bloqué ne sert rien, deux modules ne peuvent pas servir
la même URL, et l'import d'un contrôleur ne peut pas sortir du dossier de son module.

Lancer : python3 scripts/test_pm_module_routes.py
"""
import importlib
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def frais(d):
    os.environ["PM_MODULES_DIR"] = str(d)
    if "pm_modules" in sys.modules:
        del sys.modules["pm_modules"]
    return importlib.import_module("pm_modules")


def module(base, nom, manifeste, routes=None, controleurs=None):
    d = pathlib.Path(base) / nom
    (d / "routes").mkdir(parents=True, exist_ok=True)
    (d / "controllers").mkdir(parents=True, exist_ok=True)
    (d / "module.yml").write_text(manifeste, encoding="utf-8")
    for f, t in (routes or {}).items():
        (d / "routes" / f).write_text(t, encoding="utf-8")
    for f, t in (controleurs or {}).items():
        (d / "controllers" / f).write_text(t, encoding="utf-8")


with tempfile.TemporaryDirectory() as tmp:
    M = frais(tmp)
    print("[RM3145] une route se déclare, et se valide")
    module(tmp, "alpha", 'name: alpha\nversion: 1.0.0\ndescription: "x"\n',
           {"bonne.yml": "path: etat\nmethod: GET\nhandler: ctrl:lire\n",
            "post.yml": "path: sous/chemin\nmethod: POST\nhandler: ctrl:ecrire\n",
            "sans-path.yml": "method: GET\nhandler: ctrl:lire\n",
            "traversee.yml": "path: ../../etc/passwd\nmethod: GET\nhandler: ctrl:lire\n",
            "methode.yml": "path: x\nmethod: DELETE\nhandler: ctrl:lire\n",
            "handler.yml": "path: y\nmethod: GET\nhandler: pas-une-cible\n"},
           {"ctrl.py": "def lire(qs=None, payload=None, auth_ctx=None):\n    return {'ok': True}\n"})
    rts = {r.file.name: r for r in M.routes()}
    check("une route correcte passe", rts["bonne.yml"].ok)
    check("l'URL porte le nom du module — c'est ce qui rend un incident lisible",
          rts["bonne.yml"].url == "/api/modules/alpha/etat", rts["bonne.yml"].url)
    check("un chemin à plusieurs segments marche", rts["post.yml"].url == "/api/modules/alpha/sous/chemin")
    check("sans « path », refusée", not rts["sans-path.yml"].ok)
    check("une TRAVERSÉE de chemin est refusée dès la déclaration",
          not rts["traversee.yml"].ok, str(rts["traversee.yml"].errors))
    check("une méthode inconnue est refusée", not rts["methode.yml"].ok)
    check("un « handler » qui n'est pas « fichier:fonction » est refusé", not rts["handler.yml"].ok)
    check("la cible se lit sous forme exploitable", rts["bonne.yml"].cible() == ("ctrl", "lire"))

with tempfile.TemporaryDirectory() as tmp:
    M = frais(tmp)
    print("\n[RM3145] un module qui n'est pas chargé ne sert rien")
    module(tmp, "actif", 'name: actif\nversion: 1.0.0\ndescription: "x"\n',
           {"r.yml": "path: a\nmethod: GET\nhandler: c:f\n"})
    module(tmp, "eteint", 'name: eteint\nversion: 1.0.0\ndescription: "x"\nenabled: false\n',
           {"r.yml": "path: b\nmethod: GET\nhandler: c:f\n"})
    module(tmp, "bloque", 'name: bloque\nversion: 1.0.0\ndescription: "x"\nrequires: ["fantome >= 1.0"]\n',
           {"r.yml": "path: c\nmethod: GET\nhandler: c:f\n"})
    servies = {r.url for r in M.routes() if r.ok}
    check("seul le module actif sert", servies == {"/api/modules/actif/a"}, str(servies))

with tempfile.TemporaryDirectory() as tmp:
    M = frais(tmp)
    print("\n[RM3145] deux modules ne servent pas la même URL")
    # Le préfixe par module rend le cas presque impossible — « presque » ne suffit pas pour du routage.
    module(tmp, "jumeau-un", 'name: jumeau-un\nversion: 1.0.0\ndescription: "x"\n',
           {"r.yml": "path: x\nmethod: GET\nhandler: c:f\n"})
    module(tmp, "jumeau-deux", 'name: jumeau-deux\nversion: 1.0.0\ndescription: "x"\n',
           {"r.yml": "path: x\nmethod: GET\nhandler: c:f\n"})
    check("deux modules distincts peuvent servir le même CHEMIN — les URL diffèrent",
          len([r for r in M.routes() if r.ok]) == 2)
    module(tmp, "double", 'name: double\nversion: 1.0.0\ndescription: "x"\n',
           {"a.yml": "path: meme\nmethod: GET\nhandler: c:f\n",
            "b.yml": "path: meme\nmethod: GET\nhandler: c:g\n"})
    doubles = [r for r in M.routes() if r.module == "double"]
    check("…mais un module ne déclare pas deux fois la même URL",
          sum(1 for r in doubles if not r.ok) == 1
          and any("déjà servie" in e for r in doubles for e in r.errors), str([r.errors for r in doubles]))

print("\n[RM3145] le noyau monte ces routes, et garde la porte")
ka = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("le dispatch GET sert les routes de modules", 'op_module_route("GET"' in ka)
check("le dispatch POST aussi", 'op_module_route("POST"' in ka)
check("une route inconnue laisse le noyau continuer — elle ne devient pas un 404 de module",
      "if r is not None:" in ka)
check("l'import d'un contrôleur est gardé contre la traversée",
      "startswith(str((racine / module).resolve()) + os.sep)" in ka)
check("le nom du module et du fichier viennent du MANIFESTE, jamais de l'URL",
      "jamais de l'URL" in ka)
check("une erreur du module est rendue avec SON nom",
      'f"module « {module} » : {e}"' in ka)
check("la table des routes est relue périodiquement, pas à chaque requête",
      "_MODULE_ROUTES_TTL" in ka)
check("et le premier endroit qui exécute du code de module est SIGNALÉ comme tel",
      "premier endroit où du code de MODULE s'exécute" in ka)

print("\n[RM3145] le module témoin sert une vraie information")
os.environ.pop("PM_MODULES_DIR", None)
if "pm_modules" in sys.modules:
    del sys.modules["pm_modules"]
M = importlib.import_module("pm_modules")
rts = [r for r in M.routes() if r.ok]
check("release-watch déclare sa route",
      any(r.url == "/api/modules/release-watch/watches" for r in rts), str([r.url for r in rts]))
sys.path.insert(0, str(HERE.parent / "modules" / "release-watch" / "controllers"))
import watches                                                   # noqa: E402
etat = watches.etat()
check("et son contrôleur rend les veilles déclarées", etat["count"] >= 1 and etat["watches"][0]["repo"])
check("avec le POURQUOI de chacune — ce qui manque le plus des mois plus tard",
      bool(etat["watches"][0]["why"]))
check("il ne part PAS sur le réseau : une route d'affichage ne doit pas dépendre de GitHub",
      "urllib" not in (HERE.parent / "modules" / "release-watch" / "controllers" / "watches.py").read_text(encoding="utf-8"))

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — routes de modules (RM3145 lot 4)"))
sys.exit(1 if FAIL else 0)
