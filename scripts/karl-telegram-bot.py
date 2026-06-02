#!/usr/bin/env python3
"""karl-telegram-bot — Bot Telegram « standardiste » de karl-pm (épic A, RM1724).

Long-polling + commandes info one-shot. Le bot ne raisonne pas — il route
Telegram ↔ Redmine REST. Couche de sécurité à deux facteurs :

  1. **Whitelist** d'IDs Telegram (TELEGRAM_WHITELIST) — qui peut parler au bot.
  2. **Verrouillage applicatif** (mot de passe) — protège même si le téléphone
     est volé déverrouillé. Verrouillé par défaut, auto-lock après inactivité,
     anti-brute-force. Cf. RM1777.

Commandes (déverrouillé) :
    /rm <id>        état d'un ticket (status, priorité, assigné, dernier journal)
    /mine           tickets en cours assignés à karl
    /recent         derniers tickets modifiés
    /search <texte> recherche plein-texte
    /note <id> <t>  ajoute une note au ticket (+ append .log.md local)
    /status         état du bot (uptime, verrou)

Commandes (toujours dispo) :
    /unlock <mdp>   déverrouille la session (le message est effacé après coup)
    /lock           verrouille immédiatement
    /help           aide
    /whoami         ton telegram_user_id (pour la whitelist)

Config (.env à la racine du repo, ou env shell) :
    TELEGRAM_BOT_TOKEN            token @BotFather (jamais loggué)
    TELEGRAM_WHITELIST           csv d'IDs autorisés (ex: "123456,789012")
    TELEGRAM_LOCK_PASSWORD_HASH  empreinte PBKDF2 du mdp (cf. --hash-password)
    REDMINE_URL / REDMINE_USER_MAIN_API_KEY   accès Redmine

Outillage :
    python3 scripts/karl-telegram-bot.py                  lance le bot
    python3 scripts/karl-telegram-bot.py --hash-password  génère l'empreinte mdp
"""
import getpass
import hashlib
import hmac
import html
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from redmine_utils import (add_issue_note, fetch_issue, get_ia_cf_id,
                           list_issues, search_issues)
from pm_paths import PMConfig

TG_API = "https://api.telegram.org/bot{token}/{method}"

AUTO_LOCK_SECONDS = 300   # 5 min d'inactivité → re-verrouillage
FAIL_THRESHOLD = 3        # nb d'échecs /unlock avant blocage
LOCKOUT_SECONDS = 300     # durée du blocage après FAIL_THRESHOLD échecs
PBKDF2_ITERATIONS = 200_000


# ─────────────────────────────── Mot de passe ───────────────────────────────

def hash_password(password):
    """Empreinte PBKDF2-SHA256 salée, format `pbkdf2_sha256$iters$salt$hash`."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password, stored):
    """Vérifie un mdp contre l'empreinte stockée (comparaison à temps constant)."""
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk, bytes.fromhex(hash_hex))
    except Exception:
        return False


# ──────────────────────────────── Verrouillage ──────────────────────────────

class Lock:
    """Gère l'état verrouillé/déverrouillé par chat + l'anti-brute-force.

    En mémoire uniquement → un redémarrage du bot re-verrouille tout (fail-secure).
    Désactivé (tout passe) si aucune empreinte n'est configurée — uniquement pour
    la phase de setup ; configure TELEGRAM_LOCK_PASSWORD_HASH pour activer.
    """

    def __init__(self, password_hash):
        self.hash = password_hash or None
        self._unlocked = {}   # chat_id -> dernier_activité_ts
        self._fails = {}      # chat_id -> {"count": int, "until": ts}

    @property
    def enabled(self):
        return self.hash is not None

    def is_unlocked(self, chat_id, now):
        if not self.enabled:
            return True
        last = self._unlocked.get(chat_id)
        if last is None:
            return False
        if now - last > AUTO_LOCK_SECONDS:
            self._unlocked.pop(chat_id, None)
            return False
        return True

    def touch(self, chat_id, now):
        """Rafraîchit le minuteur d'inactivité après une commande légitime."""
        if self.enabled and chat_id in self._unlocked:
            self._unlocked[chat_id] = now

    def lock(self, chat_id):
        self._unlocked.pop(chat_id, None)

    def attempt_unlock(self, chat_id, password, now):
        """Tente un déverrouillage. Retourne (statut, info) :
        ('ok', None) | ('lockout', secondes_restantes) |
        ('locked_now', LOCKOUT_SECONDS) | ('fail', essais_restants)."""
        f = self._fails.get(chat_id)
        if f and f["until"] > now:
            return ("lockout", int(f["until"] - now))
        if verify_password(password, self.hash):
            self._unlocked[chat_id] = now
            self._fails.pop(chat_id, None)
            return ("ok", None)
        count = (f["count"] if f else 0) + 1
        if count >= FAIL_THRESHOLD:
            self._fails[chat_id] = {"count": 0, "until": now + LOCKOUT_SECONDS}
            return ("locked_now", LOCKOUT_SECONDS)
        self._fails[chat_id] = {"count": count, "until": 0}
        return ("fail", FAIL_THRESHOLD - count)


