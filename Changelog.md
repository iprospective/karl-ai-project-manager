# Changelog système

Évolutions du système de gestion de tâches dans son ensemble.
Pour les évolutions du schéma des tâches, voir [norms/CHANGELOG.md](norms/CHANGELOG.md).

Format : [Keep a Changelog](https://keepachangelog.com/fr/)

> Ce fichier consigne les **jalons système** (architecture, outillage, surface
> d'usage). Le détail vit dans les tickets `pm-ai-agents` ; les évolutions des
> normes dans `norms/CHANGELOG.md` (versionnées indépendamment, cf. `norms/VERSION`).

---

## [Unreleased] — Cockpit & environnements de test

- **Les données de session quittent le home** (RM2992) : worklogs, état de karl-agent, curseurs de
  tour et registre des sessions vivent désormais sous **`var/` du repo PM**, communs à tous les
  agents de la machine. Ils étaient dans `~` « par défaut d'avoir choisi », et c'est le home qui
  décidait de qui voyait quoi : un agent ne voyait pas le travail d'un autre, et le régime de
  partage dépendait du hasard des montages (`~/.claude` partagé hôte↔conteneur, `~/.local/state`
  non — RM2391 s'était fait piéger dessus). Demande du 2026-09-05, débloquée le 2026-09-12 :
  « partagé, depuis le début ». `pm_stores` porte la racine (`PM_STATE_DIR`), chaque store garde sa
  variable, **`var/sessions` en gagne une** (`PM_SESSIONS_DIR` — le dossier bougera sans doute), et
  chacun conserve son **repli d'hier** là où la config PM ne se charge pas : résoudre un chemin ne
  doit jamais faire échouer l'appelant. Nouveau `mmi-pm stores-migrate` : idempotent, **ne remplace
  jamais** un fichier déjà à destination, ne déplace que nos fichiers dans les dossiers partagés
  avec Claude Code, laisse derrière les stores morts (`answers.jsonl`) et pose une trace dans
  l'ancien dossier ; `mmi-pm core update` l'appelle après le redémarrage de karl-agent. Mesuré ici :
  **683 fichiers, 167 Mo**. Les transcripts et `history.jsonl` ne bougent pas — Claude Code les
  écrit, nous les lisons. Quatre scripts qui recopiaient un chemin d'état à la main passent par
  `pm_stores` (`karl-agent`, `karl-mail-fetch`, `pm-cockpit-test-env`, `pm-gitlab-push-check`,
  `pm_notify`), et une garde de test refuse désormais tout script qui vise un store sans lui.
  NORMS 2.42.0 § « Où vivent les données de session ».
- **La garde de livraison était cassée hors du core** (RM2992, en marge) : `PMConfig.load()` **sort**
  (`sys.exit`) quand le `.env` canonique manque — le cas d'un clone de dev — et `SystemExit`
  n'héritant pas d'`Exception`, les `except Exception` des bibliothèques la laissaient remonter et
  tuer le programme. **17 tests rouges** sur `main` dans tout worktree, avec pour seul symptôme un
  message d'aide sur le `.env` et aucun nom de test. Trois occurrences corrigées ici
  (`pm_log._declared_dir`, `pm_notify._state_dir`, `pm_monitor._local_path`) : **12 tests
  repassent au vert**. Le défaut de fond — une fonction de bibliothèque qui peut tuer son appelant —
  est ticketé à part (RM3119).

- **Les questions ouvertes d'un ticket sont dans sa description** (RM3116) : elles gouvernaient déjà des
  choses sérieuses — un ticket ne se ferme pas avec une question en attente — mais ne se voyaient nulle
  part où l'on lit un ticket. `mmi-pm task-questions` régénère une section **❓ Questions ouvertes** dans
  la description, entre marqueurs, comme les chapitres du CDC le sont du même fichier : deux vues, une
  donnée. Une question tranchée s'affiche **cochée avec la décision qui l'a tranchée** — cocher sans dire
  ce qui a été décidé produirait une trace qui ment par omission. La section suit **au fil de l'eau** :
  poser ou trancher une question la remet d'aplomb. Et **une coche posée à la main est signalée**, pas
  décochée en silence : quelqu'un a voulu dire quelque chose, mais une coche n'est pas une réponse.

- **Une vue ou un panneau ne s'empile plus sous le terminal** (RM3115) : la zone centrale a **trois**
  surfaces sœurs — tickets, vues, panneaux — et RM3051 n'en gérait qu'une. Les deux autres passaient par
  un `display` posé à la main, qui ne prévient personne : la session restait affichée et la page se
  rangeait dessous, sous le terminal et même sous le composer. C'est pourquoi le défaut semblait corrigé,
  il l'était pour les tickets seulement. Les trois passent maintenant par la disposition, avec la règle
  qui manquait : fermer **une** surface ne rend la session que si plus **aucune** n'est ouverte — sinon
  passer d'un onglet à l'autre faisait réapparaître le terminal entre les deux.

- **Menu Supervision : les alertes du parc, situées chez un client** (RM3112) : un nouvel axe de
  fournisseurs, **Observateurs**, avec Zabbix pour premier type — déclaré comme les autres, jeton en
  écriture seule. Le code ne suppose pas Zabbix : `pm_monitor` définit une interface à trois questions et
  un backend par outil, Uptime Kuma étant déclaré pour le jour où l'on observera des **sites** plutôt que
  des machines. Le menu 🩺 montre les alertes actives avec leur sévérité, leur hôte et leur durée, et
  **le client associé à cet hôte**. Le bouton ＋ ticket ouvre le ticket là, par le chemin normal de
  création. **L'association hôte → client/projet se propose** (slug du client, ou domaine cité dans ses
  fiches) **et se confirme à la main**, en disant toujours sa source et sa confiance : une association
  devinée en silence enverrait un ticket chez le mauvais client. Sans projet associé, le bouton n'apparaît
  pas et la ligne renvoie vers l'association. Cockpit 3.13.0.

- **Un fil de notifications pour l'instance** (RM2792, lot 2) : trois canaux disaient déjà des choses,
  chacun dans son coin — le journal trace tout, le worklog retient ce qui est notable dans **une**
  session, l'ordonnanceur garde l'historique de ses travaux. Aucun ne répondait à « qu'est-ce qui demande
  mon attention, toutes sources confondues ». `mmi-pm notify` est cette réponse : une **file**, pas une
  trace — chaque entrée est `neuf`, puis `lu`, puis `traite`, et sort de la vue. **L'anti-répétition vient
  de l'identifiant** : c'est l'empreinte du contenu, donc un travail qui échoue toutes les heures produit
  une ligne avec un compteur, pas vingt-quatre lignes. Alimenté par l'ordonnanceur (échec ou débordement)
  et par les notifications de session. Servi par `/notifications`, marqué par `/notifications/mark`. La
  garde de taille est **molle par conception** : elle n'oublie que des entrées traitées, jamais ce qui
  attend — un fil qui jette du travail pour tenir une taille est pire qu'un fil trop long.

- **Le journal du démon écrivait dans le vide, en silence** (RM3095) : il visait la racine du **code**,
  qui appartient à root sur une instance verrouillée. Chaque écriture échouait, l'échec était compté et
  jamais dit, et le panneau « journal » du cockpit ne montrait que le navigateur — depuis des semaines.
  Le journal suit maintenant la racine déclarée `roots.log_dir` (« auto » = `{pm_dir}/var/log`, accessible
  au groupe en production), **éprouve** l'emplacement à la configuration et bascule sur l'état de
  l'utilisateur s'il faut, en le disant une fois. `/health` expose sa santé : un journal muet se voit.
- **Un objet de journal, pour l'utiliser partout** (RM3095) : `pm_log.journal("<source>", "<catégorie>")`
  porte la source et un contexte (`rm`, `sid`…) qui suivent chaque entrée, avec `.info/.warn/.error` et un
  `with journal.step("…")` qui mesure la durée, journalise l'échec avec un traceback court et le relance.
  Câblé là où un geste change un état : création et merge de merge request, changement de statut, création
  de branche de ticket, création de ticket, exécution d'un travail périodique. Chaque script survit à
  l'absence du module — un journal ne doit jamais casser ce qu'il observe.

- **La moisson rend à chaque ticket ce qui est à lui** (RM3100) : `pm-think-harvest` attribuait tout
  le transcript au ticket courant **au moment où il tournait**. Juste sur une session mono-ticket,
  faux sur une séance longue — une passe lancée sous RM3099 a versé dans son carnet cinq questions
  qui appartenaient à RM3015, RM3074 et RM3090, traités plus tôt dans le même fil. Ce n'est pas
  cosmétique : la garde de clôture refuse ensuite de fermer un ticket sur des questions qui ne sont
  pas les siennes. Le fil se découpe désormais **par tour**, chacun attribué au ticket qu'il a
  réellement touché, avec la résolution du tick de conso (mutation PM > fiche éditée > mention). Un
  tour sans signal continue le précédent ; un ticket seulement **cité** ne détourne rien, sauf si la
  citation vient du demandeur dans son prompt — là, c'est une consigne ; un identifiant capté au
  passage (chemin, URL) qui n'est aucun ticket connu est ignoré. Sur le transcript de la séance qui
  a révélé le défaut : 18 groupes au lieu d'un seul. `--no-split` rend l'ancien comportement, pour
  rattraper à la main. Au passage, le résolveur reconnaît enfin le **wrapper `mmi-pm <verbe>`** —
  la forme courante d'appel : l'ignorer, c'était n'avoir aucun signal fort sur une session qui ne
  tape jamais `pm-task-*.py`, et donc attribuer tour et conso au dernier ticket vu. NORMS 2.40.0.

- **Le navigateur devient testable, donc obligatoire** (RM3036) : nouvel outil
  `tools/browser-check` — charge une URL dans un Chromium headless, exécute le geste, lit la
  console et **constate l'effet dans l'interface**, code retour `0`/`1`. Il comble le trou
  d'outillage qui a laissé passer RM3025 : une modif front livrée sans passage navigateur avait
  cassé l'ajout au panier en prod, sur deux causes qu'aucun test unitaire ne voyait — un endpoint
  en 500 et un bundle CCC non régénéré. Le verdict vit dans un module **pur** (`lib.js`), testé
  sans navigateur : sans cette coupure, on ne peut tester l'outil de test qu'en lançant Chromium,
  donc on ne le teste pas. Trois partis pris tirés de l'incident : une **option mal tapée est une
  erreur** (un scénario qui « passe » parce qu'un contrôle a été ignoré est pire que rien) ; un
  **asset 404 est séparé d'un plantage JS** (`--allow-console-errors` ne fait pas taire un
  déploiement incomplet) ; **aucun navigateur n'est téléchargé** — à défaut de Chromium en cache,
  l'outil refuse de conclure plutôt que de laisser croire à une validation. playwright-core ou
  puppeteer-core, indifféremment. Rejoué pour de vrai sur la préprod Calicote (fiche produit →
  clic « Ajouter » → compteur panier 0→1).
  Côté conf : `pm-project-config --browser-test true` pose le drapeau `browser_test` au niveau
  **projet** (un client peut avoir un site public et un back-office interne) ; une valeur douteuse
  est **rejetée** plutôt que traduite en `false` — une règle de test qui s'éteint en silence ne
  protège plus rien. Activé sur `calicote/prestashop`. NORMS 2.38.0 : `testing` §7, tripwire #17
  amendé (le rendu navigateur n'est plus un cas « non automatisable »), runtime KERNEL synchronisé.
- **Compte-rendu : prévenir aussi le demandeur** (RM3092) : une case **par ticket** dans le
  panneau, plus une case globale. Le demandeur reçoit **son propre email, limité à ses
  tickets** — plutôt qu'une copie du compte-rendu complet : il n'a pas à découvrir ce qui a
  été livré pour les autres. Résolution depuis l'annuaire (`creator` → ref, segment ou
  prénom) ; **une correspondance multiple n'est pas une correspondance** — on signale au
  lieu de tirer au sort, et un email envoyé à la mauvaise personne ne se rattrape pas.
  Aucun doublon : qui est déjà destinataire du compte-rendu n'est pas re-servi, et `sent_to`
  consigne tout le monde. CLI : `client-notify preview|send --demandeur <RM>` (répétable) ou
  `--demandeurs`.
- **Rattrapage de file à la fermeture** (RM3087) : la mise en file ne dépendait que de la
  transition `en_mep` — un ticket livré puis fermé après recette n'entrait jamais au
  compte-rendu. Il y entre désormais à sa **fermeture**, mais sous une condition plus
  stricte (`never_queued`) : uniquement s'il n'a **jamais** été mis en file, pour qu'un
  ticket déjà annoncé ne le soit pas une seconde fois.
- **Verbes d'ajout incrémental** (RM3041) : `pm-task-description-update --add-item` /
  `--add-criterion` et `pm-task-protocol --add-test "SECTION|LIBELLÉ"` ajoutent **une ligne**
  dans la bonne section sans réécrire la description ni le protocole. Idempotents (casse et
  espaces ignorés), section créée si absente, gabarit « à définir » remplacé au premier vrai
  critère, identifiant de test incrémenté (A2 → A3) avec cases d'environnement vides.

- **Consigner AVANT la compaction** (RM3098, NORMS 2.37.0) : RM3071 réinjecte le KERNEL *après* une
  compaction ; l'*avant* n'était pas couvert. Le hook `PreCompact` ne faisait qu'un `refresh` du
  worklog — la moisson n'y était pas câblée, alors que c'est le **dernier moment où les tours existent
  en clair**. Elle l'est désormais, en passe **complète** (`--full`) : le curseur incrémental n'a pas
  à décider ce qu'on relit quand le fil va devenir un résumé. NORMS gagne la règle « avant une
  compaction, avant de rendre la main » — prochaine étape, questions non tranchées, arbitrages
  récents — et son déclencheur au KERNEL. Ce qui n'est pas consigné là n'est pas plus difficile à
  retrouver : il n'existe plus (leçon RM2997).
- **Inventaire des capacités de karl** (RM3048, **absorbé par RM3099**) : un registre curé par capacité
  (123 entrées sur 12 domaines d'usage) répond à « qu'est-ce que karl sait faire », là où le registre
  dérivé des tickets répondait à « quel ticket a fait quoi ». Une capacité couvre souvent plusieurs
  tickets. RM3099 a fondu les deux : les 123 libellés écrits à la main vivent désormais dans le registre
  unique du projet, avec leurs tickets en référence.
- **Un seul registre de fonctionnalités par projet** (RM3099) : le projet portait deux `F001` différents,
  deux feuilles de route, deux taxonomies, et un lien déjà faux de l'une vers l'autre. Arbitrage du
  demandeur : « les fonctionnalités n'ont pas besoin d'un ticket pour exister… avec mention d'un ticket
  s'il y en a un, ou même plusieurs ». Il n'y a donc plus **une** notion de fonctionnalité, décrite pour
  elle-même, qui **cite** ses tickets — éventuellement aucun. `pm-cdc-features --absorb` verse un registre
  dans un autre : ids neufs pour les entrées versées (ceux déjà publiés ne bougent pas), entrées dérivées
  **absorbées** dès que leur ticket est cité ailleurs, aucune référence perdue (123 versées, 140
  absorbées, 592 au total). Le plan suit le domaine d'**usage** (`domaine`) ; le domaine technique reste
  une **étiquette** (`domaine_technique`), une colonne du chapitre et du cockpit, jamais un second plan.
  L'état d'une entrée se dérive de ses tickets et **le plus avancé l'emporte** — une capacité livrée reste
  livrée quand un ticket d'évolution s'ouvre ; ce qui reste ouvert est compté (« livré · 2 en cours »).
  `--prefix` et `cure:` disparaissent, `manuel` (libellé) et `etat_manuel` (état) se séparent, `rm:` se
  fond dans `tickets:`. NORMS 2.39.0 : § « Une fonctionnalité, des tickets en référence ».

- **La réflexion d'un ticket sur sa fiche** (RM3089, lot L6 de RM3015) : bloc **🧠 Réflexion** —
  questions ouvertes, décisions et conseils, fonctionnalités, notes — avec le compteur qui **annonce
  le refus de clôture** au lieu de le laisser découvrir. Deux gestes au survol des entrées **encore
  ouvertes** seulement (trancher, écarter) ; l'écriture passe par la route de RM3064 (D022), donc une
  seule validation et une seule refusion des registres. Le serveur sert la réflexion avec la fiche,
  en lecture bornée (une fiche s'ouvre souvent). En CLI, `pm-task-show` nomme les registres du projet.
- **Notifications et demandes rattachées au ticket, et « ❓ à trancher » dans le worklog** (RM3088,
  lot L4 de RM3015). Une notification `--ref RM<id>` dont le message ne citait pas le numéro était
  **perdue pour le ticket** : le brief la cherchait par sous-chaîne dans son texte, jamais par sa
  référence. Et les **demandes** n'étaient pas restituées du tout à la reprise, alors que ce sont
  elles qui disent ce qui avait été demandé sans avoir encore de suite. Les deux sont corrigés
  (`rattache()` : la référence d'abord, le texte en repli). Le worklog gagne un bloc **« à
  trancher »** — les questions ouvertes des tickets de la session, comptées depuis les compteurs
  `think:` des fiches — à côté de « à traiter », jamais fondu avec : une demande appelle une action,
  une question un arbitrage. Un seul canal sert cet état (D021). Le cycle de vie des notifications
  reste à RM2792 (D024).
- **Deux sessions sur le même ticket : on le dit** (RM3086, lot L3 de RM3015). RM2818 n'alertait
  qu'au bouton « nouvelle session » du cockpit ; une prise depuis un terminal (`pm-task-take`,
  passage en `en_cours`) ne disait rien, et deux agents se disputaient la fiche, la branche et le
  statut sans le savoir. Cause de fond : le lien ticket ↔ session existait en **trois exemplaires
  qui s'ignoraient** (worklog local, jonctions locales à la machine, journal du ticket). Le registre
  **partagé** `var/sessions` (RM2034) gagne un `tickets[]`, alimenté dès qu'une opération PM touche
  un ticket ; `pm_concurrent` répond à « qui travaille déjà dessus » et l'avertissement est posé à la
  prise **et** au passage en `en_cours`. Il nomme la session, sa branche et sa machine, propose de la
  rejoindre — et **n'interdit rien** : reprendre un ticket dont la session est finie est le cas
  normal, et une session éteinte ne déclenche jamais rien. Le cockpit lit la même source (raison
  « jonction ») : écran et terminal disent enfin la même chose.
- **Une question du demandeur est une QUESTION, plus une note** (RM3090, lot L1b de RM3015 ;
  NORMS 2.34.0). La moisson ne créait de `Q` qu'à partir d'un outil de question formelle : tout ce
  que Mathieu écrivait partait en note — y compris ses propres questions, qui n'étaient donc jamais
  comptées dans « ce qui n'est pas tranché ». Arbitrage consigné (RM3015-D011) : **une question
  ouverte est tout ce qui n'est pas tranché, quel qu'en soit l'auteur** ; la ligne de partage avec
  une demande n'est pas l'auteur mais la nature — une demande appelle une action, une question un
  arbitrage. Le critère est écrit **une fois**, dans `pm-think-classify` (RM3067, D023), et importé
  par le hook — qui doit rendre la main tout de suite, d'où sa version sans modèle ; la passe LLM
  reste le filet. Une question ne passe plus par le critère de la note (elle ne porte pas de dette,
  elle porte un arbitrage en attente), et `has_text_anywhere` empêche qu'un texte reclassé se
  retrouve dans deux rubriques.
- **Versions de la feuille de route, et rattachement des fonctionnalités** (RM3060) : la feuille de route
  était un tableau tenu à la main, avec un « V0 (à définir) » qui n'a jamais bougé. Les versions vivent
  maintenant dans le registre et `cdc-roadmap.md` en est **généré**, comme la liste des fonctionnalités.
  Une version est une **étape de travail** — un rôle, un critère de passage — jamais une copie de la liste :
  les fonctionnalités s'y rattachent par une colonne. Depuis le cockpit, l'onglet Feuille de route crée et
  retire les versions, la colonne Version de l'onglet Fonctionnalités y rattache une ligne. En ligne de
  commande : `--add-version`, `--set-version`, `--drop-version`. `pm-cdc-features --check` couvre désormais
  la feuille de route. Retirer une version détache les fonctionnalités, n'en supprime aucune. Cockpit 3.12.0.

- **Stores de session : une seule résolution, une seule classification, un seul journal** (RM3085,
  lot L5 de RM3015). Ce qui cassait en silence : `pm_scope` lisait le worklog par un chemin **codé
  en dur**, si bien qu'une fois `PM_SESSION_WORKLOG_DIR` posée la **garde de périmètre RM2274
  laissait tout passer** ; `karl-move-session` résolvait `KARL_AGENT_STATE_DIR` **sans son repli**
  (le symptôme de RM2391, qu'il est censé réparer) ; deux slugifications du `cwd` coexistaient, dont
  une qui perdait tout chemin contenant `_` ; sept `append_log` reconstruisaient le format du journal
  de ticket, dont deux **sans la ligne « Tokens »** — invisibles du parseur et de la feuille de temps.
  Nouveaux modules : `pm_stores` (worklog, état, transcripts, historique, tours, slug),
  `pm_task_log` (le format, écrit une fois), `pm_worklog_states` (les buckets, importés par le
  terminal ET le cockpit — `MEP` n'existait que d'un côté). `answers.jsonl`, écrit depuis RM2302 et
  jamais relu, laisse la place au journal structuré. Les logs pipe-pane sont purgés au démarrage
  (`KARL_TMUX_LOG_KEEP_DAYS`, 30 j) et le registre `var/sessions` est borné (`PM_SESSIONS_INDEX_KEEP`).
- **Commandes de moniteur tmux masquables** (RM3094) : `monpreset`, ➕/✕ Moniteur et la disposition
  des panes sont regroupés dans un bloc de la barre du terminal, qu'une case de Réglages ▸ Thème &
  affichage montre ou masque à chaud. Affichées par défaut (masquer d'office changerait le
  comportement d'une instance sans le dire) ; masquées, les gestes restent câblés et les panes
  ouverts ne bougent pas. Le bloc est en `display: contents` : la barre garde exactement le même
  espacement qu'avant quand il est visible.
- **Titres de session sur deux lignes** (RM3093) : dans le panneau de gauche, le titre d'une tuile
  n'est plus coupé à la première ligne — deux lignes, puis points de suspension. Les tuiles gagnent
  en hauteur (vivantes comme grises) et leurs pastilles et boutons s'alignent en haut, sinon la
  colonne danse dès qu'un titre passe à deux lignes. La jauge de contexte reste en pied de tuile. Une
  garde de `test_cockpit_runtime` refuse un retour à `nowrap`. **Corrigé à la recette** : le titre
  restait un item de la ligne, coincé entre le slug et les boutons, si bien que sa seconde ligne se
  coupait alors qu'il restait de la place sous le slug et sous les boutons. Il occupe désormais une
  **rangée à lui, sur toute la largeur** de la tuile (`flex-wrap` + `order`) ; le slug rapetisse, le
  titre respire (`line-height` 1.5), et la pastille de gauche se centre sur la première ligne du
  titre au lieu de se coller au bord haut.
- **Fenêtre de contexte : le maximum du modèle** (RM3084, correctif de RM2611/RM3082) : une session
  Opus 5 à 197 k était rapportée à une fenêtre de 200 k — **99 %**, en rouge — alors qu'elle en est à
  **20 %** de sa vraie fenêtre de 1 M. `modelWindow` retenait la plus petite valeur et *devinait* la
  variante 1M seulement une fois les 200 k dépassés, si bien que le pourcentage sautait en cours de
  session. Il retient désormais **le plus grand** entre la fenêtre configurée (`context_window`,
  ajouté dans `pm.pricing.yml`) et celle que la table connaît de la famille ; un modèle inconnu
  n'affiche toujours aucun pourcentage. Corrige du même coup l'encart **infos** et la jauge des
  tuiles, qui partagent cette fonction. Et le **contexte apparaît au survol de la tuile**, quel qu'il
  soit : `contexte : 197k / 1M (20 %) · opus-5`.
- **Onglet MR du worklog** (RM3074) : les merge requests de la session quittent le bandeau de tête
  pour un **sous-onglet dédié**, groupées par étape du cycle — à merger dans l'intégration · mergées,
  **à promouvoir en production** · promues. Ce groupe du milieu ne s'affichait nulle part : le worklog
  ne listait que les MR ouvertes, si bien qu'« aucune MR » et « mergée, pas encore en production » se
  confondaient. Chaque ligne montre le ticket (cliquable), le **dépôt**, `source → cible`, l'**état**,
  l'**âge** et le bouton merger quand il a un sens. La tête ne garde qu'un rappel d'une ligne, qui
  mène à l'onglet. Le compteur ne compte que ce qui appelle un geste. La branche d'intégration vient
  de la configuration du projet, servie au front avec le bloc worklog — plus de « dev » supposé.
- **Repères d'aide « ? » sur les zones du cockpit** (RM3075) : une case dans Réglages ▸ Thème &
  affichage pose un **?** discret sur douze zones (liste des sessions, worklog, onglets de droite,
  composer, CDC, journal, panneaux de tickets…). Au survol, une phrase dit à quoi la zone **sert** ;
  au clic, sa page d'aide s'ouvre, **à la bonne section**. Un registre unique
  (`src/modules/doc/helpSpots.js`) porte zone → phrase → page → ancre, et une garde de test lit les
  vrais `help/*.md` : un repère qui pointerait une page ou une section disparue casse la suite.
  Affichés par défaut, décochables (préférence de ce navigateur), reposés après les rendus.
  `help/40-worklog.md` présente désormais le worklog comme **le tableau de bord de la session**,
  zone par zone. `core/dom.js` gagne `prepend`, symétrique d'`append`.
- **Jauge de contexte par session** (RM3082) : sous chaque tuile de la liste de gauche, une barre
  fine et un pourcentage disent l'occupation de la fenêtre du modèle, **à partir du premier palier
  seulement** (50 / 75 / 90 % par défaut, réglables dans Réglages ▸ Sessions). Le franchissement d'un
  palier pulse trois fois puis se tait — pas de couleur de fond qui oscille : la tuile en porte déjà
  une, et une animation permanente cesse d'être vue. Au palier rouge, la session rejoint le bandeau
  « à traiter » avec le geste utile (consigner, repartir sur une session neuve). La donnée sort de
  `_jsonl_tail_meta` — la lecture de queue déjà faite et cachée pour le titre — et non de
  `/usage/<id>`, qui relit le transcript entier : coût marginal nul par tuile et par tick.
- **Onglets et sections dans les réglages** (RM3081) : dix cartes s'empilaient en une seule colonne, sans
  hiérarchie — on y cherchait un réglage en faisant défiler. Cinq onglets à plat, comme le menu CDC :
  Instance, Fournisseurs, Moteurs, Affichage, Compte. Chaque carte reste une section avec son titre ; un
  onglet dont toutes les cartes sont masquées ne s'affiche pas, et le dernier ouvert est retenu par ce
  navigateur. **Le contenu ne se charge qu'à l'ouverture de son onglet** : ouvrir les réglages pour
  changer le thème n'interroge plus npm pour inventorier les moteurs. Cockpit 3.11.0.

- **Zone centrale : le split devient une OPTION** (RM3051) : ouvrir un ticket ou un document
  coupait la zone centrale en deux (session en haut, fiche en bas) — comportement que
  personne n'avait demandé. Désormais, par défaut, la fiche **prend la place** de la session
  le temps de la consultation, et celle-ci **revient à l'identique** à la fermeture (ce qui
  était masqué le reste). Le split se réactive dans **🔧 réglages → Thème & affichage**, avec
  une **poignée** pour régler la hauteur (double-clic : défaut) ; hauteur bornée et mémorisée
  par navigateur. La bascule marche **à chaud**, ticket ouvert.

- **Le pont session → `.think.md` écrit vraiment** (RM3076, correctif de RM3053) : `_think_note()`
  appelait `pm_git.autocommit` sans que `pm_git` soit importé ; son `except` transformait la
  `NameError` en avertissement console, et aucune demande (`request --ticket`) ni notification
  (`notify --ref`) n'atteignait jamais le think du ticket. Import posé, échec désormais journalisé
  (`pm_log`, catégorie `worklog`) en plus de l'avertissement, et `test_pm_session_status_think.py`
  verrouille les deux chemins — plus un contrôle qui voit un nom non résolvable sans jouer le code.
  Au passage, trois tests du think (`test_pm_think`, `test_pm_think_classify`,
  `test_karl_agent_providers`) exigeaient le `.env` du dépôt : verts dans le core qui le porte,
  **rouges dans tout worktree de dev**. Ils posent maintenant le core jetable de `test_support`
  avant d'importer un module PM — la suite est identique des deux côtés (179 verts).
- **Le runtime NORMS se génère par un fournisseur, et se contrôle** (RM3073) : `norms/runtime/` portait
  « Généré ⇒ ne pas éditer » alors qu'aucun générateur n'existait — écrit une fois à la main, il se
  désynchronisait de ses sources en silence. `mmi-pm norms-runtime` le produit par l'API d'un fournisseur
  du registre (`--build`), le compare (`--diff`) et ne remplace qu'au `--apply`. Le contrôle de non-perte
  se fait par **ancres** — noms de scripts, options, chemins, statuts, champs — qu'une réécriture dense
  n'a pas le droit de changer, et porte sur le corpus, pas fichier par fichier. `mmi-pm norms-runtime
  --check` mesure : le runtime actuel garde 238 de ses 273 ancres, 35 sont perdues. `pm_llm_call` parle
  aux trois dialectes (OpenAI, Ollama, Anthropic) pour tout le système, la clé restant lue du `.env`.

- **Fournisseurs LLM prédéfinis, et modèles demandés au fournisseur** (RM3072) : déclarer un modèle de
  travail demandait de retrouver l'URL d'une API et de savoir quel dialecte elle parle. Dix-sept services
  connus sont maintenant proposés à la création — OpenRouter, Z.ai, Groq, DeepSeek, Mistral, Together,
  Fireworks, Cerebras, xAI, Gemini, OpenAI, Anthropic, Ollama Cloud, et les locaux Ollama, Lemonade,
  LM Studio, vLLM. Le choix pose le type et l'URL, il ne reste que la clé. Aucune liste de modèles n'est
  écrite dans le code : `mmi-pm llm-models` (et le bouton du panneau) interroge le fournisseur et rend ce
  qu'il sert vraiment. La clé n'entre jamais dans une commande ni dans le navigateur. Cockpit 3.10.0.

- **Le KERNEL NORMS revient après une compaction** (RM3071) : une compaction garde la tâche et perd les
  normes ; l'agent continuait avec le souvenir qu'il avait des garde-fous. `mmi-pm norms-recall` rend le
  KERNEL à réinjecter (la version dense de `norms/runtime/` si elle existe, la source sinon), et il est
  câblé dans le bloc de hooks canonique sur `SessionStart` `compact|resume` — donc posé à l'installation,
  re-posé à chaque `pm-core-update`, et vu par `pm-claude-hooks-sync --check`. Sa sortie n'est pas silencée :
  c'est elle, le rappel. Sans KERNEL trouvable, il se tait et rend 0 plutôt que de casser la reprise.
- **Moteurs : deux portées d'installation** (RM3069) : « pour moi » (dans le home, sans privilège) et
  « pour tous » (sudo, administrateur). La détection ne se limite plus au PATH du démon — Claude Code,
  opencode et vibe étaient déclarés absents alors qu'ils sont installés chez le développeur. Le panneau dit
  où l'outil est posé et pour qui. Cockpit 3.9.1.

- **`pm-core-update` provisionne aussi l'utilisateur de l'instance** (RM3054) : étape 7 — hooks
  Claude Code manquants posés par `pm-claude-hooks-sync` (ajout seulement) et symlinks
  `~/.claude/skills/<nom>` → `<core>/skills/<nom>` pour les skills du core (jamais d'écrasement
  d'un dossier réel ou d'un lien vers ailleurs) ; `--dry-run` montre les deux plans. Un hook ou
  un skill ajouté par un ticket est actif dès le core update suivant.
- **Envoi de TEST + lisibilité du rendu** (RM3052) : le panneau gagne un bloc **« Test
  d'envoi »** — on choisit un contact de l'annuaire (liste servie par `pending`) ou on saisit
  une adresse, et le **même** compte-rendu part là, sujet préfixé `[TEST]`, **sans rien
  écrire** : ni `sent_at`, ni `sent_to`, la file ne bouge pas. Verbe CLI
  `client-notify test <ref> --to EMAIL` et endpoint `/client-notify/test` **distincts de
  `send`** (un drapeau oublié aurait pu envoyer au client). Deux corrections de rendu au
  passage : l'échappement transformait `>` en `&gt;` et **cassait les citations markdown** ;
  et le YAML repliant les lignes du frontmatter, une énumération rédigée sur dix lignes
  revenait en **pavé d'un seul tenant** — les longues énumérations « · » repassent à la ligne,
  et `nl2br` respecte les retours à la ligne voulus.
- **Email client en HTML** (RM3052) : le protocole de test d'un ticket est du markdown à
  **tableaux** — recopié dans un corps texte, il arrivait en bouillie chez le client. L'email
  part désormais en **multipart** : le texte reste le repli, et la partie **HTML** rend les
  tableaux comme des tableaux (titres, listes, citations aussi ; `[x]`/`[ ]` deviennent ✔/☐).
  Styles **en ligne** (les clients mail jettent les feuilles `<style>`), markdown source
  **échappé** (aucun HTML brut ne traverse). Dans le panneau, l'aperçu n'est plus du texte
  préformaté mais **l'email rendu**, dans une iframe cloisonnée. `karl-mail-send` gagne
  `--html-file` (alternative HTML) — utilisable par tout autre envoi.
- **Panneau « compte-rendu client » au cockpit** (RM3052) : un menu **✉ compte-rendu** au
  bandeau, dont le badge compte les évolutions livrées **pas encore annoncées** ; le clic
  déroule **un client par ligne avec son reste à annoncer** (`Calicote (5)`), et ouvre au
  centre la page du client — ses tickets **groupés par projet** mais **cochables en travers
  des projets** (un compte-rendu peut couvrir plusieurs projets), l'**aperçu de l'email**
  produit par le serveur (ce qu'on relit est ce qui part), puis **Envoyer** ou **Écarter**,
  chacun **en deux clics**. Côté outillage : `client-notify pending [client] [--json]` (la
  file groupée par client), périmètre **client** accepté par `preview|send|dismiss`
  (`calicote` = tous ses projets) et sélection `--rm` qui traverse les projets ; l'email
  d'un client multi-projets est **un seul** email groupé par projet. Quatre endpoints
  (`/client-notify/pending|preview|send|dismiss`) qui délèguent au même script que la CLI.
  Verbe **`client-notify queue <ref> --rm ID`** pour (re)mettre des tickets en file quand elle
  doit être reformée à la main (envoi échoué, annonce à refaire, recette) — refuse un ticket
  qui n'est pas en `en_mep` sauf `--force`. Au passage, **correctif** : le balayage de
  `tasks/RM*.md` prenait aussi les **frères** d'une fiche (`.log.md`, `.think.md`) — un journal
  qui *parle* de `client_notify` se présentait comme un ticket sans statut.
- **Notif client : protocole de test OPTIONNEL** (RM3052) : l'email client réinclut le
  **protocole de test de chaque ticket** (« comment le vérifier »), pilotable par projet via
  `notif_client_mep.protocole` (**défaut : true**) et surchargeable pour un envoi donné
  (`client-notify preview|send --avec-protocole | --sans-protocole`) ; réglable avec
  `client-notify config <projet> --protocole true|false`.

- **Notif client : `sent_to`, `dismiss`** (RM3052, socle du panneau compte-rendu) : à l'envoi,
  `client_notify.sent_to` consigne **à qui** le client a été notifié (pas seulement quand) ;
  nouveau verbe `mmi-pm client-notify dismiss <projet> [--rm ID]` pour **écarter** des tickets
  de la file **sans** email (tout n'a pas à être annoncé) — `dismissed_at` posé, `is_pending`
  l'exclut, et un redéploiement les remet en file proprement.

- **Menu CDC en haut = le seul CDC de PM** (RM3049) : le menu CDC en haut du cockpit affiche
  **uniquement** le CDC du projet propre de l'instance (`pm-ai-agents`) — plus de liste ni de
  sélecteur multi-projets (AtomBox et les autres n'y apparaissent plus). `op_cdc_list` ne
  renvoie que le CDC de ce projet (dérivé du `contacts_dir`) ; comme il n'y en a qu'un, le
  front l'ouvre directement (pas de sélecteur). Les CDC des autres projets restent accessibles
  depuis le panneau « projets » (par projet), jamais depuis ce menu global.

- **Notification client à la MEP** (RM3026) : quand des tickets passent en `en_mep`, un
  projet ayant l'option `notif_client_mep` (actif + contacts d'annuaire) met ses tickets
  en FILE ; `mmi-pm client-notify {config,list,preview,send}` agrège la file en **UN** email
  récap (par projet, pas un par déploiement) — sujet au nom lisible du projet, « ce qui
  change » = critères d'acceptation, sans le protocole de test interne — envoyé aux contacts
  client (via `karl-mail-send`, jamais sans OK humain), puis vide la file (`sent_at`). Un
  contact à plusieurs emails les notifie tous. Le **cockpit** signale la file par une alerte
  `client_notify` (✉️) « N évolution(s) en prod à notifier au client », par projet, datée de
  la plus ancienne en file.

- **Fichier de réflexion par ticket et fusion vers le projet** (RM3015, RM3053, NORMS 2.26.0) :
  chaque fiche a un frère `RM<id>_<slug>.think.md` — notes verbatim (N), questions (Q),
  décisions/conseils (D/C), fonctionnalités (F), états ✅ ❌ 🟡 🕐 ⏸ — matière de travail hors
  wiki, à côté du `.log.md` (événements) ; la fiche ne porte que des compteurs (`think:`).
  `pm-task-think` (ajout normé, `--set/--state`, `--show`), `pm-think-merge` (régénère
  `docs/cdc-questions.md`, `cdc-decisions.md`, `cdc-features.md`, `cdc-notes.md` entre marqueurs,
  ids `RM<id>-Xnnn`, crée `cdc.md`/`cdc-roadmap.md`/`cdc-help.md`, `--check`, `--rename-legacy`
  pour les anciens `cdc-<prefix>-NN-*.md`), `pm-think-harvest` (hook Stop/SessionEnd : questions,
  réponses et demandes du transcript → think, dédoublonné). `pm-decisions persist`,
  `pm-session-status request --ticket` / `notify --ref` écrivent dans le think ; `pm-task-brief`,
  `pm-task-show` le résument ; `pm-task-status-update … ferme` refuse avec une Q ouverte
  (`--ignore-think`). Sweep `is_task_sheet()` (`pm_think`) sur les 20 scripts qui prenaient un
  frère pour la fiche (leçon RM2362) ; `pm-task-move` déplace le think ; `karl-agent` sert le
  CDC générique (`cdc.md`, registre `docs/cdc/`) en plus de la forme par préfixe. Skill `mmi-pm-think`.
- **Reprise d'une session qui a changé de cwd** (RM3057) : `_resume_cwd` parcourt aussi
  les `cwd` du transcript depuis le début (le cwd de création nomme le dossier du
  `.jsonl`) quand ni le store ni la queue n'ont le bon slug, et **répare le store**
  (`cwd_before_fix` conservé, journal `session`/warn). Avant : `claude --resume` relancé
  dans le sous-dossier → « No conversation found » → 502 (session atombox).
- **Installer les moteurs depuis le cockpit** (RM3069, cockpit 3.9.0) : panneau 🧩 Moteurs —
  moteurs de session (Claude Code, opencode, Mistral vibe) et serveurs de modèles (Ollama,
  Lemonade), avec version installée, version disponible, état du service et sessions en cours.
  Le cockpit n'envoie qu'un **identifiant de recette** : les commandes vivent dans
  `pm_engine_recipes`, la commande exacte est affichée avant d'agir, l'installation est système
  (sudo, administrateur), et une mise à jour est refusée tant que des sessions tournent dessus.
- **Fournisseurs configurables depuis les réglages** (RM3068, cockpit 3.8.0) : catalogue de
  16 types sur 5 axes (Redmine · GitLab, Gogs, GitHub · doc · coffres · modèles de travail),
  déclaration écrite dans `pm.config.local.yml` (le fichier commenté n'est jamais réécrit),
  **clés en écriture seule** — `pm-provider-secret` les pose par l'entrée standard, aucune route
  ne les relit, le journal ne garde que le fait — et vue des **affectations par projet**, où le
  rôle appartient au couple projet ↔ instance. `.env` du dev connecté, `.env` global ou d'un autre
  dev par sudo pour un administrateur.
- **Logo karl** (RM3065, 3.7.7) : le K filaire qui relie une note, une page web et du code
  (variante A4) — marque dans l'en-tête et sur l'écran de connexion, favicon SVG dédié,
  sources dans `deploy/karl-agent/cockpit/logo/`.
- **Éditer le CDC depuis le cockpit** (RM3064, 3.7.6) : dans les registres fusionnés, chaque
  entrée de think a un sélecteur d'état et un ✕ (confirmé) ; dans la table des fonctionnalités,
  un sélecteur d'état qui fige l'entrée (`--set-etat`, jamais de suppression). Routes
  `POST /api/doc/cdc-think` et `/api/doc/cdc-feature`, scripts `pm-task-think --delete`,
  `pm-cdc-features --set-etat` ; registres régénérés dans la foulée.
- **En-tête du cockpit** (RM3063, 3.7.5) : le filtre « Clients » (contexte client) est masqué par
  défaut et se réaffiche par une option locale des réglages (carte 🎨 Thème & affichage) ; le bouton
  📋 CDC se place juste à droite du titre.
- **Dictionnaire des données du projet PM** (RM3061) : `pm-cdc` sait la forme générique
  (`cdc.md` ⇒ dictionnaire dans `docs/dict/`, chapitre `cdc-dict.md`, ids `RM<id>-D…` de
  pm-think-merge) ; `pm-dict-from-pm` dérive du code les tables champs (gabarits),
  énumérations et normes (KERNEL), routes (carte), composants (cockpit), actions (scripts),
  templates ; les tables entités, relations, workflows, protocoles, jalons sont curées.
  Onglet 📚 Dictionnaire dans le panneau CDC ; onglets nommés et ordonnés selon la norme
  `cdc` (cockpit 3.7.4).
- **Menu CDC à onglets et onglet projets** (RM3044, RM3045, RM3060, cockpit 3.7.3) : un seul
  bouton 📋 CDC en haut ouvre un panneau central dont les onglets, tous au même niveau,
  sont Fonctionnalités · CDC vivant puis un par chapitre (roadmap, décisions, questions,
  notes, dictionnaire…) — sur le CDC du projet en contexte ; la « feuille de route »
  dérivée du registre est retirée (redondante), la table gagne une colonne **Version**
  (`version` par entrée, `pm-cdc-features --assign-version`) ; l'onglet 📂 projets reprend
  les mêmes onglets par CDC (session attachée, sinon dernier choisi) :
  table des fonctionnalités triable/filtrable (`/api/doc/cdc-features`, registre yml →
  JSON), chapitres du CDC en sous-onglets avec ancres `D012`/`Q003` et `RM` cliquables,
  feuille de route par jalon (`jalon`, `jalons:` du registre) ou par état ; sélecteur
  quand un projet porte plusieurs CDC (`pm`, `karl`). Onglet 📂 projets de la colonne
  de droite : projets touchés par la session, raccourcis fiche / fichiers / CDC.
  `pm-cdc-features` : registre curé par capacité (`--init --no-sync`, `tickets: […]`,
  `jalon`). Modules `cdc/` et `sessproj/`.
- **CDC vivant du projet et menu 📋 CDC** (RM3043) : `pm-cdc-features` (registre
  `docs/cdc-<prefix>/fonctionnalites.yml` dérivé des tickets, ids `F` stables, chapitre 10
  généré, `--check`) ; docs `cdc-pm-00/10/90/91/99` du projet PM (fonctionnalités reprises
  des 660 tickets, décisions, vrac, questions) ; route `/api/doc/cdc` + bouton d'en-tête du
  cockpit (3.6.0) qui ouvre le sommaire dans la modale doc, liens entre chapitres navigables ;
  règle « au fil de l'eau » dans CLAUDE.md et NORMS `governance` (2.24.0).

### RM3014 — Cockpit : docs du projet par projet:file, plus d'alias confondu (2026-09-07)
- **Correctif** : l'explorateur de fichiers ne pouvait plus ouvrir aucun fichier (« chemin hors de projects/ ») — depuis L7 (RM2889), `/fs/file` et `/file` partageaient la cible `/api/file/file`, résolue côté serveur vers la seule route générique. `/fs/file` a désormais sa cible `/api/file/read` (`MIGRATION-ROUTES.tsv` régénérée : `endpoints.js` + `karl_api_routes.py`).
- **Racines documentaires par projet:file** : une racine `docs/` ou `project/` se désigne par `doc:<client>/<projet>/<racine>` — le cockpit ne reçoit, n'affiche et n'envoie plus de chemin absolu pour la documentation (infobulle « client/projet · docs », URL, journal du démon) ; la résolution du chemin réel est serveur (`_doc_root_path`), avec les gardes existantes (projet du périmètre, racine connue, sous-chemin confiné). Les chemins absolus restent acceptés pour les clients historiques.
- Tests : `test_karl_agent_fs.py` (alias, identifiants, gardes, portées session/projet, symlink), `test_cockpit_files.js` (routes distinctes, identifiant → portée, infobulle et URL sans chemin).
### Travaux périodiques
- **L'instance PM n'a plus qu'un seul cron** (RM2792, lot 1). Les travaux périodiques
  étaient une ligne de crontab chacun — orchestrateur toutes les 15 min, `pm-task-report`
  toutes les 30, wiki-sync toutes les 10, summarizer et veille tarifaire quotidiens, GC des
  verrous horaire. Le problème n'était pas leur nombre : c'est que le crontab ne sait rien
  faire de ce dont ils ont besoin. Il ne **garde aucun état** — « c'est passé quand, et ça
  s'est bien passé ? » n'avait de réponse qu'en fouillant des journaux séparés, quand ils
  existaient. Il ne **verrouille rien** : cron relance un job même si le précédent tourne
  encore, et deux orchestrateurs concurrents s'assignent les mêmes tâches. Et il
  n'**inventorie rien** — en vérifiant, la moitié de ces jobs n'étaient installés nulle
  part : seulement décrits dans `cron.example.sh`, un fichier que personne ne relit.
  Désormais le registre est **`jobs.reference.yml`** (11 travaux déclarés, avec pour chacun
  ce qu'on perd s'il ne tourne pas, et le motif écrit pour les deux qui sont désactivés), et
  **`pm-scheduler.py`** décide de ce qui est dû, sous verrou, avec un état, une trace et un
  journal par travail. Le crontab tient en une ligne, que `pm-scheduler crontab` imprime
  déjà remplie. Trois comportements méritent d'être connus, tous les trois délibérés : un
  job **jamais vu est armé, pas exécuté** — sinon ajouter un job quotidien au registre à
  15 h le lancerait aussitôt, au titre de l'occurrence de 6 h déjà passée ; **pas de
  rattrapage en cascade** — machine éteinte trois jours, un job quotidien tourne une fois,
  pas trois, parce que rejouer trois fois un résumé quotidien ne rend pas trois jours de
  travail ; et **pas de recouvrement** — un job encore en cours est tracé « déjà en cours »
  plutôt que doublé, ce qui était précisément le défaut du cron nu. Un job qui échoue ou qui
  dépasse son `timeout` n'empêche jamais les autres, et le passage sort en code ≠ 0 pour que
  l'échec reste visible. Premier bénéficiaire concret : le **réveil des tickets récurrents**
  de RM2772, qui n'avait jusque-là aucun moyen de tourner tout seul. Le parseur cron est
  maison et testé pour de bon (66 cas) : le champ `*` en jour-de-semaine s'y était fait
  normaliser « 7 % 7 = 0 » à l'écriture, ce qui ne laissait passer que le dimanche — une
  panne qu'aucune exécution ponctuelle ne révèle, et que seul un test étalé sur plusieurs
  jours attrape. NORMS 2.15.0 → 2.17.0 (module `scheduler`, hors précharge, + déclencheur).

### Outillage PM
- **La machine est enfin sauvegardée — et la sauvegarde est surveillée** (RM3023).
  `zfs/root/home` n'avait **qu'un seul snapshot, du 17 avril 2025**, et la machine aucune
  sauvegarde externe : ni borg, ni restic, ni rsnapshot, ni rclone configuré, ni ligne cron.
  C'est ce qui a rendu 42 transcripts de session **définitivement** irrécupérables (RM2997) —
  il n'existait aucun recours au niveau du système de fichiers. `pm-zfs-backup.py` prend des
  snapshots par seaux (24 horaires, 14 quotidiens, 8 hebdomadaires, 6 mensuels) sur
  `zfs/root`, `zfs/workspaces`, `zfs/lxc/dev` et `zfs/documents` — la politique tient dans une
  section de `pm.config.yml`, parce que le périmètre d'une machine n'est pas celui d'une autre.
  **Aucun timer dédié** : le tick se greffe sur le cron `pm-task-report`, qui tourne déjà toutes
  les 30 min sur l'hôte, seul endroit où `zfs` existe ; sur un portable un horaire fixe
  manquerait la moitié de ses créneaux, et la question utile est « le dernier snapshot a-t-il
  plus d'une heure ? ». **Aucun droit nouveau** non plus : tout passe par `pm-zfs-snap.sh`, le
  guichet sudo NOPASSWD déjà en place, root-owned, dont le périmètre est élargi — ses deux
  gardes (charset du nom, et `destroy` qui ne peut viser qu'un `dataset@snapshot`, jamais un
  dataset nu) sont ce qui rend l'élargissement tenable. La purge a ses propres gardes : elle ne
  touche que les noms `pm-auto-…` — un snapshot posé à la main est un point de restauration
  délibéré — et un seau retiré de la config n'est pas purgé, sinon éditer une ligne effacerait
  son historique en silence. Enfin la surveillance, qui est le vrai enjeu : le tick tourne sur
  l'hôte, le contrôle dans le conteneur, et ils ne se voient que par une empreinte posée sur le
  montage partagé — `_envchk_zfs_backup` distingue *jamais tourné*, *a décroché* et *tourne
  mais échoue*. **Ce que ça ne protège pas** : un snapshot vit sur le même disque, et la
  machine est un portable — la réplication hors machine reste à faire.
- **Le budget de contexte se regarde, il ne se ticketise plus** (RM3046). Le préchargement des
  rôles grossit à chaque module ajouté aux normes : `pm-context-budget --check` est passé au rouge,
  et avec lui `pm-norms-doctor` et deux tests de la suite. Le réflexe — ouvrir un ticket à chaque
  dépassement — encombre le backlog sans faire baisser un chiffre, et un contrôle rouge en
  permanence cesse d'être lu. L'indicateur vit désormais là où on le regarde vraiment : une ligne
  **« budget de contexte »** dans la santé du poste (famille **PM**), qui nomme les rôles au-dessus
  du plafond et donne la remédiation (alléger le préchargement, en-tête « Préchargé par » des
  modules). Le niveau est **`warn`, jamais `error`** : rien n'est cassé, une session coûte
  simplement plus cher qu'annoncé — et la famille PM est volontairement hors des familles à badge,
  pour qu'un chiffre qui bouge tous les jours ne clignote pas. La mesure se fait à la volée
  (`pm-context-budget --json`, un comptage d'octets sur des fichiers locaux) : pas de service, pas
  de timer, pas de fichier d'état de plus.
- **Par quel bout prendre un travail, et comment mener un CDC complet** (RM2967). Le système
  savait traiter un ticket dans le moindre détail, et ne disait **nulle part** comment attaquer
  un projet neuf, une reprise d'existant ou une migration — chacun repartait de sa mémoire, et
  la faute la plus chère n'est pas de mal coder mais de traiter en ticket ce qui demandait un
  CDC, ou l'inverse. Deux modules de normes le posent. `methodes-travail` reconnaît **quatre
  natures** et leur protocole d'entrée, et distingue le **CDC de ticket** — la proposition
  d'implémentation, forme la plus employée du parc — du **CDC de projet**. `cdc` normalise la
  méthode éprouvée sur un CDC réel (140 décisions, 124 fonctionnalités, un POC qui lit le CDC),
  corrigée par la relecture de sept CDC du parc : trois livrables qui avancent ensemble
  (chapitres numérotés + POC + dictionnaire en YAML), les identifiants stables à trois chiffres,
  les sept temps, la grille 360° et les cinq postures, et le principe qui commande le reste —
  *quand le langage et le SGBD sont statués, coder doit être une formalité*. La relecture a
  ajouté au cas fondateur ce qui lui manquait : la **provenance** en section propre (ce qui vient
  du demandeur, ce que le document infère), le hors-périmètre motivé, **ce qu'on voudra
  observer** décidé avant de construire, les mesures **datées**, le chiffrage, et des critères
  d'acceptation du CDC lui-même. La part mécanique est outillée par `pm-cdc.py` (`init` copie les
  gabarits de `templates/cdc/`, `dict` génère le chapitre dictionnaire depuis les YAML, `index`
  en extrait le registre pour le POC) et surtout par `check`, **le harnais qui teste le CDC** :
  il casse sur une décision citée qui n'existe pas, une décision rédigée mais absente du tableau
  de synthèse (donc invisible de tout ce qui lit l'index — c'est ce contrôle qui a trouvé la
  première), un cycle de dépendances, une fonctionnalité qui dépend d'un **jalon ultérieur**
  (déplacer une fonctionnalité fait alors apparaître tout ce qui doit bouger avec elle), une
  fonctionnalité écartée dont une autre dépend encore — écarter est une **suppression en
  cascade**, portée par le test plutôt que par un dialogue qu'on cliquerait sans lire —, un
  jalon vide, un état hors de l'échelle, un **domaine réel** dans un CDC. Rejoué sur le CDC
  fondateur, il reproduit son chapitre dictionnaire à l'identique depuis les mêmes YAML (la
  preuve qu'il est générique) et trouve trois fuites de domaines réels. Les avertissements d'une
  même famille tiennent sur **une ligne** : crier soixante fois, c'est ne plus être lu. Les deux
  modules sont hors précharge — +113 tokens au KERNEL, rien de plus.
- **Le PM sait faire naître un dépôt sur GitHub, pas seulement sur GitLab** (RM3016). Le registre
  `providers` déclarait GitHub depuis longtemps et `pm_forge` savait y ouvrir des PR, mais
  `pm-repo-new` ne savait créer que des projets GitLab : miroiter un dépôt sur GitHub restait un
  geste manuel — création à la souris, remote posé à la main, branches poussées en vrac. La
  première demande réelle (miroir d'un projet, `main` et `dev` seulement) a montré ce que le geste
  manuel coûte : trois différences de fond entre les deux forges, invisibles tant qu'on n'écrit
  pas le script. L'owner d'un dépôt GitHub est soit une **organisation**, soit un **utilisateur**,
  et l'API n'est pas la même (`POST /orgs/{org}/repos` contre `POST /user/repos`) : `pm-repo-new`
  le résout **par lecture**, jamais par convention de nom. GitHub prend pour branche par défaut
  **la première reçue** : elle est donc fixée explicitement *après* le push, sinon un dépôt dont
  on pousse `dev` puis `main` s'ouvre sur `dev`. Et la **protection de branche n'existe pas sur
  les dépôts privés d'un plan gratuit** : l'échec est un avertissement, pas une erreur — refuser
  la création parce que la forge ne sait pas protéger reviendrait à ne rien livrer. `--branches`
  pousse la liste choisie et elle seule (les branches de ticket restent chez soi), `--remote`
  nomme le remote pour que `origin` (GitLab) reste intact, et le remote posé est l'**alias
  canonique** `github:owner/repo.git` — jamais une URL HTTPS avec jeton (RM2328). Le jeton se
  résout **par organisation** — `GITHUB__<OWNER>__TOKEN`, sinon `GITHUB__<INSTANCE>__TOKEN`,
  sinon `GITHUB_TOKEN` — d'abord dans le `.env` utilisateur (identité par dev, RM2497) : un même
  poste travaille pour plusieurs organisations sans jamais mélanger les jetons.
  `deploy/karl-agent/git-credential-pm-github` le sert à `git` (avec
  `credential.…useHttpPath true`, sans quoi le helper ne reçoit pas le chemin et donc pas
  l'organisation), le secret ne transitant ni par un fichier de conf git ni par un remote URL.
  Piège rencontré au premier usage, et qui vaut d'être su : un jeton *fine-grained* qui lit tout
  peut n'avoir **aucun droit d'écriture** — l'API répond juste, et seul `git push` échoue en
  « Permission denied ». La sonde fiable est un `POST` d'écriture inoffensif (créer un blob) :
  403 ⇒ jeton en lecture seule, à corriger côté GitHub (permission *Contents* en écriture).
- **Un annuaire de contacts, indépendant des clients** (RM2703). Un contact vivait dans le
  `meta.yml` de SON client : une personne présente chez vingt clients s'écrivait vingt fois,
  et divergeait vingt fois. Le relevé le montrait sans appel — **31 contacts sur 21 clients,
  dont 19 lignes pour la même personne**, en deux orthographes, marquée « interne » sur 2 de
  ces 19. Ce n'était pas de la négligence de saisie mais la forme qui l'imposait. Désormais
  **l'identité** (nom, adresses, téléphones, `internal`, compte Redmine) vit dans une fiche
  unique, `contacts/<ref>.yml` ; **la relation** (rôle, titre) reste chez le client, sous la
  forme d'un `ref` — parce que le rôle n'existe que dans la relation et qu'un `meta.yml` doit
  rester lisible seul. `pm-contact.py` ajoute, cherche, fusionne (en réaiguillant les clients
  concernés, sinon la moitié du travail resterait à faire) et **migre** : sur le parc réel,
  31 lignes → **12 personnes**, en dry-run avec rapport avant toute écriture. La clé est un
  slug lisible (`moulin-mathieu`) qui se lit dans un diff, avec repli sur l'adresse pour une
  boîte fonctionnelle. Les deux formes cohabitent le temps de la migration : `pm-client-contact`
  et le routage mail (RM2669) lisent les `ref` **et** les contacts en ligne, et une `ref` dont
  la fiche a disparu se signale au lieu de disparaître. Effet de bord acquis : le routage
  retrouve maintenant une personne par **n'importe laquelle** de ses adresses. L'annuaire ne
  vit ni dans le dépôt de code (miroir GitHub public, données personnelles) ni à la racine de
  `projects_root` (qu'aucun dépôt ne versionne), mais dans le dépôt de données, privé.
- **Les sessions Claude sont archivées toutes les heures, et l'archivage est surveillé**
  (RM2997). `~/.claude/projects` était déjà un dépôt git avec un remote GitLab, mais
  l'archivage était un **geste manuel** : le 2026-06-23 à 03:17, un git interrompu y a laissé
  un `.git/index.lock`, et pendant **75 jours** chaque tentative a échoué dessus — aucun cron,
  aucun log, aucune alerte, donc aucun signal. Pendant ce temps la rétention par défaut de
  Claude Code (`cleanupPeriodDays`, 30 jours, absente du `settings.json`) effaçait les
  transcripts au fil de l'eau : **42 perdus**, dont dépendaient 70 tickets encore ouverts.
  `pm-sessions-archive.py` commite et pousse toutes les heures (timer systemd `--user`), lève
  un verrou **mort** — plus vieux que 15 min *et* aucun git vivant dans le dépôt, les deux
  conditions étant nécessaires : lever celui d'un git en cours corromprait l'index — et le met
  de côté plutôt que de le détruire. Il archive aussi `history.jsonl` et les worklogs, sous
  `_meta/` à une profondeur qui ne les fasse pas passer pour des transcripts (le moteur
  énumère `*/*.jsonl`, profondeur deux). Invariant central : **aucune suppression n'est jamais
  consignée** — un transcript déjà effacé garde son blob atteignable, ce qui a permis d'en
  récupérer 313. La surveillance manquante est le vrai livrable : `--check` distingue trois
  pannes (pas de dépôt, plus de commit depuis trop longtemps, commits non poussés) et alimente
  un contrôle d'environnement karl-agent en niveau `error` — ce qui est perdu ici ne se
  rattrape pas.
- **Reprendre un ticket sans sa session** (RM2998). Jusqu'ici, retrouver le fil d'un travail
  interrompu passait par la reprise de la conversation — et c'est précisément ce qui a manqué
  quand 42 transcripts ont été effacés (RM2997), laissant 70 tickets ouverts sans leur
  réflexion. `pm-task-brief <id> --reprise` ne résume plus, il **rassemble** ce qui a été écrit
  ailleurs et qui subsiste : les **séances** qui ont touché le ticket, avec **la prochaine étape
  qui y était notée** — mise en tête, c'est ce qu'on cherche en premier ; les **demandes**
  retrouvées dans `history.jsonl`, que le nettoyage de Claude Code n'atteint pas ; l'état
  **constaté** du code — la branche existe-t-elle encore, porte-t-elle des commits non fusionnés,
  le worktree est-il sale — plutôt que ce que raconte un frontmatter figé à la prise du ticket ;
  et le journal débarrassé de sa plomberie (sur un ticket réel, 33 entrées de ticks et d'accusés
  Redmine écartées sur 49 — les garder noyait les cinq lignes utiles). Une séance dont le
  transcript survit propose sa commande de reprise ; une séance perdue renvoie vers sa
  reconstitution. `--prompts-all` lève le filtre sur le numéro, parce qu'une demande parle du
  sujet et rarement du ticket. Le brief d'onboarding, lui, reste strictement inchangé : 30 lignes,
  mêmes clés JSON.
- **Le code du PM a une licence : GPL-3.0-or-later** (RM3029). Le repo, pourtant miroité en
  public sur GitHub, n'avait ni `LICENSE` ni mention de copyright — au sens du droit d'auteur,
  personne n'avait le droit de l'utiliser. Décision iProspective du 2026-09-07 : GPL v3 ou
  ultérieure. `LICENSE` (texte intégral) à la racine, section « Licence » du README (ce que
  cela implique pour les modules), `license` du `package.json` du tooling, provenance des
  vendors complétée (xterm.js MIT, compatible), norme de gouvernance : toute contribution est
  faite sous cette licence, toute dépendance doit lui être compatible. Les données de projets
  (dépôt privé) ne sont pas couvertes.
- **Cinq domaines du cockpit repassent sous 15 000 tokens à lire pour modifier une vue**
  (RM3017 sets, RM3018 sessions, RM3019 worklog, RM3020 center, RM3021 meta). La mesure de RM3008
  montrait que le premier poste était le fichier de test, monolithique par domaine. Chacun est
  scindé par couche — helpers (faux DOM et fixtures partagés), modèle et service, ViewModels et
  vues, contrôleur — et chaque fichier s'exécute seul. La garde de `cockpit-view-cost.py` porte
  désormais sur le coût « vue » (ViewModel + vue + contrôleur + leurs tests), l'objectif réel de
  RM2889, et compte les tests scindés ; les cinq domaines sont sous le seuil.
- **Les chemins historiques de karl-agent sont comptés avant d'être retirés** (RM3004, étape 1).
  Le front parle `/api/<type>/<action>` depuis la 3.0.0 ; les chemins historiques restent servis
  par un alias généré pour les autres clients. Chaque appel direct d'un chemin historique est
  désormais compté et journalisé (catégorie `api` : info à la première occurrence par chemin et
  client, puis une fois par heure) ; `GET /api/log/historical` donne les compteurs et la sorte de
  client depuis le démarrage. Les appelants connus sont basculés (`karl-ttyd-auth.py`,
  `karl-voice-setup.sh`, exemples de la doc). Zéro appel pendant une semaine ⇒ retrait de l'alias.
- **Un seul `mmi-pm`** (RM3033). Deux outils portaient le nom : `bin/mmi-pm` (bash, provisioning
  `<nom> <verbe>`, porte sudo) et `scripts/mmi-pm.py` (dispatcher `mmi-pm <cmd>` → `pm-<cmd>.py`,
  dans le PATH) — et aucun ne connaissait l'autre : `mmi-pm core update` en PATH répondait
  « sous-commande inconnue », la moitié du bash ne faisait que ré-exécuter des `pm-*.py` déjà
  atteignables. La logique bash est portée en python sous la convention des 90 autres scripts :
  `pm-core-update.py` (agent SSH éphémère, pull, `core-lock`, hooks du core, redémarrage de
  karl-agent, co-déploiement du helper — et il **se ré-exécute en sudo lui-même**, mot de passe
  demandé, sauf `--dry-run`), `pm-index-add|remove|rebuild|list.py`, `pm-env-vhost.py`. Le
  dispatcher gagne le repli `<nom> <verbe>` → `pm-<nom>-<verbe>` (l'ancienne grammaire reste
  valide) et les alias par nom d'appel : `mmi-core update`, `mmi-task show 42` (liens
  `/usr/local/bin/mmi-<domaine>` posés par `core-update`). `bin/mmi-pm` n'est plus qu'une
  coquille de transition.
- **Un projet, un dépôt, naissent avec leur licence** (RM3030, suite de RM3029). Aucun outil ne
  posait la question : un dépôt naissait sans `LICENSE` — donc sans droit d'usage pour personne —
  et la décision n'était consignée nulle part. `pm-project-new` demande la licence du code
  (`--license <SPDX>`, sinon un menu en terminal qui explique chaque choix — MPL-2.0 pour un cœur
  ouvert à modules libres ou fermés, Apache-2.0, MIT, LGPL/GPL/AGPL-3.0, propriétaire — défaut
  GPL-3.0 ; hors terminal : propriétaire, rien n'est publié) et l'écrit dans `.mmi-pm/meta.yml`.
  `pm-repo-new --push-from` écrit et committe `LICENSE` (texte SPDX intégral, `templates/licenses/`,
  `NOTICE` pour Apache) si le dépôt n'en a pas, en reprenant la licence du projet PM qui le
  contient. Module `scripts/pm_license.py`.
- **Ce qui traîne dans le repo de données est rattrapé au fil de l'eau** (RM3013). L'auto-commit
  des scripts (`pm_git.autocommit`, RM1834) ne couvrait que les chemins que chaque script nomme :
  en six jours, 337 fichiers modifiés et 16 non suivis (fiches, `.log.md`, `reporting.yml`, CDC
  édités à la main ou par un agent) s'étaient accumulés sans commit. Pas de timer ni de process
  dédié : c'est chaque auto-commit qui referme le filet — sur un dépôt de données, ce qui n'a pas
  été modifié depuis plus d'1 h (`git.sweep_after_min`) part dans un commit `pm(rattrapage): N
  fichier(s) laissés non commités > 60 min (déclenché par <outil>)` séparé, poussé avec le nôtre.
  Un fichier touché il y a moins d'1 h est laissé à la session qui est dessus ; un dépôt de code
  n'est jamais balayé ; `git.sweep: false` débraye. Journalisé (catégorie `pm`) ; les échecs
  d'auto-commit y tombent aussi en `warn`. Sources connues bouchées au passage : `pm-env-expose`,
  `pm-decisions`, `pm-glossaire`, `pm-task-doc` committent désormais leurs écritures.
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
- **Ce qui change arrive au cockpit sans attendre son tick** (RM3006). Statuts de tickets,
  notes, worklog de session et relève mail n'apparaissaient qu'au prochain composite `/refresh`
  (3 à 7 s). Les scripts qui écrivent publient désormais un sujet à karl-agent
  (`scripts/pm_events.py`, best-effort et silencieux si l'agent est absent) ; le service tient
  un canal SSE `/api/session/events` par cockpit, authentifié et filtré par le même `auth_ctx`
  que le tick, et y pousse les blocs de `/refresh` qui ont changé pour ce client. Le front les
  livre par la même voie que le tick (dédoublonnage par hash) ; le tick reste, en réconciliation
  ralentie (6 s / 30 s) tant que le canal vit, et reprend sa cadence à la coupure — EventSource
  se reconnecte seul. Pas de veilleur de fichiers : c'est l'écriture qui parle. Front v3.5.0.
- **Le cockpit sur un téléphone : un gabarit, pas un second cockpit** (RM3003). Sur un écran étroit
  (ou `?layout=mobile`), la page montre une colonne à la fois — panneaux, centre, colonne de la
  session — avec une barre de navigation en bas dont le badge compte les sessions qui attendent.
  Attacher une session ou ouvrir une fiche bascule sur le centre, montrer un onglet de droite sur
  la colonne de droite. Ce sont les mêmes contrôleurs, ViewModels et vues qu'au bureau : la
  disposition est décidée par `modules/layout/mobile.js` et rendue par du CSS sur
  `html[data-layout]` / `main[data-mpage]`. Le test navigateur joue un viewport de 390 px
  (Chromium + Firefox). Front v3.4.0.
- **Un registre des types d'entités, quatre niveaux d'affichage** (RM3002). Le centre, les
  onglets, l'historique, l'épinglage et les références cliquables dispatchaient chacun sur
  `kind === "…"` — une cinquantaine de sites, et un type de plus (le panneau 🧠 mémoire, la
  veille) se déclarait à cinq endroits. `core/entities.js` porte désormais chaque type : icône,
  libellé, infobulle, titre d'erreur, recette d'ouverture, surface à fermer, restaurable ou non ;
  le centre lit le registre et ne dispatche plus. Chaque ViewModel de type se lie au registre et
  décrit sa fiche par une seule `sections()`, dont `row` / `card` / `panel` / `full` sont des
  compositions — session, ticket, projet, email, fichier, dossier et client les exposent, depuis
  une fixture, dans les tests. Convention CSS unique par niveau (`.e-row`, `.e-card`…) : ajouter
  un type ne coûte aucune ligne de CSS ni aucun `kind ===`. Les vues spécialisées du bureau restent
  ; le gabarit mobile (RM3003) compose les niveaux. Front v3.3.0.
- **Le cockpit n'écrit plus de HTML qu'en un seul endroit** (RM3001). Quarante-cinq `innerHTML =`
  subsistaient dans les contrôleurs (options de listes déroulantes, badges, cartes secondaires),
  chacun avec son `String(vue)` — autant de portes par lesquelles une chaîne construite à la main
  aurait pu passer. `core/dom.js` gagne `paint(el, frag)` et `append(el, frag)`, qui n'acceptent
  qu'un fragment sûr (`html\`…\``, `raw()`) ou le vide et lèvent sur une chaîne nue ; tous les
  sites y passent, `jarg()` (argument d'un handler inline, plus aucun `on*`) est retiré, et
  `esc()` n'est plus appelé par aucune vue (linkify, titres, surlignage, glossaire réécrits sur
  le gabarit). Garde de test : aucune écriture HTML hors `core/dom.js`.
- **Sonde mémoire par module** (RM3007). Le cockpit savait dire, depuis la console, combien de
  montages et d'entrées de store il retenait (`karl.stats()`), mais rien n'était activable
  depuis l'interface ni ventilé par module — l'enquête RM2807 (onglets à 20 Go) en restait à
  la sonde opt-in du terminal. `core/probe.js` échantillonne, à la cadence choisie, ce que
  chaque module retient (montages, nœuds, écouteurs/minuteries/abonnements, entrées de store,
  rendus par minute — le module d'un montage est lu dans la pile d'appel, sans rien demander
  aux contrôleurs) et lit dans l'historique ce qui **grimpe sans redescendre**. Activation dans
  🔧 réglages (préférence de ce navigateur, coût nul décochée), panneau 🧠 mémoire au centre
  (tableau, courbe des nœuds par module, alertes, export JSON). Front v3.2.0.
- **Cockpit 3.0.0 — refonte CSMV** (RM2889, puis RM3012, RM3010/RM3011, RM3000, RM3005). Le
  cockpit était un `index.html` de plusieurs milliers de lignes avec un script inline, des
  `onclick`, des caches partagés par référence et des routes historiques. Il est désormais un
  front en **modules ES sans build runtime** : `src/boot.js` monte les domaines, `src/core/`
  porte le socle (html sûr, dom, store, api, endpoints, erreurs, markdown, journal, version), et
  chaque domaine vit dans `src/modules/<domaine>/` avec ses couches classées par suffixe (modèle,
  `Repository`, `service`, `ViewModel`, `.view`, `controller`, `.scss`) — gardes d'imports par
  suffixe. Zéro `on*` : tous les gestes passent par délégation `data-action` / `data-cmd` /
  `data-link`. L'API se lit `/api/<type>/<action>` (`route()`), les chemins historiques restant
  servis par alias généré (`scripts/karl_api_routes.py`). Le CSS est compilé depuis
  `src/styles/*.scss` + `src/modules/*/*.scss` en un seul `cockpit.css` (`npm run build:css` dans
  `tooling/`, empreinte des sources vérifiée par les tests). Les six caches partagés sont des
  **stores nommés et bornés** (`core/store.js` : LRU + TTL + abonnement) que `karl.stats()`
  compte. Le front porte une **version** (`src/core/version.js`, pied de page, `/health`) et le
  cockpit prévient quand serveur et front divergent. Un **journal structuré** (RM3010, `logs/
  karl-agent.jsonl`, sévérités debug/info/warn/error, catégories auth/issue/provider/tmux/claude/
  worklog/files/api/mail/sets/refresh/pm/session/voice/env/front/system) est lisible depuis le
  bouton **📜 journal** de l'en-tête (filtres, suivi, copie ; les erreurs du navigateur y tombent
  aussi). Deux incidents de MEP le 2026-09-05/06 ont fixé deux gardes : un `Object.assign` figeait
  le getter `authRequired` (jeton jamais envoyé → écran de login par-dessus la page) — les
  descripteurs sont conservés ; un `setTimeout` détaché appelé en méthode levait « Illegal
  invocation » dans tout navigateur mais pas sous node (page bloquée à « chargement… ») — garde
  statique et **test navigateur** Playwright (`test_cockpit_browser.js`, Chromium + Firefox,
  stockage semé d'un utilisateur revenu) à lancer avant une MEP du front. 35 suites node.
- **Retrouver une session par mots-clés** (RM2991). Le panneau « Reprendre une session » ne
  se pilotait qu'avec des filtres fermés — client, projet, marqueur, moteur — alors que la
  question qu'on se pose devant lui est « où ai-je traité ça ? ». Le serveur savait déjà
  filtrer sur un `q`, mais il ne comparait qu'au **titre** de la session et **aucun champ
  du cockpit ne l'envoyait** : la capacité existait, inatteignable. La recherche porte
  désormais sur ce que le PM a lui-même enregistré sur la session — son **worklog**
  (libellés de tickets, notes, prochaine étape, **le texte des demandes** telles que
  formulées, notifications), les **tickets traités** par numéro (`2703` comme `RM2703`)
  **et par sujet**, le client/projet et le répertoire. Taper « annuaire » ramène la session
  de RM2703 ; taper un numéro répond à « dans quelle session ce ticket a-t-il été traité,
  pour la reprendre ». Plusieurs mots se cumulent en conjonction, sans ordre ni contiguïté
  (`sieve karl@` trouvait 0 résultat en sous-chaîne stricte, 1 en conjonction). Le contenu
  des **transcripts** reste une case à cocher : 0,5 Mo de métadonnées contre 400 Mo de
  conversations, soit une réponse en 0,02 s contre 1,4 s — et le transcript **complète**
  les mots que les métadonnées n'ont pas, il ne recommence pas la recherche. Le balayage
  profond est borné (budget de temps, plafond d'octets, sessions les plus récentes
  d'abord), une seule passe multi-motifs par fichier, et la ligne trouvée par cette voie
  porte la pastille « transcript » pour ne pas ressembler à un faux positif. Chaque ligne
  affiche enfin le **sujet** des tickets, pas seulement leur numéro. Deux
  finitions dictées par l'essai sur les données réelles : l'identifiant de
  session se cherche par **préfixe** et non en sous-chaîne (« 2392 » tombait au
  milieu de `ca239234-…` et rendait une session au hasard) ; et le worklog
  **survit** au transcript, si bien qu'un ticket peut avoir été traité dans une
  session qu'on ne peut plus reprendre — celles-là sont nommées en note grise,
  avec leurs tickets, sans être cliquables : la recherche dit ce qui existe, le
  bouton ne promet que ce qui marche.
- **La carte « Sessions enregistrées » règle tous les jeux** (RM2955). Elle interrogeait
  `/session-set` avec le jeu **courant** codé en dur : pour renommer un jeu, changer sa
  règle, sa rétention ou l'effacer, il fallait d'abord **le rendre courant** — donc
  quitter la vue sur laquelle on travaillait, puisque le jeu courant gouverne aussi le
  panneau « ▶ en cours ». La carte a désormais son propre sélecteur : le jeu **édité**
  et le jeu **courant** sont deux notions distinctes (comme une vue n'est pas une cible,
  RM2446), et la liste marque « ● courant » celui qui gouverne l'affichage et reçoit
  l'adhésion automatique. Le ▶ relancer de la carte vise le jeu affiché par la carte,
  celui du panneau de gauche le jeu courant — un bouton qui écrit dit où (RM2448).
- **Une vue « toutes les sessions »** (RM2954). Les vues laissaient un angle mort, et la
  question qui l'a révélé était la bonne : « les filtres par client montrent-ils toutes
  les sessions actives du client, ou seulement celles dans des jeux ? ». Réponse : les
  vues par client lisent l'**index des sessions**, pas les jeux — elles montrent donc
  tout, mais d'**un seul client** ; c'est `all` qui trompe, en désignant « tous les
  JEUX » et non toutes les sessions. Une session éteinte, hors jeu, sur un dossier dont
  le client ne se résout pas n'apparaissait alors **nulle part** — 6 sessions sur les 66
  connues, dans l'état actuel du parc. La nouvelle vue est la vue client **sans le
  filtre client**, et sans plafond : une vue qui promet « toutes les sessions » et
  s'arrête à 24 se contredirait. Les hygiènes de RM2949 (ticket fermé, rien à rouvrir)
  s'y appliquent comme ailleurs.
- **« default » devient le registre des sessions actives** (RM2953). L'adhésion
  automatique (RM2445) visait le jeu COURANT. C'était juste tant qu'il était manuel ;
  le jour où le jeu courant est devenu un jeu **dérivé** (`pm`), elle s'est mise à
  répondre `reason: "derive"` — légitimement, une règle décide seule de son contenu —
  et **plus aucune session n'a été enregistrée nulle part** : le registre est resté à
  11 entrées pendant que les sessions défilaient. Le jeu courant redevient donc un pur
  filtre d'AFFICHAGE, et `default` un registre unique : on y entre à la création et à
  la reprise, on en sort quand la session est marquée `[DONE]` **et** éteinte (une
  `[DONE]` qui tourne encore y reste — on n'escamote pas un processus vivant). Trois
  conséquences assumées : le plafond de 24 ne s'y applique plus (un registre qui refuse
  des entrées ment sur ce qui tourne, et le refus tomberait sur la session qu'on vient
  de lancer ; les jeux manuels le gardent) ; les sessions vivantes absentes y sont
  **rattrapées** au fil du poll, dans la même passe d'hygiène qui en évacue les `[DONE]`
  éteintes ; et retirer (⊖) une session qui **tourne** est refusé avec son motif, parce
  qu'elle reviendrait au poll suivant — un geste qui se défait n'est pas un geste
  (RM2952). Le sélecteur l'annonce sous son nom, « sessions actives », plutôt que sous
  le slug de stockage.
- **La colonne de droite obéit** (RM2952). Deux mécanismes annulaient les gestes de
  l'opérateur. La largeur d'abord : l'onglet conversation était posé en
  `max(--rpanel-w, 460px)` (RM2579), donc la poignée (RM2599, bornée à [240, 900])
  ne réduisait plus rien sous 460 px tant que cet onglet était actif — un plancher
  muet, qui se lit comme un réglage cassé. Les 460 px deviennent le **défaut** du
  `var()` : une largeur réglée gagne, et « réinitialiser » retire la variable au lieu
  d'y écrire 330 px en dur (sinon le défaut de l'onglet conversation disparaissait
  aussi). Le repli ensuite : attacher une session déplie la colonne, et cela arrive
  tout seul — après un spawn, une relance, au rechargement. Un panneau replié à la
  main se rouvrait donc sans cesse. `rightPanelReduce` distingue maintenant le repli
  **voulu** du repli par défaut : une ouverture automatique (`show` sans onglet) le
  respecte, une demande ciblée (ce ticket, ce fichier) déplie comme avant, et le
  repli automatique de fin de session ne décide rien à la place de l'opérateur.
- **Un spawn ne répond plus à la place du moteur** (RM2951). Lancer une session sur un
  dossier que le moteur n'avait jamais ouvert donnait une session **morte-née** : claude
  s'arrête sur son garde-fou (« Is this a project you created or one you trust? », curseur
  sur « ❯ No, exit »), or `❯` figurait parmi les marqueurs de « TUI prêt » — karl-agent
  croyait l'invite disponible, envoyait le prompt **puis Enter**, et cet Enter validait la
  sortie. Le moteur quittait, la session tmux mourait, `POST /spawn` répondait quand même
  **201**, et la clé enregistrée désignait une conversation qui n'a jamais existé (incident
  RM2950, client matnat). Le catalogue des moteurs déclare désormais, à côté de ses
  marqueurs de prêt, ses **marqueurs de blocage** ; `engine_pane_state()` les teste **en
  premier** — un écran qui contient les deux est une question fermée, pas une invite. Un TUI
  bloqué ne reçoit **ni prompt ni Enter** : la session reste vivante avec sa question à
  l'écran, et la réponse porte `blocked` + `prompt_sent: false`, que le cockpit affiche.
  Enfin `/spawn` et `/resume` vérifient que la session a **survécu** à son démarrage avant de
  répondre « créée » — plus de 201 sur une session déjà éteinte.
- **Les tuiles grises ne promettent plus une session introuvable** (RM2949). Le panneau
  « ▶ en cours », vue par client, alignait des dizaines de sessions éteintes annoncées
  « conversation mémorisée » : le clic partait en `/resume` et retombait sur « relance
  impossible ». Deux causes, deux corrections. `resumable` ne disait que « un identifiant
  est mémorisé », jamais « la conversation existe encore » — il lit désormais la **même
  source que `/resume`** (transcript claude, base du moteur ailleurs), par le cache du
  poll ; la tuile, la liste du jeu (🟡 reprenable / 🔴 perdue) et l'estimation du « tout
  relancer » disent donc la même chose que le serveur fera. Et un clic sur une conversation
  purgée ne propose plus une reprise vouée à l'échec : il annonce une **session neuve** dans
  le même dossier, sans le contexte d'avant, et c'est cela que l'opérateur accepte. Côté
  volume, une session éteinte dont le **ticket est fermé** sort des vues — le marqueur
  `[DONE]` (RM2427) l'écartait déjà, mais il se pose à la main et ne l'était presque jamais :
  9 des 24 tuiles d'une vue client portaient un ticket clos. Une session qui **tourne** reste
  affichée, ticket fermé ou non : on n'escamote jamais un processus vivant. Effet de bord
  corrigé au passage : `_transcript_info(sid, "claude")` empruntait la branche des moteurs
  tiers, qui n'a pas de lecteur pour les transcripts claude — une conversation bien présente
  y passait pour absente.
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
