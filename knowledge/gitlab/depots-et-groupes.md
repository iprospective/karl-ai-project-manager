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

## Source connue de contamination — et pourquoi un `.gitmodules` n'est pas une référence

Un `.gitmodules` versionné se réplique dans **tous** les worktrees du dépôt et sert de
modèle à quiconque en ajoute un. S'il porte un chemin obsolète, il le propage.

C'est arrivé sur `calicote/prestashop`, qui a longtemps déclaré ses 4 submodules en
`gitlab:iprospective/prestashop/…`. **Corrigé depuis** : RM2575 a submodule-ifié les
modules `cins*` et son `.gitmodules` compte aujourd'hui 24 entrées, toutes en
`gitlab:prestashop/…` et toutes avec la clé `branch =`.

> **Le piège de second ordre, celui qui a réellement coûté** : on lit un `.gitmodules`
> **dans un worktree local en retard**. Le fichier est juste sur `origin/dev` et faux dans
> la copie qu'on a sous les yeux — 64 commits de retard dans le cas vécu (RM2648,
> 2026-08-14), ce qui a fait diagnostiquer « URLs à normaliser, module à extraire » sur un
> travail **déjà livré et mergé**. Un fichier versionné ne dit la vérité que si la copie
> lue est à jour :
>
> ```bash
> git fetch origin && git rev-list --count HEAD..origin/dev   # 0 attendu
> git show origin/dev:.gitmodules                             # sinon, lire la branche
> ```

> **Règle** : avant de conclure qu'un dépôt de module n'existe pas et qu'il faut le créer,
> le chercher à son chemin **canonique** (`prestashop/…`) **et** énumérer le groupe. Un
> `.gitmodules` existant n'est pas une source fiable pour le chemin d'un groupe — et une
> copie de travail non rafraîchie n'est pas une source fiable tout court.

## Corollaire : l'inventaire d'un site se lit sur la branche, pas dans le worktree

Ces dépôts sont consommés en **submodules**. Savoir « ce que ce site utilise » se lit donc
dans `.gitmodules` — et c'est précisément un fichier qu'un worktree de ticket, créé il y a
quinze jours, rend périmé sans le moindre signe extérieur. Un `git status` propre ne
protège de rien : le worktree est cohérent avec **son** commit, pas avec l'intégration.

Réflexe avant tout audit de structure (submodules, arborescence de modules, overrides) :
`git fetch` puis comparer à `origin/dev`, ou lire directement `git show origin/dev:<path>`.
