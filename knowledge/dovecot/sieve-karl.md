---
type: reference
product: dovecot
created: 2026-09-14
refs: [RM2667, RM2668, RM2669, RM2517]
---

# Dovecot / Sieve — la boîte `karl@iprospective.fr`

Relevé du **2026-09-14**, en lecture seule (IMAP `LIST` + ManageSieve
`LISTSCRIPTS`/`GETSCRIPT`). Vault `vw-ipro` déverrouillé requis.

## Les dossiers

| Dossier | Rôle pour la relève (RM2668) |
|---|---|
| `INBOX.Clients` | **file de confiance** — classé par le serveur, c'est elle que `karl-mail-fetch` relève en priorité |
| `INBOX` | file secondaire (non classé) |
| `INBOX.Gitlab`, `INBOX.Vault` | exclus de la relève (machines) |
| `Archives` `Drafts` `Junk` `Sent` `Trash` | special-use, jamais relevés |
| `virtual`, `virtual.*` | vues virtuelles Dovecot ; `virtual` n'est pas sélectionnable |

Treize dossiers au total. `karl-mail-fetch.py --list-folders` les affiche avec
leur rôle — c'est la commande d'inventaire, pas une capture à recopier ici.

## La règle Sieve — ce qu'elle est vraiment

**Un seul script, `roundcube`, ACTIF.** Écrit par l'interface de filtres de
Roundcube, il tient en trois règles :

```sieve
require ["fileinto"];
# rule:[clients]
if anyof (header :contains "from" "@calyclay.com", … 11 motifs …)
{ fileinto "INBOX.Clients"; stop; }
# rule:[Gitlab]   → INBOX.Gitlab
# rule:[Vault]    → INBOX.Vault
```

Deux écarts avec ce qu'on croyait :

1. **Ce n'est pas « alimenté par le carnet Roundcube ».** C'est une **liste
   statique de 11 domaines et adresses**, saisie à la main. Sieve ne sait pas
   lire un carnet d'adresses : « alimenter depuis le carnet » suppose un
   générateur qui réécrit la règle — il n'existe pas. La liste dérivera donc à
   chaque nouveau client, en silence. C'est le même défaut que la liste de
   domaines maison qu'on a sortie du code du routage en RM3024.
2. **Aucune condition d'authenticité.** Le tri se fait sur
   `header :contains "from"`, rien d'autre. Un `From:` forgé suffit donc à
   déposer un message dans la file « de confiance » — celle que l'agent relève
   en priorité et à partir de laquelle il crée des tickets. La file est
   **forgeable** (RM2667, critère 5).

## Ce que le serveur sait faire

`Dovecot (Ubuntu) Pigeonhole`, extensions disponibles :

> body, comparator-i;ascii-numeric, copy, date, duplicate, encoded-character,
> enotify, envelope, environment, extracttext, fileinto, foreverypart, ihave,
> imap4flags, include, index, mailbox, mime, regex, reject, relational,
> subaddress, vacation, variables

Ce qu'il faut pour RM2667 est là : tester `Authentication-Results` ne demande
que le `header` de base, et `copy` permet un `redirect :copy` pour l'acheminement
depuis une autre boîte.

## Le prérequis DNS est acquis

```
_dmarc.iprospective.fr   v=DMARC1; p=reject; pct=100; adkim=r; aspf=r
SPF                      v=spf1 include:iprospective.net -all
DKIM                     sélecteur « mail » présent
```

`p=reject` et DKIM signé : Dovecot appose donc un `Authentication-Results`
exploitable. La condition anti-usurpation est réalisable telle quelle.

## Accès

- IMAP : `mail.iprospective.net:993`, identifiants Vaultwarden
  `iprospective/iprospective-agents/karl@mail.iprospective.net`.
- ManageSieve : **même hôte, port 4190**, mêmes identifiants, `STARTTLS`.
  Outil : **`pm-sieve`** (RM3171) — `list`, `get`, `diff --from-file`,
  `put --from-file [--dry-run]`, `activate`, `delete`, `backups`.

## Modifier un filtre — le geste outillé

```bash
pm-sieve get roundcube > /tmp/r.sieve        # partir de ce qui est EN PLACE
$EDITOR /tmp/r.sieve
pm-sieve diff roundcube --from-file /tmp/r.sieve
pm-sieve put  roundcube --from-file /tmp/r.sieve --dry-run   # validation serveur, rien écrit
pm-sieve put  roundcube --from-file /tmp/r.sieve             # écriture gardée
```

`put` refuse si la boîte authentifiée n'est pas celle demandée, fait valider le
script par Pigeonhole (`CHECKSCRIPT`) avant de toucher à l'original, sauvegarde
l'ancien octet pour octet sous `<state_dir>/sieve-backups/<boîte>/` (hors git :
un filtre porte des adresses de clients), puis relit ce qu'il a écrit. `delete`
refuse le script actif.

**Roundcube réécrit le script `roundcube`** quand on passe par son interface de
filtres : une règle qu'elle ne sait pas représenter (l'`allof` imbriqué de RM2667)
peut y disparaître. Avant toute retouche par l'UI, `pm-sieve get` pour comparer
après ; la question d'un script séparé inclus par `include` reste ouverte
(RM3171, § À trancher).
