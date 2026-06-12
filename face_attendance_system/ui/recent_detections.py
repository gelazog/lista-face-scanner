"""
Panel de últimas detecciones con tabla scrollable y exportación a Excel.
Pestaña B de la ventana principal.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import logging
from datetime import datetime, timedelta

from database import obtener_detecciones_recientes
from export import exportar_asistencia, abrir_carpeta_exports

logger = logging.getLogger(__name__)

# ─── Colores ──────────────────────────────────────────────────────────────────
FONDO_PANEL      = "#1E1E2E"
PANEL_SECUNDARIO = "#2A2A3E"
ACENTO           = "#00D4AA"
TEXTO_CLARO      = "#E0E0F0"
TEXTO_OPACO      = "#7878A0"
ROJO_ERROR       = "#FF4444"
VERDE_OK         = "#00FF88"
FILA_PAR         = "#2A2A3E"
FILA_IMPAR       = "#252535"

INTERVALO_REFRESCO_MS = 3000   # 3 segundos


class UltimasDetecciones(ttk.Frame):
    """
    Frame de la pestaña 'Últimas Detecciones'.
    Muestra los últimos 50 registros en una tabla con auto-refresco.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._refresco_activo = True
        self.configure(style="Panel.TFrame")
        self._construir_ui()
        self._programar_refresco()

    # ── Construcción UI ───────────────────────────────────────────────────────

    def _construir_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Barra superior ────────────────────────────────────────────────────
        barra = tk.Frame(self, bg=PANEL_SECUNDARIO, padx=12, pady=8)
        barra.grid(row=0, column=0, sticky="ew")

        tk.Label(
            barra, text="Últimas Detecciones",
            bg=PANEL_SECUNDARIO, fg=ACENTO, font=("Segoe UI", 13, "bold")
        ).pack(side="left")

        # Botón exportar
        btn_exportar = tk.Button(
            barra, text="📊  Exportar a Excel",
            bg=ACENTO, fg="#0A0A1A", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=14, pady=6, cursor="hand2",
            command=self._exportar_excel
        )
        btn_exportar.pack(side="right", padx=4)
        _hover(btn_exportar, ACENTO, "#00B894")

        # Indicador de última actualización
        self._lbl_actualizacion = tk.Label(
            barra, text="",
            bg=PANEL_SECUNDARIO, fg=TEXTO_OPACO, font=("Segoe UI", 9)
        )
        self._lbl_actualizacion.pack(side="right", padx=12)

        # ── Filtros de fecha ──────────────────────────────────────────────────
        filtros = tk.Frame(self, bg=FONDO_PANEL, padx=12, pady=6)
        filtros.grid(row=1, column=0, sticky="ew")

        tk.Label(filtros, text="Desde:", bg=FONDO_PANEL, fg=TEXTO_CLARO,
                 font=("Segoe UI", 10)).pack(side="left")

        self._entrada_desde = tk.Entry(
            filtros, width=12, bg=PANEL_SECUNDARIO, fg=TEXTO_CLARO,
            insertbackground=ACENTO, relief="flat", font=("Segoe UI", 10)
        )
        self._entrada_desde.insert(0, (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"))
        self._entrada_desde.pack(side="left", padx=(4, 12))

        tk.Label(filtros, text="Hasta:", bg=FONDO_PANEL, fg=TEXTO_CLARO,
                 font=("Segoe UI", 10)).pack(side="left")

        self._entrada_hasta = tk.Entry(
            filtros, width=12, bg=PANEL_SECUNDARIO, fg=TEXTO_CLARO,
            insertbackground=ACENTO, relief="flat", font=("Segoe UI", 10)
        )
        self._entrada_hasta.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self._entrada_hasta.pack(side="left", padx=(4, 0))

        # ── Tabla ─────────────────────────────────────────────────────────────
        contenedor = tk.Frame(self, bg=FONDO_PANEL)
        contenedor.grid(row=2, column=0, sticky="nsew", padx=12, pady=8)
        contenedor.columnconfigure(0, weight=1)
        contenedor.rowconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        columnas = ("nombre", "apellido", "fecha", "hora", "estado")
        self._tree = ttk.Treeview(
            contenedor, columns=columnas,
            show="headings", selectmode="browse"
        )

        encabezados = {
            "nombre":   ("Nombre",   160),
            "apellido": ("Apellido", 160),
            "fecha":    ("Fecha",    110),
            "hora":     ("Hora",      90),
            "estado":   ("Estado",    90),
        }
        for col, (titulo, ancho) in encabezados.items():
            self._tree.heading(col, text=titulo, anchor="center")
            self._tree.column(col, width=ancho, anchor="center", stretch=False)

        # Scrollbar vertical
        scroll_v = ttk.Scrollbar(contenedor, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll_v.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        scroll_v.grid(row=0, column=1, sticky="ns")

        # Colores de filas alternadas
        self._tree.tag_configure("par",       background=FILA_PAR,   foreground=TEXTO_CLARO)
        self._tree.tag_configure("impar",     background=FILA_IMPAR, foreground=TEXTO_CLARO)
        self._tree.tag_configure("presente",  foreground=VERDE_OK)
        self._tree.tag_configure("ausente",   foreground=ROJO_ERROR)

        # ── Barra de estado inferior ──────────────────────────────────────────
        barra_inf = tk.Frame(self, bg=PANEL_SECUNDARIO, padx=12, pady=4)
        barra_inf.grid(row=3, column=0, sticky="ew")

        self._lbl_conteo = tk.Label(
            barra_inf, text="0 registros",
            bg=PANEL_SECUNDARIO, fg=TEXTO_OPACO, font=("Segoe UI", 9)
        )
        self._lbl_conteo.pack(side="left")

    # ── Refresco de datos ─────────────────────────────────────────────────────

    def _programar_refresco(self):
        """Programa el próximo refresco automático."""
        if self._refresco_activo:
            self._refrescar_tabla()
            self.after(INTERVALO_REFRESCO_MS, self._programar_refresco)

    def _refrescar_tabla(self):
        """Actualiza los datos de la tabla sin parpadeo."""
        try:
            registros = obtener_detecciones_recientes(50)
        except Exception as e:
            logger.error(f"Error al refrescar tabla: {e}")
            return

        # Limpiar tabla
        self._tree.delete(*self._tree.get_children())

        for idx, r in enumerate(registros):
            etiqueta_fila = "par" if idx % 2 == 0 else "impar"
            etiqueta_estado = "presente" if r["estado"] == "Presente" else "ausente"
            self._tree.insert(
                "", "end",
                values=(r["nombre"], r["apellido"], r["fecha"], r["hora"], r["estado"]),
                tags=(etiqueta_fila, etiqueta_estado)
            )

        ahora = datetime.now().strftime("%H:%M:%S")
        self._lbl_actualizacion.configure(text=f"Actualizado: {ahora}")
        self._lbl_conteo.configure(text=f"{len(registros)} registros mostrados")

    # ── Exportación ───────────────────────────────────────────────────────────

    def _exportar_excel(self):
        """Exporta el rango de fechas seleccionado a Excel."""
        fecha_desde = self._entrada_desde.get().strip()
        fecha_hasta = self._entrada_hasta.get().strip()

        # Validación básica de formato
        try:
            datetime.strptime(fecha_desde, "%Y-%m-%d")
            datetime.strptime(fecha_hasta, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror(
                "Fecha inválida",
                "Use el formato YYYY-MM-DD.\nEjemplo: 2024-01-15"
            )
            return

        if fecha_desde > fecha_hasta:
            messagebox.showerror("Fechas inválidas", "La fecha de inicio debe ser anterior a la fecha fin.")
            return

        def _ejecutar_exportacion():
            try:
                ruta = exportar_asistencia(fecha_desde, fecha_hasta, modo="resumen")
                self.after(0, lambda: _exportacion_exitosa(ruta))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error de exportación", str(e)))

        def _exportacion_exitosa(ruta: str):
            respuesta = messagebox.askyesno(
                "Exportación completada",
                f"Archivo generado:\n{ruta}\n\n¿Desea abrir la carpeta de exportaciones?"
            )
            if respuesta:
                abrir_carpeta_exports()

        threading.Thread(target=_ejecutar_exportacion, daemon=True).start()

    # ── Limpieza ──────────────────────────────────────────────────────────────

    def destruir(self):
        """Detener el refresco automático."""
        self._refresco_activo = False


# ─── Utilidad ─────────────────────────────────────────────────────────────────

def _hover(boton: tk.Button, color_normal: str, color_hover: str):
    """Aplica efecto hover a un botón."""
    boton.bind("<Enter>", lambda _: boton.configure(bg=color_hover))
    boton.bind("<Leave>", lambda _: boton.configure(bg=color_normal))
