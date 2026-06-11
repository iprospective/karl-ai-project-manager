# Système de gestion de tâches — iprospective

Tu opères dans le système de gestion de projets et tâches de iprospective.
Ce dépôt contient les normes, les tâches et les instructions pour les agents IA.

## Orientation rapide

- **Normes (KERNEL) :** `norms/src/NORMS-KERNEL.md` — **lecture obligatoire** (déclencheurs + tripwires) ; ouvre les `norms/src/modules/*.md` **à la demande** via les déclencheurs du KERNEL. (`norms/NORMS.md` = doc complet *généré*, pour référence humaine — ne pas l'éditer.)
- **Config des chemins :** `pm.config.yml` — patterns logiques (`entity`, `project`, `task_file`, …). Résolution Python via `scripts/pm_paths.py`.
- **Ton rôle :** `agents/worker-{role}.md` + `agents/worker-common.md`
- **Hiérarchie :** `paths.task_file` = `{tasks_dir}/RM{id}_{slug}.md` (entité → projet → tâche)
- **Cascade :** client → projet → tâche (héritage avec override possible)
- **Knowledge transverse :** `knowledge/INDEX.md` — capitalisation technique/opérationnelle par produit, partagée entre clients (Redmine, …). Référence cette knowledge avant de chercher ailleurs quand tu rencontres un produit qu'elle couvre.

## Quand tu reçois une invocation de type "traite la tâche RM{id} du client {C} projet {P}"

1. Lire `agents/worker-common.md`
2. Lire `agents/worker-{role}.md` (ton rôle précisé dans l'invocation)
3. Lire `norms/src/NORMS-KERNEL.md` (KERNEL : déclencheurs + tripwires) ; ouvrir `norms/src/modules/*.md` quand un déclencheur se présente
4. Lire `{entity_client_dir}/*.md` (overview + aspects) + `{entity_memory_dir}/*.md` pour `entity={C}`
5. Lire `{project_dir}/*.md` (overview + aspects) + `{project_memory_dir}/*.md` pour `entity={C}, project={P}`
6. Lire `paths.task_file` (ta tâche) — résolu via `cfg.path("task_file", entity={C}, project={P}, id={id}, slug=*)`
7. Lire les dernières 50 lignes du `paths.task_log_file`
8. Travailler selon le protocole de ton rôle, en respectant la cascade

## Quand tu reçois une invocation de type "review la tâche RM{id}"

1. Lire `agents/reviewer.md`
2. Lire `norms/src/NORMS-KERNEL.md` (KERNEL ; + modules à la demande)
3. Lire la tâche + son `.log.md` + ses `outputs[]`
4. Appliquer le protocole de validation

## Rappels critiques

- Tu n'écris que dans les fichiers dont tu es propriétaire (voir `worker-common.md`)
- Toujours vérifier `updated` avant d'écrire (optimistic locking)
- Appender dans `.log.md` à chaque étape significative
- Mettre à jour Redmine après chaque changement de statut
