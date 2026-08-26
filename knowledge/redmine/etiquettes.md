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

## Création — geste HUMAIN, l'API ne le fait pas

L'API REST de Redmine expose les custom fields en **lecture seule** : il n'y a
pas de `POST /custom_fields.json`. La création passe par l'UI admin.

*Administration → Champs personnalisés → Nouveau champ personnalisé*

| Réglage | Valeur |
|---|---|
| Type d'objet | **Demande** |
| Format | **Liste** |
| Nom | **Étiquettes** |
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

## Tant que le CF n'existe pas

Rien ne casse : `pm-task-tag` écrit le frontmatter, `pm-task-list --tag` filtre,
et le push Redmine est **annoncé comme non fait** (jamais silencieux). La parité
est un objectif, pas un blocage.

## Vocabulaire

Un slug : minuscules, sans accent, tirets — `pm_tags.normalize` s'en charge, si
bien que « Tunnel de Commande », « tunnel_de_commande » et « TUNNEL DE COMMANDE »
sont **une seule** étiquette. Plafond : 12 par ticket (au-delà, une étiquette ne
distingue plus rien).
