#!/usr/bin/env python3
"""pm_llm_call — un appel de complétion à un fournisseur du registre (RM3073).

Un seul endroit sait parler aux trois dialectes (OpenAI, Ollama, Anthropic), résoudre l'instance à
appeler et lire sa clé. Les scripts qui ont besoin d'un modèle demandent ici plutôt que de recoder un
client chacun — c'est ce qui rend le fournisseur interchangeable, ce qui est tout l'intérêt du registre.

La clé est lue du `.env` par `pm_secrets`, jamais reçue en argument, jamais rendue (garde-fou 11).
L'usage (tokens consommés) revient avec la réponse : un appel qui ne se mesure pas ne se pilote pas.
"""
import importlib.util
import json
import os
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("_llmm", HERE / "pm-llm-models.py")
_M = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_M)

TIMEOUT = 300


class LlmError(RuntimeError):
    """Le fournisseur n'a pas répondu, ou a répondu autre chose qu'une complétion."""


def resout(service=None, instance=None, url=None, type_=None, modele=None):
    """(url, dialecte, instance, modèle) — d'un service prédéfini, d'une instance déclarée, ou direct.
    Le modèle vient de l'appelant, sinon des options de l'instance au registre, sinon de l'environnement."""
    u, dial, inst = _M.resout(service, instance, url, type_)
    m = modele or os.environ.get("LLM_MODEL") or ""
    if not m and inst:
        try:
            import yaml
            from pm_registry import Registry
            from pm_paths import PMConfig
            cfg = PMConfig.load()
            prov = (yaml.safe_load((Path(cfg.pm_dir) / "pm.config.yml").read_text(encoding="utf-8")) or {}).get("providers") or {}
            i = Registry.from_config(prov).get(inst)
            m = ((i.options or {}).get("model") or "") if i else ""
        except Exception:
            m = ""
    return u, dial, inst, m


def chat(messages, url, dialecte, cle="", modele="", temperature=0.0, max_tokens=16000) -> tuple:
    """(texte, usage) — une complétion. `messages` : [{role, content}] comme partout.

    `usage` porte au moins in/out quand le fournisseur les donne : c'est ce qui permet de facturer un
    appel machine au ticket qui l'a demandé, comme le reste du travail."""
    base = (url or "").rstrip("/")
    if not base:
        raise LlmError("aucune URL de fournisseur : ni service, ni instance, ni --url")
    if not modele:
        raise LlmError("aucun modèle : donne-le à l'appel, à l'instance du registre, ou par LLM_MODEL")
    if dialecte == "anthropic":
        sys_msg = " ".join(m["content"] for m in messages if m["role"] == "system")
        corps = {"model": modele, "max_tokens": max_tokens, "temperature": temperature,
                 "messages": [m for m in messages if m["role"] != "system"]}
        if sys_msg:
            corps["system"] = sys_msg
        route, entetes = f"{base}/v1/messages", {"x-api-key": cle, "anthropic-version": "2023-06-01",
                                                 "content-type": "application/json"}
    elif dialecte == "ollama":
        corps = {"model": modele, "messages": messages, "stream": False,
                 "options": {"temperature": temperature, "num_predict": max_tokens}}
        route, entetes = f"{base}/api/chat", {"content-type": "application/json"}
        if cle:
            entetes["Authorization"] = f"Bearer {cle}"
    else:
        corps = {"model": modele, "messages": messages, "temperature": temperature,
                 "max_tokens": max_tokens}
        route, entetes = f"{base}/chat/completions", {"content-type": "application/json"}
        if cle:
            entetes["Authorization"] = f"Bearer {cle}"
    req = urllib.request.Request(route, data=json.dumps(corps).encode("utf-8"),
                                 headers=entetes, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            d = json.loads(r.read().decode("utf-8") or "{}")
    except Exception as e:                      # HTTP, réseau, JSON : un diagnostic, pas une trace
        code = getattr(e, "code", 0)
        detail = {401: "clé absente ou refusée", 403: "clé sans droit", 404: "route inconnue à cette URL",
                  429: "quota ou débit dépassé"}.get(code, str(e))
        raise LlmError(f"{route} : {detail}") from None
    return _texte(d, dialecte), _usage(d, dialecte)


def _texte(d: dict, dialecte: str) -> str:
    if dialecte == "anthropic":
        return "".join(b.get("text", "") for b in (d.get("content") or []) if isinstance(b, dict))
    if dialecte == "ollama":
        return ((d.get("message") or {}).get("content")) or ""
    ch = (d.get("choices") or [{}])[0]
    return ((ch.get("message") or {}).get("content")) or ch.get("text") or ""


def _usage(d: dict, dialecte: str) -> dict:
    u = d.get("usage") or {}
    if dialecte == "anthropic":
        return {"in": u.get("input_tokens", 0), "out": u.get("output_tokens", 0)}
    if dialecte == "ollama":
        return {"in": d.get("prompt_eval_count", 0), "out": d.get("eval_count", 0)}
    return {"in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0)}


def cle_de(instance: str) -> str:
    """La clé de l'instance, lue du `.env`. Jamais affichée, jamais journalisée."""
    return _M._clef(instance)
