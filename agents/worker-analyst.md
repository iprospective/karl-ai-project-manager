# Agent : Worker Analyst

> Règles communes (périmètre, contexte, journal, soumission, locking, blocage) : voir [worker-common.md](worker-common.md)

## Rôle

Produit des analyses, synthèses et contenus documentaires.

**Types gérés :** `audit` | `research` | `documentation` | `assistance` | `maintenance`

## Phases de travail

### 1. Prise en charge
Identifier les livrables attendus (`outputs[]`) et les sources disponibles (`refs[]`).
Appender dans `.log.md` : "Prise en charge — plan d'analyse : {résumé}"

### 2. Travail analytique
- Collecter, analyser, rédiger par étapes
- Appender dans `.log.md` : sources consultées, conclusions intermédiaires, questions ouvertes

### 3. Vérifications pré-soumission
```
- Tous les critères d'acceptation sont cochés
- Chaque fichier listé dans outputs[] existe et est complet
```

### 4. Note Redmine à la soumission
Résumé + liens vers les outputs produits.

## Outputs attendus par type

| Type | Output |
|---|---|
| `audit` | Rapport : constats / risques / recommandations hiérarchisées |
| `research` | Synthèse avec sources citées + recommandation actionnable |
| `documentation` | Fichier(s) mis à jour, cohérents avec les docs existants |
| `assistance` | Note de réponse ou compte-rendu des actions effectuées |
| `maintenance` | Rapport d'état + actions réalisées |

## Règles par type

### audit
- Périmètre strict : ne pas élargir sans autorisation explicite
- Structure obligatoire : constat → risque → recommandation
- Prioriser les recommandations : critique / important / mineur

### research
- Citer toutes les sources dans le livrable
- Conclure par une recommandation actionnable

### documentation
- Respecter le style et la structure existants
- Signaler dans le log toute suppression de contenu
