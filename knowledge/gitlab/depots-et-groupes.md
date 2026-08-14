---
type: knowledge
product: gitlab
created: 2026-08-14
tracks: RM2652
---

# GitLab (gitlab.iprospective.fr) — où vivent les dépôts, et le piège des anciens chemins

Complément de [`api.md`](./api.md), qui traite des pièges de l'**API**. Ici : **où chercher
un dépôt** avant de conclure qu'il faut le créer.

## Les modules PrestaShop mutualisés sont sous `prestashop/`

Groupe **`prestashop`** (id **109**), **à la racine** de l'instance — pas sous
`iprospective/`. Il contient 29 dépôts (2026-08-14), sans sous-groupe :

- `prestashop/prestashop-core` — le cœur PrestaShop
- `prestashop/prestashop-module-<nom>` — un dépôt par module mutualisé, partagé entre les
  sites du parc (calicote, pisceen, calyclay, villa-cactus…)
- `prestashop/<module>-core` — le dépôt de **données PM** d'un module qui a son propre
  projet PM (ex. `mmi_productcheck-core`)

### Convention de nommage — attention au séparateur

`prestashop-module-<nom-du-module-en-kebab-case>`.

Le nom du **dossier** du module dans PrestaShop est en `snake_case`, le nom du **dépôt**
en `kebab-case`. La traduction n'est pas automatique dans les deux sens, c'est la cause
d'une bonne part des « je ne trouve pas le dépôt » :

| Dossier du module | Dépôt GitLab |
|---|---|
| `cins_newcategoryfields` | `prestashop-module-cins-newcategoryfields` |
| `cinsThemeConfigurator` | `prestashop-module-cins-themeconfigurator` |
| `cins_imagelinks_footer` | `prestashop-module-cins-imagelinks-footer` |
| `productsdlcdluo` | `prestashop-module-products-dlc-dluo` |

Le dernier cas est le plus retors : le nom du dossier est un seul mot collé, le dépôt le
découpe en trois. **Chercher par sous-chaîne, pas par transformation mécanique du nom.**

## ⚠ Le piège : `iprospective/prestashop/…` est un ANCIEN chemin qui redirige

Le groupe a été déplacé à la racine. GitLab **redirige indéfiniment** l'ancien chemin pour
les projets qui existaient **avant** le déplacement. Conséquence :

```bash
# dépôt ancien : les DEUX chemins répondent, et rendent le MÊME sha
git ls-remote gitlab:prestashop/prestashop-module-product.git HEAD
git ls-remote gitlab:iprospective/prestashop/prestashop-module-product.git HEAD
#  → 8e81584e6f4607b0b5533e5a9c76c28bc29defce  dans les deux cas

# dépôt créé APRÈS le déplacement : seul le chemin canonique répond
git ls-remote gitlab:prestashop/prestashop-module-cins-newcategoryfields.git HEAD   # ✓
git ls-remote gitlab:iprospective/prestashop/prestashop-module-cins-newcategoryfields.git HEAD
#  → remote: The project you were looking for could not be found…
```

**Ce qui rend le piège coûteux** : le message d'erreur d'un dépôt *cherché au mauvais
chemin* est **strictement identique** à celui d'un dépôt *qui n'existe pas* — « The project
you were looking for could not be found or you don't have permission to view it. » Rien ne
distingue les deux cas. On conclut « le dépôt n'existe pas, il faut le créer », et on part
créer un doublon d'un dépôt vivant.

**Pire** : tester l'ancien chemin avec un dépôt-témoin *ancien* le **valide**, puisqu'il
redirige. Le témoin confirme alors l'erreur au lieu de la révéler.

### Comment lever le doute

Deux chemins qui rendent le **même SHA** sur `HEAD` sont **un seul dépôt vu par une
redirection**, pas deux dépôts :

```bash
git ls-remote <chemin-A> HEAD ; git ls-remote <chemin-B> HEAD    # même sha ⇒ redirection
```

Et pour savoir ce qui existe vraiment, **énumérer le groupe** plutôt que deviner un chemin
(cf. `api.md` : jamais de `?search=` seul) :

```bash
curl -s -H "PRIVATE-TOKEN: $GITLAB_WORKER_TOKEN" \
  "https://gitlab.iprospective.fr/api/v4/groups/109/projects?per_page=100&order_by=name&sort=asc" \
  | python3 -c "import sys,json;[print(p['path_with_namespace']) for p in json.load(sys.stdin)]"
```

## Source connue de contamination

Le `.gitmodules` du dépôt **`calicote/prestashop`** déclare ses submodules avec l'ancien
chemin `gitlab:iprospective/prestashop/…`. Comme il est versionné, il se réplique dans tous
ses worktrees et sert de modèle trompeur — c'est le seul `.gitmodules` du parc dans ce cas.
Normalisation suivie par **RM2651**.

> **Règle** : avant de conclure qu'un dépôt de module n'existe pas et qu'il faut le créer,
> le chercher à son chemin **canonique** (`prestashop/…`) **et** énumérer le groupe. Un
> `.gitmodules` existant n'est pas une source fiable pour le chemin d'un groupe.
