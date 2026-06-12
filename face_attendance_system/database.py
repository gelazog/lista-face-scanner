"""
Módulo de base de datos SQLite para el sistema de asistencia facial.
Gestiona usuarios, registros de asistencia y consultas.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from contextlib import contextmanager

# Ruta a la base de datos
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "attendance.db")


@contextmanager
def _conexion():
    """Manejador de contexto para conexiones SQLite."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def inicializar_base_de_datos():
    """Crea las tablas e índices si no existen."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _conexion() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre      TEXT NOT NULL,
                apellido    TEXT NOT NULL,
                ruta_carpeta TEXT NOT NULL,
                creado_en   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS asistencia (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
                detectado_en TEXT NOT NULL,
                presente    INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_asistencia_detectado_en
                ON asistencia(detectado_en);

            CREATE INDEX IF NOT EXISTS idx_asistencia_usuario_id
                ON asistencia(usuario_id);

            CREATE INDEX IF NOT EXISTS idx_asistencia_usuario_fecha
                ON asistencia(usuario_id, detectado_en);
        """)


# ─── USUARIOS ────────────────────────────────────────────────────────────────

def insertar_usuario(nombre: str, apellido: str, ruta_carpeta: str) -> int:
    """Inserta un nuevo usuario y devuelve su ID."""
    creado_en = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conexion() as conn:
        cur = conn.execute(
            "INSERT INTO usuarios (nombre, apellido, ruta_carpeta, creado_en) VALUES (?, ?, ?, ?)",
            (nombre.strip(), apellido.strip(), ruta_carpeta, creado_en)
        )
        return cur.lastrowid


def obtener_todos_los_usuarios() -> list[dict]:
    """Devuelve todos los usuarios registrados."""
    with _conexion() as conn:
        filas = conn.execute(
            "SELECT id, nombre, apellido, ruta_carpeta, creado_en FROM usuarios ORDER BY nombre"
        ).fetchall()
        return [dict(f) for f in filas]


def usuario_existe(nombre: str, apellido: str) -> bool:
    """Verifica si ya existe un usuario con ese nombre y apellido."""
    with _conexion() as conn:
        fila = conn.execute(
            "SELECT 1 FROM usuarios WHERE LOWER(nombre)=LOWER(?) AND LOWER(apellido)=LOWER(?)",
            (nombre.strip(), apellido.strip())
        ).fetchone()
        return fila is not None


def obtener_usuario_por_nombre_completo(nombre: str, apellido: str) -> dict | None:
    """Devuelve los datos de un usuario por nombre y apellido."""
    with _conexion() as conn:
        fila = conn.execute(
            "SELECT * FROM usuarios WHERE LOWER(nombre)=LOWER(?) AND LOWER(apellido)=LOWER(?)",
            (nombre.strip(), apellido.strip())
        ).fetchone()
        return dict(fila) if fila else None


def eliminar_usuario(usuario_id: int):
    """Elimina un usuario y sus registros de asistencia."""
    with _conexion() as conn:
        conn.execute("DELETE FROM asistencia WHERE usuario_id=?", (usuario_id,))
        conn.execute("DELETE FROM usuarios WHERE id=?", (usuario_id,))


# ─── ASISTENCIA ───────────────────────────────────────────────────────────────

def insertar_asistencia(usuario_id: int) -> bool:
    """
    Registra una detección de asistencia.
    Devuelve True si se insertó, False si ya se registró en los últimos 5 minutos.
    """
    ahora = datetime.now()
    hace_5_min = (ahora - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    ahora_str = ahora.strftime("%Y-%m-%d %H:%M:%S")

    with _conexion() as conn:
        duplicado = conn.execute(
            """SELECT 1 FROM asistencia
               WHERE usuario_id=? AND detectado_en >= ?""",
            (usuario_id, hace_5_min)
        ).fetchone()

        if duplicado:
            return False

        conn.execute(
            "INSERT INTO asistencia (usuario_id, detectado_en, presente) VALUES (?, ?, 1)",
            (usuario_id, ahora_str)
        )
        return True


def obtener_detecciones_recientes(limite: int = 50) -> list[dict]:
    """Devuelve los últimos N registros de asistencia con datos del usuario."""
    with _conexion() as conn:
        filas = conn.execute(
            """SELECT
                a.id,
                u.nombre,
                u.apellido,
                DATE(a.detectado_en) AS fecha,
                TIME(a.detectado_en) AS hora,
                CASE WHEN a.presente=1 THEN 'Presente' ELSE 'Ausente' END AS estado
               FROM asistencia a
               JOIN usuarios u ON u.id = a.usuario_id
               ORDER BY a.detectado_en DESC
               LIMIT ?""",
            (limite,)
        ).fetchall()
        return [dict(f) for f in filas]


def obtener_asistencia_por_rango(fecha_inicio: str, fecha_fin: str) -> list[dict]:
    """
    Devuelve registros de asistencia entre dos fechas (formato YYYY-MM-DD).
    Incluye usuarios sin registro en ese rango (presente=No).
    """
    with _conexion() as conn:
        # Usuarios presentes en el rango
        filas = conn.execute(
            """SELECT
                u.nombre,
                u.apellido,
                DATE(a.detectado_en) AS fecha,
                TIME(a.detectado_en) AS hora,
                1 AS presente
               FROM asistencia a
               JOIN usuarios u ON u.id = a.usuario_id
               WHERE DATE(a.detectado_en) BETWEEN ? AND ?
               ORDER BY a.detectado_en ASC""",
            (fecha_inicio, fecha_fin)
        ).fetchall()
        return [dict(f) for f in filas]


def obtener_resumen_asistencia(fecha_inicio: str, fecha_fin: str) -> list[dict]:
    """
    Devuelve un resumen: todos los usuarios con si estuvieron presentes o no
    en al menos una sesión dentro del rango.
    """
    with _conexion() as conn:
        todos = conn.execute(
            "SELECT id, nombre, apellido FROM usuarios ORDER BY nombre"
        ).fetchall()

        resultado = []
        for u in todos:
            presencia = conn.execute(
                """SELECT COUNT(*) as total FROM asistencia
                   WHERE usuario_id=? AND DATE(detectado_en) BETWEEN ? AND ?""",
                (u["id"], fecha_inicio, fecha_fin)
            ).fetchone()
            resultado.append({
                "nombre": u["nombre"],
                "apellido": u["apellido"],
                "presente": presencia["total"] > 0,
                "total_detecciones": presencia["total"]
            })
        return resultado


def obtener_id_usuario_por_nombre(nombre_completo: str) -> int | None:
    """
    Busca el ID de usuario dado un nombre completo 'Nombre Apellido'.
    """
    partes = nombre_completo.strip().split(" ", 1)
    if len(partes) < 2:
        return None
    nombre, apellido = partes[0], partes[1]
    with _conexion() as conn:
        fila = conn.execute(
            "SELECT id FROM usuarios WHERE LOWER(nombre)=LOWER(?) AND LOWER(apellido)=LOWER(?)",
            (nombre, apellido)
        ).fetchone()
        return fila["id"] if fila else None
