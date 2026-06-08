---
type: tool
created: 2026-06-08
---

# brevo-cleaner — purge des contacts spam (noms aléatoires) d'un compte Brevo

Outil réutilisable pour nettoyer une base **Brevo** des contacts créés par une vague
de spam d'inscription, repérables par un **nom/prénom en caractères aléatoires**
(ex. `TuwCqAoimPZYjGW tdmjAXzOZnWqvhMS`).

Né du nettoyage **calicote** de juin 2026 (~7 100 faux contacts issus d'un spam
d'inscription 2024). Conçu pour resservir sur n'importe quel projet PrestaShop/Brevo.

## Modèle de sécurité

Un contact n'est supprimé **que si les 3 conditions sont réunies** :

1. **Nom charabia** — prénom ou nom détecté comme aléatoire (voir détecteur).
2. **Absent de la prod** — email absent de l'*allowlist* construite depuis la/les
   base(s) prod du projet (clients PrestaShop + abonnés newsletter + contacts Dolibarr…).
3. **Aucune commande** — tous les attributs montant/CA du contact valent 0.

Tout le reste est **conservé** : noms vides, vrais clients, contacts présents en prod,
contacts ayant commandé. Le `plan` écrit toujours un **backup intégral** des contacts
avant toute suppression, et la suppression est **explicite** (`apply --yes`).

## Détecteur de noms-charabia

Un token (≥ `min_token_len`, alphabétique) est « charabia » si l'un des signaux
haute-précision est vrai :
- **≥ `case_switches`** transitions de casse internes (`aBcDeF…`) — un vrai nom en a 0–2 ;
- **≥ `cons_run`** consonnes consécutives — improbable dans un vrai nom ;
- **zéro voyelle** (si `require_zero_vowels`).

> Calibré pour **ne pas** flagger les noms consonantiques légitimes (alsaciens :
> *Schurck, Krantz, Stempf*…) ni les CamelCase réels (*LeGoff, MacLean*). Les rares
> faux positifs restants sont de toute façon rattrapés par les conditions 2 et 3.

## Usage

```bash
# 1. dry-run : récupère la clé, construit l'allowlist, fetch+backup, analyse
./brevo_cleaner.py <env> plan

#    → work/<env>/REVIEW_candidats.tsv   (à relire)
#    → work/<env>/delete_ids.txt
#    → work/<env>/contacts_backup.ndjson (backup intégral)

# 2. suppression effective (throttlée ~10/s, retry 429, log)
./brevo_cleaner.py <env> apply --yes
#    → work/<env>/delete.log
```

## Configuration

`environments/<env>.json` (**gitignoré** ; modèle : `environments/<env>.json.example`) :

| clé | rôle |
|-----|------|
| `brevo_key_cmd`  | commande shell imprimant la clé API Brevo v3 |
| `name_attrs`     | attributs prénom/nom (`["PRENOM","NOM"]` ou `["FIRSTNAME","LASTNAME"]`) |
| `order_attrs`    | attributs montant/CA protégeant le contact si > 0 |
| `allowlist_cmds` | commandes shell imprimant les emails légitimes (1/ligne) |
| `detector`       | seuils (`min_token_len`, `case_switches`, `cons_run`, `require_zero_vowels`) |

**Aucun secret en clair** : les commandes sont exécutées depuis la racine de l'outil et
lisent les credentials au runtime (ex. depuis `parameters.php`/`conf.php` de la prod via
SSH — voir `environments/calicote/*.sh`). Les helpers par env et les `work/` sont gitignorés.

## Prérequis

- Accès SSH aux hôtes prod (alias `~/.ssh/config`, ProxyJump inclus).
- IP de la machine **autorisée** dans Brevo si le compte restreint l'API par IP
  (*Brevo → Sécurité → IP autorisées*).
- `php` + `mysqli` disponibles côté prod (pour les helpers calicote).
