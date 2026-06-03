#!/usr/bin/env python3
"""pm-task-metrics-push — Pousse les métriques temps/tokens d'une tâche vers Redmine.

Pont MD → Redmine pour la traçabilité ROI (NORMS § « ROI assisté par IA » →
« Documentation dans Redmine » + « Journalisation par commit »). Le hook
`pm-task-tick` reste la base de mesure (il écrit le frontmatter) ; ce script
publie ces mesures côté Redmine. Les IDs de CF/activités viennent de la source
unique `redmine.reference.yml` (via redmine_utils).

Trois modes (combinables) :

  --estimate         Pousse l'estimation (frontmatter `estimate`) vers les champs :
                       estimate.tokens            → CF « Tokens prévus » (21)
                       estimate.ai_time_minutes/60 → CF « Temps estimé IA (h) » (22)
                       estimate.human_time_minutes/60 → estimated_hours (natif)
                     À faire à la création, à la prise de ticket si manquante, et
                     à la maj de description si l'estimation a changé.

  --commit <hash>    Saisie de temps pour le travail depuis le dernier report :
                       hours        = delta `ai_time_total_minutes` ÷ 60
                       activity_id  = --activity (défaut: debug)
                       spent_on     = date du commit
                       comments     = <hash> <sujet>
                       CF « Tokens » (16) = delta `tokens_total`
                     Puis resync CF « Tokens passés » (17) = tokens_total (cumul).
                     Poste une note Redmine selon traceability.commit_note_level
                     (work|all|none) — note détaillée si --note fourni.

  --cumul            Resync seul du CF « Tokens passés » (17) = tokens_total.

Idempotence : les deltas sont calculés vs `metrics.reported_*` du frontmatter,
avancés seulement après un report réussi. Relancer --commit sur le même état ne
recrée pas de saisie (delta nul → skip).
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
import redmine_utils

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)

# Alias d'activité → nom dans redmine.reference.yml :: activities.
ACTIVITY_ALIASES = {
    "dev":      "Développement",
    "debug":    "Développement/Debug",
    "sysadmin": "SysAdmin/Conf/Debug",
    "audit":    "Audit/Analyse",
}


def load_traceability_level():
    """Lit pm.config.yml :: traceability.commit_note_level (défaut 'work')."""
    cfg_path = Path(__file__).resolve().parent.parent / "pm.config.yml"
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return "work"
    return ((cfg.get("traceability") or {}).get("commit_note_level") or "work")


def resolve_activity_id(alias_or_id):
    """Alias ('debug', 'dev', …) ou id entier → activity_id Redmine."""
    if alias_or_id is None:
        alias_or_id = "debug"
    s = str(alias_or_id)
    if s.isdigit():
        return int(s)
    name = ACTIVITY_ALIASES.get(s)
    if name is None:
        sys.exit(f"ERREUR : activité inconnue '{s}'. Alias : {', '.join(ACTIVITY_ALIASES)} "
                 f"(ou un id entier).")
    activities = redmine_utils.load_reference().get("activities") or {}
    for aid, aname in activities.items():
        if aname == name:
            return aid
    sys.exit(f"ERREUR : activité '{name}' absente de redmine.reference.yml :: activities.")


def read_task(rm_id):
    """Retourne (md_path, fm_dict, m_match). Sys.exit si introuvable."""
    cfg = PMConfig.load()
    md_path = cfg.find_task(rm_id)
    if not md_path:
        sys.exit(f"ERREUR : RM{rm_id} introuvable")
    content = md_path.read_text(encoding="utf-8")
    m = FM_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : pas de frontmatter dans {md_path}")
    return md_path, (yaml.safe_load(m.group(2)) or {}), m


def write_task_fm(md_path, fm, m):
    """Réécrit le MD avec le frontmatter modifié (corps préservé)."""
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    md_path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}", encoding="utf-8")


def get_metrics(fm):
    """Bloc `metrics` du frontmatter (créé si absent), normalisé."""
    mt = fm.get("metrics") or {}
    return {
        "estimate_pushed_at": mt.get("estimate_pushed_at"),
        "reported_tokens": mt.get("reported_tokens") or 0,
        "reported_ai_minutes": mt.get("reported_ai_minutes") or 0,
        "last_time_entry_id": mt.get("last_time_entry_id"),
    }


def git_commit_meta(repo, commit):
    """(date 'YYYY-MM-DD', sujet, hash court) du commit, ou sys.exit si introuvable."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "show", "-s", "--format=%cs%n%s%n%h", commit],
            capture_output=True, text=True, check=True).stdout.splitlines()
    except subprocess.CalledProcessError:
        sys.exit(f"ERREUR : commit '{commit}' introuvable dans {repo}")
    return ((out[0] if out else None),
            (out[1] if len(out) > 1 else ""),
            (out[2] if len(out) > 2 else str(commit)[:7]))


