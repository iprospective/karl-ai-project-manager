#!/usr/bin/env python3
"""karl-telegram-bot — Bot Telegram « standardiste » de karl-pm (épic A, RM1724).

Long-polling + commandes info one-shot. Le bot ne raisonne pas — il route
Telegram ↔ Redmine REST. Couche de sécurité à deux facteurs :

  1. **Whitelist** d'IDs Telegram — qui peut parler au bot. Source : la table
     `telegram.users` de la conf (qui dit aussi QUI est chaque ID), plus
     TELEGRAM_WHITELIST (repli historique). **Vide = personne** (fail-secure,
     RM1777) : seul /whoami répond, pour qu'un nouvel utilisateur trouve son ID.
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
    TELEGRAM_WHITELIST           csv d'IDs autorisés (repli ; préférer telegram.users)
    TELEGRAM_LOCK_PASSWORD_HASH  empreinte PBKDF2 du mdp (cf. --hash-password), OU
                                 une URI de coffre (`secret:telegram/karl-lock`,
                                 `secret://…`, `vaultwarden://…`) lue au démarrage,
                                 champ `password`. Coffre fermé ⇒ le bot REFUSE de
                                 démarrer plutôt que de tourner sans verrou.

Correspondance Telegram → utilisateur (pm.config.local.yml — donnée personnelle,
propre à l'instance, jamais commitée) :
    telegram:
      users:
        - telegram_id: 123456789   # donné par /whoami
          pm_user: iprospective    # identifiant PM (team.username)
          redmine_id: 5            # « /today moi » vise cet utilisateur
          name: Mathieu
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
from redmine_utils import find_users, get_ia_cf_id, list_time_entries
from pm_task import get_task_provider  # seam TaskProvider (P1/RM2543)
from pm_paths import PMConfig

TG_API = "https://api.telegram.org/bot{token}/{method}"
SECRET_PREFIXES = ("secret:", "vaultwarden://")

AUTO_LOCK_SECONDS = 300   # 5 min d'inactivité → re-verrouillage
FAIL_THRESHOLD = 3        # nb d'échecs /unlock avant blocage
LOCKOUT_SECONDS = 300     # durée du blocage après FAIL_THRESHOLD échecs
PBKDF2_ITERATIONS = 200_000


# ── Configuration : correspondance utilisateurs, empreinte au coffre (RM1777) ──
def load_conf(pm_dir) -> dict:
    """pm.config.yml fusionné avec pm.config.local.yml (où vit `telegram.users`)."""
    import yaml
    from pm_paths import _deep_merge
    cfg = {}
    for nom in ("pm.config.yml", "pm.config.local.yml"):
        f = Path(pm_dir) / nom
        if f.is_file():
            cfg = _deep_merge(cfg, yaml.safe_load(f.read_text(encoding="utf-8")) or {})
    return cfg


def load_users(conf: dict) -> dict:
    """`telegram.users` → {telegram_id: {pm_user, redmine_id, name}}.

    Une entrée sans `telegram_id` entier est ignorée ET signalée : un ID mal saisi
    qui passerait en silence laisserait croire qu'un utilisateur est autorisé."""
    users = {}
    for i, e in enumerate(((conf.get("telegram") or {}).get("users")) or []):
        tid = (e or {}).get("telegram_id")
        if not isinstance(tid, int) or isinstance(tid, bool):
            print(f"  ⚠ telegram.users[{i}] ignorée : telegram_id entier requis (reçu {tid!r})")
            continue
        users[tid] = {"pm_user": e.get("pm_user"), "redmine_id": e.get("redmine_id"),
                      "name": e.get("name") or e.get("pm_user") or str(tid)}
    return users


def build_whitelist(users: dict, raw: str) -> set:
    """IDs autorisés : ceux de la correspondance + le repli TELEGRAM_WHITELIST."""
    extra = {int(x) for x in (raw or "").replace(" ", "").split(",") if x.strip().isdigit()}
    return set(users) | extra


def resolve_lock_hash(value, resolver=None):
    """Empreinte de verrou : valeur brute, ou URI de coffre résolue (champ `password`).

    Rend (empreinte|None, origine). Une URI qui ne se résout pas LÈVE : démarrer sans
    verrou parce que le coffre est fermé transformerait une panne en faille."""
    v = (value or "").strip()
    if not v:
        return None, "absente"
    if not v.startswith(SECRET_PREFIXES):
        return v, ".env"
    resolver = resolver or _resolve_secret
    h = (resolver(v, "password") or "").strip()
    if not h:
        raise RuntimeError(f"empreinte vide au coffre ({v})")
    return h, "coffre"


