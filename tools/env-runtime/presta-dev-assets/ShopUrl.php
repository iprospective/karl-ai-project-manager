<?php
/**
 * Override "domaine-agnostique" — DEV/TEST UNIQUEMENT. (2/2, avec Shop.php)
 *
 * Volet AVAL : `Tools::getShopDomain()`/`getShopDomainSsl()` (utilisés par les
 * redirections canonique/SSL de FrontController et par certains liens) lisent
 * `ShopUrl::getMainShopDomain()`, qui renvoie le domaine de la BASE (canonique).
 * Pour un hôte INCONNU de `ps_shop_url` (domaine de test), on renvoie l'hôte
 * courant → la cible de redirection == hôte courant → plus de 301, et les liens
 * restent sur le domaine de test.
 *
 * ⚠ NE JAMAIS COMMITER / DÉPLOYER EN PROD. Fichier LOCAL au worktree
 * (.git/info/exclude). Vider var/cache après dépôt. Skill mmi-presta-dev-vhost.
 */
class ShopUrl extends ShopUrlCore
{
    public static function getMainShopDomain($id_shop = null)
    {
        if (($host = self::rmDevAltHost()) !== null) {
            return $host;
        }

        return parent::getMainShopDomain($id_shop);
    }

    public static function getMainShopDomainSSL($id_shop = null)
    {
        if (($host = self::rmDevAltHost()) !== null) {
            return $host;
        }

        return parent::getMainShopDomainSSL($id_shop);
    }

    /**
     * @return string|null hôte courant si c'est un domaine de test inconnu de
     *                      ps_shop_url ; null sinon (→ comportement PS normal).
     */
    protected static function rmDevAltHost()
    {
        // Le back-office est inclus : sans lui, un env de session ne permet pas de
        // recetter un écran de configuration (constaté RM2687, 2026-08-14).
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
