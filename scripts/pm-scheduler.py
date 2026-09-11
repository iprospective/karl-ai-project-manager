#!/usr/bin/env python3
"""pm-scheduler — ordonnanceur unique des travaux périodiques PM (RM2792, lot 1).

UN cron système, toutes les 5 minutes, appelle `pm-scheduler.py run`. C'est lui qui
lit le registre `jobs.reference.yml`, décide de ce qui est dû, et l'exécute.

    */5 * * * * python3 "$PM_DIR/scripts/pm-scheduler.py" run >> "$LOG_DIR/scheduler.log" 2>&1

Ce que le crontab ne savait pas faire, et qui manquait :

  * **un état consultable** — « quand est-ce passé la dernière fois, et comment ? ».
    Avec des crons épars, la seule réponse était de fouiller des journaux séparés,
    quand ils existaient ;
  * **un verrou par travail** — cron relance un job même si le précédent tourne
    encore. Deux orchestrateurs concurrents s'assignent les mêmes tâches ;
  * **l'isolation des pannes** — un job qui échoue ou déborde ne doit pas empêcher
    les autres de tourner ;
  * **un point unique où lire ce qui tourne**. La moitié des jobs n'étaient
    d'ailleurs installés nulle part : seulement décrits dans `cron.example.sh`.

Deux choix explicites, écrits ici parce qu'ils surprennent si on ne les connaît pas :

  * **pas de rattrapage en cascade.** Machine éteinte trois jours ⇒ un job quotidien
    tourne UNE fois, pas trois. Rejouer trois fois un résumé quotidien ne rend pas
    trois jours de travail, ça fait trois fois du bruit ;
  * **un job jamais vu est ARMÉ, pas exécuté.** À sa première rencontre, il est
    inscrit à l'état avec l'instant courant pour repère, et attend sa prochaine
    occurrence. Sans cela, ajouter un job quotidien au registre à 15 h le ferait
    partir immédiatement au titre de l'occurrence de 6 h déjà passée.

Sous-commandes :
    run [--only ID] [--force] [--dry-run]   passage d'ordonnancement (le cron)
    list [--json]                           registre + état (dernier passage, prochain dû)
    history [--job ID] [-n N]               trace des exécutions
    check                                   valide le registre (schéma, cron, commandes)
    crontab                                 imprime LA ligne de crontab à installer

Fichiers (sous `var/scheduler/`, hors arbre tracké) :
    state.json      dernier passage, code retour, durée, échecs consécutifs
    history.jsonl   une ligne par exécution (append-only, taillé à 2000 lignes)
    log/<id>.log    sortie complète de chaque job
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:                                       # RM3095 : journal structuré, jamais bloquant
    import pm_log
    journal = pm_log.journal("pm-scheduler", "system")
except ImportError:                        # pm_log absent (clone partiel) : on continue muet
    journal = None

import pm_paths
from pm_lock import LockTimeout, atomic_write, resource_lock
from pm_output import out
from pm_paths import PMConfig

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

REGISTRY_NAME = "jobs.reference.yml"
# Le registre voyage AVEC le code, comme redmine.reference.yml : résolu depuis le
# dépôt du script, pas depuis `cfg.pm_dir`. Sinon un worktree de dev exécuterait
# le registre de la production — ou l'inverse, ce qui est pire.
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TIMEOUT = 900
HISTORY_MAX = 2000
# Fenêtre de rattrapage : au-delà, une occurrence manquée est périmée, pas en retard.
CATCHUP_HORIZON_MIN = 60 * 24 * 2


# ── Expressions cron ──────────────────────────────────────────────────────

def _field(spec, lo, hi, *, dow=False):
    """Ensemble des valeurs couvertes par un champ cron. Lève ValueError si invalide."""
    values = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"champ vide dans {spec!r}")
        step = 1
        if "/" in part:
            part, _, raw_step = part.partition("/")
            if not raw_step.isdigit() or int(raw_step) < 1:
                raise ValueError(f"pas invalide dans {spec!r}")
            step = int(raw_step)
        if part == "*":
            # `*` couvre tout l'intervalle TEL QUEL. Le normaliser en jour-de-semaine
            # (7 % 7 = 0) écraserait la borne haute sur la basse et ne laisserait que
            # le dimanche — panne silencieuse : les jobs ne seraient partis qu'un jour
            # sur sept, ce que seul un test étalé sur plusieurs jours révèle.
            values.update(range(lo, hi + 1, step))
            continue
        if "-" in part.lstrip("-"):
            a, _, b = part.partition("-")
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        if dow:                       # cron : 0 ET 7 valent dimanche
            start, end = start % 7, end % 7
            if end < start:
                start, end = end, start
        if start < lo or end > hi or end < start:
            raise ValueError(f"valeur hors bornes [{lo}-{hi}] dans {spec!r}")
        values.update(range(start, end + 1, step))
    return values


def day_match(fields, when):
    """Partie « date » d'une expression cron : mois + jour du mois / de semaine."""
    _minute, _hour, dom, month, dow = fields
    if when.month not in _field(month, 1, 12):
        return False
    m_dom = when.day in _field(dom, 1, 31)
    m_dow = (when.isoweekday() % 7) in _field(dow, 0, 7, dow=True)
    if dom.strip() != "*" and dow.strip() != "*":
        return m_dom or m_dow
    return m_dom and m_dow


