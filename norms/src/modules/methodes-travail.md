> 📂 **Module `methodes-travail` — quand lire ceci :** je démarre un travail et je ne sais pas
> **par quel bout** le prendre — un projet neuf, une reprise d'existant, une migration, un
> ticket qui ressemble à une étude. Une minute ici évite trois jours dans la mauvaise forme.
> **Outils :** `pm-cdc.py` · `pm-task-implementation` · skill `mmi-audit` · `pm-task-add`
> · **Préchargé par :** —.

## Reconnaître la nature du travail avant de commencer

La faute la plus chère n'est pas de mal coder : c'est de **traiter en ticket ce qui demandait
un CDC**, ou l'inverse — d'écrire cent pages pour ce qu'une branche réglait. Quatre natures,
quatre protocoles d'entrée.

| Ce que je reconnais | Nature | Protocole d'entrée | Livrables |
|---|---|---|---|
| un produit qui n'existe pas, plusieurs mois, des arbitrages structurants | **projet neuf** | `modules/cdc.md` — CDC complet | CDC + POC + dictionnaire, puis les tickets |
| une demande claire, une surface connue, quelques jours au plus | **ticket ordinaire** | protocole worker (KERNEL) | branche, MR, note, tests |
| « regarde comment c'est », « est-ce que c'est sain », sécurité, conformité | **audit** | `modules/audits.md` | findings dans `iprospective/audits`, remédiation chez le propriétaire |
| du code qui tourne et qu'il faut reprendre, migrer, remplacer | **reprise d'existant** | ci-dessous | inventaire mesuré, plan par lots, matrice de compatibilité |
| « explique-moi », « ça ne marche pas chez moi », « sors-moi cette donnée », une formation | **assistance** | ci-dessous | une réponse, une manipulation, une donnée — **jamais du code livré** |

Un doute entre deux natures se tranche par une question : **qu'est-ce qui sera faux dans six
mois si on se trompe ?** Un ticket traité comme un CDC coûte du temps ; un projet traité comme
un ticket coûte une réécriture.

## Assistance → répondre, pas livrer

Une assistance accompagne : elle explique, dépanne, extrait une donnée, forme. **Elle ne
livre pas de code.** Pas de branche, pas de MR, pas de proposition d'implémentation, pas
d'actions de déploiement — et ce n'est pas une préférence de style : l'instance Redmine ne
propose pas ces champs au tracker « Assistance ».

Ce que ça donnait tant que rien ne le vérifiait : l'API acceptait l'écriture, **la jetait**,
et répondait « succès ». RM3224 a porté **2 459 caractères de proposition d'implémentation**
absents de la fiche web pendant neuf jours. Le travail était fait, enregistré en local, et
invisible pour quiconque ne lisait pas le dépôt PM.

**Quand une assistance débouche sur du développement**, il y a deux issues, jamais une
troisième :

1. **Requalifier le ticket** — la demande était mal rangée au départ (`pm-task-type-update`,
   qui change le tracker Redmine autant que le `type` local). À préférer quand tout le
   ticket est en réalité du développement.
2. **Créer un ticket lié** — l'accompagnement était réel, et il a révélé un travail à faire.
   L'assistance reste ce qu'elle est et se clôt ; le développement vit dans son ticket
   (`pm-task-add --parent` ou `pm-task-link`, cf. `modules/task-links.md`). À préférer quand
   les deux temps sont distincts et se facturent différemment.

**Ce qui n'en fait pas du développement** : versionner un script d'analyse jetable dans le
dépôt PM pour répondre à la question posée. Le livrable reste la réponse. La frontière est
le **code applicatif livré au client** — celui qui se teste, se met en production et se
maintient.

**Le garde-fou** : l'outillage refuse d'écrire un champ que le tracker du ticket ne propose
pas, et dit laquelle des deux issues prendre. Il ne perd plus le contenu en silence.

## Projet neuf → le CDC complet

Voir `modules/cdc.md`. Le signe qu'on est là : les décisions à prendre engagent le **modèle de
données**, le **phasage** ou la **sécurité** — pas l'implémentation. Ce qui déclenche : un
produit, une refonte de fond, une brique que plusieurs projets consommeront.

Ce qui **n'est pas** un projet neuf : une fonctionnalité de plus dans un produit qui existe.
Elle se traite en ticket, avec au besoin une **proposition d'implémentation** (§ ci-dessous).

## Ticket ordinaire → le protocole worker

Le KERNEL le décrit en entier : cascade, prise en charge, branche, MR, traçabilité. Rien à
ajouter ici, sauf le rappel de ce qui le fait déraper : une étude qui s'installe dans un
ticket sans jamais devenir une proposition, et un ticket qu'on livre sans que la doc vivante
ait bougé.