def _resolve_secret(uri, field):
    import subprocess
    helper = Path(__file__).resolve().parent / "resolve-secret.sh"
    r = subprocess.run([str(helper), uri, field], capture_output=True, text=True)
    if r.returncode in (2, 3):
        raise RuntimeError("coffre verrouillé ou vault-agentd absent — ouvre-le puis relance")
    if r.returncode != 0:
        raise RuntimeError(f"resolve-secret ({r.returncode}) sur {uri} : {r.stderr.strip()}")
    return r.stdout.rstrip("\n")

KARL_ID = 79              # identité agent karl (Redmine) — seul producteur de tokens
# Entrée de log « Tick IA » écrite par pm-task-tick : `## <date>T.. — …` + `Tokens : N`
TOKEN_LOG_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})T[\d:]+ —.*\nTokens ?: ?(\d+)", re.M)


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
    issue = get_task_provider().fetch_issue(rm_id, include="journals")
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
    issues = get_task_provider().list_issues(params, limit=15)
    if not issues:
        return "Aucun ticket en cours assigné à karl. 🎉"
    lines = "\n".join(_fmt_issue_line(i) for i in issues)
    return f"<b>Tickets en cours (karl)</b> — {len(issues)} :\n{lines}"


def fmt_recent():
    """Derniers tickets modifiés (tous statuts), IA-trackés."""
    params = {"status_id": "*", "sort": "updated_on:desc", **_ia_filter()}
    issues = get_task_provider().list_issues(params, limit=10)
    if not issues:
        return "Aucun ticket récent."
    lines = "\n".join(_fmt_issue_line(i) for i in issues)
    return f"<b>Tickets récents</b> :\n{lines}"


def fmt_search(query):
    results = get_task_provider().search_issues(query, limit=12)
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
    get_task_provider().add_note(rm_id, body)
    logged = _append_note_log(cfg_pm, rm_id, who, note)
    suffix = " (+ .log.md)" if logged else ""
    return f"✅ Note ajoutée à <b>RM{rm_id}</b>{suffix}."


# ─────────────────────────────── Bilan du jour ──────────────────────────────

def _fmt_tokens(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f} M".replace(".", ",")
    if n >= 1_000:
        return f"{n / 1_000:.1f} k".replace(".", ",")
    return str(n)


def _fmt_hours(h):
    return f"{h:.2f}".replace(".", ",")


def resolve_user(arg, manager_id):
    """Résout l'argument de /today en (user_id, nom, is_agent).

    Retourne (None, message_erreur, False) si introuvable. Accepte : vide/karl →
    agent ; moi/me/mathieu → manager ; un id numérique ; sinon fragment de nom
    (recherche Redmine best-effort)."""
    a = (arg or "").strip().lower()
    if not a or a in ("karl", "agent"):
        return KARL_ID, "karl", True
    if a in ("moi", "me", "mathieu", "manager"):
        return manager_id, "Mathieu", manager_id == KARL_ID
    if a.isdigit():
        uid = int(a)
        return uid, f"user #{uid}", uid == KARL_ID
    users = find_users(arg.strip())
    if not users:
        return (None, f"Utilisateur « {html.escape(arg.strip())} » introuvable "
                      f"(essaie un id, « moi » ou « karl »).", False)
    u = users[0]
    name = f"{u.get('firstname', '')} {u.get('lastname', '')}".strip() or u.get("login", str(u["id"]))
    return u["id"], name, u["id"] == KARL_ID


def sum_log_tokens_today(cfg_pm, today_iso):
    """Somme les tokens des entrées `.log.md` datées d'aujourd'hui (travail karl).

    Retourne (total_tokens, set_des_rm_ids_touchés)."""
    total, tickets = 0, set()
    for p in Path(cfg_pm.projects_root).rglob("*.log.md"):
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        file_total = sum(int(m.group(2)) for m in TOKEN_LOG_RE.finditer(txt)
                         if m.group(1) == today_iso)
        if file_total:
            total += file_total
            mm = re.match(r"RM(\d+)_", p.name)
            if mm:
                tickets.add(int(mm.group(1)))
    return total, tickets


