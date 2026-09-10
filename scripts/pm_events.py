"""pm_events — prévenir le cockpit qu'une donnée a changé (RM3006).

Un script PM qui écrit quelque chose que le cockpit affiche (statut d'un ticket, note,
worklog de session, relève mail) PUBLIE un sujet sur karl-agent :
`POST /api/session/events/publish {"topics": [...], "source": "<script>"}`. Le service
réveille ses canaux SSE et pousse aux cockpits connectés les blocs de /refresh qui ont
changé, sans attendre le tick. Pas de veilleur de fichiers : c'est l'écriture qui parle.

BEST-EFFORT, JAMAIS BLOQUANT : karl-agent absent, port fermé, jeton refusé → on note en
`debug` dans le journal (pm_log, catégorie refresh) et on continue. Délai borné (0,6 s).
`PM_EVENTS_DISABLE=1` coupe la publication (tests, batchs).

Sujets connus (contrat avec karl-agent.EVENT_TOPICS) :
    tickets, sessions, pending, worklog, dashboard, mail, env, sets

Usage :
    import pm_events
    pm_events.publish(["tickets", "worklog"], source="pm-task-status-update", rm_id=rm_id)
"""
import json
import os
import urllib.error
import urllib.request

TOPICS = ("tickets", "sessions", "pending", "worklog", "dashboard", "mail", "env", "sets")
TIMEOUT_S = 0.6


def endpoint() -> str:
    host = os.environ.get("KARL_AGENT_HOST", "127.0.0.1")
    port = os.environ.get("KARL_AGENT_PORT", "9876")
    return f"http://{host}:{port}/api/session/events/publish"


def _journal(level: str, msg: str, **fields) -> None:
    try:
        import pm_log
        pm_log.log("refresh", level, msg, echo=False, **fields)
    except Exception:  # noqa: BLE001
        pass


def publish(topics, source: str | None = None, timeout: float = TIMEOUT_S, **fields) -> bool:
    """Rend True si karl-agent a accusé réception. Silencieux (journal debug) sinon."""
    if os.environ.get("PM_EVENTS_DISABLE") == "1":
        return False
    topics = [t for t in (topics or []) if t in TOPICS]
    if not topics:
        return False
    body = {"topics": topics, "source": source}
    body.update({k: v for k, v in fields.items() if v is not None})
    req = urllib.request.Request(endpoint(), data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    tok = os.environ.get("KARL_AGENT_TOKEN")
    if tok:
        req.add_header("X-Karl-Token", tok)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — loopback
            ok = 200 <= r.status < 300
        _journal("debug", "événement publié au cockpit", topics=topics, source=source)
        return ok
    except urllib.error.HTTPError as e:
        _journal("debug", "publication refusée par karl-agent", status=e.code, topics=topics, source=source)
    except (urllib.error.URLError, OSError, ValueError) as e:
        _journal("debug", "karl-agent injoignable — pas de push (le tick suffira)", why=str(e)[:120], topics=topics, source=source)
    return False
