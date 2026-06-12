"""
Panel de vista en vivo de la cámara con bounding boxes dibujados en tiempo real.
Pestaña A de la ventana principal.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import time
import logging

import cv2
import numpy as np
from PIL import Image, ImageTk

from face_engine import MotorReconocimiento, GestorCamara, detectar_camaras_disponibles
from database import obtener_id_usuario_por_nombre, insertar_asistencia

logger = logging.getLogger(__name__)

# ─── Colores ──────────────────────────────────────────────────────────────────
FONDO_PANEL      = "#1E1E2E"
PANEL_SECUNDARIO = "#2A2A3E"
ACENTO           = "#00D4AA"
TEXTO_CLARO      = "#E0E0F0"
TEXTO_OPACO      = "#7878A0"
ROJO_ERROR       = "#FF4444"
VERDE_OK         = "#00FF88"

COLOR_IDENTIFICADO    = (0, 255, 136)    # BGR: verde brillante
COLOR_NO_IDENTIFICADO = (68, 68, 255)    # BGR: rojo-azul

INTERVALO_FRAME_MS  = 30    # ~33 fps
INTERVALO_RECARGA_S = 0.05  # Pausa entre frames en el hilo


class VistaEnVivo(ttk.Frame):
    """
    Frame principal de la pestaña de vista en vivo.
    Gestiona el hilo de captura/reconocimiento y dibuja sobre el canvas de Tkinter.
    Incluye selector de cámara con detección automática y botón de refresco.
    """

    def __init__(self, parent, motor: MotorReconocimiento, **kwargs):
        super().__init__(parent, **kwargs)
        self.motor    = motor
        self._camara  = GestorCamara()
        self._activa  = False
        self._hilo: threading.Thread | None = None
        self._cola:  queue.Queue = queue.Queue(maxsize=2)

        # Lista de (indice, nombre) de cámaras disponibles
        self._camaras_disponibles: list = []

        self.configure(style="Panel.TFrame")
        self._construir_ui()

        # Detectar cámaras en segundo plano para no bloquear el arranque
        threading.Thread(target=self._detectar_y_llenar_combo, daemon=True).start()

    # ── Construcción UI ───────────────────────────────────────────────────────

    def _construir_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Barra superior ────────────────────────────────────────────────────
        barra = tk.Frame(self, bg=PANEL_SECUNDARIO, padx=12, pady=8)
        barra.grid(row=0, column=0, sticky="ew")

        tk.Label(
            barra, text="Vista en Vivo", bg=PANEL_SECUNDARIO,
            fg=ACENTO, font=("Segoe UI", 13, "bold")
        ).pack(side="left", padx=(0, 16))

        # ── Selector de cámara ────────────────────────────────────────────────
        tk.Label(
            barra, text="Cámara:", bg=PANEL_SECUNDARIO,
            fg=TEXTO_CLARO, font=("Segoe UI", 10)
        ).pack(side="left")

        self._combo_camara = ttk.Combobox(
            barra,
            state="readonly",
            width=26,
            font=("Segoe UI", 10),
        )
        self._combo_camara.pack(side="left", padx=(4, 4))
        self._combo_camara.set("Detectando cámaras...")

        # Botón de actualizar lista de cámaras
        self._btn_refresh = tk.Button(
            barra, text="Actualizar camaras",
            bg=PANEL_SECUNDARIO, fg=ACENTO,
            font=("Segoe UI", 9), relief="flat",
            padx=8, pady=4, cursor="hand2",
            command=self._refrescar_camaras,
            activebackground="#3A3A5E", activeforeground=ACENTO,
            bd=1, highlightbackground=ACENTO,
        )
        self._btn_refresh.pack(side="left", padx=(0, 12))

        # ── Botón iniciar/detener ─────────────────────────────────────────────
        self._btn_toggle = tk.Button(
            barra, text="Iniciar Camara",
            bg=ACENTO, fg="#0A0A1A", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=14, pady=6, cursor="hand2",
            command=self._toggle_camara
        )
        self._btn_toggle.pack(side="right", padx=4)

        # ── Contador ──────────────────────────────────────────────────────────
        self._lbl_contador = tk.Label(
            barra, text="Personas detectadas: 0",
            bg=PANEL_SECUNDARIO, fg=TEXTO_CLARO, font=("Segoe UI", 10)
        )
        self._lbl_contador.pack(side="right", padx=16)

        # ── Canvas de video ───────────────────────────────────────────────────
        contenedor = tk.Frame(self, bg=FONDO_PANEL)
        contenedor.grid(row=1, column=0, sticky="nsew", padx=12, pady=12)
        contenedor.columnconfigure(0, weight=1)
        contenedor.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            contenedor, bg="#0A0A1A", bd=0, highlightthickness=0,
            width=640, height=480
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")

        self._mostrar_placeholder()

        # ── Panel lateral de detectados ───────────────────────────────────────
        lateral = tk.Frame(contenedor, bg=PANEL_SECUNDARIO, padx=8, pady=8)
        lateral.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        tk.Label(
            lateral, text="Detectados ahora",
            bg=PANEL_SECUNDARIO, fg=ACENTO, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(0, 6))

        self._lista_detectados = tk.Listbox(
            lateral, bg=FONDO_PANEL, fg=TEXTO_CLARO,
            font=("Segoe UI", 10), selectbackground=ACENTO,
            relief="flat", highlightthickness=0, width=20, bd=0
        )
        self._lista_detectados.pack(fill="both", expand=True)

    def _mostrar_placeholder(self):
        """Dibuja texto de espera en el canvas."""
        self._canvas.delete("all")
        self._canvas.create_text(
            320, 240,
            text="Camara apagada\nPresione 'Iniciar Camara'",
            fill=TEXTO_OPACO, font=("Segoe UI", 14), justify="center"
        )

    # ── Gestión del combo de cámaras ──────────────────────────────────────────

    def _detectar_y_llenar_combo(self):
        """
        Corre en hilo secundario para no bloquear la UI.
        Detecta cámaras disponibles y actualiza el combo en el hilo principal.
        """
        try:
            camaras = detectar_camaras_disponibles()
        except Exception as e:
            logger.error(f"Error al detectar cámaras: {e}")
            camaras = []
        # Programar actualización en el hilo principal de Tkinter
        self.after(0, lambda: self._aplicar_lista_camaras(camaras))

    def _aplicar_lista_camaras(self, camaras: list):
        """Actualiza el combo con la lista de cámaras. Debe llamarse desde el hilo principal."""
        self._camaras_disponibles = camaras

        if not camaras:
            self._combo_camara["values"] = ["No se detectaron camaras"]
            self._combo_camara.set("No se detectaron camaras")
            self._combo_camara.configure(state="disabled")
            self._btn_toggle.configure(state="disabled")
            logger.warning("No se encontraron cámaras disponibles.")
            return

        nombres = [nombre for _, nombre in camaras]
        self._combo_camara["values"] = nombres
        self._combo_camara.set(nombres[0])
        self._combo_camara.configure(state="readonly")
        self._btn_toggle.configure(state="normal")

    def _refrescar_camaras(self):
        """Re-escanea las cámaras disponibles cuando la cámara no está activa."""
        if self._activa:
            return
        self._combo_camara.configure(state="disabled")
        self._btn_toggle.configure(state="disabled")
        self._combo_camara.set("Detectando camaras...")
        threading.Thread(target=self._detectar_y_llenar_combo, daemon=True).start()

    def _indice_camara_seleccionado(self) -> int:
        """Devuelve el índice numérico de la cámara actualmente seleccionada en el combo."""
        sel = self._combo_camara.current()
        if sel < 0 or sel >= len(self._camaras_disponibles):
            return 0
        return self._camaras_disponibles[sel][0]

    # ── Control de cámara ─────────────────────────────────────────────────────

    def _toggle_camara(self):
        if self._activa:
            self._detener_camara()
        else:
            self._iniciar_camara()

    def _iniciar_camara(self):
        if not self._camaras_disponibles:
            messagebox.showwarning(
                "Sin cámaras",
                "No se detectaron cámaras disponibles.\n"
                "Conecte una cámara y presione 'Actualizar cámaras'."
            )
            return

        indice = self._indice_camara_seleccionado()
        self._camara.indice = indice

        if not self._camara.iniciar():
            messagebox.showerror(
                "Error de cámara",
                f"No se pudo acceder a la cámara {indice}.\n"
                "Verifique que esté conectada y no esté en uso por otra aplicación.\n\n"
                "Intente con 'Actualizar cámaras' para re-detectar dispositivos."
            )
            return

        self._activa = True
        # Deshabilitar controles de selección mientras la cámara está activa
        self._combo_camara.configure(state="disabled")
        self._btn_refresh.configure(state="disabled")
        self._btn_toggle.configure(text="Detener Camara", bg=ROJO_ERROR, fg="white")

        self._hilo = threading.Thread(target=self._bucle_captura, daemon=True)
        self._hilo.start()
        self._actualizar_canvas()

    def _detener_camara(self):
        self._activa = False
        self._camara.detener()

        # Re-habilitar controles de selección
        if self._camaras_disponibles:
            self._combo_camara.configure(state="readonly")
        self._btn_refresh.configure(state="normal")
        self._btn_toggle.configure(text="Iniciar Camara", bg=ACENTO, fg="#0A0A1A")
        self._lbl_contador.configure(text="Personas detectadas: 0")
        self._lista_detectados.delete(0, "end")
        self._mostrar_placeholder()

    # ── Hilo de captura ───────────────────────────────────────────────────────

    def _bucle_captura(self):
        """
        Hilo secundario: lee frames, procesa reconocimiento facial,
        y pone el resultado en la cola para que Tkinter lo dibuje.
        """
        while self._activa:
            frame = self._camara.leer_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            resultado = self.motor.procesar_frame(frame)
            frame_dibujado = self._dibujar_bboxes(frame, resultado)

            # Registrar detecciones en DB (SQLite soporta acceso desde hilos secundarios)
            for nombre in resultado.nombres:
                if nombre != "No Identificado":
                    usuario_id = obtener_id_usuario_por_nombre(nombre)
                    if usuario_id is not None:
                        insertar_asistencia(usuario_id)

            # Poner en cola descartando el frame anterior si la cola está llena
            try:
                self._cola.put_nowait((frame_dibujado, resultado))
            except queue.Full:
                try:
                    self._cola.get_nowait()
                except queue.Empty:
                    pass
                self._cola.put_nowait((frame_dibujado, resultado))

            time.sleep(INTERVALO_RECARGA_S)

    def _dibujar_bboxes(self, frame: np.ndarray, resultado) -> np.ndarray:
        """Dibuja bounding boxes y etiquetas sobre el frame."""
        copia = frame.copy()
        for (top, right, bottom, left), nombre in zip(resultado.ubicaciones, resultado.nombres):
            identificado = nombre != "No Identificado"
            color = COLOR_IDENTIFICADO if identificado else COLOR_NO_IDENTIFICADO
            texto = nombre if identificado else "No Identificado"

            # Recuadro principal
            cv2.rectangle(copia, (left, top), (right, bottom), color, 2)

            # Fondo de la etiqueta
            (ancho_texto, alto_texto), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
            cv2.rectangle(copia, (left, top - alto_texto - 12), (left + ancho_texto + 8, top), color, -1)

            # Texto de la etiqueta
            cv2.putText(
                copia, texto, (left + 4, top - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (10, 10, 10), 1, cv2.LINE_AA
            )
        return copia

    # ── Actualización del canvas (hilo principal Tkinter) ─────────────────────

    def _actualizar_canvas(self):
        """
        Polling de la cola de frames. Llamado solo desde el hilo principal.
        Se re-programa a sí mismo con after().
        """
        if not self._activa:
            return

        try:
            frame_dibujado, resultado = self._cola.get_nowait()
            self._renderizar_frame(frame_dibujado, resultado)
        except queue.Empty:
            pass

        self.after(INTERVALO_FRAME_MS, self._actualizar_canvas)

    def _renderizar_frame(self, frame: np.ndarray, resultado):
        """Convierte el frame a ImageTk y lo dibuja en el canvas."""
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        imagen_pil = Image.fromarray(frame_rgb)

        # Escalar al tamaño actual del canvas
        canvas_w = max(self._canvas.winfo_width(), 640)
        canvas_h = max(self._canvas.winfo_height(), 480)
        imagen_pil = imagen_pil.resize((canvas_w, canvas_h), Image.LANCZOS)

        self._imagen_tk = ImageTk.PhotoImage(imagen_pil)
        self._canvas.create_image(0, 0, anchor="nw", image=self._imagen_tk)

        # Actualizar contador
        total = len(resultado.nombres)
        self._lbl_contador.configure(
            text=(
                f"Personas detectadas: {total}  "
                f"({resultado.identificados} OK  "
                f"{resultado.no_identificados} desconocidos)"
            )
        )

        # Actualizar lista lateral
        self._lista_detectados.delete(0, "end")
        for nombre in resultado.nombres:
            color = VERDE_OK if nombre != "No Identificado" else ROJO_ERROR
            self._lista_detectados.insert("end", f"  {nombre}")
            self._lista_detectados.itemconfig("end", fg=color)

    # ── Limpieza al cerrar ────────────────────────────────────────────────────

    def destruir(self):
        """Detener cámara y limpiar recursos antes de destruir el widget."""
        self._activa = False
        self._camara.detener()
