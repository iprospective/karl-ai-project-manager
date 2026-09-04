#!/bin/bash
# Configuration cron d'une instance PM — UNE SEULE LIGNE (RM2792, lot 1).
#
# Jusqu'ici ce fichier listait un cron par travail : orchestrateur */15,
# pm-task-report */30, wiki-sync */10, summarizer quotidien, veille tarifaire,
# GC des verrous… Le problème n'était pas leur nombre, c'est ce que le crontab ne
# sait pas faire :
#
#   · aucun état consultable — « c'est passé quand, et ça s'est bien passé ? »
#     n'avait de réponse qu'en fouillant des journaux séparés, quand ils existaient ;
#   · aucun verrou — cron relance un job même si le précédent tourne encore. Deux
#     orchestrateurs concurrents s'assignent les mêmes tâches ;
#   · aucun inventaire — la moitié de ces jobs n'étaient installés nulle part,
#     seulement décrits ici, dans un fichier que personne ne relit.
#
# Le registre des travaux vit désormais dans `jobs.reference.yml`, et
# `pm-scheduler.py` décide de ce qui est dû. AJOUTER UN CRON À CÔTÉ ANNULE
# L'INTÉRÊT DE LA MANŒUVRE : un nouveau travail périodique se déclare au registre.
#
# Installation :
#   crontab -e
#   puis coller la ligne ci-dessous, PM_DIR/LOG_DIR adaptés à l'instance
#   (`python3 scripts/pm-scheduler.py crontab` l'imprime déjà remplie).

PM_DIR=/zfs/workspaces/ai/project-management
LOG_DIR=/var/log/pm-ai-agents

# ── Ordonnanceur PM — LA ligne, et la seule ──────────────────────────────
*/5 * * * * python3 "$PM_DIR/scripts/pm-scheduler.py" run >> "$LOG_DIR/scheduler.log" 2>&1

# ── Au quotidien ─────────────────────────────────────────────────────────
#   pm-scheduler.py list                 ce qui tourne, quand, et comment ça s'est passé
#   pm-scheduler.py history --job <id>   les dernières exécutions d'un travail
#   pm-scheduler.py check                valide le registre (schéma, expressions cron)
#   pm-scheduler.py run --only <id> --force --dry-run   ce que ferait un travail
#
# NB (RM2438 T1) : la config est scindée en pm.env (non-secret) + .env (secrets).
# Les jobs déclarés avec `shell:` les reçoivent tous les deux, sourcés par
# l'ordonnanceur — c'est le piège que chaque ligne de cron devait traiter seule.
# Les jobs `command:` sont du Python, qui charge sa config via pm_paths.
