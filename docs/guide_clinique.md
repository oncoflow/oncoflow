# 🩺 Oncoflow — Guide à l'usage des Cliniciens

Bienvenue dans le guide d'utilisation d'**Oncoflow**. Cet espace est conçu pour vous aider à comprendre comment notre solution d'intelligence artificielle locale vous accompagne dans la préparation et la tenue des **Réunions de Concertation Pluridisciplinaire (RCP)** en oncologie digestive.

---

## 🌟 La Vision Oncoflow

La préparation d'une RCP est chronophage et exigeante. **Oncoflow** a été créé en étroite collaboration avec des professionnels de santé pour automatiser les tâches administratives et de synthèse complexes, vous permettant de vous concentrer sur votre cœur de métier : **la décision thérapeutique**.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Le Flux de Travail Oncoflow                     │
├────────────────────────────────────────────────────────────────────────┤
│  [1] Dépôt PDF ──► [2] Analyse & OCR ──► [3] Triage ──► [4] Aide TNCD  │
│    (Dossiers)       (Pièces manquantes)  (Priorisation) (Décisions)    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 💡 Fonctionnalités Clés pour le Praticien

### 1. Synthèse Automatisée du Dossier Patient
Dès que les documents médicaux (comptes-rendus d'anatomopathologie, d'imagerie, de chirurgie) sont importés, Oncoflow en extrait les informations cruciales :
* **Identité et Contexte général** (Âge, antécédents, état général OMS/ECOG).
* **Données Oncologiques** (Localisation tumorale, type histologique, classification TNM/pTNM).
* **Marqueurs Biologiques** et examens d'imagerie clés (TDM, IRM, TEP-scan).

### 2. Détection Préventive des Dossiers Incomplets (Missing Records)
Pour éviter de reporter l'examen d'un patient lors de la réunion par manque d'informations :
* L'IA analyse la présence de toutes les pièces requises selon le type de pathologie suspecté.
* Une **alerte visuelle immédiate** est émise si un document ou une donnée obligatoire (ex. taille tumorale, statut de la biopsie) fait défaut.

### 3. Triage et Priorisation des Dossiers
Les réunions RCP disposent d'un temps limité. Oncoflow analyse la complexité clinique intrinsèque de chaque cas et propose :
* Un **ordre de passage optimisé** afin de traiter en priorité les cas hautement urgents ou complexes nécessitant un débat approfondi.
* Un gain de temps sur les dossiers standards dont la prise en charge est balisée.

### 4. Alignement Scientifique : Le Référentiel TNCD
Oncoflow intègre nativement le **Thésaurus National de Cancérologie Digestive (TNCD)**, la référence scientifique officielle en France :
* L'IA interroge en temps réel le référentiel TNCD en fonction des caractéristiques du patient.
* Elle vous suggère des propositions de schémas thérapeutiques (chirurgie première, chimiothérapie péri-opératoire, radio-chimiothérapie) conformes aux recommandations à jour, servant de garde-fou clinique.

---

## 🔒 Confidentialité & Sécurité des Données (Souveraineté Totale)

> [!CAUTION] **Zéro Cloud — Zéro Fuite de Données**
> Les données de vos patients ne quittent **jamais** l'établissement de santé. Oncoflow est une solution **local-first** :
> * Aucun appel à des serveurs tiers ou des API publiques (type OpenAI, Google ou Anthropic).
> * Les modèles de traitement du langage (LLM) s'exécutent **localement** sur l'infrastructure sécurisée de l'hôpital.
> * Conformité totale avec le **RGPD** et les exigences de l'**Hébergement de Données de Santé (HDS)**.

---

## 🖥️ Navigation dans l'Interface Streamlit

L'interface est structurée pour être simple et intuitive, accessible depuis n'importe quel navigateur interne à l'hôpital.

### 📇 1. Dossiers Patients (Cards)
* **Votre tableau de bord central** : structuré en deux sections complémentaires :
  * **📁 Dossiers Patients (en haut)** : affiche une carte par patient, synthétisée à partir de sa **dernière fiche RCP analysée** (urgence, statut d'exhaustivité, intervention conseillée, experts pertinents et nombre total de RCP du patient).
  * **📄 Dernières RCP scannées (en dessous)** : présente les dernières fiches RCP individuelles par ordre chronologique de numérisation/import.

### 📝 2. Dossier Patient (Datas)
* Vue détaillée unifiée du **Dossier Patient**, organisée en **3 onglets principaux** en haut de page :
  * **👤 Données patient** : affiche le bandeau d'identité administrative du patient ainsi que la **dernière fiche RCP analysée** (PDF à gauche et onglets *Données Cliniques*, *Assistant IA sur la fiche* et *Aperçu du document* à droite).
  * **🕰️ Historique des fiches RCP** : permet de remonter dans le temps sur toutes les fiches RCP du patient via un sélecteur chronologique, avec la même vue détaillée par fiche (PDF + *Données Cliniques*, *Assistant IA sur la fiche* isolé sur la fiche courante, et *Aperçu du document*).
  * **💬 Assistant IA sur le dossier** : onglet de chat interrogeant l'agent expert sur **l'intégralité du dossier patient** (toutes ses fiches RCP passées et présentes, l'historique complet des informations IA extraites via le tool `get_patient_ai_history`, et les référentiels TNCD).
  * **🔄 Relance IA (Rerun) fiche par fiche** : la relance de l'analyse IA (`🔄 Relancer cette RCP`, `:material/robot: AI exec` par rubrique, ou `:repeat: AI process` en Power mode) est sélectionnable et exécutée **exclusivement RCP par RCP** (jamais sur l'ensemble du dossier simultanément).

### 🚀 3. Charger le/les fichier(s) (Upload)
* Espace de dépôt sécurisé supportant l'import **unitaire ou par lot (batch)** de plusieurs fiches PDF RCP.
* **Association à un patient** :
  * **Mode Automatique (par défaut)** : lance l'indexation RAG et l'extraction administrative par l'IA (`Prénom`, `Nom`, `Date de naissance`) pour créer automatiquement le patient ou rattacher la fiche à un dossier patient existant.
  * **Association manuelle** : permet de sélectionner un patient existant (globalement pour le lot ou fichier par fichier avant de lancer l'import).

### 🤖 4. Agents and Ressources
* Vue transparente sur l'activité des "agents" IA spécialisés à l'œuvre. Vous pouvez voir quel agent (le "Docteur virtuel" ou le "Spécialiste TNCD") a extrait et validé les données.

---

## 🧑‍⚕️ Vos Retours sont Précieux

Oncoflow est un projet open-source évolutif. Si vous remarquez des écarts dans les résumés ou si vous souhaitez suggérer l'ajout d'un nouveau référentiel clinique, vous pouvez soumettre un signalement directement via l'onglet **Bug reports (Reports)** dans l'interface, ou vous rapprocher de votre équipe informatique hospitalière.
