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


def usage_by_message(items) -> dict:
    """Usages d'un transcript, dédupliqués par `message.id` (RM2628).

    Une même réponse API est écrite dans le JSONL **une fois par bloc de
    contenu** (thinking, texte, chaque tool_use) et chaque ligne porte l'usage
    COMPLET de la réponse : sommer les lignes multiplie la consommation par le
    nombre de blocs (facteur mesuré ≈ 2,3 sur une session d'agent). On garde
    donc le dernier usage vu par id — ce qui traite du même coup les retries
    API, qui réémettent le même `message.id`.

    Source unique de la règle : `karl-agent` (vue cockpit) et `pm-task-tick`
    (métriques des tickets) doivent compter pareil, sinon les deux vues
    divergent sur la conso d'une même session.

    `items` : itérable de `(clé_de_repli, message)` — la clé sert quand le
    message n'a pas d'`id` (lignes synthétiques). Retourne
    `{id → (usage, model)}` dans l'ordre d'apparition (dict ordonné) : le
    dernier élément est donc le dernier tour du transcript.
    """
    per_msg = {}
    for key, msg in items:
        if not isinstance(msg, dict):
            continue
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        per_msg[msg.get("id") or key] = (usage, msg.get("model"))
    return per_msg


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


def _ktok(n) -> str:
    """923287 → « 923 k » ; < 1000 → tel quel ; non numérique → « ? »."""
    if not isinstance(n, (int, float)) or isinstance(n, bool):
        return "?"
    return "%d k" % round(n / 1000) if n >= 1000 else str(int(n))


def _compact_texts(meta) -> tuple:
    """RM3620 : (aperçu, lecture) d'une compaction depuis `compactMetadata`."""
    meta = meta if isinstance(meta, dict) else {}
    mode = {"manual": "manuel", "auto": "auto"}.get(meta.get("trigger"))
    detail = []
    if mode:
        detail.append(mode)
    if "preTokens" in meta or "postTokens" in meta:
        detail.append("%s → %s tokens" % (_ktok(meta.get("preTokens")), _ktok(meta.get("postTokens"))))
    text = "Conversation compactée" + (" (%s)" % ", ".join(detail) if detail else "")
    ms = meta.get("durationMs")
    if isinstance(ms, (int, float)) and not isinstance(ms, bool):
        return text, "%s, durée %d s" % (text, round(ms / 1000))
    return text, text


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
    RM3620 : chaque item porte `ts` (horodatage ISO de la ligne JSONL, None si
    absent) ; un `compact_boundary` (type system) devient un item `compact`.
    {n, kind, text (aperçu), full (lecture), resolved, answer, ts} — pure."""
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
        ts = obj.get("timestamp") if isinstance(obj.get("timestamp"), str) else None
        if kind == "system" and obj.get("subtype") == "compact_boundary":
            text, full = _compact_texts(obj.get("compactMetadata"))
            items.append({"n": len(items), "kind": "compact", "resolved": None,
                          "answer": None, "text": text, "full": full, "ts": ts})
            continue
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
                          "text": " ".join(text.split())[:120], "full": text[:4000],
                          "ts": ts})
        # le texte d'un message précède toujours ses appels d'outil : l'ordre
        # chronologique de l'outline est conservé en traitant les blocs après.
        for b in (content if isinstance(content, list) else []):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") in QUESTION_TOOLS:
                apercu, detail = question_parts(b.get("name"), b.get("input"))
                item = {"n": len(items), "kind": "question", "resolved": False,
                        "answer": None, "text": " ".join(apercu.split())[:120] or "(question)",
                        "full": detail[:4000], "ts": ts}
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
                              "full": detail[:4000], "ts": ts})
    if len(items) > max_items:
        items = items[-max_items:]
    return items


