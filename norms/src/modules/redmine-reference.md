## Filtrage IA — quels tickets Redmine sont synchronisés en MD

L'instance Redmine contient bien plus de tickets que ceux que PM doit
tracker. Pour éviter d'engloutir des centaines de tickets historiques en
MD (et leurs journaux) sans valeur ajoutée pour les agents, un **mutex
explicite** discrimine :

| Côté Redmine | Comportement PM |
|---|---|
| Ticket **sans** CF `IA` | Invisible pour PM. Aucun fetch, aucun MD, aucun sync. |
| Ticket **avec** CF `IA = "IA"` | Tracké par PM. MD local créé, sync bidirectionnelle active. |

**Mécanisme** : un custom field global de l'instance Redmine, type `List`,
nom `IA`, une seule valeur possible (`IA`). Présent sur tous les trackers
et tous les projets (`is_for_all: true`).

### Configuration

1. **Créer le CF** en UI Redmine (l'API REST ne supporte pas la création
   de custom fields, retourne HTTP 403) :
   - *Administration → Custom fields → Issues → New custom field*
   - Format `List`, Name `IA`, Possible values `IA`, Used as filter ✓,
     Searchable ✓, For all projects ✓, tous les trackers cochés
2. **Récupérer l'id** retourné, le stocker dans `.env` :
   ```
   REDMINE_CF_IA_ID=<id>
   ```
3. Documenté dans `.env.example`.

Si `REDMINE_CF_IA_ID` n'est pas défini, le filtre est **désactivé** (mode
rétrocompat : tous les tickets sont considérés trackables). Recommandé
uniquement pendant la phase de mise en place.

### Effet sur les scripts

| Script | Comportement quand le filtre est actif |
|---|---|
| `redmine-fetch-task.py` | Refuse de créer le MD si le ticket n'est pas tagué (sauf `--force`) |
| `redmine-fetch-updates.py` | Skip la sync si le ticket n'est plus tagué (signale le drift) |
| `pm-task-add.py` | Set automatiquement le CF `IA` au POST (les nouveaux tickets PM sont IA par construction) |
| `redmine-tag-ia.py` | Helper d'opt-in/opt-out : tag/untag un ticket existant, déclenche le fetch si nouveau tag |

### Opt-in d'un ticket existant

Pour faire entrer un ticket Redmine historique sous gestion PM :

```bash
./scripts/redmine-tag-ia.py <RM-id>           # tag + fetch + crée le MD local
./scripts/redmine-tag-ia.py <RM-id> --no-fetch # tag seulement, MD à créer plus tard
```

Pour le retirer :

```bash
./scripts/redmine-tag-ia.py <RM-id> --untag   # warning si MD local existe
```

### Règles d'intégrité

- **Pas de MD sans CF IA** : si un MD existe pour un ticket qui n'est pas
  tagué, c'est un drift à corriger (re-tag ou archive du MD).
- **Pas de CF IA sans MD** : un ticket tagué mais sans MD est en attente
  de fetch (`redmine-fetch-task.py --issue <id>` ou
  `redmine-tag-ia.py <id>` qui le déclenche).
- **Tag = consentement à la collecte** : les agents IA peuvent lire les
  journaux du ticket et appender au `.log.md`. Ne pas tagger les tickets
  contenant des données sensibles non destinées à un LLM tiers (Anthropic API).

### Test d'un ticket vis-à-vis du filtre

```bash
# Côté Redmine
curl -sS -H "X-Redmine-API-Key: $REDMINE_USER_MAIN_API_KEY" \
  "$REDMINE_URL/issues/<id>.json" | python3 -c "
import sys, json
issue = json.load(sys.stdin)['issue']
for cf in issue.get('custom_fields', []):
    if cf['name'] == 'IA': print(f'IA = {cf.get(\"value\")!r}')"
```

## Synchronisation de la configuration Redmine (obligatoire, périodique) — v1.21.0

Les IDs Redmine (statuts, trackers, priorités, custom fields, activités de
temps passé) sont **propres à chaque instance** et **mutables** : un admin
peut ajouter un statut, renommer un CF, créer une activité. Or PM les
**référence en dur** à plusieurs endroits :

- `.env` : `REDMINE_CF_IA_ID` (et autres IDs sensibles à venir)
- `knowledge/redmine/api.md` : mappings `NORMS_TO_REDMINE_STATUS`,
  `TRACKER_TO_TYPE`, et IDs des CF dédiés
- scripts : constantes (`CF_RAISON_FERME_ID = 11`, IDs CF ROI/tokens, …)

