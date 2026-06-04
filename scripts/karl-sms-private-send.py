#!/usr/bin/env python3
"""karl-sms-private-send — Notification SMS privée via l'API SMS Free Mobile.

Connecteur PRIVÉ : l'API Free Mobile n'autorise l'envoi QUE vers la ligne Free
Mobile associée au compte (identifiant + clé). Pas de destinataire arbitraire —
c'est volontaire, et c'est ce que reflète le nom du script. Pour envoyer un SMS
à un tiers, il faudra un connecteur séparé (API OVH ou autre) à faire plus tard.

Canal de secours pour alerter Mathieu en cas d'urgence quand il n'a pas de Data
(l'API Free Mobile passe par le réseau SMS opérateur, pas par Internet côté
destinataire). Le SMS arrive sur la ligne Free Mobile associée au compte.

L'API Free Mobile (option « Notifications par SMS » activée dans l'espace
abonné → Mes options) attend deux paramètres :
    user  identifiant Free Mobile à 8 chiffres   → SMS_FREE_USER
    pass  clé d'identification générée            → SMS_FREE_TOKEN
    msg   texte du message (urlencodé)

Endpoint : https://smsapi.free-mobile.fr/sendmsg  (GET ou POST)
Codes retour :
    200  SMS envoyé
    400  paramètre manquant
    402  trop de SMS envoyés (rate limit)
    403  service non activé / identifiant ou clé invalide
    500  erreur serveur Free

Secrets résolus depuis .env via PMConfig.load() (jamais loggués).
Append automatique au .log.md du ticket si --rm-id fourni.

Usage :
    karl-sms-private-send.py --message "Build prod KO, intervention requise"
    echo "Texte multiligne" | karl-sms-private-send.py --message -
    karl-sms-private-send.py --message "RM1234 livré" --rm-id 1234
    karl-sms-private-send.py --message "test" --dry-run
"""
import argparse
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

API_URL = "https://smsapi.free-mobile.fr/sendmsg"
TIMEOUT = 15

# Code HTTP → message clair
STATUS_HELP = {
    400: "paramètre manquant (user/pass/msg vides ?)",
    402: "rate limit Free atteint — trop de SMS envoyés récemment, réessaie plus tard",
    403: "service non activé ou identifiant/clé invalide "
         "(espace abonné Free → Mes options → Notifications par SMS)",
    500: "erreur serveur Free Mobile, réessaie plus tard",
}


def read_message(arg: str) -> str:
    if arg == "-":
        body = sys.stdin.read()
    else:
        body = arg
    body = body.strip()
    if not body:
        sys.exit("ERREUR : message vide.")
    # Free tronque au-delà de ~1000 caractères ; on prévient sans bloquer.
    if len(body) > 999:
        print(f"AVERTISSEMENT : message de {len(body)} caractères, "
              "il sera probablement tronqué par Free.", file=sys.stderr)
    return body


def send_sms(user: str, token: str, message: str) -> None:
    params = urllib.parse.urlencode({"user": user, "pass": token, "msg": message})
    req = urllib.request.Request(f"{API_URL}?{params}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            if resp.status == 200:
                return
            sys.exit(f"ERREUR : HTTP {resp.status} — {STATUS_HELP.get(resp.status, 'inconnu')}")
    except urllib.error.HTTPError as e:
        sys.exit(f"ERREUR : HTTP {e.code} — {STATUS_HELP.get(e.code, e.reason)}")
    except urllib.error.URLError as e:
        sys.exit(f"ERREUR réseau : {e.reason}")


def append_log(cfg: PMConfig, rm_id: int, message: str) -> None:
    """Append une entrée au .log.md du ticket, comme karl-mail-send."""
    try:
        task_file = cfg.find_task(rm_id)
    except Exception:
        task_file = None
    if not task_file:
        print(f"AVERTISSEMENT : ticket RM{rm_id} introuvable, log non écrit.", file=sys.stderr)
        return
    log_file = task_file.parent / task_file.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    preview = message if len(message) <= 120 else message[:117] + "…"
    entry = f"\n## {ts} — SMS envoyé (Free Mobile)\n\n> {preview}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Envoie un SMS privé (ligne Free Mobile du compte) via l'API Free Mobile.")
    ap.add_argument("--message", "-m", required=True,
                    help="Texte du SMS, ou '-' pour lire stdin.")
    ap.add_argument("--rm-id", type=int, help="Ticket Redmine : append une entrée au .log.md.")
    ap.add_argument("--dry-run", action="store_true",
                    help="N'envoie rien, affiche ce qui serait envoyé.")
    args = ap.parse_args()

    cfg = PMConfig.load()
    user = os.environ.get("SMS_FREE_USER", "").strip()
    token = os.environ.get("SMS_FREE_TOKEN", "").strip()
    if not token:
        sys.exit("ERREUR : SMS_FREE_TOKEN absent (.env).")
    if not user:
        sys.exit("ERREUR : SMS_FREE_USER absent (.env) — "
                 "identifiant Free Mobile à 8 chiffres requis par l'API.")

    message = read_message(args.message)

    if args.dry_run:
        print(f"[dry-run] user={user[:2]}******  longueur={len(message)} car.")
        print(f"[dry-run] message :\n{message}")
        return

    send_sms(user, token, message)
    print("SMS envoyé.")

    if args.rm_id:
        append_log(cfg, args.rm_id, message)


if __name__ == "__main__":
    main()
