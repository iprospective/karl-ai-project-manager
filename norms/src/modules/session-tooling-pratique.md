> 📂 **Module `session-tooling-pratique` — quand lire ceci :** je cherche si un geste a son outil ou s'il reste manuel · je veux l'invocation exacte d'un `pm-*` sans relancer `--help`.
> **Outils :** tous les `pm-*` · **Préchargé par :** *(personne — ouvert à la demande)*.

Détail sorti de `session-tooling` (RM3037) pour tenir le budget de contexte : la **règle** — tout ce qui
change un état passe par l'outil PM, un trou se comble en créant le script — reste dans le module
préchargé et dans le tripwire #1. Ce qui suit est de la **consultation**.

### Couverture actuelle (à compléter au fil des trous identifiés)

| Domaine | Opération | Outil canonique |
|---|---|---|
| Tâche | créer | `pm-task-add.py` · `mmi-pm-task-add` (`--porcelain` = id nu sur stdout) |
| Tâche | changer le statut | `pm-task-status-update.py` · `mmi-pm-task-status-update` |
| Tâche | commenter | `pm-task-comment.py` · `mmi-pm-task-comment` |
| Tâche | lier (relates/depends/blocks) | `pm-task-link.py` · `mmi-pm-task-link` |
| Tâche | **déplacer vers un autre projet PM** (fiche + `.log` + `.reporting`, et `project_id` Redmine vérifié par relecture) | `pm-task-move.py <id> --to <client>/<projet>` (RM2866) |
| Tâche | description / checklist | `pm-task-description-update.py` |
| Tâche | estimation (CF prévisionnels) | `pm-task-metrics-push.py --estimate` |
| Tâche | mesure temps/tokens (hook) | `pm-task-tick.py` |
| Tâche | report conso → Redmine (time_entries + CF17) | `pm-task-report.py` |
| Donnée PM | commit+push des écritures de scripts | *(automatique — `pm_git.autocommit`, RM1834 ; **silencieux si ça passe**, RM2440 ; `--no-commit` pour débrayer)* |
| Donnée PM | **rattrapage** de ce qui traîne (édits libres : fiches, `.log.md`, CDC…) | *(automatique — chaque `pm_git.autocommit` d'un script embarque, dans un commit `pm(rattrapage): …` séparé, les fichiers non commités depuis **plus d'1 h** ; ni timer ni process dédié, RM3013 ; `git.sweep: false` / `git.sweep_after_min` ; journalisé catégorie `pm`)* |
| Repo | protection de branches (code **ou** core) | `pm-protect.py` (`--repo` · `--all-cores`) |
| Instance | **faire tourner un travail PÉRIODIQUEMENT** — jamais une ligne de crontab (RM2792) | `jobs.reference.yml` + `pm-scheduler.py list|check|history` |
| Instance | pont d'onboarding des workspaces (`AGENTS.md` + `CLAUDE.md`) | `pm-workspace-bridge.py` (nu = contrôle · `--install` · `--update`, RM1892) |
| Repo | promouvoir intégration → prod | `pm-promote.py` — ⚠ **transition** (RM2440), hors flux nominal |
| Tâche | démarrer la branche de ticket (+ CF GIT Branche) | `pm-branch-start.py` (`--worktree --print-cd` = chemin nu à `cd`) |
| Tâche | se (re)placer dans le worktree du ticket | `pm-task-cd.py` — `cd "$(pm-task-cd.py <id>)"` (RM2240) |
| Projet | cohérence des paires cross-projet (used_by/provided, implements) | `pm-doctor.py` |
| Tâche | sync depuis Redmine | `pm-task-sync.py` · `mmi-pm-task-sync` |
| Tâche | lister / afficher | `pm-task-list.py`, `pm-task-show.py` |
| Tâche | **reprendre sans sa session** (séances, prochaine étape notée, demandes retrouvées, état constaté du code) | `pm-task-brief.py <id> --reprise` (RM2998) |
| Contact | **annuaire de personnes** (ajout, fusion, recherche par adresse, migration) | `pm-contact.py` (RM2703) |
| Contact | rattacher à un client (rôle, titre) | `pm-client-contact.py` |
| Projet / client | créer / bootstrap | `pm-project-new.py`, `pm-project-bootstrap.py`, `pm-client-new.py` |
| Ticket Redmine (bas niveau) | note / fetch / tag IA / config | `redmine-post-note.py`, `redmine-fetch-*.py`, `redmine-tag-ia.py`, `redmine-config-check.py` |
| Session | worklog d'avancement | `pm-session-status.py` · `mmi-pm-session-status` |
| Session | **archiver les transcripts** (+ `history.jsonl`, worklogs) et surveiller que ça tourne | `pm-sessions-archive.py` (`--check`, `--install-timer`) (RM2997) |
| Machine | **sauvegarde ZFS** — snapshots au fil de l'eau, purge bornée, surveillance | `pm-zfs-backup.py` (`--status`, `--check`) (RM3023) · `knowledge/zfs/sauvegarde.md` |
| Courrier | **filtres Sieve d'une boîte** — lire, comparer, écrire (boîte vérifiée, validation serveur avant écriture, sauvegarde octet pour octet), activer, supprimer (jamais l'actif) | `pm-sieve.py list|get|diff|put|activate|delete|backups` (RM3171) · `knowledge/dovecot/sieve-karl.md` |
| MEP | **point de restauration ZFS pré-MEP** (tripwire #10) sur le bon hyperviseur, via atlas | `pm-snapshot.py <id> [--dry-run]` (RM2989) |
| Session | **événement notable** (secret exposé, refus, garde-fou, outillage en défaut, décision bloquante) | `pm-session-status.py notify` |
| Session | **demande du demandeur** (avant même de savoir si elle sera ticketée) | `pm-session-status.py request` |
| Session → tâche | **consigner les décisions** (questions tranchées / restées sans réponse) dans le journal du ticket | `pm-decisions.py persist <id>` |
| **Branches / repos / submodules** | créer la branche d'un ticket (+ CF GIT Branche) | `pm-branch-start.py` (livré RM1923 ; `--worktree`, `--take`) |
| **Commit + push conventionné** | message conventionné, push immédiat, base de version | **⚠ trou — pas de script dédié** : geste manuel encadré (cf. § « Commit + push systématique ») |

### Idiomes fréquents (évite de relancer `--help` à chaque session)

- **Contenu long / multi-ligne via stdin** : `pm-task-comment <id> --note - < note.md`,
  `redmine-post-note <id> --note -`, `pm-task-add --description -` (ou
  `--description-file <path>`), `pm-task-description-update <id> --set-from-file <path>`.
  Passer par stdin/fichier plutôt qu'un argument quoté évite AUSSI la protection
  Bash « newline + `#` » de Claude Code (validation à répétition sur les arguments
  multi-lignes contenant un dièse).
- **Transitions valides depuis le statut courant** : `pm-task-status-update <id> --list-next`
  (au lieu de deviner le flow d'états).
- **Auto-assignation** : `en_cours` auto-assigne au porteur (`--assign-to me` implicite) ;
  `--assign-to <id|me|author>` pour forcer, `--no-assign` pour débrayer.
- **Détection de projet** : si la détection cwd échoue ou est ambiguë,
  `--project entity/project` explicite (`pm-task-add`, `pm-task-list`, …).
- **Répétition sans risque** : `--dry-run` sur `pm-task-add`, `pm-task-status-update`,
  `pm-task-sync` — voir le diff avant d'écrire.
- **Script lancé depuis un worktree sans `.env`** : préfixer
  `PM_CORE_DIR=<racine du repo PM actif>` (sinon « ERREUR : aucun .env trouvé »).

## Le CYCLE DE SESSION — une procédure nommée (RM3162)

**Invocation :** « fais le cycle de session » (bouton **↻ Relancer** du cockpit, RM3159).
Le nom suffit : le texte vit ici, une seule fois, et s'amende par MR comme le reste des normes.

Pourquoi ce nom plutôt que « enchaîne » : *enchaîne* sert couramment à dire « continue ». Un mot qui
déclenche des fermetures et des mises en production ne doit pas pouvoir être écrit par hasard.

### Les quatre temps, dans cet ordre

1. **Constater** — ce qui est réellement déployé. Le core de prod suit `main` : ce qui y est mergé
   **est** en production, quel que soit le statut du ticket. C'est le statut qui retarde, pas le code.
2. **Fermer** ce qui est en prod depuis le cycle précédent et qui est bouclé.
3. **Mettre en prod** (promotion vers `main`) ce qui est fini, pour que le demandeur déploie et teste.
4. **Enchaîner** sur **un** ticket de la session, faisable sans arbitrage, livré de bout en bout —
   tests, MR, promotion, protocole de test. Dire lequel, et pourquoi lui.

**L'ordre n'est pas décoratif** : mettre en prod avant de fermer ferme ce qu'on vient d'y mettre.

### Ce qui ne se force pas

- **Les questions ouvertes.** Un ticket qui en porte reste ouvert, et on dit lesquelles. C'est le seul
  endroit où la réflexion non tranchée survit ; l'escamoter revient à la perdre. Le demandeur peut
  demander de passer outre — c'est alors sa décision, tracée dans la note.
- **Les critères d'acceptation non cochés** se passent outre en traçant le motif : ils décrivent
  souvent une hygiène passée, pas un travail inachevé.
- **Les tickets portés par une autre session vivante** (`pm_concurrent`) : deux agents sur un même
  ticket se disputent sa fiche, sa branche et son statut.
- **Un parent dont une sous-tâche est ouverte** : Redmine refuse *silencieusement* (PUT 204, statut
  inchangé). Ne pas s'acharner, le dire.

### Rendre compte

Trois chiffres, toujours : **fermés**, **mis en prod**, **écartés avec leur motif**. Un lot de deux
cents transitions ne laisse sinon aucune trace lisible, et personne ne peut vérifier ce qui a été
fait. Ce qui a été volontairement laissé de côté se nomme — un silence se lit comme un oubli.

### Si quelque chose cloche

Le dire **avant** d'agir, pas après. Le malentendu fondateur de cette procédure (« en prod » : le
statut, ou le code dans `main` ?) aurait coûté une phrase ; il a coûté deux passages et une
quarantaine de tickets fermés au mauvais moment.

## Grouper les appels d'outils — le premier poste de coût (RM3109, tripwire #20)

Détail du tripwire #20. La règle est **permanente** : il n'existe aucun moment
observable « je m'apprête à appeler un outil », c'est pourquoi elle est au KERNEL
et non derrière un déclencheur (critère `MAINTAINING.md` §6).

### Ce qui a été mesuré

Session d'étude réelle du 2026-09-11 (42 étapes, moteur claude-opus-5, 1 M de
fenêtre) :

