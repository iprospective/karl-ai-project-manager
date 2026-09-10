#!/usr/bin/env python3
"""pm_engine_recipes — le CATALOGUE des moteurs et des serveurs de modèles installables (RM3069).

Deux familles, et la distinction n'est pas cosmétique (arbitrage Mathieu, 2026-09-10) :

  · `engine` — un CLIENT qui tient une session d'agent : claude, opencode, mistral vibe. Le PM les
    connaît déjà à l'exécution (`karl-agent :: ENGINES`) ; ici on sait en plus les installer.
  · `server` — un SERVEUR de modèles : ollama, lemonade. Il ne tient aucune session : il alimente
    l'axe `llm` du registre des fournisseurs (RM3067), qu'un client ou un script appelle ensuite.

Une recette dit cinq choses, toutes **connues à l'avance** : détecter, lire la version installée, lire la
version disponible, installer, mettre à jour. Le cockpit n'envoie jamais qu'un IDENTIFIANT de recette —
aucune commande ne vient du client (garde-fou 10). L'installation est SYSTÈME, donc `sudo` : les moteurs
servent tous les utilisateurs de la machine, et c'est ce qui justifie le privilège.
"""
import re

#: chaque commande est une LISTE (jamais une chaîne passée au shell). Deux PORTÉES, au choix (RM3069) :
#:   `user`   — dans l'espace du développeur (aucun privilège) : c'est ainsi qu'opencode arrive dans
#:              ~/.opencode/bin, et que `npm -g` écrit dans le préfixe personnel ;
#:   `system` — pour tous les utilisateurs de la machine, donc `sudo`, et c'est ce qui le justifie.
#: Un outil peut donc être présent pour un seul utilisateur : la détection le dit, elle ne l'ignore pas.
RECETTES = {
    "claude": {
        "kind": "engine", "label": "Claude Code", "bin": "claude",
        "version": ["claude", "--version"], "version_re": r"(\d+\.\d+\.\d+)",
        "latest": ["npm", "view", "@anthropic-ai/claude-code", "version"],
        "install": {"user": ["npm", "install", "-g", "@anthropic-ai/claude-code"],
                    "system": ["sudo", "-n", "npm", "install", "-g", "--prefix", "/usr/local", "@anthropic-ai/claude-code"]},
        "update": {"user": ["npm", "update", "-g", "@anthropic-ai/claude-code"],
                   "system": ["sudo", "-n", "npm", "update", "-g", "--prefix", "/usr/local", "@anthropic-ai/claude-code"]},
        "config": "compte Claude (`claude` puis /login) ou ANTHROPIC_API_KEY",
        "note": "moteur par défaut des sessions PM",
    },
    "opencode": {
        "kind": "engine", "label": "opencode", "bin": "opencode",
        "version": ["opencode", "--version"], "version_re": r"(\d+\.\d+\.\d+)",
        "latest": ["npm", "view", "opencode-ai", "version"],
        "install": {"user": ["sh", "-c", "curl -fsSL https://opencode.ai/install | bash"],
                    "system": ["sudo", "-n", "npm", "install", "-g", "--prefix", "/usr/local", "opencode-ai"]},
        "update": {"user": ["sh", "-c", "curl -fsSL https://opencode.ai/install | bash"],
                   "system": ["sudo", "-n", "npm", "update", "-g", "--prefix", "/usr/local", "opencode-ai"]},
        "extra_paths": ["~/.opencode/bin"],
        "config": "fournisseur et modèle dans ~/.config/opencode/opencode.jsonc",
    },
    "vibe": {
        "kind": "engine", "label": "Mistral vibe", "bin": "vibe",
        "version": ["vibe", "--version"], "version_re": r"(\d+\.\d+\.\d+)",
        "latest": ["npm", "view", "@mistralai/vibe", "version"],
        "install": {"user": ["npm", "install", "-g", "@mistralai/vibe"],
                    "system": ["sudo", "-n", "npm", "install", "-g", "--prefix", "/usr/local", "@mistralai/vibe"]},
        "update": {"user": ["npm", "update", "-g", "@mistralai/vibe"],
                   "system": ["sudo", "-n", "npm", "update", "-g", "--prefix", "/usr/local", "@mistralai/vibe"]},
        "config": "MISTRAL_API_KEY",
    },
    "ollama": {
        "kind": "server", "label": "Ollama (serveur de modèles)", "bin": "ollama",
        "version": ["ollama", "--version"], "version_re": r"(\d+\.\d+\.\d+)",
        "latest": None,
        "install": {"system": ["sudo", "-n", "sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"]},
        "update": {"system": ["sudo", "-n", "sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"]},
        "service": ["systemctl", "is-active", "ollama"],
        "provider_type": "ollama",
        "note": "sert les modèles ; se déclare ensuite comme fournisseur de l'axe « llm ». Un service système : pas d'installation par utilisateur.",
    },
    "lemonade": {
        "kind": "server", "label": "Lemonade Server (Ryzen AI)", "bin": "lemonade-server",
        "version": ["lemonade-server", "--version"], "version_re": r"(\d+\.\d+\.\d+)",
        "latest": ["pip", "index", "versions", "lemonade-sdk"],
        "install": {"user": ["pip", "install", "--user", "lemonade-sdk[dev]"],
                    "system": ["sudo", "-n", "pip", "install", "--break-system-packages", "lemonade-sdk[dev]"]},
        "update": {"user": ["pip", "install", "--user", "-U", "lemonade-sdk[dev]"],
                   "system": ["sudo", "-n", "pip", "install", "--break-system-packages", "-U", "lemonade-sdk[dev]"]},
        "extra_paths": ["~/.local/bin"],
        "provider_type": "lemonade",
        "note": "API compatible OpenAI, accélérée sur Ryzen AI ; se déclare ensuite à l'axe « llm »",
    },
}

