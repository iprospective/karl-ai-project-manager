<?php
/**
 * Override "domaine-agnostique" — DEV/TEST UNIQUEMENT. (1/2, avec ShopUrl.php)
 *
 * Sert un worktree PrestaShop sur un domaine ALTERNATIF (vhost par worktree/ticket)
 * en PARTAGEANT la base d'un autre env, sans la redirection canonique 301 que PS
 * force vers le domaine de `ps_shop_url`.
 *
 * Ici : neutralise la redirection de RÉSOLUTION (Shop::initialize) — pour un hôte
 * inconnu, on spoofe le domaine canonique le temps de parent::initialize() (→ pas
 * de 301), on restaure l'hôte réel, puis on force shop->domain dessus.
 * Le volet AVAL (liens + Tools::getShopDomain → ShopUrl::getMainShopDomain) est
 * traité dans override/classes/shop/ShopUrl.php.
 *
 * ⚠ NE JAMAIS COMMITER / DÉPLOYER EN PROD. Fichier LOCAL au worktree
 * (.git/info/exclude). Vider var/cache après dépôt. Skill mmi-presta-dev-vhost.
 */
class Shop extends ShopCore
{
    public static function initialize()
    {
        // Le back-office est inclus : sans lui, un env de session ne permet pas de
        // recetter un écran de configuration (constaté RM2687, 2026-08-14).
        if (Tools::isPHPCLI()) {
            return parent::initialize();
        }

        $host = Tools::getHttpHost(false, false, true);
        if (!$host) {
            return parent::initialize();
        }

        // Domaine canonique lu DIRECTEMENT (getMainShopDomain n'est pas fiable si
        // tôt dans le bootstrap : le contexte shop n'est pas encore posé).
        $canonical = Db::getInstance()->getValue(
            'SELECT `domain` FROM `' . _DB_PREFIX_ . 'shop_url` WHERE `main` = 1 ORDER BY `id_shop_url`'
        );

        // Hôte déjà connu de ps_shop_url (env principal), ou pas de canonique, ou
        // hôte == canonique → résolution normale.
        $known = (int) Db::getInstance()->getValue(
            'SELECT COUNT(*) FROM `' . _DB_PREFIX_ . 'shop_url`
             WHERE `domain` = \'' . pSQL($host) . '\' OR `domain_ssl` = \'' . pSQL($host) . '\''
        );
        if ($known || !$canonical || $host === $canonical) {
            return parent::initialize();
        }

        // Spoof du canonique le temps de la résolution → aucune redirection.
        $savedHost = isset($_SERVER['HTTP_HOST']) ? $_SERVER['HTTP_HOST'] : null;
        $savedFwd = isset($_SERVER['HTTP_X_FORWARDED_HOST']) ? $_SERVER['HTTP_X_FORWARDED_HOST'] : null;

        $_SERVER['HTTP_HOST'] = $canonical;
        unset($_SERVER['HTTP_X_FORWARDED_HOST']);

        $shop = parent::initialize();

        if ($savedHost !== null) {
            $_SERVER['HTTP_HOST'] = $savedHost;
        } else {
            unset($_SERVER['HTTP_HOST']);
        }
        if ($savedFwd !== null) {
            $_SERVER['HTTP_X_FORWARDED_HOST'] = $savedFwd;
        }

        if (Validate::isLoadedObject($shop)) {
            $shop->domain = $host;
            $shop->domain_ssl = $host;
        }

        return $shop;
    }
}