def cron_match(expr, when):
    """`when` tombe-t-il sur une occurrence de l'expression cron 5 champs ?

    Sémantique cron respectée sur le couple jour-du-mois / jour-de-semaine : quand
    les DEUX sont restreints, la correspondance est un **OU** (« le 1er du mois ou
    tous les lundis »), pas un ET. C'est contre-intuitif, et c'est la règle.
    """
    fields = str(expr).split()
    if len(fields) != 5:
        raise ValueError(f"expression cron à 5 champs attendue, reçu {expr!r}")
    if when.minute not in _field(fields[0], 0, 59):
        return False
    if when.hour not in _field(fields[1], 0, 23):
        return False
    return day_match(fields, when)


def due_since(expr, since, now):
    """Une occurrence est-elle tombée dans ]since, now] ? (`since=None` → False)

    On remonte minute par minute plutôt que de calculer la prochaine occurrence :
    c'est quelques milliers d'itérations au pire, et ça évite d'écrire — donc de
    déboguer — l'arithmétique inverse d'un calendrier.
    """
    if since is None:
        return False
    cur = now.replace(second=0, microsecond=0)
    floor = max(since, now - timedelta(minutes=CATCHUP_HORIZON_MIN))
    while cur > floor:
        if cron_match(expr, cur):
            return True
        cur -= timedelta(minutes=1)
    return False


