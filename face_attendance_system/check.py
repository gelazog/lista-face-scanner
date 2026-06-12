"""
check.py — Diagnóstico rápido del Sistema de Asistencia Facial.

No instala nada ni requiere activar el venv. Usa el Python del sistema
(o el del venv si ya está activado).

Uso:
    python check.py
    python face_attendance_system/check.py
"""

import os
import platform
import sqlite3
import sys
from pathlib import Path

# Forzar UTF-8 en stdout para Windows (evita UnicodeEncodeError con símbolos)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─── Colores ANSI ─────────────────────────────────────────────────────────────

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


# ─── Directorio base ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent


# ─── Helpers de formato ───────────────────────────────────────────────────────

COL_LABEL = 18  # ancho de la columna de etiquetas


def fila(etiqueta: str, exito: bool, detalle: str = ""):
    simbolo = verde("✓") if exito else rojo("✗")
    label = (etiqueta + ":").ljust(COL_LABEL)
    det = f"  {detalle}" if detalle else ""
    print(f"  {simbolo} {label}{det}")


def fila_info(etiqueta: str, detalle: str):
    label = (etiqueta + ":").ljust(COL_LABEL)
    print(f"  {cyan('→')} {label}{detalle}")


# ─── Verificación de dependencias ────────────────────────────────────────────

def verificar_dependencias() -> dict:
    """
    Intenta importar cada dependencia.
    Devuelve dict {nombre: (disponible, versión_o_mensaje)}.
    """
    paquetes = [
        ("cv2", "opencv-python"),
        ("insightface", "insightface"),
        ("onnxruntime", "onnxruntime"),
        ("PIL", "Pillow"),
        ("openpyxl", "openpyxl"),
        ("pandas", "pandas"),
        ("tkinter", "tkinter"),
    ]

    resultados = {}
    for modulo, nombre_legible in paquetes:
        try:
            mod = __import__(modulo)
            version = getattr(mod, "__version__", None)
            if version is None and modulo == "tkinter":
                # tkinter no expone __version__, pero podemos obtener la versión de Tcl
                try:
                    import tkinter as _tk
                    root = _tk.Tk()
                    version = root.tk.call("info", "patchlevel")
                    root.destroy()
                except Exception:
                    version = "disponible"
            resultados[nombre_legible] = (True, version or "ok")
        except ImportError as exc:
            resultados[nombre_legible] = (False, str(exc))

    return resultados


# ─── Detección de cámaras ────────────────────────────────────────────────────

def detectar_camaras() -> list[int]:
    """
    Itera índices 0-4. Para cada uno intenta abrir la cámara con un
    timeout implícito (cap.open es bloqueante pero rápido si la cámara no existe).
    Devuelve lista de índices disponibles.
    """
    disponibles = []

    try:
        import cv2  # type: ignore
    except ImportError:
        return []

    for idx in range(5):
        try:
            cap = cv2.VideoCapture(idx, cv2.CAP_ANY)
            if cap is not None and cap.isOpened():
                disponibles.append(idx)
            cap.release()
        except Exception:
            pass

    return disponibles


# ─── Base de datos ────────────────────────────────────────────────────────────

def verificar_base_de_datos() -> tuple[bool, str]:
    """
    Comprueba si la base de datos existe y devuelve el conteo de usuarios
    y registros de asistencia.
    Devuelve (existe, mensaje).
    """
    db_path = BASE_DIR / "data" / "attendance.db"

    if not db_path.exists():
        return False, "no encontrada"

    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        try:
            usuarios = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
            registros = conn.execute("SELECT COUNT(*) FROM asistencia").fetchone()[0]
            conn.close()
            return True, f"existe  ({usuarios} usuarios, {registros} registros)"
        except sqlite3.OperationalError:
            conn.close()
            return True, "existe (tablas no inicializadas — ejecuta setup.py)"
    except Exception as exc:
        return False, f"error al abrir: {exc}"


# ─── Modelos InsightFace ─────────────────────────────────────────────────────

