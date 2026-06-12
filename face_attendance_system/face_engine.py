"""
Motor de reconocimiento facial usando InsightFace + ONNX.
No requiere dlib, cmake ni Visual Studio.
"""

import os
import pickle
import hashlib
import threading
import logging
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ─── Rutas ────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(__file__)
USERS_DIR  = os.path.join(BASE_DIR, "data", "users")
CACHE_PATH = os.path.join(BASE_DIR, "data", "encodings_cache.pkl")

# ─── Configuración ────────────────────────────────────────────────────────────
UMBRAL_SIMILITUD = 0.40   # Similitud coseno mínima para considerar coincidencia (0-1)

# ─── Registro global de cámaras en uso por esta app ──────────────────────────
# Permite que detectar_camaras_disponibles() incluya cámaras que estén abiertas
# por otra pestaña aunque no se puedan probar en este momento.
_camaras_en_uso: dict[int, str] = {}   # {indice: nombre_legible}
_lock_camaras_en_uso = threading.Lock()


@dataclass
class ResultadoFrame:
    """Resultado del procesamiento de un frame."""
    ubicaciones:      list = field(default_factory=list)  # (top, right, bottom, left)
    nombres:          list = field(default_factory=list)
    identificados:    int  = 0
    no_identificados: int  = 0


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Similitud coseno entre dos vectores de embedding."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ─── Detección de cámaras disponibles ────────────────────────────────────────

def detectar_camaras_disponibles() -> list:
    """
    Prueba índices de cámara del 0 al 4.
    Usa solo backend MSMF (estable en Windows 10/11) y default.
    DSHOW se omite — lanza excepciones C++ en algunos sistemas.

    Las cámaras actualmente abiertas por esta app se incluyen siempre,
    incluso si no se pueden abrir para la prueba (evita que desaparezcan
    del combo mientras están en uso por otra pestaña).
    """
    disponibles = []
    indices_encontrados: set[int] = set()

    # CAP_DSHOW omitido intencionalmente: causa heap corruption en Python 3.14/Win10
    backends = [
        (cv2.CAP_MSMF, "MSMF"),
        (None,         "default"),
    ]

    for indice in range(5):
        for backend, nombre_backend in backends:
            cap = None
            try:
                cap = cv2.VideoCapture(indice, backend) if backend is not None else cv2.VideoCapture(indice)
                if cap is not None and cap.isOpened():
                    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    alto  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    nombre = f"Cámara {indice} - {ancho}x{alto}" if ancho > 0 else f"Cámara {indice}"
                    disponibles.append((indice, nombre))
                    indices_encontrados.add(indice)
                    cap.release()
                    break  # Ya encontramos esta cámara, pasar al siguiente índice
            except Exception as e:
                logger.debug(f"Error al probar cámara {indice} backend {nombre_backend}: {e}")
            finally:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass

    # Incluir cámaras en uso por esta app que no se pudieron probar
    with _lock_camaras_en_uso:
        for indice, nombre in _camaras_en_uso.items():
            if indice not in indices_encontrados:
                disponibles.append((indice, nombre))

    disponibles.sort(key=lambda x: x[0])
    logger.info(f"Cámaras detectadas: {len(disponibles)} -> {[n for _, n in disponibles]}")
    return disponibles


