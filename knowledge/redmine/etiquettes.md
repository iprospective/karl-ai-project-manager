# Étiquettes de ticket — le CF « Étiquettes » (RM2829, chantier RM2828)

Le **domaine** d'un ticket (`front`, `bo`, `bdd`, `refacto`, `livraison`,
`tunnel-de-commande`…) se porte par un **custom field Redmine « liste » à valeurs
multiples**, partagé à tous les projets, tenu en parité avec le champ `tags` du
frontmatter PM.

## Pourquoi un CF, et pas les catégories ni un plugin

Constat vérifié sur l'instance le 2026-08-25 :

- **Pas de tags en standard** dans Redmine, et **aucun plugin de tags installé**
  (`GET /tags.json` → 404). Un plugin serait une dépendance à porter à chaque
  montée de version.
- Les **catégories de ticket** existent et sont natives
  (`GET /projects/<id>/issue_categories.json` répond, aucune définie à ce jour),
  mais : **une seule par ticket**, et le jeu de valeurs est **propre à chaque
  projet**. « refacto » serait à recréer partout, et un ticket ne pourrait pas
  être « front » ET « refacto ».
- Un **CF liste multi-valeurs** partagé à tous les projets donne exactement des
  tags contrôlés : plusieurs par ticket, vocabulaire commun, filtrables et
  groupables dans les vues, sans dépendance.

Les catégories restent disponibles, plus tard, pour un vocabulaire **propre à un
projet** — elles ne sont pas en concurrence avec les étiquettes.

## Ce qui a été créé (2026-08-26)

**CF id 32, nom « Tags »**, `customized_type: issue`, **format `enumeration`**,
`multiple: true`, `is_filter: true`, trackers Anomalie / Evolution / Assistance /
Tâche. Valeurs initiales : Front, DB, Refacto, BO, Config, Debug,
Tunnel de commande.

⚠ **Format `enumeration`, pas `list`** : chaque valeur possible a un **id**
(45, 46…) et c'est **cet id** que l'API attend — pousser un libellé est refusé.
La table `slug ↔ label ↔ id` vit dans **`tags.registry.yml`** (racine du dépôt PM,
comme `redmine.reference.yml`), lue par `pm_tags`. Le registre doit rester
synchrone avec la définition Redmine : une valeur ajoutée dans l'UI et absente du
registre ne peut pas être poussée.

Conséquence directe : une étiquette du frontmatter **hors registre** reste locale.
Elle n'est pas perdue (`pm-task-list --tag`, recherche cockpit continuent de la
voir) et `pm-task-tag` l'annonce plutôt que de laisser croire qu'elle est montée.

## Création — geste HUMAIN, l'API ne le fait pas

L'API REST de Redmine expose les custom fields en **lecture seule** : il n'y a
pas de `POST /custom_fields.json`. La création passe par l'UI admin.

*Administration → Champs personnalisés → Nouveau champ personnalisé*

| Réglage | Valeur |
|---|---|
| Type d'objet | **Demande** |
| Format | **Liste** |
| Nom | **Tags** (nom retenu à la création) |
| Valeurs possibles | `front`, `bo`, `bdd`, `refacto`, `livraison`, `tunnel-de-commande` (une par ligne, en **slug minuscule** — c'est la forme que `pm_tags.normalize` produit) |
| Valeurs multiples | **coché** — sans lui, un ticket ne peut porter qu'un domaine |
| Pour tous les projets | **coché** — c'est ce qui rend le vocabulaire transverse |
| Utilisé comme filtre | **coché** — sinon l'étiquette ne sert à rien dans les vues |
| Trackers | ceux du travail (Evolution, Bug, Tâche, Assistance…) |

Le champ **Valeurs possibles** vaut règle : une étiquette hors liste est refusée
par Redmine. Pour en ajouter une, on l'ajoute là — et l'outillage suit.

## Après la création — brancher l'outillage

1. Relever l'**id** du champ (visible dans l'URL de son écran d'édition,
   `/custom_fields/<id>/edit`). **Ne pas le deviner** : les ids sont séquentiels
   à l'instance et attribués en concurrence (tripwire NORMS #13).
2. Le déclarer dans **`redmine.reference.yml`**, section `custom_fields` :

   ```yaml
     <id>: {name: "Étiquettes", format: list, type: issue, used_by: "tags[] du frontmatter (pm_tags, RM2829)"}
   ```

3. Vérifier : `scripts/redmine-config-check.py` doit rester vert (il diffe la
   référence contre la config live).
4. Contrôle de bout en bout :

   ```bash
   pm-task-tag.py <RM> --add front,refacto     # → frontmatter + Redmine
   pm-task-tag.py <RM>                          # → lit
   pm-task-sync.py <RM>                         # → relit le CF vers le frontmatter
   ```

Un **override** ponctuel reste possible sans toucher la référence :
`REDMINE_CF_TAGS_ID=<id>` dans le `.env` (même convention que les autres CF).

## Une vue Redmine par étiquette (une fois le CF créé)

Le CF étant **utilisé comme filtre** et **pour tous les projets**, il apparaît
dans les filtres de la liste des demandes :

1. *Demandes → Filtres → Étiquettes* → `est` → choisir une ou plusieurs valeurs ;
2. *Options → Grouper par : Étiquettes* pour une vue ventilée ;
3. « Enregistrer » la requête (cocher « Pour tous les projets » si la vue doit
   suivre le vocabulaire transverse).

Côté PM, la même ventilation existe hors Redmine :
`pm-conso-report.py --by tag` — coût, tokens et temps par domaine. ⚠ un ticket
portant deux étiquettes compte dans les deux groupes : la somme des lignes
dépasse le total, et le rapport le dit.

## Tant que le CF n'existe pas

Rien ne casse : `pm-task-tag` écrit le frontmatter, `pm-task-list --tag` filtre,
et le push Redmine est **annoncé comme non fait** (jamais silencieux). La parité
est un objectif, pas un blocage.

## Router le travail : étiquette → rôle d'agent (RM2833)

Une étiquette dit le **domaine** ; les rôles (`agents/worker-*.md`) disent **qui
sait le traiter**. La table se déclare dans le `meta.yml` du projet (ou du
client — cascade NORMS, le projet surcharge), jamais en dur :

```yaml
tag_roles:
  front: dev
  bdd: db
  infra: infra
  design: design
```

Ce qu'on en fait : `pm-task-brief` affiche « rôle suggéré », et l'écran de
lancement d'une session du cockpit le montre puis le cite dans la consigne (de
quoi charger `agents/worker-<rôle>.md`).

**Ça propose, ça n'assigne pas.** Réassigner un ticket, c'est changer son
propriétaire — donc le verrou d'écriture (« Redmine est le mutex ») — et cela
reste un geste humain. Quand plusieurs étiquettes routent, le départage est
alphabétique : arbitraire mais stable, et les autres candidates sont nommées.

## Vocabulaire

Un slug : minuscules, sans accent, tirets — `pm_tags.normalize` s'en charge, si
bien que « Tunnel de Commande », « tunnel_de_commande » et « TUNNEL DE COMMANDE »
sont **une seule** étiquette. Plafond : 12 par ticket (au-delà, une étiquette ne
distingue plus rien).
