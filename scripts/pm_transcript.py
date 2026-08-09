"""pm_transcript — lecture typée d'un transcript claude (JSONL). RM2305.

Source UNIQUE du typage questions/réponses introduit par RM2549. Le cockpit
(`karl-agent.py`) et les scripts PM en ont tous deux besoin : dupliquer la
logique produirait deux vérités sur « cette question a-t-elle été tranchée ».

Stdlib seulement — `karl-agent.py` est un serveur sans dépendances.
"""
import json
import re

# RM2549 : outils par lesquels l'agent interpelle EXPLICITEMENT l'utilisateur.
# Liste fermée, volontairement : une question est un fait déclaré par l'agent,
# jamais une devinette sur de la prose (« on dirait qu'il demande un avis »).
QUESTION_TOOLS = ("AskUserQuestion", "ExitPlanMode")
# Un tool_result existe, mais il ne porte AUCUN choix : la question est restée
# sans réponse (interruption, refus). À distinguer d'une question répondue.
NO_ANSWER_MARKERS = ("[Request interrupted by user",
                      "The user doesn't want to proceed",
                      "The user doesn't want to take this action")
# « "Quelle option ?"="Barre permanente" selected preview:… » → le choix retenu.
ANSWER_PAIR_RE = re.compile(r'"[^"]*"="([^"]*)"')


def content_text(content) -> str:
    """Texte d'un `content` (message ou tool_result) : chaîne, ou blocs texte."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def question_parts(name: str, inp) -> tuple:
    """RM2549 : (aperçu, détail) d'une question posée à l'utilisateur."""
    inp = inp if isinstance(inp, dict) else {}
    if name == "ExitPlanMode":
        return "Plan proposé — validation demandée", str(inp.get("plan") or "")
    questions = [q for q in (inp.get("questions") or []) if isinstance(q, dict)]
    apercu = " / ".join(str(q.get("question") or "").strip() for q in questions)
    detail = []
    for q in questions:
        detail.append(str(q.get("question") or "").strip())
        for opt in (q.get("options") or []):
            if isinstance(opt, dict):
                detail.append("  - " + str(opt.get("label") or "").strip())
    return apercu, "\n".join(detail)


def answer_parts(text: str):
    """RM2549 : (aperçu de la réponse retenue, détail), ou None si la question
    est restée sans réponse — l'utilisateur a interrompu ou refusé."""
    if not text or any(m in text for m in NO_ANSWER_MARKERS):
        return None
    choix = [c.strip() for c in ANSWER_PAIR_RE.findall(text) if c.strip()]
    apercu = " / ".join(choix) if choix else " ".join(text.split())
    return apercu, text


def transcript_outline(lines, max_items: int = 400) -> list:
    """RM2330 : items de conversation depuis un transcript claude (JSONL).
    Source de référence pour les sessions claude : leur TUI tourne en écran
    alterné (history tmux VIDE — vérifié : alternate_on=1, history_size=0),
    le scrollback ne contient donc PAS la conversation.

    Un item = un message user|assistant, ou (RM2549) une `question` posée à
    l'utilisateur / la `answer` retenue — jusqu'ici jetées avec le reste des
    tool_use/tool_result alors que c'est là que se joue « où en est-on ».
    Une question sans tool_result, ou dont le résultat ne porte aucun choix,
    reste `resolved: False`.
    {n, kind, text (aperçu), full (lecture), resolved, answer} — pure."""
    items = []
    pending = {}                    # tool_use_id → item question sans réponse
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = obj.get("type")
        if kind not in ("user", "assistant") or obj.get("isMeta"):
            continue
        content = (obj.get("message") or {}).get("content")
        if not isinstance(content, (str, list)):
            continue
        # enveloppes techniques (<command-name>, <local-command-stdout>,
        # <system-reminder>…) : pas des messages de conversation
        text = content_text(content).strip()
        if text and not text.startswith("<"):
            items.append({"n": len(items), "kind": kind, "resolved": None, "answer": None,
                          "text": " ".join(text.split())[:120], "full": text[:4000]})
        # le texte d'un message précède toujours ses appels d'outil : l'ordre
        # chronologique de l'outline est conservé en traitant les blocs après.
        for b in (content if isinstance(content, list) else []):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") in QUESTION_TOOLS:
                apercu, detail = question_parts(b.get("name"), b.get("input"))
                item = {"n": len(items), "kind": "question", "resolved": False,
                        "answer": None, "text": " ".join(apercu.split())[:120] or "(question)",
                        "full": detail[:4000]}
                pending[b.get("id")] = item
                items.append(item)
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                question = pending.pop(b.get("tool_use_id"))
                reponse = answer_parts(content_text(b.get("content")))
                if reponse is None:
                    continue                # question laissée sans réponse
                apercu, detail = reponse
                question["resolved"] = True
                question["answer"] = apercu[:120]
                items.append({"n": len(items), "kind": "answer", "resolved": True,
                              "answer": None, "text": apercu[:120] or "(réponse)",
                              "full": detail[:4000]})
    if len(items) > max_items:
        items = items[-max_items:]
    return items


