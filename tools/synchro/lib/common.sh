#!/bin/bash
# common.sh — configuration infra PARTAGÉE par tous les environnements.
# Sourcé par sync.sh avant la conf d'environnement.
# Ne contient AUCUN secret en clair : le mot de passe admin MySQL local est
# résolu au runtime depuis Vaultwarden (voir helpers.sh::resolve_secret).

# Racine workspace (bind-mount ZFS identique host/conteneur) — où vivent les sites
# à synchroniser. Indépendant de l'emplacement de ce framework (qui se localise via
# son propre dossier dans sync.sh).
export WORKSPACE_ROOT="/home/workspaces"
export TMP_PATH="$WORKSPACE_ROOT/tmp"

# Serveur MySQL local (conteneur LXC dev) — cible des imports
export MYSQL_HOST="10.0.3.11"
export MYSQL_ADMIN_USER="admin"
# Mot de passe admin MySQL local :
#   - vide (défaut) → on s'appuie sur le ~/.my.cnf de l'utilisateur (root) ; cas dev local.
#   - sur un conteneur de test distant sans ~/.my.cnf, définir une URI Vaultwarden
#     (résolue au runtime, jamais écrite sur disque), p.ex. :
#     export MYSQL_ADMIN_SECRET="vaultwarden://iProspective/<collection>/<item>"
export MYSQL_ADMIN_SECRET="${MYSQL_ADMIN_SECRET:-}"

# Utilisateur PHP-FPM (pour purge de cache appartenant à www).
# En dev local c'est l'utilisateur courant (mathieu) ; sur un conteneur de test
# distant ça peut différer → surchargeable dans la conf d'environnement.
export PHP_USER="${PHP_USER:-mathieu}"

# IP du client (host LXC) à whitelister en maintenance PrestaShop
export CLIENT_USER_IP="10.0.3.1"
