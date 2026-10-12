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

## À CONFIRMER / À FAIRE par Mathieu (valeurs posées dans `pm.config.yml`, non vérifiées)

1. **Compte** : `providers.servers.nc-ipro.user: karl` — le compte existe-t-il sur nc-ipro ?
2. **Mot de passe d'application** : Nextcloud (connecté en karl) → Paramètres → Sécurité → « Créer un
   nouveau mot de passe d'application » (nom : `pm-nextcloud-put`).
3. **Item Vaultwarden** : le créer dans la collection agents, `agents/nextcloud-karl`, champ mot de
   passe = le mot de passe d'application (URI configurée : `secret://vw-ipro/agents/nextcloud-karl#password`).
4. **Dossier racine** : `providers.servers.nc-ipro.root: Partages` — dossier existant côté karl (sinon
   il est créé par `MKCOL`) ; confirmer le nom.
5. **Forme du partage** : lien public en lecture seule (défaut de l'outil, `--expire J` pour l'échéance)
   — ou dossier partagé nominativement : à trancher.

## Exemples

```bash
# voir ce qui serait fait (aucun réseau, aucun secret)
scripts/pm-nextcloud-put.py --dry-run --project calicote/prestashop \
    /zfs/workspaces/calicote/prestashop/.mmi-pm/docs/partages/2026-10-06-etude-labels-allergenes.md

# déposer et obtenir le lien (30 jours)
URL=$(scripts/pm-nextcloud-put.py --share --expire 30 --porcelain docs/rapport.md)

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

Re-déposer le même nom écrase le fichier (le lien de partage déjà émis reste valable ; un nouveau
`--share` crée un nouveau lien).
