"""
setup.py — Script de configuración e instalación del Sistema de Asistencia Facial.

Uso:
    python setup.py                   # ejecutar desde cualquier directorio
    python face_attendance_system/setup.py

Pasos que realiza:
  1. Verifica versión de Python (≥3.10)
  2. Verifica que pip está disponible
  3. Crea/verifica el entorno virtual en venv/
  4. Instala dependencias desde requirements.txt
  5. Verifica que cada dependencia importa correctamente
  6. Crea directorios necesarios (data/users/, exports/)
  7. Inicializa la base de datos
  8. Descarga los modelos de InsightFace (buffalo_sc)
  9. Imprime resumen final
"""

import ast
import os
import platform
import subprocess
import sys
import venv
from pathlib import Path

# ─── Colores ANSI ─────────────────────────────────────────────────────────────

# Desactivar colores si la terminal no los soporta
_USE_COLOR = sys.stdout.isatty() or os.environ.get("FORCE_COLOR", "0") == "1"


def _c(code: str, text: str) -> str:
    if _USE_COLOR:
        return f"\033[{code}m{text}\033[0m"
    return text


def verde(t: str) -> str:
    return _c("32", t)


def rojo(t: str) -> str:
    return _c("31", t)


def amarillo(t: str) -> str:
    return _c("33", t)


def negrita(t: str) -> str:
    return _c("1", t)


def cyan(t: str) -> str:
    return _c("36", t)


# ─── Utilidades de I/O ────────────────────────────────────────────────────────

def ok(msg: str):
    print(f"  {verde('✓')} {msg}")


def err(msg: str):
    print(f"  {rojo('✗')} {msg}")


def aviso(msg: str):
    print(f"  {amarillo('!')} {msg}")


def info(msg: str):
    print(f"  {cyan('→')} {msg}")


def titulo(msg: str):
    print(f"\n{negrita(msg)}")


def separador():
    print("─" * 52)


def preguntar_continuar(pregunta: str = "¿Continuar de todos modos?") -> bool:
    """Pregunta al usuario si continuar o abortar. Devuelve True para continuar."""
    while True:
        resp = input(f"  {amarillo('?')} {pregunta} [s/N]: ").strip().lower()
        if resp in ("s", "si", "sí", "y", "yes"):
            return True
        if resp in ("n", "no", ""):
            return False
        print("    Por favor responde 's' para sí o 'n' para no.")


# ─── Directorio base ──────────────────────────────────────────────────────────

# El script puede ejecutarse desde dentro o fuera de face_attendance_system/
_SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = _SCRIPT_DIR  # siempre apunta a face_attendance_system/

VENV_DIR = BASE_DIR / "venv"
REQUIREMENTS = BASE_DIR / "requirements.txt"


def _python_del_venv() -> Path:
    """Ruta al ejecutable de Python dentro del venv."""
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _pip_del_venv() -> Path:
    """Ruta a pip dentro del venv."""
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


# ─── Pasos de configuración ───────────────────────────────────────────────────

def paso_verificar_python() -> bool:
    """Paso 1: Verificar que la versión de Python es ≥3.10."""
    titulo("Paso 1/9 — Verificando versión de Python")
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    if version.major < 3 or (version.major == 3 and version.minor < 10):
        err(
            f"Python {version_str} detectado. Se requiere Python 3.10 o superior.\n"
            f"    Descarga la versión más reciente en: https://www.python.org/downloads/"
        )
        return False

    ok(f"Python {version_str}")
    return True


def paso_verificar_pip() -> bool:
    """Paso 2: Verificar que pip está disponible en el Python actual."""
    titulo("Paso 2/9 — Verificando pip")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err("pip no está disponible en este Python.")
        info("Intenta: python -m ensurepip --upgrade")
        return False

    version_pip = result.stdout.split()[1] if result.stdout else "?"
    ok(f"pip {version_pip}")
    return True


