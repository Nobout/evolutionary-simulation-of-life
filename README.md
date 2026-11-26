# Evolutionary Simulation of Life



Simulation d'écosystème 2D en temps réel développée en Python avec une interface graphique interactive sous Qt (PySide6). Le projet modélise les interactions dynamiques et l'évolution d'agents autonomes au sein de leur environnement.



## Structure du projet

```text
.
├── .gitignore
├── README.md
├── requirements.txt
├── src/
│   ├── core/
│   │   ├── tiles.py
│   │   ├── world.py
│   │   └── world\_generator.py
│   ├── gui/
│   │   ├── hud\_bar.py
│   │   ├── main\_window.py
│   │   ├── map\_view.py
│   │   └── new\_map\_overlay.py
│   └── main.py
└── tests/
```



## Installation



### 1\. Environnement virtuel (.venv)



**Windows (PowerShell) :**



```powershell
python -m venv .venv
.venv\\Scripts\\Activate.ps1
```

*(Si vous utilisez l'Invite de commandes `cmd.exe` : `.venv\\Scripts\\activate.bat`)*



**Linux / macOS :**



```bash
python3 -m venv .venv
source .venv/bin/activate
```



### 2\. Dépendances



```bash
pip install -r requirements.txt
```



## Lancement de l'application



```bash
python src/main.py
```

