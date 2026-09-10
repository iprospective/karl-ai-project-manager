> 📂 **Module `roi-pricing` — quand lire ceci :** j'estime · je calcule le ROI · je priorise · journalisation temps/tokens par commit.
> **Outils :** `pm-task-add`, `pm-task-tick`, `priority.py`, `pm-task-report` · **Préchargé par :** orchestrateur.

## Ordonnancement par ROI

Script `scripts/priority.py` qui calcule pour chaque tâche `a_faire` :

```
score = (immediate_benefit + monthly_benefit * 12) * priority_weight / max(estimate.time_minutes, 1)
```

Avec `priority_weight = {low: 0.5, normal: 1, high: 2, urgent: 4}`.

Filtre : tâches `a_faire` dont toutes les `depends_on` sont `ferme`.
Sortie : top N tâches triées par score décroissant, par client/projet ou global.

## ROI assisté par IA (RM1717)

Chaque ticket porte un coût (tokens IA + temps humain) et un gain
(immédiat + récurrent). Le ROI se calcule à partir de ces 4 dimensions.

### Tarification

Les prix par modèle sont dans `pm.pricing.yml` (commitable, à maintenir
quand Anthropic ajuste). Unités : **USD/MTok** pour input/output/cache,
**EUR/h** pour le coût humain.

### Frontmatter étendu (v1.11.0)

```yaml
# Estimation prévisionnelle
estimate:
  difficulty: medium                  # inchangé
  human_time_minutes: 30              # NEW — temps humain prévu (revue, décisions, tests)
  ai_time_minutes: 15                 # NEW — temps wall-clock IA prévu
  tokens: 50000                       # tokens prévus (total)
  cost_usd: 0.75                      # NEW — coût USD prévu (estimé depuis tokens × prix)
  estimated_model: claude-opus-4-7    # NEW — modèle prévu (pour calcul cost prévu)
  confidence: 0.6
  estimated_by: pm-task-add
  estimated_at: 2026-05-17T14:30

# ROI — les deux échelles coexistent
roi:
  immediate_benefit: 3                # 1-5 — rapide à estimer (qualitatif)
  monthly_benefit: 3                  # 1-5 — récurrent qualitatif
  immediate_gain_eur: null            # NEW — gain € immédiat (one-shot)
  monthly_gain_eur: null              # NEW — gain € récurrent mensuel
  # yearly_gain_eur dérivé = monthly_gain_eur × 12 (pas stocké)

# Cumulés effectifs (auto-incrémentés par le hook pm-task-tick)
tokens_total: 0                       # somme tous types
tokens_breakdown:                     # NEW — détail par type
  input: 0
  output: 0
  cache_read: 0
  cache_creation: 0
cost_total_usd: 0.0                   # NEW — cumulé recalculé à chaque tick
human_time_total_minutes: 0           # NEW — temps humain effectif
ai_time_total_minutes: 0              # NEW — temps wall-clock IA effectif
```

**Comment la conso est mesurée et journalisée** (hook `Stop`, format du journal par commit, champs
Redmine dédiés) : `roi-pricing-pratique`. Ce qui reste ici : **quand** estimer, **comment** prioriser.

### Calcul du ROI

```
invest_eur = cost_total_usd × usd_to_eur + (human_time_total_minutes / 60) × human_hourly_rate_eur
benefit_yearly_eur = (immediate_gain_eur ou immediate_benefit × 100)
                   + (monthly_gain_eur ou monthly_benefit × 50) × 12
roi_ratio = benefit_yearly_eur / max(invest_eur, 1)
```

Quand `*_gain_eur` est renseigné, il prime sur l'échelle 1-5. Si seul le
1-5 est connu, un facteur conventionnel s'applique (100 €/point immédiat,
50 €/point/mois récurrent — ajustable dans `pm.pricing.yml` plus tard).

### Hook vs script manuel

- **Hook automatique** : sessions Claude Code (~/.claude/settings.json),
  attribution silencieuse en arrière-plan
- **Script manuel** : `scripts/pm-task-tick.py --rm-id X --tokens-input N --tokens-output N --model M --human-minutes M`
  pour les agents non-Claude-Code (n8n, scripts custom) ou ajout manuel de
  temps humain post-hoc

### Notes

- **Race conditions multi-sessions** : 2 Claude bossant sur le même ticket
  simultanément écrivent dans le même frontmatter — l'optimistic locking
  (`updated`) doit faire son job. Vérifier en pratique.
- **Cache reads** : ~10× moins chers que input pur — bien distinguer dans
  le calcul (cf. tableau `pm.pricing.yml`).
- **Précision** : la mesure ne prend en compte que les sessions Claude Code
  hookées. Sessions oubliées (sans hook) ou autres agents (n8n) → invisibles.

### Documentation dans Redmine — champs dédiés (obligatoire) — v1.21.0

Le frontmatter MD n'est pas suffisant : l'estimation et les cumuls doivent
être **visibles côté Redmine** dans les champs dédiés de l'instance (IDs à
revalider via le § « Synchronisation de la configuration Redmine »).

**Estimation prévisionnelle → poussée sur le ticket :**

| Frontmatter | Champ Redmine |
|---|---|
| `estimate.tokens` | CF **21** `Tokens prévus` (int) |
| `estimate.ai_time_minutes` (÷ 60) | CF **22** `Temps estimé IA (h)` (float) |
| `estimate.human_time_minutes` (÷ 60) | natif `estimated_hours` (temps estimé) |

**Quand estimer / réestimer** :
- **À la création** de la tâche (`pm-task-add`) : estimation initiale obligatoire,
  poussée immédiatement sur CF 21 / 22 / `estimated_hours`.
- **À la prise de ticket** (passage `en_cours`) : si aucune estimation n'a été
  faite auparavant (ticket créé hors PM, ou estimation oubliée), **l'établir à ce
  moment** — filet de sécurité avant de commencer le travail.
- **À la mise à jour de la description** : réestimer **uniquement si** le changement
  est assez conséquent pour impacter le temps/tokens prévu (sinon ne pas toucher).
  Tracer la réestimation dans le `.log.md` (ancienne → nouvelle valeur).

**Cumul effectif → poussé sur le ticket :** CF **17** `Tokens passés` reflète
`tokens_total` du frontmatter (recalé à chaque mise à jour Redmine).

