#!/usr/bin/env python3
"""pm-think-classify — classe les tours d'une conversation par un LLM LÉGER, au lieu d'une heuristique (RM3067).

Le critère d'une entrée de `.think.md` est sémantique (NORMS `session-tooling` § « Les quatre rubriques ») :
une note ne retient QUE ce qui n'a pas été traité, se comprend hors du fil, et n'est pas déjà réglé. Un motif
de texte ne décide pas de ça ; un modèle léger, si — pour ~1 $ par million de jetons.

  Ce qui part au modèle : les tours de CONVERSATION (utilisateur ET agent), tronqués.
  Ce qui n'y va JAMAIS  : le tooling (`tool_use`, `tool_result`), les enveloppes techniques
                          (`<command-name>`, `<system-reminder>`…), les commandes `/…`, les modifications
                          de fichiers — ils ne portent pas de réflexion et coûteraient le plus cher.

  pm-think-classify --transcript <f.jsonl> [--rm <id>]     un transcript
  pm-think-classify --session <sid> [--rm <id>]            la session (transcript résolu)
  pm-think-classify --all [--since AAAA-MM-JJ] [--limit N] reprise de l'historique
  --apply            écrit dans les `.think.md` (défaut : rapport seul, rien n'est écrit)
  --model <id>       défaut : claude-haiku-4-5-20251001 ; --batch <n> tours par appel (défaut 25)
  --engine claude|api|ollama|openai
                     `claude -p` (pas de clé à gérer) · l'API Anthropic · **Ollama** (local ou hébergé),
                     choisi d'office si `OLLAMA_HOST`/`OLLAMA_API_KEY` est posé, puis l'API si sa clé existe.
                     Ollama : `OLLAMA_HOST` (défaut `http://localhost:11434`), `OLLAMA_API_KEY` pour un service
                     hébergé, modèle via `--model` (ex. `qwen3:8b`, `llama3.1:8b`) — coût nul, c'est l'abonnement.
                     `openai` : tout serveur à l'API OpenAI — **Lemonade Server** (AMD Ryzen AI / Strix Halo),
                     vLLM, LM Studio, llama.cpp. `LLM_BASE_URL` (ex. `http://strix.lan:8000/api/v1`),
                     `LLM_API_KEY` si le serveur en demande une, `LLM_MODEL` pour le défaut.

LOCAL ou distant, c'est le même code : rien n'est codé en dur vers un service. En local, les transcripts —
qui portent le travail des clients — ne quittent pas la machine, et la passe ne coûte rien.

Coût (mesuré le 2026-09-10) : par l'API, ~1 $ par million de jetons d'entrée, soit ~3 $ pour les 276 transcripts.
Par `claude -p`, le CLI refacture son propre prompt système à chaque appel : compter ~40× plus, et donc réserver
ce mode à une session isolée, avec un gros `--batch`.

Le moteur est injectable pour les tests : `PM_CLASSIFY_CMD` reçoit le prompt sur stdin et rend le JSON.
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_git                                   # noqa: E402
import pm_think                                 # noqa: E402
from pm_paths import PMConfig                   # noqa: E402

MODEL = "claude-haiku-4-5-20251001"
BATCH = 60          # RM3067 : `claude -p` refacture son prompt système à CHAQUE appel (~15-20 k jetons) —
                    # de gros lots l'amortissent ; `--engine api` n'envoie que le prompt et coûte ~40× moins.
MAX_CHARS = 600
MIN_USER, MIN_AGENT = 30, 120
TYPES = {"rien", "dette", "question", "decision", "feature"}
KIND = {"dette": "note", "question": "question", "decision": "decision", "feature": "feature"}
CLAUDE_STORES = [Path(p).expanduser() for p in
                 os.environ.get("PM_CLAUDE_STORES", str(Path.home() / ".claude" / "projects")).split(":") if p.strip()]

CONSIGNE = """Tu tries les tours d'une conversation entre un développeur (« M ») et un agent de code (« A »), pour un
carnet de bord de projet. Le carnet ne sert QU'À une chose : retrouver plus tard ce qui n'a PAS été traité.

