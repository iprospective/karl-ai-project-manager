---
type: knowledge
product: migration
created: 2026-10-19
---

# Migrer les configurations locales d'un hébergement à l'autre

Leçon tirée de la migration Calicote (SFY → conteneur du parc, RM2827), où des
confs reconstituées à la main ont bloqué la génération des expéditions pendant
une demi-journée, sans aucun signal dans les journaux.

## La règle

**Migrer, ce n'est pas réinstaller.** Un fichier de configuration se **reprend**
depuis la source et s'**adapte** — on ne le réécrit pas à partir d'un `.dist`
ou de mémoire. Ce qu'on ne reprend pas, on le perd en silence.

## Pourquoi ces fichiers échappent à tous les filets

Les confs locales d'un environnement cumulent trois protections qui, ensemble,
les rendent invisibles :

1. **Elles sont dans le `.gitignore`** — par conception, puisqu'elles varient
   d'un environnement à l'autre. Le déploiement git ne les apporte donc jamais.
2. **Le script de synchro les exclut** — ce sont ses « confs préservées », il
   les protège activement pour ne pas écraser les identifiants de la cible.
3. **Rien ne les vérifie au démarrage** — une constante absente retombe sur une
   valeur par défaut, ou vaut la chaîne de son propre nom en PHP.

> **Les fichiers qu'un script de synchro préserve sont exactement ceux qu'il ne
> peut pas réparer.** Ils demandent donc une vérification *manuelle et explicite*.

## Comparer : un vrai diff, pas une comparaison de clés

Sur Calicote, une comparaison des variables définies avait conclu « 21 contre 22,
5 écarts ». Le `diff` du même fichier a révélé en plus **un bloc de code entier
manquant** en fin de fichier : réglages `ini_set`, `set_time_limit`, et un
blocage de crawler. Du code libre, hors de toute variable — invisible à une
comparaison clé par clé.

```sh
# masquer les secrets avant de comparer
mask() { sed -E 's/((pass|pwd|key|secret|token)[A-Za-z_]*["\x27]?\s*(=>|=|,)\s*)["\x27][^"\x27]*["\x27]/\1"***"/Ig'; }
ssh <source> 'cat <chemin>' | mask > /tmp/a
ssh <cible>  'cat <chemin>' | mask > /tmp/b
diff -u /tmp/a /tmp/b
```

À la fin, le diff ne doit plus contenir **que** les adaptations voulues :
chemins, bases, identifiants, URL. Tout le reste est une perte.

## Les secrets dérivés d'un identifiant d'instance

Certaines applications chiffrent leurs valeurs sensibles en base avec une clé
tirée d'un identifiant posé dans la conf locale — `dolibarr_main_instance_unique_id`
pour Dolibarr, `cookie_key` / `cookie_iv` pour PrestaShop.

**Si la base est copiée mais pas cet identifiant, tous les secrets chiffrés
deviennent illisibles** : clés de paiement, jetons d'API, clés de tâches
planifiées. L'application démarre normalement et échoue plus tard, ailleurs.

Vérifier systématiquement, sans afficher les valeurs :

```sh
a=$(ssh <source> '… | sha256sum | cut -c1-16')
b=$(ssh <cible>  '… | sha256sum | cut -c1-16')
[ "$a" = "$b" ] || echo "identifiant d'instance différent : secrets en base illisibles"
```

## Les services tiers qui filtrent par IP

Changer d'hébergement change l'IP sortante. Tout service tiers authentifiant par
IP cesse de répondre — **sans trace dans les journaux locaux**, seulement un
échec fonctionnel que personne ne voit avant qu'un utilisateur le signale.

Sur Calicote : l'API REST de Dolibarr elle-même (`API_RESTRICT_ON_IP`), et le
webservice DPD, qui a demandé un appel au prestataire.

Inventorier avant la bascule : passerelles de paiement, transporteurs, API
fournisseurs, relais SMTP. Et retenir que **joignable n'est pas autorisé** : un
`curl` qui répond 200 sur la page d'accueil du service ne dit rien de
l'autorisation du compte depuis la nouvelle IP.

## Après la bascule, la source devient un piège

Une fois le DNS basculé, la cible est la production. Relancer la synchro
écraserait les données du jour. Le script doit **refuser de s'exécuter**, avec
un message qui dit pourquoi et un contournement explicite pour un retour arrière
décidé :

```sh
if [[ " $* " != *" --je-sais-ce-que-je-fais "* ]]; then
  echo "REFUS : la bascule est faite, la cible EST la production." >&2
  exit 3
fi
```

## Checklist

- [ ] Lister les fichiers exclus du git **et** ceux préservés par la synchro
- [ ] `diff` réel de chacun, source contre cible, secrets masqués
- [ ] Ne laisser dans le diff que chemins, bases, identifiants, URL
- [ ] Comparer les identifiants d'instance (secrets chiffrés en base)
- [ ] Inventorier les services tiers filtrant par IP et les faire autoriser
- [ ] Vérifier que les URL internes pointent sur la cible, pas sur la préparation
- [ ] Interdire la synchro une fois la bascule faite
