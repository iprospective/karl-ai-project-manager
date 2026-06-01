#!/usr/bin/env python3
"""karl-telegram-bot — Bot Telegram « standardiste » de karl-pm (épic A, RM1724).

V0 d'essai (sous-tickets RM1772/RM1774) : long-polling + commandes info one-shot.
Le bot ne raisonne pas — il route Telegram ↔ Redmine REST.

Commandes :
    /rm <id>     état courant d'un ticket (status, priorité, assigné, dernier journal)
    /help        aide
    /status      état du bot
    /whoami      renvoie ton telegram_user_id (utile pour la whitelist)

Sécurité : whitelist d'IDs Telegram (TELEGRAM_WHITELIST, csv). Si vide → mode
découverte : le bot répond mais logge chaque sender_id (pour te whitelister).
Un user hors whitelist reçoit un refus poli.

Config (lue depuis .env à la racine du repo, ou env du shell) :
    TELEGRAM_BOT_TOKEN     token @BotFather (jamais loggué)
    TELEGRAM_WHITELIST     csv d'IDs autorisés (ex: "123456,789012") — optionnel
    REDMINE_URL / REDMINE_USER_MAIN_API_KEY   accès Redmine (déjà présents)

Usage :
    python3 scripts/karl-telegram-bot.py
"""
import html
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from redmine_utils import fetch_issue

REPO_ROOT = Path(__file__).resolve().parent.parent
TG_API = "https://api.telegram.org/bot{token}/{method}"


def load_dotenv():
    """Charge .env (KEY=VALUE) dans os.environ sans écraser l'existant."""
    env = REPO_ROOT / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def tg(token, method, **params):
    r = requests.post(TG_API.format(token=token, method=method), json=params, timeout=40)
    r.raise_for_status()
    return r.json()


def send(token, chat_id, text):
    tg(token, "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
       disable_web_page_preview=True)


def fmt_ticket(rm_id):
    """Construit la réponse HTML pour /rm <id>."""
    issue = fetch_issue(rm_id, include="journals")
    if not issue:
        return f"RM{rm_id} introuvable."
    subj = html.escape(issue.get("subject", "?"))
    status = (issue.get("status") or {}).get("name", "?")
    prio = (issue.get("priority") or {}).get("name", "?")
    assignee = (issue.get("assigned_to") or {}).get("name", "—")
    done = issue.get("done_ratio", 0)
    # Dernier journal porteur d'une note
    last_note = None
    for j in reversed(issue.get("journals") or []):
        note = (j.get("notes") or "").strip()
        if note:
            who = (j.get("user") or {}).get("name", "?")
            when = (j.get("created_on") or "")[:16].replace("T", " ")
            snippet = note if len(note) <= 400 else note[:400] + "…"
            last_note = f"\n\n<b>Dernier journal</b> ({html.escape(who)}, {when}):\n{html.escape(snippet)}"
            break
    return (f"<b>RM{rm_id}</b> — {subj}\n"
            f"• Statut : <b>{html.escape(status)}</b>\n"
            f"• Priorité : {html.escape(prio)}\n"
            f"• Assigné : {html.escape(assignee)}\n"
            f"• Avancement : {done}%"
            f"{last_note or ''}")


HELP = ("<b>karl-pm</b> — commandes :\n"
        "/rm &lt;id&gt; — état d'un ticket\n"
        "/status — état du bot\n"
        "/whoami — ton ID Telegram\n"
        "/help — cette aide")


def handle(token, whitelist, msg):
    chat_id = msg["chat"]["id"]
    user = msg.get("from") or {}
    uid = user.get("id")
    text = (msg.get("text") or "").strip()
    uname = user.get("username") or user.get("first_name") or "?"

    # /whoami répond toujours (sert à se whitelister)
    if text.startswith("/whoami"):
        send(token, chat_id, f"Ton telegram_user_id : <code>{uid}</code>\nchat_id : <code>{chat_id}</code>")
        return

    # Sécurité
    if whitelist and uid not in whitelist:
        print(f"  ⨯ refus : uid={uid} (@{uname}) hors whitelist — text={text!r}")
        send(token, chat_id, "Désolé, tu n'es pas autorisé à interroger karl-pm. "
                             "Demande à Mathieu de t'ajouter (ton ID : /whoami).")
        return
    if not whitelist:
        print(f"  ⚠ mode découverte : message de uid={uid} (@{uname}) — "
              f"ajoute-le à TELEGRAM_WHITELIST pour verrouiller")

    if text.startswith("/rm"):
        parts = text.split()
        if len(parts) < 2 or not parts[1].lstrip("#").isdigit():
            send(token, chat_id, "Usage : <code>/rm 1724</code>")
            return
        rm_id = int(parts[1].lstrip("#"))
        try:
            send(token, chat_id, fmt_ticket(rm_id))
        except SystemExit as e:
            send(token, chat_id, f"Erreur Redmine pour RM{rm_id} : {e}")
        except Exception as e:
            send(token, chat_id, f"Erreur : {e}")
    elif text.startswith(("/help", "/start")):
        send(token, chat_id, HELP)
    elif text.startswith("/status"):
        send(token, chat_id, "✅ karl-pm en ligne (v0 essai). Commandes : /help")
    else:
        send(token, chat_id, "Commande inconnue. /help pour la liste.")


def main():
    load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("ERREUR : TELEGRAM_BOT_TOKEN absent (.env ou env). "
                 "Crée le bot via @BotFather puis ajoute la ligne dans .env.")
    wl_raw = os.environ.get("TELEGRAM_WHITELIST", "")
    whitelist = {int(x) for x in wl_raw.replace(" ", "").split(",") if x.strip().isdigit()}

    me = tg(token, "getMe")["result"]
    print(f"✓ Bot connecté : @{me.get('username')} ({me.get('first_name')})")
    print(f"  Whitelist : {whitelist or 'VIDE (mode découverte)'}")
    print("  Long-polling… (Ctrl-C pour arrêter)")

    offset = None
    while True:
        try:
            resp = tg(token, "getUpdates", offset=offset, timeout=30)
        except requests.RequestException as e:
            print(f"  ⚠ getUpdates erreur réseau : {e} — retry dans 3s")
            time.sleep(3)
            continue
        for upd in resp.get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message") or upd.get("edited_message")
            if not msg or "text" not in msg:
                continue
            print(f"  → update {upd['update_id']} : {msg['text']!r}")
            try:
                handle(token, whitelist, msg)
            except Exception as e:
                print(f"  ⚠ handler erreur : {e}")


if __name__ == "__main__":
    main()