# ───────────────────────────────── Telegram I/O ─────────────────────────────

def tg(token, method, **params):
    r = requests.post(TG_API.format(token=token, method=method), json=params, timeout=40)
    r.raise_for_status()
    return r.json()


def send(token, chat_id, text):
    tg(token, "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
       disable_web_page_preview=True)


def delete_message(token, chat_id, message_id):
    """Best-effort : efface un message (scrub le mdp du /unlock de l'historique)."""
    try:
        tg(token, "deleteMessage", chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


# ──────────────────────────── Formatage Redmine ─────────────────────────────

def _trunc(s, n):
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def fmt_ticket(rm_id):
    """Réponse HTML détaillée pour /rm <id>."""
    issue = fetch_issue(rm_id, include="journals")
    if not issue:
        return f"RM{rm_id} introuvable."
    subj = html.escape(issue.get("subject", "?"))
    status = (issue.get("status") or {}).get("name", "?")
    prio = (issue.get("priority") or {}).get("name", "?")
    assignee = (issue.get("assigned_to") or {}).get("name", "—")
    done = issue.get("done_ratio", 0)
    last_note = None
    for j in reversed(issue.get("journals") or []):
        note = (j.get("notes") or "").strip()
        if note:
            who = (j.get("user") or {}).get("name", "?")
            when = (j.get("created_on") or "")[:16].replace("T", " ")
            last_note = (f"\n\n<b>Dernier journal</b> ({html.escape(who)}, {when}):\n"
                         f"{html.escape(_trunc(note, 400))}")
            break
    return (f"<b>RM{rm_id}</b> — {subj}\n"
            f"• Statut : <b>{html.escape(status)}</b>\n"
            f"• Priorité : {html.escape(prio)}\n"
            f"• Assigné : {html.escape(assignee)}\n"
            f"• Avancement : {done}%"
            f"{last_note or ''}")


def _ia_filter():
    """Filtre custom-field IA pour /issues.json (dict vide si non configuré)."""
    cf = get_ia_cf_id()
    return {f"cf_{cf}": "IA"} if cf is not None else {}


def _fmt_issue_line(issue):
    rm = issue.get("id")
    subj = html.escape(_trunc(issue.get("subject", "?"), 60))
    status = html.escape((issue.get("status") or {}).get("name", "?"))
    prio = html.escape((issue.get("priority") or {}).get("name", "?"))
    return f"• <b>RM{rm}</b> [{status}] {subj} <i>({prio})</i>"


def fmt_mine():
    """Tickets ouverts assignés à karl (l'owner de la clé API), récents d'abord."""
    params = {"assigned_to_id": "me", "status_id": "open",
              "sort": "updated_on:desc", **_ia_filter()}
    issues = list_issues(params, limit=15)
    if not issues:
        return "Aucun ticket en cours assigné à karl. 🎉"
    lines = "\n".join(_fmt_issue_line(i) for i in issues)
    return f"<b>Tickets en cours (karl)</b> — {len(issues)} :\n{lines}"


def fmt_recent():
    """Derniers tickets modifiés (tous statuts), IA-trackés."""
    params = {"status_id": "*", "sort": "updated_on:desc", **_ia_filter()}
    issues = list_issues(params, limit=10)
    if not issues:
        return "Aucun ticket récent."
    lines = "\n".join(_fmt_issue_line(i) for i in issues)
    return f"<b>Tickets récents</b> :\n{lines}"


def fmt_search(query):
    results = search_issues(query, limit=12)
    if not results:
        return f"Aucun résultat pour « {html.escape(query)} »."
    lines = []
    for r in results:
        rid = r.get("id")
        # Titre Redmine = "Tracker #id (Statut): sujet" → on ne garde que le sujet.
        raw = re.sub(r"^\w+ #\d+\s*(?:\([^)]*\))?:?\s*", "", r.get("title", ""))
        title = html.escape(_trunc(raw, 70))
        lines.append(f"• <b>RM{rid}</b> — {title}")
    return (f"<b>Recherche « {html.escape(query)} »</b> — {len(results)} résultat(s) :\n"
            + "\n".join(lines))


def _append_note_log(cfg_pm, rm_id, who, note):
    """Append la note au `.log.md` du ticket s'il est tracké localement (best-effort)."""
    try:
        path = cfg_pm.find_task(rm_id)
    except Exception:
        path = None
    if not path:
        return False
    log_path = path.parent / path.name.replace(".md", ".log.md")
    stamp = datetime.now().strftime("%Y-%m-%dT%H:%M")
    entry = (f"\n## {stamp} — Note Telegram ({who})\nTokens : 0 | Durée : 0 min\n\n"
             f"{note}\n")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry)
    return True


