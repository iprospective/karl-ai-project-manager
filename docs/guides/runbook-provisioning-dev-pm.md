# Runbook — provisionner un développeur PM (`<dev>-pm`)

> Couche **multi-utilisateur OS** du PM (RM2438 / T6 RM2502). À exécuter à l'arrivée
> d'un nouveau développeur devant écrire les données communes (tâches, dépôts `*-core`,
> docs). Conception : `docs/cdc/…convergence-forge-multiuser` §3.4.

## Modèle (rappel)

- **Comptes de rôle `<dev>-pm`** (modèle `mathieu-pm`, uid 1007, comme `service`/`*-www`),
  membres d'un **groupe `pm`**. Le dev humain (`<dev>`) est lui aussi membre de `pm`.
- **Données communes** : dossiers de churn en **setgid `2770`/`2775` groupe `pm`**,
  bares en **`core.sharedRepository=group`** → écriture directe multi-`<dev>-pm`, **sans
  sudo**, git multi-user natif. Squelette (racine, `repos/`) en `2750` (non group-writable).
- **Secrets 3 niveaux** :
  - **perso** `~/.config/mmi-pm/.env` — **`600`, `<dev>-pm`** — clés API/git personnelles
    (attribution Redmine/GitLab par dev) ;
  - **instance** `pm.env` du core — **`640 root:pm`**, NON-secret (URLs, ids de CF, chemins) ;
  - **commun** `.env` du core — **`640 root:pm`**, secrets de service / fallback karl.
    Groupe `pm` car **le PM doit lire config+secrets communs pour tourner** (crons, tooling).
- **Privilège = `sudo`→`root`** (pas de compte `karl-sudo` : divergence actée vs CDC) :
  écrire la prod `.mmi-pm-core` (root-owned), merger `main` protégée (RM2030), roter les
  tokens partagés, systemd/cron.

## Étapes — un seul outil (RM3208)

Le compte PM d'un développeur est **un seul objet** : compte de rôle système, groupe `pm`, compte du
cockpit (les comptes du cockpit sont ceux du CLI) et profil. Tout se fait par `mmi-pm user`, idempotent :

```bash
sudo mmi-pm user add <dev> --dry-run          # le plan : ce qui manque, rien d'écrit
sudo mmi-pm user add <dev> --password-prompt  # compte cockpit avec mot de passe (sinon : sans session cockpit)
sudo mmi-pm user add <dev> --pm-gid 1008      # si le groupe pm n'existe pas encore (ids fixes hôte ↔ conteneur)
```

Ce que fait `add`, dans l'ordre, en sautant ce qui existe déjà :
1. groupe `pm` (créé s'il manque) ;
2. compte de rôle `<dev>-pm` (`useradd -M -d $WORKSPACES_ROOT -s /bin/bash`) ;
3. `<dev>-pm` **et** `<dev>` dans le groupe `pm` (le dev doit rouvrir sa session) ;
4. compte PM au registre `var/karl-users.json` ;
5. gabarit `~<dev>/.config/mmi-pm/.env` (dossier 700, fichier 600, **jamais écrasé**) : le dev y pose ses
   propres clés (`REDMINE_API_KEY`, jetons forge) — ses actions partent sous son identité ;
6. skills PM et hooks Claude Code, sous le compte du dev.

Le compte humain `<dev>` doit exister avant : le PM ne crée pas de personnes. Le mot de passe ne passe
jamais en argument (`--password-stdin` ou `--password-prompt`).

Retirer l'accès : `sudo mmi-pm user disable <dev>` (compte désactivé, appareils révoqués, sortie du groupe
`pm` — réversible par `enable`). Supprimer : `sudo mmi-pm user remove <dev>` (le compte de rôle n'est
supprimé qu'avec `--purge-os` ; le compte humain, jamais). État : `mmi-pm user list`.

Reste à la main, **par workspace** et non par utilisateur : appliquer le modèle de droits
(`pm-perms.py --apply <workspace>`, `sudo pm-perms.py --apply --var <workspace>`), et le `umask 002` du
compte de rôle.

## Vérifications

- `getent group pm` liste bien `<dev>-pm` (et `<dev>`).
- `id <dev>-pm` montre le groupe `pm`.
- Les fichiers env communs du core sont en **`640 root:pm`** :
  `stat -c '%A %U:%G %n' <core>/pm.env <core>/.env`.
- Test d'écriture multi-user : depuis un `<dev>-pm`, un `git commit` dans un bare
  `core.sharedRepository=group` passe **sans sudo** et le fichier résultant est
  group-writable (`umask 002`).
- Aucun dossier de churn ne porte le **sticky bit** (`pm-perms` le signale/retire) —
  sinon `atomic_write` (`os.replace`) échoue en EPERM pour un writer non-propriétaire
  (bug RM2438).

## Anti-régression

`pm-perms` est l'**enforcer unique et committé** du modèle (remplace les runbooks
scratchpad éphémères, cause de dérive). Le relancer après toute opération douteuse
(migration, restauration, création de worktree en masse) ou périodiquement.
