"""Paquete principal de la API de Ares Pathfinder."""

import sys
from pathlib import Path

# Raíz del repositorio (mars-explorer-lab/). Se añadio a sys.path para poder
# importar el paquete `algorithms`, que vive fuera de `backend/`.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
