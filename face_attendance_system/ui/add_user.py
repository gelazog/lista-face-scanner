"""
Formulario para registrar nuevos usuarios con captura MANUAL de fotos.
Pestaña C de la ventana principal.

Flujo:
  1. El usuario escribe nombre y apellido.
  2. Selecciona la cámara y presiona "Iniciar Preview".
  3. InsightFace detecta rostros en cada frame; cuando hay rostro en el frame
     actual el botón "Capturar Foto" se habilita.
  4. El usuario presiona "Capturar Foto" para guardar cada imagen manualmente.
  5. Al alcanzar ≥5 fotos aparece el botón "Registrar Usuario".
  6. Al registrar se recargan los encodings del motor y se refresca la tabla.
"""

import os
import time
import queue
import threading
import logging
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox

from database import usuario_existe, insertar_usuario, obtener_todos_los_usuarios
from face_engine import MotorReconocimiento, crear_carpeta_usuario, detectar_camaras_disponibles, GestorCamara

logger = logging.getLogger(__name__)

# ─── Paleta de colores ────────────────────────────────────────────────────────
FONDO_PANEL      = "#1E1E2E"
PANEL_SECUNDARIO = "#2A2A3E"
ACENTO           = "#00D4AA"
TEXTO_CLARO      = "#E0E0F0"
TEXTO_OPACO      = "#7878A0"
ROJO_ERROR       = "#FF4444"
VERDE_OK         = "#00FF88"

# Color del bounding box cuando hay rostro detectado (BGR para OpenCV)
COLOR_BBOX_DETECCION = (255, 136, 68)   # Azul #4488FF en BGR

# Parámetros de captura
FOTOS_DEFAULT    = 20
FOTOS_MIN        = 10
FOTOS_MAX        = 60
FOTOS_MINIMAS    = 5        # Mínimo para habilitar el registro
INTERVALO_FRAME  = 33       # ms entre actualizaciones del canvas (~30 fps)
PAUSA_HILO       = 0.04     # s que duerme el hilo entre frames
DURACION_FLASH   = 80       # ms del flash blanco al capturar
COOLDOWN_BOTON   = 500      # ms de espera entre capturas (anti-doble clic)

# Tamaño del canvas de preview
CANVAS_ANCHO = 480
CANVAS_ALTO  = 360

# Tamaño de las miniaturas
THUMB_ANCHO = 80
THUMB_ALTO  = 60