def cmd_today(cfg_pm, today_iso, user_id, display, is_agent):
    """Bilan du jour pour un user : heures saisies (Redmine) + tokens (logs, karl)."""
    te = list_time_entries({"user_id": user_id, "spent_on": today_iso}, limit=100)
    hours = sum(float(t.get("hours") or 0) for t in te)
    if te and (te[0].get("user") or {}).get("name"):
        display = te[0]["user"]["name"]
    issues = sorted({t["issue"]["id"] for t in te if t.get("issue")})

    lines = [f"📊 <b>Aujourd'hui {today_iso}</b> — {html.escape(display)}",
             f"• Heures saisies : <b>{_fmt_hours(hours)} h</b> ({len(te)} saisie(s))"]
    if issues:
        shown = ", ".join(f"RM{i}" for i in issues[:8])
        more = f" +{len(issues) - 8}" if len(issues) > 8 else ""
        lines.append(f"• Tickets : {shown}{more}")
    if is_agent:
        tok, tickets = sum_log_tokens_today(cfg_pm, today_iso)
        suffix = f" sur {len(tickets)} ticket(s)" if tickets else ""
        lines.append(f"• Tokens IA (logs du jour) : <b>{_fmt_tokens(tok)}</b>{suffix}")
    else:
        lines.append("• Tokens IA : — (user humain)")
    return "\n".join(lines)


# ────────────────────────────────── Handler ─────────────────────────────────