PORTEES = ("user", "system")
#: où chercher un binaire au-delà du PATH du démon : un outil posé par un utilisateur n'y est pas
CHEMINS = ["~/.local/bin", "~/.opencode/bin", "~/.bun/bin", "~/.npm-global/bin", "~/bin",
           "/usr/local/bin", "/usr/bin", "/opt/homebrew/bin"]

ACTIONS = ("install", "update", "test")


def catalogue() -> dict:
    """Les recettes en JSON, familles séparées, **une entrée par portée disponible**. Les commandes sont
    rendues pour AFFICHAGE : le panneau les montre avant d'agir, il ne les renvoie jamais au serveur."""
    def vue(nom, r):
        return {"id": nom, "kind": r["kind"], "label": r["label"], "bin": r["bin"],
                "scopes": [s for s in PORTEES if s in r["install"]],
                "config": r.get("config", ""), "note": r.get("note", ""), "provider_type": r.get("provider_type", ""),
                "cmds": {s: {"install": " ".join(r["install"][s]), "update": " ".join(r.get("update", {}).get(s, []))}
                         for s in PORTEES if s in r["install"]}}
    return {"engines": [vue(n, r) for n, r in sorted(RECETTES.items()) if r["kind"] == "engine"],
            "servers": [vue(n, r) for n, r in sorted(RECETTES.items()) if r["kind"] == "server"]}


def recette(nom: str) -> dict:
    return RECETTES.get(str(nom or "").strip(), {})


def commande(nom: str, action: str, portee: str = "user") -> list:
    """La commande d'une recette, pour une action et une PORTÉE — la seule façon d'obtenir une commande.
    Le client n'en propose jamais : il nomme une recette, une action et une portée, connues d'ici."""
    r = recette(nom)
    if not r:
        raise KeyError(f"recette inconnue : {nom}")
    if action not in ACTIONS:
        raise ValueError(f"action inconnue : {action}")
    if action == "test":
        return list(r["version"])
    if portee not in PORTEES:
        raise ValueError(f"portée inconnue : {portee}")
    cmd = (r.get(action) or {}).get(portee)
    if not cmd:
        dispo = ", ".join(s for s in PORTEES if s in r.get(action, {}))
        raise ValueError(f"{nom} : pas de recette « {action} » en portée « {portee} »"
                         + (f" (disponible : {dispo})" if dispo else ""))
    return list(cmd)


def demande_sudo(nom: str, action: str, portee: str) -> bool:
    try:
        return "sudo" in commande(nom, action, portee)[:1]
    except (KeyError, ValueError):
        return False


def version_de(sortie: str, nom: str) -> str:
    """La version lue dans la sortie d'une commande, ou "" — pur, testé."""
    m = re.search(recette(nom).get("version_re") or r"(\d+\.\d+\.\d+)", str(sortie or ""))
    return m.group(1) if m else ""