| Poste | valeur |
|---|---|
| Socle payé au **1er** appel (prompt système + définitions d'outils + skills + CLAUDE.md + mémoire) | 50 538 tokens |
| Contexte relu **à chaque** appel d'outil (moyenne) | 105 504 tokens |
| Appels API | 80 |
| `cache_read` cumulé | 8 440 334 tokens |
| Coût | ≈ 8,07 $ |

Ventilation de la facture : `cache_read` **52 %**, raisonnement interne **17 %**,
écriture du cache **29 %**, texte produit **2 %**.

Deux conséquences contre-intuitives, et c'est pourquoi la règle se viole en
silence :

* **Ce qu'on lit coûte moins cher que le nombre de fois où l'on s'arrête.** Lire
  le KERNEL (26 Ko) coûte une fois ~8 k tokens ; trois `ls` d'un même dossier
  coûtent 1,5 k de sortie **plus trois relectures complètes** — davantage.
* **Le raisonnement reste dans le contexte.** Il est facturé une première fois en
  sortie, puis **relu à chaque appel suivant**. Un raisonnement de 3 k au 5ᵉ appel
  est relu 37 fois.

### Les idiomes

```bash
# ✅ séquentiel : UN appel, sections lisibles
git status --short; echo "=== BRANCHE ==="; git branch --show-current

# ✅ filtre pensé d'emblée
ls scripts/ | grep -v '^test_'          # et non : ls, puis head, puis tail

# ✅ plan d'abord, section ensuite
grep -n '^#\+ ' doc.md                  # puis sed -n 'A,Bp' doc.md

# ❌ trois appels pour un dossier
ls scripts/ | head -100 ; # puis ls scripts/ | tail -80 ; # puis ls | grep -v test_
```

Côté agent : plusieurs `tool_use` **indépendants** émis dans une **même** réponse
s'exécutent en parallèle pour le prix d'une seule relecture. C'est la forme à
préférer chaque fois qu'aucune commande n'attend le résultat d'une autre.

### Quand le groupage est impossible

Quand la commande N+1 **dépend** du résultat de N : capturer un RM-id avant de
créer sa branche (tripwire #13), lire un chemin avant de l'ouvrir, vérifier un
état avant d'agir dessus. Dans ces cas, l'aller-retour est le prix de la
correction — on ne devine pas pour économiser un appel. La parade n'est pas de
fusionner à tout prix, mais de **chaîner dans un seul shell** quand c'est
possible (`ID=$(outil --porcelain) && autre-outil "$ID"`).