def next_occurrence(expr, after, limit_days=370):
    """Prochaine occurrence strictement après `after` (None si aucune d'ici `limit_days`)."""
    fields = str(expr).split()
    if len(fields) != 5:
        raise ValueError(f"expression cron à 5 champs attendue, reçu {expr!r}")
    cur = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = after + timedelta(days=limit_days)
    while cur <= end:
        # Un job mensuel demanderait un demi-million de tours si l'on avançait
        # minute par minute sans jamais regarder la date : on saute au lendemain
        # dès que le jour est exclu.
        if not day_match(fields, cur):
            cur = (cur + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if cron_match(expr, cur):
            return cur
        cur += timedelta(minutes=1)
    return None


# ── Registre ──────────────────────────────────────────────────────────────

def registry_path(cfg):
    return REPO_ROOT / REGISTRY_NAME


def load_registry(cfg):
    p = registry_path(cfg)
    if not p.is_file():
        out.fail(f"registre introuvable : {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    jobs = data.get("jobs") or {}
    if not isinstance(jobs, dict):
        out.fail(f"{REGISTRY_NAME} : `jobs` doit être une table id → définition")
    return jobs


def validate(jobs):
    """[(job_id, problème)] — vide si le registre est sain."""
    problems = []
    for jid, spec in jobs.items():
        if not isinstance(spec, dict):
            problems.append((jid, "définition non-table"))
            continue
        if not spec.get("description"):
            problems.append((jid, "`description` manquante"))
        has_cmd, has_shell = bool(spec.get("command")), bool(spec.get("shell"))
        if has_cmd == has_shell:
            problems.append((jid, "exactement un de `command` / `shell` est requis"))
        if has_cmd and not isinstance(spec["command"], list):
            problems.append((jid, "`command` doit être une liste argv"))
        try:
            expr = spec.get("schedule")
            if not expr:
                raise ValueError("`schedule` manquant")
            cron_match(expr, datetime.now())
        except (ValueError, TypeError) as e:
            problems.append((jid, f"schedule : {e}"))
        timeout = spec.get("timeout", DEFAULT_TIMEOUT)
        if not isinstance(timeout, int) or timeout <= 0:
            problems.append((jid, "`timeout` doit être un entier de secondes > 0"))
    return problems


# ── État ──────────────────────────────────────────────────────────────────

def sched_dir(cfg):
    d = Path(cfg.state_dir) / "scheduler"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_state(cfg):
    p = sched_dir(cfg) / "state.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except json.JSONDecodeError:
        # Un état illisible ne doit pas immobiliser l'ordonnanceur : on repart
        # d'un état vide (donc tous les jobs « armés »), et on le dit.
        out.warn("state.json illisible — repartir d'un état vide (jobs ré-armés)")
        return {}


def save_state(cfg, state):
    atomic_write(sched_dir(cfg) / "state.json",
                 json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def append_history(cfg, entry):
    p = sched_dir(cfg) / "history.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    lines = p.read_text(encoding="utf-8").splitlines()
    if len(lines) > HISTORY_MAX:
        atomic_write(p, "\n".join(lines[-HISTORY_MAX:]) + "\n")


def parse_ts(value):
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


# ── Exécution ─────────────────────────────────────────────────────────────

def build_command(cfg, spec):
    """(argv, use_shell) — `shell:` source pm.env et .env avant la commande.

    Le code Python charge sa config via `pm_paths` ; une ligne shell, non. Les
    jobs shell héritaient donc d'un environnement amputé ($PROJECTS_PATH vide…),
    piège déjà documenté dans `cron.example.sh` : on le règle ici, une fois.
    """
    if spec.get("command"):
        return [str(a) for a in spec["command"]], False
    # Exactement les mêmes fichiers que ceux résolus par pm_paths pour le code
    # Python : sans quoi les deux familles de jobs ne verraient pas le même
    # environnement, et l'écart ne se remarquerait qu'en production.
    prelude = "set -a; "
    for resolver in (pm_paths._instance_env, pm_paths._secrets_env):
        try:
            env_file = resolver(REPO_ROOT)
        except Exception:
            env_file = None
        if env_file:
            prelude += f". {shlex.quote(str(env_file))}; "
    prelude += "set +a; "
    return ["bash", "-c", prelude + str(spec["shell"]).strip()], True


def run_job(cfg, jid, spec, *, dry_run=False):
    """Exécute un job sous SON verrou. Retourne l'entrée d'historique.

    Ne lève jamais : un job qui casse ne doit pas emporter le passage entier —
    c'est la moitié de l'intérêt d'avoir un ordonnanceur plutôt que dix crons.
    """
    started = datetime.now()
    argv, _shell = build_command(cfg, spec)
    entry = {"job": jid, "started": started.isoformat(timespec="seconds")}
    if dry_run:
        entry.update(status="dry-run", rc=None, duration_s=0,
                     command=" ".join(argv[:3]) + (" …" if len(argv) > 3 else ""))
        return entry

    cwd = REPO_ROOT / str(spec.get("cwd") or ".")
    timeout = int(spec.get("timeout", DEFAULT_TIMEOUT))
    logs = sched_dir(cfg) / "log"
    logs.mkdir(parents=True, exist_ok=True)
    try:
        with resource_lock(sched_dir(cfg) / f"{jid}.lock", timeout=0):
            t0 = time.monotonic()
            try:
                proc = subprocess.run(argv, cwd=str(cwd), capture_output=True,
                                      text=True, timeout=timeout)
                rc, output = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
                status = "ok" if rc == 0 else "échec"
            except subprocess.TimeoutExpired as e:
                rc, status = None, "timeout"
                output = (e.stdout or "") + (e.stderr or "") if isinstance(e.stdout, str) else ""
                output += f"\n[pm-scheduler] tué après {timeout} s"
            except OSError as e:
                rc, status, output = None, "injoignable", f"{e}"
            duration = round(time.monotonic() - t0, 1)
    except LockTimeout:
        # Le passage précédent tourne encore : c'est un fait à tracer, pas un échec.
        entry.update(status="déjà en cours", rc=None, duration_s=0)
        return entry

    with (logs / f"{jid}.log").open("a", encoding="utf-8") as f:
        f.write(f"\n===== {started.isoformat(timespec='seconds')} — {status} "
                f"(rc={rc}, {duration}s) =====\n{output}")
    entry.update(status=status, rc=rc, duration_s=duration,
                 tail=output.strip()[-500:] or None)
    return entry


# ── Sous-commandes ────────────────────────────────────────────────────────

def cmd_run(cfg, args):
    jobs = load_registry(cfg)
    problems = validate(jobs)
    if problems:
        for jid, msg in problems:
            out.warn(f"{jid} : {msg}")
        out.fail(f"{REGISTRY_NAME} invalide — aucun job lancé "
                 f"({len(problems)} problème(s), cf. pm-scheduler.py check)")

    now = datetime.now()
    try:
        # Verrou de PASSAGE : deux ordonnanceurs concurrents ré-évalueraient le même
        # état et pourraient doubler un job dont le verrou vient d'être relâché.
        with resource_lock(sched_dir(cfg) / "scheduler.lock", timeout=0):
            state = load_state(cfg)
            ran, skipped, armed = [], 0, []
            for jid, spec in jobs.items():
                if args.only and jid != args.only:
                    continue
                if not spec.get("enabled", True) and not args.force:
                    skipped += 1
                    continue
                st = state.setdefault(jid, {})
                since = parse_ts(st.get("last_start"))
                if since is None and not args.force:
                    # Premier contact : on arme, on n'exécute pas (cf. docstring).
                    st["last_start"] = now.isoformat(timespec="seconds")
                    st["status"] = "armé"
                    armed.append(jid)
                    continue
                if not args.force and not due_since(spec["schedule"], since, now):
                    continue
                entry = run_job(cfg, jid, spec, dry_run=args.dry_run)
                ran.append(entry)
                if args.dry_run:
                    continue
                append_history(cfg, entry)
                ok = entry.get("status") == "ok"
                if journal:
                    (journal.info if ok else journal.warn)(
                        f"travail périodique « {jid} » : {entry.get('status')}",
                        job=jid, rc=entry.get("rc"), ms=round((entry.get("duration_s") or 0) * 1000))
                if not ok:
                    # le journal trace, le fil INTERPELLE : un travail qui échoue en boucle ne doit pas
                    # produire une ligne par passage, d'où l'empreinte qui fait remonter la même entrée
                    try:
                        import pm_notify
                        pm_notify.add("scheduler", "warn",
                                      f"travail périodique « {jid} » : {entry.get('status')}",
                                      job=jid, rc=entry.get("rc"))
                    except Exception:
                        pass
                st["last_start"] = entry["started"]
                st["status"] = entry["status"]
                st["rc"] = entry["rc"]
                st["duration_s"] = entry["duration_s"]
                st["consecutive_failures"] = (
                    0 if entry["status"] == "ok"
                    else int(st.get("consecutive_failures") or 0) + 1)
            if not args.dry_run:
                save_state(cfg, state)
    except LockTimeout:
        out.info("passage précédent encore en cours — rien à faire")
        return

    if armed:
        out.info(f"armé(s) sans exécuter (premier contact) : {', '.join(armed)}")
    if not ran:
        out.op("scheduler", extra=f"rien de dû ({len(jobs) - skipped} job(s) actif(s))")
        return
    out.op("scheduler", extra=f"{len(ran)} job(s)")
    for e in ran:
        mark = "✓" if e["status"] in ("ok", "dry-run") else "✗"
        print(f"  {mark} {e['job']:<20} {e['status']:<14} "
              f"rc={e['rc']} {e['duration_s']}s")
    if any(e["status"] not in ("ok", "dry-run", "déjà en cours") for e in ran):
        sys.exit(1)


def cmd_list(cfg, args):
    jobs, state, now = load_registry(cfg), load_state(cfg), datetime.now()
    rows = []
    for jid, spec in sorted(jobs.items()):
        st = state.get(jid) or {}
        last = parse_ts(st.get("last_start"))
        nxt = next_occurrence(spec.get("schedule", "* * * * *"), last or now)
        rows.append({
            "job": jid, "schedule": spec.get("schedule"),
            "enabled": bool(spec.get("enabled", True)),
            "last_start": st.get("last_start"), "status": st.get("status"),
            "rc": st.get("rc"), "duration_s": st.get("duration_s"),
            "consecutive_failures": st.get("consecutive_failures") or 0,
            "next": nxt.isoformat(timespec="minutes") if nxt else None,
        })
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    out.op("scheduler", extra=f"{len(rows)} job(s), "
                              f"{sum(1 for r in rows if r['enabled'])} actif(s)")
    for r in rows:
        flag = " " if r["enabled"] else "✗"
        fails = f"  ⚠ {r['consecutive_failures']} échec(s) d'affilée" \
            if r["consecutive_failures"] else ""
        print(f"{flag} {r['job']:<18} {str(r['schedule']):<14} "
              f"dernier {str(r['last_start'] or '—'):<20} "
              f"{str(r['status'] or '—'):<14} prochain {r['next'] or '—'}{fails}")


def cmd_history(cfg, args):
    p = sched_dir(cfg) / "history.jsonl"
    if not p.is_file():
        out.op("scheduler", extra="aucune exécution enregistrée")
        return
    entries = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not args.job or e.get("job") == args.job:
            entries.append(e)
    for e in entries[-args.n:]:
        mark = "✓" if e.get("status") == "ok" else "✗"
        print(f"{mark} {e.get('started'):<20} {e.get('job'):<18} "
              f"{str(e.get('status')):<14} rc={e.get('rc')} {e.get('duration_s')}s")
        if args.verbose_tail and e.get("tail"):
            print("    " + e["tail"].replace("\n", "\n    "))


def cmd_check(cfg, args):
    jobs = load_registry(cfg)
    problems = validate(jobs)
    for jid, msg in problems:
        out.warn(f"{jid} : {msg}")
    if problems:
        out.fail(f"{len(problems)} problème(s) dans {REGISTRY_NAME}")
    out.op("scheduler", extra=f"{REGISTRY_NAME} valide — {len(jobs)} job(s)")


def cmd_crontab(cfg, args):
    script = Path(__file__).resolve()
    log = Path(cfg.log_dir) / "scheduler.log"
    print("# Ordonnanceur PM (RM2792) — LA ligne de crontab, et la seule.")
    print("# Elle remplace les crons par travail : le registre est jobs.reference.yml,")
    print("# `pm-scheduler.py list` dit ce qui tourne et ce qui a échoué.")
    print(f"*/5 * * * * python3 {script} run >> {log} 2>&1")


def main():
    ap = argparse.ArgumentParser(
        description="Ordonnanceur unique des travaux périodiques PM.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Passage d'ordonnancement (appelé par le cron)")
    p_run.add_argument("--only", help="Ne considérer que ce job")
    p_run.add_argument("--force", action="store_true",
                       help="Exécuter sans regarder l'échéance (ni le drapeau enabled)")
    p_run.add_argument("--dry-run", action="store_true",
                       help="Dire ce qui serait lancé, sans rien lancer ni rien écrire")

    p_list = sub.add_parser("list", help="Registre + état")
    p_list.add_argument("--json", action="store_true")

    p_hist = sub.add_parser("history", help="Trace des exécutions")
    p_hist.add_argument("--job")
    p_hist.add_argument("-n", type=int, default=30)
    p_hist.add_argument("--verbose-tail", action="store_true",
                        help="Affiche la queue de sortie conservée")

    sub.add_parser("check", help="Valide le registre")
    sub.add_parser("crontab", help="Imprime LA ligne de crontab à installer")

    args = ap.parse_args()
    cfg = PMConfig.load()
    {"run": cmd_run, "list": cmd_list, "history": cmd_history,
     "check": cmd_check, "crontab": cmd_crontab}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
