# Système de gestion de tâches — iprospective

Tu opères dans le système de gestion de projets et tâches de iprospective.
Ce dépôt contient les normes, les tâches et les instructions pour les agents IA.

## Orientation rapide

- **Normes et schéma :** `norms/NORMS.md` (v1.2.0)
- **Ton rôle :** `agents/worker-{role}.md` + `agents/worker-common.md`
- **Tâche assignée :** `projects/{projet}/tasks/RM{id}_*.md`
- **Journal :** `projects/{projet}/tasks/RM{id}_*.log.md`

## Quand tu reçois une invocation de type "traite la tâche RM{id}"

1. Lire `agents/worker-common.md`
2. Lire `agents/worker-{role}.md` (ton rôle précisé dans l'invocation)
3. Lire `norms/NORMS.md`
4. Lire `projects/{projet}/project.md`
5. Lire `projects/{projet}/tasks/RM{id}_*.md` (ta tâche)
6. Lire les dernières 50 lignes de `projects/{projet}/tasks/RM{id}_*.log.md`
7. Travailler selon le protocole de ton rôle

## Quand tu reçois une invocation de type "review la tâche RM{id}"

1. Lire `agents/reviewer.md`
2. Lire `norms/NORMS.md`
3. Lire la tâche + son `.log.md` + ses `outputs[]`
4. Appliquer le protocole de validation

## Rappels critiques

- Tu n'écris que dans les fichiers dont tu es propriétaire (voir `worker-common.md`)
- Toujours vérifier `updated` avant d'écrire (optimistic locking)
- Appender dans `.log.md` à chaque étape significative
- Mettre à jour Redmine après chaque changement de statut
