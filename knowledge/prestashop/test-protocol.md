# PrestaShop — protocole de test / non-régression (commun au parc)

Surface de test canonique d'un site PrestaShop, et comment la rejouer. Voisin de
`knowledge/prestashop/mep.md` (§ 6 « présenter un vrai panier » en est l'ancêtre
manuel). Éprouvé sur calicote (RM2564, RM2576) avant d'être normé (RM2885).

## Modèle en couches

| Niveau | Quoi | Où |
|---|---|---|
| **N0** | Surface générique PrestaShop : types de page + workflows | `test-surface.yml` (ce dossier) + ce doc |
| **N1** | Manifeste du site : IDs réels, features off, spécifiques, envs | `<projet>/.mmi-pm/project/test-manifest.yml` |
| **N2** | Runner exécutable | `scripts/pm-site-test.py` |
| **N3** | Sous-ensemble impacté par un ticket | champ `test_protocol` du ticket + `--subset` |
| **N4** | Run complet en préprod puis prod | `--full` — **gate** du passage `en_mep → ferme` |

Le runner **fusionne** N0 (surface générique) et N1 (manifeste site) : le site ne
redit pas les types de page standard, il ne fournit que ses valeurs et ses écarts.

## Types de page couverts (N0)

accueil, catégorie, produit, CMS, marque (+liste), fournisseur (+liste),
nouveautés, meilleures ventes, promos, recherche, plan du site, magasins, contact,
authentification, panier, 404. Chacun : URL/pattern, code HTTP attendu **après
redirection** (les `index.php?controller=` renvoient vers l'URL SEO — c'est voulu,
on suit `-L`), et scan d'erreurs dans le corps.

## Workflows couverts (N0)

- **checkout** : session → jeton statique → ajout panier (`id_product`) → contrôleur
  `order` → la 1re étape du tunnel doit être rendue (login/création de compte ou
  étapes nommées, selon le thème).

D'autres workflows (recherche, contact, création de compte, newsletter) s'ajoutent
par site via `manifest.workflows` / `extra_pages` quand ils portent une logique
métier propre.

## Détection d'erreurs

PrestaShop en mode debug affiche notices/exceptions dans le HTML. Le runner scanne
un jeu de motifs (`fatal error`, `notice:`, `warning:`, `uncaught`, `sf-dump`…) et
**FAIL dès un match, quel que soit le code HTTP** — un 200 qui contient une notice
n'est pas un succès. Les faux positifs (attributs `exceptions"`…) sont filtrés.

## Pièges connus

- **Redirection canonique** : PS 301 vers l'URL SEO puis ajoute `/fr/`. On suit les
  redirections ; en conteneur, le vhost `.lxc` ne résout pas (dnsmasq côté hôte) →
  `manifest.envs.<env>.resolve` fournit `host:127.0.0.1` (passé à `curl --resolve`).
- **Features désactivées** : un site sans fournisseurs renvoie 404 sur
  `controller=supplier`. Ce n'est **pas** une régression → à déclarer dans
  `manifest.expect_overrides` (ex. `supplier_list: 404`). Le runner compare au code
  déclaré, pas à 200 en dur.
- **DB partagée en dev** : les envs de ticket partagent souvent la base dev ; le
  workflow checkout crée un panier réel (pollution mineure, acceptable en dev).

## Usage

```bash
# baseline de référence (état sain courant)
pm-site-test.py --manifest <projet>/.mmi-pm/project/test-manifest.yml --env dev --record

# N3 — sous-ensemble impacté par un ticket (avant livraison)
pm-site-test.py --manifest … --env dev --subset home,product,category,checkout

# N4 — run complet, préprod puis prod (gate de MEP)
pm-site-test.py --manifest … --env preprod --full
pm-site-test.py --manifest … --env prod --full
```

Le runner sort un tableau `PASS/FAIL`, signale les écarts `CHANGED` vs la baseline
enregistrée, et rend un **code de sortie non nul** dès qu'un FAIL ou un CHANGED
apparaît — donc branchable tel quel comme gate d'un script de MEP ou d'un hook de
statut.

## Voir aussi

- `knowledge/prestashop/mep.md` — procédure de mise en production du parc.
- `test-surface.yml` — la surface N0 machine-lisible (ce dossier).
- `templates/site-test-manifest.example.yml` — squelette de manifeste N1.
