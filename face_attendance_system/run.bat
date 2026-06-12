@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: run.bat — Lanzador del Sistema de Asistencia Facial (Windows)
::
:: - Si el venv no existe, ejecuta setup.py primero.
:: - Activa el venv y lanza main.py.
:: - Si la app termina con error, muestra un aviso y pausa.
:: ─────────────────────────────────────────────────────────────────────────────

:: Cambiar al directorio donde está este script (face_attendance_system/)
cd /d "%~dp0"

:: ── Verificar / crear entorno virtual ────────────────────────────────────────
if not exist "venv\Scripts\python.exe" (
    echo.
    echo  Entorno virtual no encontrado. Ejecutando configuracion inicial...
    echo  ^(Esto ocurre solo la primera vez^)
    echo.
    python setup.py
    if errorlevel 1 (
        echo.
        echo  La configuracion fallo. Revisa los mensajes anteriores.
        pause
        exit /b 1
    )
)

:: ── Activar el entorno virtual ────────────────────────────────────────────────
call venv\Scripts\activate

:: ── Lanzar la aplicacion ──────────────────────────────────────────────────────
python main.py

:: ── Manejar errores de la app ────────────────────────────────────────────────
if errorlevel 1 (
    echo.
    echo  La aplicacion termino con un error.
    echo  Revisa el log en: data\app.log
    echo.
    pause
)
