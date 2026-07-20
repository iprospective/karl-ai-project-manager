#!/bin/bash
# Exemple de configuration cron pour l'orchestrateur et le summarizer.
#
# Adapter PM_DIR au chemin réel d'installation (doit correspondre à
# pm.config.yml :: roots.pm_dir) et LOG_DIR à l'emplacement souhaité.
#
# Installation :
#   crontab -e
#   puis copier les lignes ci-dessous (sans le shebang)

PM_DIR=/zfs/workspaces/ai/project-management
LOG_DIR=/var/log/pm-ai-agents

# ── Orchestrateur ────────────────────────────────────────────────
# Toutes les 15 minutes : scan des tâches a_faire, assignation aux workers
*/15 * * * * cd "$PM_DIR" && source .env && claude -p "Tu es orchestrateur. Scanne tous les clients et projets, assigne les tâches a_faire éligibles." >> "$LOG_DIR/orchestrateur.log" 2>&1

# ── Summarizer ───────────────────────────────────────────────────
# Tous les jours à 06:00 : agrégation Pistes/Remarques + Structure
0 6 * * * cd "$PM_DIR" && source .env && claude -p "Tu es summarizer. Régénère les Changelog, Pistes, Remarques de tous les clients et projets actifs depuis la dernière exécution." >> "$LOG_DIR/summarizer.log" 2>&1

# ── Rapport hebdomadaire ─────────────────────────────────────────
# Tous les lundis à 08:00 : ranking ROI global
0 8 * * 1 cd "$PM_DIR" && source .env && python3 scripts/priority.py "$PROJECTS_PATH" --top 30 >> "$LOG_DIR/priority-weekly.log" 2>&1

# ── Reporting tokens/temps → Redmine (RM2160) ────────────────────
# Toutes les 30 min : pousse la conso tickée localement par pm-task-tick
# (frontmatter MD) vers Redmine (time_entries + CF17). Sans ce cron, le
# reporting reste invisible côté Redmine tant qu'un humain ne lance pas
# pm-task-report à la main. Idempotent (clés de dédup par time_entry).
*/30 * * * * python3 "$PM_DIR/scripts/pm-task-report.py" --all --apply >> "$LOG_DIR/pm-task-report.log" 2>&1

# ── Veille tarifaire Anthropic (RM2165) ──────────────────────────
# 1x/jour : compare pm.pricing.yml à la doc officielle (extraction via
# claude -p headless, modèle sonnet). En cas d'écart : ticket Redmine
# tagué pricing-watch (dédup : pas de doublon tant qu'un ticket est ouvert).
# Ne modifie JAMAIS le YAML lui-même.
30 8 * * * python3 "$PM_DIR/scripts/pm-pricing-check.py" >> "$LOG_DIR/pm-pricing-check.log" 2>&1

# ── Wiki-sync (fallback async) ───────────────────────────────────
# Toutes les 10 min : capte les édits faits côté Wiki Redmine entre deux push git
# (fold-back wiki→git + auto-commit [wiki-sync], puis git push). Le sens git→wiki
# normal passe par `pm-sync-push` à la publication ; ce cron rattrape les retouches
# wiki hors activité git. Lock-file par projet → pas de chevauchement avec un push manuel.
*/10 * * * * cd "$PM_DIR" && set -a && source .env && set +a && python3 scripts/pm-wiki-sync.py --all --push >> "$LOG_DIR/wiki-sync.log" 2>&1

# ── Promotion PM dev→main (RM2298) ───────────────────────────────
# Toutes les heures : promeut par lot les auto-commits pm-* repliés sur `dev`
# (branches protégées RM2030) vers `main` du repo de DONNÉES PM — MR auto-créée
# et auto-mergée (PAT manager). Idempotent : sans lot en attente, no-op.
# Adapter --repo au chemin du repo de données de l'instance.
15 * * * * cd "$PM_DIR" && set -a && source .env && set +a && python3 scripts/pm-promote.py --repo "$PROJECTS_PATH" >> "$LOG_DIR/pm-promote.log" 2>&1

# ── Bench surconsommation couche PM (RM2361/S0) ──────────────────
# Mensuel : mesure la part PM vs baseline (audit RM2275) ; poste le résumé
# en note sur le ticket de suivi et alerte (exit 1) si dérive > +2 pts.
# Adapter BENCH_NOTIFY_RM au ticket de suivi de l'instance.
# 0 7 1 * * $PM_DIR/scripts/pm-bench-overhead.py --compare $PM_DIR/var/bench/baseline-2026-07-rm2275.json --notify-rm ${BENCH_NOTIFY_RM:-2316} >> $LOG_DIR/bench-overhead.log 2>&1