def paso_crear_venv() -> bool:
    """Paso 3: Crear o verificar el entorno virtual."""
    titulo("Paso 3/9 — Entorno virtual")
    python_venv = _python_del_venv()

    if VENV_DIR.exists() and python_venv.exists():
        aviso(f"El entorno virtual ya existe en: {VENV_DIR}")
        regenerar = preguntar_continuar("¿Deseas regenerar el entorno virtual (borrará el existente)?")
        if regenerar:
            info("Eliminando entorno virtual anterior...")
            import shutil
            shutil.rmtree(VENV_DIR)
        else:
            ok(f"Usando entorno virtual existente en {VENV_DIR}")
            return True

    info(f"Creando entorno virtual en {VENV_DIR} ...")
    try:
        builder = venv.EnvBuilder(
            system_site_packages=False,
            clear=False,
            with_pip=True,
        )
        builder.create(str(VENV_DIR))
    except Exception as exc:
        err(f"No se pudo crear el entorno virtual: {exc}")
        return False

    if not python_venv.exists():
        err(f"El entorno virtual se creó pero no se encontró el ejecutable: {python_venv}")
        return False

    ok(f"Entorno virtual creado en {VENV_DIR}")
    return True


def paso_instalar_dependencias() -> bool:
    """Paso 4: Instalar/actualizar dependencias desde requirements.txt."""
    titulo("Paso 4/9 — Instalando dependencias")

    if not REQUIREMENTS.exists():
        err(f"No se encontró requirements.txt en {REQUIREMENTS}")
        return False

    python_venv = _python_del_venv()
    if not python_venv.exists():
        err("No se encontró el Python del entorno virtual. Ejecuta el paso 3 primero.")
        return False

    info("Actualizando pip dentro del venv...")
    subprocess.run(
        [str(python_venv), "-m", "pip", "install", "--upgrade", "pip"],
        capture_output=True,
    )

    info(f"Instalando paquetes desde {REQUIREMENTS} ...")
    print()
    result = subprocess.run(
        [
            str(python_venv),
            "-m",
            "pip",
            "install",
            "--requirement",
            str(REQUIREMENTS),
        ],
        # No capturamos la salida — la mostramos en tiempo real para que el
        # usuario vea el progreso de descarga.
    )
    print()

    if result.returncode != 0:
        err("La instalación de dependencias falló.")
        return False

    ok("Dependencias instaladas correctamente")
    return True