def verificar_modelos() -> tuple[bool, str]:
    """Comprueba si el directorio de modelos buffalo_sc existe y no está vacío."""
    models_dir = Path.home() / ".insightface" / "models" / "buffalo_sc"

    if models_dir.exists() and any(models_dir.iterdir()):
        # Contar archivos .onnx para dar más detalle
        onnx_count = len(list(models_dir.glob("*.onnx")))
        return True, f"buffalo_sc descargado  ({onnx_count} modelos .onnx)"

    if models_dir.exists():
        return False, f"carpeta vacía en {models_dir}"

    return False, f"no encontrado en {models_dir}"


# ─── Función principal ────────────────────────────────────────────────────────

def main():
    print()
    print(negrita("=" * 54))
    print(negrita("   Diagnóstico del Sistema de Asistencia Facial"))
    print(negrita("=" * 54))
    print()

    # ── Python ────────────────────────────────────────────────────────────────
    version_str = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    python_ok = sys.version_info >= (3, 10)
    label_py = f"{version_str}"
    if not python_ok:
        label_py += amarillo("  (se requiere ≥3.10)")
    fila("Python", python_ok, label_py)

    # ── Dependencias ──────────────────────────────────────────────────────────
    print()
    deps = verificar_dependencias()
    for nombre, (ok_flag, detalle) in deps.items():
        fila(nombre, ok_flag, detalle if ok_flag else rojo(detalle))

    # ── Cámaras ───────────────────────────────────────────────────────────────
    print()
    cv2_ok = deps.get("opencv-python", (False,))[0]
    if cv2_ok:
        indices = detectar_camaras()
        if indices:
            fila_info(
                "Cámaras detectadas",
                f"{len(indices)}  (índices: {', '.join(str(i) for i in indices)})",
            )
        else:
            fila_info("Cámaras detectadas", amarillo("0  — no se detectó ninguna cámara"))
    else:
        fila_info("Cámaras detectadas", amarillo("no disponible  (opencv no instalado)"))

    # ── Base de datos ─────────────────────────────────────────────────────────
    print()
    db_ok, db_detalle = verificar_base_de_datos()
    fila("Base de datos", db_ok, db_detalle)

    # ── Modelos ───────────────────────────────────────────────────────────────
    modelos_ok, modelos_detalle = verificar_modelos()
    fila("Modelos IA", modelos_ok, modelos_detalle)

    # ── Información del sistema ───────────────────────────────────────────────
    print()
    fila_info("Sistema operativo", f"{platform.system()} {platform.release()}")
    fila_info("Ejecutable Python", sys.executable)

    # Detectar si estamos dentro del venv del proyecto
    venv_dir = BASE_DIR / "venv"
    dentro_del_venv = (
        sys.prefix != sys.base_prefix
        or str(venv_dir) in sys.executable
    )
    fila_info(
        "Entorno virtual",
        verde("activo") if dentro_del_venv else amarillo("inactivo — activa el venv para ejecutar la app"),
    )

    # ── Estado final ──────────────────────────────────────────────────────────
    print()
    print("─" * 54)

    deps_ok = all(v for v, _ in deps.values())
    todo_listo = python_ok and deps_ok and db_ok and modelos_ok

    if todo_listo:
        print(f"\n  {verde(negrita('Estado:'))} {verde('LISTO para ejecutar.')}")
        if platform.system() == "Windows":
            print(f"  Usa: {cyan('run.bat')}  o  {cyan('python main.py')}  (con venv activo)")
        else:
            print(f"  Usa: {cyan('bash run.sh')}  o  {cyan('python main.py')}  (con venv activo)")
    else:
        problemas = []
        if not python_ok:
            problemas.append("versión de Python")
        if not deps_ok:
            faltantes = [n for n, (ok_flag, _) in deps.items() if not ok_flag]
            problemas.append(f"dependencias faltantes: {', '.join(faltantes)}")
        if not db_ok:
            problemas.append("base de datos")
        if not modelos_ok:
            problemas.append("modelos InsightFace")

        print(f"\n  {amarillo(negrita('Estado:'))} {amarillo('NO listo — ejecuta setup.py para corregir.')}")
        for p in problemas:
            print(f"    {rojo('•')} {p}")
        print(f"\n  Ejecuta: {cyan('python setup.py')}")

    print()


if __name__ == "__main__":
    main()
