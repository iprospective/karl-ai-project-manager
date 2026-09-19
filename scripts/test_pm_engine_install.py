#!/usr/bin/env python3
"""Tests RM3069 — moteurs et serveurs : le catalogue est la SEULE source des commandes, aucune ne vient du
client, la mise à jour est refusée sous des sessions vives, --dry-run n'exécute rien. Deux PORTÉES : un outil
posé par un utilisateur (hors du PATH du démon) est trouvé et reconnu comme tel, pas déclaré absent."""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_engine_recipes as R                        # noqa: E402
spec = importlib.util.spec_from_file_location("ei", HERE / "pm-engine-install.py")
E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


print("[RM3069] catalogue : deux familles")
cat = R.catalogue()
check("les clients de session sont des « engine »", {e["id"] for e in cat["engines"]} == {"claude", "opencode", "vibe"})
check("les serveurs de modèles sont des « server », rattachés à un type de fournisseur",
      {s["id"] for s in cat["servers"]} == {"ollama", "lemonade"} and all(s["provider_type"] for s in cat["servers"]))
check("chaque outil annonce les portées où il s'installe",
      all(x["scopes"] and set(x["scopes"]) <= set(R.PORTEES) for x in cat["engines"] + cat["servers"]))
check("les moteurs de session s'installent dans les DEUX portées",
      all(set(e["scopes"]) == {"user", "system"} for e in cat["engines"]))
check("un service système ne s'installe que pour tous",
      [s["scopes"] for s in cat["servers"] if s["id"] == "ollama"] == [["system"]])
check("la portée « pour tous » passe par sudo, « pour moi » jamais",
      all(c["cmds"]["system"]["install"].startswith("sudo -n ") for c in cat["engines"])
      and all("sudo" not in c["cmds"]["user"]["install"] for c in cat["engines"]))
check("la commande est rendue pour AFFICHAGE, avant d'agir", bool(cat["engines"][0]["cmds"]["user"]["install"]))

print("\n[RM3069] les commandes ne viennent JAMAIS du client")
check("une recette inconnue est refusée", not R.recette("rm -rf /"))
for mauvais in ("rm -rf /", "claude; curl evil.sh", ""):
    try:
        R.commande(mauvais, "install"); check(f"refus « {mauvais[:20]} »", False)
    except (KeyError, ValueError):
        check(f"refus « {mauvais[:20]} »", True)
try:
    R.commande("claude", "boum"); check("action inconnue refusée", False)
except ValueError:
    check("action inconnue refusée", True)
check("la commande est une LISTE, jamais une chaîne pour le shell", isinstance(R.commande("claude", "install"), list))
try:
    R.commande("claude", "install", "root"); check("portée inventée refusée", False)
except ValueError:
    check("portée inventée refusée", True)
try:
    R.commande("ollama", "install", "user"); check("portée non offerte refusée, en le disant", False)
except ValueError as e:
    check("portée non offerte refusée, en le disant", "system" in str(e))
src = (HERE / "pm-engine-install.py").read_text()
check("aucun shell=True dans l'exécutant", "shell=True" not in src)

print("\n[RM3069] versions")
check("version lue dans une sortie bavarde", R.version_de("claude 2.1.267 (Claude Code)", "claude") == "2.1.267")
check("sortie sans version → vide", R.version_de("commande introuvable", "claude") == "")

print("\n[RM3069] garde des sessions vives et --dry-run")
vraies = E.sessions_du_moteur
E.sessions_du_moteur = lambda nom: ["karl-RM1", "karl-RM2"] if nom == "claude" else []
r = E.execute("claude", "update")
check("mise à jour refusée sous des sessions vives, avec leur nom", r["ok"] is False and r["blocked"] == ["karl-RM1", "karl-RM2"] and "force" in r["error"])
r = E.execute("claude", "update", dry=True, force=True, portee="system")
check("--dry-run rend la commande exacte sans rien exécuter",
      r["ok"] and r["dry_run"] and r["cmd"].startswith("sudo -n npm update") and r["scope"] == "system")
r = E.execute("claude", "update", dry=True, force=True, portee="user")
check("la même action « pour moi » ne demande aucun privilège", r["ok"] and "sudo" not in r["cmd"])
r = E.execute("opencode", "install", dry=True)
check("une installation n'est pas gardée par les sessions (rien à casser)", r["ok"] and r["dry_run"])
check("la portée par défaut est la moins privilégiée", r["scope"] == "user")
E.sessions_du_moteur = vraies

