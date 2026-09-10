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

#: chaque commande est une LISTE (jamais une chaîne passée au shell) ; `sudo` est explicite et signalé.
RECETTES = {
    "claude": {
        "kind": "engine", "label": "Claude Code", "bin": "claude",
        "version": ["claude", "--version"], "version_re": r"(\d+\.\d+\.\d+)",
        "latest": ["npm", "view", "@anthropic-ai/claude-code", "version"],
        "install": ["sudo", "-n", "npm", "install", "-g", "@anthropic-ai/claude-code"],
        "update": ["sudo", "-n", "npm", "update", "-g", "@anthropic-ai/claude-code"],
        "sudo": True, "config": "compte Claude (`claude` puis /login) ou ANTHROPIC_API_KEY",
        "note": "moteur par défaut des sessions PM",
    },
    "opencode": {
        "kind": "engine", "label": "opencode", "bin": "opencode",
        "version": ["opencode", "--version"], "version_re": r"(\d+\.\d+\.\d+)",
        "latest": ["npm", "view", "opencode-ai", "version"],
        "install": ["sudo", "-n", "npm", "install", "-g", "opencode-ai"],
        "update": ["sudo", "-n", "npm", "update", "-g", "opencode-ai"],
        "sudo": True, "config": "fournisseur et modèle dans ~/.config/opencode",
    },
    "vibe": {
        "kind": "engine", "label": "Mistral vibe", "bin": "vibe",
        "version": ["vibe", "--version"], "version_re": r"(\d+\.\d+\.\d+)",
        "latest": ["npm", "view", "@mistralai/vibe", "version"],
        "install": ["sudo", "-n", "npm", "install", "-g", "@mistralai/vibe"],
        "update": ["sudo", "-n", "npm", "update", "-g", "@mistralai/vibe"],
        "sudo": True, "config": "MISTRAL_API_KEY",
    },
    "ollama": {
        "kind": "server", "label": "Ollama (serveur de modèles)", "bin": "ollama",
        "version": ["ollama", "--version"], "version_re": r"(\d+\.\d+\.\d+)",
        "latest": None,
        "install": ["sudo", "-n", "sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
        "update": ["sudo", "-n", "sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
        "service": ["systemctl", "is-active", "ollama"],
        "sudo": True, "provider_type": "ollama",
        "note": "sert les modèles ; se déclare ensuite comme fournisseur de l'axe « llm »",
    },
    "lemonade": {
        "kind": "server", "label": "Lemonade Server (Ryzen AI)", "bin": "lemonade-server",
        "version": ["lemonade-server", "--version"], "version_re": r"(\d+\.\d+\.\d+)",
        "latest": ["pip", "index", "versions", "lemonade-sdk"],
        "install": ["sudo", "-n", "pip", "install", "--break-system-packages", "lemonade-sdk[dev]"],
        "update": ["sudo", "-n", "pip", "install", "--break-system-packages", "-U", "lemonade-sdk[dev]"],
        "sudo": True, "provider_type": "lemonade",
        "note": "API compatible OpenAI, accélérée sur Ryzen AI ; se déclare ensuite à l'axe « llm »",
    },
}

ACTIONS = ("install", "update", "test")


def catalogue() -> dict:
    """Les recettes en JSON, familles séparées. Les commandes sont rendues **pour affichage** :
    c'est ce que le panneau montre avant d'agir ; il ne les renvoie jamais au serveur."""
    def vue(nom, r):
        return {"id": nom, "kind": r["kind"], "label": r["label"], "bin": r["bin"], "sudo": bool(r.get("sudo")),
                "config": r.get("config", ""), "note": r.get("note", ""), "provider_type": r.get("provider_type", ""),
                "install_cmd": " ".join(r["install"]), "update_cmd": " ".join(r["update"])}
    return {"engines": [vue(n, r) for n, r in sorted(RECETTES.items()) if r["kind"] == "engine"],
            "servers": [vue(n, r) for n, r in sorted(RECETTES.items()) if r["kind"] == "server"]}


def recette(nom: str) -> dict:
    return RECETTES.get(str(nom or "").strip(), {})


def commande(nom: str, action: str) -> list:
    """La commande d'une recette pour une action — la SEULE façon d'obtenir une commande.
    Le client n'en propose jamais : il nomme une recette et une action, connues d'ici."""
    r = recette(nom)
    if not r:
        raise KeyError(f"recette inconnue : {nom}")
    if action not in ACTIONS:
        raise ValueError(f"action inconnue : {action}")
    if action == "test":
        return list(r["version"])
    cmd = r.get(action)
    if not cmd:
        raise ValueError(f"{nom} : pas de recette pour « {action} »")
    return list(cmd)


def version_de(sortie: str, nom: str) -> str:
    """La version lue dans la sortie d'une commande, ou "" — pur, testé."""
    m = re.search(recette(nom).get("version_re") or r"(\d+\.\d+\.\d+)", str(sortie or ""))
    return m.group(1) if m else ""
