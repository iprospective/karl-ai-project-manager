#!/usr/bin/env python3
"""pm-llm-models — ce qu'un fournisseur LLM sert VRAIMENT, demandé au fournisseur (RM3072).

Une liste de modèles écrite dans du code périme en quelques semaines et ment ensuite sans le dire. Les API
du dialecte OpenAI exposent `GET /models`, Ollama expose `GET /api/tags` : on demande, on ne devine pas.

  pm-llm-models --service openrouter          les modèles d'un service prédéfini (clé prise du .env)
  pm-llm-models --instance vw-llm             les modèles d'une instance déjà déclarée au registre
  pm-llm-models --url … --type openai         un service qu'on n'a pas encore déclaré
  --json          la liste brute, pour le cockpit
  --grep motif    ne garder que les identifiants qui contiennent ce motif

La clé n'est jamais affichée, jamais journalisée, jamais passée en argument (garde-fou 11) : elle est lue
du `.env` par `pm_secrets`, comme partout ailleurs.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_llm_services as S                              # noqa: E402
try:
    import pm_secrets
except ImportError:                                      # pragma: no cover
    pm_secrets = None

TIMEOUT = 20


def _clef(instance: str) -> str:
    """La clé d'API de l'instance, depuis le `.env`. Vide si aucune n'est posée — un service local n'en
    veut pas, et un service hébergé répondra 401, ce qui est un diagnostic en soi."""
    if not pm_secrets or not instance:
        return ""
    try:
        creds = pm_secrets.creds_for(instance, legacy=False)
    except Exception:
        return ""
    for suffixe in ("API_KEY", "KEY", "TOKEN"):
        if creds.get(suffixe):
            return str(creds[suffixe])
    return ""


def _http(url: str, entetes: dict) -> dict:
    req = urllib.request.Request(url, headers=entetes)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def modeles(url: str, dialecte: str, cle: str = "") -> list:
    """Les identifiants de modèles servis, triés. Lève une erreur parlante si le service refuse."""
    base = (url or "").rstrip("/")
    if not base:
        raise ValueError("aucune URL : ni service prédéfini, ni instance déclarée, ni --url")
    if dialecte == "ollama":
        d = _http(f"{base}/api/tags", {"Authorization": f"Bearer {cle}"} if cle else {})
        return sorted({m.get("name", "") for m in (d.get("models") or []) if m.get("name")})
    if dialecte == "anthropic":
        if not cle:
            raise ValueError("l'API Anthropic exige une clé — pose-la par `mmi-pm provider-secret`")
        d = _http(f"{base}/v1/models", {"x-api-key": cle, "anthropic-version": "2023-06-01"})
        return sorted({m.get("id", "") for m in (d.get("data") or []) if m.get("id")})
    # dialecte OpenAI : openai, lemonade, et tous les services hébergés compatibles
    d = _http(f"{base}/models", {"Authorization": f"Bearer {cle}"} if cle else {})
    return sorted({m.get("id", "") for m in (d.get("data") or d.get("models") or []) if m.get("id")})


def dialecte_de(type_provider: str) -> str:
    """Le type déclaré au registre dit comment on parle au service."""
    t = str(type_provider or "").lower()
    if t in ("ollama",):
        return "ollama"
    if t in ("anthropic",):
        return "anthropic"
    return "openai"          # openai, lemonade, et tous les compatibles


def _du_registre(nom: str):
    """(url, type) d'une instance déjà déclarée, ou (None, None) si le registre ne la connaît pas."""
    try:
        import yaml
        from pm_registry import Registry
        from pm_paths import PMConfig
        cfg = PMConfig.load()
        prov = (yaml.safe_load((Path(cfg.pm_dir) / "pm.config.yml").read_text(encoding="utf-8")) or {}).get("providers") or {}
        inst = Registry.from_config(prov).get(nom)
        return (inst.url, inst.type) if inst else (None, None)
    except Exception:
        return None, None


def resout(service=None, instance=None, url=None, type_=None):
    """(url, dialecte, instance_pour_la_clé) — un service prédéfini, une instance déclarée, ou du direct."""
    if service:
        s = S.service(service)
        if not s:
            raise KeyError(f"service inconnu : {service} — `--list` donne les connus")
        return (url or s["url"]), dialecte_de(type_ or s["type"]), (instance or service)
    if instance:
        u, t = _du_registre(instance)
        return (url or u), dialecte_de(type_ or t), instance
    return url, dialecte_de(type_), (instance or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="les services prédéfinis, sans rien interroger")
    ap.add_argument("--service", help="identifiant d'un service prédéfini (openrouter, zai, ollama…)")
    ap.add_argument("--instance", help="nom d'une instance déclarée au registre (porte la clé)")
    ap.add_argument("--url"); ap.add_argument("--type", dest="type_")
    ap.add_argument("--grep", help="ne garder que les identifiants contenant ce motif")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.list or not (a.service or a.instance or a.url):
        cat = S.catalogue()
        if a.json:
            print(json.dumps(cat, ensure_ascii=False, indent=1)); return 0
        for e in cat:
            ou = "local " if e["local"] else "hébergé"
            print(f"  {ou} {e['id']:14} {e['label']:28} {e['url']}")
            if e["note"]:
                print(f"          {'':14} {e['note']}")
        return 0
    try:
        url, dial, inst = resout(a.service, a.instance, a.url, a.type_)
        noms = modeles(url, dial, _clef(inst))
    except (KeyError, ValueError) as e:
        sys.exit(f"ERREUR : {e}")
    except urllib.error.HTTPError as e:
        quoi = {401: "clé absente ou refusée", 403: "clé sans droit sur cette route",
                404: "cette URL n'expose pas de liste de modèles"}.get(e.code, f"HTTP {e.code}")
        sys.exit(f"ERREUR : {url} → {quoi}")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        sys.exit(f"ERREUR : {url} injoignable ou muet ({e})")
    if a.grep:
        noms = [n for n in noms if a.grep.lower() in n.lower()]
    if a.json:
        print(json.dumps({"url": url, "dialect": dial, "models": noms}, ensure_ascii=False, indent=1))
    else:
        print("\n".join(noms) if noms else "(aucun modèle servi)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
