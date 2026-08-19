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

## Étapes (sur l'hôte, en root)

1. **Créer le compte de rôle** (nologin-like, home partagé) :
   ```
   sudo useradd -M -d /zfs/workspaces -s /bin/bash <dev>-pm
   ```
2. **Groupe `pm`** — le compte de rôle ET le dev humain :
   ```
   sudo usermod -aG pm <dev>-pm
   sudo usermod -aG pm <dev>          # le dev humain aussi
   getent group pm                    # vérif : doit lister <dev>-pm et <dev>
   ```
   (Le dev doit rouvrir sa session pour que l'appartenance au groupe prenne effet.)
3. **`umask 002`** pour le compte de rôle (écriture de groupe par défaut) — dans son
   `~/.bashrc`/`~/.profile`, ou via le profil PM déjà en place pour `mathieu-pm`.
4. **Perso `~/.config/mmi-pm/.env`** du dev — ses propres clés (jamais commité, `600`) :
   ```
   install -d -m 700 ~<dev>/.config/mmi-pm
   # y déposer REDMINE_USER_MAIN_API_KEY, GITLAB_*_TOKEN perso, etc.
   chmod 600 ~<dev>/.config/mmi-pm/.env
   chown <dev>:<dev> ~<dev>/.config/mmi-pm/.env
   ```
5. **Appliquer/réparer les perms** (idempotent) — dossiers de chaque workspace projet,
   puis state + fichiers env communs du core :
   ```
   pm-perms.py --apply <workspace>            # par workspace projet (en pm ou root)
   sudo pm-perms.py --apply --var <workspace> # + var/ (state) + pm.env/.env → root:pm 640
   ```
   `pm-perms` sans `--apply` = dry-run (liste les écarts, exit 1). Relancer jusqu'à
   « ✓ conforme ».

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