class MotorReconocimiento:
    """
    Carga encodings de usuarios (insightface embeddings), los cachea,
    y compara contra cada frame de la cámara.
    """

    def __init__(self, umbral: float = UMBRAL_SIMILITUD):
        self.umbral = umbral
        self._encodings_conocidos: list = []
        self._nombres_conocidos:   list = []
        self._lock    = threading.Lock()
        self._cargado = False
        self._app     = None   # insightface.app.FaceAnalysis, inicializado lazy

    def _obtener_app(self):
        """Inicializa FaceAnalysis una sola vez (descarga modelos si hace falta)."""
        if self._app is None:
            try:
                from insightface.app import FaceAnalysis
                self._app = FaceAnalysis(
                    name="buffalo_sc",
                    providers=["CPUExecutionProvider"]
                )
                self._app.prepare(ctx_id=0, det_size=(640, 480))
                logger.info("InsightFace FaceAnalysis inicializado (buffalo_sc).")
            except Exception as e:
                logger.error(f"Error al inicializar InsightFace: {e}")
                raise
        return self._app

    # ── Carga y caché ─────────────────────────────────────────────────────────

    def cargar_encodings(self):
        with self._lock:
            if self._cache_es_valido():
                self._cargar_desde_cache()
            else:
                self._regenerar_y_guardar_cache()
            self._cargado = True

    def _hash_directorio_usuarios(self) -> str:
        rutas = []
        if not os.path.isdir(USERS_DIR):
            return ""
        for usuario in sorted(os.listdir(USERS_DIR)):
            carpeta = os.path.join(USERS_DIR, usuario)
            if not os.path.isdir(carpeta):
                continue
            for archivo in sorted(os.listdir(carpeta)):
                if archivo.lower().endswith((".jpg", ".jpeg", ".png")):
                    ruta = os.path.join(carpeta, archivo)
                    rutas.append(f"{ruta}:{os.path.getmtime(ruta)}")
        return hashlib.md5("|".join(rutas).encode()).hexdigest()

    def _cache_es_valido(self) -> bool:
        if not os.path.isfile(CACHE_PATH):
            return False
        try:
            with open(CACHE_PATH, "rb") as f:
                datos = pickle.load(f)
            return datos.get("hash") == self._hash_directorio_usuarios()
        except Exception:
            return False

    def _cargar_desde_cache(self):
        logger.info("Cargando encodings desde caché...")
        with open(CACHE_PATH, "rb") as f:
            datos = pickle.load(f)
        self._encodings_conocidos = datos["encodings"]
        self._nombres_conocidos   = datos["nombres"]
        logger.info(
            f"Caché cargado: {len(self._nombres_conocidos)} encodings, "
            f"{len(set(self._nombres_conocidos))} usuarios."
        )

    def _regenerar_y_guardar_cache(self):
        logger.info("Regenerando caché de encodings con InsightFace...")
        app = self._obtener_app()
        encodings = []
        nombres   = []

        os.makedirs(USERS_DIR, exist_ok=True)

        for nombre_usuario in sorted(os.listdir(USERS_DIR)):
            carpeta = os.path.join(USERS_DIR, nombre_usuario)
            if not os.path.isdir(carpeta):
                continue

            procesadas = 0
            for archivo in sorted(os.listdir(carpeta)):
                if not archivo.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue
                ruta = os.path.join(carpeta, archivo)
                try:
                    imagen = cv2.imread(ruta)
                    if imagen is None:
                        continue
                    caras = app.get(imagen)
                    if caras:
                        encodings.append(caras[0].embedding)
                        nombres.append(nombre_usuario.replace("_", " "))
                        procesadas += 1
                except Exception as e:
                    logger.warning(f"No se pudo procesar {ruta}: {e}")

            if procesadas == 0:
                logger.warning(f"Carpeta '{nombre_usuario}' sin rostros detectables.")

        hash_actual = self._hash_directorio_usuarios()
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "wb") as f:
            pickle.dump(
                {"hash": hash_actual, "encodings": encodings, "nombres": nombres},
                f,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

        self._encodings_conocidos = encodings
        self._nombres_conocidos   = nombres
        logger.info(f"Caché generado: {len(nombres)} encodings, {len(set(nombres))} usuarios.")

    def invalidar_cache(self):
        if os.path.isfile(CACHE_PATH):
            os.remove(CACHE_PATH)
        self._cargado = False

    def recargar(self):
        self.invalidar_cache()
        self.cargar_encodings()

    # ── Procesamiento de frame ─────────────────────────────────────────────────

    def procesar_frame(self, frame_bgr: np.ndarray) -> ResultadoFrame:
        if not self._cargado:
            return ResultadoFrame()

        app = self._obtener_app()
        resultado = ResultadoFrame()

        try:
            caras = app.get(frame_bgr)
        except Exception as e:
            logger.warning(f"Error en detección: {e}")
            return resultado

        with self._lock:
            enc_conocidos = list(self._encodings_conocidos)
            nom_conocidos = list(self._nombres_conocidos)

        for cara in caras:
            nombre = self._identificar(cara.embedding, enc_conocidos, nom_conocidos)
            resultado.nombres.append(nombre)

            # InsightFace bbox: [x1, y1, x2, y2] → convertir a (top, right, bottom, left)
            x1, y1, x2, y2 = [int(v) for v in cara.bbox]
            resultado.ubicaciones.append((y1, x2, y2, x1))

            if nombre != "No Identificado":
                resultado.identificados += 1
            else:
                resultado.no_identificados += 1

        return resultado

    def _identificar(self, emb: np.ndarray, enc_conocidos: list, nom_conocidos: list) -> str:
        if not enc_conocidos:
            return "No Identificado"
        similitudes = [_cosine_similarity(emb, e) for e in enc_conocidos]
        idx_max = int(np.argmax(similitudes))
        if similitudes[idx_max] >= self.umbral:
            return nom_conocidos[idx_max]
        return "No Identificado"

    # ── Propiedades ───────────────────────────────────────────────────────────

    @property
    def usuarios_cargados(self) -> list:
        return list(set(self._nombres_conocidos))

    @property
    def total_encodings(self) -> int:
        return len(self._encodings_conocidos)


# ─── Cámara ───────────────────────────────────────────────────────────────────

class GestorCamara:
    """
    Abstrae la apertura y lectura de frames desde una cámara.

    Intentará abrir la cámara en el siguiente orden de backends:
      1. cv2.CAP_DSHOW  (DirectShow – menor latencia en Windows)
      2. Sin backend    (OpenCV elige automáticamente)
      3. cv2.CAP_MSMF   (Media Foundation – fallback Windows)
    """

    def __init__(self, indice: int = 0):
        self._indice: int = indice
        self._cap: Optional[cv2.VideoCapture] = None
        self._activa = False
        self._backend_usado: Optional[str] = None

    # ── Propiedad indice con getter y setter ──────────────────────────────────

    @property
    def indice(self) -> int:
        return self._indice

    @indice.setter
    def indice(self, valor: int):
        if self._activa:
            logger.warning(
                "Se intentó cambiar el índice de cámara mientras estaba activa. "
                "Detenga la cámara primero."
            )
            return
        self._indice = valor

    # ── Apertura con fallback de backend ──────────────────────────────────────

    def iniciar(self) -> bool:
        """
        Abre la cámara. Intenta MSMF primero, luego default.
        CAP_DSHOW se omite — causa heap corruption en Python 3.14/Win10.
        """
        backends = [
            (cv2.CAP_MSMF, "CAP_MSMF"),
            (None,         "default"),
        ]

        for backend, nombre_backend in backends:
            try:
                cap = cv2.VideoCapture(self._indice, backend) if backend is not None else cv2.VideoCapture(self._indice)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    cap.set(cv2.CAP_PROP_FPS,          30)
                    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    alto  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    self._cap = cap
                    self._activa = True
                    self._backend_usado = nombre_backend
                    nombre_legible = f"Cámara {self._indice} - {ancho}x{alto}" if ancho > 0 else f"Cámara {self._indice}"
                    with _lock_camaras_en_uso:
                        _camaras_en_uso[self._indice] = nombre_legible
                    logger.info(f"Cámara {self._indice} abierta con backend {nombre_backend}.")
                    return True
                else:
                    cap.release()
            except Exception as e:
                logger.debug(f"Excepción al intentar cámara {self._indice} con {nombre_backend}: {e}")

        logger.error(
            f"No se pudo abrir la cámara {self._indice} con ningún backend "
            f"(MSMF, default). Verifique que esté conectada y no esté en uso por otra aplicación."
        )
        self._backend_usado = None
        return False

    def leer_frame(self) -> Optional[np.ndarray]:
        if not self._activa or self._cap is None:
            return None
        ok, frame = self._cap.read()
        return frame if ok else None

    def detener(self):
        self._activa = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        with _lock_camaras_en_uso:
            _camaras_en_uso.pop(self._indice, None)
        self._backend_usado = None

    @property
    def activa(self) -> bool:
        return self._activa

    @property
    def backend_usado(self) -> Optional[str]:
        return self._backend_usado


# ─── Utilidades para captura de nuevos usuarios ───────────────────────────────

def crear_carpeta_usuario(nombre: str, apellido: str) -> str:
    nombre_carpeta = f"{nombre.strip()}_{apellido.strip()}"
    ruta = os.path.join(USERS_DIR, nombre_carpeta)
    os.makedirs(ruta, exist_ok=True)
    return ruta
