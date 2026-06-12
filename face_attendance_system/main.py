"""
Punto de entrada del Sistema de Asistencia por Reconocimiento Facial.
Ejecutar: python main.py
"""

import sys
import os
import logging

# Agregar el directorio raíz al path para importaciones absolutas
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _suprimir_logs_opencv():
    """Silencia los warnings de OpenCV en la consola (DSHOW/MSMF/FFMPEG)."""
    import os
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    os.environ.setdefault("OPENCV_VIDEOIO_PRIORITY_DSHOW", "0")   # deshabilita DSHOW
    import cv2
    if hasattr(cv2, "setLogLevel"):
        cv2.setLogLevel(3)


def _configurar_logging():
    """Configura el sistema de logging con salida a consola y archivo."""
    log_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "app.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ]
    )


def _verificar_dependencias():
    """
    Verifica que las dependencias críticas estén instaladas
    antes de lanzar la interfaz gráfica.
    """
    faltantes = []
    dependencias = [
        ("cv2",          "opencv-python"),
        ("insightface",  "insightface"),
        ("onnxruntime",  "onnxruntime"),
        ("PIL",          "Pillow"),
        ("openpyxl",     "openpyxl"),
    ]
    for modulo, paquete in dependencias:
        try:
            __import__(modulo)
        except ImportError:
            faltantes.append(paquete)

    if faltantes:
        print("\n[ERROR] Faltan dependencias. Instale con:\n")
        print(f"    pip install {' '.join(faltantes)}\n")
        sys.exit(1)


def main():
    _suprimir_logs_opencv()
    _configurar_logging()
    logger = logging.getLogger(__name__)
    logger.info("Iniciando Sistema de Asistencia Facial...")

    _verificar_dependencias()

    # Inicializar base de datos (crea tablas si no existen)
    from database import inicializar_base_de_datos
    inicializar_base_de_datos()
    logger.info("Base de datos inicializada.")

    # Lanzar interfaz gráfica
    try:
        from ui.main_window import VentanaPrincipal
        app = VentanaPrincipal()
        logger.info("Ventana principal creada. Iniciando bucle de eventos.")
        app.mainloop()
        logger.info("Aplicación cerrada.")
    except Exception as e:
        import traceback
        logger.error(f"Error fatal al iniciar la interfaz: {e}")
        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
