# Changelog système

Évolutions du système de gestion de tâches dans son ensemble.
Pour les évolutions du schéma des tâches, voir [norms/CHANGELOG.md](norms/CHANGELOG.md).

Format : [Keep a Changelog](https://keepachangelog.com/fr/)

> Ce fichier consigne les **jalons système** (architecture, outillage, surface
> d'usage). Le détail vit dans les tickets `pm-ai-agents` ; les évolutions des
> normes dans `norms/CHANGELOG.md` (versionnées indépendamment, cf. `norms/VERSION`).

---

## [Unreleased] — Cockpit & environnements de test

### Outillage PM
- **Un env de dev ou de test PrestaShop ne se prend plus pour la production** (RM2932). Le
  back-office des envs de recette affichait en permanence « Action requise : confirmez l'URL de
  votre boutique ». Le réflexe — aligner `ps_shop_url` — ne pouvait pas marcher : le bandeau vient
  de **ps_accounts**, qui compare l'URL enregistrée **chez PrestaShop Cloud** à celle de l'env,
  et un clone hérite de l'identité de la boutique d'origine. L'écart est donc structurel, et le
  bouton « confirmer » du bandeau est un piège : cliqué depuis un env de test, il **réassocie
  l'identité cloud de la production au domaine de test**. En creusant, le bandeau s'est révélé le
  symptôme visible d'un problème plus large — un clone porte aussi les **jetons marchands** de la
  prod (compte PayPal `PS_CHECKOUT_PAYPAL_*`, identités Firebase, clés RSA de ps_accounts) : 41
  clés d'identité mesurées sur la seule base de dev pisceen, et quatre modules cloud actifs. La
  réponse est un script unique, `tools/env-runtime/presta-nonprod-sql.sh`, qui **émet du SQL sur
  stdout sans jamais ouvrir de connexion** — c'est ce qui lui permet de servir les trois contextes
  d'un même geste : le framework de synchro prod→local (`presta_adapt_db`), le clone par ticket de
  `pm-env-session` (détection PrestaShop par `config/defines.inc.php`, appliqué **avant** le
  `post_sql` du manifeste pour que celui-ci garde le dernier mot), et un env de recette distant
  (`… | ssh <hôte> "mysql <db>"`). Il aligne le domaine, purge les identités cloud et désactive
  les modules qui dialoguent avec ces services. Garde : il refuse de fabriquer son SQL pour un
  domaine qui ne ressemble pas à du dev/test — le geste délie une boutique, joué sur une prod il
  la casse.
- **Créer un workspace ne demande plus de `sudo` interactif** (RM2909). Le modèle de perms
  multi-user verrouille la racine d'un workspace en `2750 pm:pm` — invariant voulu — mais
  personne n'avait outillé son corollaire : plus aucun dev ne peut y créer `repos/`,
  `envs/`, `.mmi-pm/` ni les partagés du layout. `pm-project-new` et `pm-env-init`
  échouaient donc en `Permission denied` au milieu de l'instanciation, et l'usage s'était
  fixé sur deux `sudo` humains encadrant chaque création de projet — précisément le runbook
  jetable que `pm-perms` devait remplacer (constaté trois fois sur la seule création de
  `iprospective/communication`). Le helper privilégié gagne deux verbes NOPASSWD,
  `ws-init` et `ws-perms`, appelés automatiquement par les deux scripts quand — et
  seulement quand — la racine verrouillée l'exige ; no-op silencieux sur les workspaces
  historiques, aucune migration subie. Le modèle n'est pas dupliqué dans le shell
  privilégié : dossiers et modes viennent de `pm-perms` (`--list-dirs` / `--apply`), le
  `.gitignore` de whitelist de `pm-env-init --print-gitignore`. Ligne de partage posée en
  norme : **structure = privilège, contenu = groupe**.
- **`pm-task-doc` : adosser une doc partagée à un ticket, sans geste manuel** (RM1890, sous-tâche
  de RM1856). La convention « un aspect par SUJET, jamais par ticket » (RM1856) était écrite depuis
  juin et **jamais outillée** — résultat mesuré au moment de la livraison : sur 24 aspects du projet
  `pm-ai-agents`, **12 n'avaient aucun frontmatter** et **9 portaient un RM-id dans leur slug**, alors
  que ce slug **devient l'URL de la page wiki** et qu'un rename la casse. L'outil crée l'aspect depuis
  le template partagé (RM1891) ou l'y rattache, maintient `related_tickets[]`, insère la référence
  « Doc partagée » dans la description du ticket (via l'outil canonique, pas à la main), et publie au
  wiki à la demande — le tout **idempotent**. Il **refuse** un slug portant un RM-id, et `--check`
  audite la conformité de tous les aspects d'un projet. L'édition de `related_tickets[]` est
  **textuelle et non par round-trip YAML** : un round-trip mangerait les commentaires de fin de ligne,
  qui portent la moitié de l'information de la liste (test dédié). La dérivation du titre de page wiki
  quitte `pm-wiki-sync` pour `pm_doc` : `pm-task-doc` doit produire la **même** URL pour poser le lien
  **avant** le premier sync — deux copies, c'est deux URL le jour où la règle bouge.
  ⚠ Reste dû : le **CF link** ticket→page wiki prévu par la convention § 3.3 n'est pas posé, faute de
  champ dédié sur l'instance Redmine (les CF `link` existants sont « GIT PR » et « Environnement de
  test »). L'outil le signale ; créer le champ est une opération d'instance.
- **Feuille de temps : reconstituer les heures HUMAINES depuis les traces d'agents** (RM2890).
  Le constat qui ouvre le chantier est mesurable : les saisies de temps de Mathieu passent de
  118 en février à **9 en août**, et ces 9 portent sur du travail *non* assisté (réunions,
  téléphone). Autrement dit, tout ce qui se fait avec Karl n'était plus facturable faute d'être
  noté. `mmi-pm timesheet --month AAAA-MM` produit un compte rendu lisible et une **proposition
  YAML amendable** ; après relecture, `--apply` crée les saisies Redmine, idempotent (une ligne
  déjà posée porte sa marque et n'est jamais recréée). **Aucun modèle n'est appelé : 0 token**,
  32 s pour rejouer un mois — le rejeu mensuel ne coûte que la relecture.
  Les traces viennent de **sources déclarées**, locales ou distantes : transcripts Claude Code
  (partagés hôte/conteneur par bind mount — `history.jsonl`, lui, ne l'est pas, et il manquait
  **213 prompts en août**, soit 19,8 h), `history.jsonl` comme complément durable, bases
  **opencode**, journaux `.log.md` des tickets. Un gisement non déclaré reste invisible : c'est
  assumé, pas deviné. Le **filtre du bruit système** est structurel — sur les messages de rôle
  `user` absents de l'historique, seuls **26 % sont humains** (le reste : skills injectées,
  reprises de session, relances automatiques) ; sans lui le mois serait surévalué du double.
  L'attribution au ticket **rejoue la cascade de `pm-task-tick`** plutôt que d'en réinventer une
  (94,2 % des tours d'août attribués), complétée par les `.log.md` quand un transcript a été
  purgé, et un ticket est toujours rattaché **à son propre projet** — un ticket appartient à un
  seul projet, il le sait mieux que le répertoire courant.
  Le temps se calcule par **union d'intervalles** `[t − rédaction ; t + suivi]` : le
  chevauchement devient impossible **par construction** (134,9 h d'intervalles bruts en août pour
  167,5 h mesurées — 80 % de recouvrement éliminé), et le plafond de suivi borne ce qui est
  compté quand l'agent travaille seul. Le temps **transversal** (PM, infra, écosystèmes produit)
  a trois destins selon la journée — refacturé aux clients du jour au prorata (semaine, heures
  ouvrées, journée cliente), laissé interne le soir et le week-end, ou **proposé non compté** les
  journées passées surtout sur du perso. Les **absences** déclarées écartent tout, mais
  **remontent en évidence** les journées à activité cliente : « je n'étais pas là » et « rien n'a
  été fait » ne sont pas la même chose. Deux invariants sont sous test — non-double-comptage (la
  somme des lignes égale la mesure de l'union) et conservation (refacturation, clés multi-clients
  et arrondi déplacent du temps sans en créer ni en perdre).
  Le nom : `worklog` étant **déjà pris** par le suivi de session (cockpit, `pm-session-status`),
  l'outil s'appelle `timesheet` — deux objets sans rapport sous un seul mot, c'est la définition
  d'un piège. Configuration : `timesheet.example.yml` à copier en `timesheet.yml`.

- **Cockpit : changer le statut d'un ticket depuis la fiche et depuis le worklog** (RM2888).
  Le geste existait mais restait cantonné : trois verdicts figés dans la console de test, une
  réouverture sur les tickets fermés — partout ailleurs il fallait sortir du cockpit pour une
  transition banale. Ce qui manquait n'était pas l'exécution (`/pm/run` expose `task-status`
  depuis RM2209) mais de savoir **ce qui est possible ici** : le catalogue déclare les 14 statuts
  en dur, quel que soit l'état du ticket. `pm-task-status-update --list-next` gagne donc une
  sortie **`--json`**, et le cockpit une route **`GET /ticket-transitions/<rm>`** qui l'interroge :
  la règle de transition reste dans les NORMS, elle n'est **pas recopiée** côté UI — deux tables
  divergeraient au premier statut ajouté. La pastille de statut ouvre le menu, sur la fiche comme
  sur chaque ligne du worklog. Une transition que **ce compte** ne peut pas poser reste visible
  mais désactivée, avec sa raison : la masquer laisserait croire qu'elle n'existe pas. Redmine
  injoignable ⇒ liste complète et avertissement, jamais un geste inatteignable. Les gardes NORMS
  (checklist non cochée, merge gate RM2319) sont franchissables **explicitement**, jamais d'office
  — c'est l'incident RM2302 qui l'impose — et leur mécanique, jusqu'ici propre à la console de
  test, est désormais partagée.
- **Cockpit : filtre par statut dans « Tickets ouverts »** (RM2883). La carte empile jusqu'à
  40 tickets consultés, tous statuts mêlés. Elle offre maintenant, à côté du filtre par client et
  cumulable avec lui, un filtre par **famille de statut** : à faire / en cours / à tester / à MEP
  / en pause / fermé. Seules les familles **présentes** ont un bouton, et l'en-tête passe à
  `(vu / total)` dès qu'un filtre est actif. « à MEP » est distingué de « à faire » par cohérence
  avec le worklog (RM2860). Un test vérifie que **tous** les statuts NORMS ont une famille : sans
  lui, un statut ajouté un jour disparaîtrait silencieusement du filtre.
- **Fiche ticket : la consigne de lancement se choisit et s'édite** (RM2873). Le bouton
  « ▶ nouvelle session » lançait avec une consigne **imposée** (`traite la tâche RM…`), visible
  seulement dans la boîte de confirmation : vouloir « étudie et chiffre » obligeait à repasser
  par le formulaire de gauche. La fiche offre maintenant le même sélecteur de modèle et le même
  champ éditable — et par **réutilisation**, pas par copie : `taskPromptText` rendait déjà la
  formulation commune (RM2726), la **liste des modèles** (jusqu'ici en dur dans le HTML de
  gauche) et la **règle de remplissage** (« libre » intouché, calcul impossible → on ne vide pas)
  le deviennent. La consigne vaut aussi pour « ➜ envoyer dans cette session » : un champ affiché
  au-dessus d'un bouton qui l'ignorerait serait un piège. L'état vit hors du DOM — la fiche est
  re-rendue sur événement et une saisie en cours y serait perdue — et changer de ticket repart
  d'une consigne propre.
- **`pm-task-add … --porcelain | head -1` pouvait laisser un ticket orphelin** (RM2870).
  Le tube se ferme dès la première ligne lue, l'écriture suivante lève `BrokenPipeError`, et le
  processus mourait **après** le POST Redmine : ticket créé côté forge, aucune fiche PM, rien
  pour le signaler — c'est ainsi qu'est né RM2868. `pm_output` avale désormais l'écriture sur un
  flux mort et bascule sur `os.devnull` : l'affichage n'est jamais une raison d'interrompre une
  mutation déjà engagée. Le correctif est dans la couche de sortie, donc vaut pour **tous** les
  scripts `pm-*`. Le second volet du ticket — `same_project()` et le `project_id` textuel — a
  été traité en amont par RM2784 ; la version de `dev` est conservée telle quelle.
- **Déplacer une tâche d'un projet PM à un autre : `mmi-pm task-move`** (RM2866). Un ticket
  ouvert depuis le mauvais cwd — ou déplacé dans l'UI Redmine par un humain — laissait sa
  fiche PM orpheline dans le projet d'origine, sans outil pour la suivre : `cp` + `git rm` à
  la main, soit exactement ce que le tripwire #1 interdit (« pas d'outil = trou à combler »).
  Incident fondateur : RM2865, créé dans `pm-ai-agents` puis déplacé vers `calicote/dolibarr`
  deux minutes plus tard. `pm-task-move <id> --to <client>/<projet>` déplace la fiche, son
  `.log.md` et son `.reporting.yml`, et aligne le `project_id` Redmine. Trois pièges traités :
  (a) la cible se résout par `resolve_project_ref(require_redmine=True)` — un slug nu ambigu
  est refusé (tripwire #14) ; (b) le PUT Redmine est **vérifié par relecture**, parce que sans
  la permission « Move issues » Redmine répond 204 en droppant l'attribut — l'échec serait
  muet et laisserait la divergence que l'outil est censé supprimer ; (c) source et cible ne
  vivent pas forcément dans le **même dépôt de données** (un workspace par projet), d'où deux
  commits path-scopés au lieu d'un rename — ce qui a demandé d'apprendre à `pm_git.autocommit`
  à committer une **suppression** (`allow_missing`, opt-in : hors ce cas un chemin manquant
  reste une erreur d'appelant). Le cas « Redmine déjà à jour » ne fait aucune écriture
  distante, et une tâche portant une branche de code est refusée : une branche ne se déplace
  pas de dépôt.
- **Cockpit : un fichier ouvert s'affiche en pleine hauteur** (RM2861). Dans l'onglet 📁 fichiers,
  un `.md` atterrissait dans un bloc de **160 px** avec son propre ascenseur, au milieu d'un
  panneau qui défile déjà : le contenu était rendu dans `.desc`, le style du bloc « description
  encadrée ». Il prend désormais les classes pleine hauteur `.facetfull .descfull .mdview`
  introduites par RM2797/RM2806 pour le même défaut sur la fiche de ticket — avec le piège que
  RM2806 avait documenté : `.desc` est déclarée plus loin dans la feuille, la garder aurait rendu
  le correctif inerte. Cause de fond traitée : le corps d'un fichier se rendait en **trois
  exemplaires** (panneau droit RM2586, vue projet RM2590, vue centrale RM2759) — d'où le fait que
  seule la vue centrale était déjà correcte. Un `fileBodyHtml` unique et testé les sert tous.
- **Worklog : la MEP a son onglet** (RM2860). Les tickets `a_mep` et `en_mep` étaient comptés
  dans « reste à faire », où ils se noyaient entre des tickets encore à écrire. C'est pourtant
  un travail d'une autre nature : le développement est fini, ce qui reste est une mise en
  production — batchée (plusieurs tickets montent ensemble), souvent portée par un autre acteur.
  Ils ont désormais leur bucket `mep` et un sous-onglet **🚀 à mettre en prod**, entre « reste à
  faire » et « fait ». La même section apparaît dans le worklog Markdown de session
  (`pm-session-status`) : les deux vues du même worklog ne doivent pas donner deux vérités sur
  « où on en est », et un test vérifie que les deux tables de statuts ne divergent pas. Piège
  traité au passage : `ticketsOfSession` énumère les buckets par une liste en dur — un bucket
  neuf oublié là aurait fait disparaître ces tickets de l'onglet « tickets » de la session.
- **Synchro des tags : additive dans les deux sens, suppression seulement quand elle est
  attestée** (RM2840). Deux pertes silencieuses corrigées. À la **relecture**, `pm-task-sync`
  remplaçait la liste locale par celle du CF : un ticket portant `cockpit` (mot-clé local, sans
  équivalent possible) et `front` perdait `cockpit` à chaque refresh. À l'**écriture**,
  `pm-task-tag` poussait la liste locale telle quelle : une valeur ajoutée depuis l'UI Redmine
  et pas encore connue ici était écrasée. Désormais : ajout bidirectionnel ; suppression
  PM→Redmine ; suppression Redmine→PM **uniquement** pour ce que les **journaux** attestent
  comme retiré depuis la dernière synchro (un CF multi-valeurs émet une entrée par valeur). Sans
  repère de journal exploitable, la relecture est additive et le dit — mieux vaut un tag de trop
  qu'un tag effacé sans qu'on sache par qui. Vérifié en réel sur un ticket de bout en bout.
- **`pm-task-add` : KeyError après le POST quand `--tags` remplit `extra_cf`** (RM2842,
  régression de RM2829). La ligne qui logue le CF « Task type » lisait
  `tt_values[args.type]` sous la seule condition `if extra_cf:` — vrai depuis que le CF « Tags »
  s'y ajoute aussi. Résultat : toute création avec `--tags` et un type absent de la table
  task-type (soit tout sauf documentation / database / configuration) levait une exception
  **après** le POST, laissant un ticket côté Redmine **sans fichier local** (incident RM2840,
  rattrapé par `redmine-fetch-task`). Chaque CF se logue désormais sous sa propre garde, et un
  test statique vérifie qu'aucune lecture de `tt_values` ne précède la sienne.
- **Tags : 2e lot et spécialisations** (RM2839). Le CF passe à **30 valeurs**. Quatre familles
  nouvelles cartographiées — Design (charte, branding, maquettes, 3d, rendu…), Inventaire
  (inventory, cartographie, parc), Data (curation, fragments, contenu, catalogue…) et
  « Bench/Perf » (performance, scaling, benchmark, résilience) — avec les déplacements que ça
  implique : `charte`/`branding` quittent Front pour Design, `parc` quitte Infra pour
  Inventaire, `benchmark` quitte Tests pour Perf, `pricing-watch` quitte Tunnel de commande
  pour Veille. Et surtout, **Review, Veille, Hooks et CLI deviennent des valeurs** là où
  c'étaient des alias d'Audit et de Tooling : le registre porte désormais la relation
  `precise:`, montrée par l'audit. Le point qui compte : les garder en alias les aurait
  rabattus sur leur parent à l'écriture — la précision aurait été perdue au moment même où on
  la demande. Le champ étant multi-valeurs, un ticket porte `audit` ET `review`. Couverture :
  56 % des usages.
- **Registre des Tags remappé sur les 22 valeurs réelles** (RM2837). Les valeurs ont été créées
  avec des libellés parfois différents de ceux proposés — « Tooling » pour Outillage, « Archi »
  pour Architecture, « Backup » pour Sauvegarde, « Debug/Bugfix » pour Debug — plus deux
  familles non prévues, **Notifications** et **Audit**. Le registre porte désormais l'id et le
  libellé exact de chacune, et le synonyme proposé devient un alias : rien n'est perdu et aucun
  ticket n'a à être réécrit. Le slug reste distinct du libellé quand celui-ci est composé
  (« Debug/Bugfix » s'écrit `debug`) — un slug se tape à la main. Deux familles nouvelles
  cartographiées (telegram, communication, bot → Notifications ; analyse, revue, inventaire →
  Audit) et le paiement rejoint « Tunnel de commande » sans créer de valeur (`etransactions`,
  `mmipayments`, `panier`…). **Correctif d'audit** : la comparaison se fait par **id** et non
  par libellé — sinon un slug volontairement différent du libellé passait pour un écart — et
  les **renommages** côté Redmine sont désormais détectés. Couverture : 53 % des usages.
- **Registre des Tags : vocabulaire multi-projet, mapping n-1, audit et garde** (RM2836,
  chantier RM2828). Le CF portait 7 valeurs quand les frontmatters comptaient **747 mots-clés
  sur 2 578 usages** : deux objets différents qu'il fallait réconcilier sans réécrire
  l'historique. Le registre porte désormais le vocabulaire contrôlé (7 valeurs actives + **13
  proposées**, choisies sur un critère mesurable — fréquentes ET multi-projets, hors produits
  mono-projet) et **265 alias** qui y ramènent les mots-clés existants ; le reste demeure
  mot-clé local, filtrable comme avant. `pm-task-tag` canonicalise un alias en l'annonçant,
  **refuse** une étiquette hors vocabulaire (avec les valeurs acceptées et l'échappatoire
  `--free`), et distingue « décidée mais pas encore créée dans Redmine » de « mot-clé local » —
  deux raisons très différentes de ne pas monter. `pm-tags-audit` compare définition Redmine,
  registre et usages, et rend les quatre écarts : à créer dans l'UI, à recopier au registre,
  orphelines, libres. Il ne corrige rien : créer une valeur reste un geste humain.
- **Socle étiquettes branché sur le CF réel** (RM2829). Le champ a été créé côté Redmine sous
  le nom **« Tags » (id 32)** et en format **`enumeration`** — pas « liste » : l'API y désigne
  ses valeurs par **id** (45, 46…), et pousser un libellé est refusé. Le socle apprend donc à
  traduire : `tags.registry.yml` (racine du dépôt, comme `redmine.reference.yml`) porte la table
  `slug ↔ label ↔ id`, et le registre voyage avec le code plutôt qu'avec l'instance — sinon un
  worktree de dev pousserait les ids d'un autre checkout. Une étiquette hors registre reste
  locale et `pm-task-tag` le DIT : sans ça, un « ✓ frontmatter + Redmine » mentirait sur la
  moitié des étiquettes. Vérifié de bout en bout sur RM2829 (frontmatter `front` → CF valeur 45).
- **L'étiquette propose un rôle d'agent** (RM2833, chantier RM2828). Table `tag_roles` déclarée
  en conf (`meta.yml`, cascade client → projet — un vocabulaire métier n'a pas à être connu du
  code) : `pm-task-brief` affiche le rôle suggéré, et l'écran de lancement d'une session le
  montre puis le cite dans la consigne, de quoi faire charger `agents/worker-<rôle>.md`. Ça
  **propose**, ça n'assigne pas : réassigner un ticket changerait son propriétaire — donc le
  verrou d'écriture — sans que personne l'ait demandé. Quand plusieurs étiquettes routent, le
  départage est alphabétique (arbitraire mais stable) et les autres candidates sont nommées ;
  un rôle absent de `agents/` est suggéré mais signalé, plutôt que d'envoyer l'agent lire un
  fichier qui n'existe pas.
- **Étiquettes de ticket — le socle** (RM2829, chantier RM2828). Le domaine d'un ticket
  (`front`, `bo`, `bdd`, `refacto`, `livraison`, `tunnel-de-commande`…) vivait à moitié :
  `tags:` au frontmatter, écrit par `pm-task-add --tags` et filtré par `pm-task-list --tag`,
  mais invisible côté Redmine. Constat vérifié sur l'instance : Redmine n'a pas de tags en
  standard, aucun plugin n'est installé, et les catégories natives sont mono-valeur ET propres
  à chaque projet — « refacto » serait à recréer partout. Le porteur retenu est donc un
  **custom field « liste » multi-valeurs partagé à tous les projets**. Livré : `pm_tags`
  (normalisation en slug — « Tunnel de Commande » et « tunnel_de_commande » sont UNE étiquette
  —, tri stable, plafond, payload et lecture du CF), la commande `pm-task-tag` (add / rm / set
  / lecture, frontmatter + Redmine + journal), le push au POST de `pm-task-add` et la
  relecture par `pm-task-sync`. Le CF lui-même se crée à la main (l'API Redmine ne crée pas de
  custom fields) : marche à suivre dans `knowledge/redmine/etiquettes.md`. Tant qu'il n'existe
  pas, tout fonctionne côté frontmatter et le push est annoncé comme non fait — jamais en
  silence.
### Outillage
- **Lisibilité du texte des tickets** (RM2789), deux défauts au même endroit.
  **Le gabarit « (à compléter) » n'est plus une case à cocher** : posé en case, il bloquait
  la livraison sans que personne puisse le cocher, et le seul recours (`--allow-unchecked`)
  désarmait le garde-fou pour les **vrais** critères aussi — le contournement était plus
  grossier que le problème. Le marqueur reste visible, il n'est plus comptable, et le
  correctif vaut **rétroactivement** pour les tickets qui le portent déjà. `count_unchecked`
  passe par `pm_markdown` : une checklist *citée* dans un bloc de code ne compte plus. Et
  « aucun critère jamais défini » **avertit** au lieu de bloquer — ça ne dit rien de la
  qualité d'une livraison, et bloquer là-dessus n'aurait fait qu'ancrer le réflexe
  `--allow-unchecked`.
  **Les paragraphes arrivent dé-enveloppés dans Redmine** : l'outillage compose du markdown
  enveloppé à ~95 colonnes, or Redmine rend chaque retour à la ligne comme un `<br>`, d'où
  des textes hachés. Le dé-enveloppement se fait au **point de passage unique** vers l'API
  (une douzaine d'appelants : en oublier un aurait laissé le défaut revenir par une porte de
  côté) et préserve blocs de code, listes, tableaux, titres, citations et sauts durs.

### Cockpit
- **Les étiquettes se voient et se comptent** (RM2832, chantier RM2828). Stockées sans être
  montrées, elles ne servaient qu'aux filtres — personne ne savait ce qu'un ticket portait.
  La fiche du ticket les affiche (🏷) et chacune est **cliquable** : elle emmène vers la
  recherche réglée sur cette étiquette, plutôt que d'inventer une vue de plus. Côté outillage,
  `pm-conso-report --by tag` ventile coût, tokens et temps par domaine ; c'est la seule
  dimension multi-valuée, donc un ticket `front` + `refacto` compte dans les deux et la somme
  des lignes dépasse le total — annoncé dans le rapport lui-même, un total qui semble faux
  ferait douter de l'ensemble. La marche à suivre pour la vue Redmine équivalente (une fois le
  CF créé) est dans `knowledge/redmine/etiquettes.md`.
- **⇱ session sur un lot filtré par domaine** (RM2831, chantier RM2828). RM2823 sortait les
  intrus d'une session, un par un ; ici la **liste de triage filtrée par étiquette EST le lot** —
  rien à cocher. Le chemin de lancement est factorisé avec RM2823 (`spawnBatchSession`) : deux
  copies auraient divergé au premier correctif. La consigne reste celle de « ▶ traiter », rendue
  par le serveur, et la session vient de `/spawn`. Les dix premiers tickets partent ; ce qui est
  laissé de côté est annoncé plutôt que tronqué en silence.
- **Filtrer par étiquette : recherche, triage ROI, jeux dérivés** (RM2830, chantier RM2828).
  Une étiquette ne sert à rien si elle ne sert pas à choisir quoi faire. Nouvel endpoint
  `GET /tags` (les étiquettes réellement en usage, avec leur compte — jamais une liste écrite
  en dur, qui dériverait au premier vocabulaire ajouté) ; filtre étiquette dans la recherche de
  tickets, avec les étiquettes affichées sur chaque ligne (filtrer sans les voir, c'est filtrer
  à l'aveugle) ; même filtre dans le triage ROI ; et nouveau critère de **jeu de sessions
  dérivé** — un jeu « étiquette = refacto » se remplit tout seul. Une session ancrée sur un
  slug n'a pas de ticket, donc pas d'étiquette : elle ne matche jamais « au cas où ».
- **« Reprendre une session » : filtre par client** (RM2834). La liste des projets était plate
  — tous clients mêlés, des dizaines d'entrées où retrouver le sien supposait de le connaître
  par cœur. Un sélecteur client s'ajoute au-dessus et filtre les projets ; client seul, sans
  projet, liste toutes ses sessions (`/resumable` filtre déjà client et projet séparément — pas
  de changement serveur). Le contexte client du bandeau pré-sélectionne le client, et changer
  de client abandonne explicitement un projet qui n'est pas le sien : le couple incohérent
  renvoyait une liste vide sans dire pourquoi.
- **⇱ sortir des tickets d'une session vers une session dédiée** (RM2823). Une session est
  ancrée sur un projet, mais le fil ramasse des tickets d'ailleurs : un de temps en temps on
  le traite au vol, et quand ça s'accumule la session porte deux chantiers — contexte pollué,
  worktree du mauvais projet, tickets oubliés à la fermeture. Cocher les intrus dans le
  worklog et « ⇱ nouvelle session » ouvre une session ancrée sur LEUR projet qui les prend en
  charge. La consigne vient du même générateur que « ▶ traiter » (`/worklog/batch` en dry_run)
  et la session de `/spawn` : aucun second chemin. Garde-fous : un seul projet par lot (les
  projets en présence sont nommés en cas de mélange), et un ticket au projet non résolu reste
  sur place sans retenir les autres.
- **Alerte avant d'ouvrir une 2e session sur un ticket déjà pris** (RM2818). Le serveur
  refusait déjà (409) une seconde session ANCRÉE sur l'id ; ce qui passait sans bruit, c'est
  le ticket traité par une session ancrée AILLEURS — branche du registre, worklog —, soit le
  cas courant du ticket ramassé en cours de route. Les deux points de lancement (fiche du
  ticket, lanceur du panneau sessions) montrent désormais ce qui existe — sid, titre, état,
  et à quel titre la session le traite — puis proposent de **rejoindre** avant d'offrir
  d'ouvrir quand même. Une session marquée « terminé » (RM2515) ne déclenche rien : c'est
  exactement ce que la marque sert à dire ; « parké » ou éteinte, si — le travail n'est pas
  fini. L'état est relu avant de trancher, un cache périmé dirait « libre » à tort.
- **Cliquer l'onglet d'une session éteinte la relance** (RM2819). Un onglet épinglé survit à
  la session qu'il montrait ; le clic appelait pourtant `attach()` dans tous les cas — donc un
  terminal vide dès que la session ne tournait plus, sans un mot ni le geste utile. Le clic
  route désormais sur l'état réel : vivante → attach, seulement enregistrée → la relance
  (exactement le chemin de la tuile grise, RM2427/RM2536 — pas un second), disparue → on le dit
  et on propose de fermer l'onglet. Le cache de sessions ne connaissant que le jeu affiché, la
  liste complète est redemandée avant de conclure à une disparition.
- **Déverrouillage de clé SSH : « bad file descriptor » corrigé** (RM2822). Le cockpit passe
  la passphrase à `ssh-add` par un tube anonyme, lu par `karl-askpass.sh` — qui lisait le
  descripteur **3 en dur**. Or `pass_fds` conserve le numéro du tube au lieu de le remapper :
  dans un processus nu `os.pipe()` rend 3 (d'où des tests verts et une fonction réputée
  bonne), mais dans karl-agent, dont les sockets tiennent les descripteurs bas, le tube tombe
  sur 8 ou 11 et l'askpass lisait dans le vide — **aucun chargement de clé ne pouvait
  aboutir**. Le serveur dit désormais quel descripteur lire (`KARL_ASKPASS_FD`, repli sur 3 :
  un numéro de descripteur n'est pas un secret, la passphrase reste dans le tube), et la
  lecture passe par `/dev/fd/<n>` — `<&$fd` ne sait pas dépasser le descripteur 9 (« Bad fd
  number »), justement la zone où atterrit le tube d'un serveur. Le test reproduit maintenant
  le cas réel en occupant les descripteurs bas, au lieu de partir d'un processus vierge.
- **« ⬆ MAJ dispo » passe en bout de rangée** (RM2821). Bouton intermittent posé au milieu
  du header : son apparition décalait tous les boutons suivants, juste au moment où on visait
  autre chose. Dernier de la rangée, il ne pousse plus personne — comportement inchangé par
  ailleurs (masqué par défaut, même infobulle, même clic).
- **« ⚙ commandes pm » et « 🔧 réglages » quittent la colonne de gauche** (RM2816). Ces deux
  surfaces ne sont pas des listes de travail : on y va pour faire un geste — lancer une action
  PM, changer un réglage — puis on en sort. Elles occupaient pourtant deux des huit onglets
  d'une colonne dédiée à ce qui tourne, et leurs formulaires y tenaient dans 300 px de large.
  Elles passent au **menu du haut** (à côté de ❓ aide, 📖 glossaire, 🩺 poste) et leur contenu
  s'ouvre au **centre**, dans le modèle d'onglets RM2672 : temporaire par défaut, épinglable
  quand on enchaîne plusieurs actions, refermable, restauré au rechargement. Rien n'est perdu
  au déplacement (catalogue PM, authentification, utilisateurs, voix, thème, colonne de droite,
  sessions, réglages whitelist) et chaque panneau charge sa donnée serveur à la première
  ouverture, comme avant. Le démarrage « auth requise sans jeton » mène toujours aux réglages.
- **Glossaire de projet + sous-onglet « vocabulaire »** (RM2675). Chaque projet peut porter son
  vocabulaire métier dans `docs/glossaire.md` — tableau `Terme / Définition / Contexte / Alias`,
  écrit par `pm-glossaire.py` (tri, unicité et format garantis). L'étude a montré que la
  plomberie existait déjà aux trois quarts : `docs/` est group-writable (RM2043), symlinké dans
  le workspace de code, wiki-syncé vers Redmine et déjà rendu au cockpit. Le sous-onglet n'ajoute
  donc que ce qui manquait vraiment — **la recherche** (filtre sur terme, définition, contexte et
  alias). Et surtout, le glossaire est désormais **injecté au contexte des workers**
  (`worker-common.md` §5bis), plafonné à 1 500 tokens avec troncature annoncée : sans quoi un
  agent qui croise un terme qu'il ne connaît pas n'ouvre pas le glossaire, il suppose.
- **Bouton « traiter » : à UN seul ticket, il n'y a plus de lot** (RM2762). La consigne
  générée gardait tout le cadre de série — « EN SÉRIE, dans cet ordre », « un ticket à la
  fois », « passe au suivant », « bilan ticket par ticket », notification de fin de lot —
  pour un ticket unique : l'unique consigne utile se noyait sous des règles sans objet.
  Le mot « lot » disparaît entièrement du cas solo (les deux modes, « traiter » et
  « à tester ») ; ce qui est substantiel est conservé à l'identique (protocole NORMS,
  statut de fin, interdiction de forcer, portée restreinte). À 2 tickets ou plus, rien ne
  change. **Second défaut corrigé au passage** : la consigne prescrivait
  `pm-session-status.py notify --kind lot`, or `lot` n'existe pas dans `NOTIFY_KINDS` — la
  commande finale d'un lot **échouait telle qu'écrite**, quel que soit le nombre de
  tickets. Un test vérifie désormais que le `--kind` prescrit est une valeur acceptée.
- **« ⤢ au centre » échouait en « worktree hors du périmètre »** (RM2761) : ouvrir un
  fichier au centre commence par **détacher** la session et fermer la fiche projet — or
  la requête n'était construite qu'après, en relisant un contexte que ce détachement
  venait de vider. Elle partait donc sans portée (`sid=` seul) et le serveur refusait le
  worktree, à juste titre. La portée est désormais **capturée au clic**, transportée
  avec la vue et mémorisée dans la clé d'onglet — donc rejouée à la réactivation et
  après un rechargement de page. Elle garde les **deux** droits quand ils existent
  (session *et* projet, dont le serveur fait l'union) : le `sid` couvre les worktrees
  hors projet, `client/projet` survit à la mort de la session.
- **Déverrouiller le coffre et charger une clé SSH depuis le cockpit** (RM2748) :
  le coffre de secrets se referme tout seul (inactivité, verrouillage nocturne,
  redémarrage) et l'agent SSH démarre vide. Jusqu'ici le cockpit ne savait que
  CONSTATER la panne — il fallait un terminal pour `unlock-vault.sh` ou `ssh-add`,
  et tout ce qui dépend d'un secret restait à l'arrêt en attendant. Un bouton
  **🔓 déverrouiller** apparaît désormais en tête, *uniquement* quand il y a un
  geste à faire, et disparaît une fois l'affaire réglée.
  Le secret saisi ne laisse **aucune trace** : il descend dans `unlock-vault.sh`
  par l'**entrée standard** (nouveau `--stdin`) et dans `ssh-add` par un
  **descripteur hérité** (`deploy/karl-agent/karl-askpass.sh`) — jamais en argument
  de commande, jamais dans l'environnement, jamais dans un fichier ; il n'est ni
  journalisé, ni renvoyé, ni mémorisé côté navigateur. Les routes exigent une
  session authentifiée, et le formulaire refuse de s'afficher hors connexion
  sécurisée : on ne tape pas un mot de passe maître dans une page en clair.

### Outillage
- **Le pont d'onboarding des workspaces cesse d'être un fichier qu'on recopie**
  (RM1892) : un agent lancé dans un workspace de code n'a aucun contexte PM — il le
  reçoit d'un `AGENTS.md` posé à la racine des workspaces (+ symlink `CLAUDE.md`), lu
  par remontée d'arborescence et conditionnel au `.mmi-pm` du projet. Ce fichier vit
  **hors git** (il est propre à l'instance), et jusqu'ici « garder le template et le
  déployé synchrones » n'était qu'un vœu : sur cette machine, le déployé avait dérivé
  du template et avait gagné 48 lignes de contexte local que toute recopie aurait
  effacées. `pm-workspace-bridge.py` contrôle (présent ? symlink ? à jour ?), pose
  (`--install`) et met à jour (`--update`) — en **préservant** le bloc délimité
  `BEGIN/END INSTANCE`, qui porte la part machine. L'`install.sh` de karl-agent le
  pose au provisioning, et 🩺 **poste** signale la dérive.
- **Un ticket `bugfix` naît enfin valide** (RM2752) : `validate-task` exige
  `bug.reproducibility` + `bug.reproduce_steps` pour ce type, or `pm-task-add` ne
  posait pas le bloc et n'offrait aucun flag — **tout** bugfix créé par l'outil
  canonique sortait invalide, et le remède affiché (`pm-doctor RM<id>`) n'accepte
  pas d'argument RM, donc suivre l'indication menait dans le mur. Nouveaux
  `--bug-steps` / `--bug-steps-file` / `--bug-reproducibility` (défaut `always`) ;
  le script **refuse** un bugfix sans étapes plutôt que d'en créer un invalide, et
  le warning renvoie vers `validate-task.py <chemin>`. Le chemin cockpit suit :
  choisir « bugfix » ouvre un bloc « étapes de reproduction » requis, et
  `POST /tickets` répond 400 lisible au lieu d'un 500 sur un ticket qu'on croit
  créé. Le ticket décrivant le défaut l'avait reproduit en se créant.
- **Le doctor NORMS n'avertit plus à vide** (RM2751) : `pm-norms-doctor` signalait à
  **chaque** exécution « outils cités INTROUVABLES : mmi-pm-client, mmi-pm-core ».
  Faux positifs : le motif des skills (`\bmmi-pm-[a-z0-9-]+\b`) capturait les noms
  de symlinks d'ancrage `.mmi-pm-core` / `.mmi-pm-client` — un point est un non-mot,
  donc `\b` les acceptait. Un lookbehind les écarte. L'enjeu n'était pas le bruit
  mais ce qu'il masquait : le jour où les NORMS citeront un outil réellement
  manquant, l'avertissement ne se confondra plus avec le décor. Les deux sens sont
  testés — les ancres ne sont plus vues, un skill réellement cité l'est toujours,
  et un skill absent de `skills/` reste déclaré introuvable.
- **La protection des branches est posée à la création du projet** (RM2057) :
  `pm-protect` existait depuis RM2052 mais s'appliquait **à la main, dépôt par dépôt**
  — donc, en pratique, après les premiers pushes directs. `pm-project-new` l'appelle
  désormais dès que le dépôt `-core` est publié (sa branche de prod existe), et sur les
  dépôts de code du workspace qui portent déjà un remote de forge. Chaque dépôt reçoit
  la politique de sa nature : `pm-protect` distingue core et code, on ne la force pas.
  L'étape n'est **jamais bloquante** — un échec de droits ou de token s'annonce avec sa
  commande de rattrapage, et le projet reste créé. Ce que ça ferme : un dépôt neuf
  n'hérite que du défaut GitLab (`main` en push *Maintainer*), qui ressemble à une
  protection conforme sans en être une (RM2568).
- **Le doctor NORMS repasse au vert, et un test l'y maintient** (RM2750) :
  `pm-norms-doctor` était en **échec permanent sur `dev`** depuis le jalon v2.0.0
  (RM2438) — deux lignes de l'oracle réécrites sans entrée au registre. Les deux
  sont bien des **réécritures assumées**, pas des pertes : le jalon multi-utilisateur
  a requalifié la « propriété **exclusive** » du fichier MD en propriété de 1ᵉʳ niveau
  (l'exclusion réelle vient de `flock`, pas de l'assignation Redmine), et repositionné
  l'optimistic locking comme filet **inter-machine**. Les deux motifs sont désormais
  au `dedup-ledger.yml`. Surtout : **rien ne lançait le doctor**, d'où trois semaines
  de rouge inaperçu — `scripts/test_norms_doctor.py` l'exécute maintenant dans la
  suite, et son message d'échec dit quoi réparer pour chaque contrôle.
- **`pm-env-session teardown` se bloquait sur son propre canari** (RM2679) : la garde
  « worktree sale » exemptait bien les artefacts posés par `create` (`.user.ini`,
  `pm-env.txt`), mais en **comparant des chaînes concaténées**. Avec `docroot: "."` —
  tout projet servi depuis la racine du checkout, dont `pisceen/presta` — elle
  produisait `?? ./pm-env.txt` là où `git status` écrit `?? pm-env.txt` : l'exemption
  ne matchait **jamais**. Comme l'échec du teardown est annoncé « non bloquant », il
  passait inaperçu et les worktrees (228 Mo pièce) s'accumulaient avec leur vhost.
  La comparaison porte désormais sur des **chemins normalisés** et gère les chemins
  quotés et les renommages.
- **`runtime.teardown_ignore`** (RM2679) : le projet peut déclarer les chemins **non
  suivis** que son appli écrit au runtime (ex. `yaml/*.php`, le cache de config de
  PrestaShop) — motifs fnmatch relatifs au worktree. Choix assumé de ne PAS passer la
  garde en `--porcelain -uno` : un fichier neuf qu'on a oublié d'ajouter doit continuer
  à bloquer le teardown. Un fichier **suivi et modifié** n'est jamais rendu jetable,
  même s'il correspond à un motif.
- **`pm-repo-new`** (RM2640) : le PM outillait la vie d'un dépôt mais pas sa **naissance** —
  créer un projet se faisait à l'UI ou au `curl`, exactement le cas visé par le tripwire #1.
  La commande enchaîne désormais résolution du groupe **par chemin exact** (tripwire #14,
  jamais par basename : incidents RM2219/RM2410), refus si le projet existe, `POST /projects`
  (**privé par défaut**, `default_branch` explicite), `--push-from` d'un dépôt local avec
  remote en **alias SSH canonique `gitlab:`** (jamais HTTPS, RM2328), puis `pm-protect`
  **appelé** et non réimplémenté. `--porcelain` sort `<id> <path_with_namespace>` : aucun id
  n'est deviné ni recopié de mémoire (tripwire #13). `--dry-run` montre la séquence complète.
  Passe par `pm_forge` — GitLab n'est pas codé en dur.

### Cockpit
- **« ⬆ MAJ dispo » se voit enfin** (RM2721) : le bouton signalant une mise à jour
  du core (RM2571) portait le style `.mini` de ses six voisins du header — il
  apparaissait sans que rien ne bouge à l'œil, et une MAJ pouvait rester des jours
  non appliquée. Il passe en **orange (`--warn`) avec une pulsation du fond**. Deux
  niveaux volontairement cumulés : la couleur le distingue en permanence (capture
  d'écran, `prefers-reduced-motion: reduce`), l'animation attire le regard à son
  apparition. Pas de `kblink` (l'idiome « attention » des pastilles) : fondre à
  `opacity .25` un bouton **porteur de texte**, affiché tant que la MAJ n'est pas
  faite, le rendrait illisible la moitié du temps.
- **Onglets épinglés du panneau central** (RM2672) : une vue ouverte (session, fiche de
  ticket, fiche projet, création) devient un onglet. **Un seul onglet non épinglé à la
  fois** — la vue suivante le remplace ; épingler le conserve. Les épinglés survivent au
  rechargement (une session n'est jamais rattachée d'office au boot). Le rail gauche
  reste la liste de référence : l'onglet est un marque-page, pas l'annuaire de sessions
  retiré en RM2140/2283. Nouvelle vue **＋ créer un ticket** en pleine page, avec les
  champs que la carte repliée ne portait pas (passe agent-testeur, env cible, estimation,
  difficulté) — validés côté serveur.
- **Panneau « 📧 emails »** (RM2671, chantier RM2666) : la file de triage devient
  cliquable — relever, router, rédiger, **créer à la validation**, rattacher à un fil
  existant, reclasser (la correction est apprise) ou écarter avec un motif. Le corps
  d'un email n'est chargé qu'au dépliage, jamais dans la liste. Le panneau ne
  réimplémente rien : il lit `/mail/queue` et délègue chaque geste au script du
  pipeline (argv strict, allowlist). `--mark-seen` n'est **pas** exposé : marquer lu
  agit sur une boîte de production, ça reste un geste CLI. Aide dédiée : page
  « Emails ».
- **Correctif — lancer une session non-claude** (RM2691) : `POST /spawn` avec
  `engine` = `shell`, `opencode` ou `vibe` répondait **500** (`UnboundLocalError`
  sur `joined`, affecté seulement dans la branche claude) alors que la session
  tmux était bien créée — l'appelant relançait et se prenait un 409 « session
  déjà active ». La réponse dit maintenant explicitement que le jeu de sessions
  n'a pas été rejoint (`reason: "sans-session-id"`) : sans set-at-launch, une
  entrée de jeu serait hollow (ni engine, ni session_id, ni cwd), donc non
  relançable, tout en consommant un slot du plafond.
- **Plafond mémoire des sessions** (RM2690) : chaque session tmux naît avec un
  plafond sur sa **scope systemd** (`MemoryHigh=6G` / `MemoryMax=8G` par défaut) —
  une session qui fuit se fait tuer **seule** au lieu de saturer la workstation et
  de laisser le kernel choisir la victime (incident OOM du 2026-08-13 : 15,7 Go de
  RSS, victime arbitraire). L'UUID de scope étant aléatoire, aucun drop-in
  déclaratif n'est possible : l'accroche est le spawn (couvre `/spawn` **et**
  `/resume`), jamais bloquante (systemd absent, délégation `memory` manquante ou
  `set-property` en échec → warning, session créée). **Réglable depuis le cockpit**
  (🔧 réglages, rubrique « Sessions », en GiB, `0` = illimité) via
  `sessions.memory_{high,max,swap}_gib` de `pm.config.yml` ; `KARL_AGENT_MEM_HIGH`
  / `_MAX` / `_SWAP` (`.env`, syntaxe systemd) **figent** la valeur — le champ est
  alors marqué 🔒 et l'écriture refusée. Ne s'applique qu'aux sessions créées
  ensuite. Le **swap est plafonné à 0** par défaut (`MemorySwapMax`) : sans lui,
  une session qui fuit grimpe lentement de `MemoryHigh` à `MemoryMax` en saturant
  le swap — et c'est le swap saturé qui fait ramer le poste. Convention inversée
  sur ce champ : `0` = aucun swap, `-1` = illimité.
- **Aide intégrée** (RM2593) : menu **❓ aide** + boutons `?` contextuels par
  panneau, ouvrant des pages de doc utilisateur markdown versionnées
  (`deploy/karl-agent/cockpit/help/`) servies par karl-agent (`/help`,
  `/help/<topic>`) et rendues dans le cockpit. Maintenues au fil des devs.
- **Instances cockpit de test relançables en un clic** (RM2588) : la file « à
  tester » sonde l'instance HTTPS (`/health`), affiche son état ●/⚠ + lien
  `https`, et expose « 🚀 (re)lancer » quand elle est down (survit aux reboots).

### Environnements de test
- **Exposition HTTPS des instances cockpit de test** (RM2565) : vhost karl
  factorisé (source unique `karl-vhost-render.sh`, non-régression `karl.conf`),
  réutilisé par `pm-cockpit-test-env` via `pm-env-helper vhost-karl-add` —
  terminal (wss) et micro (getUserMedia) fonctionnels en contexte sécurisé.

### Providers
- **Raccordement réel du premier partenaire : MatNat** (RM2657, L4 du chantier RM2626) :
  `matnat/infra` déclare `tasks.materiaux-naturels.fr` en provider **secondaire**
  (`policy: optional`, pull actif, `push.on: []` — aucune écriture chez eux). Premier
  rattachement en production : RM2618 ↔ leur #5576. Trois obstacles levés au passage,
  tous invisibles avant de brancher une vraie instance tierce :
  * **auth HTTP Basic** devant leur Redmine (Apache, realm « Pas touche minouche ») : la
    clé API seule prenait un 401 du serveur web, avant d'atteindre l'application.
    `redmine_creds(instance)` rend désormais un `Creds` — toujours un tuple `(url, key)`
    pour les appelants — qui transporte l'auth Basic
    (`REDMINE__<INST>__HTTP_USER` / `__HTTP_PASSWORD`) ; `http_json` pose l'en-tête
    `Authorization` en plus de la clé API, les deux se cumulent.
  * **le champ de référence existait déjà** : CF **9 « Réf ticket outil externe »**
    (`string`, **16 caractères**) — donc pas d'URL possible. On y pousse une référence
    compacte `matnat#5576` ; l'URL complète reste dans `refs[]`.
  * **Redmine accepte un CF non activé et l'ignore en silence** (HTTP 200 sans effet) :
    `push_cf` relisait donc un succès mensonger. Il vérifie maintenant que la valeur a
    pris et, sinon, dit quoi faire (« CF non activé pour le projet — le cocher dans
    l'admin »). Nouvelle sous-commande `pm-task-partner sync-cf [--all]` pour rattraper
    les liens posés avant l'activation du champ.
- **Rendre compte chez le partenaire** (RM2656, N2 du chantier RM2626) :
  `pm-task-partner push <RM>` poste une **note de suivi** chez les partenaires du ticket,
  et une **transition de statut** la déclenche automatiquement — mais **seulement** si le
  secondaire déclare ce statut dans `sync.push.on`. **Défaut : rien ne part chez
  personne** ; l'activation est un geste explicite par projet, après revue du gabarit,
  parce qu'une note poussée chez un tiers ne se rattrape pas. Écriture **pauvre** : une
  note de texte, jamais un statut, un CF ni une saisie de temps (les ids de
  `redmine.reference.yml` ne valent que chez nous). **Gabarit fermé** : identifiant de
  suivi, titre, état **en clair** (`a_tester_demandeur` → « livré, en attente de
  validation » — le partenaire ne connaît pas notre machine d'états), plus un message
  rédigé à la main ; ni chemin, ni hôte, ni branche, ni URL interne (notre Redmine ne lui
  est pas accessible). Le hook est **best-effort** : il n'échoue jamais une transition
  déjà écrite, et reste muet sur les projets sans partenaire (~80 ms). Enfin,
  `link --create-remote` crée le ticket manquant chez eux puis le rattache, en exigeant
  un `create.tracker_id` déclaré — les ids de tracker ne sont pas portables.
- **Lire ce qui se dit chez le partenaire** (RM2655, N1 du chantier RM2626) :
  `pm-task-partner pull <RM>` — ou `--all`, câblable en cron (exemple fourni, 30 min) —
  importe dans le `.log.md` les **notes nouvelles** du ticket rattaché (citées, sous un
  en-tête qui nomme l'instance : on distingue d'un coup d'œil ce qui vient d'ailleurs)
  et le **statut brut** de leur côté. Réglable par secondaire
  (`sync.pull: {notes, status}`). Le pointeur `last_seen_journal_id` vit **dans le
  lien** — pas dans `redmine_last_journal_id`, qui suit l'instance primaire : deux
  boucles, deux pointeurs, sinon elles se marchent dessus. Lecture seule et sans effet
  de bord : **rien** n'est répercuté sur le statut, la priorité ou l'assignation ; un
  partenaire injoignable produit un avertissement et le balayage continue. `--all` ne
  scanne que les tickets **ouverts** portant un lien.
- **Rattacher un ticket à un gestionnaire partenaire** (RM2654, N0 du chantier RM2626,
  NORMS v1.69.0) : `pm-task-partner link|unlink|show` pose un lien `refs[]` typé
  `partner_issue` entre un ticket PM et un ticket du **provider secondaire** d'un projet
  (`role: mirror|upstream|related`, un seul miroir par tâche). L'outil refuse une
  instance qui n'est pas un secondaire déclaré, un doublon ou un second miroir ; il pose
  le CF Redmine « Ticket partenaire » quand `REDMINE_CF_PARTNER_ISSUE_ID` est configuré
  (sinon il saute proprement — la définition d'un CF se crée par l'UI admin), journalise,
  et poste chez le partenaire une **note de rattachement à gabarit fermé** (identité,
  titre, URL — jamais de chemin, d'hôte, de branche ni de secret). Les effets distants
  sont **best-effort** : un partenaire injoignable n'empêche pas de poser le lien. Avec
  `link.policy: required`, `pm-doctor` signale chaque ticket **ouvert** non rattaché.
  Aucune synchro de contenu à ce stade (pull = RM2655, push = RM2656).
  Au passage : `resolve_instance` accepte une **URL** là où un `meta.yml` historique en
  contient une au lieu d'un nom d'instance (constaté sur `lemathou/mathematicians-db`,
  qui faisait échouer `pm-doctor`), et `PMConfig.locate_task()` rend enfin le projet
  d'un ticket — nécessaire dès qu'une opération dépend de la config projet.
- **Un provider par défaut + des providers secondaires** (RM2653, chantier RM2626) :
  l'axe **task** d'un projet cesse d'être *une* instance et devient une **liste
  ordonnée** — un **primaire** (source de vérité PM : états NORMS, reporting
  temps/tokens, cascade, tag IA) et N **secondaires** (gestionnaires partenaires),
  chacun portant ses règles `link:` / `sync:` dans `meta.yml`. Deux défauts du socle
  P0/P1 sont corrigés au passage : `resolve_instance()` ne savait résoudre qu'une
  instance (→ `resolve_instances()`, `secondaries()`), et surtout
  **`RedmineTaskProvider` recevait une instance et l'ignorait** — toutes les requêtes
  partaient sur les globales `REDMINE_URL`/`REDMINE_API_KEY`, ce qui rendait le
  multi-instance inopérant malgré le registre. `redmine_creds(instance)` résout
  désormais URL + clé **par instance** (`REDMINE__<INST>__API_KEY`, socle RM2546),
  avec repli sur les clés globales quand l'instance déclarée *est* l'instance de
  travail. Conf incohérente refusée d'entrée : zéro ou deux primaires, instance
  dupliquée, ou `link:`/`sync:` posé sur le primaire (la source de vérité ne se
  synchronise avec personne). `pm-providers resolve` affiche la liste par axe.
  **Iso-comportement prouvé** : sans instance, les appels à `redmine_utils` sont
  littéralement ceux d'avant (pas même un kwarg en plus) ; formes dict, legacy
  `redmine:`/`gitlab:` et défauts du registre rendent un primaire unique.

### Outillage
- **Worklog de session : les tickets sont groupés par projet** (RM2724). Le projet
  n'apparaissait qu'en suffixe de ligne (`_(pisceen-presta)_`), en queue d'une ligne
  qui porte déjà statut, référence, titre, dérive et commit — invisible dès que la
  session mélange plusieurs projets, ce qui est le cas normal. Il devient un
  **sous-titre de groupe** dans chacune des trois sections (*Reste à faire*, *En
  attente*, *Fait*), et le suffixe disparaît. Le regroupement est un rendu, pas un
  tri : l'ordre des items dans un groupe reste celui de la session, celui des groupes
  suit leur première apparition — sauf `hors projet`, qui ferme la marche. Un item
  ouvert **sans `--project`** n'est plus orphelin : son projet est rattrapé depuis le
  chemin de la tâche résolue par `resolve_live`. Au passage, un item dont le label ne
  fait que répéter sa référence affiche enfin le titre de la tâche (« RM2680 — RM2680 »).
- **Notifications de session : une notification traitée quitte le backlog**
  (RM2715, NORMS v1.71.0). Le canal `notify` (RM2466) n'avait que deux états —
  *au backlog* ou *effacée* : une notification consignée « ticket à ouvrir »
  restait affichée telle quelle après l'ouverture, la livraison ET la MEP du
  ticket, sa consigne devenue fausse. Elle porte désormais sa résolution
  (`notify --resolve <n> --ticket RM<id> [--note …]`) : elle sort du backlog
  **sans sortir du store** et descend dans une section d'archive avec le ticket
  qui l'a portée — modèle déjà posé par `mr_pending` (RM2583) et le registre des
  demandes (RM2621). `--clear` cesse d'être le geste par défaut : il DÉTRUIT, et
  ne vide plus que l'archive (ni les ouvertes ni les `critical` sans `--all`).
  Le rognage du canal sacrifie l'archive avant les notifications encore ouvertes.
  Côté **cockpit** (onglet état), seules les ouvertes sont servies, avec un
  rappel discret du nombre de traitées.
- **La doc ne suppose plus un vault unique** (RM2710, lot L4 du chantier RM2662) :
  NORMS `environments` § « Gestion des secrets » (**v1.70.0**) décrit des vaults
  **déclarés** — instances du registre providers, slug, défaut, surcharge
  client/projet, identifiants par dev — et les trois formes d'URI, dont
  `vaultwarden://` **toujours valide** ; tripwire 11 du KERNEL généralisé (« le
  secret de déverrouillage », pas « le master password Vaultwarden »). Suivent les
  templates (aspect `environments`, bootstrap secrets et environnements), les skills
  (`mmi-env-sync`, `mmi-pm-karl-mail-send`), `karl-mail-send.py`, et
  `tools/synchro`, qui **refusait** les nouvelles formes d'URI (`case
  vaultwarden://*` — un `secret://…` dans `MYSQL_ADMIN_SECRET` mourait en « URI
  invalide »). Le contrôle d'environnement du cockpit liste désormais **une ligne
  par instance de vault déclarée** avec les *noms* des identifiants trouvés, au lieu
  de guetter trois variables `BW_*` en dur — et ne rend plus muet un poste dont le
  `.env` d'instance est illisible (cas d'un worktree ou d'une instance de test).
  Deux gardes ajoutées au test : aucune **valeur** d'identifiant présente dans
  l'environnement ne doit apparaître dans le rapport (l'ancien test ne cherchait
  qu'un motif de nom, il serait passé sur un secret affiché en clair), et une ligne
  par instance déclarée. L'identifiant du template `001-secrets-vaultwarden` est
  volontairement conservé : c'est la clé référencée par les `bootstrap.skip` des
  projets, le renommer les ferait re-proposer.
- **Backend KeePass** (RM2684, lot L3a du chantier RM2662) : un fichier `.kdbx`
  et une passphrase suffisent — aucun serveur, aucun compte à créer. C'est le
  backend qu'un intervenant externe peut fournir sans rien installer côté
  iProspective, et la preuve que l'abstraction de L0 tient. Déclaration
  `{ axis: secret, type: keepass, file: "~/vaults/ipro.kdbx" }` (ou
  `SECRET__<SLUG>__FILE` / `__KEYFILE` par dev) ; déverrouillage
  `unlock-vault.sh -i <instance>`, qui pousse la passphrase au daemon **et vérifie
  aussitôt qu'elle ouvre la base** — sinon l'échec ne se verrait qu'à la première
  résolution, longtemps après la saisie. Le chemin d'un secret suit les groupes
  KeePass (`secret://kdbx-perso/clients/acme/prod-db`), le chemin donné valant
  **suffixe** du groupe réel. Dépendance **optionnelle** : sans `pykeepass`
  (`sudo apt install python3-pykeepass`), l'instance se déclare `unreachable` avec
  la commande d'installation, sans gêner les autres vaults. Diagnostics ordonnés
  comme on les corrige : configuration → dépendance → déverrouillage.
  `pm-providers.py instance <slug> [--field …]` expose la fiche d'une instance
  (c'est ce qui permet aux scripts shell de connaître le type d'un vault).
  Corrigé au passage : le flux Vaultwarden posait sa session **sans slug**, donc
  `unlock-vault.sh -i <autre-instance>` aurait déverrouillé l'instance par défaut
  — le bon jeton dans le mauvais coffre.
- **Plusieurs vaults déverrouillés en parallèle** (RM2683, lot L2 du chantier
  RM2662). `vault-agentd` tenait **une** session ; il tient désormais un **état par
  instance** (session, horodatages, backend), donc des TTL et des verrous
  indépendants : déverrouiller le vault d'un client ne prolonge pas celui
  d'iProspective, et son expiration ne le verrouille pas. Le daemon ne quitte que
  lorsqu'il ne reste plus aucune instance ouverte — comportement d'origine dès lors
  qu'il n'y en a qu'une. Protocole étendu, **rétrocompatible** (un appel sans slug
  vise l'instance par défaut) : `SET-SESSION [<slug>] <token>`, `LOCK [<slug>]`,
  `SYNC [<slug>]`, `LIST-IN <slug> [filtre]`, et `STATUS <slug>` qui garde le format
  historique tandis que `STATUS` nu devient un tableau de bord `<slug>\t<état>`.
  Côté scripts : `unlock-vault.sh -i <instance>` (+ `--print-instance` pour
  diagnostiquer sans rien déverrouiller), `lock-vault.sh [<instance>]`,
  `vault-list.sh -i <instance>`. Le type de chaque instance vient du registre
  providers ; **sans registre lisible, le daemon dégrade** vers l'instance unique
  au lieu de tomber — un `sys.exit()` de `PMConfig.load()` (qui ne dérive pas
  d'`Exception`) tuait sinon le thread de service et le client recevait un silence.
  Corrigé au passage : la convention de nommage des identifiants par instance
  devient `SECRET__<SLUG>__…` avec slug **normalisé** (`vw-ipro` → `VW_IPRO`) — la
  forme à tiret n'était pas un nom de variable shell valide, donc inutilisable
  depuis un `.env` sourcé ; la forme littérale reste lue par tolérance.
- **Vaults déclarés en conf, par client ou par projet** (RM2682, lot L1 du
  chantier RM2662). Le registre providers gagne un **axe `secret`** : chaque vault
  est une instance nommée (`providers.servers.<slug>`, sans aucun secret dedans),
  avec un défaut (`providers.defaults.secret: vw-ipro`, qui reproduit l'existant).
  Deux limites du registre tombent au passage, au bénéfice de **tous** les axes :
  la liste d'axes devient **déclarative** (`providers.axes`) — un axe futur
  (monitoring/Zabbix) ne coûte plus qu'une ligne de conf —, et la résolution gagne
  le **niveau client** : `resolve_instance(project_meta, axis, registry,
  client_meta=…)` applique projet > legacy projet > **client** > défaut, ce qui
  permet « tous les projets de ce client passent par tel vault ». Sans
  `client_meta`, la résolution est identique à avant (prouvé par test). Les
  identifiants restent **par dev** : `SECRET__<slug>__CLIENTID` / `__FILE` /
  `__TOKEN` dans `~/.config/mmi-pm/.env` (convention RM2546), avec repli sur les
  variables historiques tant qu'un dev n'a pas migré ; `pm-providers.py resolve`
  affiche l'instance retenue et les **noms** des identifiants trouvés, jamais leurs
  valeurs. Corrigé au passage : `pm-providers resolve --client X` se laissait
  écraser par la détection du cwd et répondait pour le projet courant.
- **Socle multi-vault : `pm_secrets`** (RM2681, lot L0 du chantier RM2662). La
  résolution de secrets passe derrière une interface `SecretBackend` (statut,
  résolution, listing, `Capabilities`) avec des erreurs normalisées
  (`locked` / `unreachable` / `not_found` / `denied` / `bad_uri` / `unsupported`) ;
  `VaultwardenBackend` est l'**extraction iso-comportement** de l'existant, et
  `vault-agentd` ne fait plus que porter la session et le protocole. Trois formes
  d'URI acceptées : `secret://<instance>/<chemin…>[#champ]`, `secret:<chemin…>` et
  la forme historique `vaultwarden://<org>/<coll>/<item>` — **supportée
  définitivement**, aucun pointeur existant à réécrire. Un URI visant une instance
  autre que celle servie est **refusé explicitement** plutôt que résolu en silence
  dans le mauvais coffre (multi-instances : RM2683). Point d'extension
  `register_backend()` pour les backends suivants (KeePass RM2684, 1Password,
  Nextcloud Passwords, sops). Non-régression prouvée par un harnais qui rejoue
  l'ancienne et la nouvelle implémentation sur un faux `bw`
  (`test_vault_agentd_isocomportement.py`, comparaison stricte des réponses
  nominales + codes de sortie de `resolve-secret.sh`).
- **Contacts clients : nom, prénom, email, téléphone** (RM2702) :
  `pm-client-contact.py` (`add` / `list` / `set` / `remove` / `mark-internal` /
  `import-redmine`) devient le seul point d'écriture de `contacts[]` dans le
  `meta.yml` du client, au schéma `last_name` / `first_name` / `email` / `phone` /
  `role`. `internal: true` marque **nos** adresses — le gabarit de création en pose
  une chez chaque client, elle n'identifie donc personne (et a failli servir à router
  du courrier entrant, RM2669). `import-redmine` amorce la fiche depuis les comptes
  Redmine rattachés aux projets du client (nom, prénom, email y sont déjà ; le
  téléphone reste à saisir). Documenté dans NORMS (`structure-reference`, **v1.69.0**).
  Cockpit : catégorie *contacts*, et les arguments `const` du catalogue acceptent
  désormais une **sous-commande positionnelle**. Un **annuaire indépendant des
  clients** (une personne, plusieurs rattachements) est à l'étude — RM2703.
- **De l'email au ticket, à la validation** (RM2670, chantier RM2666) :
  `karl-mail-draft.py` rédige une proposition de ticket depuis un email de la file
  (`claude -p` sans outils, JSON strict, projet **choisi dans une liste fournie** —
  jamais inventé), puis crée le ticket **quand un humain valide** (`--create`), en
  journalisant le `Message-ID` d'origine dans la description. Un email qui répond à un
  fil pose une **note** au lieu d'ouvrir un doublon — y compris quand le sujet a perdu
  son marqueur `[RM<id>]` (`--note-on`). Par défaut, seuls sujet, expéditeur et
  500 premiers caractères partent au modèle ; `--full-body` reste un choix explicite.
  Cockpit : `mail-draft` / `mail-show` / `mail-create` / `mail-dismiss`.
- **Relève des emails de karl** (RM2668, chantier RM2666) :
  `scripts/karl-mail-fetch.py` ouvre enfin la **lecture** de la boîte
  `karl@iprospective.fr` (RM1723 était *send-only*) et dépose les messages humains
  dans une **file de triage** locale — hors git, le repo de données partant sur
  GitLab. Les dossiers classés côté serveur sont relevés en premier, **`INBOX`
  ensuite** (un correspondant inconnu du carnet n'est classé nulle part). Lecture
  **non destructive** (`BODY.PEEK`, pas de DELETE/MOVE, `--mark-seen` opt-in),
  **idempotente** (index des `Message-ID`), robots et listes écartés. Exposé au
  cockpit via le catalogue de commandes (catégorie *mail*), qui gagne au passage
  les arguments **`const`** — un flag imposé par le catalogue, ni affiché ni
  négociable côté client. Défauts calés sur la boîte réelle : `INBOX.Clients` est
  de confiance, `INBOX.Gitlab` / `INBOX.Vault` jamais relevés.
- **Routage des emails entrants → client/projet** (RM2669, chantier RM2666) :
  `karl-mail-route.py` + `pm_mail_routing.py` proposent, pour chaque email de la
  file, un client et — seulement quand c'est certain — un projet, avec **confiance
  et source** : fil `[RM<id>]`, table apprise `mail-routing.yml`, compte Redmine de
  l'expéditeur, `contacts[]` du client, indice textuel. Sinon l'email reste « à
  classer » — jamais de choix silencieux entre deux candidats (tripwire 14). Chaque
  correction humaine est **apprise** ; apprendre le *domaine* d'un fournisseur grand
  public (gmail, orange…) est refusé, et les adresses maison sont exclues des
  indices — sans quoi tout mail de Mathieu partirait chez un client au hasard,
  `contacts[]` portant la même adresse propriétaire chez les 20 clients.
- **Instances cockpit de test : les commandes ⚙ fonctionnent enfin** (RM2668) :
  `pm-cockpit-test-env` transmet `PM_CORE_DIR` à l'instance. Sans lui, le worktree
  de code n'a pas de `.env` et **toute** commande du catalogue mourait en rc=1
  (« aucun .env trouvé ») — `conso-report` comme les nouvelles commandes mail.
- **MR sans ticket** (RM2644) : `pm-mr create --no-ticket --title "…"` ouvre une MR
  pour un changement qui n'a pas de ticket — ajout d'un terme au glossaire du
  cockpit, coquille (cf. NORMS `governance` § « Changements sans ticket », v1.68.0).
  La **MR reste due** : les branches d'intégration et de prod sont protégées, « sans
  ticket » n'est pas « push direct » ; seules tombent les accroches au ticket (CF
  *GIT Branche* / *GIT PR*, `git.mr_urls`, `--status`). Le mode exige un titre,
  refuse un `rm_id` simultané et **refuse une branche préfixée `<id>-`** — elle y
  trahirait un ticket oublié. Comble le trou qui avait obligé à créer la MR du terme
  « one-off » à la main par l'API.
- **Env de session : plus de saut ssh inutile, plus de base périmée** (RM2646).
  Deux défauts de `pm-env-session`, constatés en prenant un ticket depuis le
  conteneur `dev` : (1) le helper privilégié était **toujours** appelé via
  `ssh <env_runtime.ssh_host>`, donc la box tentait de se joindre elle-même et
  échouait — « non bloquant », donc **le vhost n'était jamais posé sans que rien
  ne le dise** ; il s'exécute désormais en local (`sudo -n`) dès que le binaire
  helper est présent et exécutable, `env_runtime.force_ssh: true` rétablissant
  l'ancien comportement. (2) `resolve_base()` retenait le ref **local** de la
  branche d'intégration même périmé (vu : `refs/heads/dev` à ~200 commits de
  retard) et créait les branches de ticket sur du vieux code ; le garde de
  `pm-branch-start` (RM2574) est factorisé dans `pm_git.resolve_base_ref` et
  partagé par les deux outils — il ne pouvait pas rester d'un seul côté.
- **Clôture de ticket robuste** (RM2587) : le hook worklog de session
  (`pm-task-status-update`, étape 7) est best-effort — un checkout sans
  `pm_session_hook.py` ne casse plus la clôture ni l'auto-commit.
- **GC des envs de tickets fermés** (RM2566) : `pm-env-gc` / `mmi-pm env gc`
  retire les worktrees `envs/` dont le ticket est `ferme`, **propres** et
  **intégrés** (HEAD ancêtre de `origin/main`/`origin/dev`), et élague leurs
  branches locales en merge-safe. Dry-run par défaut ; saute tout worktree sale
  ou non intégré. (Comble l'absence de nettoyage périodique ; le bug de nommage
  qui produisait les slugs à rallonge était déjà corrigé, RM2523.)

### Documentation
- **Point d'entrée développeur** (RM2594) : `DEVELOPMENT.md` relie README,
  normes, `knowledge/` et `docs/` (architecture, flux, boucle de dev « comment
  contribuer »), référencé depuis le README. Pointe les sources vivantes, sans
  valeur qui rouille.

### Gouvernance
- **Contrat « docs vivantes » étendu à 4 cibles** (RM2595, NORMS v1.67.0) : la
  section dédiée « Développement du PM » (module `governance`) impose de mettre à
  jour, dans la même MR, la doc correspondant à la surface changée — `Changelog.md`,
  `README.md`, **aide cockpit** et **`DEVELOPMENT.md`** — avec déclencheur KERNEL
  « je livre un changement de surface ».

---

## [2.0.0] - 2026-08-19 — Multi-utilisateur & concurrence

Jalon d'architecture **majeur** : le PM passe de *mono-`karl` / single-writer global* à
*multi-développeur à données communes partagées, accès concurrent sérialisé par ressource*.
Aboutissement de la convergence **RM2438**. Publié avec **T6 (RM2502)** et **T7 (RM2551)**.
Le détail normatif est versionné à part (**NORMS v2.0.0**, cf. `norms/CHANGELOG.md`).

### Architecture
- **Multi-utilisateur au niveau OS** (T6/RM2502) : comptes de rôle `<dev>-pm` dans un groupe
  **`pm`** ; données communes partagées (squelette `2750` non group-writable, churn `2770`/`2775`
  setgid **jamais sticky**, bares `core.sharedRepository=group`) → écriture multi-dev **sans
  sudo**. Opérations privilégiées (prod `.mmi-pm-core` root-owned, branches protégées, tokens,
  systemd/cron) via **`sudo` humain** — **pas de compte `karl-sudo`**.
- **Secrets 3 niveaux** : perso `~/.config/mmi-pm/.env` (`600`, par dev, attribution) > instance
  `pm.env` (non-secret) > commun `.env` (secrets de service / fallback karl, `640 root:pm`).
- **Contrôle de concurrence** (T7/RM2551) : verrous **par ressource** (`flock` par ticket,
  écritures atomiques `os.replace`) remplaçant le single-writer global ; verrou optimiste
  `updated` = arbitre inter-machine ; `pm-lock-gc` (cron) = filet post-crash.

### Outillage
- **`pm-perms`** : enforcer idempotent et **committé** du modèle de perms multi-user (dossiers
  + fichiers env communs → `root:pm 640` sous `--var`) — remplace les runbooks scratchpad,
  source de dérive.

---

## [1.12.1] - 2026-07-20 — Garde de cible pm-branch-start

### Outillage
- **`pm-branch-start` refuse un CORE comme cible de branche de code** (RM2360). La
  cible n'était validée que contre `projects_root` (blocklist de taille 1) : lancé
  depuis la racine d'un workspace projet — le core, porteur de `.mmi-pm` — le script
  branchait le core au lieu du repo de code (bug RM2325). Garde structurelle : un repo
  qui **révisionne `.mmi-pm`** (`git ls-files`) est un core → refus avec message
  actionnable (le code se branche dans un worktree `envs/` tiré de `repos/`). S'appuie
  sur l'invariant NORMS 1.58.0 (structure-reference, RM2348). Cross-check ajouté : un
  cwd pointant sur un repo ≠ `git.repo` enregistré est refusé (contournable par `--repo`
  explicite). Tests : `test_pm_branch_start_guard.py`.

### Gouvernance documentaire
- Règle « **docs vivantes du repo PM** » (module governance, NORMS v1.54.0) :
  `Changelog.md` alimenté **dans la même MR** que toute livraison qui change la
  surface du système ; README sans valeurs qui rouillent (RM2250).

### Cockpit karl (web-UI, `karl.iprospective.fr`)
- **Backend de sessions** `karl-agent` (RM1771) : superviseur tmux d'agents
  (spawn/send/kill/capture), reprise de session (RM1939), nommage ticket ou slug
  (RM2144), unit systemd **user** dans le conteneur dev.
- **Front v0 → v0.1** : lanceur + attach navigateur (RM1873), ergonomie de
  supervision — prompts, chips skills, moniteurs multi-panes (RM1893), onglets
  groupés par projet + badge d'attention (RM2140), encart session en direct
  (branches/worktrees du registre pm_session, RM2166) restructuré multi-tickets
  (RM2173), copier/coller fiable ttyd (RM2168), choix moteur/modèle (RM1921,
  RM1941). Auth user/mdp + exposition publique (RM2139, spike RM1803).
- **Command-catalog déclaratif** (chapeau RM2203) : `GET /pm/commands` +
  runner générique allowlisté `POST /pm/run` (RM2209), menus/formulaires
  auto-générés (RM2211), menu Nouveau projet/client (RM2212), menu Réglages —
  édition contrôlée de pm.config/pm.pricing (RM2213).
- **Console de test / revue** (RM2210) : file `a_tester_*` enchaînable en
  onglets 🧪, déploiement d'env de session (choix clone BDD), verdicts
  valider/MEP/renvoyer ; déploiement vers l'env de test PARTAGÉ (`pm-env-deploy`,
  RM2218) ; **sonde de vivacité** des envs (canari `pm-env.txt`), fiche ticket
  riche avec **protocole de test** en évidence (RM2229).

### Boucle de recette outillée (RM2229)
- CF Redmine 30 « **Protocole de test** » (texte long) + miroir frontmatter
  `test_protocol`, outil `pm-task-protocol` (--set/--append, rédaction **au fil
  de l'eau**), garde-fou à la livraison ; `pm-env-session` tient `test_url`
  (frontmatter + CF 14) : create écrit, teardown vide ; étapes `post_create`
  déclaratives du manifeste (vendor, assets… — create = « réparer »).
  NORMS v1.53.0.

### Fiabilité outillage
- **Garde de périmètre projet** sur les 5 outils PM mutants (RM2274) : refus
  d'écrire sur un ticket d'un autre projet si l'id n'a jamais été vu dans la
  session (empreinte d'un id prédit, tripwire #13) ; `--cross-project` pour
  l'assumer. Complète les gardes code (RM2224/RM2240) côté écritures Redmine/MD.
- Fin de la prédiction d'ids : tripwire NORMS + `pm-task-add --porcelain`
  (RM2170), gardes `pm-mr` branche≠id + verbe atomique (RM2224), anti-prédiction
  d'iid de MR (RM2232), résolution de projet par path complet — fin de la fuite
  inter-clients (RM2219) ; `redmine-post-note` diagnostique les relations
  bloquantes au lieu de conclure « permissions » (RM2222) ;
  `pm-workspace-coloc` : alias PM_CLIENTS (RM2216) ; `pm-task-add` description
  multi-ligne (RM2003) ; `pm-project-new` crée le volet PM co-localisé (RM2228).

## [1.11.0] - 2026-07-08 — Privsep, instances, métriques

### Privilèges séparés & instances
- Code du core **root-owned** verrouillé par `core-lock` (RM2032), périmètre
  `var/` préservé aux updates (RM2056), migration `docs/` + refactor scripts
  (étape 0, RM2043) ; installeur complet d'instance `install-mmi-pm` + alias
  `mmi-pm` sur le PATH (RM2062) ; multiplexing SSH du `core update` — une
  connexion au lieu de N (RM2069).
- Outils de recâblage : `pm-gitlab-rename` (RM1983), `pm-session-relocate`
  (RM1989), remotes re-câblés après promotion des groupes GitLab (RM1992) ;
  détection projet via cwd dans les workspaces co-localisés (RM2095, RM2120).

### Métriques temps/tokens → Redmine
- Push des métriques par ticket : estimation + delta par commit (RM1806,
  réconcilié RM1825), reporting v2 split input/output idempotent (RM2048),
  auto-report post-commit / fin de session / clôture (RM2035), cron de
  rattrapage (RM2160), fix du sous-comptage du hook Stop (RM2161), tarifs
  Fable 5 / Opus 4.x dans `pm.pricing.yml` (RM2163/RM2164), ROI assisté
  (RM1717) ; garde anti-tick sur ticket fermé (RM2053).
- **Budget de contexte par rôle** : mesure + plafonds enforcés par le doctor
  (RM1943).

## [1.10.0] - 2026-06-29 — Discipline git & envs de session

- **Workflow 3 branches** dev → preprod → prod (RM2030), interdiction du commit
  direct sur branche protégée (NORMS RM2051) enforcée côté GitLab par
  `pm-protect` (RM2052) ; `pm-mr` — push + MR + CF + merge fiable avec poll de
  mergeabilité (RM1871, RM2055) ; `pm-branch-start` — branche par ticket +
  en_cours (RM1897).
- **Layout workspaces repos/+envs/** : migration des workspaces pré-norme
  (`pm-env-migrate`, RM2028, skill RM2159), ids de session courts + worktrees
  suivis (RM2034) ; **envs de session par ticket** `pm-env-session` (RM1834,
  hooks auto sur en_cours/ferme).
- Rotation auto des tokens GitLab à J-7 + vérif début de session
  (`pm-token-check`, RM2046) ; worklog de session auto-alimenté par hooks +
  statut live (RM2068) ; `norms/VERSION` + `pm-norms-changes` (RM2033) ;
  `pm-task-blockers` — diagnostic des transitions refusées (RM2066).

## [1.9.0] - 2026-06-12 — Gouvernance NORMS & rôles Redmine

- **NORMS factorisé** : KERNEL runtime (déclencheurs + tripwires) + modules à la
  demande + assemblage `pm-norms-assemble` / garde `pm-norms-doctor` (RM1922) ;
  skills `mmi-pm-*` migrés dans le repo et distribués cross-instance (RM1868) ;
  ledger de non-perte réconcilié (RM2070).
- **Rôles & attribution Redmine** : statut terminal unique « Fermé » + CF Raison
  (RM1742), Manager IA formalisé + cascade projet (RM1734), demandeur effectif
  via author (RM1735, migration RM1739), passe agent-testeur conditionnelle
  `requires_agent_test` (RM1879), statut d'entrée `nouveau` (RM1829), couplage
  statut+assignation (RM1752).
- Outillage : `pm-task-link` (RM1709), `pm-task-edit-desc` (RM1794),
  `redmine-config-check` (RM1807), stats PM (RM1865), `pm-wiki-sync` P1
  (RM1841), bot Telegram karl — spawn + injection conversationnelle
  (RM1775/RM1776), symlink workspace unifié `.mmi-pm` (RM1750), filtrage CF
  « IA » (RM1716).

---

## [1.8.0] - 2026-05-15

### Ajouté — Couche d'abstraction des chemins (`pm.config.yml` + `pm_paths.py`)
- Nouveau fichier `pm.config.yml` à la racine : tous les chemins du système
  (racines, entités, projets, tâches, symlinks) sont définis comme patterns
  paramétrables. Aucun chemin absolu local n'est commité (uniquement `${VAR}`
  depuis `.env`)
- Nouvelle lib `scripts/pm_paths.py` : `PMConfig.load()` + `cfg.path(...)` +
  itérateurs (`iter_entities`, `iter_projects`) + lookups Redmine
  (`find_task`, `find_project_by_redmine_id`)
- Support d'un `pm.config.local.yml` (gitignored) pour surcharge locale
- Permet de déplacer le repo PM, déplacer le repo projets, ou réorganiser la
  structure interne sans toucher au code ni à la doc — une seule ligne à
  modifier dans la config

### Modifié — Symlink workspace → PM caché (`.mmi-pm`)
- Renommage de `mmi-pm` → `.mmi-pm` dans les 2 workspaces concernés
  (`/zfs/workspaces/redmine`, `/zfs/workspaces/perso/mathematicians-db`)
- Convention portée par `paths.reverse_link` dans `pm.config.yml`

### Modifié — Refacto exhaustif scripts + doc
- 5 scripts refactorés pour passer par `PMConfig` : `pm-dashboard.py`,
  `redmine-fetch-task.py`, `redmine-fetch-updates.py`, `pm-project-bootstrap.py`
  (+ corrections docstrings `priority.py`, `validate-task.py`)
- Doc reformulée en patterns logiques (`paths.task_file`, `{entity_client_dir}`,
  …) : `CLAUDE.md`, `agents/worker-common.md`, `agents/orchestrateur.md`,
  `agents/summarizer.md`, `README.md`, `templates/bootstrap-tasks/002-git-repos.md`,
  `TODO/003-pm-cli.md`
- Plus aucun hardcode `projects_root / "clients"` ni `mmi-pm/...` dans le code
  ou la doc vivante

### Conventions
- NORMS v1.8.0 (minor bump) : `norms/CHANGELOG.md` détaille les évolutions ;
  snapshot v1.7.2 archivé dans `norms/archive/`

---

## [1.7.2] - 2026-05-15

### Ajouté
- NORMS § "Memberships par défaut sur nouveau projet Redmine" :
  groupe Admin (49) en Manager + groupe iProspective (70) en Intervenant

### Acté
- Bootstrap projet `clients/redmine/projects/redmine/` exécuté avec succès :
  tickets RM1661 (secrets), RM1662 (git-repos), RM1663 (environnements) créés
  côté Redmine + tâches MD générées + bootstrap.done rempli

---

## [1.7.1] - 2026-05-15

### Ajouté — Tâches de bootstrap projet
- 7 templates dans `templates/bootstrap-tasks/` (001-secrets, 002-git, 003-envs
  cochés par défaut ; 004-stack, 005-deployment, 006-testing, 007-monitoring
  optionnels)
- Section NORMS "Création d'un projet PM ↔ Redmine" + "Tâches de bootstrap"
- Frontmatter `project/overview.md` : champ `bootstrap.{skip,done}[]`
- Script `pm-project-bootstrap.py` à venir (commit suivant)

---

## [1.7.0] - 2026-05-14

### Ajouté — Environnements + gestion des secrets via Vaultwarden
- NORMS v1.7.0 (cf [norms/CHANGELOG.md](norms/CHANGELOG.md)) :
  - Aspect `environments.md` + énumération noms d'env standard
  - Tableau `env_vars[]` (noms + description, sans valeurs)
  - Convention `vaultwarden://<org>/<collection>/<item>` pour les secrets
  - Architecture vault : org iProspective + collections `<client>-agents` + user `karl@iprospective.fr` (read-only)
  - Task : nouveau champ `target_env`
- Scripts (4 nouveaux) :
  - `scripts/vault-agentd.py` — daemon local, session BW en mémoire, socket Unix
  - `scripts/unlock-vault.sh` — déverrouillage manuel (master password prompt)
  - `scripts/resolve-secret.sh` — résolution d'un secret par les agents
  - `scripts/lock-vault.sh` — verrouillage explicite
- Templates : `aspects/common/environments.md` créé ; `hosting.md` resserré
- `.env.example` étendu (VAULT_URL, BW_CLIENTID/SECRET, options d'expiration)

### Modifié
- `templates/task.md` bumped 1.5.2 → 1.7.0 + `target_env`

---

## [1.6.0] - 2026-05-14

### Ajouté — Types d'entités + partage cross-client + symlinks bidirectionnels + knowledge base
- NORMS v1.6.0 (cf [norms/CHANGELOG.md](norms/CHANGELOG.md)) :
  - `client.type` ∈ {`client`, `product`, `self`}
  - `project.used_by_clients[]` + `project.provided_by` (cross-client)
  - `clients/<c>/projects_used/` (symlinks générés, navigation humaine)
  - Symlink inverse `workspace` côté PM (en plus du `mmi-pm` existant côté workspace)
- `knowledge/` (knowledge base transverse, complémentaire à `security/knowledge/`) :
  - `knowledge/INDEX.md`
  - `knowledge/redmine/` : overview, api, gotchas, migration Textile→Markdown, script
- Clients créés : `iprospective` (type self), `redmine` (type product)
- Migration Textile → Markdown réussie sur l'instance Redmine interne `tasks.iprospective.fr` :
  6974 modèles convertis, 0 échec, procédure capitalisée

### Modifié
- `clients/lemathou/client/overview.md` bumped `schema_version: 1.6.0` + `type: self`
- `CLAUDE.md` : référence `knowledge/INDEX.md`, version 1.6.0

---

## [1.5.5] - 2026-05-13

### Ajouté
- `redmine-fetch-updates.py` : appende désormais chaque nouveau journal Redmine
  dans le `.log.md` de la tâche (persistance, conforme append-only NORMS)
- `redmine-post-note.py` : option `--attach <fichier>` (peut être répété) — upload
  les fichiers via `/uploads.json`, récupère les tokens, les associe au PUT issue
- NORMS § "Workflow multi-tour" : format de l'entrée log issue de Redmine documenté

### Acté
- Cycle multi-tour testé sur RM1658 :
  - User a posté remarques + repassé en a_corriger + réassigné à l'agent
  - Agent a détecté les nouveautés via fetch-updates, traité les 4 demandes,
    enrichi les 3 livrables, soumis avec les fichiers en pièces jointes

---

## [1.5.4] - 2026-05-13

### Ajouté
- `scripts/redmine-fetch-updates.py` — récupère les nouveaux journaux Redmine
  depuis `redmine_last_journal_id`, affiche notes + changements d'attributs,
  met à jour le frontmatter de la tâche
- `scripts/redmine-post-note.py --assign-to <id|author|me>` — réattribution
  manuelle ou automatique
- Auto-réattribution au demandeur sur `--norms-status a_tester_verifier`
- Vérification post-PUT étendue à `assigned_to_id` (warn + exit 2 si non appliqué)
- Schema 1.5.2 : champs `redmine_last_journal_id`, `redmine_last_checked_at`
- NORMS : section "Workflow multi-tour" + règle d'attribution Redmine

### Acté
- Workflow end-to-end testé sur RM1658 (création Redmine → fetch → traitement →
  livrables → soumission → réattribution au demandeur)

---

## [1.5.3] - 2026-05-12

### Ajouté — Intégration Redmine (premiers scripts)
- `scripts/redmine-test.py` — vérifie connexion API (URL, clé, projets accessibles, ticket spécifique)
- `scripts/redmine-fetch-task.py` — fetch un ticket Redmine, identifie le projet MD via `redmine.project_id`, génère le fichier de tâche conforme au schéma + journal initial, lance le validateur
  - Mapping `tracker` → `type` (bug→bugfix, feature→feature, support→assistance, etc.)
  - Mapping `priority` → `priority` (low/normal/high/urgent)
- `scripts/redmine-post-note.py` — poste une note (avec changement de statut optionnel) sur un ticket ; utilisé par les agents pour répondre

### Acté
- Connexion vérifiée : compte API = `claude-chefproj-1` (orchestrateur), projets `ai-agents` + `mathematicians-db` accessibles

---

## [1.5.2] - 2026-05-12

### Ajouté
- `scripts/pm-dashboard.py` — CLI dashboard du système (phase 0 de TODO 002)
  - Vue d'ensemble : clients, projets, tâches
  - Tableau des statuts par projet
  - Top ROI (tâches `a_faire` avec dépendances satisfaites)
  - Sections "En cours", "À tester", "À corriger" (affichées si non-vides)
  - Activité récente (5 derniers `.log.md` modifiés)
  - Utilise `rich` si disponible (rendu coloré), fallback ASCII sinon
  - Filtres : `--client <slug>`, `--top N`, `--activity N`
- TODO 002 phase 0 marquée comme réalisée

---

## [1.5.1] - 2026-05-12

### Modifié
- Symlink de cohabitation renommé : `.pm` → `mmi-pm` (évite conflit avec extension Perl, visible dans `ls`, préfixe cohérent avec les skills `mmi-*`)
- Symlink existant sur `mathematicians-db` renommé en place

---

## [1.5.0] - 2026-05-12

### Ajouté — Lien Redmine strict + symlink `.pm`
- Convention `.pm` : symlink dans chaque workspace projet vers le dossier PM centralisé
- Lien dur MD ↔ Redmine : `redmine_id` + cohérence filename, `redmine.project_id` obligatoire
- Validator étendu (`validate_redmine_coherence`)
- TODO 002 (interface de gestion + supervision) et TODO 003 (CLI `pm`) créés

### Modifié
- NORMS bumped 1.4.0 → 1.5.0
- Templates `task.md`, `project-overview.md`, `client-overview.md` mis à jour
- `worker-common.md` : résolution de chemins documentée
- PISTES.md : ajout de la piste « Création MD → Redmine » (sens inverse)

---

## [1.4.0] - 2026-04-27

### Ajouté — Cahier des charges multi-fichiers
- Structure `client/` et `project/` en dossiers (overview + aspects)
- 40 templates d'aspects par domaine : common, website, ecommerce, api, saas,
  mobile, data, legal
- Cascade aspect par aspect entre niveaux client et projet

### Modifié
- Templates renommés en `*-overview.md`
- Agents (worker-common, summarizer) mis à jour pour charger tout le dossier
- NORMS bumped 1.3.0 → 1.4.0

---

## [1.3.0] - 2026-04-27

### Ajouté — Multi-client / multi-projet hiérarchique
- Structure `clients/{C}/projects/{P}/tasks/` dans le repo projets
- Cascade contextuelle : client → projet → tâche, héritage avec override
- Fichiers auto-générés (Changelog, Pistes, Remarques) aux niveaux client et projet
- Section "Structure / Fonctionnement" enrichie automatiquement
- `agents/summarizer.md` : nouvel agent pour génération automatique
- `scripts/priority.py` : ordonnancement par ROI avec filtre dépendances
- `scripts/cron.example.sh` : exemple de configuration cron pour orchestrateur,
  summarizer, ranking ROI hebdomadaire
- `templates/client.md` : nouveau template client
- `templates/project.md` enrichi : client, defaults, stack (avec section tests),
  section Structure / Fonctionnement

### Modifié
- `agents/orchestrateur.md` : déclenchement par cron, scan multi-clients,
  référence à scripts/priority.py
- `agents/worker-common.md` : contexte chargé en cascade (4 niveaux)
- `CLAUDE.md` : invocation mise à jour avec client + projet
- `README.md` : workflow création client / projet / tâche
- NORMS bumped v1.2.1 → v1.3.0 (archive v1.2.1 créée)

---

## [1.2.5] - 2026-04-27

### Ajouté
- `scripts/validate-task.py` : validateur structurel (champs obligatoires,
  enums, transitions, cohérence status_history, conditional rules, completion_pct)
- `.gitlab-ci.yml` : pipeline CI exécutant la validation sur chaque push
- `templates/RM9999_exemple-tache-complete.md` : exemple complet et valide,
  utilisé par le CI comme cas de test
- Règle test-first dans `worker-dev.md` (test reproduisant le bug avant fix,
  tests des critères d'acceptation avant code)
- Obligation pour `reviewer.md` d'exécuter les tests (pas juste vérifier
  leur existence) — tout échec = rejet automatique
- `PISTES.md` : section "Tests — évolutions reportées" avec stack de tests
  dans templates/project.md, validation cross-fichiers, génération automatique
  de stubs depuis critères d'acceptation, tests workflow E2E

---

## [1.2.4] - 2026-04-27

### Ajouté
- `PISTES.md` : document de pistes d'évolution AI-natives pour une v3
  (branch & merge, critiques continus, décomposition asymétrique,
  pipeline Intent→Plan→Fan-out→Synthèse, exécution spéculative)
- Nouveaux rôles d'agents proposés : intent-extractor, adversary, critic, synthesizer

---

## [1.2.3] - 2026-04-27

### Ajouté
- `.env.example` : variables d'environnement requises (GitLab, Redmine, chemins)
- `projects/` gitignored : le dossier projects est désormais un repo git séparé,
  cloné indépendamment — le repo PM est publiable sans données de projets

### Modifié
- `.gitignore` : ajout de `.env` et `projects/`
- `norms/NORMS.md` v1.2.1 : config globale externalisée en variables d'environnement

---

## [1.2.2] - 2026-04-27

### Ajouté
- `CLAUDE.md` : bootstrap automatique pour Claude Code — orientation, ordre de lecture, rappels critiques
- `scripts/invoke.md` : guide d'invocation manuelle (workers, reviewer, orchestrateur, workflow complet)

---

## [1.2.1] - 2026-04-27

### Refactoring
- Extraction des règles communes des workers dans `agents/worker-common.md`
  (périmètre d'écriture, contexte, format journal, soumission, locking, blocage)
- Workers réécrits en version compacte : chaque fichier ne contient plus que
  ce qui est spécifique au rôle — taille réduite de ~50%

---

## [1.1.0] - 2026-04-27

### Ajouté
- Section collaboration multi-agents dans NORMS.md (rôles, règles d'écriture, protocoles)
- Section architecture de déploiement dans NORMS.md (V1, V1.5 NFS/ZFS, V2 Git/branches)
- `README.md` racine : guide d'utilisation humain et agent
- `agents/` : system prompts de référence pour orchestrateur, workers, reviewer
- `.gitignore`

### Modifié
- `CHANGELOG.md` racine : rempli et séparé du changelog de normes

---

## [1.0.0] - 2026-04-26

### Initial
- Structure de dossiers : `norms/`, `projects/`, `templates/`, `norms/archive/`
- `norms/NORMS.md` v1.0 : schéma frontmatter complet, machine d'états 7 statuts,
  valeurs énumérées, règles du journal append-only, versionning des normes
- `norms/CHANGELOG.md` au format Keep a Changelog
- `templates/task.md` : template tâche avec tous les champs
- `templates/project.md` : template projet
- Initialisation Git sur branche `dev`
