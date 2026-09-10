#!/usr/bin/env python3
"""pm_provider_types — le CATALOGUE des types de fournisseurs (RM3068).

Un type dit trois choses : sur quel axe il vit, quels champs le déclarent, et quelles clés il attend.
Le cockpit construit ses formulaires à partir d'ici : ajouter un type est une entrée de ce catalogue,
jamais du code d'interface.

Une entrée de `secrets` ne porte QUE le nom de la clé et son libellé — **jamais une valeur** : les
secrets vivent dans un `.env` (voir `pm-provider-secret.py`) et rien ne les relit.
"""
#: champ : (nom, libellé, requis, aide)
_URL = ("url", "URL", True, "adresse du service, sans barre finale")
_MODEL = ("model", "Modèle", False, "identifiant du modèle servi (ex. qwen3-8b)")

CATALOGUE = {
    # ── axe task : le gestionnaire de tickets ────────────────────────────────
    "redmine": {"axis": "task", "label": "Redmine", "fields": [_URL],
                "secrets": [("API_KEY", "Clé d'API")], "prefix": "REDMINE"},
    # ── axe forge : le dépôt de code ─────────────────────────────────────────
    "gitlab": {"axis": "forge", "label": "GitLab", "fields": [_URL,
               ("ssh_aliases", "Alias SSH", False, "alias de ~/.ssh/config qui atteignent cette forge, séparés par des virgules")],
               "secrets": [("TOKEN", "Jeton d'accès")], "prefix": "GITLAB"},
    "gogs": {"axis": "forge", "label": "Gogs", "fields": [_URL,
             ("ssh_port", "Port SSH", False, "22 par défaut ; 28022 chez certains hébergeurs"),
             ("ssh_aliases", "Alias SSH", False, "séparés par des virgules")],
             "secrets": [("TOKEN", "Jeton d'accès")], "prefix": "GOGS"},
    "github": {"axis": "forge", "label": "GitHub", "fields": [("url", "URL", False, "https://github.com par défaut"),
               ("owner", "Compte ou organisation", False, "")],
               "secrets": [("TOKEN", "Jeton d'accès")], "prefix": "GITHUB"},
    # ── axe doc : où publier la documentation ────────────────────────────────
    "redmine_wiki": {"axis": "doc", "label": "Wiki Redmine", "fields": [_URL], "secrets": [], "prefix": "REDMINE",
                     "note": "utilise la clé du Redmine de même URL"},
    "nextcloud": {"axis": "doc", "label": "Nextcloud", "fields": [_URL],
                  "secrets": [("USER", "Utilisateur"), ("TOKEN", "Mot de passe d'application")], "prefix": "NC"},
    # ── axe secret : les coffres ─────────────────────────────────────────────
    "vaultwarden": {"axis": "secret", "label": "Vaultwarden", "fields": [_URL],
                    "secrets": [("CLIENTID", "Identifiant client"), ("CLIENTSECRET", "Secret client")], "prefix": "SECRET"},
    "keepass": {"axis": "secret", "label": "KeePass (.kdbx)", "fields": [("file", "Fichier", True, "chemin du .kdbx")],
                "secrets": [("PASSWORD", "Mot de passe du coffre")], "prefix": "SECRET"},
    "age": {"axis": "secret", "label": "Fichier chiffré (age)", "fields": [("file", "Fichier", True, "YAML ou JSON chiffré")],
            "secrets": [("AGE_KEY_FILE", "Chemin de la clé privée (0600)")], "prefix": "SECRET"},
    "onepassword": {"axis": "secret", "label": "1Password", "fields": [("vault", "Coffre", True, "")],
                    "secrets": [("TOKEN", "Jeton de compte de service")], "prefix": "SECRET"},
    "nextcloud_passwords": {"axis": "secret", "label": "Nextcloud Passwords", "fields": [_URL],
                            "secrets": [("USER", "Utilisateur"), ("TOKEN", "Mot de passe d'application")], "prefix": "SECRET"},
    # ── axe llm : le modèle de travail de karl (RM3067) ──────────────────────
    "lemonade": {"axis": "llm", "label": "Lemonade Server (Ryzen AI)", "fields": [_URL, _MODEL],
                 "secrets": [("API_KEY", "Clé (souvent inutile en local)")], "prefix": "LLM",
                 "note": "API compatible OpenAI, en local sur la machine"},
    "ollama": {"axis": "llm", "label": "Ollama", "fields": [_URL, _MODEL],
               "secrets": [("API_KEY", "Clé (service hébergé seulement)")], "prefix": "LLM"},
    "openai": {"axis": "llm", "label": "Serveur compatible OpenAI (vLLM, LM Studio…)", "fields": [_URL, _MODEL],
               "secrets": [("API_KEY", "Clé")], "prefix": "LLM"},
    "anthropic": {"axis": "llm", "label": "API Anthropic", "fields": [_MODEL],
                  "secrets": [("API_KEY", "Clé d'API")], "prefix": "LLM"},
    "claude-cli": {"axis": "llm", "label": "Claude Code (claude -p)", "fields": [_MODEL], "secrets": [], "prefix": "LLM",
                   "note": "aucun secret ; le CLI refacture son prompt système à chaque appel"},
}

AXES = ("task", "forge", "doc", "secret", "llm")
AXE_LABEL = {"task": "Tickets", "forge": "Dépôts de code", "doc": "Documentation",
             "secret": "Coffres à secrets", "llm": "Modèles de travail"}


def catalogue() -> dict:
    """Le catalogue en JSON : axes (dans l'ordre) et types, champs et NOMS des clés attendues."""
    types = []
    for nom, d in sorted(CATALOGUE.items(), key=lambda kv: (AXES.index(kv[1]["axis"]), kv[0])):
        types.append({"type": nom, "axis": d["axis"], "label": d["label"], "prefix": d["prefix"],
                      "note": d.get("note", ""),
                      "fields": [{"name": f[0], "label": f[1], "required": f[2], "help": f[3]} for f in d["fields"]],
                      "secrets": [{"key": k, "label": l} for k, l in d["secrets"]]})
    return {"axes": [{"axis": a, "label": AXE_LABEL[a]} for a in AXES], "types": types}


def type_de(nom: str) -> dict:
    return CATALOGUE.get(str(nom or "").lower(), {})


def champs_admis(nom: str) -> set:
    return {f[0] for f in type_de(nom).get("fields", [])}


def prefixe_de(nom: str) -> str:
    return type_de(nom).get("prefix", "")


def cles_attendues(nom: str) -> list:
    return [k for k, _ in type_de(nom).get("secrets", [])]