print("\n[RM3069] détection : un outil posé par un utilisateur n'est pas « absent »")
with tempfile.TemporaryDirectory() as tmp:
    faux = pathlib.Path(tmp) / "home" / ".opencode" / "bin"
    faux.mkdir(parents=True)
    (faux / "opencode").write_text("#!/bin/sh\necho 9.9.9\n"); (faux / "opencode").chmod(0o755)
    os.environ["PM_TARGET_HOME"] = str(pathlib.Path(tmp) / "home")
    chemin_reel = E.trouve("opencode")
    hors_path = str(faux / "opencode")
    check("trouvé hors du PATH, dans l'emplacement usuel de l'outil",
          bool(chemin_reel) and (chemin_reel == hors_path or "opencode" in chemin_reel), chemin_reel)
    check("un binaire sous un home est de portée « utilisateur »", E.portee_du_chemin(hors_path)[0] == "user")
    check("un binaire hors des homes est de portée « système »", E.portee_du_chemin("/usr/local/bin/opencode")[0] == "system")
    check("un outil vraiment absent reste absent", E.trouve("recette-qui-nexiste-pas") == "")
    os.environ.pop("PM_TARGET_HOME", None)

print("\n[RM3069] état réel de la machine")
st = {d["id"]: d for d in E.etats()}
check("les cinq recettes sont rapportées", set(st) == set(R.RECETTES))
check("un outil présent porte son chemin, sa version et sa portée",
      (not st["claude"]["installed"]) or (st["claude"]["path"] and st["claude"]["version"] and st["claude"]["scope"] in R.PORTEES))
check("un outil absent n'annonce aucune portée d'installation",
      all(d["scope"] == "" for d in st.values() if not d["installed"] and not d["installed_elsewhere"]))
check("chaque état dit dans quelles portées il PEUT s'installer", all(d["scopes"] for d in st.values()))
check("un outil absent est dit absent, sans version", all(d["version"] == "" for d in st.values() if not d["installed"]))
r = subprocess.run([sys.executable, str(HERE / "pm-engine-install.py"), "--recipe", "claude", "--action", "install", "--dry-run", "--json"],
                   capture_output=True, text=True)
check("le CLI en JSON n'exécute rien avec --dry-run", r.returncode == 0 and '"dry_run": true' in r.stdout, r.stdout[-200:])

# ── RM3097 : « pour moi », c'est le home du DÉVELOPPEUR CONNECTÉ, pas celui du démon ──
print("\n[RM3097] installé pour qui ?")
import pwd as _pwd   # noqa: E402
moi = _pwd.getpwuid(os.getuid()).pw_name
autre = next((u.pw_name for u in _pwd.getpwall()
              if 1000 <= u.pw_uid < 65534 and u.pw_name != moi and os.path.isdir(u.pw_dir)), None)
check("home_de() sans argument = le nôtre", E.home_de() == os.path.expanduser("~"))
check("home_de(<login>) = le sien", (not autre) or E.home_de(autre) == _pwd.getpwnam(autre).pw_dir)
sous_moi = os.path.join(os.path.expanduser("~"), ".local", "bin", "truc")
check("un binaire de MON home, vu pour moi : portée utilisateur", E.portee_du_chemin(sous_moi)[0] == "user")
if autre:
    p, proprio = E.portee_du_chemin(sous_moi, autre)
    check("…le même binaire, vu pour un AUTRE développeur : « other », avec mon login",
          p == "other" and proprio == moi, f"{p}/{proprio}")
    st2 = {d["id"]: d for d in E.etats(autre)}
    check("…et l'état le dit : pas « installed » pour lui",
          all(not d["installed"] for d in st2.values() if d.get("installed_elsewhere")), str([d for d in st2.values() if d.get("installed_elsewhere")][:1]))
    r = E.execute("claude", "install", dry=True, portee="user", cible=autre)
    check("installer « pour moi » dans le home d'un autre : refusé, avec la commande à lancer en tant que lui",
          r["ok"] is False and autre in r["error"] and "--scope user" in r["error"], str(r)[:200])
else:
    print("· ignoré (aucun autre utilisateur réel sur cette machine) — les gardes « other » tournent ailleurs")
r = E.execute("claude", "install", dry=True, portee="user", cible=moi)
check("pour moi-même : rien ne change, la simulation passe", r["ok"] is True and r.get("dry_run"), str(r)[:160])
check("…et la réponse dit pour QUI elle vaut", r.get("for_user") == moi or "for_user" in r, str(r)[:120])

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm-engine-install"))
sys.exit(1 if FAIL else 0)
