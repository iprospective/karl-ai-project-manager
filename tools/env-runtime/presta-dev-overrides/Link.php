<?php
/**
 * Override "domaine-agnostique" — DEV/TEST UNIQUEMENT. (3/3, avec Shop.php et ShopUrl.php)
 *
 * Volet BACK-OFFICE. Les deux premiers volets suffisent au front, mais pas à
 * l'admin : pendant le cycle `$kernel->handle()` de `admin/index.php`, l'objet
 * shop du contexte est REchargé depuis la base, ce qui écrase le domaine forcé
 * par Shop::initialize(). `Link::getAdminBaseLink()` lit `$shop->domain` et
 * reconstruit donc une URL sur le domaine canonique — d'où la redirection du
 * back-office vers l'env principal, alors que le RequestContext Symfony, lui,
 * porte bien l'hôte de test.
 *
 * On corrige au point d'usage plutôt qu'en amont : plus simple à raisonner, et
 * sans risque de casser la résolution du shop.
 *
 * ⚠ NE JAMAIS COMMITER / DÉPLOYER EN PROD. Fichier LOCAL au worktree
 * (.git/info/exclude). Vider var/cache après dépôt. Skill mmi-presta-dev-vhost.
 */
class Link extends LinkCore
{
    public function getAdminBaseLink($idShop = null, $ssl = null, $relativeProtocol = false)
    {
        $base = parent::getAdminBaseLink($idShop, $ssl, $relativeProtocol);

        if (($host = self::rmDevAltHostLink()) === null) {
            return $base;
        }

        $canonical = Db::getInstance()->getValue(
            'SELECT `domain` FROM `' . _DB_PREFIX_ . 'shop_url` WHERE `main` = 1 ORDER BY `id_shop_url`'
        );
        if (!$canonical || $canonical === $host) {
            return $base;
        }

        return str_replace($canonical, $host, $base);
    }

    /**
     * @return string|null hôte courant s'il est inconnu de ps_shop_url ; null sinon
     */
    protected static function rmDevAltHostLink()
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
