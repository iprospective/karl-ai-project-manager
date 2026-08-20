#!/usr/bin/env python3
"""pm-task-add — Crée une nouvelle tâche (POST Redmine + MD + log + valide).

Usage :
    pm-task-add.py --title "Setup CI GitLab" --type infrastructure --priority high
    pm-task-add.py --title "..." --description "Détails..." --tags "ci,gitlab"
    pm-task-add.py --project iprospective/pm-ai-agents --title "..." --type feature
    pm-task-add.py --title "..." --retro              # ticket de suivi de travail déjà fait

Détection projet :
  1. --project entity/project explicite
  2. cwd via .mmi-pm symlink (comme pm-task-list)
  3. cwd dans projects_root/clients/<E>/projects/<P>/

Mapping NORMS → Redmine tracker (par défaut) :
    bugfix       → 1 (Anomalie)
    feature      → 2 (Évolution)
    assistance   → 3 (Assistance)
    autre        → 4 (Tâche)

--retro (ticket rétroactif) :
    Crée le ticket PUIS le fait traverser le state machine NORMS
    (a_faire → en_cours+self-assign → a_tester_verifier+Manager IA) en un seul
    appel. À utiliser quand l'agent crée un ticket pour tracer un travail qu'il
    vient de finir (« ticket de suivi »). Évite l'oubli récurrent des
    transitions de statut documenté dans NORMS v1.12.0 § « Prise en charge
    d'une tâche ».

Sortie dense par défaut (RM2362) : --verbose ou PM_VERBOSE=1 restaure le détail.
"""
import argparse
import re
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from pm_output import out
from pm_task import get_task_provider  # seam TaskProvider (P1/RM2543)
import pm_git
import pm_hierarchy

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")


# Taxonomie canonique des `type` de tâche → tracker Redmine (coarse).
# SOURCE DE VÉRITÉ : ce dict. Tout consommateur (cockpit karl-agent, doc) doit
# lire la liste via `--list-types`, jamais la redupliquer en dur (NORMS § « Source
# de vérité unique »). Cohérent avec `redmine.reference.yml :: trackers` et
# `type_to_activity` (research = Audit/Analyse).
# Les 14 `type` canoniques NORMS (cf. table de routage worker, NORMS §
# « Assignation »). Seuls bugfix/feature/assistance ont un tracker Redmine dédié ;
# tous les autres retombent sur « Tâche » (4) — la nature fine est portée par le
# nom du type, l'activité de temps (type_to_activity) et, à terme, le CF 20.
# Gabarit de fiche + tables type/priorité : partagés avec pm-task-import.py, qui
# ADOPTE un ticket Redmine existant au lieu d'en créer un (pm_task_md, RM2657).
from pm_task_md import (  # noqa: E402  (re-exportés : d'autres scripts les importent)
    CODE_FENCE_RE, CRITERIA_HEADING_RE, PRIORITY_TO_ID, TYPE_LABELS, TYPE_TO_TRACKER,
    build_frontmatter, has_acceptance_criteria, render_log, render_md, slugify,
)

# RM2752 — valeurs acceptées par validate-task.py pour `bug.reproducibility`.
# Deux listes qui divergeraient, c'est un ticket refusé à la validation sans que
# rien ne l'ait dit à la création : test_pm_task_add_bugfix.py les garde alignées.
VALID_REPRODUCIBILITIES = ("always", "often", "sometimes", "rarely", "never")


def _with_bug(fm, reproducibility, steps):
    """Insère le bloc `bug` juste après `type`, sans réordonner le reste."""
    out = {}
    for k, v in fm.items():
        out[k] = v
        if k == "type":
            out["bug"] = {"reproducibility": reproducibility,
                          "reproduce_steps": steps.rstrip() + "\n"}
    return out


def load_ia_manager_id():
    """Lit pm.config.yml :: ia.default_manager.redmine_id. Defaut 5 (Mathieu)."""
    cfg_path = Path(__file__).resolve().parent.parent / "pm.config.yml"
    if not cfg_path.is_file():
        return 5
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return 5
    return ((cfg.get("ia") or {}).get("default_manager") or {}).get("redmine_id", 5)


def detect_project_from_cwd(cfg):
    """Détection du projet courant — déléguée à PMConfig (overview-based,
    gère `.mmi-pm` symlink OU dossier co-localisé, RM1942)."""
    return cfg.detect_project_from_cwd()


