> 📂 **Module `structure-reference-pratique` — quand lire ceci :** je cherche un projet dans l'index centralisé · j'ajoute ou je corrige un contact.
> **Outils :** `pm-client-contact`, `refresh-indexes.py` · **Préchargé par :** *(personne — ouvert à la demande)*.

Référence sortie de `structure-reference` (RM3037) pour tenir le budget de contexte : la **règle** —
jamais de chemin en dur, tout se résout par `pm_paths.PMConfig` — reste dans le module préchargé.

### Repo projets (index centralisé)

Racine : `pm.config.yml :: roots.projects_root` (résolu depuis `$PROJECTS_PATH`).
Structure interne définie par les patterns de `paths:` — la représentation
ci-dessous montre la **résolution par défaut**.

> **⚠ Sens du lien inversé — `projects_root` est un INDEX, plus le stockage.**
> Historiquement cette arbo **contenait** les données PM et le `.mmi-pm` de chaque
> workspace y **pointait** (symlink entrant). Le modèle canonique actuel est
> **inversé** : la source de vérité est le **`.mmi-pm` du core** de chaque projet (cf.
> « Anatomie d'un projet » ci-dessus), et chaque
> `projects_root/{entity_projects_dir}/<P>` est un **symlink SORTANT** vers ce
> `.mmi-pm`. `projects_root` est donc un **index** de liens vers les cores — maintenu
> par `mmi-pm index add|rebuild` (reconstruit depuis les emplacements canoniques
> `.mmi-pm` / `.mmi-pm-client`) —, pratique pour que l'orchestrateur scanne tous les
> projets d'un coup (`cfg.iter_projects()`), mais ce **n'est plus** l'endroit où vivent
> les tâches/docs. L'arbre par défaut ci-dessous décrit donc ce que chaque core expose
> **à travers** son lien d'index, pas un stockage central.

```
{projects_root}/                      # = $PROJECTS_PATH (repo ai-projects)
  README.md
  {entities_dir}/                     # = projects_root/clients
    {entity}/                         # entité = client | product | self (slug)
      {entity_client_dir}/            # = entity/client  — cahier des charges
        overview.md                   # OBLIGATOIRE — frontmatter + sommaire
        hosting.md                    # aspect — optionnel
        contracts.md                  # aspect — optionnel
        ...                           # tout aspect pertinent
      {entity_memory_dir}/            # = entity/memory  — mémoire structurée (agents)
      Changelog.md                    # AUTO — activité agrégée
      Pistes.md                       # AUTO — idées non décidées
      Remarques.md                    # AUTO — observations factuelles
      {entity_projects_dir}/          # = entity/projects
        {project}/                    # = entity_projects_dir/{project-slug}
          {project_dir}/              # = project/project  — CANONIQUES (mathieu-pm, via mmi-pm)
            overview.md               # OBLIGATOIRE — frontmatter + sommaire/index des aspects
            environments.md           # aspect canonique — optionnel (consommé par l'outillage)
          {docs_dir}/                 # = project/docs  — aspects LIBRES (wiki-syncés, group-writable)
            hosting.md                # aspect — optionnel
            stack.md
            data-model.md
            workflows.md
            audience.md               # exemples — uniquement les aspects pertinents
            ...
          {project_memory_dir}/       # = project/memory  — mémoire spécifique projet
          Changelog.md                # AUTO
          Pistes.md                   # AUTO
          Remarques.md                # AUTO
          {tasks_dir}/                # = project/tasks
            RM{id}_{titre-kebab}.md         # = paths.task_file
            RM{id}_{titre-kebab}.log.md     # = paths.task_log_file
```

**Contacts d'un client** (`meta.yml :: contacts[]`, écriture par
`pm-client-contact`) : voir `modules/project-modeling.md` — c'est de la
modélisation d'entité, pas de la résolution de chemins (RM2755).

### L'annuaire de contacts (RM2703)

Une personne = **une fiche**, `contacts/<ref>.yml`, dans le dépôt de **données**
(`paths.contacts_dir`). Le rattachement à un client reste chez lui :

```yaml
contacts:
  - ref: moulin-mathieu     # → l'annuaire
    role: owner
    title: Gérant
```

Deux objets, deux responsabilités : **l'identité** (nom, adresses, téléphones,
`internal`, `redmine_user_id`) vit dans l'annuaire ; **la relation** (rôle,
titre) reste chez le client, parce qu'elle n'existe que là et qu'un `meta.yml`
doit rester lisible seul.

Trois choses à ne pas confondre :

- ce n'est **pas** un doublon des comptes Redmine — celui-ci dit qui a un compte
  et des droits, l'annuaire dit qui l'on côtoie (lien facultatif par
  `redmine_user_id`) ;
- ce n'est **pas** `team[]`, qui dit qui *travaille* sur un projet ;
- ce n'est **pas** le CRM du client : les contacts de nos clients vivent dans
  leur Dolibarr.

**Pas sous `conf_dir`** : le dépôt de code part sur un miroir GitHub public, et
ce sont des données personnelles. **Pas à la racine de `projects_root`** :
aucun dépôt ne la versionne. Écriture par `pm-contact.py` uniquement.

**Ce qu'un dépôt git n'oublie pas** : effacer une fiche ne l'efface pas de
l'historique. Un droit à l'effacement réellement honoré demande une réécriture
d'historique — donc une procédure, pas un `git rm`.
