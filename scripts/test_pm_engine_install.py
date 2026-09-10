#!/usr/bin/env python3
"""Tests RM3069 — moteurs et serveurs : le catalogue est la SEULE source des commandes, aucune ne vient du
client, la mise à jour est refusée sous des sessions vives, et --dry-run n'exécute rien."""
import importlib.util
import pathlib
import subprocess
import sys

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
check("toute installation est signalée comme système (sudo)", all(x["sudo"] for x in cat["engines"] + cat["servers"]))
check("la commande est rendue pour AFFICHAGE, avant d'agir", cat["engines"][0]["install_cmd"].startswith("sudo -n "))

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
r = E.execute("claude", "update", dry=True, force=True)
check("--dry-run rend la commande exacte sans rien exécuter", r["ok"] and r["dry_run"] and r["cmd"] == "sudo -n npm update -g @anthropic-ai/claude-code")
r = E.execute("opencode", "install", dry=True)
check("une installation n'est pas gardée par les sessions (rien à casser)", r["ok"] and r["dry_run"])
E.sessions_du_moteur = vraies

print("\n[RM3069] état réel de la machine")
st = {d["id"]: d for d in E.etats()}
check("les cinq recettes sont rapportées", set(st) == set(R.RECETTES))
check("un outil présent porte son chemin et sa version", (not st["claude"]["installed"]) or (st["claude"]["path"] and st["claude"]["version"]))
check("un outil absent est dit absent, sans version", all(d["version"] == "" for d in st.values() if not d["installed"]))
r = subprocess.run([sys.executable, str(HERE / "pm-engine-install.py"), "--recipe", "claude", "--action", "install", "--dry-run", "--json"],
                   capture_output=True, text=True)
check("le CLI en JSON n'exécute rien avec --dry-run", r.returncode == 0 and '"dry_run": true' in r.stdout, r.stdout[-200:])

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm-engine-install"))
sys.exit(1 if FAIL else 0)
