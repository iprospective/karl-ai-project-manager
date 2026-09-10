#!/usr/bin/env python3
"""pm_llm_services — les fournisseurs de modèles connus, prêts à déclarer (RM3072).

Brancher un modèle demandait de retrouver l'URL de son API, de savoir si elle parle le dialecte OpenAI ou
celui d'Anthropic, et d'écrire de mémoire un identifiant de modèle qu'on ne vérifiait qu'à l'usage. Cette
friction fait renoncer à brancher un modèle bon marché là où il rendrait service.

Un service prédéfini donne tout sauf la clé : le type de provider auquel il se ramène, l'URL de base, et où
aller chercher une clé. Il ne porte AUCUN secret — la clé se pose par `pm-provider-secret`, en écriture
seule, et rien ne la relit (garde-fou 11).

**Les modèles ne sont pas écrits ici.** Une liste de modèles figée dans du code périme en quelques semaines
et ment ensuite sans le dire. Les API du dialecte OpenAI exposent `GET /models` : `pm-llm-models` interroge
le service une fois la clé posée et rend ce qui est RÉELLEMENT disponible.

  local=True   le service tourne sur la machine ou le réseau local : pas de clé, pas de facturation.
"""
#: chaque entrée : type de provider, URL de base de l'API, page des clés, et le piège s'il y en a un.
SERVICES = {
    # ── hébergés, dialecte OpenAI ────────────────────────────────────────────
    "openrouter": {"label": "OpenRouter", "type": "openai", "url": "https://openrouter.ai/api/v1",
                   "keys_url": "https://openrouter.ai/keys",
                   "note": "passerelle vers des centaines de modèles de tous les éditeurs ; "
                           "l'identifiant du modèle y est préfixé par son éditeur"},
    "zai": {"label": "Z.ai (GLM)", "type": "openai", "url": "https://api.z.ai/api/paas/v4",
            "keys_url": "https://z.ai/manage-apikey/apikey-list",
            "note": "les modèles GLM ; l'instance chinoise de Zhipu a une autre base (open.bigmodel.cn)"},
    "groq": {"label": "Groq", "type": "openai", "url": "https://api.groq.com/openai/v1",
             "keys_url": "https://console.groq.com/keys", "note": "inférence très rapide, catalogue restreint"},
    "deepseek": {"label": "DeepSeek", "type": "openai", "url": "https://api.deepseek.com/v1",
                 "keys_url": "https://platform.deepseek.com/api_keys"},
    "mistral": {"label": "Mistral AI", "type": "openai", "url": "https://api.mistral.ai/v1",
                "keys_url": "https://console.mistral.ai/api-keys"},
    "together": {"label": "Together AI", "type": "openai", "url": "https://api.together.xyz/v1",
                 "keys_url": "https://api.together.ai/settings/api-keys"},
    "fireworks": {"label": "Fireworks AI", "type": "openai", "url": "https://api.fireworks.ai/inference/v1",
                  "keys_url": "https://fireworks.ai/account/api-keys"},
    "cerebras": {"label": "Cerebras", "type": "openai", "url": "https://api.cerebras.ai/v1",
                 "keys_url": "https://cloud.cerebras.ai"},
    "xai": {"label": "xAI (Grok)", "type": "openai", "url": "https://api.x.ai/v1",
            "keys_url": "https://console.x.ai"},
    "gemini": {"label": "Google Gemini", "type": "openai",
               "url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "keys_url": "https://aistudio.google.com/apikey",
               "note": "endpoint de compatibilité OpenAI ; l'API native de Gemini a un autre dialecte"},
    "openai": {"label": "OpenAI", "type": "openai", "url": "https://api.openai.com/v1",
               "keys_url": "https://platform.openai.com/api-keys"},
    "ollama-cloud": {"label": "Ollama Cloud", "type": "ollama", "url": "https://ollama.com",
                     "keys_url": "https://ollama.com/settings/keys",
                     "note": "les mêmes modèles qu'en local, servis à distance ; clé requise"},
    # ── hébergé, dialecte propre ─────────────────────────────────────────────
    "anthropic": {"label": "Anthropic", "type": "anthropic", "url": "https://api.anthropic.com",
                  "keys_url": "https://console.anthropic.com/settings/keys",
                  "note": "dialecte propre ; un abonnement Claude ne donne pas de crédit d'API"},
    # ── locaux : rien à payer, rien à déclarer d'autre que le port ───────────
    "ollama": {"label": "Ollama (local)", "type": "ollama", "url": "http://localhost:11434", "local": True,
               "note": "port par défaut ; `ollama list` dit ce qui est déjà tiré"},
    "lemonade": {"label": "Lemonade Server (local)", "type": "lemonade", "url": "http://localhost:8000/api/v1",
                 "local": True, "note": "accéléré sur Ryzen AI ; dialecte OpenAI"},
    "lmstudio": {"label": "LM Studio (local)", "type": "openai", "url": "http://localhost:1234/v1", "local": True,
                 "note": "le serveur doit être démarré depuis l'application"},
    "vllm": {"label": "vLLM (local ou réseau)", "type": "openai", "url": "http://localhost:8000/v1", "local": True,
             "note": "un serveur vLLM sert un seul modèle à la fois"},
}

#: dialectes que `GET /models` renseigne — ailleurs, il faut demander au service autrement
LISTABLES = ("openai", "lemonade", "ollama")


def service(nom: str) -> dict:
    return SERVICES.get(str(nom or "").strip().lower()) or {}


def catalogue() -> list:
    """Les services, hébergés d'abord puis locaux, chacun tel que le cockpit l'affiche."""
    def vue(k, s):
        return {"id": k, "label": s["label"], "type": s["type"], "url": s["url"],
                "keys_url": s.get("keys_url", ""), "note": s.get("note", ""),
                "local": bool(s.get("local")), "listable": s["type"] in LISTABLES,
                "needs_key": not s.get("local")}
    return ([vue(k, s) for k, s in SERVICES.items() if not s.get("local")]
            + [vue(k, s) for k, s in SERVICES.items() if s.get("local")])


def declaration(nom: str, instance: str = "") -> dict:
    """Ce qu'il faut écrire dans le registre pour ce service : type, url, et rien d'autre.
    Le nom de l'instance reste libre — on peut avoir deux OpenRouter, un par compte."""
    s = service(nom)
    if not s:
        raise KeyError(f"service inconnu : {nom}")
    return {"name": (instance or nom), "axis": "llm", "type": s["type"], "url": s["url"]}
