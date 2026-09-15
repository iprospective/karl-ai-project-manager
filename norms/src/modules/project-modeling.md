> 📂 **Module `project-modeling` — quand lire ceci :** je crée/range un projet ou une entité · partage cross-client · relation implements · je documente un aspect (CDC) · je note les contacts d'un client.
> **Outils :** `pm-client-new`, `pm-doctor` · **Préchargé par :** worker-analyst.

## Types d'entités

Le dossier `paths.entities_dir` (par défaut `{projects_root}/clients`) regroupe
**3 types d'entités**, distingués par le champ `type` du frontmatter
`{entity_client_dir}/overview.md` :

| `type` | Sémantique | Exemples |
|---|---|---|
| `client` (défaut) | Entité commerciale tierce qui commande des prestations | `lemathou` (perso/freelance Mathieu), `clientf`, `clienta` |
| `product` | Écosystème produit dont iprospective développe des modules (génériques) ou maintient une instance interne | `redmine`, `dolibarr`, `prestashop`, `symfony` |
| `self` | Entité où l'on est client de soi-même : outils internes, scripts propres, projets perso non commerciaux | `iprospective` (entreprise freelance), `lemathou` aussi (projets perso de Mathieu) |

Cohérent avec l'arborescence workspace : `/zfs/workspaces/<entité>/` existe au même niveau
pour chaque entité, qu'elle soit `client`, `product` ou `self`.

**Règle d'arbitrage** lorsqu'un projet pourrait vivre sous plusieurs entités (ex: un
module Dolibarr générique utilisé par plusieurs clients) :

- Si **commandé/financé par un client** → sous ce client (`paths.project` avec `entity=<client>`)
- Si **générique** (marketplace, communauté, usage interne propre) → sous l'écosystème produit (`paths.project` avec `entity=<product>`)
- Si **outil interne** non rattaché à un produit tiers → sous `self` (`paths.project` avec `entity=iprospective`)

Suivre l'engagement de livraison et la responsabilité des données.

## Contacts d'un client — `meta.yml :: contacts[]` (v1.69.0, RM2702)

Les personnes d'un client vivent dans le `meta.yml` de son core
(`.mmi-pm-client/meta.yml`), et **uniquement** là. Écriture par
`pm-client-contact.py` (`add` / `list` / `set` / `remove` / `mark-internal` /
`import-redmine`) — jamais à la main (tripwire #1).

```yaml
contacts:
  - last_name: Dupont              # NOM de famille
    first_name: Claire             # prénom
    email: claire@exemple.fr       # identifie la fiche (clé de `set` / `remove`)
    phone: "+33 6 12 34 56 78"     # CHAÎNE : le « + » et les zéros de tête comptent
    role: technique                # owner | decideur | technique | facturation | autre
    title: Gérant                  # fonction EN CLAIR — `role` est une catégorie, pas un titre
    internal: true                 # posé AUTOMATIQUEMENT sur nos propres adresses
```

Deux pièges, tous deux rencontrés en production :

- **`internal`** marque **nos** adresses (`iprospective.fr`…). Le gabarit de création
  en pose une chez **chaque** client : elle n'identifie donc aucun client et ne doit
  jamais servir à l'identifier — router un email entrant sur cette base enverrait tout
  notre courrier chez un client au hasard (cf. routage RM2669).
- Une fiche **entièrement vide** (`{name: "", email: "", role: owner}`) est un résidu
  de gabarit, pas un contact : les outils l'ignorent.

Une **boîte de service** (« Service informatique », « comptabilité ») est un contact
légitime sans nom propre : on renseigne `title` + `email`, sans `last_name`/`first_name`.

Le champ historique `name` (nom complet en un bloc) reste **lu en repli** tant que
toutes les fiches n'ont pas été reprises ; les nouvelles écritures utilisent
`last_name` / `first_name`.

> Un **annuaire de contacts indépendant** des clients (une personne rattachée à
> plusieurs clients/projets, avec un rôle par rattachement) est à l'étude — RM2703.
> Tant qu'il n'existe pas, `contacts[]` reste la source unique.

## Partage cross-client (used_by_clients / provided_by)

Un projet rangé sous une entité (`product` notamment) peut être **utilisé par plusieurs
clients**. Plutôt que de dupliquer le projet ou de jouer avec des symlinks à la main,
on utilise deux champs dans le frontmatter `project/overview.md` :

| Champ | Sens | Côté |
|---|---|---|
| `used_by_clients: [<slug>, ...]` | Liste des entités qui consomment ce projet | déclaré côté **fournisseur** (ex: module Dolibarr générique liste `clientf, clienta, clientb`) |
| `provided_by: <client>/<projet>` | Pointeur vers le projet fournisseur | déclaré côté **consommateur** (ex: un projet client qui s'appuie sur le module) |

Ces deux champs sont **redondants par construction**, pour permettre la lecture dans les
deux sens sans scan inverse coûteux. `scripts/pm-doctor.py` valide la cohérence des paires.

**Source de vérité** : le frontmatter, pas l'arborescence filesystem. Le chemin
canonique d'un projet est toujours `paths.project` (`entity=<owner>`,
`project=<projet>`).

**Vue cross-client (navigation humaine uniquement)** : un dossier `paths.entity_used_dir`
(par défaut `{entity}/projects_used`, au même niveau que `entity_projects_dir`, **pas**
un sous-dossier) peut contenir des symlinks relatifs vers les projets fournisseurs.
Ces symlinks sont **générés** par un script (`pm sync-views`) à partir des
`used_by_clients[]`, jamais édités à la main.

**Règles cross-client :**
- La cascade des aspects reste **mono-client** : un projet hérite uniquement de son
  client `client:`, jamais des clients listés dans `used_by_clients[]`.
- Tous les chemins dans le frontmatter (`outputs[]`, etc.) sont **canoniques**
  (résolus via `paths.project` avec l'`entity` propriétaire), jamais via `entity_used_dir`.
- Les scripts d'itération doivent utiliser `find -P` (ou `! -type l`) et **ne pas suivre
  les symlinks** dans `projects_used/`. Sinon double-comptage.
- L'édition se fait toujours via le chemin canonique. `projects_used/` est en lecture
  pour les humains.
- Suppression d'un usage : retirer le client de `used_by_clients[]` côté fournisseur ET
  `provided_by` côté consommateur si présent. `pm sync-views` nettoie les symlinks
  orphelins.

## Relation « implémentation » entre projets

Un projet client peut **implémenter** un projet général (un socle commun décliné par client) :
`implements` d'un côté, `implemented_by` de l'autre, et l'héritage de la cascade suit ce lien.
**Modélisation, champs, cas limites et exemples : `project-modeling-pratique`.**
