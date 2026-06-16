---
schema_version: "1.10.0"
# Liste des environnements de ce projet (ou client si appliqué au niveau client).
# Chaque env est indépendant — pas tous les projets ont tous les envs.
environments:
  - name: dev                  # local | dev | test | staging | prod | demo | qa | sandbox | <custom>  (preprod = alias de staging)
    status: active             # active | disabled | planned
    url:                       # URL publique de l'env, ex: https://dev.calicote.test
    admin_url:                 # URL d'admin si distincte, ex: https://dev.calicote.test/admin
    ssh_alias:                 # alias ~/.ssh/config — À UTILISER DE PRÉFÉRENCE, ex: calicote-presta
    ssh_target:                # cible SSH explicite user@hostname (fallback), ex: calicote@srv1.sfy-gestion.com
    host:                      # identité machine hôte (indicatif, préfixe logs distants), ex: sfy-srv1
    user:                      # user système, ex: calicote
    app_path:                  # chemin code sur l'host, ex: /home/calicote/public_html
    branch:                    # branche git associée, ex: dev
    fpm_pool:                  # nom du pool FPM si PHP, ex: calicote-74
    logs:
      app:                     # chemin relatif/absolu, ex: var/logs/dev.log
      fpm:                     # ex: /var/log/php/calicote-74.error.log
      access:                  # access log nginx, préfixé host si distant — prod OVH : <host>:/var/log/nginx/<domaine>_access.log
    secrets_source:            # vaultwarden://<org>/<collection>/<item>  (ou null)
    post_deploy:               # commandes shell à lancer APRÈS un déploiement sur cet env — DÉCLARATIF (non auto-exécuté), chemins ABSOLUS obligatoires
      # - "rm -rf <app_path>/var/cache/*"        # ex. PrestaShop : purge cache (overrides/templates) — JAMAIS de chemin relatif (viserait /var/cache)
    notes:                     # ex: "Hot-reload activé, données dé-anonymisées"
  # - name: test
  # - name: staging          # env de non-régression avant MEP (alias historique : preprod)
  # - name: prod

# Tableau des variables d'environnement attendues par l'app (sans les valeurs).
# Sert de référence pour onboarder un nouvel env ou un nouveau dev.
env_vars:
  # - name: DATABASE_URL
  #   description: "Connexion BDD principale"
  #   envs: [dev, test, staging, prod]
  # - name: STRIPE_SECRET
  #   description: "Clé API Stripe (mode test ou live selon env)"
  #   envs: [staging, prod]
---

## Procédure de déploiement par env

<!-- Liens vers deployment.md le cas échéant, ou commandes spécifiques :
     - dev   : `git pull` côté serveur (auto via cron)
     - prod  : MR validée + tag + déploiement manuel via script `./deploy.sh prod`
-->

## Accès et credentials

<!-- Où sont rangés les secrets, qui a les accès.
     Convention iprospective :
     - Pointeur vers Vaultwarden (vaultwarden://<org>/<collection>/<item>) dans `secrets_source`
     - Résolu à l'exécution par `scripts/resolve-secret.sh`, jamais commité

     Voir norms/NORMS.md § "Gestion des secrets — Vaultwarden" pour les détails.
-->

## Spécificités par env

<!-- Différences fonctionnelles entre envs (feature flags actifs, jeux de données,
     monitoring activé, throttling, etc.) -->
