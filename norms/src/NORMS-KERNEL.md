## ⚙ KERNEL — lecture obligatoire à chaque session PM

> **Tu lis ce fichier en ENTIER, à chaque session — et de nouveau après chaque
> compaction ou reprise** (elles gardent la tâche et perdent les normes : il ne t'en
> reste qu'un souvenir). Le système te le redonne seul (`mmi-pm norms-recall`) ; sinon
> relis-le avant d'agir. Il est court par conception. Il
> contient deux choses : (1) les **tripwires** — règles à respecter en permanence — et
> (2) la **table des déclencheurs** — *quand* ouvrir *quel* module pour le détail.
>
> **Tu n'ouvres un module QUE quand son déclencheur se présente.** Le détail complet de
> chaque règle vit dans `modules/<nom>.md` ; le KERNEL te dit qu'elle existe et quand y
> aller. En cas de doute : le module fait foi sur le **détail**, le KERNEL sur
> l'**obligation d'y aller**.
>
> `NORMS.md` (document complet, ~117 Ko) est un **artefact généré** par
> `pm-norms-assemble.py` à partir de ce KERNEL + des modules — **ne l'édite jamais à la
> main**. Contrat de maintenance : [`../MAINTAINING.md`](../MAINTAINING.md).

## Table des déclencheurs — quand ouvrir quel module

| QUAND (situation que tu reconnais) | → ouvre / applique | Outil canonique |
|---|---|---|
| je cherche un projet dans l'index, j'ajoute un contact | `modules/structure-reference-pratique.md` | `pm-client-contact` |
| je résous un chemin PM | `modules/structure-reference.md` (jamais de hardcode) | `pm_paths.PMConfig` |
| je commence à coder un ticket (branche) | `modules/git-mep.md` | `pm-branch-start` |
| je push / crée une MR / projet versionné | `modules/git-mep.md` | `glab` |
| le transport git résiste (SSH/token, submodules), l'API GitLab répond de travers, je prépare une MEP, ou je touche un ticket d'interface | `modules/git-mep-pratique.md` (mode d'emploi, hors précharge) | `pm-mr`, `pm-promote` |
| je livre / teste / mets en preprod (MEP) | `modules/git-mep.md` + `modules/status-workflow.md` (actions au déploiement : `pm-task-deploy`) | `pm-task-status-update` |
| je code ou modifie de la logique (fonction, règle, calcul, transition, flux), ou je livre un ticket : écrire les **tests AVEC le code** | **tripwire #17** + `modules/testing.md` | `mmi-pm test`, `pm-task-protocol`, `pm-task-deliver` |
| je modifie le **rendu front d'un site public** (projet `browser_test: true`) : valider au **NAVIGATEUR** avant de livrer | **tripwire #17** + `modules/testing.md` §7 | `tools/browser-check`, `pm-project-config --browser-test` |
| je livre un changement de SURFACE (outil, flux, cockpit UI, archi/dev) : mettre à jour la doc vivante dans la MÊME MR (Changelog · README · aide cockpit · DEVELOPMENT) | `modules/governance.md` (§ Développement du PM) | — |
| je m'apprête à ouvrir un ticket pour un changement TRIVIAL du repo PM (terme de glossaire, coquille) | `modules/governance.md` (§ Changements sans ticket) — la MR reste due, le ticket non | `pm-mr create --no-ticket` |
| je change un statut de tâche | **tripwire #4** + `modules/status-workflow.md` | `pm-task-status-update` (`--list-next`) |
| je cherche la transition exacte permise, je qualifie en phase d'étude, **je rédige un CDC de ticket** (proposition d'implémentation obligatoire dès que l'étude débouche sur du code — `pm-task-implementation`), une transition m'est refusée (assignee-only), ou un ticket revient avec des notes | `modules/status-workflow-pratique.md` (hors précharge) | `pm-task-status-update --list-next` |
| je prends une tâche (passage en_cours) | **tripwire #5** + `modules/status-workflow.md` | `pm-task-status-update` |
| fin de dev / routing vers test | `modules/status-workflow.md` (`requires_agent_test`) | `pm-task-status-update` |
| **« fais le cycle de session »** (bouton ↻ Relancer) — constater le déployé, fermer, mettre en prod, enchaîner un ticket | `modules/session-tooling-pratique.md` § « Le CYCLE DE SESSION » — l'ordre compte, et ce qui ne se force pas y est dit | `pm-task-status-update`, `pm-promote` |
| je cherche si un geste a son outil PM, ou l'invocation exacte d'un `pm-*` | `scripts/INDEX.md` (TOUS les scripts, par domaine — jamais `ls scripts/`) puis `modules/session-tooling-pratique.md` (trous connus, idiomes) | tous les `pm-*` |
| le demandeur formule une demande (quelle qu'elle soit, même si elle sera ticketée dans la minute) | `modules/session-tooling.md` § « Registre des demandes » | `pm-session-status.py request` |
| un événement notable arrive en séance (secret affiché, action refusée, garde-fou déclenché, outil PM en défaut, décision qui bloque) | `modules/session-tooling.md` § « Notifications importantes » | `pm-session-status.py notify` |
| le contexte se remplit, une compaction approche, ou je rends la main en fin de séance | `modules/session-tooling.md` § « Avant une compaction » | `pm-session-status set --next`, `pm-task-think` |
| je rends un conseil, le demandeur arbitre, une question reste ouverte, une fonctionnalité prend forme — ou je m'apprête à fermer un ticket | `modules/session-tooling.md` § « Consignation par ticket — le `.think.md` » | `pm-task-think`, `pm-think-merge --check` |
| un ticket me revient (a_corriger / réattribution) | `modules/status-workflow.md` | `redmine-fetch-updates` |
| le ticket a une checklist / desc périmée / done_ratio bouge | `modules/redmine-hygiene.md` | `pm-task-description-update` |
| j'introduis/fais évoluer une donnée ou un artefact partagé Redmine↔PM (champ, vue, template, doc, métrique) | `modules/redmine-sync.md` (principe de parité) | scripts de sync dédiés |
| je démarre un travail et je ne sais pas **par quel bout** le prendre — projet neuf, reprise d'existant, migration, ticket qui ressemble à une étude | `modules/methodes-travail.md` (quatre natures, quatre protocoles) | — |
| j'attaque un **projet neuf par un cahier des charges complet**, je consigne un arbitrage dans un CDC, ou je veux savoir quand il est fini | `modules/cdc.md` (trois livrables, grille 360°, harnais) | `pm-cdc` |
| on me demande un **audit** (site, sécurité, infra, DNS, mail, conformité), d'où que parte la demande | `modules/audits.md` — lire l'existant AVANT de mesurer ; findings dans `iprospective/audits`, remédiation dans le projet propriétaire | skill `mmi-audit`, `new-audit-session.sh` |
| je produis un livrable documentaire (audit, CDC, spec, roadmap, rapport) | `modules/redmine-sync.md` (format portable : markdown en repo, jamais un artefact LLM-spécifique) | `pm-wiki-sync` |
| je commit / franchis une étape significative | `modules/traceability.md` (note + log + métriques) | `pm-task-report` |
| un échange porte une décision / arbitrage sur la tâche | `modules/traceability.md` (journaliser au fil de l'eau) | — |
| je crée un ticket | **tripwire #7** (CF IA) + estimation | `pm-task-add` |
| je crée un projet / une entité PM | `modules/project-creation.md` (+ bootstrap, memberships) | `pm-project-new`, `pm-project-bootstrap`, `pm-client-new` |
| un projet sert plusieurs clients / implémente un général | `modules/project-modeling.md` | `pm-doctor`, `pm-sync-views` ⚠ |
| je documente un aspect / cahier des charges | `modules/project-modeling.md` (aspects) | — |
| je crée / répare le lien workspace↔PM | `modules/structure-reference.md` | `pm-sync-links` ⚠ |
| je note / cherche un contact d'un client | `modules/project-modeling.md` (§ Contacts) | `pm-client-contact` |
| je me connecte à / référence un environnement | `modules/environments.md` | `ssh_alias` |
| j'écris ou j'édite un aspect `environments.md` (noms d'env, champs, `post_deploy`, chemins de logs) | `modules/environments-reference.md` (hors précharge) | `templates/aspects/common/environments.md` |
| je diagnostique un incident / il me faut l'historique de charge d'une machine du parc | **tripwire #16** + `knowledge/zabbix/api.md` | API JSON-RPC, `ZABBIX_API_TOKEN` |
| je manipule un secret / credential | **tripwire #11** + `modules/environments.md` | `resolve-secret.sh` |
| début de session PM : péremption des PAT GitLab | `modules/git-mep-pratique.md` (rotation J-7) | `pm-token-check` |
| je lie / fais dépendre / parente deux tickets | `modules/task-links.md` | `pm-task-link` |
| une tâche est dans le mauvais projet PM (ou déplacée côté Redmine) | `modules/session-tooling.md` | `pm-task-move` |
| je veux qu'un travail tourne PÉRIODIQUEMENT / j'allais écrire un cron | `modules/scheduler.md` — l'instance n'a qu'UN cron, tout se déclare au registre | `pm-scheduler`, `jobs.reference.yml` |
| avant une session touchant Redmine / périodiquement | `modules/redmine-reference.md` | `redmine-config-check` |
| micro-tâche (≤ 30 min, sans code) | `modules/status-workflow.md` § flux court | `pm-task-take --no-branch`, `pm-task-add --retro` |
| j'estime / calcule le ROI / priorise | `modules/roi-pricing.md` | `pm-task-add`, `pm-task-tick`, `priority.py` |
| je suis l'orchestrateur (assignation, sous-tâches, propagation) | `modules/collaboration.md` | — |
| je génère les fichiers auto (Changelog/Pistes/Remarques) | `modules/summarizer.md` | — |
| gouvernance : déploiement, versionning de NORMS, distribution des skills | `modules/governance.md` + [`../MAINTAINING.md`](../MAINTAINING.md) | `pm-norms-assemble`, `pm-norms-doctor` |
| j'ajoute/édite un module ou le préchargement d'un rôle (coût de contexte) | `modules/governance.md` | `pm-context-budget` |

⚠ = outil pas encore livré (suivi RM1923) ; en attendant, l'opération manuelle est décrite dans le module.

## Tripwires — à respecter en permanence (dangereux si raté)

Règles dont l'oubli casse silencieusement quelque chose. Énoncé **auto-suffisant** ici ; le détail/rationnel est dans le module indiqué.

1. **Outillage obligatoire.** Toute opération touchant l'**état** d'une tâche, une **branche**, un **repo/submodule** ou un **ticket Redmine** passe par le **script/skill PM dédié**, jamais à la main. Pas d'outil pour une telle opération = **trou à combler** (créer le script), pas une exception manuelle. → `modules/session-tooling.md`
2. **Commit + push systématique.** Après toute modif d'un fichier PM (ai-projects) ou du workspace de code : `git add <chemins explicites>` + commit + **push immédiat**. **Jamais `git add .` / `-A`** ; ne stage et ne commit **que tes propres modifs** (repos partagés souvent dirty en concurrence). → `modules/git-mep.md`
3. **Branche par ticket + livraison par MR — sur les dépôts de CODE.** Coder un ticket = sur une branche `<RMid>-<slug>` tirée de la branche d'intégration (jamais directement dessus) ; renseigner le CF Redmine *GIT Branche*. **Livraison = Merge Request** sur le remote (jamais un merge poussé en direct sur l'intégration), et **la branche distante est CONSERVÉE** après merge (suppression d'une branche distante = accord explicite requis ; autoriser un merge ≠ autoriser une suppression). Ménage des branches mergées **uniquement en local**. **Aucun commit/push direct sur une branche protégée** — intégration (`dev`) **ET** prod (`main`/`master`) : tout passe par branche de ticket + MR, y compris la **promotion `dev`→prod** (modèle 3 branches). Un commit direct sur `main` court-circuite la promotion → divergences et collisions de version ; à **enforcer côté GitLab** (protection de branche : push direct interdit, seul le merge de MR autorisé).
   **Exception — dépôts de DONNÉES PM (`*-core`), RM2440 :** un dépôt portant un `.mmi-pm/` ou `.mmi-pm-client/` **réel** à sa racine (*symlink* = workspace de code, **pas** un core) n'a ni code ni revue possible — l'historique git **est** l'audit. Sa branche de prod accepte le **push direct** (`push=Developer`) : les scripts pm-* y écrivent sans branche ni MR. Pas un contournement : `allow_force_push=false` reste posé, l'historique ne peut que **croître**. **Et on n'en parle pas** : cette plomberie est muette en restitution → tripwire #15. → `modules/git-mep.md`
4. **Sync statut MD↔Redmine.** Tout changement de `status` se répercute **dans le même cycle** : Redmine (status_id + note) + frontmatter (`status`, `status_history`, `updated`) + `.log.md`. **Toujours** via `pm-task-status-update.py`, **jamais** un statut « en dur » ; demande les cibles valides via `--list-next`. **Fermeture bloquée par sous-tâche ouverte** : un parent ne passe `ferme` que si **toutes ses sous-tâches sont elles-mêmes fermées** — sinon Redmine **refuse silencieusement** (PUT 204, statut inchangé, faux air de « permission *Edit issues* manquante »). Ne pas s'acharner ni conclure « droits » : vérifier `GET /issues/<id>.json?include=children` (et `allowed_statuses`). → `modules/status-workflow.md`
5. **Prise en charge ⇒ auto-assignation.** Passer une tâche en `en_cours` **implique**, dans le même mouvement, se l'**assigner** (`assigned_to`). Pas d'`en_cours` flottant. → `modules/status-workflow.md`
6. **redmine_id obligatoire.** Toute tâche/projet MD est reliée à son équivalent Redmine ; nom de fichier `RM{id}_…` cohérent avec `redmine_id`. → `modules/status-workflow.md`
7. **Filtrage IA.** Tout ticket créé depuis le système PM porte le CF `IA = "IA"` (posé par les outils au POST). Pas de MD local sans CF IA. → `modules/redmine-reference.md`
8. **Estimation.** Estimer (tokens + temps) **à la création** d'une tâche, et **à la prise** si l'estimation manque. → `modules/roi-pricing.md`
9. **Description vivante.** Si le ticket a une **checklist** ou un état décrit en prose : la tenir à jour **dans la description** (pas seulement en note), + `done_ratio` au fil de l'eau. → `modules/redmine-hygiene.md`
10. **Sécurité prod.** Aucune commande susceptible de modifier/casser la **production** sans **consentement humain explicite pour cette action précise**. Inspecter en lecture seule, proposer la commande exacte, attendre le feu vert ; un accord ne vaut pas pour l'étape suivante. **Point de restauration préalable** : si la cible tourne sur une infra **opensvc / LXC / ZFS**, prendre le **snapshot ZFS du conteneur depuis l'hôte AVANT la MEP** (`om <svc> sync update --rid sync#root_hour`) — il tient lieu de sauvegarde préalable (pas de dump applicatif ad hoc en plus), et son nom se logue avec la procédure de rollback. → `modules/git-mep.md`
11. **Secrets.** Jamais commités, loggués, écrits sur disque ni dans un transcript ; jamais demander le secret de déverrouillage d'un vault (master password, passphrase). → `modules/environments.md`
12. **Traçabilité par étape.** À chaque étape significative : commit + **note Redmine** (détail + réf commit + temps/tokens) + entrée `.log.md`. → `modules/traceability.md`
13. **Jamais d'identifiant séquentiel prédit — RM-id, iid de MR, ou autre.** Ne **jamais** saisir de mémoire un id issu d'une séquence partagée (« dernier vu + 1 ») : Redmine ET GitLab séquencent **globalement à l'instance** (plusieurs agents/projets créent en concurrence), le prochain numéro n'est **pas prévisible** (incidents : RM2142, RM2163, branche 2219→RM2222, merge de la MR !122 d'une autre session). **INTERDIT** (décision Mathieu 2026-07-11) : tout numéro se **capture de la sortie d'un script**, jamais ne s'infère. Outillage : `ID=$(pm-task-add … --porcelain)` ou `--start-branch` (atomique) ; `IID=$(pm-mr create … --porcelain)` ou `pm-mr create --merge` (atomique) ; `pm-mr merge --expect-rm <id>` (garde). Gardes automatiques : refus pm-mr sur branche divergente, hook git pre-push. → `modules/session-tooling.md`
14. **Résolution projet→Redmine précise (jamais par slug nu).** Cibler un projet pour une opération Redmine (sync wiki, note, description, stats…) se fait par référence **non ambiguë** — `client/slug` (ex. `matnat/infra`) ou `redmine.project_id` unique (ex. `matnat-infra`) —, **jamais** par match de slug nu : plusieurs clients partagent un même slug (ex. `infra` chez abatik/calicote/calyclay/matnat/pisceen) et un match « premier arrivé » écrit **silencieusement dans le mauvais projet Redmine**. Un slug **ambigu**, ou un projet **sans `redmine.project_id` en conf** (`meta.yml`), ⇒ **erreur bloquante** (« pas de projet Redmine précis → on n'avance pas »), jamais de choix silencieux. Outillage : `PMConfig.resolve_project_ref(ref, require_redmine=True)`. (incident : RM2410 → `pm-wiki-sync infra` ciblait abatik au lieu de matnat.) → `modules/redmine-reference.md`
15. **Plomberie PM : muette en restitution, et jamais le sujet d'une question.** La mécanique git des dépôts de **données PM** (`*-core`) — auto-commits `pm(...)`, push, branche, MR, « ✓ commité », hash — **ne figure JAMAIS** dans ta restitution : ce sont des process automatiques, les annoncer noie le fond sous du bruit. Tu restitues le **fond du ticket** et le **code livré** ; une MR de *code*, elle, se raconte. **Exception : l'échec** — un auto-push qui échoue se signale en **une ligne**. Idem outillage : `pm_git` est muet sur le nominal (`git.verbose: true` pour déboguer).
    **La règle vaut aussi en LECTURE.** Une question non qualifiée (« mergé en main ? », « c'est poussé ? », « où en est la branche ? ») porte sur les dépôts de **CODE** et sur le dépôt du **projet PM** — **jamais** sur un `*-core` que l'utilisateur n'a pas **nommé**. Le support n'est pas le sujet : la fiche d'un ticket est stockée dans le `<Projet>-core`, mais le ticket **porte sur** le code de `repos/` (RM2929). Répondre sur un `*-core` non nommé coûte un tour de conversation entier.
    **Pourquoi c'est un tripwire** : la règle s'applique au moment où tu **rédiges**, quand tu n'ouvres plus aucun fichier. Elle doit donc être sous tes yeux en permanence, sinon elle se viole en silence — et se re-viole après chaque compactage (incidents 2026-08-13 en restitution, 2026-09-01 en interprétation). → `agents/worker-common.md`, `structure-reference` § Vocabulaire du demandeur
16. **Métriques avant conclusion (incidents).** Le parc est supervisé par **Zabbix** (`https://zabbix.iprospective.fr`, JSON-RPC, `ZABBIX_API_TOKEN` du `.env` PM) : CPU, charge, réseau, workers Apache, pools PHP-FPM, MySQL. **Ne jamais conclure sur la cause d'un incident depuis les seuls logs de la machine** : ils disent ce qui a été journalisé, pas ce qui n'a **pas pu** l'être — un service engorgé cesse d'écrire, Apache journalise en FIN de requête, un rsyslog affamé imite une panne réseau. Un agent local qui « mesure » n'est pas fiable tant que Zabbix ne corrobore pas (incident RM2455 : deux diagnostics réfutés, cause réelle — pool PHP saturé → workers Apache épuisés → `MaxRequestWorkers` — trouvée en 3 requêtes Zabbix). → `knowledge/zabbix/api.md`

17. **Tests au fil de l'eau.** Coder = **livrer les tests avec le code**, pas après : TDD par défaut sur la logique, tests **unitaires** + **fonctionnels/workflow** anticipés dès la conception, **tous les cas** couverts (tests auto ET protocole de test, complémentaires). `mmi-pm test` **vert avant livraison** (front/cockpit ⇒ tests node même MR). Projet `browser_test: true` (site public) ⇒ **validation NAVIGATEUR obligatoire** avant toute livraison front, sur l'env du ticket (`tools/browser-check`) — le rendu navigateur n'est PLUS un cas « non automatisable » (RM3036). Non automatisable (intégration tierce, matériel, envoi réel) ⇒ recette humaine + **justification tracée** ; jamais « pas de test ». → `modules/testing.md`

18. **Restitution point par point (RM3127).** Un message du demandeur qui porte **plusieurs demandes ou questions** se traite **point par point, dans SON ordre**, en reprenant l'intitulé de chacun : il doit vérifier d'un coup d'œil que rien n'a été perdu, **sans relire son propre message**. **La réponse d'abord, le raisonnement après.** Ce qui n'a **pas** été traité se dit **explicitement, à sa place dans la liste** — jamais par omission, jamais renvoyé à la fin. Répondre en prose continue à un lot de demandes oblige le demandeur à faire l'inventaire lui-même ; s'il doit demander « tu as bien tout pris ? », la restitution a échoué (incident fondateur : 2026-09-13, deux messages, quatre demandes tombées).

19. **Antériorité avant de ticketer (RM3130).** Une **nouvelle demande** du demandeur se cherche d'abord dans l'existant : `mmi-pm task-search <mots-clés>` — titres, corps et `.think.md`, **fermés inclus** (un ticket clos est souvent la meilleure réponse). Un résultat proche se **lie** (`pm-task-link … relates`) ou **complète** le ticket trouvé ; il ne donne pas un doublon. Vaut aussi avant de consigner une F ou une D. Sans cette recherche, on recrée ce qui existe et on éparpille un même sujet sur trois tickets — la sortie est volontairement brève pour qu'aucun agent n'ait de raison de s'en passer. **`pm-task-add` fait la recherche lui-même (RM3248)** : il affiche les antériorités, et **refuse** de créer sur une correspondance forte dans le même projet sauf `--not-duplicate "<pourquoi>"`, tracé au journal. La recherche manuelle reste due sur les MOTS-CLÉS du besoin, que le titre ne contient pas toujours : la garde ne compare que des titres.

20. **Grouper les appels d'outils.** Chaque appel d'outil refacture **tout le contexte accumulé** en relecture — mesuré sur une session d'étude : ~105 k tokens par appel, **52 % de la facture** (RM3109). Le **nombre d'appels** est donc le premier poste de coût, avant le volume lu. Appels **indépendants ⇒ une seule réponse** (plusieurs `tool_use` dans le même bloc partent en parallèle et ne coûtent qu'**une** relecture) ; appels **séquentiels ⇒ une seule commande** chaînée (`cmd1; echo "=== SECTION 2 ==="; cmd2`). Ne **jamais** relister le même dossier : penser le filtre AVANT (`| head -N`, `grep -v '^test_'`). Lire le **plan** d'un document (`grep '^#' f.md`) puis sa seule section utile — jamais le fichier entier « pour voir ». Le groupage n'est irréductible que lorsque la commande N+1 **dépend** du résultat de N. → `modules/session-tooling-pratique.md`

Les tripwires **structurels** (propriété exclusive du fichier, optimistic locking, journal append-only) sont énoncés juste en dessous, suivis de la colonne vertébrale (cascade, nommage, schéma frontmatter, énumérations).

## Propriété, verrou & journal — tripwires structurels

### Principe fondamental

**Redmine est le mutex. Les fichiers MD sont le contexte de travail.**

L'assignation d'un ticket Redmine à un agent lui confère la **propriété** du fichier MD correspondant (coordination de 1er niveau) ; en multi-dev, l'accès concurrent réel est **sérialisé par ressource** (`flock`), pas garanti par un unique écrivain.

L'inférence LLM est déjà distribuée par nature (appels API vers Anthropic). Ce qui doit être coordonné, c'est uniquement l'accès aux fichiers.

**Multi-utilisateur (v2.0.0) :** données communes partagées (groupe `pm`), accès concurrent **sérialisé par ressource** (`flock`), karl = admin via `sudo` humain. → `modules/collaboration.md`.

### Règles d'écriture

| Fichier | Orchestrateur | Worker assigné | Autres workers | Reviewer |
|---|---|---|---|---|
| `RM{id}.md` (tâche assignée) | lecture | **R+W** | lecture | lecture |
| `RM{id}.md` (tâche parente) | **R+W** | lecture | lecture | lecture |
| `RM{id}.log.md` | append | append | lecture | append |
| `project.md` | **R+W** | lecture | lecture | lecture |
| `NORMS.md` | lecture | lecture | lecture | lecture |

### Protocole optimistic locking

Filet inter-machine contre les écritures simultanées ; complète les verrous `flock` (même machine). Rare si propriété et verrous sont respectés.

```
1. Agent lit le fichier, note la valeur courante de updated (T1)
2. Agent prépare ses modifications
3. Agent relit le champ updated avant d'écrire
4. Si updated ≠ T1 → collision détectée → re-lire le fichier et recommencer
5. Si updated = T1 → écrire et mettre updated à T2 (timestamp courant)
```

Ce protocole s'applique à tous les fichiers `.md` (jamais aux `.log.md` qui sont append-only).

### Règles du journal (.log.md)

- **Append-only** : on n'efface jamais, on n'édite jamais une entrée existante
- Tout agent peut appender, même en lecture seule sur la tâche
- En cas d'écriture simultanée, l'ordre des entrées n'est pas garanti — c'est acceptable
- Pas d'optimistic locking sur les `.log.md` (append = pas de perte de données)

Format imposé pour chaque entrée :

```markdown
## 2026-04-27T14:32 — agent-dev (claude-sonnet-4-6)
Tokens : 3 200 | Durée : 15 min

Résumé de ce qui a été fait, décisions prises, problèmes rencontrés.
```

## Cascade et héritage

Le système suit une cascade à 3 niveaux : **client → projet → tâche**.

**Règles :**
- Par défaut, les valeurs d'un niveau parent sont héritées par tous ses enfants
- Un niveau enfant peut **surcharger** une valeur en la redéfinissant explicitement
- Les sections de texte (Description, Structure...) ne se surchargent pas — elles s'additionnent

**Champs candidats à l'héritage :**
- `team`, `defaults.priority`, `gitlab.group`, `gitlab.default_branch`
- `redmine.instance`, contraintes globales

**Lecture du contexte par un agent (worker, summarizer, reviewer) :**
```
1. Système    : NORMS.md + agents/worker-common.md + agents/worker-{role}.md
2. Client     : {entity_client_dir}/*.md + {entity_memory_dir}/*.md
3. Projet     : {project_dir}/*.md + {docs_dir}/*.md + {project_memory_dir}/*.md
4. Tâche      : paths.task_file + paths.task_log_file
```

(Chemins résolus via `pm.config.yml` — par défaut : `{projects_root}/clients/{C}/...`)

Chaque niveau **complète** ou **surcharge** le précédent selon les règles ci-dessus.

## Nommage des fichiers

| Élément | Format |
|---|---|
| Tâche | `RM{id}_{titre-en-kebab-case}.md` |
| Journal | `RM{id}_{titre-en-kebab-case}.log.md` |
| Overview projet | `project/overview.md` |
| Overview client | `client/overview.md` |

## Schéma frontmatter — Tâche

Voir [templates/task.md](../templates/task.md) pour le template complet.

### Champs obligatoires
`schema_version`, `redmine_id`, `title`, `type`, `creator`, `status`, `priority`, `created`

### Champs conditionnels
- `bug.*` — uniquement si `type: bugfix`
- `git.*` — si développement impliqué
- `test_url` — si environnement de test disponible
- `deploy_actions` — si déploiement nécessaire
- `close_reason` — obligatoire quand `status: ferme`
- `requires_agent_test` — `default` (défaut) | `oui` | `non` | `demander` : conditionne la
  passe agent-testeur en fin de dev (cf. § « Passe agent-testeur indépendante »). Mappé sur
  le CF Redmine 27. Absent ⇔ `default`.

## Valeurs énumérées

### type
`audit` | `feature` | `bugfix` | `refactoring` | `documentation` | `security` | `performance` | `infrastructure` | `configuration` | `database` | `design` | `research` | `maintenance` | `assistance`

### status
`nouveau` | `a_etudier_chiffrer` | `etude_chiffrage_en_cours` | `etude_chiffrage_a_valider` | `etude_chiffrage_a_corriger` | `a_faire` | `en_cours` | `a_tester_dev` | `a_tester_demandeur` | `a_tester_preprod` | `a_mep` | `a_mep_prod` | `en_mep` | `en_pause` | `a_corriger` | `ferme`

Liste exhaustive et **source unique** : `redmine.reference.yml :: statuses`. Ne pas recopier
les libellés Redmine dans NORMS — ils changent (RM2926) et la copie ment en silence.

`a_tester_verifier` est **déprécié** (≤ v1.18.0) — alias en lecture de
`a_tester_demandeur`, normalisé par les scripts.

### priority
`low` | `normal` | `high` | `urgent`

### close_reason
`resolu` | `abandonne` | `doublon` | `wont_fix` | `invalide` | `hors_perimetre`

### bug.reproducibility
`always` | `often` | `sometimes` | `rarely` | `never`

### estimate.difficulty
`low` | `medium` | `high` | `critical`

### pistes.type
`automation` | `amélioration` | `sécurité` | `performance` | `intégration` | `documentation`

### pistes.effort
`low` | `medium` | `high`

### roi.immediate_benefit / roi.monthly_benefit
`1` (négligeable) → `5` (critique)

### target_env
`null` | `local` | `dev` | `test` | `staging` | `prod` | `demo` | `qa` | `sandbox` | `<custom-kebab-case>`

Doit correspondre à un `environments[].name` du `project/environments.md` (ou
`client/environments.md` en cascade). Custom autorisé si le projet a un env spécifique
(`staging-eu`, `prod-canary`…). `preprod` reste accepté comme **alias** de `staging`
(cf. § Environnements) mais `staging` est la valeur canonique à privilégier.

## Journal (fichier .log.md)

Format append-only — ne jamais modifier rétroactivement. Chaque entrée :

```markdown
## 2026-04-26T14:32 — agent-scraper (claude-sonnet-4-6)
Tokens : 3 200 | Durée : 15 min

Résumé de ce qui a été fait...
```

