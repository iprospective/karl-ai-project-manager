# Changelog système

Évolutions du système de gestion de tâches dans son ensemble.
Pour les évolutions du schéma des tâches, voir [norms/CHANGELOG.md](norms/CHANGELOG.md).

Format : [Keep a Changelog](https://keepachangelog.com/fr/)

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
