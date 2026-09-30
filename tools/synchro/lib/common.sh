#!/bin/bash
# common.sh — configuration infra PARTAGÉE par tous les environnements.
# Sourcé par sync.sh avant la conf d'environnement.
# Ne contient AUCUN secret en clair : le mot de passe admin MySQL local est
# résolu au runtime depuis le vault déclaré (voir helpers.sh::resolve_secret).

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
#   - sur un conteneur de test distant sans ~/.my.cnf, définir une URI de secret
#     (résolue au runtime, jamais écrite sur disque), p.ex. :
#     export MYSQL_ADMIN_SECRET="secret://vw-ipro/<collection>/<item>"
#     (la forme historique vaultwarden://<org>/<coll>/<item> reste valide)
export MYSQL_ADMIN_SECRET="${MYSQL_ADMIN_SECRET:-}"

# Utilisateur PHP-FPM (pour purge de cache appartenant à www).
# En dev local c'est l'utilisateur courant (mathieu) ; sur un conteneur de test
# distant ça peut différer → surchargeable dans la conf d'environnement.
export PHP_USER="${PHP_USER:-mathieu}"

# IP du client (host LXC) à whitelister en maintenance PrestaShop
export CLIENT_USER_IP="10.0.3.1"

# Options passées à ssh et rsync par lib/db.sh et lib/<type>.sh. Vides par défaut :
# le framework tourne sous `set -u`, sans ces défauts toute conf d'environnement qui
# omet de les déclarer échoue sur « SSH_OPTS: unbound variable » avant même de
# contacter la production. Une conf reste libre de les surcharger.
export SSH_OPTS="${SSH_OPTS:-}"
export RSYNC_OPTS="${RSYNC_OPTS:-}"

# ── Paramètres PROPRES À L'INSTANCE — RM3221 ──────────────────────────────────
# Le domaine des environnements de recette dépend de l'instance qui fait tourner
# ce framework, pas du framework : le repo PM est fédérable, et une autre instance
# n'a ni le même domaine ni le même conteneur de dev. Ces valeurs vivent donc dans
# le `pm.env` de l'instance (racine du repo PM) — la config d'instance NON SECRÈTE et
# non versionnée qui porte déjà GITLAB_URL, REDMINE_URL, ZABBIX_URL (RM2438). Pas de
# fichier de conf propre au framework : un troisième emplacement pour la même nature
# de paramètre serait le suivant qu'on oublie de renseigner.
#
# Une conf d'environnement écrit DOMAIN="<site>.${TEST_DOMAIN}", jamais un domaine en
# dur. Une variable déjà présente dans l'environnement l'emporte sur pm.env.
#
# pm.env est LU, pas sourcé : on n'y prend que les trois clés utiles, sans exécuter
# son contenu ni importer ses autres clés dans l'environnement de la synchro.
# Chemin surchargeable par SYNCHRO_INSTANCE_ENV (tests, instance atypique).
SYNCHRO_PM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SYNCHRO_INSTANCE_ENV="${SYNCHRO_INSTANCE_ENV:-$SYNCHRO_PM_ROOT/pm.env}"
_pm_env_get() {
  [ -r "$SYNCHRO_INSTANCE_ENV" ] || return 0
  sed -nE "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*[\"']?([^\"'#]*[^\"'#[:space:]])?[\"']?[[:space:]]*(#.*)?\$/\1/p" \
    "$SYNCHRO_INSTANCE_ENV" | tail -1
}
# Défauts vides plutôt qu'absents : sous `set -u`, une conf qui cite ${TEST_DOMAIN}
# sans valeur échouerait sur « unbound variable », message qui ne dit pas quoi faire.
# Vide, le domaine se termine par un point et sync.sh l'explique.
export TEST_DOMAIN="${TEST_DOMAIN:-$(_pm_env_get TEST_DOMAIN)}"
export TEST_HOST="${TEST_HOST:-$(_pm_env_get TEST_HOST)}"
export DEV_DOMAIN="${DEV_DOMAIN:-$(_pm_env_get DEV_DOMAIN)}"
