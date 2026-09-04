---
type: knowledge
product: dolibarr
created: 2026-08-31
---

# Dolibarr — procédure de mise en production (commune au parc)

Invariants valables sur **toutes** les instances Dolibarr du parc. Chaque
`environments.md` de projet renvoie ici et ne garde que **ses** spécificités.

Issu de la MEP RM2815 (Calicote, 2026-08-27) : les vérifications du § 2 et l'étape
du § 4 sont **constatées**, pas supposées.

> **Le point à ne pas oublier, celui qui motive ce document** : quand une MEP fait
> changer la version d'un **module** (submodule sous `htdocs/custom/`), le déploiement
> du code ne suffit pas. Il faut **désactiver puis réactiver le module** dans Dolibarr,
> sinon le code est neuf et la base reste ancienne.
>
> Ce document complète les normes PM (`modules/git-mep.md` et `git-mep-pratique.md`),
> il ne les remplace pas : consentement humain explicite pour chaque action de prod,
> snapshot ZFS pré-MEP, branches protégées et MR restent la règle générale. Ici, on
> ne décrit que ce qui est **propre à Dolibarr**.

## Séquence

```
0. snapshot / point de restauration        (si infra opensvc/LXC/ZFS — cf. NORMS)
1. inspecter l'arbre git de prod           (§ 2 — trois signaux d'arrêt)
2. fetch + revue du lot réellement déployé
3. relever les submodules dont le gitlink change   ← détermine l'étape 6
4. ── feu vert humain ──
5. git pull --ff-only  +  git submodule update --init --recursive
6. désactiver / réactiver CHAQUE module dont la version a changé   ← l'étape oubliée
7. vérifier (pages des modules, droits, protocole de test du ticket)
```

## 1. Le modèle de déploiement

La production est un **checkout git**, pas un livrable copié. Chaque instance suit une
branche `<version>-mmi` du dépôt `gitlab.iprospective.fr/dolibarr/dolibarr` :

| Instance | Version | Branche |
|---|---|---|
| `erp.calicote.com` | 19.0.4 | `19.0-mmi` |
| `erp.dercya.com` | 19.0.4 | `19.0-mmi` |
| `erp.villa-cactus.com` | 16.0.5 | `16.0-mmi` |

Deux conséquences immédiates :

- **Un correctif ne se propage pas tout seul entre branches.** Un patch mergé dans
  `19.0-mmi` n'atteindra jamais Villa Cactus ; il faut le porter sur `16.0-mmi`.
- **Les instances qui partagent une branche partagent aussi les commits des autres
  tickets.** Déployer chez Dercya, c'est déployer tout ce qui a été mergé dans
  `19.0-mmi` depuis son dernier pull, pas seulement ce qu'on visait.

Les **modules métier sont des submodules git** sous `htdocs/custom/` : `mmicrm`,
`mmishipping`, `mmiproduct`, `mmifournisseurprice`, `mmistats`,
`ylvfournisseurpricepisceen`… Un « bump de module » est un changement de gitlink dans
le dépôt principal.

## 2. Avant de déployer — inspecter, en lecture seule

L'arbre de production **n'est pas propre par défaut** et ce n'est pas une anomalie à
corriger dans l'urgence : il porte des modifications locales historiques. Il faut
simplement les connaître avant d'écrire dessus.

```bash
cd <racine du checkout>          # ex. /home/erp-calicote/public_html
git status --porcelain --branch  # modifications locales, avance/retard
git log -1 --format='%h %ad %s' --date=short
git fetch origin <branche>
git log --oneline HEAD..origin/<branche>   # ce qui sera réellement déployé
```

**Trois signaux d'arrêt** — on remonte à l'humain, on ne force pas :

1. **Un écart de plusieurs commits.** Le 27/08, la prod Calicote était **13 commits en
   retard** sur `19.0-mmi` : RM2779, RM2559, RM1800, DEC1 et plusieurs bumps de
   submodules. Un `pull` « pour livrer un correctif d'une ligne » aurait livré le
   travail de quatre autres tickets. Si la demande porte sur un seul correctif,
   déployer **ce seul commit** (voir § 3).
2. **Des modifications locales sur les fichiers ou submodules que la MEP va toucher.**
   Le pull échouera, ou pire, écrasera.
3. **Une source divergente** : branche suivie ou remote inattendus.

Relever aussi **la liste des submodules dont le gitlink change** — c'est elle qui
détermine le § 4 :

```bash
git diff --submodule=short HEAD origin/<branche> | grep -E '^(diff --git|[-+]Subproject)'
```

