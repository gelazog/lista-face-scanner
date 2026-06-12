@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: run.bat — Lanzador del Sistema de Asistencia Facial (Windows)
::
:: Que hace este script:
::   1. Cambia al directorio donde se encuentra (face_attendance_system/).
::   2. Si el entorno virtual (venv/) no existe, ejecuta setup.py para
::      crearlo, instalar dependencias y descargar los modelos de IA.
::      Esto ocurre solo la primera vez.
::   3. Activa el entorno virtual.
::   4. Lanza main.py con la bandera -X utf8 para garantizar codificacion
::      UTF-8 en consola (necesario en Python 3 sobre Windows 10/11).
::   5. Si la app termina con error, muestra un aviso y pausa la ventana
::      para que el usuario pueda leer el mensaje antes de que se cierre.
:: ─────────────────────────────────────────────────────────────────────────────

:: Cambiar al directorio donde esta este script (face_attendance_system/)
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

:: ── Lanzar la aplicacion (UTF-8 forzado para Python 3) ───────────────────────
python -X utf8 main.py

:: ── Manejar errores de la app ─────────────────────────────────────────────────
if errorlevel 1 (
    echo.
    echo  La aplicacion termino con un error.
    echo  Revisa el log en: data\app.log
    echo.
    pause
)
