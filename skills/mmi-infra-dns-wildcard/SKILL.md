---
name: mmi-infra-dns-wildcard
description: Expose un service interne sur un sous-domaine public dédié du parc iProspective — enregistrements DNS, délégation ACME, certificat wildcard auto-renouvelé (dns-rfc2136) et reverse proxy. Reproduit le modèle établi (sfy, dev, test, core, tools, ai, stats, proxy). Usage : "/mmi-infra-dns-wildcard", ou langage naturel "crée un sous-domaine <x>.iprospective.fr avec un wildcard", "expose le conteneur <c> en https", "je veux *.<x>.iprospective.fr qui pointe sur proxy".
allowed-tools: Bash, Read, Write, Edit
---

# Skill : mmi-infra-dns-wildcard

Créer un **sous-domaine public délégué** du parc, avec **wildcard TLS qui se renouvelle
seul**, et le brancher sur un conteneur interne via le reverse proxy.

Modèle éprouvé : `sfy`, `dev`, `test`, `core`, `tools`, `ai`, `stats`, `proxy`
— et `calicote` (RM2827), d'où viennent les pièges ci-dessous.

## Quand le déclencher

- « crée un sous-domaine `<x>.iprospective.fr` », « je veux `*.<x>.iprospective.fr` »
- « expose le conteneur `<c>` en HTTPS », « mets un wildcard qui se renouvelle tout seul »

## Le point à savoir avant tout : quelle zone

**`iprospective.fr` est auto-hébergée** (`ns.iprospective.net` + `ns-bkp`, BIND dans le
conteneur `core`). C'est ce qui rend possibles la délégation ACME et le renouvellement
automatique. **Les délégations `_acme-challenge` existantes sont TOUTES en `.fr`.**

`iprospective.net` n'a qu'une délégation racine. Un sous-domaine `.net` demanderait donc
de construire d'abord la même mécanique. **Par défaut, travailler en `.fr`.**

## Les cinq pièces du modèle

### 1. Zone `iprospective.fr` (dans `core`, `/etc/bind/zones/iprospective.fr.hosts`)

```
<x>				IN	CNAME	proxy.iprospective.net.
*.<x>				IN	CNAME	proxy
_acme-challenge.<x>		IN	NS	ns.iprospective.net.
```

Puis **bump du serial** (format `YYYYMMDDNN`) — sans quoi les secondaires ne suivent pas.

### 2. Micro-zone du challenge (`/var/lib/bind/db._acme-challenge.<x>.iprospective.fr`)

SOA + `NS ns.iprospective.net.`, `chown bind:bind`, `chmod 644` — BIND doit pouvoir y
écrire, c'est une zone à mise à jour dynamique.

### 3. Déclaration dans `named.conf.local`

```
zone "_acme-challenge.<x>.iprospective.fr" {
        type master;
        file "/var/lib/bind/db._acme-challenge.<x>.iprospective.fr";
        allow-query { any; };
        update-policy {
                grant letsencrypt. name _acme-challenge.<x>.iprospective.fr. TXT;
        };
};
```

`letsencrypt.` est la clé TSIG déclarée dans `named.conf.options`. C'est elle, et elle
seule, qui autorise certbot à poser le TXT.

**Toujours** `named-checkconf` et `named-checkzone` **avant** `rndc reload`.

### 4. Certificat wildcard (sur `proxy`)

```bash
certbot certonly --non-interactive \
  --dns-rfc2136 --dns-rfc2136-credentials /etc/letsencrypt/rfc2136.ini \
  --dns-rfc2136-propagation-seconds 60 \
  -d '<x>.iprospective.fr' -d '*.<x>.iprospective.fr' \
  --cert-name <x>.iprospective.fr
```

⚠ **`*.<x>` ne couvre PAS `<x>`.** Les deux doivent figurer dans la même demande, sinon
l'apex — souvent le site principal — reste sans certificat.

Le renouvellement est **automatique** : certbot réutilise la même méthode DNS, qui ne
dépend ni de l'accessibilité HTTP ni de l'endroit où pointent les A records. C'est tout
l'intérêt de la délégation.

### 5. Vhost reverse proxy (sur `proxy`)

Un seul vhost wildcard suffit (`ServerAlias *.<x>.iprospective.fr`) ; le modèle `sfy`
en fait un par nom, ce qui n'est utile que si les backends diffèrent.

```apache
<VirtualHost *:443>
    ServerName <x>.iprospective.fr
    ServerAlias *.<x>.iprospective.fr
    SSLEngine on
    SSLCertificateFile    /etc/letsencrypt/live/<x>.iprospective.fr/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/<x>.iprospective.fr/privkey.pem
    RequestHeader set X_FORWARDED_PROTO 'https'
    ProxyPreserveHost On
    ProxyPass        / http://<conteneur>.lan/
    ProxyPassReverse / http://<conteneur>.lan/
    <Proxy *>   { Require all granted }
    <Location /> { Require all granted }
</VirtualHost>
```

`ProxyPreserveHost On` transmet le **nom demandé** au backend : c'est ce qui lui permet de
choisir son vhost et d'écrire des URL cohérentes. TLS terminé au proxy, backend en HTTP
tant qu'il n'a pas ses propres certificats.

## Pièges vécus

- **Le backend doit connaître les nouveaux noms.** Avec `ProxyPreserveHost`, il reçoit
  `<app>.<x>.iprospective.fr` : sans `ServerAlias` correspondant, Apache sert son premier
  vhost pour tout. Symptôme trompeur : le mauvais site répond.
- **PrestaShop : redirection canonique.** `ps_shop_url.domain` prime sur le nom demandé —
  un accès par le nouveau nom **redirige vers l'ancien domaine**, donc vers l'ancien
  hébergeur. Aligner `ps_shop_url` sur le nom de test, puis purger `var/cache`.
- **PrestaShop en maintenance = 503**, pas une panne de proxy. `PS_SHOP_ENABLE` vide, et
  `PS_MAINTENANCE_IP` liste les IP autorisées. Derrière un proxy, PrestaShop voit l'IP du
  **proxy** sauf si `_PS_USE_HTTP_X_FORWARDED_FOR_` est défini dans `config/defines.inc.php`.
  ⚠ Avant d'activer la boutique pour contourner : une instance de préparation porte les
  **vraies données clients** — la publier expose une copie de la production (indexation,
  contenu dupliqué, confusion). Le mode maintenance est une protection, pas un défaut.
- **Vérifier la résolution avant de demander le certificat** (`dig` sur `ns.iprospective.net`
  puis en public) : un certbot lancé trop tôt consomme du quota Let's Encrypt pour rien.

## Vérifications de fin

```bash
dig +short <x>.iprospective.fr ; dig +short quoi-que-ce-soit.<x>.iprospective.fr
dig +short NS _acme-challenge.<x>.iprospective.fr
curl -sL -o /dev/null -w '%{http_code} (TLS %{ssl_verify_result})\n' https://<x>.iprospective.fr/
openssl s_client -connect <x>.iprospective.fr:443 -servername a.<x>.iprospective.fr </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -dates
certbot renew --dry-run --cert-name <x>.iprospective.fr   # valide le renouvellement auto
```

## Où c'est documenté

Dépôt `iprospective/sysadmin/infrastructure` : `docs/dns.md`, `docs/network.md`,
`containers/core/README.md` (BIND), `containers/proxy/README.md`.