def paso_verificar_imports() -> bool:
    """Paso 5: Verificar que cada dependencia importa correctamente desde el venv."""
    titulo("Paso 5/9 — Verificando imports")

    python_venv = _python_del_venv()

    # (módulo_a_importar, nombre_legible, instrucciones_si_falla)
    dependencias = [
        ("cv2", "opencv-python", None),
        ("insightface", "insightface", None),
        ("onnxruntime", "onnxruntime", None),
        ("PIL", "Pillow", None),
        ("openpyxl", "openpyxl", None),
        ("pandas", "pandas", None),
        (
            "tkinter",
            "tkinter",
            {
                "Windows": "Reinstala Python desde https://python.org y asegúrate de marcar 'tcl/tk and IDLE'.",
                "Darwin": "Instala Python desde https://python.org (la versión Homebrew puede omitir tkinter).",
                "Linux": "Ejecuta: sudo apt-get install python3-tk  (Debian/Ubuntu)\n"
                "         o: sudo dnf install python3-tkinter  (Fedora/RHEL)",
            },
        ),
    ]

    todo_ok = True
    for modulo, nombre, instrucciones in dependencias:
        # tkinter viene con Python, verificar con el Python del venv
        check_code = f"import {modulo}; print(getattr({modulo}, '__version__', 'ok'))"
        result = subprocess.run(
            [str(python_venv), "-c", check_code],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            version_out = result.stdout.strip() or "ok"
            ok(f"{nombre}  ({version_out})")
        else:
            err(f"{nombre}  — no se pudo importar")
            todo_ok = False
            if instrucciones:
                sistema = platform.system()
                msg = instrucciones.get(sistema) or instrucciones.get("Linux", "")
                if msg:
                    for linea in msg.splitlines():
                        aviso(f"    {linea}")

    return todo_ok


def paso_crear_directorios() -> bool:
    """Paso 6: Crear directorios necesarios."""
    titulo("Paso 6/9 — Creando directorios")

    directorios = [
        BASE_DIR / "data" / "users",
        BASE_DIR / "exports",
    ]

    for d in directorios:
        try:
            d.mkdir(parents=True, exist_ok=True)
            ok(f"{d.relative_to(BASE_DIR)}")
        except OSError as exc:
            err(f"No se pudo crear {d}: {exc}")
            return False

    return True


def paso_inicializar_db() -> bool:
    """Paso 7: Inicializar la base de datos."""
    titulo("Paso 7/9 — Inicializando base de datos")

    python_venv = _python_del_venv()
    codigo = (
        "import sys, os; "
        f"sys.path.insert(0, {str(BASE_DIR)!r}); "
        "os.chdir(sys.path[0]); "
        "from database import inicializar_base_de_datos; "
        "inicializar_base_de_datos(); "
        "print('ok')"
    )

    result = subprocess.run(
        [str(python_venv), "-c", codigo],
        capture_output=True,
        text=True,
        cwd=str(BASE_DIR),
    )

    if result.returncode == 0 and "ok" in result.stdout:
        ok("Base de datos inicializada correctamente")
        return True

    err("No se pudo inicializar la base de datos")
    if result.stderr:
        for linea in result.stderr.strip().splitlines()[-5:]:
            aviso(f"    {linea}")
    return False


def paso_descargar_modelos() -> bool:
    """Paso 8: Descargar modelos de InsightFace si no existen."""
    titulo("Paso 8/9 — Modelos InsightFace (buffalo_sc)")

    models_dir = Path.home() / ".insightface" / "models" / "buffalo_sc"

    if models_dir.exists() and any(models_dir.iterdir()):
        ok(f"Modelos ya descargados en {models_dir}")
        return True

    info("Descargando modelos buffalo_sc (~30 MB), por favor espera...")
    info("(Esta descarga ocurre solo la primera vez)")
    print()

    python_venv = _python_del_venv()
    codigo = (
        "import warnings; warnings.filterwarnings('ignore'); "
        "from insightface.app import FaceAnalysis; "
        "app = FaceAnalysis(name='buffalo_sc', providers=['CPUExecutionProvider']); "
        "app.prepare(ctx_id=-1, det_size=(320, 320)); "
        "print('descarga_ok')"
    )

    result = subprocess.run(
        [str(python_venv), "-c", codigo],
        capture_output=True,
        text=True,
        timeout=300,  # 5 minutos máximo
    )
    print()

    if result.returncode == 0 and "descarga_ok" in result.stdout:
        ok("Modelos InsightFace descargados correctamente")
        return True

    # Puede que los modelos se descargaran pero haya otro error al preparar
    if models_dir.exists() and any(models_dir.iterdir()):
        ok(f"Modelos descargados en {models_dir} (con advertencias menores)")
        return True

    err("No se pudieron descargar los modelos de InsightFace")
    if result.stderr:
        for linea in result.stderr.strip().splitlines()[-8:]:
            aviso(f"    {linea}")
    aviso("    Puedes descargarlos manualmente desde:")
    aviso("    https://github.com/deepinsight/insightface/releases")
    return False


def paso_resumen(resultados: dict):
    """Paso 9: Imprimir resumen final."""
    titulo("Resumen de configuración")
    separador()

    version_str = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )

    pasos = [
        ("Python " + version_str, resultados.get("python", False)),
        ("Dependencias instaladas", resultados.get("deps", False)),
        ("Imports verificados", resultados.get("imports", False)),
        ("Directorios creados", resultados.get("dirs", False)),
        ("Base de datos lista", resultados.get("db", False)),
        ("Modelos InsightFace", resultados.get("modelos", False)),
    ]

    todo_ok = all(v for _, v in pasos)

    for nombre, exito in pasos:
        simbolo = verde("✓") if exito else rojo("✗")
        print(f"  {simbolo} {nombre}")

    separador()

    if todo_ok:
        print(f"\n{verde(negrita('¡Configuración completada con éxito!'))}\n")
        print(f"  Para iniciar la app:")
        if platform.system() == "Windows":
            print(f"    {cyan('run.bat')}              (doble clic o desde CMD)")
        else:
            print(f"    {cyan('bash run.sh')}")
        print(f"    {cyan('python main.py')}       (con el venv activado)")
        print()
        if platform.system() == "Windows":
            print(f"  Activar el venv manualmente:  {cyan('venv\\Scripts\\activate')}")
        else:
            print(f"  Activar el venv manualmente:  {cyan('source venv/bin/activate')}")
    else:
        fallidos = [n for n, v in pasos if not v]
        print(f"\n{amarillo(negrita('Configuración completada con advertencias.'))}")
        print(f"  Los siguientes pasos tuvieron problemas: {', '.join(fallidos)}")
        print("  Revisa los mensajes anteriores para más detalles.")

    print()