**Le CDC de ticket** (`docs/cdc-rm<id>-<sujet>.md`) est une forme légère et utile : une
**proposition d'implémentation** écrite avant de coder, quand la solution n'est pas évidente
ou quand elle engage d'autres tickets. C'est le format le plus employé du parc. Il porte le
problème, deux ou trois options avec leur pour/contre, le retenu et **pourquoi**, et ce que ça
change ailleurs. Il ne porte **pas** de dictionnaire ni de POC — sinon c'est un projet neuf
qui s'ignore. Déclenchement et outil : `modules/status-workflow-pratique.md`
(`pm-task-implementation`).

## Audit → le système d'audit

Voir `modules/audits.md`. Le piège : produire l'analyse **dans le projet audité**. Un audit se
range dans le projet d'audits, avec une méthodologie **paramétrable et rejouable** ; la
remédiation seule retourne chez le propriétaire.

Un audit **de l'existant mené dans un CDC** est autre chose : c'est un chapitre du CDC, une
**source d'exigences**, pas un livrable d'audit. Sur un projet réel, la lecture d'un fichier de
règles de production et la mesure sur données réelles ont produit plus de décisions que les
discussions — dont une qui corrigeait un arbitrage déjà pris.

## Reprise d'existant → mesurer, puis un plan par lots

La reprise (migration de framework, refonte d'un vieux code, remplacement d'un outil) n'est ni
un projet neuf — le périmètre est **donné par le code qui tourne** — ni un ticket : elle dure.
Sa forme éprouvée dans le parc :

1. **Inventorier en mesurant**, avant toute décision : combien de fichiers, de méthodes, de
   scripts, de dépendances, lesquels sont morts. Un inventaire par domaine (ORM, helpers,
   scripts, admin), **daté**. L'inventaire n'est pas une lecture : c'est un comptage.
2. **La matrice de compatibilité** : ce qui existe des deux côtés, ce qui n'existe que d'un
   côté, ce qui porte le même nom et ne fait pas la même chose — c'est cette dernière colonne
   qui coûte.
3. **Le plan par lots**, dans un ordre justifié, avec pour chaque lot ce qu'il ferme et
   comment on vérifie qu'il est fermé. Un lot qui ne se vérifie pas n'est pas un lot.
4. **La gestion des conflits et des fusions** si l'ancien continue de vivre pendant la
   reprise : dire **qui gagne**, et où on rejoue.
5. **Le chiffrage par lot**, en ordres de grandeur assumés, affiné lot par lot. Un chiffrage
   global d'une reprise est faux ; un chiffrage par lot se corrige.

Le reste (registre des décisions, questions ouvertes, critère d'acceptation) se prend au CDC :
une reprise **est** un CDC dont le périmètre est déjà écrit — en code.

## Ce que la relecture des CDC du parc a appris

Sept CDC relus, de la note de trois fichiers au document de 2 300 lignes. Ce qui revient
partout mérite d'être dans la méthode ; ce qui n'apparaît qu'une fois mérite d'être su :

- **la provenance** — « ce qui vient du demandeur / ce que le document infère » — écrite en
  section propre, pas seulement en intention : c'est ce qui permet de relire un CDC à froid ;
- **le hors-périmètre explicite**, avec un motif par exclusion ;
- **ce qu'on voudra observer**, décidé avant de construire ;
- **les mesures datées** : un chiffre sans date pourrit sans prévenir ;
- **le chiffrage** et **les critères d'acceptation du CDC lui-même** — les deux manquaient au
  cas fondateur, et les deux sont ce qui distingue un accord d'un plan ;
- un **journal des révisions** n'est pas nécessaire : git le tient, le registre dit pourquoi.

## Langue du code : les identifiants en anglais

Les **identifiants se nomment en anglais** — fonctions, méthodes, paramètres, variables,
classes, noms de fichiers source. `lotsForTier()`, pas `lotsPourPalier()` ; `$restriction`,
pas `$restreint`.

L'**exception** est une base de code **déjà écrite en français** : on s'y conforme, plutôt
que d'y introduire un troisième dialecte. Attention au faux ami : un code **mixte** —
quelques noms français hérités dans une base par ailleurs anglaise, ce qui est le cas de
Dolibarr et des modules MMI — **n'est pas** une base française. Les ajouts s'y font en
anglais.

Restent en **français** : les commentaires et la documentation, les notes de commit et de
ticket, les libellés affichés à l'utilisateur. Et ne relèvent pas du choix : les **noms de
données existants** — colonnes, extrafields, clés d'API, valeurs stockées comme `palier` ou
`date_courte` — se citent tels qu'ils sont, les renommer casserait les données. Une variable
locale qui porte une telle valeur peut, elle, s'appeler `$tier`.

**Pourquoi.** Un code dont les identifiants mélangent deux langues ne se lit pas seulement
moins bien : il ne se **cherche** plus. Personne ne sait s'il faut grepper `palier` ou
`tier`, `expedition` ou `shipping` — et les deux finissent par coexister. Le coût est
permanent, et il croît avec la base.

**Quand l'appliquer :** au moment de **nommer**, pas au moment de relire. Avant d'écrire une
fonction, regarder comment la base nomme ses propres symboles ; en cas de mélange, choisir
l'anglais.
