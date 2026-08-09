# À tester & revue

Le panneau **🧪 à tester** liste les tickets en `a_tester_demandeur` (pastille
« demandeur ») ou `a_tester_dev` (« dev »), enrichis de leur branche et de leur
environnement de test.

## Actions par ticket

- **🧪 revue** : ouvre la console de revue du ticket.
- **✅ testé OK → fermer** / **🚧 testé OK → MEP** / **↩ KO → corriger** :
  pose le verdict et transitionne le statut.

## Environnement de test

Deux natures d'env, avec un indicateur ● (en ligne) / ⚠ (indisponible) :

- **Env de session applicatif** (docroot) : bouton **🔁 re-déployer** /
  **🧹 démonter**.
- **Instance cockpit de test** (ticket dont le worktree embarque karl-agent,
  exposée en **HTTPS**) :
  - **🚀 (re)lancer l'instance de test** quand elle est down — la relance
    (idempotent : survit à un reboot qui tue le service) ;
  - **🧹 démonter** quand elle tourne ;
  - le lien ● pointe sur `test_url` en `https://…` (accepter le certificat
    auto-signé une fois ; terminal et micro exigent ce contexte sécurisé).

Une instance de test se relance donc **en un clic** ; inutile de repasser en CLI.
