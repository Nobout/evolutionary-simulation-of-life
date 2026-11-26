"""Point d'entrée de l'application Evolutionary Simulation of Life."""

import sys
from pathlib import Path

# Ajoute src/ au sys.path pour les imports modulaires (core.*, gui.*)
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Evolutionary Simulation of Life")

    # Fenêtre principale avec overlay de configuration intégré
    window = MainWindow()

    # Positionnement sur l'écran principal
    primary = QGuiApplication.primaryScreen()
    if primary:
        geo = primary.availableGeometry()
        window.move(geo.topLeft())
        if window.windowHandle():
            window.windowHandle().setScreen(primary)

    # Ouverture maximisée avec focus immédiat
    window.showMaximized()
    window.raise_()
    window.activateWindow()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
