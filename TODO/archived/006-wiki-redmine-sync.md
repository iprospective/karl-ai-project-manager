# TODO 006 — Publication des documents projet vers le Wiki Redmine

| | |
|---|---|
| **Statut** | `pending` |
| **Priorité** | `#priority:high` |
| **Tags** | `#user-request` `#redmine` `#docs` `#norms` |
| **Origine** | Demande user — 2026-05-13 |
| **Créé** | 2026-05-13 |

## Contexte

Une tâche Redmine est traitée dans le cadre d'un **projet** Redmine. Certains
livrables produits côté MD pendant le traitement (cahier des charges,
documentation technique, schémas, etc.) ont vocation à vivre dans le **Wiki
du projet Redmine** correspondant, parce que :

- Le client / les intervenants Redmine les y attendent (= surface visible)
- Le repo `ai-projects` est privé (équipe interne), le Wiki Redmine est l'endroit
  partageable
- Cela évite de recoller du contenu en commentaire de ticket à chaque fois (cf.
  RM1658 où la v1 avait été collée en note avant qu'on switch sur pièces jointes)

Le sens unique **MD → Wiki** (read-only côté Wiki, source de vérité côté repo MD)
est l'hypothèse de travail. Le sens inverse (Wiki édité → MD réconcilié) sort
du scope MVP — à reconsidérer si un cas concret apparaît.

## Cas d'usage initiaux pressentis

À itérer avec le user au fil des projets, mais probables :

- Cahier des charges (`project/overview.md`, `project/data-model.md`, `project/roadmap.md`)
- Documentation d'aspects (`project/<aspect>.md` du dossier `aspects/`)
- Documentation technique (ex: décisions d'architecture, schéma de DB en image)
- Comptes-rendus de phase
- Glossaire / lexique métier
- Spec d'API exposée

## Questions ouvertes — à acter au fur et à mesure

### Q1 — Quels documents publier ?

Hypothèses :
- (a) Tout `outputs[]` avec `type: documentation` → automatique
- (b) Flag explicite par output : `publish_to_wiki: true` (par défaut `false`)
- (c) Décision côté projet : `project/overview.md :: publish.wiki: { auto, manual }`
- (d) Combinaison : flag par défaut au niveau projet, override par output

Recommandation initiale : **(b)** — explicit > implicit, le worker décide à la
soumission. Quand un pattern stable émergera (ex: cahier des charges Phase 0
toujours publié), on automatisera ce sous-cas.

### Q2 — Mapping MD → page Wiki

Hypothèses :
- Une page par fichier MD ? Une page par dossier `project/` ?
- Titre de page = slug du fichier (ex: `Overview`, `Data-model`, `Roadmap`) ?
- Hiérarchie : page parent = nom du projet ? Pages plates ?

Recommandation initiale : **une page Wiki par fichier MD**, titre déduit du
nom de fichier (CamelCase ou tel quel), page parent unique = `Cahier_des_charges`
(ou nom plus explicite) sous la racine du Wiki du projet. À tester sur un cas.

### Q3 — Format du contenu (Markdown / Textile)

Redmine accepte le format configuré au niveau de l'instance (Textile par défaut,
Markdown / CommonMark si activé). À vérifier sur https://tasks.iprospective.fr.

- Si Markdown actif → push direct du contenu, peut-être ajuster quelques
  conventions (notes de bas de page, liens internes).
- Si Textile → conversion via `pandoc` (`md → textile`).

Action préalable : tester avec un GET d'une page wiki existante pour voir le
format renvoyé.

### Q4 — Liens internes et images

- Liens internes MD entre fichiers (`[X](data-model.md)`) → réécrire vers `[[Data-model]]` (syntaxe Wiki Redmine)
- Images embarquées : upload `/uploads.json` → token → `wiki_page[uploads]` au PUT
- Convention de stockage des images dans le repo : `project/img/` ? À acter quand un premier cas apparaîtra.

### Q5 — Déclencheur de publication

Hypothèses :
- (a) Auto au passage `a_tester_verifier` (publication = "ce qui sera testé")
- (b) Auto au passage `ferme:resolu` (publication = "ce qui est validé")
- (c) Manuel via commande : `pm wiki publish <output>` ou `redmine-publish-wiki.py`
- (d) Hybride : preview manuelle, publication finale au passage `ferme:resolu`

Recommandation initiale : **(c)** pour la v1 (manuel, commande explicite), puis
on regardera les patterns qui émergent pour automatiser. Évite de publier
prématurément du contenu encore en travail.

### Q6 — Identité de publication

Auteur des éditions Wiki :
- Compte API `claude-chefproj-1` (déjà en groupe Managers) ?
- Compte dédié `claude-publisher` ?

Recommandation initiale : `claude-chefproj-1` réutilisé (pas d'éclatement
de comptes tant qu'il n'y a pas une raison concrète).

### Q7 — Versionning et conflits

Redmine versionne nativement les pages Wiki. Côté MD on a `git`. Quand on
republie, on écrase la version courante (Redmine garde l'historique).

Cas problématique : un humain édite la page Wiki entre deux publications →
ses modifications sont perdues à la prochaine publi. Mitigation :
- À la publi, GET la page actuelle et comparer le contenu attendu (=
  version précédemment publiée) avec le contenu courant côté Wiki. Si divergence
  → warn ou fail (à éventuellement forcer avec `--overwrite`).
- Stocker dans la frontmatter de l'output côté MD : `wiki: { page: ..., last_published_at: ..., last_published_version: N }`.

À implémenter au moment où le risque se matérialise.

## API Redmine Wiki — rappels techniques

```
GET    /projects/{id}/wiki/index.json
GET    /projects/{id}/wiki/{title}.json
PUT    /projects/{id}/wiki/{title}.json  -> {"wiki_page": {"text": "...", "comments": "...", "uploads": [...]}}
DELETE /projects/{id}/wiki/{title}.json
```

Auth : même `?key=<api_key>` que pour `/issues`. Permission requise : "Edit wiki
pages" — vérifier que le groupe Managers l'a (probable).

## Phasage proposé

### Phase 1 — MVP minimal
- [ ] Vérifier format Wiki (Textile vs Markdown) et permission "Edit wiki pages" du compte API
- [ ] Script `scripts/redmine-publish-wiki.py` : MD path → page Wiki d'un projet donné
  - Args : `--file <md>`, `--project <id>`, `--page <title>`, `--parent <title|optional>`
  - Conversion Markdown → format Wiki si nécessaire
  - Pas encore d'images, pas encore de liens internes
- [ ] Test sur un projet de test avec un fichier simple
- [ ] Ajout NORMS § "Publication vers Wiki Redmine" (sens unique, déclencheur manuel, identité)

### Phase 2 — Intégration au workflow MD
- [ ] Extension du schéma `outputs[]` : `wiki:` optionnel par output (page, parent, last_published_*)
- [ ] Validator étendu pour cohérence
- [ ] `pm wiki publish [<output>]` côté CLI (TODO 003)
- [ ] Mise à jour automatique de la frontmatter après publi

### Phase 3 — Médias et liens
- [ ] Images embarquées : upload + rewrite des URLs
- [ ] Liens internes MD → liens Wiki (`[[Page]]`)
- [ ] Convention de stockage `project/img/`

### Phase 4 — Automatisation conditionnelle
- [ ] Publi auto sur transitions de statut (selon politique par projet)
- [ ] Détection de conflits (humain a édité côté Wiki)

## Critères d'acceptation MVP (Phase 1)

- Un document MD du repo peut être publié vers une page Wiki d'un projet Redmine via une commande
- Le contenu publié est lisible et correctement formatté (titres, listes, code)
- La commande est idempotente (re-publi = mise à jour, pas duplication)
- Les permissions et le format Wiki de l'instance sont documentés dans NORMS

## Liens

- Tâche d'origine : RM1658 (premier cas concret avec attachements, à transposer en Wiki dans le projet associé)
- TODO 003 (CLI `pm`) — verra arriver `pm wiki publish`
- NORMS § "Lien Redmine ↔ MD" — à enrichir d'une section Wiki

## Journal

- **2026-05-13** : TODO créée. Cadrage initial, questions ouvertes listées. À itérer au fil des projets.