def cmd_note(cfg_pm, who, rm_id, note):
    """Poste la note sur Redmine + append .log.md local. Retourne le message HTML."""
    body = f"[Telegram via {who}] {note}"
    add_issue_note(rm_id, body)
    logged = _append_note_log(cfg_pm, rm_id, who, note)
    suffix = " (+ .log.md)" if logged else ""
    return f"✅ Note ajoutée à <b>RM{rm_id}</b>{suffix}."


# ────────────────────────────────── Handler ─────────────────────────────────

HELP = ("<b>karl-pm</b> — commandes :\n"
        "/rm &lt;id&gt; — état d'un ticket\n"
        "/mine — mes tickets en cours\n"
        "/recent — tickets récemment modifiés\n"
        "/search &lt;texte&gt; — recherche\n"
        "/note &lt;id&gt; &lt;texte&gt; — ajoute une note\n"
        "/status — état du bot\n"
        "/lock — verrouiller\n"
        "/unlock &lt;mdp&gt; — déverrouiller\n"
        "/whoami — ton ID Telegram")


def handle(bot, msg):
    token = bot["token"]
    lock = bot["lock"]
    chat_id = msg["chat"]["id"]
    msg_id = msg.get("message_id")
    user = msg.get("from") or {}
    uid = user.get("id")
    uname = user.get("username") or user.get("first_name") or "?"
    text = (msg.get("text") or "").strip()
    parts = text.split()
    cmd = parts[0].split("@")[0].lower() if parts else ""
    now = time.time()

    # /whoami : toujours dispo (sert à se whitelister)
    if cmd == "/whoami":
        send(token, chat_id, f"Ton telegram_user_id : <code>{uid}</code>\n"
                             f"chat_id : <code>{chat_id}</code>")
        return

    # Facteur 1 — whitelist
    wl = bot["whitelist"]
    if wl and uid not in wl:
        print(f"  ⨯ refus whitelist : uid={uid} (@{uname}) — text={text!r}")
        send(token, chat_id, "Désolé, tu n'es pas autorisé à interroger karl-pm. "
                             "Demande à Mathieu de t'ajouter (ton ID : /whoami).")
        return
    if not wl:
        print(f"  ⚠ mode découverte : uid={uid} (@{uname}) — "
              f"ajoute-le à TELEGRAM_WHITELIST pour verrouiller")

    # Aide : dispo même verrouillé
    if cmd in ("/help", "/start"):
        send(token, chat_id, HELP)
        return

    # Facteur 2 — verrouillage
    if cmd == "/unlock":
        # On efface le message tout de suite : le mdp ne doit pas rester en clair.
        if msg_id:
            delete_message(token, chat_id, msg_id)
        if not lock.enabled:
            send(token, chat_id, "🔓 Verrouillage non configuré "
                                 "(TELEGRAM_LOCK_PASSWORD_HASH absent).")
            return
        password = text.split(None, 1)[1] if len(parts) > 1 else ""
        status, info = lock.attempt_unlock(chat_id, password, now)
        if status == "ok":
            print(f"  🔓 unlock OK : uid={uid}")
            send(token, chat_id, "🔓 Déverrouillé. Auto-verrouillage dans 5 min "
                                 "d'inactivité. /lock pour verrouiller maintenant.")
        elif status == "lockout":
            print(f"  ⛔ unlock pendant lockout : uid={uid} ({info}s restantes)")
            send(token, chat_id, f"⛔ Trop d'échecs. Réessaie dans {info // 60} min "
                                 f"{info % 60} s.")
        elif status == "locked_now":
            print(f"  ⛔ lockout déclenché : uid={uid}")
            send(token, chat_id, f"⛔ {FAIL_THRESHOLD} échecs — bloqué "
                                 f"{LOCKOUT_SECONDS // 60} min.")
        else:  # fail
            print(f"  ✗ unlock échec : uid={uid} ({info} essai(s) restant(s))")
            send(token, chat_id, f"❌ Mot de passe incorrect. "
                                 f"{info} essai(s) avant blocage.")
        return

    if cmd == "/lock":
        lock.lock(chat_id)
        send(token, chat_id, "🔒 Verrouillé.")
        return

    if not lock.is_unlocked(chat_id, now):
        send(token, chat_id, "🔒 Verrouillé. Déverrouille avec "
                             "<code>/unlock &lt;mot de passe&gt;</code>.")
        return

    # Session déverrouillée — on rafraîchit le minuteur d'inactivité
    lock.touch(chat_id, now)

    if cmd == "/status":
        up = timedelta(seconds=int(now - bot["start"]))
        verrou = "désactivé (setup)" if not lock.enabled else "actif 🔓 (session ouverte)"
        send(token, chat_id, f"✅ karl-pm en ligne ({bot['version']}).\n"
                             f"• Uptime : {up}\n• Verrou : {verrou}")
        return

    if cmd == "/rm":
        if len(parts) < 2 or not parts[1].lstrip("#").isdigit():
            send(token, chat_id, "Usage : <code>/rm 1724</code>")
            return
        _safe(token, chat_id, lambda: fmt_ticket(int(parts[1].lstrip("#"))))
        return

    if cmd == "/mine":
        _safe(token, chat_id, fmt_mine)
        return

    if cmd == "/recent":
        _safe(token, chat_id, fmt_recent)
        return

    if cmd == "/search":
        m = re.match(r"/search(?:@\S+)?\s+(.+)", text, re.S)
        if not m:
            send(token, chat_id, "Usage : <code>/search texte à chercher</code>")
            return
        _safe(token, chat_id, lambda: fmt_search(m.group(1).strip()))
        return

    if cmd == "/note":
        m = re.match(r"/note(?:@\S+)?\s+#?(\d+)\s+(.+)", text, re.S)
        if not m:
            send(token, chat_id, "Usage : <code>/note 1724 ton message</code>")
            return
        rm_id, note = int(m.group(1)), m.group(2).strip()
        _safe(token, chat_id, lambda: cmd_note(bot["cfg_pm"], uname, rm_id, note))
        return

    send(token, chat_id, "Commande inconnue. /help pour la liste.")