# ── Modes ────────────────────────────────────────────────────────────────────

def _verify_pushed(rm_id, cfs, est_hours):
    """Re-GET et avertit si un CF/estimated_hours poussé n'a pas pris (silent drop)."""
    iss = redmine_utils.fetch_issue(rm_id)
    live = {c["id"]: (c.get("value") or "") for c in iss.get("custom_fields", [])}
    present = set(live)
    for c in (cfs or []):
        cid = c["id"]
        if cid not in present:
            print(f"  ⚠ CF{cid} non présent sur le ticket (champ non associé au tracker "
                  f"'{(iss.get('tracker') or {}).get('name')}' ?) — valeur ignorée par Redmine.",
                  file=sys.stderr)
        elif str(live[cid]) != str(c["value"]):
            print(f"  ⚠ CF{cid} = {live[cid]!r} après push (attendu {c['value']!r}) — drop probable.",
                  file=sys.stderr)
    if est_hours is not None:
        got = iss.get("estimated_hours")
        if got is None or abs(float(got) - float(est_hours)) > 0.001:
            print(f"  ⚠ estimated_hours = {got!r} après push (attendu {est_hours}).", file=sys.stderr)


def resolve_llm_tier(estimated_model):
    """Mappe un nom de modèle → value id du CF « LLM prévu » via llm_tiers.model_match.

    Retourne (value_id_str, label) ou (None, None) si pas de modèle / pas de match.
    """
    if not estimated_model:
        return None, None
    tiers = redmine_utils.load_reference().get("llm_tiers") or {}
    matches = tiers.get("model_match") or {}
    low = str(estimated_model).lower()
    for substr, vid in matches.items():
        if str(substr).lower() in low:
            label = (tiers.get("values") or {}).get(vid)
            return str(vid), label
    return None, None


