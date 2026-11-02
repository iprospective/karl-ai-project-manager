# PrestaShop — copies non-prod (dev, recette, préprod) : ce qu'on neutralise

Une copie de PrestaShop (synchro prod → local, clone de ticket, recette distante) porte
**tout** ce que la production a configuré : identités cloud, identifiants marchands, pixels
publicitaires, domaine. Laissés tels quels, ils font agir la copie **au nom de la prod**.
Cette fiche dit ce qu'on neutralise, pourquoi, et avec quel outil.

## L'outil : `tools/env-runtime/presta-nonprod-sql.sh`

Il **émet du SQL** sur stdout et n'ouvre aucune connexion : l'appelant choisit la base.
Il est appelé automatiquement par la synchro (`tools/synchro/lib/presta.sh`) et par
`pm-env-session` (clone de ticket). Pour une **recette distante**, on le lance à la main :

```bash
tools/env-runtime/presta-nonprod-sql.sh --domain <nom>.test.iprospective.fr \
  | ssh <hôte> "mysql <base>"
# puis purger var/cache/ du site : ps_configuration et la liste des hooks sont en cache
```

Idempotent. Il refuse un `--domain` qui ne ressemble pas à du dev/test (`--force` pour un
domaine atypique) : joué sur une production, il la casse. Détail des options :
`--help` et [`tools/env-runtime/README.md`](../../tools/env-runtime/README.md).

⚠ **Base partagée entre plusieurs sites** (cas calicote : `calicote_test2` sert trois
docroots) : ne pas passer `--domain` si les sites ne partagent pas le même nom — il
réécrit `ps_shop_url`. Les modules et identités, eux, se neutralisent sans risque.

## Ce qui est neutralisé, et pourquoi

| Quoi | Pourquoi | Depuis |
|---|---|---|
| Domaine (`ps_shop_url`, `PS_SHOP_DOMAIN(_SSL)`) | sinon PrestaShop redirige (301) vers le domaine de la prod | RM2932 |
| Identités cloud (`PS_ACCOUNTS%`, `PS_PSX_%`, `PS_EVENTBUS%`, `PS_METRICS%`) | bandeau « confirmez l'URL » ; et le bouton « confirmer » **déplace l'identité de la prod** sur le domaine de test | RM2932 |
| Compte PayPal marchand (`PS_CHECKOUT_PAYPAL_%`) | une copie ne doit pas pouvoir encaisser au nom du client | RM2932 |
| Modules cloud (`ps_accounts`, `ps_eventbus`, `ps_metrics`, `ps_checkout`, `psaddonsconnect`) | ils dialoguent avec les services PrestaShop au nom de la boutique d'origine | RM2932 |
| **Modules de suivi publicitaire et d'audience** (`facebookproductad`, `gadwordstracking`, `ps_googleanalytics`, `cdc_googletagmanager`, `ps_facebook`, `psxmarketingwithgoogle`) | leurs pixels gardent les identifiants de la prod : chaque visite d'une copie compte dans les statistiques publicitaires et d'audience du client | RM3619 |

### Le suivi publicitaire (RM3619)

**Incident fondateur — RM3616 (calicote, 2026-11-02).** Deux recettes calicote ont été
indexées par Google. Pendant deux semaines, robots et vrais visiteurs (34 arrivées depuis
Google, deux paniers remplis) ont déclenché à chaque page le pixel Meta
(`facebookproductad`) et le suivi Google Ads (`gadwordstracking`) **avec les comptes de la
production**.

- On **désactive** le module (`ps_module.active = 0`), on ne touche pas à sa
  configuration : réactiver le suivi pour le recetter lui-même reste un geste simple.
  `--keep-tracking` laisse ces modules en place ; `--tracking-modules "<a b>"` remplace la
  liste.
- Un module de suivi absent de la liste par défaut (un autre pixel, un autre tag) se
  désactive avec `--tracking-modules`, **et s'ajoute à la liste par défaut** du script
  dans la foulée : la prochaine copie doit en hériter sans y penser.
- Un module **installé mais non rattaché à la boutique** (`ps_module_shop` vide) ne
  s'exécute déjà pas ; le désactiver ne coûte rien et protège d'un rattachement futur.

**Vérifier** sur la page d'accueil de la copie (après purge du cache) :

```bash
curl -s https://<copie>/fr/ | grep -ciE 'fbq\(|connect\.facebook\.net|googletagmanager\.com|gtag\(|googleadservices'
# attendu : 0
```

Une copie en maintenance (503) ne sert pas la page : vérifier depuis une IP de
`PS_MAINTENANCE_IP`, ou en base (`SELECT name, active FROM ps_module WHERE …`).

## Ce qui n'est PAS dans ce script

- **L'indexation par les moteurs** se règle au niveau du serveur web, pas de PrestaShop :
  `X-Robots-Tag: noindex, nofollow` posé sur tout l'Apache des conteneurs de dev/test
  (RM3615) et contrôlé chaque jour (RM3614). Ne pas compter sur `robots.txt` : un
  `Disallow: /` empêche Google de lire le `noindex`.
- **Le mode maintenance** (`PS_SHOP_ENABLE` + `PS_MAINTENANCE_IP`) : géré par la synchro
  pour le local, voir [`mep.md`](mep.md) pour la MEP.