def _safe(token, chat_id, fn):
    """Exécute fn() et envoie son résultat ; convertit les erreurs en message poli."""
    try:
        send(token, chat_id, fn())
    except SystemExit as e:
        send(token, chat_id, f"Erreur Redmine : {e}")
    except Exception as e:
        send(token, chat_id, f"Erreur : {e}")


# ─────────────────────────────────── Main ───────────────────────────────────

def gen_password_hash():
    """Mode --hash-password : prompt + impression de la ligne .env à coller."""
    p1 = getpass.getpass("Mot de passe de verrouillage : ")
    if len(p1) < 6:
        sys.exit("Trop court (6 caractères minimum).")
    if p1 != getpass.getpass("Confirme : "):
        sys.exit("Les deux saisies diffèrent.")
    print("\nAjoute cette ligne dans .env (le mdp en clair n'est stocké nulle part) :\n")
    print(f"TELEGRAM_LOCK_PASSWORD_HASH={hash_password(p1)}")


def main():
    if "--hash-password" in sys.argv:
        gen_password_hash()
        return

    cfg_pm = PMConfig.load()  # charge .env + donne find_task()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("ERREUR : TELEGRAM_BOT_TOKEN absent (.env ou env). "
                 "Crée le bot via @BotFather puis ajoute la ligne dans .env.")
    wl_raw = os.environ.get("TELEGRAM_WHITELIST", "")
    whitelist = {int(x) for x in wl_raw.replace(" ", "").split(",") if x.strip().isdigit()}
    lock = Lock(os.environ.get("TELEGRAM_LOCK_PASSWORD_HASH"))

    bot = {"token": token, "whitelist": whitelist, "lock": lock,
           "cfg_pm": cfg_pm, "start": time.time(), "version": "v0.2"}

    me = tg(token, "getMe")["result"]
    print(f"✓ Bot connecté : @{me.get('username')} ({me.get('first_name')})")
    print(f"  Whitelist : {whitelist or 'VIDE (mode découverte)'}")
    if lock.enabled:
        print(f"  Verrou : ACTIF (auto-lock {AUTO_LOCK_SECONDS // 60} min, "
              f"lockout {FAIL_THRESHOLD} échecs / {LOCKOUT_SECONDS // 60} min)")
    else:
        print("  Verrou : DÉSACTIVÉ — configure TELEGRAM_LOCK_PASSWORD_HASH "
              "(python3 scripts/karl-telegram-bot.py --hash-password)")
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
            # On ne logge que la 1re token (la commande) : évite de fuiter un mdp /unlock.
            first_tok = (msg["text"].split() or [""])[0]
            print(f"  → update {upd['update_id']} : {first_tok!r}")
            try:
                handle(bot, msg)
            except Exception as e:
                print(f"  ⚠ handler erreur : {e}")


if __name__ == "__main__":
    main()