HELP = ("<b>karl-pm</b> — commandes :\n"
        "/rm &lt;id&gt; — état d'un ticket\n"
        "/mine — mes tickets en cours\n"
        "/recent — tickets récemment modifiés\n"
        "/search &lt;texte&gt; — recherche\n"
        "/note &lt;id&gt; &lt;texte&gt; — ajoute une note\n"
        "/today [user] — bilan heures + tokens du jour (défaut : karl)\n"
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
    ident = bot.get("users", {}).get(uid)   # qui est cet ID côté PM (RM1777)
    text = (msg.get("text") or "").strip()
    parts = text.split()
    cmd = parts[0].split("@")[0].lower() if parts else ""
    now = time.time()

    # /whoami : toujours dispo (sert à se whitelister)
    if cmd == "/whoami":
        qui = (f"\nReconnu : <b>{html.escape(ident['name'])}</b>" if ident
               else "\nNon reconnu : donne cet ID à Mathieu pour être ajouté.")
        send(token, chat_id, f"Ton telegram_user_id : <code>{uid}</code>\n"
                             f"chat_id : <code>{chat_id}</code>{qui}")
        return

    # Facteur 1 — whitelist
    # Liste vide = personne (RM1777) : l'ancien « mode découverte » laissait
    # n'importe quel compte Telegram interroger Redmine.
    wl = bot["whitelist"]
    if uid not in wl:
        # Pas le texte : il peut contenir un /unlock <mdp> tapé par un inconnu.
        print(f"  ⨯ refus whitelist : uid={uid} (@{uname}) — commande {cmd!r}")
        send(token, chat_id, "Désolé, tu n'es pas autorisé à interroger karl-pm. "
                             "Demande à Mathieu de t'ajouter (ton ID : /whoami).")
        return

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
        _safe(token, chat_id, lambda: cmd_note(bot["cfg_pm"], (ident or {}).get("pm_user") or uname, rm_id, note))
        return

    if cmd in ("/today", "/jour"):
        m = re.match(r"/(?:today|jour)(?:@\S+)?(?:\s+(.+))?$", text, re.S)
        arg = (m.group(1) or "").strip() if m else ""
        moi = (ident or {}).get("redmine_id")
        uid, name, is_agent = resolve_user(arg, moi or bot["manager_id"])
        if moi and uid == moi and not is_agent:
            name = ident["name"]
        if uid is None:
            send(token, chat_id, name)  # name porte le message d'erreur
            return
        today_iso = datetime.now().strftime("%Y-%m-%d")
        _safe(token, chat_id,
              lambda: cmd_today(bot["cfg_pm"], today_iso, uid, name, is_agent))
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


# ───────────────────────────── Offset persistant ────────────────────────────
# L'offset getUpdates est persisté sur disque : au redémarrage le bot reprend là
# où il s'était arrêté, sans re-traiter ni sauter d'updates. (Telegram garde les
# updates non confirmés ~24 h, donc une perte du fichier reste récupérable.)

def _offset_file():
    base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    return Path(base) / "karl-telegram-bot" / "offset"


def load_offset():
    """Lit l'offset persisté, ou None si absent/illisible."""
    try:
        return int(_offset_file().read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None
    except Exception as e:
        print(f"  ⚠ lecture offset échouée ({e}) — repart de zéro")
        return None


def save_offset(offset):
    """Persiste l'offset (écriture atomique). Best-effort, non fatal."""
    if offset is None:
        return
    f = _offset_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(str(offset), encoding="utf-8")
        tmp.replace(f)
    except Exception as e:
        print(f"  ⚠ persistance offset échouée ({e}) — on continue")


# ─────────────────────────────────── Main ───────────────────────────────────

def gen_password_hash():
    """Mode --hash-password : prompt + impression de la ligne .env à coller."""
    p1 = getpass.getpass("Mot de passe de verrouillage : ")
    if len(p1) < 6:
        sys.exit("Trop court (6 caractères minimum).")
    if p1 != getpass.getpass("Confirme : "):
        sys.exit("Les deux saisies diffèrent.")
    print("\nRange cette empreinte au coffre, champ « password » (ex. entrée telegram/karl-lock),")
    print("puis pose dans .env :  TELEGRAM_LOCK_PASSWORD_HASH=secret:telegram/karl-lock")
    print("(à défaut, l'empreinte elle-même en valeur — accepté, mais signalé au démarrage).")
    print("Le mot de passe en clair n'est stocké nulle part.\n")
    print(hash_password(p1))


def main():
    if "--hash-password" in sys.argv:
        gen_password_hash()
        return

    cfg_pm = PMConfig.load()  # charge .env + donne find_task()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("ERREUR : TELEGRAM_BOT_TOKEN absent (.env ou env). "
                 "Crée le bot via @BotFather puis ajoute la ligne dans .env.")
    conf = {}
    try:
        conf = load_conf(cfg_pm.pm_dir)
    except Exception as e:
        print(f"  ⚠ conf illisible ({e}) — correspondance utilisateurs vide")
    users = load_users(conf)
    whitelist = build_whitelist(users, os.environ.get("TELEGRAM_WHITELIST", ""))
    try:
        lock_hash, lock_src = resolve_lock_hash(os.environ.get("TELEGRAM_LOCK_PASSWORD_HASH"))
    except RuntimeError as e:
        sys.exit(f"ERREUR : empreinte du verrou illisible — {e}. "
                 "Le bot ne démarre pas sans verrou quand un verrou est configuré.")
    lock = Lock(lock_hash)

    # Id Redmine du manager (cf. pm.config.yml :: ia.default_manager) — /today moi
    # quand l'appelant n'a pas de redmine_id dans telegram.users
    manager_id = ((conf.get("ia") or {}).get("default_manager") or {}).get("redmine_id", 5)

    bot = {"token": token, "whitelist": whitelist, "users": users, "lock": lock, "cfg_pm": cfg_pm,
           "manager_id": manager_id, "start": time.time(), "version": "v0.4"}

    me = tg(token, "getMe")["result"]
    print(f"✓ Bot connecté : @{me.get('username')} ({me.get('first_name')})")
    print(f"  Whitelist : {len(whitelist)} ID(s), dont {len(users)} identifié(s)"
          if whitelist else "  Whitelist : VIDE — personne n'est autorisé (seul /whoami répond)")
    if lock.enabled:
        print(f"  Empreinte du verrou : {lock_src}"
              + ("" if lock_src == "coffre" else " — à migrer au coffre (TELEGRAM_LOCK_PASSWORD_HASH=secret:…)"))
        print(f"  Verrou : ACTIF (auto-lock {AUTO_LOCK_SECONDS // 60} min, "
              f"lockout {FAIL_THRESHOLD} échecs / {LOCKOUT_SECONDS // 60} min)")
    else:
        print("  Verrou : DÉSACTIVÉ — configure TELEGRAM_LOCK_PASSWORD_HASH "
              "(python3 scripts/karl-telegram-bot.py --hash-password)")
    offset = load_offset()
    print(f"  Long-polling… (offset repris : {offset}) (Ctrl-C pour arrêter)")

    while True:
        try:
            resp = tg(token, "getUpdates", offset=offset, timeout=30)
        except requests.RequestException as e:
            print(f"  ⚠ getUpdates erreur réseau : {e} — retry dans 3s")
            time.sleep(3)
            continue
        for upd in resp.get("result", []):
            offset = upd["update_id"] + 1
            # On confirme l'update (offset persisté) AVANT de le traiter : même si
            # le handler crashe, on ne le rejouera pas en boucle au redémarrage.
            save_offset(offset)
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