Pour chaque tour, réponds par UN type :
- "dette"    : il reste quelque chose à faire, explicitement différé ou manquant (« pour l'instant… on verra plus
               tard », « il faudra », « il manque », une intention non réalisée), ET on comprend QUOI en lisant le
               tour seul, hors du fil.
- "question" : quelque chose n'est pas tranché et bloque une suite.
- "decision" : le développeur tranche, arbitre, ou pose une règle à suivre.
- "feature"  : une fonctionnalité à faire, atomique, qui donnera un ticket ou complétera un ticket.
- "rien"     : tout le reste, et c'est le cas le PLUS fréquent.

Sont TOUJOURS "rien" : un ordre d'exécution à l'agent, même long et même s'il contient « il faudra » (« merge et
pousse », « consigne tout ça », « fais un ticket », « étudie RM3058 ») ; une réponse à une question déjà posée
(« Q23 : oui… ») ; un accord ou un accusé (« ok », « ça marche », « j'ai fait le ssh-add ») ; un constat de bug
(c'est un ticket, pas une note) ; une contrainte sans contexte dont on ne sait pas de quoi elle parle ; un rendu
de travail de l'agent (« j'ai livré », « les tests passent ») ; du collage de console.

Pour tout ce qui n'est pas "rien", écris dans "x" une reformulation AUTO-SUFFISANTE d'une phrase : elle doit se
comprendre seule dans six mois, en nommant l'objet concerné. Sinon, c'est "rien".

Réponds UNIQUEMENT par un tableau JSON, un objet par tour, sans texte autour :
[{"i": 0, "t": "rien"}, {"i": 3, "t": "dette", "x": "Le déploiement passe par ssh -A faute de mieux : prévoir un accès propre."}]
Les tours "rien" peuvent être omis."""


# ── RM3090 : LE critère, en version heuristique ──────────────────────────────
# La moisson (`pm-think-harvest`) tourne à CHAQUE fin de tour, en hook : elle doit rendre la main
# tout de suite, donc sans appeler de modèle. Elle applique donc la même règle de partage que la
# consigne ci-dessus, en version pauvre — et le classificateur LLM reste la passe de fond qui
# complète et corrige (`--all`).
#
# La règle vient d'un arbitrage de Mathieu (2026-09-10, RM3015-D011) : une question ouverte est
# TOUT ce qui n'est pas tranché, **quel qu'en soit l'auteur** — y compris ce que le demandeur se
# demande à lui-même. La moisson ne créait de question que depuis un outil de question formelle ;
# tout le reste devenait une note, et la question posée ce jour-là a fini en note.
#
# En cas de doute : note. Une note mal classée se trie ; une question perdue ne se retrouve pas.
# RM3141 : la liste des verbes n'est pas décorative — un verbe absent fait passer une DEMANDE pour
# une question, et une question ouverte bloque la clôture d'un ticket. « ferme » manquait, et c'est
# l'ordre le plus fréquent de fin de séance : six captures accidentelles en une seule journée.
_ORDRE = re.compile(r"^\s*(?:[-*•]\s*)?(fais|fait|ajoute|cr[ée]e|corrige|livre|merge|pousse|lance|"
                    r"refais|relance|mets?|met |applique|supprime|renomme|d[ée]place|continue|"
                    r"reprends?|go\b|ok\b|consigne|note |ticket|traite|termine|finis|ferme|"
                    r"encha[îi]ne|v[ée]rifie|regarde|[ée]tudie|avance|requalifie|teste|d[ée]ploie|"
                    r"promeus|analyse|pr[ée]pare|passe|rends?|garde|laisse|arr[êe]te|stoppe|"
                    r"compacte|bascule|migre|renseigne|remplace|all[ée]ge|s[ée]pare)", re.I)
#: RM3141 : un résumé de compaction est un ARTEFACT de session, jamais une parole du demandeur.
#: Il en est arrivé un entier dans les questions ouvertes d'un ticket (RM1923).
_ARTEFACT = re.compile(r"(This session is being continued|Summary:|<command-name>|"
                       r"system-reminder|Analysis:\s*$)", re.I | re.M)
# RM3141 : les six questions RÉELLES que l'audit signalait à tort — elles se posent sans « ? » et
# sans marque interrogative de la première liste. Une question qui n'a pas la bonne forme reste une
# question ; c'est l'arbitrage qui manque, pas la ponctuation.
_INTERRO = re.compile(r"(?:^|[\s(])(est-ce que|pourquoi|comment|combien|qui |quoi|quel(?:le|s|les)?\b|"
                      r"faut-il|peut-on|doit-on|serait-il|y a-t-il|à quoi|dans quel|"
                      r"que fait-on|on fait quoi|lequel|laquelle|lesquel(?:le)?s|"
                      r"l'id[ée]al (?:c'est|serait)|vaut-il mieux|ou bien\b|"
                      r"reste[- ]t[- ]il|tenable\b|à trancher|à arbitrer)", re.I)


# ── RM3259 : ce qui mérite de rester une QUESTION OUVERTE ────────────────────────
# Mesure du 2026-09-19 sur RM2881 : 21 questions ouvertes, 20 n'en étaient pas — « quel est le mdp
# de test ? », « on en est où de la v0 ? », « on enchaîne avec quoi ? ». Elles bloquaient la clôture
# du ticket. Une question de CONDUITE DE SÉANCE se répond dans la minute et ne change rien plus
# tard ; une question d'ARBITRAGE attend une décision, et c'est elle qu'on veut retrouver.
_CONDUITE = re.compile(r"(o[uù] (?:en )?(?:est-on|en sommes-nous|en es-tu)|on en est o[uù]|"
                       r"(?:c'est|ca|ça) (?:fait|bon|pr[êe]t|fini)\s*\?|tu as fini|as-tu fini|"
                       r"encha[îi]ne(?:r|s)? avec quoi|on fait quoi (?:maintenant|apr[èe]s)|"
                       r"(?:quelle|la) suite\b|on continue\s*\?|"
                       r"mot de passe|mdp\b|identifiants?\b|quelle url|quel (?:lien|port|chemin)\b|"
                       r"je ne (?:vois|comprends) pas|c'est o[uù]\s*\?|"
                       r"quelles? questions? bloque|[çc]a (?:marche|fonctionne)\s*\?)", re.I)
#: marques d'un ARBITRAGE en attente — elles priment sur la conduite de séance : « on enchaîne
#: avec quoi, ou faut-il d'abord trancher X ? » est une question, malgré sa première moitié.
_ARBITRAGE = re.compile(r"(faut-il|doit-on|vaut-il mieux|ou bien\b|plut[ôo]t que|"
                        r"est-ce (?:pertinent|souhaitable|raisonnable)|"
                        r"quelle (?:strat[ée]gie|architecture|convention|politique|r[èe]gle)|"
                        r"[àa] terme\b|[àa] trancher|[àa] arbitrer|on part sur)", re.I)
#: une question d'arbitrage tient rarement en six mots ; en dessous, c'est de la conduite de séance
_MIN_MOTS_QUESTION = 7
#: un « mot » au sens du critère : les nombres et la ponctuation ne comptent pas (même règle que
#: `pm_think.note_pertinente`, qui mesure la même chose — la matière du texte)
_MOT = re.compile(r"[^\W\d_]{2,}", re.U)


#: « Q29 : pour les ACL je dirais oui » — le demandeur RÉPOND à une question numérotée du carnet.
#: C'est une décision, et surtout pas une nouvelle question ouverte.
_REPONSE_A_Q = re.compile(r"^\s*(?:[-*•]\s*)?Q\s*\d{1,3}\s*[:.\)]", re.I)


def question_pertinente(texte: str):
    """(pertinente, motif) — cette question mérite-t-elle de rester OUVERTE sur un ticket ?

    Pendant de `pm_think.note_pertinente` pour les questions. RM3090 les en avait dispensées à
    dessein (« une question ne porte pas de dette, elle porte un arbitrage en attente ») : c'est
    vrai d'un arbitrage, faux d'une question d'exploitation, et c'est cette nuance qui manquait.
    En cas de doute : PERTINENTE — une question perdue ne se retrouve pas, une question de trop
    se trie (et, depuis RM3258, se déplace). Pure, testée sur les 21 entrées réelles de RM2881."""
    s = " ".join(str(texte or "").split())
    if not s:
        return False, "vide"
    if _REPONSE_A_Q.match(s):
        return False, "réponse à une question du carnet — c'est une décision"
    if _ARBITRAGE.search(s):
        return True, "arbitrage"
    if _CONDUITE.search(s):
        return False, "conduite de séance (se répond dans la minute, ne change rien plus tard)"
    if len(_MOT.findall(s)) < _MIN_MOTS_QUESTION:
        return False, "trop courte pour porter un arbitrage"
    return True, "question"


def deja_tranchee(suite: list) -> bool:
    """La question a-t-elle été RÉGLÉE dans la suite du fil ? Pure.

    `suite` = les tours qui suivent, du plus proche au plus lointain, sous forme (role, texte).
    Le signal n'est pas que l'agent ait répondu — il répond toujours — mais que le DEMANDEUR ait
    PRIS la réponse : son tour suivant approuve (« ok »), ou donne la consigne d'après. S'il
    réinterroge, ou si la séance s'arrête sans qu'il dise rien, la question reste ouverte.
    Un seul tour décide : celui d'après. Plus loin dans le fil, on parle d'autre chose."""
    for role, texte in suite:
        if role != "M":
            continue
        s = " ".join(str(texte or "").split())
        if not s:
            continue
        return type_heuristique("M", s) != "question"
    return False


def type_heuristique(role: str, texte: str) -> str:
    """`question` ou `dette` (→ note) pour un tour, SANS modèle. Pure, testée.

    Une question est reconnue à deux marques conjointes : une forme interrogative et l'absence
    d'ordre en tête. « fais-moi X, tu en penses quoi ? » est un ordre : il appelle une action, pas
    un arbitrage — c'est la distinction demande / question de RM3015-C008."""
    brut = str(texte or "")
    txt = " ".join(brut.split())
    if role != "M" or not txt:
        return "dette"
    if _ARTEFACT.search(brut):
        return "dette"
    # RM3141 : l'ordre se cherche en tête de CHAQUE ligne, pas du seul message. Une séance se donne
    # souvent en liste — « * core update fait. * ferme ce qui est en prod. * go 3140 » — et la tête
    # du message n'y est alors pas un ordre, alors que tout le reste en est. Le « ? » d'une ligne
    # suffisait alors à faire classer l'ENSEMBLE comme une question, qui bloquait ensuite une clôture.
    lignes = [l for l in brut.splitlines() if l.strip()]
    if any(_ORDRE.match(l) for l in (lignes or [txt])):
        return "dette"
    # Plusieurs demandes dans un même message : ce n'est pas UNE question. En cas de doute, note —
    # une note mal classée se trie, une question perdue ne se retrouve pas (règle ci-dessus).
    if len(lignes) > 2:
        return "dette"
    interro = txt.rstrip().endswith("?") or bool(_INTERRO.search(txt))
    return "question" if interro else "dette"


def tours(lines) -> list:
    """[(role, texte)] — les tours de CONVERSATION seulement. Le tooling n'y entre jamais. Pure, testée."""
    out = []
    for l in lines:
        try:
            o = json.loads(l)
        except ValueError:
            continue
        if not isinstance(o, dict) or o.get("isMeta") or o.get("type") not in ("user", "assistant"):
            continue
        c = (o.get("message") or {}).get("content")
        if isinstance(c, str):
            txt = c
        elif isinstance(c, list):
            # UNIQUEMENT les blocs de texte : ni tool_use, ni tool_result, ni thinking
            txt = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
        else:
            continue
        txt = " ".join(str(txt).split())
        if not txt or txt.startswith(("<", "/", "[Request interrupted")) or "This session is being continued" in txt:
            continue
        role = "M" if o["type"] == "user" else "A"
        if len(txt) < (MIN_USER if role == "M" else MIN_AGENT):
            continue
        out.append((role, txt[:MAX_CHARS]))
    return out


def prompt_lot(lot) -> str:
    corps = "\n".join(f"[{i}] {role} : {txt}" for i, (role, txt) in enumerate(lot))
    return f"{CONSIGNE}\n\n--- {len(lot)} tours ---\n{corps}"


def _json_tableau(texte: str) -> list:
    """Le tableau JSON d'une réponse de modèle, même entourée de prose ou d'une clôture ```json."""
    s = re.sub(r"^```(?:json)?|```$", "", (texte or "").strip(), flags=re.M).strip()
    i, j = s.find("["), s.rfind("]")
    if i < 0 or j <= i:
        return []
    try:
        v = json.loads(s[i:j + 1])
    except ValueError:
        return []
    return [x for x in v if isinstance(x, dict)]


def appelle(prompt: str, model: str, engine: str) -> tuple:
    """(items, coût_usd). Moteur injectable par PM_CLASSIFY_CMD (tests)."""
    cmd = os.environ.get("PM_CLASSIFY_CMD")
    if cmd:
        p = subprocess.run(cmd, shell=True, input=prompt, capture_output=True, text=True, timeout=300)
        return _json_tableau(p.stdout), 0.0
    if engine == "ollama":
        return _ollama(prompt, model)
    if engine == "openai":
        return _openai(prompt, model)
    if engine == "api":
        return _api(prompt, model)
    p = subprocess.run(["claude", "-p", prompt, "--model", model, "--output-format", "json"],
                       capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError(f"claude -p : {(p.stderr or p.stdout or '').strip()[-300:]}")
    try:
        d = json.loads(p.stdout)
    except ValueError:
        return _json_tableau(p.stdout), 0.0
    return _json_tableau(d.get("result", "")), float(d.get("total_cost_usd") or 0.0)


def _ollama(prompt: str, model: str) -> tuple:
    """Ollama, local ou hébergé (RM3067). Coût nul : c'est l'abonnement ou la machine. `format: json`
    contraint la sortie, ce que les petits modèles rendent volontiers bavarde autrement."""
    import urllib.request
    host = (os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    if not host.startswith("http"):
        host = "https://" + host
    if model == MODEL:                      # le défaut Anthropic n'a pas de sens ici
        model = os.environ.get("OLLAMA_MODEL") or "qwen3:8b"
    body = json.dumps({"model": model, "stream": False, "format": "json", "options": {"temperature": 0},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    headers = {"content-type": "application/json"}
    if os.environ.get("OLLAMA_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["OLLAMA_API_KEY"]
    req = urllib.request.Request(host + "/api/chat", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read().decode())
    texte = ((d.get("message") or {}).get("content") or "") if isinstance(d, dict) else ""
    items = _json_tableau(texte)
    if not items and texte.strip().startswith("{"):     # `format: json` rend parfois un objet enveloppe
        try:
            o = json.loads(texte)
            for v in (o.values() if isinstance(o, dict) else []):
                if isinstance(v, list):
                    items = [x for x in v if isinstance(x, dict)]; break
        except ValueError:
            pass
    return items, 0.0


def _openai(prompt: str, model: str) -> tuple:
    """Tout serveur parlant l'API OpenAI (RM3067) : Lemonade Server (Ryzen AI), vLLM, LM Studio, llama.cpp.
    `response_format: json_object` quand le serveur le sait ; sinon le parseur tolérant fait le reste."""
    import urllib.request
    base = (os.environ.get("LLM_BASE_URL") or "http://localhost:8000/api/v1").rstrip("/")
    if model == MODEL:
        model = os.environ.get("LLM_MODEL") or "qwen3-8b"
    body = json.dumps({"model": model, "temperature": 0, "max_tokens": 2000,
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    headers = {"content-type": "application/json"}
    if os.environ.get("LLM_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["LLM_API_KEY"]
    req = urllib.request.Request(base + "/chat/completions", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read().decode())
    texte = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    items = _json_tableau(texte)
    if not items and texte.strip().startswith("{"):
        try:
            o = json.loads(texte)
            for v in (o.values() if isinstance(o, dict) else []):
                if isinstance(v, list):
                    items = [x for x in v if isinstance(x, dict)]; break
        except ValueError:
            pass
    return items, 0.0


def _api(prompt: str, model: str) -> tuple:
    import urllib.request
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY absente (ou --engine claude)")
    body = json.dumps({"model": model, "max_tokens": 2000, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read().decode())
    u = d.get("usage") or {}
    cout = (u.get("input_tokens", 0) / 1e6) * 1.0 + (u.get("output_tokens", 0) / 1e6) * 5.0
    return _json_tableau("".join(b.get("text", "") for b in d.get("content", []))), cout


def classe(lot, model=MODEL, engine="claude") -> tuple:
    """[(role, texte, type, reformulation)] pour ce qui n'est pas « rien », et le coût."""
    items, cout = appelle(prompt_lot(lot), model, engine)
    out = []
    for it in items:
        try:
            i = int(it.get("i"))
        except (TypeError, ValueError):
            continue
        t = str(it.get("t") or "").strip().lower()
        if t not in TYPES or t == "rien" or not (0 <= i < len(lot)):
            continue
        x = " ".join(str(it.get("x") or lot[i][1]).split())
        if len(x) < 25:
            continue
        out.append((lot[i][0], lot[i][1], t, x))
    return out, cout


#: type d'instance du registre → moteur du classifieur
TYPE_MOTEUR = {"lemonade": "openai", "openai": "openai", "vllm": "openai", "lmstudio": "openai",
               "ollama": "ollama", "anthropic": "api", "claude-cli": "claude"}


def moteur_du_registre(project=None):
    """(engine, model) depuis l'axe `llm` du registre des providers (RM3067), ou (None, None).

    C'est là que se déclare le modèle de travail de karl — local d'abord — avec surcharge par client et
    par projet, comme les autres axes. Les variables d'environnement priment encore : elles servent à
    essayer un modèle sans toucher la conf."""
    try:
        import yaml
        from pm_registry import Registry
        from pm_paths import PMConfig as _C
        cfg = _C.load()
        prov = (yaml.safe_load((Path(cfg.pm_dir) / "pm.config.yml").read_text(encoding="utf-8")) or {}).get("providers") or {}
        reg = Registry.from_config(prov)
        nom = reg.defaults.get("llm")
        inst = reg.get(nom) if nom else next(iter(reg.by_axis("llm")), None)
        if inst is None:
            return None, None
        eng = TYPE_MOTEUR.get(str(inst.type or "").lower())
        if not eng:
            return None, None
        if inst.url:
            os.environ.setdefault("LLM_BASE_URL" if eng == "openai" else "OLLAMA_HOST", str(inst.url))
        return eng, (inst.options or {}).get("model")
    except Exception:
        return None, None


def transcript_de(sid):
    return next((p for root in CLAUDE_STORES for p in root.glob(f"*/{sid}.jsonl")), None) if sid else None


def ecrit(rm_id, retenus, sid=None, cfg=None) -> int:
    cfg = cfg or PMConfig.load()
    sheet = cfg.find_task(int(rm_id))
    if not sheet:
        return 0
    think = pm_think.think_path(sheet)
    n = 0
    for role, _brut, t, x in retenus:
        kind = KIND[t]
        if pm_think.has_text(pm_think.load(think), kind, x):
            continue
        pm_think.append(think, kind, x, rm_id=int(rm_id), by=("M" if role == "M" else "A"),
                        state=("valide" if t == "decision" else "attente"), sid=sid)
        n += 1
    if n:
        pm_think.set_counters(sheet, pm_think.counters(pm_think.load(think)))
        pm_git.autocommit([think, sheet], f"pm(think): RM{rm_id} +{n} entrée(s) classées (RM3067)")
    return n


def passe(tp: Path, rm_id, a) -> dict:
    lignes = open(tp, encoding="utf-8", errors="replace").readlines()
    ts = tours(lignes)
    retenus, cout = [], 0.0
    for k in range(0, len(ts), a.batch):
        r, c = classe(ts[k:k + a.batch], a.model, a.engine)
        # les index sont relatifs au lot : on a déjà les tours, rien à recaler
        retenus += r; cout += c
    ecrites = ecrit(rm_id, retenus, sid=tp.stem) if (a.apply and rm_id) else 0
    return {"transcript": tp.name, "tours": len(ts), "retenus": len(retenus), "ecrites": ecrites,
            "cout_usd": round(cout, 4), "items": retenus}


_Q_LIGNE = re.compile(r"^\|\s*(Q\d{3})\s*\|\s*(.*?)\s*\|[^|]*\|[^|]*\|\s*(\S+)\s*\|\s*$")


def audit_questions(racine=None) -> list:
    """RM3141 — les questions OUVERTES qui n'en sont pas, d'après le critère courant.

    Six captures accidentelles en une journée ont bloqué autant de clôtures : un message de séance,
    un résumé de compaction, une liste de consignes. Corriger le critère empêche les suivantes ; il
    reste à voir celles qui dorment déjà dans les fiches. Cet audit LIT et signale — il ne réécrit
    rien : une question mal classée se tranche à la main, avec sa réponse, pas par un script."""
    base = pathlib.Path(racine) if racine else None
    if base is None:
        try:
            from pm_paths import PMConfig
            base = pathlib.Path(PMConfig.load().projects_root)
        except Exception:      # noqa: BLE001
            # Depuis un worktree de dev, la config PM ne se charge pas : le `.mmi-pm` du repo courant
            # est alors la bonne racine. Sans ce repli, l'audit rendait « 0 suspecte » — un zéro faux
            # est pire qu'une erreur, parce qu'on le croit.
            local = None
            for cand in [pathlib.Path(__file__).resolve().parent.parent] + list(
                    pathlib.Path(__file__).resolve().parents):
                if (cand / ".mmi-pm").exists():
                    local = cand / ".mmi-pm"
                    break
                if (cand / "projects" / "clients").is_dir():
                    local = cand / "projects"
                    break
            if local is None:
                return []
            base = local
    out = []
    for f in sorted(base.rglob("*.think.md")):
        try:
            lignes = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for l in lignes:
            m = _Q_LIGNE.match(l)
            if not m or "🕐" not in m.group(3):
                continue
            qid, texte = m.group(1), m.group(2)
            if type_heuristique("M", texte) == "question":
                continue
            # Le MOTIF, parce qu'ils n'ont pas la même force : un artefact de session ou un ordre
            # reconnu est une capture certaine ; « plusieurs lignes » est un doute, et une vraie
            # question longue existe. Un audit qui crierait au loup ne serait pas relu.
            brut = texte
            motif = ("artefact de session" if _ARTEFACT.search(brut)
                     else "commence par un ordre" if _ORDRE.match(brut)
                     else "plusieurs demandes" if len([l for l in brut.splitlines() if l.strip()]) > 2
                     else "rien d'interrogatif")
            out.append({"fiche": f.name, "id": qid, "texte": texte[:160],
                        "taille": len(texte), "motif": motif,
                        "certain": motif in ("artefact de session", "commence par un ordre")})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audit-questions", action="store_true",
                    help="RM3141 : lister les questions ouvertes que le critère courant ne tiendrait PAS pour des questions")
    ap.add_argument("--transcript"); ap.add_argument("--session"); ap.add_argument("--rm", type=int)
    ap.add_argument("--all", action="store_true"); ap.add_argument("--since"); ap.add_argument("--limit", type=int)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--model", default=MODEL)
    ap.add_argument("--batch", type=int, default=BATCH); ap.add_argument("--engine", choices=("claude", "api", "ollama", "openai"),
                    default=("openai" if os.environ.get("LLM_BASE_URL")
                             else "ollama" if (os.environ.get("OLLAMA_HOST") or os.environ.get("OLLAMA_API_KEY"))
                             else "api" if os.environ.get("ANTHROPIC_API_KEY") else "claude"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.audit_questions:
        susp = audit_questions()
        if a.json:
            print(json.dumps({"suspectes": susp, "total": len(susp)}, ensure_ascii=False, indent=1))
            return 0
        for x in susp:
            print(f"  {'✗' if x['certain'] else '?'} {x['fiche'].split('_')[0]:<8} {x['id']}  "
                  f"{x['motif']:<22} {x['texte'][:70]}")
        certains = sum(1 for x in susp if x["certain"])
        print(f"\n  {len(susp)} question(s) ouverte(s) à revoir — dont {certains} capture(s) certaine(s) (✗)."
              + ("\n  Chacune se tranche à la main : `mmi-pm task-think <rm> --set <id> --state invalide --note \"…\"`."
                 if susp else ""))
        return 0

    if not (os.environ.get("LLM_BASE_URL") or os.environ.get("OLLAMA_HOST") or os.environ.get("OLLAMA_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY") or "--engine" in sys.argv):
        eng, mod = moteur_du_registre()            # RM3067 : le modèle de travail vient du registre des providers
        if eng:
            a.engine = eng
            if mod and a.model == MODEL:
                a.model = mod

    cibles = []
    if a.transcript:
        cibles = [Path(a.transcript)]
    elif a.session:
        tp = transcript_de(a.session)
        if not tp:
            sys.exit(f"transcript introuvable pour la session {a.session}")
        cibles = [tp]
    elif a.all:
        seuil = datetime.strptime(a.since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() if a.since else 0
        cibles = sorted((p for root in CLAUDE_STORES for p in root.glob("*/[0-9a-f]*.jsonl") if p.stat().st_mtime >= seuil),
                        key=lambda p: p.stat().st_mtime, reverse=True)[:a.limit or None]
    else:
        ap.print_help(); sys.exit(2)

    total = {"tours": 0, "retenus": 0, "ecrites": 0, "cout_usd": 0.0}
    rapports = []
    for tp in cibles:
        try:
            r = passe(tp, a.rm, a)
        except (OSError, RuntimeError) as e:
            print(f"✗ {tp.name} : {e}", file=sys.stderr); continue
        rapports.append(r)
        for k in ("tours", "retenus", "ecrites"):
            total[k] += r[k]
        total["cout_usd"] = round(total["cout_usd"] + r["cout_usd"], 4)
        if not a.json:
            print(f"── {tp.name} — {r['tours']} tours, {r['retenus']} retenu(s)"
                  + (f", {r['ecrites']} écrite(s)" if a.apply else "") + f", {r['cout_usd']} $")
            for role, _b, t, x in r["items"]:
                print(f"   [{t:8}] {role} · {x[:150]}")
    if a.json:
        print(json.dumps({"total": total, "rapports": rapports}, ensure_ascii=False, indent=1))
    else:
        print(f"\n{len(cibles)} transcript(s) · {total['tours']} tours · {total['retenus']} retenu(s)"
              + (f" · {total['ecrites']} écrite(s)" if a.apply else " · (rapport seul, --apply pour écrire)")
              + f" · {total['cout_usd']} $")
    return 0


if __name__ == "__main__":
    sys.exit(main())
