---
type: knowledge
product: redmine
topic: gotchas
created: 2026-05-14
---

# Redmine — pièges et comportements surprenants

Liste cumulative, alimentée à chaque épisode où on a perdu du temps.

## API

### Silent drop sur permission manquante

`PUT /issues/{id}.json` avec `notes` + `status_id` :
- Si le compte n'a que "Add notes" : la note est créée, **le status_id est silencieusement ignoré**.
- Réponse HTTP 204 OK quand même, journal créé sans détail de change.
- Détection : refetch et comparer ; ou regarder `journal.details[]` vide.
- Fix : permission "Edit issues" via rôle / groupe Managers.

### Pas de `?since=` pour les journals

Pour récupérer les nouveaux journaux depuis la dernière consultation, il faut tout
fetch via `?include=journals` et filtrer côté client sur `j.id > last_seen`.

### Auteur d'un ticket n'a que `name` dans `/issues.json`

Pour résoudre le `login`/`username` (utile en chaîne d'agents), faire un appel
supplémentaire `GET /users/{id}.json`.

### Le `project.identifier` n'est pas dans le payload `/issues/{id}.json`

`issue.project = { id, name }` mais pas l'`identifier`. Pour résoudre, faire `GET
/projects/{id}.json` séparément.

## Wiki

### Pages wiki — historique via `wiki_content_versions`

Une page wiki a :
- `wiki_contents` (1 ligne = état courant)
- `wiki_content_versions` (N lignes = historique)

Lors d'une migration de format, **ne pas oublier `wiki_content_versions`** sinon
l'historique reste dans l'ancien format → mal rendu après bascule.

### Compression wiki (gzip)

Le `Setting.wiki_compression` peut être `'gzip'` ou vide.
- Si `gzip` : `wiki_content_versions.data` est un blob `Zlib::Deflate.deflate(text, BEST_COMPRESSION)`
- Sinon : `data` contient le texte brut
- Le model `WikiContentVersion` expose un getter/setter `text` qui gère la
  (dé)compression transparente — mais `update_column(:data, ...)` BYPASS cette logique.
- En migration : lire via `v.text`, écrire via `v.update_columns(data: ..., compression: v.compression)`
  en respectant la compression d'origine de chaque version.

## Plugins

### Double-chargement de plugins

Si on a un dossier `plugins/` ET un `plugins-enabled/` (ou similaire), et qu'une install
clonée pointe via symlink sur le premier alors qu'une autre pointe sur le second, le
Rails démarre avec des warnings `already initialized constant`. Non bloquant, mais sale.

À résoudre : un seul chemin canonique de plugins, pas de duplication par path.

## Rake / scripts

### `rake -T` ne liste pas les tasks sans `desc`

Une rake task écrite sans `desc "..."` n'apparaît pas dans `rake -T`. Utiliser
`rake -A -T` (all). Le user qui tape `rake -T` croira que sa task n'est pas chargée.

### `Setting.welcome_text` n'est pas un attribut model

Setting est un module spécial — l'écriture passe par `Setting.welcome_text =` (et lecture
par `Setting.welcome_text`). Le setter persiste via une row dans `settings`.

### `find_each` itère par batch (default 1000), pas en ordre strict

`Model.find_each` charge les records par batch de 1000 (modifiable via `:batch_size`).
**L'ordre est par primary key croissant** par défaut. Si un crash survient au milieu,
les éléments traités sont ceux d'ID < (last_seen_id) — pas un préfixe contigu si le
crash survient en mémoire avant le commit du batch.

### `update_column` bypass tout

`model.update_column(:attr, value)` :
- Pas de validations
- Pas de callbacks
- Pas de mise à jour de `updated_at`
- Écriture SQL directe

Utile pour migrations massives où on veut tagger comme "non-touché" niveau timestamps.
Dangereux pour les modèles qui ont des callbacks importants (ex: indexation
ElasticSearch, compression wiki — cf. plus haut).

## Conversion Textile → Markdown (pandoc)

Voir [textile-to-markdown-migration.md](./textile-to-markdown-migration.md) pour la procédure complète. Pièges spécifiques :

### Wiki links `[[Page_Name|label]]` cassés par échappement

Pandoc échappe `_` en `\_` partout, y compris à l'intérieur des `[[...]]`. Le résultat
`[[Page\_Name|label]]` est cherché tel quel par Redmine → page introuvable, lien mort.

Le script Planio un-escape `\[\[` et `\]\]` mais oublie les `_` à l'intérieur. Patch
nécessaire :
```ruby
markdown.gsub!(/\[\[([^\]]+)\]\]/) { "[[#{$1.gsub('\\_', '_')}]]" }
```

### Tables Textile avec col/row span ou alignement

Pandoc ne supporte pas `|\2.` (colspan), `|/2.` (rowspan), `|>.` / `|<.` / `|=.`
(alignement). Le script Planio les drop avant pandoc.

### `<pre>` sans blank line avant

Pandoc transforme en "indented code block" et peut insérer `<!-- end list -->`, que
Redmine ne supporte pas en Markdown. Le script Planio force une blank line avant.

### `@text@domain@` (inline code Textile contenant `@`)

Pandoc ne le supporte pas. Le script Planio le tag avec un placeholder
`pandoc-unescaped-single-backtick` avant pandoc, puis remplace par backtick après.

### pandoc plante sur input vide

Si on appelle `pandoc -f textile -t gfm -i empty_file`, il peut planter (selon version).
Solution : skip côté caller si la string est vide.

### Versions de pandoc

- 2.9.x (Ubuntu 22.04) : suffisant pour la conversion basique, médiocre sur tableaux complexes
- 3.x : meilleur sur tableaux et structures complexes — installer via snap ou binary
