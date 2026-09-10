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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transcript"); ap.add_argument("--session"); ap.add_argument("--rm", type=int)
    ap.add_argument("--all", action="store_true"); ap.add_argument("--since"); ap.add_argument("--limit", type=int)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--model", default=MODEL)
    ap.add_argument("--batch", type=int, default=BATCH); ap.add_argument("--engine", choices=("claude", "api", "ollama", "openai"),
                    default=("openai" if os.environ.get("LLM_BASE_URL")
                             else "ollama" if (os.environ.get("OLLAMA_HOST") or os.environ.get("OLLAMA_API_KEY"))
                             else "api" if os.environ.get("ANTHROPIC_API_KEY") else "claude"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
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
