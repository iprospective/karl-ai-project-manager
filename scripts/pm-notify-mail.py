#!/usr/bin/env python3
"""pm-notify-mail — le canal mail du fil de notifications (RM2792, lot 3).

Le fil se lit dans le cockpit ; encore faut-il y aller. Le mail est le canal qui va CHERCHER
quelqu'un — donc celui qui doit se taire le plus. Un canal qui redit toutes les quinze minutes ce
qu'il a déjà dit n'alerte plus : il apprend à être ignoré.

D'où trois règles, et pas une de plus :

  1. **Un seul mail** par passage, qui rassemble tout ce qui attend. Jamais un mail par ligne.
  2. **Ce qui est déjà parti ne repart pas** — le fil retient l'envoi (`mailed`) sur l'entrée
     elle-même, avec le niveau auquel elle est partie.
  3. **Sauf si ça a empiré** : une alerte passée de `warn` à `critical` est une nouvelle.

Le corps part par l'entrée standard de `karl-mail-send`, jamais en argument : une ligne de commande
se retrouve dans `ps`, dans les journaux du shell et dans l'historique — un message qui cite un
ticket ou un hôte n'a rien à y faire.

  pm-notify-mail                        envoie ce qui attend (niveau « warn » et au-dessus)
  pm-notify-mail --level critical       ne dérange que pour du critique
  pm-notify-mail --to a@b.fr            destinataire explicite (défaut : PM_NOTIFY_MAIL_TO)
  pm-notify-mail --dry-run              montre le mail exact, n'envoie rien, ne marque rien
"""
import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_notify as N                                   # noqa: E402
try:
    from pm_log import Journal
    _J = Journal("pm-notify-mail", "system")
except ImportError:                                     # le canal ne dépend pas du journal
    _J = None

ICONE = {"info": "·", "warn": "!", "critical": "!!"}


def sujet(entrees: list) -> str:
    """Ce qu'on lit sans ouvrir le mail : combien, et le pire. Le reste est dans le corps."""
    pires = [e for e in entrees if e.get("level") == "critical"]
    tete = f"PM · {len(entrees)} notification" + ("s" if len(entrees) > 1 else "")
    if pires:
        tete += f" dont {len(pires)} critique" + ("s" if len(pires) > 1 else "")
    return tete + " en attente"


def corps(entrees: list, qui: str) -> str:
    """Le mail doit se suffire : ce qui attend, d'où ça vient, depuis quand, et comment le traiter."""
    lignes = ["Le fil de notifications PM a des entrées en attente.", ""]
    for e in entrees:
        refs = " ".join(f"{k}={e[k]}" for k in ("job", "rm", "sid", "ref") if e.get(k))
        rep = f" (×{e['repeats']})" if e.get("repeats", 1) > 1 else ""
        lignes.append(f"[{ICONE.get(e.get('level'), '·')}] {(e.get('last') or e.get('ts', ''))[:16]}  "
                      f"{e.get('origin', '?')} — {e.get('msg', '')}{rep}")
        if refs:
            lignes.append(f"      {refs}")
        lignes.append(f"      id {e.get('id')}")
    lignes += ["", "Pour les traiter :",
               "  mmi-pm notify                  ce qui attend",
               "  mmi-pm notify --done <id>…     marquer traité (sort de la vue)",
               "", f"(fil lu au nom de « {qui} » ; les notifications privées d'autrui n'y figurent pas)"]
    return "\n".join(lignes)


def envoie(destinataire: str, titre: str, texte: str) -> tuple:
    """Rend (ok, détail). Le corps passe par stdin — `--body -` — jamais par la ligne de commande."""
    cmd = [sys.executable, str(HERE / "karl-mail-send.py"), "--to", destinataire,
           "--subject", titre, "--body", "-"]
    try:
        p = subprocess.run(cmd, input=texte, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    return p.returncode == 0, ((p.stderr or p.stdout or "").strip()[-500:])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", help="destinataire (défaut : PM_NOTIFY_MAIL_TO)")
    ap.add_argument("--level", choices=N.NIVEAUX, default="warn", help="seuil d'envoi (défaut : warn)")
    ap.add_argument("--as", dest="viewer", metavar="UTILISATEUR",
                    help="au nom de qui le fil est lu (défaut : PM_NOTIFY_OWNER, sinon le compte courant)")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    qui = a.viewer or N.owner() or getpass.getuser()
    destinataire = (a.to or os.environ.get("PM_NOTIFY_MAIL_TO") or "").strip()
    attente = N.pending_mail(a.level, viewer=qui)

    if not attente:
        if a.json:
            print(json.dumps({"sent": 0, "reason": "rien à envoyer"}, ensure_ascii=False))
        else:
            print("rien à envoyer")
        return 0
    if not destinataire:
        # Pas une erreur : un canal non configuré doit le DIRE une fois, pas faire clignoter
        # l'ordonnanceur à chaque passage. Le fil, lui, garde tout : rien n'est perdu.
        msg = f"{len(attente)} notification(s) à envoyer, mais aucun destinataire — poser PM_NOTIFY_MAIL_TO"
        print(msg)
        if a.json:
            print(json.dumps({"sent": 0, "reason": "aucun destinataire"}, ensure_ascii=False))
        return 0

    titre, texte = sujet(attente), corps(attente, qui)
    if a.dry_run:
        print(f"À : {destinataire}\nObjet : {titre}\n\n{texte}")
        return 0

    ok, detail = envoie(destinataire, titre, texte)
    if ok:
        N.mark_mailed([e["id"] for e in attente])
    if _J:
        _J.write("info" if ok else "warn",
                 f"canal mail : {len(attente)} notification(s) {'envoyées' if ok else 'NON envoyées'}",
                 to=destinataire, level=a.level)
    if a.json:
        print(json.dumps({"sent": len(attente) if ok else 0, "to": destinataire,
                          "ok": ok, "detail": detail}, ensure_ascii=False))
    else:
        print(("✓ " if ok else "✗ ") + f"{len(attente)} notification(s) → {destinataire}"
              + (f"\n  {detail}" if detail and not ok else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