## 3. Déployer

### Cas courant — la branche entière

```bash
git pull --ff-only origin <branche>
git submodule update --init --recursive
```

`--ff-only` est délibéré : si le fast-forward est refusé, c'est que la prod a divergé,
et c'est une information, pas un obstacle à contourner.

`--init` n'est pas facultatif : il crée le répertoire des submodules **nouveaux**.
Sans lui, le répertoire reste vide et le module casse au chargement.

### Cas ciblé — un seul correctif

Quand la prod est en retard et qu'on ne veut livrer qu'un correctif, ne pas déployer la
branche. Vérifier d'abord que le fichier visé est identique entre la prod et la base du
correctif, puis :

```bash
git diff --stat <HEAD prod> <commit>^ -- <fichier>   # doit être vide
git cherry-pick <commit>
```

La prod se retrouve alors **en avance d'un commit** sur sa branche, en plus de son
retard. C'est assumé et temporaire : le prochain déploiement complet le résorbe, la
branche contenant déjà le même correctif. **Le noter dans le `.log.md` du ticket**, sans
quoi l'écart devient une énigme pour le suivant.

### Le cache PHP

Sur les pools vérifiés (`erp-calicote`), l'opcache tourne avec
`validate_timestamps=On` et `revalidate_freq=2` : **un fichier PHP modifié est repris
tout seul en quelques secondes**, aucun reload FPM n'est nécessaire. À revérifier par
instance avant de s'en remettre à ce comportement — ce n'est pas garanti ailleurs.

## 4. Réactiver les modules dont la version a changé — l'étape oubliée

**C'est ici que le process se joue.** Déployer le code d'un module ne rejoue rien côté
base. À l'activation, Dolibarr exécute le SQL du module, enregistre ses droits, ses
entrées de menu et ses déclarations de triggers. Tant qu'on ne repasse pas par là, un
module bumpé tourne avec **du code neuf sur un schéma et des permissions anciens**.

Le symptôme est différé et trompeur — une colonne manquante, un droit qui n'existe pas,
un menu absent, un trigger qui ne part pas — et il se manifeste des jours après la MEP,
loin de sa cause.

**Règle** : pour **chaque** module dont le gitlink a changé au § 2, désactiver puis
réactiver le module.

**Distinguer deux cas :**

| Situation | Geste |
|---|---|
| Module existant, gitlink bumpé | **Désactiver puis réactiver** |
| **Nouveau** submodule (gitlink ajouté, `.gitmodules` modifié) | `git submodule update --init` **puis activer** — il n'a jamais été actif, il n'y a rien à réactiver |

> **À confirmer par Mathieu** — la procédure exacte : passage par l'interface
> d'administration des modules, script dédié, ou les deux ? Faut-il une fenêtre de
> maintenance, les utilisateurs connectés étant affectés par la coupure d'un module ?
> Le mécanisme décrit ci-dessus est celui de Dolibarr en général ; la pratique maison
> reste à écrire par celui qui l'exerce.

## 5. Vérifier

- Les pages servies par les modules réactivés s'affichent, et leurs droits sont bien
  présents dans la fiche d'un utilisateur.
- Le protocole de test du ticket déployé passe.
- `git status --porcelain` ne révèle pas de submodule resté vide.

## 6. Revenir en arrière

- **Correctif isolé** : `git revert <commit>` puis redéploiement.
- **MEP complète** : snapshot ZFS pris avant la MEP (cf. `modules/git-mep-pratique.md`
  § « Point de restauration avant MEP »). Rétention courte sur `sync#root_hour` (~8 h) :
  c'est un filet **pour la fenêtre d'intervention**, pas une sauvegarde.
- Un module réactivé qu'on désactive ne défait **pas** forcément son SQL : le rollback
  d'un bump de module passe par le snapshot, pas par la désactivation.

## 7. À inscrire dans les tickets

Le champ `deploy_actions` du frontmatter existe pour ça. Un ticket qui bumpe un module
doit porter la réactivation dans ses actions de déploiement **et** dans son protocole de
test — c'est ce qui a manqué à RM2779 et RM2559.

## Points ouverts

- La procédure exacte de réactivation (§ 4) reste à dicter.
- Ce process vaut-il tel quel pour les trois instances, ou faut-il des variantes par
  client ?
- Les `environments.md` des projets Dolibarr (Calicote, Dercya, Villa Cactus,
  CalyClay, Pisceen) ne renvoient pas encore ici — à faire, sur le modèle de ce que
  `prestashop/mep.md` a mis en place.
