#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run.sh — Lanzador del Sistema de Asistencia Facial (Linux / macOS)
#
# Que hace este script:
#   1. Cambia al directorio donde se encuentra (face_attendance_system/).
#   2. Si el entorno virtual (venv/) no existe, lo crea con python3 -m venv
#      e instala las dependencias desde requirements.txt.
#      Esto ocurre solo la primera vez.
#   3. Activa el entorno virtual.
#   4. Lanza main.py.
#   5. Si la app termina con error, muestra el codigo de salida y la ruta
#      del log para facilitar el diagnostico.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Cambiar al directorio donde esta este script (face_attendance_system/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Verificar / crear entorno virtual ─────────────────────────────────────────
if [ ! -f "venv/bin/python" ]; then
    echo ""
    echo " Entorno virtual no encontrado. Creando entorno e instalando dependencias..."
    echo " (Esto ocurre solo la primera vez)"
    echo ""
    python3 -m venv venv
    # shellcheck disable=SC1091
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

# ── Lanzar la aplicacion ──────────────────────────────────────────────────────
set +e
python main.py
EXIT_CODE=$?
set -e

# ── Manejar errores de la app ─────────────────────────────────────────────────
if [ "$EXIT_CODE" -ne 0 ]; then
    echo ""
    echo " La aplicacion termino con un error (codigo: $EXIT_CODE)."
    echo " Revisa el log en: data/app.log"
    echo ""
    exit "$EXIT_CODE"
fi