def load_project_overview(cfg, entity, project):
    """Manifeste du projet (meta.yml, sinon frontmatter overview) — RM1994.

    Le contrôle du champ requis (redmine.project_id) est fait par l'appelant.
    """
    return cfg.project_meta(entity, project)


def main():
    # Liste machine des types canoniques (consommée par karl-agent / cockpit pour
    # peupler le sélecteur sans dupliquer la taxonomie). Traité avant argparse car
    # --title est requis pour une création normale mais pas pour un simple listing.
    if "--list-types" in sys.argv:
        import json
        print(json.dumps(
            [{"value": t, "label": TYPE_LABELS.get(t, t), "tracker": TYPE_TO_TRACKER[t]}
             for t in TYPE_TO_TRACKER],
            ensure_ascii=False))
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-types", action="store_true",
                    help="Affiche la taxonomie canonique des types (JSON) et quitte.")
    ap.add_argument("--title", required=True)
    ap.add_argument("--type", default="feature", choices=list(TYPE_TO_TRACKER))
    ap.add_argument("--priority", default="normal", choices=list(PRIORITY_TO_ID))
    ap.add_argument("--status", default="nouveau",
                    choices=["nouveau", "a_etudier_chiffrer", "a_faire", "en_cours"],
                    help="Statut initial du ticket (défaut: nouveau — ticket déposé non "
                         "trié). Si ≠ nouveau, le ticket est créé en nouveau puis "
                         "transitionné via pm-task-status-update (couplage NORMS : "
                         "auto-assignation karl pour en_cours, note, status_history).")
    ap.add_argument("--description", default="",
                    help="Description du ticket. Mets '-' pour lire l'entrée standard "
                         "(stdin) — pratique pour une description multi-ligne lisible.")
    ap.add_argument("--description-file", default=None,
                    help="Lit la description depuis un fichier ('-' = stdin). À "
                         "privilégier pour une description structurée multi-ligne "
                         "(évite les descriptions sur une seule ligne illisibles).")
    ap.add_argument("--tags", default="", help="Liste csv de tags")
    ap.add_argument("--agent-test", dest="agent_test", default="default",
                    choices=["default", "oui", "non", "demander"],
                    help="Passe agent-testeur en fin de dev (frontmatter requires_agent_test "
                         "/ CF27). default → hérite du projet (défaut système : non).")
    ap.add_argument("--target-env", default=None)
    # RM2752 — `validate-task` EXIGE `bug.reproducibility` + `bug.reproduce_steps`
    # pour type=bugfix. Aucun flag ne permettait de les poser : tout ticket bugfix
    # créé par l'outil canonique naissait invalide, et il fallait ouvrir le MD.
    ap.add_argument("--bug-reproducibility", dest="bug_reproducibility",
                    default=None, choices=list(VALID_REPRODUCIBILITIES),
                    help="Reproductibilité du bug (type=bugfix ; défaut : always)")
    ap.add_argument("--bug-steps", dest="bug_steps", default=None,
                    help="Étapes de reproduction ('-' = stdin). OBLIGATOIRE pour --type bugfix.")
    ap.add_argument("--bug-steps-file", dest="bug_steps_file", default=None,
                    help="Étapes de reproduction lues depuis un fichier ('-' = stdin).")
    # Estimation (NORMS § ROI) — poussée vers Redmine (CF21/22/25 + estimated_hours)
    # si au moins un flag est fourni. Cf. pm-task-metrics-push.py --estimate.
    ap.add_argument("--est-tokens", type=int, default=None, help="Tokens prévus (CF21)")
    ap.add_argument("--est-ai-minutes", type=float, default=None, help="Temps IA prévu en min (→ CF22 h)")
    ap.add_argument("--est-human-minutes", type=float, default=None, help="Temps humain prévu en min (→ estimated_hours)")
    ap.add_argument("--est-model", default=None, help="Modèle LLM prévu (→ palier CF25, cf. llm_tiers)")
    ap.add_argument("--est-difficulty", default=None, choices=["low", "medium", "high", "critical"])
    ap.add_argument("--est-confidence", type=float, default=None, help="Confiance 0..1")
    ap.add_argument("--no-push-estimate", action="store_true",
                    help="N'envoie pas l'estimation vers Redmine même si des flags --est-* sont fournis")
    ap.add_argument("--project", help="Override auto-detect (format: entity/project)")
    ap.add_argument("--parent", type=int, default=None, metavar="RM_ID",
                    help="Crée la tâche comme enfant de RM_ID (attribut natif Redmine "
                         "parent_issue_id). Pose parent_task côté enfant + sub_tasks "
                         "côté parent. Cf. NORMS § « Hiérarchie parent/enfant ».")
    ap.add_argument("--initiator-agent", action="store_true",
                    help="Le créateur effectif est l'agent (karl, id 79) : "
                         "cas audit autonome ou bootstrap. "
                         "Sinon par défaut : Manager IA (pm.config.yml :: ia.default_manager)")
    ap.add_argument("--retro", action="store_true",
                    help="Ticket rétroactif : après création, enchaîne automatiquement "
                         "en_cours (auto-assign agent courant) puis a_tester_verifier "
                         "(ré-assignation au Manager IA). À utiliser pour les tickets de "
                         "suivi de travail déjà livré. Cf. NORMS v1.12.0 § « Prise en "
                         "charge d'une tâche » + memory feedback-pm-ticket-workflow.")
    ap.add_argument("--start-branch", action="store_true",
                    help="Enchaîne pm-branch-start --take après création (RM2224) : "
                         "branche <id>-<slug> + prise en_cours, l'id capturé en interne "
                         "— l'agent ne manipule JAMAIS l'id (tripwire #13). "
                         "Incompatible avec --retro/--status.")
    ap.add_argument("--branch-repo", default=None,
                    help="Repo cible pour --start-branch (défaut : résolution pm-branch-start)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--porcelain", "--id-only", dest="porcelain", action="store_true",
                    help="Sortie machine (RM2170) : n'imprime que l'id nu du ticket créé "
                         "sur stdout, tous les logs partent sur stderr. Pour capturer l'id "
                         "de façon fiable dans un pipeline (ID=$(pm-task-add … --porcelain)) "
                         "sans jamais le PRÉDIRE — la séquence Redmine est globale à "
                         "l'instance, le prochain id n'est pas prévisible.")
    out.add_args(ap)
    args = ap.parse_args()
    # Configuré AVANT toute émission : en --porcelain, pm_output route op/info/warn
    # vers stderr et réserve stdout à out.value(id) — fix RM2307 (l'ancien swap
    # global sys.stdout→stderr ne couvrait pas les subprocess, qui héritent des fd).
    out.configure(args)

    # Description multi-ligne : --description-file (fichier, ou '-' = stdin) prime ;
    # sinon --description (avec '-' = stdin). Évite les descriptions illisibles
    # passées sur une seule ligne en argument shell.
    _DESC_FROM_STDIN = False
    if args.description_file is not None:
        _DESC_FROM_STDIN = args.description_file == "-"
        args.description = (sys.stdin.read() if args.description_file == "-"
                            else Path(args.description_file).read_text(encoding="utf-8"))
    elif args.description == "-":
        _DESC_FROM_STDIN = True
        args.description = sys.stdin.read()

    # RM2752 — bloc `bug` du frontmatter, exigé par validate-task pour un bugfix.
    # Un seul flux stdin est disponible : si la description l'a déjà consommé, on
    # le dit au lieu de rendre des étapes vides (le symptôme d'origine).
    _desc_pris_stdin = _DESC_FROM_STDIN
    bug_steps = None
    if args.bug_steps_file is not None:
        if args.bug_steps_file == "-" and _desc_pris_stdin:
            sys.exit("ERREUR : stdin est déjà pris par la description — passe les "
                     "étapes par --bug-steps '…' ou --bug-steps-file <fichier>.")
        bug_steps = (sys.stdin.read() if args.bug_steps_file == "-"
                     else Path(args.bug_steps_file).read_text(encoding="utf-8"))
    elif args.bug_steps is not None:
        if args.bug_steps == "-" and _desc_pris_stdin:
            sys.exit("ERREUR : stdin est déjà pris par la description — passe les "
                     "étapes par --bug-steps '…' ou --bug-steps-file <fichier>.")
        bug_steps = sys.stdin.read() if args.bug_steps == "-" else args.bug_steps
    bug_steps = (bug_steps or "").strip()

    if args.type == "bugfix" and not bug_steps:
        sys.exit(
            "ERREUR : --type bugfix exige les étapes de reproduction.\n"
            "  validate-task.py les impose (`bug.reproduce_steps`) : sans elles le\n"
            "  ticket naît invalide, et un bug sans repro se rouvre trois fois.\n"
            "    --bug-steps \"1. …\\n2. …\"        (ou --bug-steps-file <fichier>)\n"
            "    --bug-reproducibility always|often|sometimes|rarely|never  (défaut : always)"
        )
    if args.type != "bugfix" and (bug_steps or args.bug_reproducibility):
        sys.exit(f"ERREUR : --bug-* n'a de sens que pour --type bugfix (ici : {args.type}).")

    if args.start_branch and (args.retro or args.status != "nouveau"):
        sys.exit("ERREUR : --start-branch est incompatible avec --retro/--status "
                 "(pm-branch-start --take gère lui-même la prise en_cours).")
    if args.retro and args.status != "nouveau":
        sys.exit("ERREUR : --status et --retro sont incompatibles (--retro pilote sa "
                 "propre séquence en_cours → a_tester_verifier).")

    cfg = PMConfig.load()

    if args.project:
        if "/" not in args.project:
            sys.exit("ERREUR : --project doit être entity/project")
        entity, project = args.project.split("/", 1)
    else:
        det = detect_project_from_cwd(cfg)
        if not det:
            sys.exit("ERREUR : projet non détecté depuis cwd, utilise --project entity/project")
        entity, project = det

    fm_proj = load_project_overview(cfg, entity, project)
    rm_proj_id = (fm_proj.get("redmine") or {}).get("project_id")
    if not rm_proj_id:
        sys.exit(f"ERREUR : project_id Redmine manquant dans overview.md de {entity}/{project}")

    tracker_id = TYPE_TO_TRACKER[args.type]
    priority_id = PRIORITY_TO_ID[args.priority]

    if args.dry_run:
        print(f"--dry-run : POST Redmine project={rm_proj_id} tracker={tracker_id} prio={priority_id}")
        print(f"--dry-run : title={args.title!r}")
        if args.parent:
            print(f"--dry-run : parent_issue_id={args.parent}")
        return

    # CF « Task type » (taxonomie fine) : posé si le type NORMS a une
    # correspondance dans la référence (ex. documentation → 42). Le tracker reste
    # la catégorie coarse (documentation retombe sur « Tâche »).
    from redmine_utils import task_type_cf
    extra_cf = []
    tt_cf_id, tt_values = task_type_cf()
    if tt_cf_id and args.type in tt_values:
        extra_cf.append({"id": tt_cf_id, "value": str(tt_values[args.type])})

    # POST Redmine (via helper partagé — set CF IA + PUT author_id).
    # author_id : None si --initiator-agent (POST author=karl OK), sinon Manager IA.
    target_author = None if args.initiator_agent else load_ia_manager_id()
    rm_id = get_task_provider().create_issue(
        project_id=rm_proj_id,
        tracker_id=tracker_id,
        priority_id=priority_id,
        subject=args.title,
        description=args.description,
        author_id=target_author,
        parent_issue_id=args.parent,
        extra_custom_fields=extra_cf or None,
    )
    # Id nu sur stdout dès que le ticket existe côté Redmine (RM2170) :
    # le caller le capture même si une étape de post-traitement échoue ensuite.
    if args.porcelain:
        out.value(rm_id)

    if extra_cf:
        out.info(f"  · CF{tt_cf_id} task-type → {args.type} (val {tt_values[args.type]})")
    if target_author is not None:
        out.info(f"  · author_id → {target_author}")

    # CF27 « AI Test par agent » : poussé seulement si ≠ default (vide côté Redmine = default).
    if args.agent_test != "default":
        from redmine_utils import load_reference, update_issue_fields
        enum_id = (load_reference().get("agent_test_values") or {}).get(args.agent_test)
        if enum_id:
            ok, err = update_issue_fields(rm_id, custom_fields=[{"id": 27, "value": str(enum_id)}])
            if ok:
                out.info(f"  · CF27 agent-test → {args.agent_test}")
            else:
                out.warn(f"push CF27 échoué : {err}")
        else:
            out.warn(f"CF27 non poussé : valeur {args.agent_test!r} absente de agent_test_values")

    slug = slugify(args.title) or f"task-{rm_id}"
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    # Build MD — gabarit partagé avec pm-task-import (pm_task_md)
    fm = build_frontmatter(
        rm_id, args.title, type=args.type, priority=args.priority,
        parent=args.parent, tags=tags, target_env=args.target_env,
        agent_test=args.agent_test, now=now,
        estimate={"difficulty": args.est_difficulty,
                  "human_time_minutes": args.est_human_minutes,
                  "ai_time_minutes": args.est_ai_minutes,
                  "tokens": args.est_tokens,
                  "estimated_model": args.est_model,
                  "confidence": args.est_confidence},
    )
    # RM2752 — le bloc `bug`, posé APRÈS `type` pour que le MD se lise comme les
    # tickets écrits à la main. Réinsertion ordonnée : `yaml.safe_dump` conserve
    # l'ordre du dict (sort_keys=False), donc il faut le placer, pas l'ajouter.
    # Propre à la création : un ticket ADOPTÉ (pm-task-import) n'a pas ces champs.
    if args.type == "bugfix":
        fm = _with_bug(fm, args.bug_reproducibility or "always", bug_steps)
    md = render_md(fm, args.description)
    tasks_dir = cfg.path("tasks_dir", entity=entity, project=project)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    md_path = tasks_dir / f"RM{rm_id}_{slug}.md"
    log_path = tasks_dir / f"RM{rm_id}_{slug}.log.md"
    md_path.write_text(md, encoding="utf-8")
    log_path.write_text(render_log(rm_id, now), encoding="utf-8")

    # ligne dense unique (contrat T1 RM2316) : ✓ add RM<id> <slug>
    out.op("add", rm=rm_id, extra=slug)
    out.info(f"✓ RM{rm_id} créé sur Redmine + MD/log écrits :")
    out.info(f"  {md_path.relative_to(cfg.projects_root)}")

    # Worklog de session (best-effort, no-op hors session Claude Code) : enregistre
    # le ticket comme `nouveau`. Si --status transitionne ensuite, pm-task-status-update
    # ré-upsertera le statut final. Cf RM1875.
    import pm_session_hook
    pm_session_hook.log_to_session(f"RM{rm_id}", label=args.title,
                                   status="nouveau", project=project)

    # Validate — agrégé en 1 warning dense ; le détail complet reste en --verbose.
    try:
        import subprocess
        r = subprocess.run([sys.executable, str(Path(__file__).parent / "validate-task.py"), str(md_path)],
                           capture_output=True, text=True, check=False)
        if r.returncode != 0:
            detail = f"{r.stdout}{r.stderr}".rstrip()
            n = sum(1 for ln in detail.splitlines() if ln.lstrip().startswith("✗")) or "?"
            # RM2752 : le remède doit être une commande qui EXISTE et qui accepte
            # ses arguments. « pm-doctor RM<id> » n'en prenait aucun
            # (« unrecognized arguments ») — suivre l'indication de bonne foi
            # menait dans le mur, juste après un ticket déjà invalide.
            out.warn(f"{n} warning(s) validate → scripts/validate-task.py {md_path}")
            out.info(f"⚠ validate-task.py warnings :\n{detail}")
    except Exception as e:
        out.warn(f"validate-task.py non exécuté : {e}")

    # Push estimation → Redmine (CF21/22/25 + estimated_hours) si estimation
    # explicite fournie. NORMS § ROI « Documentation dans Redmine » : estimer à
    # la création. Délègue à pm-task-metrics-push.py (source unique du mapping).
    est_provided = any(v is not None for v in (
        args.est_tokens, args.est_ai_minutes, args.est_human_minutes,
        args.est_model, args.est_difficulty, args.est_confidence))
    if est_provided and not args.no_push_estimate:
        import subprocess
        r = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "pm-task-metrics-push.py"),
             "--rm-id", str(rm_id), "--estimate"],
            check=False, capture_output=True, text=True)
        for stream in (r.stdout, r.stderr) if r.returncode == 0 else (r.stdout,):
            if (stream or "").strip():
                out.info(stream.rstrip())
        if r.returncode != 0:
            err1 = " ".join((r.stderr or "").strip().splitlines())[:200]
            out.warn(f"push estimation échoué (exit {r.returncode}){' : ' + err1 if err1 else ''}"
                     f" — relance : pm-task-metrics-push.py --rm-id {rm_id} --estimate")

    # --parent : le MD enfant porte déjà parent_task (cf. fm). Maintenir le côté
    # parent (sub_tasks du parent) + tracer dans les deux logs.
    if args.parent:
        pm_hierarchy.append_log(md_path, "pm-task-add",
                                f"`parent_task` = RM{args.parent} (posé à la création).")
        sub = pm_hierarchy.maintain_parent_subtasks(
            cfg, rm_id, old_parent=None, new_parent=args.parent, source="pm-task-add")
        if sub["added_to"]:
            out.info(f"  · parent RM{args.parent} : sub_tasks += RM{rm_id}")
        else:
            out.warn(f"parent RM{args.parent} : MD non trouvé localement — "
                     f"sub_tasks non maintenu (parent côté Redmine OK)")

    # Auto-commit atomique des fichiers écrits (RM1834 piste A) : la tâche créée
    # (+ le MD/log du parent si --parent les a modifiés). Placé AVANT --status /
    # --retro : les transitions déléguées à pm-task-status-update auto-committent
    # leurs propres écritures.
    commit_paths = [md_path, log_path]
    if args.parent:
        parent_md = cfg.find_task(args.parent)
        if parent_md:
            commit_paths += [parent_md, parent_md.parent / parent_md.name.replace(".md", ".log.md")]
    pm_git.autocommit(commit_paths, f"pm(add): RM{rm_id} {slug}")

    if args.start_branch:
        # Verbe atomique (RM2224) : l'id sort de create_redmine_issue et entre
        # directement dans pm-branch-start — aucune ressaisie possible.
        cmd = [sys.executable, str(Path(__file__).resolve().parent / "pm-branch-start.py"),
               str(rm_id), "--take"]
        if args.branch_repo:
            cmd += ["--repo", args.branch_repo]
        r = subprocess.run(cmd)
        if r.returncode != 0:
            out.warn(f"pm-branch-start a échoué (exit {r.returncode}) — relance : "
                     f"pm-branch-start.py {rm_id} --take")

    # --status <statut> : le ticket est créé en `nouveau` (défaut tracker Redmine) ;
    # si un autre statut est demandé, on transitionne via pm-task-status-update
    # (source unique des transitions : couplage NORMS — auto-assign karl pour
    # en_cours, note Redmine, MAJ frontmatter status/status_history + log).
    if not args.retro and args.status != "nouveau":
        import subprocess
        status_script = Path(__file__).parent / "pm-task-status-update.py"
        out.info(f"  → statut initial demandé : {args.status} (transition depuis nouveau)")
        r = subprocess.run(
            [sys.executable, str(status_script), str(rm_id), args.status,
             "--note", "Statut initial posé à la création (pm-task-add --status)"],
            check=False, capture_output=True, text=True,
        )
        for stream in (r.stdout, r.stderr) if r.returncode == 0 else (r.stdout,):
            if (stream or "").strip():
                out.info(stream.rstrip())
        if r.returncode != 0:
            err1 = " ".join((r.stderr or "").strip().splitlines())[:200]
            out.warn(f"Transition initiale vers {args.status} échouée (exit {r.returncode})"
                     f"{' : ' + err1 if err1 else ''}. "
                     f"Reprends : pm-task-status-update.py {rm_id} {args.status}")

    # --retro : enchaîne en_cours puis a_tester_verifier via pm-task-status-update.
    # Le ticket Redmine doit déjà être indexable (POST ci-dessus a renvoyé rm_id),
    # donc l'API peut être interrogée immédiatement.
    if args.retro:
        import subprocess
        status_script = Path(__file__).parent / "pm-task-status-update.py"
        for status, note in [
            ("en_cours", "Prise en charge (ticket rétroactif, travail déjà livré)"),
            ("a_tester_verifier", "Travail livré au moment de la création du ticket — prêt à vérifier"),
        ]:
            out.info(f"  → transition --retro : {status}")
            r = subprocess.run(
                [sys.executable, str(status_script), str(rm_id), status, "--note", note],
                check=False, capture_output=True, text=True,
            )
            for stream in (r.stdout, r.stderr) if r.returncode == 0 else (r.stdout,):
                if (stream or "").strip():
                    out.info(stream.rstrip())
            if r.returncode != 0:
                err1 = " ".join((r.stderr or "").strip().splitlines())[:200]
                out.warn(f"Transition --retro {status} a échoué (exit {r.returncode})"
                         f"{' : ' + err1 if err1 else ''}. "
                         f"Reprends manuellement : pm-task-status-update.py {rm_id} {status}")
                break


if __name__ == "__main__":
    main()
