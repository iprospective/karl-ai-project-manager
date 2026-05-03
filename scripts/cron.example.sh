#!/bin/bash
# Exemple de configuration cron pour l'orchestrateur et le summarizer.
#
# Adapter les chemins et fréquences au besoin.
#
# Installation :
#   crontab -e
#   puis copier les lignes ci-dessous (sans le shebang)

PM_DIR=/zfs/workspaces/ai/project-management
LOG_DIR=/var/log/ai-agents

# ── Orchestrateur ────────────────────────────────────────────────
# Toutes les 15 minutes : scan des tâches a_faire, assignation aux workers
*/15 * * * * cd "$PM_DIR" && source .env && claude -p "Tu es orchestrateur. Scanne tous les clients et projets, assigne les tâches a_faire éligibles." >> "$LOG_DIR/orchestrateur.log" 2>&1

# ── Summarizer ───────────────────────────────────────────────────
# Tous les jours à 06:00 : agrégation Pistes/Remarques + Structure
0 6 * * * cd "$PM_DIR" && source .env && claude -p "Tu es summarizer. Régénère les Changelog, Pistes, Remarques de tous les clients et projets actifs depuis la dernière exécution." >> "$LOG_DIR/summarizer.log" 2>&1

# ── Rapport hebdomadaire ─────────────────────────────────────────
# Tous les lundis à 08:00 : ranking ROI global
0 8 * * 1 cd "$PM_DIR" && source .env && python3 scripts/priority.py "$PROJECTS_PATH" --top 30 >> "$LOG_DIR/priority-weekly.log" 2>&1
