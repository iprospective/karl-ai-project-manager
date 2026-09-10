# CDC vivant

Le bouton **📋 CDC**, juste à droite du titre « Cockpit karl-agent », ouvre au centre, en onglet épinglable, le **CDC du projet en
contexte** — celui de la session attachée, sinon le dernier choisi, sinon le premier — avec, en tête de page,
**tous les onglets au même niveau**, dans l'ordre et avec les noms de la norme `cdc` (§ livrables d'un CDC complet) :
📋 Fonctionnalités · 📘 CDC vivant (le sommaire) · chapitres thématiques · 🗺 Roadmap · 📚 Dictionnaire · ⚖️ Registre des
décisions · 🗒 Vrac · ❓ Questions ouvertes · 📖 Glossaire · 📖 Guide. L'onglet courant est mémorisé. Un projet peut porter plusieurs CDC (le projet PM : « pm » et « karl ») — des puces
permettent d'en changer.

- **Fonctionnalités** : une ligne par ticket (ou par capacité, pour un registre curé) — clic sur un en-tête
  pour trier, second clic pour inverser ; filtre texte (libellé, domaine, état, `RM…`) ; un ticket ouvre sa fiche.
- **CDC vivant et chapitres** : chaque chapitre est un onglet ; les liens entre chapitres et les ancres `D012` /
  `Q003` naviguent dans la page ; un `RM1234` dans le texte ouvre la fiche.
- **Feuille de route** : le chapitre `cdc-roadmap.md`, **généré** — une **version = une étape de travail**
  (ce qu'elle doit permettre, et à quoi on sait qu'elle est passée), jamais une copie des fonctionnalités ;
  la version est une **colonne** de la table.

### Ajouter une version, y rattacher des fonctionnalités

Sur l'onglet **Feuille de route**, un formulaire crée une version : un identifiant (V1, V2…), son rôle, son
critère de passage, son état. Nommer une version qui existe déjà la complète plutôt que de la dupliquer.
« Retirer » l'enlève du registre et **détache** les fonctionnalités qui la portaient, sans en supprimer aucune.

Le rattachement se fait dans l'autre onglet : **Fonctionnalités**, colonne *Version*, un sélecteur par ligne.
La feuille de route affiche alors, par version, combien de fonctionnalités sont livrées sur le total, puis la
liste. Les fonctionnalités en cours ou prévues qui ne sont rattachées à rien apparaissent sous « Sans version » :
c'est ce qui reste à placer.

Dans la colonne de droite, l'onglet **📂 projets** liste les projets touchés par la session attachée avec
leurs raccourcis : fiche, fichiers, et les mêmes onglets que le panneau pour chaque CDC vivant.

Un projet porte un CDC dès qu'il a un `docs/cdc-<prefix>-00-sommaire.md` ; le registre des fonctionnalités
(`docs/cdc-<prefix>/fonctionnalites.yml`) se crée et se tient avec `pm-cdc-features` (`--init`, `--sync`,
`--build`, `--check`). Le CDC se tient à jour **au fil de l'eau**, comme NORMS : une décision, une question,
une fonctionnalité livrée entrent dans le registre dans la même livraison.

## Corriger depuis le panneau

Dans un registre (décisions, questions, vrac, fonctionnalités des think), chaque ligne porte un **sélecteur
d'état** (✅ validé · ❌ invalidé · 🟡 proposé · 🕐 en attente · ⏸ en réserve) et un bouton **✕** qui supprime
l'entrée après confirmation — pour une entrée incohérente. Dans la table des fonctionnalités, le sélecteur
d'une ligne change son état (prévu · en cours · en pause · écarté · livré) et **fige** l'entrée ; une
fonctionnalité ne se supprime pas, elle s'écarte. Le geste passe par les scripts (`pm-task-think`,
`pm-cdc-features`) et les registres sont régénérés aussitôt (RM3064).
