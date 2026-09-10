#!/usr/bin/env python3
"""Tests RM3072 — les fournisseurs LLM prédéfinis, et les modèles demandés au fournisseur.

Ce qui doit tenir : un service donne tout sauf la clé, aucun secret ne traîne dans le catalogue, le
dialecte est déduit du type et non deviné, la liste de modèles vient de l'API et jamais du code, et une
clé absente donne un diagnostic plutôt qu'une trace.
"""
import importlib.util
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_llm_services as S                              # noqa: E402
spec = importlib.util.spec_from_file_location("llmm", HERE / "pm-llm-models.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


print("[RM3072] le catalogue des services")
cat = S.catalogue()
check("les services demandés sont là",
      {"openrouter", "zai", "anthropic", "ollama", "lemonade"} <= {e["id"] for e in cat})
check("chacun porte un type, une URL et un libellé", all(e["type"] and e["url"] and e["label"] for e in cat))
check("les URL sont des adresses, sans barre finale",
      all(e["url"].startswith("http") and not e["url"].endswith("/") for e in cat))
check("les hébergés viennent avant les locaux",
      [e["local"] for e in cat] == sorted([e["local"] for e in cat]))
check("un service local ne réclame pas de clé", all(not e["needs_key"] for e in cat if e["local"]))
check("un service hébergé en réclame une", all(e["needs_key"] for e in cat if not e["local"]))
check("où trouver une clé est dit pour les hébergés",
      all(S.service(e["id"]).get("keys_url") for e in cat if not e["local"]))

print("\n[RM3072] aucun secret dans un catalogue versionné (garde-fou 11)")
brut = json.dumps(S.SERVICES).lower()
check("aucune clé, aucun jeton, aucun mot de passe",
      not any(m in brut for m in ("api_key\":", "sk-", "bearer ", "password", "secret\":")))
src = (HERE / "pm-llm-models.py").read_text()
check("la clé ne passe jamais en argument de ligne de commande",
      "--key" not in src and "--api-key" not in src and "--token" not in src)
check("la clé est lue du .env, comme partout ailleurs", "pm_secrets" in src and "creds_for" in src)

print("\n[RM3072] déclarer un service, c'est trois champs")
d = S.declaration("openrouter", "or-perso")
check("nom libre, axe llm, type et URL posés",
      d == {"name": "or-perso", "axis": "llm", "type": "openai", "url": "https://openrouter.ai/api/v1"})
check("sans nom donné, l'identifiant du service fait l'affaire", S.declaration("groq")["name"] == "groq")
try:
    S.declaration("service-imaginaire"); check("un service inconnu est refusé", False)
except KeyError:
    check("un service inconnu est refusé", True)

print("\n[RM3072] le dialecte se déduit du type, il ne se devine pas")
check("ollama a le sien", M.dialecte_de("ollama") == "ollama")
check("anthropic a le sien", M.dialecte_de("anthropic") == "anthropic")
check("lemonade et les compatibles parlent OpenAI",
      M.dialecte_de("lemonade") == "openai" and M.dialecte_de("openai") == "openai")
check("un type inconnu retombe sur le dialecte le plus répandu", M.dialecte_de("zzz") == "openai")

print("\n[RM3072] les modèles viennent de l'API, jamais du code")
appels = []


def faux_http(url, entetes):
    appels.append((url, dict(entetes)))
    if url.endswith("/api/tags"):
        return {"models": [{"name": "qwen3:8b"}, {"name": "llama3.2:3b"}]}
    return {"data": [{"id": "z-beta"}, {"id": "a-alpha"}]}


vrai = M._http; M._http = faux_http
noms = M.modeles("https://api.exemple.fr/v1", "openai", "clef-factice")
check("le dialecte OpenAI interroge /models", appels[-1][0] == "https://api.exemple.fr/v1/models")
check("la clé part en en-tête, jamais dans l'URL",
      appels[-1][1].get("Authorization", "").startswith("Bearer ") and "clef" not in appels[-1][0])
check("les identifiants reviennent triés", noms == ["a-alpha", "z-beta"])
appels.clear()
noms = M.modeles("http://localhost:11434", "ollama")
check("Ollama a sa propre route", appels[-1][0] == "http://localhost:11434/api/tags")
check("sans clé, aucun en-tête d'autorisation n'est inventé", "Authorization" not in appels[-1][1])
check("les modèles tirés localement sont rendus", noms == ["llama3.2:3b", "qwen3:8b"])
appels.clear()
M.modeles("https://api.anthropic.com", "anthropic", "clef-factice")
check("Anthropic a son en-tête et sa version d'API",
      appels[-1][1].get("x-api-key") == "clef-factice" and appels[-1][1].get("anthropic-version"))
try:
    M.modeles("https://api.anthropic.com", "anthropic"); check("Anthropic sans clé : refus parlant", False)
except ValueError as e:
    check("Anthropic sans clé : refus parlant", "clé" in str(e))
try:
    M.modeles("", "openai"); check("sans URL, on le dit plutôt que d'appeler dans le vide", False)
except ValueError:
    check("sans URL, on le dit plutôt que d'appeler dans le vide", True)
check("aucun service ne porte de liste de modèles : elle périmerait en silence",
      not any(set(v) & {"models", "model", "default_model"} for v in S.SERVICES.values()))
M._http = vrai

print("\n[RM3080] la clé posée par le cockpit est retrouvée à l'usage")
import os                                                # noqa: E402
import pm_secrets                                        # noqa: E402
check("les préfixes que sait poser pm-provider-secret sont connus de la lecture",
      {"SECRET__", "LLM__", "REDMINE__", "GITLAB__"} <= set(pm_secrets.CREDS_PREFIXES))
faux = {"LLM__OLLAMA_STRIX__API_KEY": "clef", "SECRET__VW__CLIENTID": "autre"}
check("sous le seul SECRET__, une clé de modèle reste introuvable — c'était le défaut",
      pm_secrets.creds_keys("ollama-strix", env=faux, legacy=False) == [])
check("sous tous les préfixes, elle est retrouvée",
      pm_secrets.creds_keys("ollama-strix", env=faux, legacy=False,
                            prefixes=pm_secrets.CREDS_PREFIXES) == ["API_KEY"])
check("et un coffre continue d'être lu comme avant",
      pm_secrets.creds_keys("vw", env=faux, legacy=False) == ["CLIENTID"])
os.environ["LLM__OLLAMA_TEST__API_KEY"] = "clef-de-test"
try:
    check("le lecteur de l'axe llm va la chercher au bon endroit", M._clef("ollama-test") == "clef-de-test")
    check("une instance sans clé posée rend une chaîne vide, pas une erreur", M._clef("instance-sans-cle") == "")
finally:
    os.environ.pop("LLM__OLLAMA_TEST__API_KEY", None)

print("\n[RM3072] résoudre : un service, une instance déclarée, ou du direct")
u, dial, inst = M.resout(service="zai")
check("un service prédéfini donne son URL et son dialecte",
      u.startswith("https://api.z.ai") and dial == "openai" and inst == "zai")
u, dial, inst = M.resout(service="ollama", instance="ollama-strix")
check("l'instance nommée porte la clé, le service porte l'URL",
      dial == "ollama" and inst == "ollama-strix" and u == "http://localhost:11434")
u, dial, _ = M.resout(url="http://ailleurs:8000/v1", type_="openai")
check("une URL directe se suffit", u == "http://ailleurs:8000/v1" and dial == "openai")

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm_llm_services"))
sys.exit(1 if FAIL else 0)
