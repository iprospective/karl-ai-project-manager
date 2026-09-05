> 📂 **Module `task-links` — quand lire ceci :** je lie / fais dépendre / parente deux tickets.
> **Outils :** `pm-task-link` · **Préchargé par :** —.

## Liens entre tâches

Le frontmatter d'une tâche supporte plusieurs types de liens, chacun avec une
sémantique propre. Ces champs sont **symétrisés** (RM-id miroir maintenu côté
cible) et synchronisés avec les `relations` Redmine via le script
`scripts/pm-task-link.py`.

| Champ | Cardinalité | Sémantique | Miroir côté cible | Redmine `relation_type` |
|---|---|---|---|---|
| `parent_task` | `int \| null` | Hiérarchie : ce ticket a un parent | `sub_tasks` (attribut `parent_issue_id`) | — (attribut d'issue) |
| `sub_tasks` | `list[int]` | Hiérarchie : enfants directs | `parent_task` (attribut `parent_issue_id`) | — (attribut d'issue) |
| `depends_on` | `list[int]` | Bloquant : A doit attendre B (B finit avant A) | `blocks` côté B | POST sur B : `blocks` → A |
| `blocks` | `list[int]` | Bloquant : A doit finir avant B (réciproque de `depends_on`) | `depends_on` côté B | POST sur A : `blocks` → B |
| `relates` | `list[int]` | **Lien latéral non-bloquant** : sujet/famille commun | `relates` côté cible | POST `relates` |
| `refs` | `list[obj]` | Référence externe libre (URL, commit, ticket partenaire) | — | — (champ libre, pas de relation Redmine) |

### `refs: partner_issue` — ticket d'un gestionnaire partenaire (v1.69.0)

Quand un projet déclare un **provider secondaire** (gestionnaire de tâches d'un client
ou d'un prestataire, cf. `providers.task[]` du `meta.yml` — RM2653), un ticket PM peut
être **rattaché** à un ticket de ce gestionnaire. Le lien est un item `refs[]` typé :

```yaml
refs:
  - type: partner_issue
    instance: redmine-matnat      # DOIT être un secondaire déclaré du projet
    issue_id: 1234
    url: https://tasks.materiaux-naturels.fr/issues/1234
    role: mirror                  # mirror | upstream | related
    last_seen_journal_id: null    # pointeur de synchro, PAR LIEN
    added: 2026-08-12
```

| `role` | Sens |
|---|---|
| `mirror` | ce ticket **est** le mien vu de chez eux (1↔1) — **un seul** par tâche |
| `upstream` | leur ticket est la demande d'origine |
| `related` | voisinage : plusieurs de leurs tickets peuvent toucher la même tâche |

**Règles.** Le lien se pose **toujours** avec `pm-task-partner` (tripwire #1), jamais à
la main : l'outil valide que l'instance est un secondaire déclaré, refuse un doublon
`(instance, issue_id)` ou un second `mirror`, pose le CF Redmine « Ticket partenaire »,
journalise, et poste la note de rattachement chez le partenaire.

**Le partenaire ne décide de rien chez nous** : un `partner_issue` ne modifie **aucun**
champ du frontmatter (statut, priorité, assignation) — au mieux, sous le régime
`incoming` du miroir d'états (ci-dessous), il en **propose** un que nous validons. Le provider **primaire** reste la
seule source de vérité ; ce qui vient d'un secondaire s'écrit dans le `.log.md`.

Quand le secondaire porte `link.policy: required` (« tout ce que je fais pour eux doit
être rattaché chez eux »), `pm-doctor` signale chaque ticket **ouvert** sans lien.

**Importer ce qui se dit chez eux** (v1.69.0) : `pm-task-partner pull <RM-id>` (ou
`--all`, câblable en cron) lit le ticket distant et **appende au `.log.md`** les notes
nouvelles — citées, sous un en-tête qui nomme l'instance — et leur statut **brut**
(leur libellé, pas un état NORMS). Réglable par secondaire via
`sync.pull: {notes, status}`. Le pointeur de lecture (`last_seen_journal_id`) vit **dans
le lien**, jamais dans `redmine_last_journal_id` qui suit l'instance primaire — deux
boucles, deux pointeurs. Un partenaire injoignable produit un avertissement, jamais un
échec : le PM ne dépend pas de la disponibilité d'un tiers.

**Rendre compte chez eux** (v1.69.0) : une transition de statut poste une **note de
suivi** chez le partenaire — **seulement** si le secondaire déclare ce statut dans
`sync.push.on`. **Défaut : rien ne part.** L'activation se fait projet par projet, après
revue du gabarit : une note poussée chez un tiers ne se rattrape pas.

* **Écriture pauvre** : une note de texte, jamais un statut, un champ personnalisé ni une
  saisie de temps — les ids de `redmine.reference.yml` sont ceux d'iProspective.
* **Gabarit fermé** : identifiant de suivi, titre, état **en clair**
  (`a_tester_demandeur` → « livré, en attente de validation » : le partenaire ne connaît
  pas notre machine d'états), plus un message rédigé à la main. Pas de chemin, d'hôte, de
  branche, d'environnement de test, ni d'URL interne — notre Redmine ne lui est pas
  accessible de toute façon.
* Le push est **best-effort** : il n'échoue jamais une transition déjà écrite côté PM.
* `pm-task-partner link --create-remote` crée le ticket manquant chez eux puis le
  rattache ; il exige un `create.tracker_id` déclaré (les ids de tracker ne sont pas
  portables — on ne devine pas).

**Miroir d'états** (v2.16.0, RM2746) : les deux états peuvent enfin se répondre — sans
que le partenaire ne prenne la main. Trois régimes, cumulables, déclarés par secondaire
dans `sync.mirror` (meta.yml) et surchargeables **par ticket** en cochant le CF Redmine
**35 « Sync ticket externe »** (miroir local : `state_mirror`, rapatrié par
`pm-task-sync`) :

| Régime | Ce qu'il fait | Écrit chez eux | Change notre statut |
|---|---|---|---|
| `signal` | constate la divergence et la rapporte (`pm-doctor`) | non | non |
| `outgoing` | pose **notre** statut chez eux | oui | non |
| `incoming` | **propose** une transition chez nous | non | seulement après validation |

* **Défaut : inerte.** Sans déclaration, rien ne change — ni projet, ni ticket.
* `signal` est le socle : il est ajouté d'office dès qu'un autre régime est actif.
* La **table de correspondance** est déclarative (`sync.mirror.map`), jamais en dur :
  `en_cours: "En cours"` suffit à comparer, `{label: "En cours", id: 2}` est requis pour
  écrire — l'API pose un statut par son id. Un statut absent de la table n'est pas mappé,
  et ne produit ni divergence ni écriture.
* Le constat est **hors ligne** : il relit le `last_seen_status` déposé par le pull, donc
  `pm-doctor` voit la divergence sans ouvrir une connexion.
* **Aucune transition automatique.** Le régime `incoming` produit une proposition, qu'un
  humain accepte (`pm-task-partner mirror <id> --accept`, qui délègue la transition à
  `pm-task-status-update`) ou refuse (`--reject`, mémorisé : la même proposition ne
  revient pas). Une correspondance ambiguë — plusieurs de nos statuts visant le même
  libellé chez eux — ne propose **rien** et se tranche par `sync.mirror.map_in`.
* Le CF est **mono-valeur** : un ticket porte un seul régime. D'où la valeur
  **`Mirror`**, alias des **deux sens** (`outgoing` + `incoming`) — pas un quatrième
  régime : elle s'étend, et le code continue de raisonner sur les trois. Un CF laissé
  **vide** fait hériter du réglage projet ; `none` (accepté par le code, pas encore
  dans l'énumération Redmine) soustrait au contraire le ticket à ce réglage.


**Règles d'intégrité :**
- Tout lien `relates` / `depends_on` / `blocks` doit avoir son miroir côté cible.
  Si l'un est présent sans l'autre, c'est un drift à corriger via
  `pm-task-link sync <rm-id>`.
- `parent_task` est unique (au plus un parent par tâche).
- Un ticket ne peut pas se lier à lui-même.
- `pm-task-link rm` supprime les deux côtés.

**Sens des dépendances** : ne pas confondre. Si **A dépend de B**, alors
`A.depends_on = [B]` ET `B.blocks = [A]`. Côté Redmine, c'est une seule
relation `blocks` postée depuis B vers A.

### Hiérarchie parent/enfant (v1.20.3)

`parent_task` / `sub_tasks` ne sont **pas des relations Redmine** mais l'**attribut
natif d'issue `parent_issue_id`** (colonne « Redmine `relation_type` » = `—` dans le
tableau). Ils ne transitent donc pas par `/issues/<id>/relations.json` mais par un
`PUT parent_issue_id` sur l'enfant. La réflexion MD ↔ Redmine est outillée — **ne jamais
éditer ces champs à la main** :

| Geste | Commande | Effet |
|---|---|---|
| Créer un ticket enfant | `pm-task-add … --parent <RM>` | POST avec `parent_issue_id` + `parent_task` enfant + `sub_tasks` parent |
| (Re)poser / déplacer le parent d'un ticket existant | `pm-task-link parent <child> <parent>` | PUT Redmine + migre `sub_tasks` ancien→nouveau parent |
| Détacher | `pm-task-link parent <child> --unset` | PUT Redmine (parent vidé) + retire de `sub_tasks` du parent |
| Réconcilier depuis Redmine | `pm-task-sync <RM>` | lit `issue.parent.id` → `parent_task` + maintient les `sub_tasks` locaux |

Le cœur (réflexion frontmatter des deux côtés + logs) vit dans `scripts/pm_hierarchy.py`,
partagé par les trois scripts. Quand le parent n'est pas tracké localement (ticket
Redmine hors-PM), le champ enfant est posé mais `sub_tasks` n'est pas maintenu (no-op
silencieux, le lien Redmine reste correct).

**Règles d'intégrité hiérarchie :**
- `parent_task` est unique (au plus un parent par tâche).
- Pas d'auto-parent ni de cycle (Redmine refuse les cycles au PUT ; les scripts
  refusent l'auto-parent en amont).
- `sub_tasks` est dérivé : il doit toujours refléter l'ensemble des enfants dont le
  `parent_task` pointe vers ce ticket. En cas de drift, `pm-task-sync` sur l'enfant
  rétablit la cohérence.

