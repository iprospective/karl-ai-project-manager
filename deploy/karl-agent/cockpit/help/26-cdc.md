# CDC vivant

Le bouton **📋 CDC** du menu du haut ouvre au centre, en onglet épinglable, le **CDC du projet en
contexte** — celui de la session attachée, sinon le dernier choisi, sinon le premier — avec, en tête de page,
**tous les onglets au même niveau**, dans l'ordre et avec les noms de la norme `cdc` (§ livrables d'un CDC complet) :
📋 Fonctionnalités · 📘 CDC vivant (le sommaire) · chapitres thématiques · 🗺 Roadmap · 📚 Dictionnaire · ⚖️ Registre des
décisions · 🗒 Vrac · ❓ Questions ouvertes · 📖 Glossaire · 📖 Guide. L'onglet courant est mémorisé. Un projet peut porter plusieurs CDC (le projet PM : « pm » et « karl ») — des puces
permettent d'en changer.

- **Fonctionnalités** : une ligne par ticket (ou par capacité, pour un registre curé) — clic sur un en-tête
  pour trier, second clic pour inverser ; filtre texte (libellé, domaine, état, `RM…`) ; un ticket ouvre sa fiche.
- **CDC vivant et chapitres** : chaque chapitre est un onglet ; les liens entre chapitres et les ancres `D012` /
  `Q003` naviguent dans la page ; un `RM1234` dans le texte ouvre la fiche.
- **Roadmap** : le chapitre `cdc-roadmap.md` — une **version = un rôle** (ce qu'elle doit permettre, critère de
  passage), jamais une copie des fonctionnalités ; la version est une **colonne** de la table (`version` par entrée).

Dans la colonne de droite, l'onglet **📂 projets** liste les projets touchés par la session attachée avec
leurs raccourcis : fiche, fichiers, et les mêmes onglets que le panneau pour chaque CDC vivant.

Un projet porte un CDC dès qu'il a un `docs/cdc-<prefix>-00-sommaire.md` ; le registre des fonctionnalités
(`docs/cdc-<prefix>/fonctionnalites.yml`) se crée et se tient avec `pm-cdc-features` (`--init`, `--sync`,
`--build`, `--check`). Le CDC se tient à jour **au fil de l'eau**, comme NORMS : une décision, une question,
une fonctionnalité livrée entrent dans le registre dans la même livraison.
