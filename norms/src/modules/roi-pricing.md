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

### Auto-incrémentation (hook Claude Code Stop)

Le hook `~/.claude/hooks/pm-task-tick.py` est déclenché à la fin de chaque
réponse Claude. Il :

1. Lit l'event JSON sur stdin (`session_id`, `transcript_path`, `cwd`, …)
2. Identifie le RM-id courant via une cascade **isolée par projet** (pas de
   sentinel global utilisateur — éviter les collisions multi-sessions) :
   - Fichier sentinel `<workspace>/.mmi-pm/CURRENT_TASK` (si cwd dans workspace)
   - Seule tâche `status: en_cours` dans le projet pointé par cwd `.mmi-pm`
   - (V2 prévue : sentinel par-`session_id` populé par un hook `UserPromptSubmit`
     qui parse les "RM1234" dans le prompt user)
3. Si aucune cible identifiée → log dans `~/.claude/logs/pm-task-tick-untracked.jsonl` et exit propre
4. Sinon : lit le dernier message assistant du transcript, somme les tokens
   par type, calcule le coût USD via `pm.pricing.yml`, met à jour le frontmatter
   du MD (atomique avec optimistic locking)
5. Append au `.log.md` une entrée concise (seuil : >1000 tokens total pour
   éviter le bruit, sinon silencieux)

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

### Journalisation par commit — temps + tokens consommés (obligatoire) — v1.21.0, convention activités + outillage v1.26.0

Le hook `pm-task-tick` (déclenché à chaque fin de réponse Claude) reste
**nécessaire** : il mesure et accumule en continu tokens + temps IA dans le
frontmatter MD — c'est la **base de calcul**. Le commit en est le **point de
report** vers Redmine.

**Règle** : à chaque commit **de travail** (unité = l'étape significative, cf. §
« Unité de traçabilité »), reporter sur le ticket Redmine le **delta** consommé
depuis le commit précédent, sous forme d'une **saisie de temps**
(`POST /time_entries.json`) :

- `issue_id` = le ticket ; `spent_on` = date du commit
- `hours` = temps IA wall-clock écoulé depuis le dernier commit (delta de
  `ai_time_total_minutes` ÷ 60). `hours=0` est **accepté** par l'instance —
  une étape sans temps mesuré reste donc une saisie datée valide (le tokens du
  delta, lui, est toujours porté par le CF 16).
- `activity_id` = **nature** du travail, dérivée du `type` de la tâche selon la
  **convention canonique ci-dessous** (≠ le tracker, qui encode la *catégorie*
  de ticket). Résolution outillée : `redmine_utils.activity_for_type(type)`.
- CF **16** `Tokens` = tokens consommés depuis le dernier commit (delta de
  `tokens_total`)
- commentaire = le hash + sujet du commit (lien `git.*`)

**Convention `type` de tâche → activité de temps Redmine** (source unique :
`redmine.reference.yml :: type_to_activity` ; surchargagle par saisie via
`pm-task-report.py --activity <id>`) :

| `type` NORMS | Activité Redmine | id | Nature |
|---|---|---|---|
| `feature` | `Developpement/Feature` | 31 | écrire une fonctionnalité neuve |
| `bugfix` | `Développement/Debug` | 16 | corriger un défaut |
| `maintenance` | `Développement/Refacto/Clean` | 30 | refacto, nettoyage, entretien |
| `infrastructure` | `SysAdmin/Conf/Debug` | 13 | déploiement, conteneurs, systemd, conf |
| `research` | `Audit/Analyse` | 10 | investigation, audit, exploration |
| `assistance` | `Assistance` | 11 | aide / support ponctuel |
| `autre` | `Autre` | 18 | fourre-tout (défaut de repli) |

> La résolution se fait au grain **tâche** (par son `type`). La refacto ou la
> feature qui vit *dans* un commit d'un ticket d'un autre type ne sera taguée
> finement qu'avec le futur **mode incrémental par commit**, où chaque commit
> pourra déclarer sa propre nature (override `--activity` en attendant).

Après le report, le CF **17** `Tokens passés` du ticket est resynchronisé sur
le cumul, et l'entrée est tracée dans le `.log.md` (cf. § « Référencer un commit »).

**Note Redmine accompagnante.** Ces métriques (temps + tokens du delta) sont
reprises dans la **note Redmine** du commit, aux côtés du résumé détaillé et de
la réf du commit. Le *quand* et le *quoi* de cette note sont définis **une seule
fois**, dans la matrice canonique § « Unité de traçabilité : l'étape
significative » — ne pas les redéfinir ici.

**Outillage : `scripts/pm-task-report.py`** (RM1819). Lit le frontmatter +
`.log.md` d'un ticket (`--rm-id`) ou de tous (`--all`), et pousse vers Redmine :
une **time_entry datée par entrée `Tokens :` du log** (`spent_on`, `hours` =
temps IA, CF 16 = tokens, `activity_id` selon la convention ci-dessus,
comments = titre de l'entrée), puis **resync CF 17** = `tokens_total`.
Idempotent : le `time_entry.id` de chaque saisie est historisé dans le bloc
`reporting.time_entries[]` du frontmatter (clé de dédup `<ts>#<tokens>`), un
re-run ne crée pas de doublon. Dry-run par défaut, `--apply` pour exécuter.

> **Reste à outiller (gap résiduel)** : le déclenchement **automatique au
> commit** (hook `post-commit` calculant le delta depuis le dernier report).
> Aujourd'hui `pm-task-report.py` se lance à la main / par lot. Le mode
> incrémental fin (un time_entry par commit, avec nature de travail déclarée
> par commit) viendra dessus.