Un ID périmé fait **échouer silencieusement** un POST/PUT (CF ignoré) ou
mappe un mauvais statut. C'est une classe de bug difficile à diagnostiquer.

**Règle** : avant toute session qui touche à l'intégration Redmine (création
de tâche, sync de statut, push de métriques, bootstrap), et **a minima
périodiquement** (ou en cas de comportement inattendu), **revérifier que la
config locale colle à l'instance live**. En cas de drift → corriger `.env` /
`knowledge/redmine/api.md` / les constantes des scripts, puis committer.

**Quoi resynchroniser, et endpoints de référence** (lecture, clé API) :

| Dimension | Endpoint | Référence locale |
|---|---|---|
| Custom fields (issue **et** time_entry) | `GET /custom_fields.json` (admin) | `knowledge/redmine/api.md`, `.env`, constantes scripts |
| Statuts de ticket | `GET /issue_statuses.json` | `NORMS_TO_REDMINE_STATUS` |
| Trackers | `GET /trackers.json` | `TRACKER_TO_TYPE` |
| Priorités | `GET /enumerations/issue_priorities.json` | mapping priorité |
| Activités de temps passé | `GET /enumerations/time_entry_activities.json` | mapping type→activité (cf. § ROI) |

**CF dédiés actuels de l'instance iprospective** (issue sauf mention) — à
revalider lors du resync, ne pas présumer stables :

| ID | Type | Nom | Usage PM |
|---|---|---|---|
| 15 | list (issue) | `IA` | filtrage IA (cf. § Filtrage IA) |
| 21 | int (issue) | `Tokens prévus` | estimation tokens (cf. § ROI) |
| 22 | float (issue) | `Temps estimé IA (h)` | estimation temps IA |
| 17 | int (issue) | `Tokens passés` | cumul tokens effectifs |
| 16 | int (time_entry) | `Tokens` | tokens d'une saisie de temps (par commit) |
| 5 | int (issue) | `Gain/Perte (eq h dev/mois)` | gain ROI |
| 6 | int (issue) | `ROI` | ratio ROI |
| 11 | enum (issue) | `Raison Fermé` | `close_reason` |
| 20 | enum (issue) | `Task type` | taxonomie **fine** du `type` (cf. note ci-dessous) |

**Tracker (coarse) vs CF `Task type` (fin).** Le `type` NORMS est plus riche
(13 valeurs) que les 4 trackers Redmine (`Anomalie`/`Evolution`/`Assistance`/
`Tâche`). Le **tracker** porte la catégorie *coarse* (`TYPE_TO_TRACKER` :
`documentation`, `infrastructure`, `maintenance`, `autre` retombent tous sur
`Tâche`/4). Quand un type n'a pas de tracker dédié, son détail est porté par le
**CF 20 `Task type`** (enumeration) si une valeur correspond — mapping **source
unique** `redmine.reference.yml :: task_type_cf` (ex. `documentation` → val 42).
`pm-task-add` le pose à la création, `redmine-fetch-task` le relit (il **prime**
sur le tracker pour reconstituer le `type` fin). Ajouter une valeur d'énumération
côté Redmine + une ligne dans `task_type_cf` suffit à câbler un nouveau type fin.

> **Outillage souhaité (gap connu)** : un script `scripts/redmine-config-check.py`
> qui diff la config live contre les références locales et signale tout drift.
> En attendant, le contrôle est manuel (requêtes `GET` ci-dessus).

**Règle de propagation — source unique → consommateurs (v1.37.0).** Quand tu fais
évoluer un **paramètre canonique** (taxonomie de `type` et mappings
`TYPE_TO_TRACKER` / `type_to_activity` / `task_type_cf`, IDs Redmine, statuts,
priorités, énumérations…), mets à jour **dans le même changement** *tous* les
scripts et consommateurs qui le référencent — y compris ceux qui en dérivent une
liste pour l'UI. Préférer une **lecture à l'exécution** de la source (ex. le
cockpit karl-agent peuple son sélecteur de types via `pm-task-add --list-types`,
plutôt qu'une liste codée en dur) ; à défaut, le miroir est resynchronisé dans le
même commit. Une source de vérité et son miroir ne doivent **jamais diverger en
silence** — c'est la même classe de bug que le drift de config Redmine ci-dessus,
côté *écriture* cette fois. Avant de clore : vérifier la cohérence
`pm-task-add.py::TYPE_TO_TRACKER` ⇄ `redmine.reference.yml` ⇄ doc/UI.

