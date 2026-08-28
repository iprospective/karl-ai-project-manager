<?php
/**
 * Override "domaine-agnostique" — DEV/TEST UNIQUEMENT. (4/4)
 *
 * Deux nuisances du back-office quand on sert un worktree sur un domaine
 * alternatif en partageant la base d'un autre env :
 *
 * 1. PrestaShop compare `$_SERVER['HTTP_HOST']` à `$shop->domain` et affiche
 *    « Vous êtes actuellement connecté avec le nom de domaine suivant… »
 *    (AdminDashboardController::getWarningDomainName). L'objet shop est rechargé
 *    depuis la base pendant le cycle admin, d'où l'écart. On le réaligne sur
 *    l'hôte courant : le message disparaît à la source, et les liens front
 *    générés depuis le BO pointent sur l'env de test — ce qu'on veut.
 *
 * 2. Le module ps_accounts compare l'URL de la boutique à celle enregistrée dans
 *    le compte PrestaShop et affiche « Action requise : confirmez l'URL de votre
 *    boutique ». Ce bandeau-là n'est PAS lié au vhost : il compare à
 *    www.pisceen.com et apparaît donc aussi sur l'env de dev. Il est masqué ici
 *    parce qu'un env de dev n'a rien à confirmer auprès du compte de production —
 *    surtout pas depuis un domaine de test.
 *
 * ⚠ NE JAMAIS COMMITER / DÉPLOYER EN PROD. Fichier LOCAL au worktree
 * (.git/info/exclude). Vider var/cache après dépôt. Skill mmi-presta-dev-vhost.
 */
class AdminController extends AdminControllerCore
{
    public function init()
    {
        parent::init();

        if (($host = self::rmDevAltHostAdmin()) !== null && isset($this->context->shop)) {
            $this->context->shop->domain = $host;
            $this->context->shop->domain_ssl = $host;
        }
    }

    public function initContent()
    {
        parent::initContent();

        if (self::rmDevAltHostAdmin() === null) {
            return;
        }

        // Les notifications ps_accounts sont injectées en AJAX après le rendu :
        // le CSS est le seul point d'accroche qui les attrape à coup sûr.
        $this->content = '<style>'
            . '.acc-alert,.acc-alert-warning,.acc-alert-danger{display:none!important}'
            . '</style>'
            . $this->content;
    }

    /**
     * @return string|null hôte courant s'il est inconnu de ps_shop_url ; null sinon
     */
    protected static function rmDevAltHostAdmin()
    {
        if (Tools::isPHPCLI()) {
            return null;
        }
        $host = Tools::getHttpHost(false, false, true);
        if (!$host) {
            return null;
        }
        $known = (int) Db::getInstance()->getValue(
            'SELECT COUNT(*) FROM `' . _DB_PREFIX_ . 'shop_url`
             WHERE `domain` = \'' . pSQL($host) . '\' OR `domain_ssl` = \'' . pSQL($host) . '\''
        );

        return $known ? null : $host;
    }
}
