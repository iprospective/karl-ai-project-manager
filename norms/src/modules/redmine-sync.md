> 📂 **Module `redmine-sync` — quand lire ceci :** tu introduis ou fais évoluer une **donnée / vue / artefact partagé** entre Redmine et le PM (nouveau champ, nouvelle vue, template d'issue, doc, métrique…) · tu te demandes « où est la source de vérité et comment les deux côtés restent-ils alignés ? ».
> **Outils :** scripts de sync dédiés (`pm-task-status-update`, `pm-task-description-update`, `redmine-template-sync`, `pm-wiki-sync`, `pm-task-metrics-push`…) · **Préchargé par :** —.

## Principe de parité Redmine ↔ PM

**On cherche en permanence à établir (ou à rapprocher) la synchronisation entre les
données Redmine et les données PM — pour qu'humains et agents IA voient toujours le
même état.** Redmine est la **vitrine humaine**, les fichiers MD sont le **plan de
travail des agents**, mais c'est le **même état** vu sous deux angles, pas deux
référentiels concurrents.

Toute donnée qui existe **des deux côtés** (statut, priorité, titre, description /
CDC, done_ratio, liens entre tâches, métriques temps/tokens…) est tenue synchronisée
**dans le même cycle** que sa modification — jamais mise à jour d'un seul côté en
laissant l'autre dériver.

### Objectif directeur, pas perfection imposée

C'est un **objectif directeur**. La parité parfaite n'est pas toujours atteignable
(API partielle, plugin sans REST, latence de fetch…) ; la règle est alors :
**réduire l'écart, jamais l'agrandir sciemment**. Quand un côté ne peut pas être
synchronisé automatiquement, on le documente et on prévoit le rapprochement, plutôt
que d'acter une divergence silencieuse.

### Conséquence pratique — concevoir la sync *avant* la copie

Chaque fois qu'on introduit une donnée ou un artefact partagé, on conçoit **d'abord**
sa synchronisation :

- privilégier une **source canonique unique** dont les autres représentations sont
  des **miroirs générés**, plutôt que plusieurs copies maintenues à la main ;
- si la cible n'a pas d'API (ex. plugin Redmine), écrire l'outil de sync qui pousse
  la source vers la cible de façon **idempotente** (un trou d'outillage = un script
  à créer, cf. tripwire #1) ;
- marquer toute représentation **générée** comme telle (bandeau « ne pas éditer ici »)
  pour ne pas recréer un drift à deux sources.

### Format du livrable — portable et versionné

Avant de se demander *comment* on synchronise une source canonique, il faut se
demander **dans quoi elle vit**. La réponse est invariante :

**Tout livrable documentaire — audit, CDC, spec, roadmap, rapport — est du markdown
dans le repo git du projet.** C'est la source canonique : diffable, revue en MR,
versionnée, lisible par n'importe qui.

**Interdit : un livrable dont la source vit dans un outil propriétaire à un
fournisseur de LLM** (Artifact, canvas, doc hébergé côté vendor…) ou dans tout format
qu'un autre agent, outil ou humain ne peut pas reprendre. Le système PM est
**fédéré et multi-agents** : un livrable qui n'existe que dans le contexte d'un
fournisseur est un livrable perdu dès qu'on change d'agent — et une source hors git,
donc sans diff, sans revue, sans historique.

> **Critère de décision** — *« un autre LLM, demain, sans mon outillage, peut-il
> lire, éditer et versionner ce livrable ? »* Si la réponse est non, le format est
> mauvais, quelle que soit sa qualité de rendu.

Les représentations hébergées (Wiki Redmine, description projet…) restent ce qu'elles
sont partout ailleurs dans ce module : des **miroirs générés** depuis git (via
`pm-wiki-sync`), jamais la source. Le rendu joli est un miroir ; le markdown est le
livrable.

Corollaire pour les agents disposant d'outils de rendu (Artifacts & co) : ils sont
utilisables comme **vue jetable** (prévisualiser, montrer), jamais comme livrable ni
comme source. Le cycle reste : markdown en repo → commit → miroir généré.

### Ce principe est l'ombrelle de tripwires concrets déjà en vigueur

Il ne remplace pas, il **chapeaute** — le détail vit dans les modules dédiés :

- **Statut** (tripwire #4) : tout changement de `status` se répercute Redmine
  (status_id + note) + frontmatter + `.log.md` dans le même cycle. → `status-workflow`.
- **Description vivante** (tripwire #9) : la description Redmine est l'état courant,
  tenue à jour (checklist, done_ratio) ; les notes sont l'historique. → `redmine-hygiene`.
- **Traçabilité** (tripwire #12) : note Redmine + entrée `.log.md` à chaque étape
  significative. → `traceability`.
- **Liens** entre tâches : miroir maintenu des deux côtés. → `task-links`.
- **Métriques** temps/tokens poussées vers les CF Redmine. → `roi-pricing`.
- **Docs / Wiki** : aspects et overviews poussés en Wiki / description projet depuis
  git (source canonique, wiki = miroir). → `pm-wiki-sync`.

### Exemples de référence

- **`redmine-template-sync.py`** — les templates d'issue (plugin
  `redmine_issue_templates`, sans API REST) sont des **miroirs** d'un fichier source
  unique (`templates/redmine/issue-body.md`), poussés via rails runner idempotent.
  On édite la source, on relance, les N templates sont alignés (RM2016).
- **`pm-wiki-sync`** — sens unique git → Wiki, bandeau « généré » sur chaque page.