def do_estimate(rm_id, fm, md_path, m, dry_run):
    est = fm.get("estimate") or {}
    cf21 = redmine_utils.cf_id_by_name("Tokens prévus")
    cf22 = redmine_utils.cf_id_by_name("Temps estimé IA (h)")
    cf25 = redmine_utils.cf_id_by_name("LLM prévu")
    cfs = []
    if est.get("tokens") is not None and cf21:
        cfs.append({"id": cf21, "value": str(int(est["tokens"]))})
    est_hours = None
    if est.get("human_time_minutes") is not None:
        est_hours = round(est["human_time_minutes"] / 60.0, 2)
    if est.get("ai_time_minutes") is not None and cf22:
        cfs.append({"id": cf22, "value": str(round(est["ai_time_minutes"] / 60.0, 2))})
    if cf25:
        tier_id, tier_label = resolve_llm_tier(est.get("estimated_model"))
        if tier_id:
            cfs.append({"id": cf25, "value": tier_id})
        elif est.get("estimated_model"):
            print(f"  ⚠ LLM prévu : modèle {est['estimated_model']!r} non mappé "
                  f"(llm_tiers.model_match) → CF{cf25} non poussé.", file=sys.stderr)

    if not cfs and est_hours is None:
        print("  · estimation : rien à pousser (estimate vide)")
        return False
    desc = [f"CF{c['id']}={c['value']}" for c in cfs]
    if est_hours is not None:
        desc.append(f"estimated_hours={est_hours}")
    if dry_run:
        print(f"--dry-run : estimation → {', '.join(desc)}")
        return False
    ok, err = redmine_utils.update_issue_fields(rm_id, custom_fields=cfs or None,
                                                estimated_hours=est_hours)
    if not ok:
        sys.exit(f"ERREUR push estimation : {err}")
    print(f"✓ estimation poussée : {', '.join(desc)}")
    # Vérification : Redmine renvoie 204 même quand il *drop* un CF non associé au
    # tracker ou interdit par permissions (cf. knowledge/redmine/api.md). On re-GET
    # pour confirmer que chaque valeur a bien pris.
    _verify_pushed(rm_id, cfs, est_hours)
    mt = get_metrics(fm)
    mt["estimate_pushed_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    fm["metrics"] = mt
    return True


def do_cumul(rm_id, fm, dry_run):
    cf17 = redmine_utils.cf_id_by_name("Tokens passés")
    total = int(fm.get("tokens_total") or 0)
    if not cf17:
        print("  · cumul : CF 'Tokens passés' absent de la référence — skip")
        return
    if dry_run:
        print(f"--dry-run : cumul CF{cf17} (Tokens passés) = {total}")
        return
    ok, err = redmine_utils.update_issue_fields(rm_id, custom_fields=[{"id": cf17, "value": str(total)}])
    if not ok:
        sys.exit(f"ERREUR resync cumul : {err}")
    print(f"✓ cumul CF{cf17} (Tokens passés) = {total}")


def do_commit(rm_id, commit, repo, activity, note, fm, md_path, m, dry_run):
    mt = get_metrics(fm)
    cur_tokens = int(fm.get("tokens_total") or 0)
    cur_ai = float(fm.get("ai_time_total_minutes") or 0)
    delta_tokens = cur_tokens - int(mt["reported_tokens"])
    delta_ai = round(cur_ai - float(mt["reported_ai_minutes"]), 2)
    hours = round(delta_ai / 60.0, 2)
    date, subject, short = git_commit_meta(repo, commit)
    activity_id = resolve_activity_id(activity)
    cf16 = redmine_utils.cf_id_by_name("Tokens")

    print(f"  · commit {short} ({date}) : Δtokens={delta_tokens}, ΔIA={delta_ai} min → {hours} h, "
          f"activité={activity_id}")

    te_id = None
    if hours <= 0:
        print("  ⚠ delta temps nul → pas de saisie de temps (le cumul tokens reste poussé via --cumul).")
    elif dry_run:
        print(f"--dry-run : POST time_entry hours={hours} activity={activity_id} "
              f"spent_on={date} CF{cf16}={delta_tokens} comments='{short} {subject}'")
    else:
        cfs = [{"id": cf16, "value": str(delta_tokens)}] if cf16 else None
        ok, res = redmine_utils.create_time_entry(
            rm_id, hours=hours, activity_id=activity_id, spent_on=date,
            comments=f"{short} {subject}", custom_fields=cfs)
        if not ok:
            sys.exit(f"ERREUR création time_entry : {res}")
        te_id = res
        print(f"✓ time_entry #{te_id} : {hours} h, CF{cf16} (Tokens)={delta_tokens}")

    # Cumul CF17 (toujours, capture les tokens même si temps nul).
    do_cumul(rm_id, fm, dry_run)

    # Note Redmine selon le niveau de traçabilité.
    level = load_traceability_level()
    should_note = (level == "all") or (level == "work" and note)
    if should_note:
        body = note or f"Commit {short} — {subject}"
        metrics_line = (f"\n\n_Réf commit `{short}` · {hours} h IA · "
                        f"{delta_tokens} tokens (cumul {cur_tokens})._")
        full_note = body + metrics_line
        if dry_run:
            print(f"--dry-run : note Redmine (niveau={level}) :\n{full_note}")
        else:
            redmine_utils.add_issue_note(rm_id, full_note)
            print(f"✓ note Redmine postée (niveau={level})")
    elif level == "none":
        print("  · note : commit_note_level=none → pas de note")
    else:
        print("  · note : commit sans --note (housekeeping) → pas de note (niveau=work)")

    if dry_run:
        return False
    # Avance les marqueurs : tokens toujours (cumul poussé) ; ai seulement si saisi.
    mt["reported_tokens"] = cur_tokens
    if hours > 0:
        mt["reported_ai_minutes"] = cur_ai
        mt["last_time_entry_id"] = te_id
    fm["metrics"] = mt
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rm-id", type=int, required=True)
    ap.add_argument("--estimate", action="store_true", help="Pousse l'estimation (CF21/22 + estimated_hours)")
    ap.add_argument("--commit", metavar="HASH", help="Saisie de temps pour ce commit (delta depuis dernier report)")
    ap.add_argument("--cumul", action="store_true", help="Resync seul du cumul CF17 (Tokens passés)")
    ap.add_argument("--activity", default="debug",
                    help=f"Activité du time_entry : {', '.join(ACTIVITY_ALIASES)} ou un id (défaut: debug)")
    ap.add_argument("--repo", default=".", help="Dépôt git du commit (défaut: cwd)")
    ap.add_argument("--note", help="Note détaillée à publier avec le commit (signale un commit de travail)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not (args.estimate or args.commit or args.cumul):
        sys.exit("ERREUR : préciser au moins un mode (--estimate / --commit / --cumul).")

    md_path, fm, m = read_task(args.rm_id)
    dirty = False

    if args.estimate:
        dirty = do_estimate(args.rm_id, fm, md_path, m, args.dry_run) or dirty
    if args.commit:
        repo = Path(args.repo).resolve()
        dirty = do_commit(args.rm_id, args.commit, repo, args.activity, args.note,
                          fm, md_path, m, args.dry_run) or dirty
    if args.cumul and not args.commit:   # --commit fait déjà le cumul
        do_cumul(args.rm_id, fm, args.dry_run)

    if dirty and not args.dry_run:
        write_task_fm(md_path, fm, m)
        print(f"✓ frontmatter métriques mis à jour : {md_path.name}")


if __name__ == "__main__":
    main()
