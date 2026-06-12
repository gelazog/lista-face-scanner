"""
Ventana principal de la aplicación.
Configura estilos globales de Tkinter y organiza las 3 pestañas.
"""

import tkinter as tk
from tkinter import ttk
import threading
import logging

from face_engine import MotorReconocimiento
from ui.camera_view import VistaEnVivo
from ui.recent_detections import UltimasDetecciones
from ui.add_user import AgregarUsuario
from ui.manage_photos import GestionarFotos

logger = logging.getLogger(__name__)

# ─── Paleta ───────────────────────────────────────────────────────────────────
FONDO           = "#1E1E2E"
PANEL_SEC       = "#2A2A3E"
ACENTO          = "#00D4AA"
TEXTO_CLARO     = "#E0E0F0"
TEXTO_OPACO     = "#7878A0"
PESTAÑA_ACTIVA  = "#2A2A3E"
PESTAÑA_INACTIVA= "#161626"


class VentanaPrincipal(tk.Tk):
    """
    Ventana principal de la aplicación de asistencia facial.
    Hereda de tk.Tk para ser el root de la aplicación.
    """

    def __init__(self):
        super().__init__()
        self.title("Sistema de Asistencia por Reconocimiento Facial")
        self.geometry("1100x700")
        self.minsize(900, 600)
        self.configure(bg=FONDO)

        # Icono de la aplicación (si existe)
        try:
            self.iconbitmap(default="")
        except Exception:
            pass

        self._motor = MotorReconocimiento()
        self._configurar_estilos()
        self._construir_ui()
        self._iniciar_carga_encodings()

        # Manejo del cierre
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

    # ── Estilos globales TTK ──────────────────────────────────────────────────

    def _configurar_estilos(self):
        estilo = ttk.Style(self)
        estilo.theme_use("clam")

        # Frame base
        estilo.configure("Panel.TFrame",     background=FONDO)
        estilo.configure("PanelSec.TFrame",  background=PANEL_SEC)
        estilo.configure("TFrame",           background=FONDO)

        # Notebook (pestañas)
        estilo.configure(
            "TNotebook",
            background=FONDO, borderwidth=0,
            tabmargins=[0, 0, 0, 0]
        )
        estilo.configure(
            "TNotebook.Tab",
            background=PESTAÑA_INACTIVA,
            foreground=TEXTO_OPACO,
            padding=[20, 8],
            font=("Segoe UI", 10),
            borderwidth=0
        )
        estilo.map(
            "TNotebook.Tab",
            background=[("selected", PESTAÑA_ACTIVA), ("active", "#1A1A2E")],
            foreground=[("selected", ACENTO),         ("active", TEXTO_CLARO)],
            font=[("selected", ("Segoe UI", 10, "bold"))]
        )

        # Treeview
        estilo.configure(
            "Treeview",
            background=FONDO, foreground=TEXTO_CLARO,
            fieldbackground=FONDO, rowheight=26,
            font=("Segoe UI", 10), borderwidth=0
        )
        estilo.configure(
            "Treeview.Heading",
            background=PANEL_SEC, foreground=ACENTO,
            font=("Segoe UI", 10, "bold"), relief="flat"
        )
        estilo.map(
            "Treeview",
            background=[("selected", ACENTO)],
            foreground=[("selected", "#0A0A1A")]
        )

        # Progressbar
        estilo.configure(
            "TProgressbar",
            troughcolor=PANEL_SEC, background=ACENTO,
            thickness=12, borderwidth=0
        )

        # Scrollbar
        estilo.configure(
            "Vertical.TScrollbar",
            background=PANEL_SEC, troughcolor=FONDO,
            borderwidth=0, arrowcolor=ACENTO
        )

    # ── Construcción UI ───────────────────────────────────────────────────────

    def _construir_ui(self):
        # ── Cabecera superior ─────────────────────────────────────────────────
        cabecera = tk.Frame(self, bg=PANEL_SEC, height=54)
        cabecera.pack(fill="x", side="top")
        cabecera.pack_propagate(False)

        tk.Label(
            cabecera,
            text="  Sistema de Asistencia Facial",
            bg=PANEL_SEC, fg=ACENTO,
            font=("Segoe UI", 15, "bold")
        ).pack(side="left", padx=16, pady=10)

        self._lbl_estado_motor = tk.Label(
            cabecera,
            text="⏳ Cargando reconocimiento facial...",
            bg=PANEL_SEC, fg=TEXTO_OPACO,
            font=("Segoe UI", 9)
        )
        self._lbl_estado_motor.pack(side="right", padx=16)

        # ── Notebook (pestañas) ───────────────────────────────────────────────
        self._notebook = ttk.Notebook(self, style="TNotebook")
        self._notebook.pack(fill="both", expand=True, padx=0, pady=0)

        # Pestaña A: Vista en vivo
        self._vista_vivo = VistaEnVivo(self._notebook, self._motor)
        self._notebook.add(self._vista_vivo, text="  📷  Vista en Vivo  ")

        # Pestaña B: Últimas detecciones
        self._vista_detecciones = UltimasDetecciones(self._notebook)
        self._notebook.add(self._vista_detecciones, text="  📋  Últimas Detecciones  ")

        # Pestaña C: Agregar usuario
        self._vista_agregar = AgregarUsuario(self._notebook, self._motor)
        self._notebook.add(self._vista_agregar, text="  👤  Agregar Usuario  ")

        # Pestaña D: Gestionar fotos de usuarios existentes
        self._vista_fotos = GestionarFotos(self._notebook, self._motor)
        self._notebook.add(self._vista_fotos, text="  🖼  Gestionar Fotos  ")

        # ── Barra de estado inferior ──────────────────────────────────────────
        barra_inf = tk.Frame(self, bg="#0D0D1A", height=24)
        barra_inf.pack(fill="x", side="bottom")
        barra_inf.pack_propagate(False)

        self._lbl_barra_inf = tk.Label(
            barra_inf,
            text="Listo",
            bg="#0D0D1A", fg=TEXTO_OPACO,
            font=("Segoe UI", 8)
        )
        self._lbl_barra_inf.pack(side="left", padx=10, pady=4)

    # ── Carga de encodings en segundo plano ───────────────────────────────────

    def _iniciar_carga_encodings(self):
        """Carga los encodings sin bloquear la UI."""
        hilo = threading.Thread(target=self._cargar_encodings_bg, daemon=True)
        hilo.start()

    def _cargar_encodings_bg(self):
        """Hilo de carga de encodings."""
        try:
            self._motor.cargar_encodings()
            total = self._motor.total_encodings
            usuarios = len(self._motor.usuarios_cargados)
            self.after(0, lambda: self._on_encodings_cargados(usuarios, total))
        except Exception as e:
            logger.exception("Error al cargar encodings")
            self.after(0, lambda: self._on_error_encodings(str(e)))

    def _on_encodings_cargados(self, usuarios: int, total_enc: int):
        texto = f"✓ {usuarios} usuario(s) reconocibles  |  {total_enc} encodings cargados"
        self._lbl_estado_motor.configure(text=texto, fg=ACENTO)
        self._lbl_barra_inf.configure(text="Motor de reconocimiento listo")

    def _on_error_encodings(self, mensaje: str):
        self._lbl_estado_motor.configure(
            text="⚠ Error al cargar encodings — vea el log para detalles",
            fg="#FF4444"
        )
        logger.error(f"Fallo carga encodings: {mensaje}")

    # ── Cierre ────────────────────────────────────────────────────────────────

    def _al_cerrar(self):
        """Detiene la cámara y limpia recursos antes de cerrar."""
        try:
            self._vista_vivo.destruir()
            self._vista_detecciones.destruir()
            self._vista_agregar.destruir()
            self._vista_fotos.destruir()
        except Exception:
            pass
        self.destroy()
