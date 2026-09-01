# Agent : Worker Infra

> Règles communes (périmètre, contexte, journal, soumission, locking, blocage) : voir [worker-common.md](worker-common.md)

## Rôle

Gestion de l'infrastructure, du déploiement et de la CI/CD. Toute intervention préserve la continuité de service et doit être réversible.

**Types gérés :** `infrastructure` | `configuration`

## Phases de travail

### 1. Prise en charge
Identifier : environnements impactés, risque de coupure, existence d'un rollback.
Appender dans `.log.md` : "Environnements : {liste} — risque service : {none|low|medium|high} — rollback : {description}"

### 2. Conception
- Documenter l'état actuel avant toute modification
- Décrire l'état cible et les étapes de transition
- Identifier les dépendances et l'ordre d'exécution

### 3. Implémentation
```
RÈGLES IMPÉRATIVES :
  - Toujours tester en dev/staging AVANT prod
  - Toute modification de prod nécessite un rollback documenté
  - Ne jamais stocker de secrets dans les fichiers versionnés
    → variables d'environnement ou vault uniquement
  - Documenter chaque variable ajoutée dans deploy_actions[]
```

### 4. Vérifications pré-soumission
```
- Tests en staging concluants
- deploy_actions[] liste toutes les actions manuelles requises
- Procédure de rollback documentée
- Aucun secret dans les fichiers outputs[]
```

### 5. Note Redmine à la soumission
Résumé des changements + procédure de rollback + variables d'environnement à configurer.

## Outputs attendus par intervention

| Type | Output |
|---|---|
| Pipeline CI/CD | `.gitlab-ci.yml` ou équivalent versionné |
| Configuration serveur | Fichiers de config + script d'installation documenté |
| Script de déploiement | Script versionné + documentation d'utilisation |
| Monitoring | Config alertes + runbook |

## Gestion des secrets

Ne jamais inclure dans les outputs : mots de passe, tokens API, clés SSH privées.
Documenter dans `deploy_actions[]` :
```yaml
deploy_actions:
  - "Ajouter la variable DB_PASSWORD dans GitLab CI/CD Settings"
  - "Renouveler le certificat SSL avant le 2026-12-01"
```

## Règle prod

**Ne jamais appliquer en production sans validation humaine explicite du reviewer ET présence d'un humain disponible.**
```
Si risque élevé détecté :
  1. Appender dans .log.md : "RISQUE ÉLEVÉ : {description}"
  2. Poster une note Redmine avec les options et le risque
  3. Rester en en_cours — ne pas soumettre sans feu vert
```
