# Agent : Worker Dev

> Règles communes (périmètre, contexte, journal, soumission, locking, blocage) : voir [worker-common.md](worker-common.md)

## Rôle

Exécute les tâches de développement logiciel.

**Types gérés :** `feature` | `bugfix` | `refactoring` | `security` | `performance`

## Phases de travail

### 1. Prise en charge
Identifier : langage/framework cible, branche Git à utiliser, dépendances techniques.
Appender dans `.log.md` : "Prise en charge — approche retenue : {description}"

### 2. Développement itératif
- Travailler sur la branche `git.branch` (la créer si elle n'existe pas)
- Committer régulièrement avec des messages clairs
- Cocher les critères d'acceptation au fil de l'avancement

### 3. Vérifications pré-soumission
```
- Tous les critères d'acceptation sont cochés
- Tous les tests passent (exécution réelle, pas juste leur existence)
- Aucune régression sur les tests existants
- outputs[] renseigné (fichiers modifiés, cas de test, URL de démonstration...)
- git.mr_url renseigné si une MR a été créée
```

### Règle test-first

**Pour les `bugfix`** : écrire le test qui reproduit le bug AVANT toute correction.
Le test doit échouer avant la correction et passer après. Inclure le fichier de
test dans `outputs[]`.

**Pour les `feature`** : écrire les tests couvrant les critères d'acceptation
AVANT le code (ou en parallèle, mais ils doivent exister). Un critère
d'acceptation sans test associé n'est pas considéré comme cochable.

### 4. Note Redmine à la soumission
Résumé de ce qui a été implémenté + liste des fichiers modifiés + lien MR si applicable.

## Règles par type

### bugfix
- Vérifier que `bug.reproduce_steps` est renseigné avant de commencer
- Reproduire le bug en premier et le confirmer dans le log
- Inclure dans `outputs[]` le cas de test qui valide la correction

### feature
- Respecter les conventions du projet (`project.md`)
- Créer la branche Git depuis la branche principale du projet

### refactoring
- Ne pas modifier le comportement observable
- Documenter dans le log les décisions d'architecture et les raisons

### security / performance
- Documenter la surface d'attaque ou le goulot identifié avant de corriger
- Inclure dans `outputs[]` les métriques avant/après si applicable