# ─── Función principal ────────────────────────────────────────────────────────

def main():
    print()
    print(negrita("=" * 52))
    print(negrita("  Sistema de Asistencia Facial — Configuración"))
    print(negrita("=" * 52))

    resultados = {}

    # ── Paso 1: Python ──────────────────────────────────────────────────────
    resultados["python"] = paso_verificar_python()
    if not resultados["python"]:
        sys.exit(1)

    # ── Paso 2: pip ──────────────────────────────────────────────────────────
    pip_ok = paso_verificar_pip()
    if not pip_ok:
        if not preguntar_continuar("pip no está disponible. ¿Continuar de todos modos?"):
            sys.exit(1)

    # ── Paso 3: venv ─────────────────────────────────────────────────────────
    venv_ok = paso_crear_venv()
    if not venv_ok:
        if not preguntar_continuar("No se pudo crear el entorno virtual. ¿Continuar?"):
            sys.exit(1)

    # ── Paso 4: dependencias ─────────────────────────────────────────────────
    resultados["deps"] = paso_instalar_dependencias()
    if not resultados["deps"]:
        if not preguntar_continuar("La instalación de dependencias falló. ¿Continuar?"):
            sys.exit(1)

    # ── Paso 5: imports ──────────────────────────────────────────────────────
    resultados["imports"] = paso_verificar_imports()
    if not resultados["imports"]:
        if not preguntar_continuar("Algunos imports fallaron. ¿Continuar?"):
            sys.exit(1)

    # ── Paso 6: directorios ──────────────────────────────────────────────────
    resultados["dirs"] = paso_crear_directorios()
    if not resultados["dirs"]:
        if not preguntar_continuar("No se pudieron crear algunos directorios. ¿Continuar?"):
            sys.exit(1)

    # ── Paso 7: base de datos ────────────────────────────────────────────────
    resultados["db"] = paso_inicializar_db()
    if not resultados["db"]:
        if not preguntar_continuar("No se pudo inicializar la base de datos. ¿Continuar?"):
            sys.exit(1)

    # ── Paso 8: modelos InsightFace ──────────────────────────────────────────
    resultados["modelos"] = paso_descargar_modelos()
    if not resultados["modelos"]:
        aviso("Puedes ejecutar la app sin los modelos, pero el reconocimiento facial no funcionará.")
        if not preguntar_continuar("¿Continuar de todos modos?"):
            sys.exit(1)

    # ── Paso 9: resumen ──────────────────────────────────────────────────────
    paso_resumen(resultados)

    # Código de salida: 0 si todo OK, 1 si hubo fallos
    if not all(resultados.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