# ─────────────────────────────────────────────────────────────────────────────
class AgregarUsuario(ttk.Frame):
    """
    Frame de la pestaña 'Agregar Usuario'.

    Muestra un preview en vivo de la cámara, detecta rostros con InsightFace
    y permite capturar fotos manualmente para registrar un nuevo usuario.
    """

    def __init__(self, parent, motor: MotorReconocimiento, **kwargs):
        super().__init__(parent, **kwargs)
        self.motor = motor

        # ── Estado interno ────────────────────────────────────────────────────
        self._preview_activo  = False
        self._camara: Optional[GestorCamara] = None
        self._hilo:   Optional[threading.Thread] = None
        self._cola:   queue.Queue = queue.Queue(maxsize=2)

        # Resultado del último frame: (frame_bgr, hay_rostro)
        self._ultimo_frame:     Optional[np.ndarray] = None
        self._hay_rostro_frame: bool = False

        # Fotos capturadas en esta sesión
        self._fotos_capturadas: int = 0
        self._ruta_carpeta:     Optional[str] = None

        # Nombre/apellido al momento de crear la carpeta (para detectar cambios)
        self._nombre_carpeta:   str = ""
        self._apellido_carpeta: str = ""

        # Control del cooldown del botón capturar
        self._captura_habilitada: bool = True

        # Lista de (indice, nombre) de cámaras disponibles
        self._camaras_disponibles: list = []

        # Referencia a la imagen Tk actual (evita GC)
        self._imagen_tk: Optional[ImageTk.PhotoImage] = None

        # Lista de referencias a miniaturas (evita GC)
        self._thumbs_tk: list[ImageTk.PhotoImage] = []

        self.configure(style="Panel.TFrame")
        self._construir_ui()
        self._refrescar_tabla_usuarios()

    # ═════════════════════════════════════════════════════════════════════════
    # Construcción de la UI
    # ═════════════════════════════════════════════════════════════════════════

    def _construir_ui(self):
        self.columnconfigure(0, weight=1)
        # Filas con pesos: barra_titulo=0, fila_controles=0, canvas=1,
        #                  estado_rostro=0, btn_capturar=0, progreso=0,
        #                  btn_registrar=0, tabla=0
        self.rowconfigure(2, weight=1)

        self._construir_barra_titulo()
        self._construir_fila_controles()
        self._construir_area_preview()
        self._construir_barra_estado_rostro()
        self._construir_btn_capturar()
        self._construir_area_miniaturas()
        self._construir_barra_progreso()
        self._construir_btn_registrar()
        self._construir_tabla_usuarios()

    # ── Barra título ──────────────────────────────────────────────────────────

    def _construir_barra_titulo(self):
        barra = tk.Frame(self, bg=PANEL_SECUNDARIO, padx=12, pady=8)
        barra.grid(row=0, column=0, sticky="ew")
        tk.Label(
            barra,
            text="Registrar Nuevo Usuario",
            bg=PANEL_SECUNDARIO,
            fg=ACENTO,
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left")

    # ── Fila de controles (nombre, apellido, cámara, botón preview) ───────────

    def _construir_fila_controles(self):
        fila = tk.Frame(self, bg=FONDO_PANEL, padx=16, pady=10)
        fila.grid(row=1, column=0, sticky="ew")

        # Nombre
        tk.Label(
            fila, text="Nombre:", bg=FONDO_PANEL, fg=TEXTO_CLARO,
            font=("Segoe UI", 10)
        ).grid(row=0, column=0, sticky="e", padx=(0, 4))

        self._var_nombre = tk.StringVar()
        self._var_nombre.trace_add("write", self._on_nombre_cambiado)
        self._entry_nombre = _entrada_estilizada(fila, textvariable=self._var_nombre, width=16)
        self._entry_nombre.grid(row=0, column=1, padx=(0, 16))

        # Apellido
        tk.Label(
            fila, text="Apellido:", bg=FONDO_PANEL, fg=TEXTO_CLARO,
            font=("Segoe UI", 10)
        ).grid(row=0, column=2, sticky="e", padx=(0, 4))

        self._var_apellido = tk.StringVar()
        self._var_apellido.trace_add("write", self._on_nombre_cambiado)
        self._entry_apellido = _entrada_estilizada(fila, textvariable=self._var_apellido, width=16)
        self._entry_apellido.grid(row=0, column=3, padx=(0, 24))

        # Cámara disponible
        tk.Label(
            fila, text="Cámara:", bg=FONDO_PANEL, fg=TEXTO_CLARO,
            font=("Segoe UI", 10)
        ).grid(row=0, column=4, sticky="e", padx=(0, 4))

        self._var_camara = tk.StringVar()
        self._combo_camara = ttk.Combobox(
            fila, textvariable=self._var_camara,
            state="readonly", width=14, font=("Segoe UI", 10)
        )
        self._combo_camara.grid(row=0, column=5, padx=(0, 4))

        # Botón refrescar lista de cámaras
        self._btn_refrescar_cam = tk.Button(
            fila, text="🔄", bg=PANEL_SECUNDARIO, fg=TEXTO_CLARO,
            font=("Segoe UI", 10), relief="flat", padx=6, pady=4,
            cursor="hand2", command=self._refrescar_camaras
        )
        self._btn_refrescar_cam.grid(row=0, column=6, padx=(0, 16))

        # Botón iniciar / detener preview (deshabilitado hasta que haya cámaras disponibles)
        self._btn_preview = tk.Button(
            fila, text="▶  Iniciar Preview",
            bg=ACENTO, fg="#0A0A1A", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=14, pady=6, cursor="hand2",
            command=self._toggle_preview,
            state="disabled",
        )
        self._btn_preview.grid(row=0, column=7, padx=(0, 8))
        _hover(self._btn_preview, ACENTO, "#00B894")

        # Spinbox: límite de fotos
        tk.Label(
            fila, text="Límite fotos:", bg=FONDO_PANEL, fg=TEXTO_CLARO,
            font=("Segoe UI", 10)
        ).grid(row=0, column=8, sticky="e", padx=(8, 4))

        self._var_limite = tk.IntVar(value=FOTOS_DEFAULT)
        self._spin_limite = tk.Spinbox(
            fila, from_=FOTOS_MIN, to=FOTOS_MAX, increment=5,
            textvariable=self._var_limite,
            bg=PANEL_SECUNDARIO, fg=TEXTO_CLARO,
            insertbackground=ACENTO,
            buttonbackground=PANEL_SECUNDARIO,
            relief="flat", font=("Segoe UI", 10), width=5
        )
        self._spin_limite.grid(row=0, column=9)

        # Cargar cámaras al inicio
        self._refrescar_camaras()

    # ── Área de preview (canvas) ──────────────────────────────────────────────

    def _construir_area_preview(self):
        contenedor = tk.Frame(self, bg=FONDO_PANEL)
        contenedor.grid(row=2, column=0, sticky="nsew", padx=16, pady=(8, 0))
        contenedor.columnconfigure(0, weight=1)
        contenedor.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            contenedor,
            bg="#0A0A1A",
            bd=0,
            highlightthickness=2,
            highlightbackground=PANEL_SECUNDARIO,
            width=CANVAS_ANCHO,
            height=CANVAS_ALTO,
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._dibujar_placeholder()

    def _dibujar_placeholder(self):
        """Dibuja texto de espera cuando la cámara está apagada."""
        self._canvas.delete("all")
        self._canvas.create_text(
            CANVAS_ANCHO // 2,
            CANVAS_ALTO // 2,
            text="Vista previa apagada\nPresione '▶ Iniciar Preview'",
            fill=TEXTO_OPACO,
            font=("Segoe UI", 13),
            justify="center",
        )

    # ── Barra de estado del rostro ────────────────────────────────────────────

    def _construir_barra_estado_rostro(self):
        barra = tk.Frame(self, bg=PANEL_SECUNDARIO, padx=12, pady=5)
        barra.grid(row=3, column=0, sticky="ew", padx=16, pady=(2, 0))
        barra.columnconfigure(0, weight=1)

        self._lbl_estado_rostro = tk.Label(
            barra,
            text="✗  Sin rostro en frame",
            bg=PANEL_SECUNDARIO,
            fg=ROJO_ERROR,
            font=("Segoe UI", 10, "bold"),
        )
        self._lbl_estado_rostro.grid(row=0, column=0, sticky="w")

        self._lbl_contador_fotos = tk.Label(
            barra,
            text=f"0 / {FOTOS_DEFAULT} fotos capturadas",
            bg=PANEL_SECUNDARIO,
            fg=TEXTO_CLARO,
            font=("Segoe UI", 10),
        )
        self._lbl_contador_fotos.grid(row=0, column=1, sticky="e")

    # ── Botón capturar foto ───────────────────────────────────────────────────

    def _construir_btn_capturar(self):
        marco = tk.Frame(self, bg=FONDO_PANEL)
        marco.grid(row=4, column=0, pady=8)

        self._btn_capturar = tk.Button(
            marco,
            text="📸  Capturar Foto",
            bg=PANEL_SECUNDARIO,
            fg=TEXTO_OPACO,
            font=("Segoe UI", 12, "bold"),
            relief="flat",
            padx=24,
            pady=8,
            cursor="hand2",
            state="disabled",
            command=self._capturar_foto,
        )
        self._btn_capturar.pack()

    # ── Fila de miniaturas ────────────────────────────────────────────────────

    def _construir_area_miniaturas(self):
        contenedor = tk.Frame(self, bg=FONDO_PANEL)
        contenedor.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 4))

        self._frame_thumbs = tk.Frame(contenedor, bg=FONDO_PANEL)
        self._frame_thumbs.pack(side="left")

    # ── Barra de progreso ─────────────────────────────────────────────────────

    def _construir_barra_progreso(self):
        marco = tk.Frame(self, bg=FONDO_PANEL, padx=16)
        marco.grid(row=6, column=0, sticky="ew", pady=(0, 4))
        marco.columnconfigure(0, weight=1)

        self._barra_progreso = ttk.Progressbar(
            marco,
            orient="horizontal",
            mode="determinate",
            maximum=FOTOS_DEFAULT,
            value=0,
        )
        self._barra_progreso.grid(row=0, column=0, sticky="ew")

    # ── Botón registrar usuario ───────────────────────────────────────────────

    def _construir_btn_registrar(self):
        marco = tk.Frame(self, bg=FONDO_PANEL)
        marco.grid(row=7, column=0, pady=6)

        self._btn_registrar = tk.Button(
            marco,
            text="✅  Registrar Usuario",
            bg=VERDE_OK,
            fg="#0A0A1A",
            font=("Segoe UI", 12, "bold"),
            relief="flat",
            padx=24,
            pady=8,
            cursor="hand2",
            command=self._registrar_usuario,
        )
        self._btn_registrar.pack()
        # Oculto hasta tener ≥ FOTOS_MINIMAS fotos
        self._btn_registrar.pack_forget()

        # Etiqueta de estado del registro
        self._lbl_estado_registro = tk.Label(
            self,
            text="",
            bg=FONDO_PANEL,
            fg=TEXTO_CLARO,
            font=("Segoe UI", 10),
            wraplength=600,
        )
        self._lbl_estado_registro.grid(row=8, column=0, pady=(0, 4), padx=16, sticky="w")

    # ── Tabla de usuarios registrados ─────────────────────────────────────────

    def _construir_tabla_usuarios(self):
        marco = tk.Frame(self, bg=FONDO_PANEL, padx=16, pady=6)
        marco.grid(row=9, column=0, sticky="ew")
        marco.columnconfigure(0, weight=1)

        tk.Label(
            marco,
            text="Usuarios registrados:",
            bg=FONDO_PANEL,
            fg=ACENTO,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        columnas = ("nombre", "apellido", "fotos", "registrado_en")
        self._tree = ttk.Treeview(
            marco,
            columns=columnas,
            show="headings",
            height=6,
            selectmode="browse",
        )
        self._tree.heading("nombre",        text="Nombre",       anchor="center")
        self._tree.heading("apellido",       text="Apellido",     anchor="center")
        self._tree.heading("fotos",          text="Fotos",        anchor="center")
        self._tree.heading("registrado_en",  text="Registrado en", anchor="center")

        self._tree.column("nombre",       width=160, anchor="center")
        self._tree.column("apellido",     width=160, anchor="center")
        self._tree.column("fotos",        width=80,  anchor="center")
        self._tree.column("registrado_en", width=180, anchor="center")

        scroll = ttk.Scrollbar(marco, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.grid(row=1, column=0, sticky="ew")
        scroll.grid(row=1, column=1, sticky="ns")

    # ═════════════════════════════════════════════════════════════════════════
    # Detección y selección de cámaras
    # ═════════════════════════════════════════════════════════════════════════

    def _refrescar_camaras(self):
        """Detecta cámaras en hilo secundario para no bloquear la UI."""
        if self._preview_activo:
            return
        self._combo_camara.configure(state="disabled")
        self._btn_refrescar_cam.configure(state="disabled")
        self._btn_preview.configure(state="disabled")
        self._combo_camara.set("Detectando cámaras...")
        threading.Thread(target=self._detectar_camaras_bg, daemon=True).start()

    def _detectar_camaras_bg(self):
        """Hilo secundario: detecta cámaras y actualiza el combo en el hilo principal."""
        # Delay para no chocar con el escaneo simultáneo de camera_view.py al arrancar
        time.sleep(0.5)
        try:
            camaras = detectar_camaras_disponibles()
        except Exception as e:
            logger.warning(f"No se pudieron detectar cámaras: {e}")
            camaras = []
        if not camaras:
            camaras = [(0, "Cámara 0")]
        self.after(0, lambda: self._aplicar_lista_camaras(camaras))

    def _aplicar_lista_camaras(self, camaras: list):
        """Aplica la lista de cámaras al combo (hilo principal)."""
        self._camaras_disponibles = camaras
        nombres = [nombre for _, nombre in camaras]
        self._combo_camara["values"] = nombres
        self._combo_camara.configure(state="readonly")
        self._btn_refrescar_cam.configure(state="normal")
        self._btn_preview.configure(state="normal")
        if nombres:
            self._combo_camara.current(0)

    def _indice_camara_seleccionada(self) -> int:
        """Devuelve el índice entero de la cámara seleccionada en el combobox."""
        sel = self._combo_camara.current()
        if sel < 0 or sel >= len(self._camaras_disponibles):
            return 0
        return self._camaras_disponibles[sel][0]

    # ═════════════════════════════════════════════════════════════════════════
    # Control del preview
    # ═════════════════════════════════════════════════════════════════════════

    def _toggle_preview(self):
        if self._preview_activo:
            self._detener_preview()
        else:
            self._iniciar_preview()

    def _iniciar_preview(self):
        indice = self._indice_camara_seleccionada()
        self._camara = GestorCamara(indice)
        if not self._camara.iniciar():
            messagebox.showerror(
                "Error de cámara",
                "No se pudo acceder a la cámara seleccionada.\n"
                "Verifique que esté conectada y no esté en uso.",
            )
            self._camara = None
            return

        self._preview_activo = True

        # Deshabilitar controles de cámara mientras el preview está activo
        self._combo_camara.configure(state="disabled")
        self._btn_refrescar_cam.configure(state="disabled")
        self._btn_preview.configure(
            text="⏹  Detener Preview", bg=ROJO_ERROR, fg="white"
        )

        # Arrancar hilo de captura
        self._hilo = threading.Thread(target=self._bucle_captura, daemon=True)
        self._hilo.start()

        # Iniciar polling del canvas en el hilo principal
        self._actualizar_canvas()

    def _detener_preview(self, *, mantener_fotos: bool = True):
        self._preview_activo = False
        if self._camara is not None:
            self._camara.detener()
            self._camara = None

        self._hay_rostro_frame = False
        self._actualizar_estado_rostro()
        self._actualizar_btn_capturar()

        self._btn_preview.configure(
            text="▶  Iniciar Preview", bg=ACENTO, fg="#0A0A1A"
        )
        self._combo_camara.configure(state="readonly")
        self._btn_refrescar_cam.configure(state="normal")
        self._dibujar_placeholder()

    # ═════════════════════════════════════════════════════════════════════════
    # Hilo de captura y detección
    # ═════════════════════════════════════════════════════════════════════════

    def _bucle_captura(self):
        """
        Hilo secundario: lee frames, detecta rostros con InsightFace
        y encola (frame_dibujado, hay_rostro, frame_original).
        """
        app_deteccion = self._obtener_app_deteccion()

        while self._preview_activo:
            if self._camara is None:
                break

            frame = self._camara.leer_frame()
            if frame is None:
                time.sleep(0.05)
                continue

            hay_rostro = False
            frame_dibujado = frame.copy()

            try:
                if app_deteccion is not None:
                    caras = app_deteccion.get(frame)
                    if caras:
                        hay_rostro = True
                        for cara in caras:
                            x1, y1, x2, y2 = [int(v) for v in cara.bbox]
                            cv2.rectangle(
                                frame_dibujado,
                                (x1, y1), (x2, y2),
                                COLOR_BBOX_DETECCION,
                                2,
                            )
            except Exception as e:
                logger.debug(f"Error en detección de rostro: {e}")

            # Encolar resultado (descartar frame anterior si la cola está llena)
            payload = (frame_dibujado, hay_rostro, frame)
            try:
                self._cola.put_nowait(payload)
            except queue.Full:
                try:
                    self._cola.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._cola.put_nowait(payload)
                except queue.Full:
                    pass

            time.sleep(PAUSA_HILO)

    def _obtener_app_deteccion(self):
        """
        Intenta reusar el FaceAnalysis ya inicializado en el motor para
        no cargar el modelo dos veces. Si el motor no lo tiene listo todavía,
        inicializa uno propio (solo detección, no embeddings).
        """
        try:
            # El motor ya tiene _obtener_app() — lo reusamos
            return self.motor._obtener_app()
        except Exception as e:
            logger.warning(f"No se pudo obtener app del motor, inicializando propia: {e}")
            try:
                from insightface.app import FaceAnalysis
                app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
                app.prepare(ctx_id=0, det_size=(640, 480))
                return app
            except Exception as e2:
                logger.error(f"No se pudo inicializar FaceAnalysis: {e2}")
                return None

    # ═════════════════════════════════════════════════════════════════════════
    # Actualización del canvas (hilo principal Tkinter)
    # ═════════════════════════════════════════════════════════════════════════

    def _actualizar_canvas(self):
        """
        Polling de la cola de frames; se re-programa con after().
        Solo se ejecuta en el hilo principal de Tkinter.
        """
        if not self._preview_activo:
            return

        try:
            frame_dibujado, hay_rostro, frame_original = self._cola.get_nowait()
            self._ultimo_frame     = frame_original
            self._hay_rostro_frame = hay_rostro

            # Renderizar en el canvas
            self._renderizar_frame(frame_dibujado)

            # Actualizar indicadores
            self._actualizar_estado_rostro()
            self._actualizar_btn_capturar()

        except queue.Empty:
            pass

        self.after(INTERVALO_FRAME, self._actualizar_canvas)

    def _renderizar_frame(self, frame_bgr: np.ndarray):
        """Convierte el frame BGR a ImageTk y lo dibuja en el canvas."""
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        imagen_pil = Image.fromarray(frame_rgb)

        ancho_canvas = max(self._canvas.winfo_width(),  CANVAS_ANCHO)
        alto_canvas  = max(self._canvas.winfo_height(), CANVAS_ALTO)
        imagen_pil   = imagen_pil.resize((ancho_canvas, alto_canvas), Image.LANCZOS)

        self._imagen_tk = ImageTk.PhotoImage(imagen_pil)
        self._canvas.create_image(0, 0, anchor="nw", image=self._imagen_tk)

    # ═════════════════════════════════════════════════════════════════════════
    # Indicadores de estado
    # ═════════════════════════════════════════════════════════════════════════

    def _actualizar_estado_rostro(self):
        if self._hay_rostro_frame:
            self._lbl_estado_rostro.configure(
                text="✓  Rostro detectado — listo para capturar",
                fg=VERDE_OK,
            )
        else:
            self._lbl_estado_rostro.configure(
                text="✗  Sin rostro en frame",
                fg=ROJO_ERROR,
            )

    def _actualizar_btn_capturar(self):
        """Habilita el botón de captura solo si hay rostro Y el cooldown terminó."""
        limite = self._var_limite.get()
        limite_alcanzado = self._fotos_capturadas >= limite

        puede_capturar = (
            self._preview_activo
            and self._hay_rostro_frame
            and self._captura_habilitada
            and not limite_alcanzado
        )

        if puede_capturar:
            self._btn_capturar.configure(
                state="normal",
                bg=ACENTO,
                fg="#0A0A1A",
                cursor="hand2",
            )
        else:
            self._btn_capturar.configure(
                state="disabled",
                bg=PANEL_SECUNDARIO,
                fg=TEXTO_OPACO,
            )

    # ═════════════════════════════════════════════════════════════════════════
    # Detección de cambio en nombre/apellido
    # ═════════════════════════════════════════════════════════════════════════

    def _on_nombre_cambiado(self, *_args):
        """
        Si ya se capturaron fotos bajo un nombre/apellido y el usuario cambia
        alguno de los campos, se avisa y se limpian las fotos.
        """
        if self._fotos_capturadas == 0:
            return

        nombre_actual   = self._var_nombre.get().strip()
        apellido_actual = self._var_apellido.get().strip()

        if (nombre_actual != self._nombre_carpeta or
                apellido_actual != self._apellido_carpeta):
            respuesta = messagebox.askyesno(
                "Cambio de nombre detectado",
                "Se detectó un cambio en el nombre o apellido.\n"
                "Las fotos capturadas hasta ahora se perderán.\n\n"
                "¿Desea continuar?",
            )
            if respuesta:
                self._limpiar_sesion_fotos()
            else:
                # Revertir al nombre anterior
                self._var_nombre.set(self._nombre_carpeta)
                self._var_apellido.set(self._apellido_carpeta)

    # ═════════════════════════════════════════════════════════════════════════
    # Captura de foto
    # ═════════════════════════════════════════════════════════════════════════

    def _capturar_foto(self):
        """Guarda el frame actual y actualiza la UI."""
        if not self._hay_rostro_frame or self._ultimo_frame is None:
            return

        nombre   = self._var_nombre.get().strip()
        apellido = self._var_apellido.get().strip()

        # Validar nombre/apellido antes de la primera captura
        if not nombre or not apellido:
            messagebox.showwarning(
                "Campos incompletos",
                "Ingrese nombre y apellido antes de capturar fotos.",
            )
            return

        if not nombre.isalpha() or not apellido.isalpha():
            messagebox.showwarning(
                "Nombre inválido",
                "El nombre y apellido solo pueden contener letras (sin números ni símbolos).",
            )
            return

        # Si es la primera foto, verificar duplicados y crear carpeta
        if self._fotos_capturadas == 0:
            if usuario_existe(nombre, apellido):
                messagebox.showerror(
                    "Usuario duplicado",
                    f"Ya existe un usuario registrado como '{nombre} {apellido}'.",
                )
                return
            try:
                self._ruta_carpeta     = crear_carpeta_usuario(nombre, apellido)
                self._nombre_carpeta   = nombre
                self._apellido_carpeta = apellido
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo crear la carpeta del usuario:\n{e}")
                return

        # Guardar foto
        num = self._fotos_capturadas + 1
        nombre_archivo = f"foto_{num:03d}.jpg"
        ruta_foto = os.path.join(self._ruta_carpeta, nombre_archivo)

        try:
            cv2.imwrite(ruta_foto, self._ultimo_frame)
        except Exception as e:
            messagebox.showerror("Error al guardar", f"No se pudo guardar la foto:\n{e}")
            return

        self._fotos_capturadas += 1

        # Flash visual
        self._flash_canvas()

        # Añadir miniatura
        self._agregar_miniatura(ruta_foto)

        # Actualizar barra de progreso y contador
        limite = self._var_limite.get()
        self._barra_progreso.configure(maximum=limite, value=self._fotos_capturadas)
        self._lbl_contador_fotos.configure(
            text=f"{self._fotos_capturadas} / {limite} fotos capturadas"
        )

        # Mostrar/ocultar botón registrar
        if self._fotos_capturadas >= FOTOS_MINIMAS:
            self._btn_registrar.pack()
            _hover(self._btn_registrar, VERDE_OK, "#00CC66")
        else:
            self._btn_registrar.pack_forget()

        # Cooldown de 0.5 s
        self._captura_habilitada = False
        self._btn_capturar.configure(state="disabled", bg=PANEL_SECUNDARIO, fg=TEXTO_OPACO)
        self.after(COOLDOWN_BOTON, self._fin_cooldown)

    def _flash_canvas(self):
        """Muestra un destello blanco en el canvas por DURACION_FLASH ms."""
        ancho = max(self._canvas.winfo_width(), CANVAS_ANCHO)
        alto  = max(self._canvas.winfo_height(), CANVAS_ALTO)
        id_rect = self._canvas.create_rectangle(
            0, 0, ancho, alto, fill="white", outline=""
        )
        self.after(DURACION_FLASH, lambda: self._canvas.delete(id_rect))

    def _fin_cooldown(self):
        self._captura_habilitada = True
        self._actualizar_btn_capturar()

    def _agregar_miniatura(self, ruta_foto: str):
        """Añade una miniatura 80×60 del archivo guardado a la fila de miniaturas."""
        try:
            img = Image.open(ruta_foto).resize((THUMB_ANCHO, THUMB_ALTO), Image.LANCZOS)
            img_tk = ImageTk.PhotoImage(img)
            self._thumbs_tk.append(img_tk)   # evitar GC

            lbl = tk.Label(
                self._frame_thumbs,
                image=img_tk,
                bg=FONDO_PANEL,
                bd=1,
                relief="solid",
                highlightbackground=ACENTO,
            )
            lbl.pack(side="left", padx=2)
        except Exception as e:
            logger.warning(f"No se pudo crear miniatura de {ruta_foto}: {e}")

    # ═════════════════════════════════════════════════════════════════════════
    # Registro del usuario
    # ═════════════════════════════════════════════════════════════════════════

    def _registrar_usuario(self):
        if self._fotos_capturadas < FOTOS_MINIMAS:
            messagebox.showwarning(
                "Fotos insuficientes",
                f"Se necesitan al menos {FOTOS_MINIMAS} fotos para registrar un usuario.",
            )
            return

        nombre   = self._nombre_carpeta
        apellido = self._apellido_carpeta

        if not nombre or not apellido:
            messagebox.showwarning("Datos incompletos", "Nombre o apellido vacíos.")
            return

        # Detener el preview antes de registrar
        if self._preview_activo:
            self._detener_preview()

        self._btn_registrar.configure(state="disabled")
        self._btn_preview.configure(state="disabled")
        self._lbl_estado_registro.configure(
            text="Registrando usuario...", fg=TEXTO_OPACO
        )

        hilo = threading.Thread(
            target=self._ejecutar_registro,
            args=(nombre, apellido, self._ruta_carpeta, self._fotos_capturadas),
            daemon=True,
        )
        hilo.start()

    def _ejecutar_registro(
        self,
        nombre: str,
        apellido: str,
        ruta_carpeta: str,
        fotos: int,
    ):
        """Hilo secundario: inserta en DB y recarga encodings."""
        try:
            insertar_usuario(nombre, apellido, ruta_carpeta)

            self.after(
                0,
                lambda: self._lbl_estado_registro.configure(
                    text="Procesando encodings faciales…", fg=TEXTO_OPACO
                ),
            )
            self.motor.recargar()

            self.after(0, lambda: self._on_registro_exitoso(nombre, apellido, fotos))

        except Exception as e:
            logger.exception("Error al registrar usuario")
            self.after(0, lambda: self._on_registro_error(str(e)))

    def _on_registro_exitoso(self, nombre: str, apellido: str, fotos: int):
        self._lbl_estado_registro.configure(
            text=(
                f"✓  Usuario '{nombre} {apellido}' registrado correctamente "
                f"con {fotos} fotos.\n"
                "El sistema ya puede reconocerle sin necesidad de reiniciar."
            ),
            fg=VERDE_OK,
        )
        self._btn_preview.configure(state="normal")
        self._limpiar_sesion_fotos()
        self._refrescar_tabla_usuarios()

    def _on_registro_error(self, mensaje: str):
        self._lbl_estado_registro.configure(
            text=f"✗  Error: {mensaje}", fg=ROJO_ERROR
        )
        self._btn_registrar.configure(state="normal")
        self._btn_preview.configure(state="normal")
        messagebox.showerror("Error al registrar", mensaje)

    # ═════════════════════════════════════════════════════════════════════════
    # Limpieza de la sesión de fotos
    # ═════════════════════════════════════════════════════════════════════════

    def _limpiar_sesion_fotos(self):
        """Restablece el formulario y los contadores de fotos."""
        self._fotos_capturadas  = 0
        self._ruta_carpeta      = None
        self._nombre_carpeta    = ""
        self._apellido_carpeta  = ""
        self._captura_habilitada = True

        # Limpiar campos de texto
        self._var_nombre.set("")
        self._var_apellido.set("")

        # Limpiar miniaturas
        for widget in self._frame_thumbs.winfo_children():
            widget.destroy()
        self._thumbs_tk.clear()

        # Reiniciar progreso
        self._barra_progreso.configure(value=0)
        limite = self._var_limite.get()
        self._lbl_contador_fotos.configure(
            text=f"0 / {limite} fotos capturadas"
        )

        # Ocultar botón registrar
        self._btn_registrar.pack_forget()

        # Actualizar estado del botón capturar
        self._actualizar_btn_capturar()

    # ═════════════════════════════════════════════════════════════════════════
    # Tabla de usuarios registrados
    # ═════════════════════════════════════════════════════════════════════════

    def _refrescar_tabla_usuarios(self):
        """Consulta la DB y rellena la tabla con todos los usuarios."""
        try:
            usuarios = obtener_todos_los_usuarios()
        except Exception as e:
            logger.warning(f"No se pudo cargar la lista de usuarios: {e}")
            return

        self._tree.delete(*self._tree.get_children())

        for u in usuarios:
            # Contar fotos en la carpeta del usuario
            ruta = u.get("ruta_carpeta", "")
            try:
                fotos = len([
                    f for f in os.listdir(ruta)
                    if f.lower().endswith((".jpg", ".jpeg", ".png"))
                ]) if os.path.isdir(ruta) else 0
            except Exception:
                fotos = "?"

            registrado = u.get("creado_en", "")
            self._tree.insert(
                "", "end",
                values=(u["nombre"], u["apellido"], fotos, registrado),
            )

    # ═════════════════════════════════════════════════════════════════════════
    # Limpieza al destruir el widget
    # ═════════════════════════════════════════════════════════════════════════

    def destruir(self):
        """Detener la cámara y limpiar recursos antes de destruir el widget."""
        self._preview_activo = False
        if self._camara is not None:
            self._camara.detener()
            self._camara = None


# ─── Utilidades ───────────────────────────────────────────────────────────────

def _entrada_estilizada(padre, **kwargs) -> tk.Entry:
    """Crea un Entry con el estilo oscuro del sistema."""
    params = dict(
        bg=PANEL_SECUNDARIO,
        fg=TEXTO_CLARO,
        insertbackground=ACENTO,
        relief="flat",
        font=("Segoe UI", 11),
        width=20,
    )
    params.update(kwargs)
    return tk.Entry(padre, **params)


def _hover(boton: tk.Button, color_normal: str, color_hover: str):
    """Aplica efecto hover a un botón tk."""
    boton.bind("<Enter>", lambda _: boton.configure(bg=color_hover))
    boton.bind("<Leave>", lambda _: boton.configure(bg=color_normal))
