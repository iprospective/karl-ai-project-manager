# CDC vivant

Le bouton **📋 CDC** du menu du haut ouvre au centre, en onglet épinglable, le **CDC du projet en
contexte** — celui de la session attachée, sinon le dernier choisi, sinon le premier — avec, en tête de page,
les onglets du POC AtomBox : **📋 Fonctionnalités · 📘 CDC · 🗺 Feuille de route** (l'aide reste ❓). L'onglet
courant est mémorisé. Un projet peut porter plusieurs CDC (le projet PM : « pm » et « karl ») — des puces
permettent d'en changer.

- **Fonctionnalités** : une ligne par ticket (ou par capacité, pour un registre curé) — clic sur un en-tête
  pour trier, second clic pour inverser ; filtre texte (libellé, domaine, état, `RM…`) ; un ticket ouvre sa fiche.
- **CDC** : les chapitres en sous-onglets (sommaire, décisions, vrac, questions…) ; les liens entre chapitres et
  les ancres `D012` / `Q003` naviguent dans la page ; un `RM1234` dans le texte ouvre la fiche.
- **Feuille de route** : la même donnée, groupée par **jalon** (`jalon` par entrée, `jalons:` en tête du
  registre) ou, sans jalon, par état : en cours, prévu, en pause, puis les livrées récentes.

Dans la colonne de droite, l'onglet **📂 projets** liste les projets touchés par la session attachée avec
leurs raccourcis : fiche, fichiers, et les trois pages de chaque CDC vivant.

Un projet porte un CDC dès qu'il a un `docs/cdc-<prefix>-00-sommaire.md` ; le registre des fonctionnalités
(`docs/cdc-<prefix>/fonctionnalites.yml`) se crée et se tient avec `pm-cdc-features` (`--init`, `--sync`,
`--build`, `--check`). Le CDC se tient à jour **au fil de l'eau**, comme NORMS : une décision, une question,
une fonctionnalité livrée entrent dans le registre dans la même livraison.
