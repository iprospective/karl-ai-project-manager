#!/usr/bin/env python3
"""pm-secret-watch — un secret a transité dans le tour : notifier et ouvrir la rotation. RM3274.

RM2466 avait livré le **canal** de notifications et la **règle** NORMS qui demande
à l'agent de signaler un secret affiché en séance. Mais c'était une obligation
d'agent : s'il n'y pensait pas, rien ne rattrapait. L'incident fondateur (RM3271,
2026-09-21) l'a montré — un `SELECT` non filtré sur `ps_configuration` a affiché
le token d'API Meta d'un site de production ; l'agent l'a signalé, mais parce
qu'il y a pensé, et le demandeur a dû demander « tu as bien mis en notif/log ? ».

Ce hook `Stop` relit le tour qui vient de finir et agit **sans geste de l'agent** :

1. **notification `critical`** adressée à l'owner — tous les secrets, sans palier
   (arbitrage Mathieu, 2026-09-21 : le réglage porte sur la précision de la
   détection, jamais sur le niveau) ;
2. **ticket de rotation créé automatiquement**, type `security`, priorité
   `immediat`, dans le projet du dossier courant, lié au ticket du tour ;
3. **entrée au `.log.md`** du ticket courant, pour que l'incident survive à la
   session.

**Rien de ce qui sort d'ici ne contient la valeur du secret** : ni la
notification, ni le ticket, ni le journal. Un garde qui recopie ce qu'il dénonce
le propage une fois de plus, et dans des supports qui durent plus longtemps que
le transcript. On nomme la clé, l'endroit et l'empreinte (`sha256[:12]`).

Deux gardes contre l'emballement, parce qu'un hook qui crée des tickets Redmine
à chaque tour serait pire que le mal :

- **mémoire d'incident** par empreinte : le même secret revu dans dix tours ne
  produit qu'un ticket et qu'une entrée au fil (qui remonte, avec son compteur) ;
- **plafond par session** (`PM_SECRET_WATCH_MAX`, 3 par défaut) : au-delà, on
  notifie encore mais on cesse d'ouvrir des tickets, et la notification le dit.

  hook : payload JSON sur stdin ({session_id, transcript_path, cwd}) — jamais d'échec bloquant.
  CLI  : pm-secret-watch.py --transcript <jsonl> [--cwd D] [--session S] [--dry-run]
         pm-secret-watch.py --text "…" --dry-run      # essayer un texte à la main
         pm-secret-watch.py --forget                  # oublier les incidents mémorisés
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_secret_scan  # noqa: E402

MAX_TICKETS_DEFAUT = 3


def _mod(nom_fichier, nom_module):
    """Charge un script à tirets voisin comme module (ils ne sont pas importables tels quels)."""
    spec = importlib.util.spec_from_file_location(nom_module, HERE / nom_fichier)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _etat_path():
    """Fichier mémoire des incidents déjà traités (par empreinte)."""
    d = os.environ.get("PM_SECRET_WATCH_DIR")
    if d:
        return Path(d) / "secret-watch.json"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "pm" / "secret-watch.json"


def _etat_lire():
    try:
        return json.loads(_etat_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _etat_ecrire(etat):
    p = _etat_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")
        return True
    except OSError:
        return False


def dernier_tour(events):
    """(tout ce qui a transité, ce que l'agent a dit) pour le dernier tour du transcript.

    Le tour court du dernier prompt humain jusqu'à la fin. On sépare les deux
    textes parce qu'ils ne servent pas au même signal : le secret se cherche dans
    TOUT (une sortie d'outil, surtout), l'aveu seulement dans ce que l'agent écrit.
    """
    tick = _mod("pm-task-tick.py", "pm_task_tick")
    debut = 0
    for i, evt in enumerate(events):
        try:
            if tick._is_human_prompt(evt):
                debut = i
        except Exception:
            continue
    montre, dit = [], []
    for evt in events[debut:]:
        role, blocs = tick._blocks(evt)
        for b in blocs:
            if not isinstance(b, dict):
                montre.append(str(b))
                continue
            txt = b.get("text") or b.get("content") or ""
            if not isinstance(txt, str):
                txt = json.dumps(txt, ensure_ascii=False)
            if not txt:
                continue
            montre.append(txt)
            if role == "assistant" and b.get("type") == "text":
                dit.append(txt)
    return "\n".join(montre), "\n".join(dit)


def message_notification(inc, rm_courant, ticket_rotation, plafonne):
    """Message du fil — nomme la clé et l'endroit, jamais la valeur."""
    quoi = ", ".join(inc["labels"]) if inc["labels"] else ", ".join(inc["avowal"])
    msg = f"SÉCURITÉ — un secret a transité dans le transcript : {quoi}."
    if inc["fingerprints"]:
        msg += f" Empreinte(s) : {', '.join(inc['fingerprints'])} (sha256 tronqué, pas la valeur)."
    if inc["avowal"] and inc["labels"]:
        msg += f" L'agent l'a signalé ({', '.join(inc['avowal'])})."
    elif inc["avowal"]:
        msg += " Détecté sur le signalement de l'agent, la valeur n'étant plus dans la fenêtre relue."
    if ticket_rotation:
        msg += f" Rotation à faire : RM{ticket_rotation}."
    elif plafonne:
        msg += (" Plafond de tickets atteint pour cette session : aucun ticket ouvert, "
                "la rotation reste à faire à la main.")
    if rm_courant:
        msg += f" Vu pendant RM{rm_courant}."
    return msg


def corps_ticket(inc, rm_courant):
    quoi = ", ".join(inc["labels"]) if inc["labels"] else ", ".join(inc["avowal"])
    lignes = [
        "## Contexte",
        "",
        f"Un secret a transité en clair dans le transcript d'une session agent : **{quoi}**.",
        "",
        "Détecté automatiquement par le hook `pm-secret-watch` (RM3274). Le secret est à "
        "considérer comme **compromis** : il a quitté le périmètre où il était rangé.",
        "",
    ]
    if inc["fingerprints"]:
        lignes += ["Empreinte(s) : `" + "`, `".join(inc["fingerprints"]) + "` — sha256 tronqué. "
                   "La valeur n'est volontairement reproduite nulle part : ni ici, ni dans le fil, "
                   "ni dans le journal.", ""]
    if rm_courant:
        lignes += [f"Vu pendant le travail sur RM{rm_courant}.", ""]
    lignes += [
        "## À faire",
        "",
        "- [ ] Régénérer le secret chez son émetteur.",
        "- [ ] Reporter la nouvelle valeur là où elle est lue (configuration, vault, `.env`).",
        "- [ ] Vérifier que ce qui s'en servait fonctionne encore.",
        "- [ ] Si l'ancien est encore actif, le révoquer explicitement.",
        "",
        "## Critères d'acceptation",
        "",
        "- [ ] L'ancienne valeur ne fonctionne plus (vérifié par un appel qui échoue).",
        "- [ ] La nouvelle est en place et le service qui s'en sert répond.",
    ]
    return "\n".join(lignes)


def commande_ticket(inc, rm_courant):
    """L'argv exact de création du ticket de rotation — extraite pour être testable.

    C'est ici que se lit l'arbitrage du 2026-09-21 : type `security`, priorité
    `immediat`. Un test vérifie cet argv plutôt que d'ouvrir un vrai ticket.
    """
    quoi = ", ".join(inc["labels"]) if inc["labels"] else "secret exposé en séance"
    titre = f"Sécurité : régénérer un secret exposé en séance ({quoi})"[:120]
    return [sys.executable, str(HERE / "pm-task-add.py"),
            "--title", titre, "--type", "security", "--priority", "immediat",
            "--description", corps_ticket(inc, rm_courant),
            "--not-duplicate", "incident de sécurité distinct : chaque exposition a sa rotation",
            "--porcelain"]


def ouvrir_ticket_rotation(inc, cwd, rm_courant, dry_run=False):
    """Crée le ticket de rotation. Rend son id, ou None.

    Priorité `immediat` (RM3275) : c'est précisément le cas qui a motivé ce cran —
    ce pour quoi on lâche ce qu'on est en train de faire.
    """
    cmd = commande_ticket(inc, rm_courant)
    if dry_run:
        # On ne renvoie pas la commande comme « souci » : elle finirait dans le
        # message du fil, qui doit rester lisible. Le dry-run la montre à part.
        print("  (dry-run) " + " ".join(cmd[:8]) + " …", file=sys.stderr)
        return None, None
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=90, cwd=cwd or None)
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"échec de création : {type(e).__name__}"
    if p.returncode != 0:
        return None, f"pm-task-add a échoué (code {p.returncode}) : {(p.stderr or '')[-300:]}"
    for ligne in (p.stdout or "").splitlines():
        if ligne.strip().isdigit():
            return int(ligne.strip()), None
    return None, "id de ticket illisible dans la sortie de pm-task-add"


def journaliser(rm_courant, msg, cwd):
    """Append au `.log.md` du ticket courant — l'incident survit à la session."""
    if not rm_courant:
        return False
    try:
        from pm_paths import PMConfig
        md = PMConfig.load().find_task(rm_courant)
        if not md:
            return False
        log = md.parent / md.name.replace(".md", ".log.md")
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
        with log.open("a", encoding="utf-8") as f:
            f.write(f"\n## {ts} — Secret détecté dans le transcript (pm-secret-watch)\n"
                    f"Tokens : 0 | Durée : 0 min\n\n{msg}\n")
        return True
    except Exception:
        return False


def traiter(montre, dit, cwd=None, sid=None, rm_courant=None, dry_run=False):
    """Cœur du hook. Rend un dict de ce qui a été fait (ou sauté, et pourquoi)."""
    inc = pm_secret_scan.incident(montre, dit)
    if not inc:
        return {"incident": False}

    etat = _etat_lire()
    vus = etat.setdefault("incidents", {})
    sessions = etat.setdefault("sessions", {})
    deja = vus.get(inc["key"])
    if deja:
        # Même secret, nouveau tour : on fait remonter le fil (pm_notify compte les
        # répétitions) mais on n'ouvre pas un second ticket.
        if not dry_run:
            try:
                import pm_notify
                pm_notify.add("session", "critical", deja.get("msg") or message_notification(
                    inc, rm_courant, deja.get("rm_rotation"), False),
                    user=pm_notify.owner(), ref=f"RM{deja.get('rm_rotation') or rm_courant or ''}",
                    sid=sid)
            except Exception:
                pass
        return {"incident": True, "deja_connu": True, "rm_rotation": deja.get("rm_rotation")}

    n = int(sessions.get(str(sid), 0)) if sid else 0
    plafond = int(os.environ.get("PM_SECRET_WATCH_MAX") or MAX_TICKETS_DEFAUT)
    plafonne = n >= plafond

    rm_rotation, souci = (None, None)
    if not plafonne:
        rm_rotation, souci = ouvrir_ticket_rotation(inc, cwd, rm_courant, dry_run=dry_run)

    msg = message_notification(inc, rm_courant, rm_rotation, plafonne)
    if souci:
        msg += f" ⚠ {souci}"

    if not dry_run:
        try:
            import pm_notify
            pm_notify.add("session", "critical", msg, user=pm_notify.owner(),
                          ref=f"RM{rm_rotation or rm_courant or ''}", sid=sid)
        except Exception:
            pass
        if rm_rotation and rm_courant:
            try:
                subprocess.run([sys.executable, str(HERE / "pm-task-link.py"), "add",
                                str(rm_rotation), str(rm_courant), "--type", "relates",
                                "--cross-project"],
                               capture_output=True, text=True, timeout=60, cwd=cwd or None)
            except (OSError, subprocess.SubprocessError):
                pass
        journaliser(rm_courant, msg, cwd)
        vus[inc["key"]] = {"ts": datetime.now().isoformat(timespec="seconds"),
                           "labels": inc["labels"], "rm_rotation": rm_rotation, "msg": msg}
        if sid and rm_rotation:
            sessions[str(sid)] = n + 1
        _etat_ecrire(etat)

    return {"incident": True, "deja_connu": False, "rm_rotation": rm_rotation,
            "plafonne": plafonne, "message": msg, "labels": inc["labels"],
            "fingerprints": inc["fingerprints"], "souci": souci}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transcript", help="Fichier .jsonl de transcript (défaut : celui du payload)")
    ap.add_argument("--text", help="Texte à examiner directement, au lieu d'un transcript")
    ap.add_argument("--cwd", help="Dossier de travail (résolution du projet et du ticket)")
    ap.add_argument("--session", help="Identifiant de session")
    ap.add_argument("--dry-run", action="store_true", help="Dit ce qui serait fait, n'écrit rien")
    ap.add_argument("--forget", action="store_true", help="Oublie les incidents mémorisés")
    args = ap.parse_args()

    if args.forget:
        _etat_ecrire({})
        print("✓ incidents oubliés")
        return

    payload = {}
    if not args.text and not args.transcript:
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except (ValueError, OSError):
            payload = {}

    cwd = args.cwd or payload.get("cwd") or os.getcwd()
    sid = args.session or payload.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID")

    if args.text:
        montre = dit = args.text
        rm_courant = None
    else:
        tp = args.transcript or payload.get("transcript_path")
        if not tp:
            return
        tick = _mod("pm-task-tick.py", "pm_task_tick")
        events = tick._load_transcript(tp)
        if not events:
            return
        montre, dit = dernier_tour(events)
        try:
            rm_courant, _ = tick.resolve_current_rm_id(cwd, str(tp))
        except Exception:
            rm_courant = None

    res = traiter(montre, dit, cwd=cwd, sid=sid, rm_courant=rm_courant, dry_run=args.dry_run)

    if not res.get("incident"):
        if args.dry_run or args.text:
            print("rien à signaler")
        return
    if res.get("deja_connu"):
        print(f"incident déjà connu — rotation suivie par RM{res.get('rm_rotation')}")
        return
    print(res.get("message", "incident détecté"))
    if res.get("rm_rotation"):
        print(f"✓ ticket de rotation RM{res['rm_rotation']} (security, priorité immediat)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # un hook ne fait jamais échouer le tour de l'agent
        print(f"pm-secret-watch : {type(e).__name__} — {e}", file=sys.stderr)
