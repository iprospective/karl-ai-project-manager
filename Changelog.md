# Changelog système

Évolutions du système de gestion de tâches dans son ensemble.
Pour les évolutions du schéma des tâches, voir [norms/CHANGELOG.md](norms/CHANGELOG.md).

Format : [Keep a Changelog](https://keepachangelog.com/fr/)

---

## [1.4.0] - 2026-04-27

### Ajouté — Cahier des charges multi-fichiers
- Structure `client/` et `project/` en dossiers (overview + aspects)
- 40 templates d'aspects par domaine : common, website, ecommerce, api, saas,
  mobile, data, legal
- Cascade aspect par aspect entre niveaux client et projet

### Modifié
- Templates renommés en `*-overview.md`
- Agents (worker-common, summarizer) mis à jour pour charger tout le dossier
- NORMS bumped 1.3.0 → 1.4.0

---

## [1.3.0] - 2026-04-27

### Ajouté — Multi-client / multi-projet hiérarchique
- Structure `clients/{C}/projects/{P}/tasks/` dans le repo projets
- Cascade contextuelle : client → projet → tâche, héritage avec override
- Fichiers auto-générés (Changelog, Pistes, Remarques) aux niveaux client et projet
- Section "Structure / Fonctionnement" enrichie automatiquement
- `agents/summarizer.md` : nouvel agent pour génération automatique
- `scripts/priority.py` : ordonnancement par ROI avec filtre dépendances
- `scripts/cron.example.sh` : exemple de configuration cron pour orchestrateur,
  summarizer, ranking ROI hebdomadaire
- `templates/client.md` : nouveau template client
- `templates/project.md` enrichi : client, defaults, stack (avec section tests),
  section Structure / Fonctionnement

### Modifié
- `agents/orchestrateur.md` : déclenchement par cron, scan multi-clients,
  référence à scripts/priority.py
- `agents/worker-common.md` : contexte chargé en cascade (4 niveaux)
- `CLAUDE.md` : invocation mise à jour avec client + projet
- `README.md` : workflow création client / projet / tâche
- NORMS bumped v1.2.1 → v1.3.0 (archive v1.2.1 créée)

---

## [1.2.5] - 2026-04-27

### Ajouté
- `scripts/validate-task.py` : validateur structurel (champs obligatoires,
  enums, transitions, cohérence status_history, conditional rules, completion_pct)
- `.gitlab-ci.yml` : pipeline CI exécutant la validation sur chaque push
- `templates/RM9999_exemple-tache-complete.md` : exemple complet et valide,
  utilisé par le CI comme cas de test
- Règle test-first dans `worker-dev.md` (test reproduisant le bug avant fix,
  tests des critères d'acceptation avant code)
- Obligation pour `reviewer.md` d'exécuter les tests (pas juste vérifier
  leur existence) — tout échec = rejet automatique
- `PISTES.md` : section "Tests — évolutions reportées" avec stack de tests
  dans templates/project.md, validation cross-fichiers, génération automatique
  de stubs depuis critères d'acceptation, tests workflow E2E

---

## [1.2.4] - 2026-04-27

### Ajouté
- `PISTES.md` : document de pistes d'évolution AI-natives pour une v3
  (branch & merge, critiques continus, décomposition asymétrique,
  pipeline Intent→Plan→Fan-out→Synthèse, exécution spéculative)
- Nouveaux rôles d'agents proposés : intent-extractor, adversary, critic, synthesizer

---

## [1.2.3] - 2026-04-27

### Ajouté
- `.env.example` : variables d'environnement requises (GitLab, Redmine, chemins)
- `projects/` gitignored : le dossier projects est désormais un repo git séparé,
  cloné indépendamment — le repo PM est publiable sans données de projets

### Modifié
- `.gitignore` : ajout de `.env` et `projects/`
- `norms/NORMS.md` v1.2.1 : config globale externalisée en variables d'environnement

---

## [1.2.2] - 2026-04-27

### Ajouté
- `CLAUDE.md` : bootstrap automatique pour Claude Code — orientation, ordre de lecture, rappels critiques
- `scripts/invoke.md` : guide d'invocation manuelle (workers, reviewer, orchestrateur, workflow complet)

---

## [1.2.1] - 2026-04-27

### Refactoring
- Extraction des règles communes des workers dans `agents/worker-common.md`
  (périmètre d'écriture, contexte, format journal, soumission, locking, blocage)
- Workers réécrits en version compacte : chaque fichier ne contient plus que
  ce qui est spécifique au rôle — taille réduite de ~50%

---

## [1.1.0] - 2026-04-27

### Ajouté
- Section collaboration multi-agents dans NORMS.md (rôles, règles d'écriture, protocoles)
- Section architecture de déploiement dans NORMS.md (V1, V1.5 NFS/ZFS, V2 Git/branches)
- `README.md` racine : guide d'utilisation humain et agent
- `agents/` : system prompts de référence pour orchestrateur, workers, reviewer
- `.gitignore`

### Modifié
- `CHANGELOG.md` racine : rempli et séparé du changelog de normes

---

## [1.0.0] - 2026-04-26

### Initial
- Structure de dossiers : `norms/`, `projects/`, `templates/`, `norms/archive/`
- `norms/NORMS.md` v1.0 : schéma frontmatter complet, machine d'états 7 statuts,
  valeurs énumérées, règles du journal append-only, versionning des normes
- `norms/CHANGELOG.md` au format Keep a Changelog
- `templates/task.md` : template tâche avec tous les champs
- `templates/project.md` : template projet
- Initialisation Git sur branche `dev`
