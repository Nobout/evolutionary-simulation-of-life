# Evolutionary Simulation of Life

Projet d'ingénierie (4A) portant sur la modélisation et la simulation d'un écosystème multi-agents autonome.

Dépôt : github.com/Nobout/evolutionary-simulation-of-life

**Présentation**

Ce projet vise à modéliser un environnement discret dans lequel évoluent des agents autonomes soumis à des contraintes de survie, d'exploitation de ressources et de reproduction. L'objectif est d'observer l'émergence de dynamiques démographiques et de comportements adaptatifs à partir de règles locales simples.

**Fonctionnalités cibles**

Comportement des agents : gestion des besoins physiologiques (faim, énergie), perception locale, récolte de ressources (nourriture, bois, pierre) et construction d'abris.

Dynamique de population : reproduction conditionnée par les réserves énergétiques, mortalité naturelle et transmission héréditaire de caractéristiques élémentaires.

Supervision & Métriques : tableau de bord en temps réel permettant de suivre l'évolution des stocks et les courbes de population.

**Environnement technique**

Langage : Python 3

Interface graphique : Qt (PySide6 / PyQt6)

Architecture : découplage strict entre le moteur logique de simulation et l'interface de visualisation (MVC).

## Installation & Lancement ##

**Cloner le dépôt**
git clone https://github.com/Nobout/evolutionary-simulation-of-life.git
cd evolutionary-simulation-of-life

### Créer un environnement virtuel
python -m venv venv
source venv/bin/activate  # Sur Windows : venv\Scripts\activate

### Installer les dépendances (à venir)
pip install -r requirements.txt
