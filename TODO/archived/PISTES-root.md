# Pistes d'évolution

Document de réflexion sur les évolutions futures du système, non engageantes.
Pour les évolutions actées, voir `Changelog.md`.

---

## Contexte

La v1 actuelle calque son organisation sur celle d'une équipe humaine :
orchestrateur → workers spécialisés → reviewer.
Ce modèle est familier, debuggable et opérationnel — c'est le bon point de départ.

Mais il transpose des contraintes humaines (mémoire courte, communication lente,
spécialisation forcée, sync points) à des agents qui n'en ont aucune. Une équipe
d'IA peut collaborer plus efficacement avec des patterns AI-natifs.

---

## Patterns AI-natifs pour une v3

### 1. Branch & merge (au lieu de spécialisation)

Spawner N agents identiques sur la même tâche avec des approches différentes,
comparer les sorties, garder la meilleure (ou en synthétiser une).
Comme git pour les idées. Particulièrement adapté aux tâches `research`, `audit`,
`design` exploration.

### 2. Critiques continus (au lieu de reviewers gate)

Aujourd'hui : `a_tester_verifier` est un gate qui bloque le worker en attente
du reviewer.
AI-natif : un agent critique tourne en parallèle de l'exécuteur et signale
les dérives en temps réel. Le worker corrige au fil de l'eau, pas en fin
de cycle.

### 3. Décomposition asymétrique

Un seul agent puissant (Opus, contexte large) qui décompose finement,
puis N agents simples (Sonnet/Haiku) qui exécutent en parallèle.
La valeur est dans la qualité de décomposition, pas dans la spécialisation
des exécuteurs.

### 4. Pipeline Intent → Plan → Fan-out → Synthèse

```
[Humain] → [Intent extractor] → [Decomposer] → [N executors parallèles] → [Synthesizer] → [Humain]
```

Le rôle critique manquant aujourd'hui : le **synthesizer** qui rassemble
cohéremment des sorties parallèles. Différent du reviewer (qui valide).

### 5. Exécution spéculative

Ne pas attendre la fin d'une tâche pour démarrer la suivante. Exécuter
spéculativement les branches probables, jeter les mauvaises. Comme la
prédiction de branchement d'un CPU.

---

## Nouveaux rôles d'agents (v3)

### intent-extractor

**Premier rôle invoqué sur tout nouveau ticket vague.**

Transforme une demande floue ("je veux que ça aille mieux") en spec exécutable.
Droit de poser N questions au demandeur en une seule fois, plutôt que N rounds.

Output : tâche structurée prête pour la décomposition, critères d'acceptation
clairs et mesurables.

### adversary (reformulateur)

Reformule ce qu'il a compris du besoin et le confronte au demandeur.
"Voici ce que je vais faire — confirme ou corrige."
Coût : 1 round-trip. Bénéfice : éviter 10h de mauvaise direction.

### critic (continu)

Tourne en parallèle de l'exécuteur, pas en gate. Imagine des scénarios
d'usage, teste mentalement, signale les dérives.
Différent du reviewer : intervient pendant le travail, pas après.

### synthesizer

Rassemble les outputs de sous-tâches parallèles en un livrable cohérent.
Résout les conflits, harmonise les styles, produit la sortie finale.
Indispensable dès que le pattern "branch & merge" ou "fan-out" est utilisé.

---

## Ordre d'introduction recommandé

L'erreur serait de tout repenser maintenant. Approche progressive :

| Étape | Action | Pourquoi |
|---|---|---|
| 1 | Vivre avec la v1 quelques mois | Identifier les vrais frottements à l'usage |
| 2 | Ajouter `intent-extractor` | Le besoin de capture qualifiée se fait toujours sentir tôt |
| 3 | Ajouter `synthesizer` | Quand on commence à utiliser les sous-tâches en parallèle |
| 4 | Remplacer reviewer-gate par `critic`-continu | Quand le gate devient un goulot |
| 5 | Introduire branch & merge sur tâches exploration | Quand la qualité plafonne sur un seul agent |

---

## Tests — évolutions reportées

### Stack de tests dans `templates/project.md`

Enrichir le template projet d'une section obligatoire "Stack de tests"
(framework, commande de lancement, seuil de couverture minimum).
**Reporté au premier vrai projet** — sera dimensionné selon ses besoins
réels plutôt que théoriques.

### Validation cross-fichiers

Le validateur actuel (v1) vérifie chaque fichier indépendamment.
Évolutions à prévoir :
- `depends_on` et `parent_task` pointent vers des tâches existantes
- `sub_tasks` du parent contient bien les enfants
- Cohérence `completion_pct` du parent vs status des enfants

### Génération de tests depuis les critères d'acceptation

Un agent `test-stub-generator` qui transforme automatiquement les
critères d'acceptation en stubs de tests (pytest, jest, etc.) selon
le framework déclaré dans `project.md`.

### Tests de workflow end-to-end

Simulation du cycle de vie complet d'une tâche (création → assignation
→ travail → review → fermeture) pour valider que le système global
fonctionne.

---

## Création de tickets Redmine depuis MD

Sens **MD → Redmine** sans ticket préexistant.

Cas d'usage : un agent rédige une tâche en MD (par auto-décomposition d'un parent ou
par initiative), sans qu'un humain ait créé le ticket Redmine au préalable. Le
système devrait alors créer le ticket Redmine côté serveur, récupérer l'ID,
renommer le fichier et compléter le frontmatter.

**Pas pour la v1.5** : ajoute un couplage outillage important (gestion d'erreur
API Redmine, gestion de collisions sur les IDs, droits d'écriture côté Redmine
de chaque agent). À réfléchir quand le besoin se manifestera.

Actuellement v1.5 : deux flux supportés
- **Redmine → MD** : humain crée le ticket dans Redmine, l'orchestrateur génère le MD
- **CLI → Redmine + MD** : commande `pm task create` qui orchestre les deux côtés
  depuis le workspace projet (à implémenter, voir [TODO.md](TODO.md))

---

## Tradeoffs à garder en tête

- **Coût** : N agents en parallèle = N × tokens. Vérifier que le bénéfice (qualité, vitesse) le justifie
- **Debugabilité** : un système plus sophistiqué est plus dur à tracer quand quelque chose va mal
- **Complexité du synthesizer** : agréger des sorties contradictoires est non-trivial
- **Risque de boucles** : critique continu × exécuteur peut osciller — prévoir un cap d'itérations
