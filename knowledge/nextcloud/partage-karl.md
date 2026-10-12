# Partager un fichier via le Nextcloud du compte karl (RM3447)

Un livrable à partager (rapport, schéma, étude) ne devient **jamais** un artefact claude.ai :
il vit dans le repo (`plans/`, `docs/`) ou dans `<core>/.mmi-pm/docs/partages/<AAAA-MM-JJ>-<slug>.md`,
puis est déposé sur le Nextcloud du compte karl par `pm-nextcloud-put --share`. L'URL va dans la note
Redmine. Norme : module `redmine-sync` § « Fichier à partager ».

## Ce qui est en place

- Outil : `scripts/pm-nextcloud-put.py` (WebDAV `MKCOL` récursif + `PUT`, lien public par l'API OCS ;
  `urllib`, aucune dépendance). Tests hors ligne : `scripts/test_pm_nextcloud_put.py`.
- Fournisseur : instance `nc-ipro` de `pm.config.yml :: providers.servers` (`https://cloud.iprospective.fr`).
- Dépôt : `<racine>/<client>/<projet>/[<dest>/]<AAAA-MM-JJ>-<slug>.<ext>` ; `--name` force le nom.
- Secret : jamais affiché ni loggué ; résolu par `scripts/resolve-secret.sh` (URI `secret`), repli
  `NEXTCLOUD_APP_PASSWORD` pour un essai manuel.
- Pas de conversion md → pdf : aucun convertisseur (pandoc, soffice) n'existe au repo. Un `.md` est
  déposé tel quel, Nextcloud le rend.
- **Format (consigne Mathieu, 2026-10-12)** : **pas de PDF sauf s'il n'y a pas de choix** — un texte se
  dépose en `.md`, un document bureautique dans son format natif (`.docx`, `.xlsx`). Le PDF est
  accepté **quand il y a des visuels** (schémas, images : ex. les schémas SVG du cahier CalyPrint,
  exportés par `rsvg-convert -f pdf`, réunis par `pdfunite`), parce qu'il garantit le rendu.

## État réel (confirmé par Mathieu le 2026-10-12)

- **Compte** : `karl` sur nc-ipro. Identifiants dans l'item Vaultwarden **existant**
  `agents/karl@cloud.iprospective.fr` (username = karl) ; URI configurée
  `secret://vw-ipro/agents/karl@cloud.iprospective.fr#password`, résolue par `resolve-secret.sh`
  (vault déverrouillé requis, sinon code 2). Rien à créer.
- **Racine** : `Partages/` existe côté Nextcloud.
- **Convention validée** : `Partages/<client>/<projet>/<date>-<slug>.<ext>`. Le dossier client existant
  porte une **majuscule** (`Partages/Calicote/`) : l'outil résout client et projet **sans tenir compte
  de la casse** (PROPFIND Depth 1) et, s'il doit créer le client, lui met une majuscule initiale.
- **Partage** : lien public en lecture seule, échéance par défaut **14 jours** (`share_expire_days: 14`
  de l'instance ; `--expire J` l'emporte). Un fichier déjà partagé garde son lien : l'outil le réutilise
  (et le dit) au lieu d'en créer un second.
- **Précédent manuel** (Calicote, 06/10) : `Partages/Calicote/2026-10-06-etude-labels-allergenes.md`,
  sans sous-dossier projet, lien `https://cloud.iprospective.fr/s/AzQ4KTY2945HXFX` (expire le
  2026-10-20). L'outil déposera la même étude dans `Partages/Calicote/prestashop/` ; l'ancien fichier
  n'est pas supprimé (décision de Mathieu).

## Exemples

```bash
# voir ce qui serait fait (aucun réseau, aucun secret)
scripts/pm-nextcloud-put.py --dry-run --project calicote/prestashop \
    /zfs/workspaces/calicote/prestashop/.mmi-pm/docs/partages/2026-10-06-etude-labels-allergenes.md

# déposer et obtenir le lien (14 jours par défaut ; --expire 30 pour changer)
URL=$(scripts/pm-nextcloud-put.py --share --porcelain docs/rapport.md)

# sous-dossier et nom imposé, depuis le cwd d'un projet PM
scripts/pm-nextcloud-put.py --dest schemas --name schema-reseau.svg --share schema.svg

# essai manuel sans vault
NEXTCLOUD_APP_PASSWORD=… scripts/pm-nextcloud-put.py --share fichier.md --project client/slug
```

## Codes retour

| Code | Sens | Que faire |
|---|---|---|
| 0 | déposé (et lien créé si `--share`) | — |
| 2 | vault verrouillé | demander à Mathieu `unlock-vault.sh` (jamais son secret) |
| 3 | erreur réseau ou HTTP (le statut figure dans le message) | 401 = mauvais mot de passe d'application ; 404 sur le partage = chemin ; 423 = fichier verrouillé |
| 4 | configuration manquante ou usage invalide | instance inconnue, pas de secret, projet ambigu (`--project client/slug`), fichier absent |

Re-déposer le même nom écrase le fichier (le lien de partage déjà émis reste valable et est réutilisé par `--share`).
