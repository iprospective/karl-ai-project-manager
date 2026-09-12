---
type: procedure
product: zfs
created: 2026-09-12
refs: [RM3023, RM2997, RM2989]
---

# ZFS — sauvegarde de la machine (snapshots au fil de l'eau)

## Pourquoi

Le 2026-09-06, `zfs/root/home` (= `/home`) n'avait **qu'un seul snapshot**,
`@now` du **17 avril 2025**, et la machine n'avait **aucune** sauvegarde externe
(ni borg, ni restic, ni rsnapshot, ni rclone configuré, ni ligne cron). Quand
42 transcripts de session ont été effacés par la rétention par défaut de Claude
Code (RM2997), il n'existait **aucun recours** au niveau du système de fichiers.

## Ce qui tourne

`pm-zfs-backup.py --tick`, **greffé sur `pm-task-report`** — le cron de l'hôte
qui tourne déjà toutes les 30 minutes. Pas de timer dédié : sur un portable, un
horaire fixe manque la moitié de ses créneaux ; la question utile est « le
dernier snapshot a-t-il plus d'une heure ? », pas « est-il minuit ? ».

| | |
|---|---|
| Politique | `pm.config.yml` → `zfs_backup:` (datasets, seaux, seuil d'alerte) |
| Nommage | `pm-auto-<seau>-<AAAAMMJJTHHMM>` |
| Seaux | `hourly` ×24 · `daily` ×14 · `weekly` ×8 · `monthly` ×6 |
| Empreinte | `{state_dir}/zfs-backup.json` — sur `/zfs/workspaces`, donc lisible depuis le conteneur |
| Surveillance | `_envchk_zfs_backup` dans karl-agent (pastille cockpit, niveau `error`) |

## Les droits : rien de nouveau

Tout passe par **`pm-zfs-snap.sh`**, guichet sudo NOPASSWD **déjà en place**,
root-owned, dont RM3023 a élargi le périmètre (`zfs/workspaces` → + `zfs/root`,
`zfs/lxc`, `zfs/documents`). Ses deux gardes rendent l'élargissement tenable :
le nom doit passer un charset strict, et `destroy` ne peut viser qu'un
`dataset@snapshot` — **jamais un dataset nu**.

L'utilisateur `mathieu` a par ailleurs une délégation `zfs allow` directe sur
`zfs/workspaces` (`mount,snapshot`) — elle permet de **créer** mais pas de
**détruire** : c'est le guichet sudo qui fait les deux.

## Deux gardes de la purge, à ne pas retirer

1. **Seuls les noms `pm-auto-…` sont candidats.** Un snapshot posé à la main
   (pré-MEP, migration de workspace) est un point de restauration délibéré, pas
   un déchet à ramasser.
2. **Un seau absent de la politique n'est pas purgé.** Sinon retirer une ligne
   de config effacerait, au tick suivant et en silence, tout son historique.

## Ce que ça ne protège PAS

Un snapshot vit **sur le même disque**. Il couvre l'effacement, l'écrasement et
la bêtise ; il ne couvre **ni la panne de disque, ni le vol, ni l'incendie** —
et la machine est un portable. La réplication hors machine (`zfs send` vers
srv3/4/5) reste à faire : c'est un ticket à part, et tant qu'il n'est pas fait,
il faut le dire ainsi plutôt que se croire sauvegardé.

## Gestes

```sh
pm-zfs-backup.py --status              # ce qui existe, par dataset et par seau
pm-zfs-backup.py --check               # sort 1 si ça a décroché
pm-zfs-backup.py --run --verbose       # forcer une passe
pm-zfs-backup.py --run --only zfs/root --dry-run    # essai ciblé, sans empreinte
sudo pm-zfs-snap.sh list               # tous les snapshots du périmètre
```

Restaurer un fichier : `/<point de montage>/.zfs/snapshot/<snap>/<chemin>` —
lecture seule, on y copie depuis, on n'y écrit pas.
