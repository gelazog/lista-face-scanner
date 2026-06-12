#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run.sh — Lanzador del Sistema de Asistencia Facial (Linux / macOS)
#
# - Si el venv no existe, ejecuta setup.py primero.
# - Activa el venv y lanza main.py.
# - Si la app termina con error, muestra un aviso.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Cambiar al directorio donde está este script (face_attendance_system/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Verificar / crear entorno virtual ─────────────────────────────────────────
if [ ! -f "venv/bin/python" ]; then
    echo ""
    echo " Entorno virtual no encontrado. Ejecutando configuración inicial..."
    echo " (Esto ocurre solo la primera vez)"
    echo ""
    python3 setup.py
fi

# ── Activar el entorno virtual ────────────────────────────────────────────────
# shellcheck disable=SC1091
source venv/bin/activate

# ── Lanzar la aplicación ──────────────────────────────────────────────────────
set +e
python main.py
EXIT_CODE=$?
set -e

# ── Manejar errores de la app ─────────────────────────────────────────────────
if [ "$EXIT_CODE" -ne 0 ]; then
    echo ""
    echo " La aplicación terminó con un error (código: $EXIT_CODE)."
    echo " Revisa el log en: data/app.log"
    echo ""
    exit "$EXIT_CODE"
fi
