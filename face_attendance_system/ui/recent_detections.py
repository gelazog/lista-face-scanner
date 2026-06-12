"""
Panel de últimas detecciones con tabla scrollable y exportación a Excel.
Pestaña B de la ventana principal.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import logging
from datetime import datetime, timedelta

from database import (
    obtener_detecciones_con_id,
    obtener_todos_los_usuarios,
    actualizar_asistencia,
    eliminar_asistencia,
)
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
    Muestra los últimos registros en una tabla con auto-refresco,
    filtros rápidos, filtro por alumno, edición y corrección de detecciones.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._refresco_activo = True
        self._dialogo_abierto = False

        # Estado del filtro activo: "hoy", "ayer", "semana", "mes", "personalizado"
        self._filtro_activo = "hoy"

        # Botones de chip para resaltar el seleccionado
        self._chip_btns: dict[str, tk.Button] = {}

        # Lista de usuarios cargados: [{"id": int, "nombre": str, "apellido": str}]
        self._usuarios: list[dict] = []

        # Mapeo nombre_completo → usuario_id
        self._mapa_usuarios: dict[str, int] = {}

        self.configure(style="Panel.TFrame")
        self._construir_ui()
        self._cargar_usuarios()
        self._programar_refresco()

    # ── Construcción UI ───────────────────────────────────────────────────────

    def _construir_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        # ── Barra superior ────────────────────────────────────────────────────
        barra = tk.Frame(self, bg=PANEL_SECUNDARIO, padx=12, pady=8)
        barra.grid(row=0, column=0, sticky="ew")

        tk.Label(
            barra, text="Últimas Detecciones",
            bg=PANEL_SECUNDARIO, fg=ACENTO, font=("Segoe UI", 13, "bold")
        ).pack(side="left")

        btn_exportar = tk.Button(
            barra, text="📊  Exportar a Excel",
            bg=ACENTO, fg="#0A0A1A", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=14, pady=6, cursor="hand2",
            command=self._exportar_excel
        )
        btn_exportar.pack(side="right", padx=4)
        _hover(btn_exportar, ACENTO, "#00B894")

        self._lbl_actualizacion = tk.Label(
            barra, text="",
            bg=PANEL_SECUNDARIO, fg=TEXTO_OPACO, font=("Segoe UI", 9)
        )
        self._lbl_actualizacion.pack(side="right", padx=12)

        # ── Fila de chips de filtro rápido ────────────────────────────────────
        fila_chips = tk.Frame(self, bg=FONDO_PANEL, padx=12, pady=8)
        fila_chips.grid(row=1, column=0, sticky="ew")

        chips = [
            ("hoy",           "📅 Hoy"),
            ("ayer",          "📅 Ayer"),
            ("semana",        "📅 Esta semana"),
            ("mes",           "📅 Este mes"),
            ("personalizado", "📅 Personalizado"),
        ]

        for key, label in chips:
            btn = tk.Button(
                fila_chips, text=label,
                bg=ACENTO if key == self._filtro_activo else PANEL_SECUNDARIO,
                fg="#0A0A1A" if key == self._filtro_activo else TEXTO_CLARO,
                font=("Segoe UI", 9, "bold"),
                relief="flat", padx=10, pady=4, cursor="hand2",
                command=lambda k=key: self._seleccionar_chip(k)
            )
            btn.pack(side="left", padx=3)
            self._chip_btns[key] = btn

        # Separador + filtro de alumno en la misma fila (derecha)
        tk.Label(
            fila_chips, text="Alumno:",
            bg=FONDO_PANEL, fg=TEXTO_CLARO, font=("Segoe UI", 10)
        ).pack(side="left", padx=(20, 4))

        self._var_alumno = tk.StringVar(value="Todos los alumnos")
        self._combo_alumno = ttk.Combobox(
            fila_chips,
            textvariable=self._var_alumno,
            state="readonly",
            width=22,
            font=("Segoe UI", 10),
        )
        self._combo_alumno["values"] = ["Todos los alumnos"]
        self._combo_alumno.pack(side="left", padx=2)
        self._combo_alumno.bind("<<ComboboxSelected>>", lambda _: self._refrescar_tabla())

        # ── Panel de fechas personalizadas (oculto por defecto) ───────────────
        self._frame_fechas = tk.Frame(self, bg=FONDO_PANEL, padx=12, pady=4)
        self._frame_fechas.grid(row=2, column=0, sticky="ew")
        self._frame_fechas.grid_remove()   # oculto inicialmente

        tk.Label(
            self._frame_fechas, text="Desde:",
            bg=FONDO_PANEL, fg=TEXTO_CLARO, font=("Segoe UI", 10)
        ).pack(side="left")

        self._entrada_desde = tk.Entry(
            self._frame_fechas, width=12, bg=PANEL_SECUNDARIO, fg=TEXTO_CLARO,
            insertbackground=ACENTO, relief="flat", font=("Segoe UI", 10)
        )
        self._entrada_desde.insert(0, (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"))
        self._entrada_desde.pack(side="left", padx=(4, 12))

        tk.Label(
            self._frame_fechas, text="Hasta:",
            bg=FONDO_PANEL, fg=TEXTO_CLARO, font=("Segoe UI", 10)
        ).pack(side="left")

        self._entrada_hasta = tk.Entry(
            self._frame_fechas, width=12, bg=PANEL_SECUNDARIO, fg=TEXTO_CLARO,
            insertbackground=ACENTO, relief="flat", font=("Segoe UI", 10)
        )
        self._entrada_hasta.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self._entrada_hasta.pack(side="left", padx=(4, 12))

        btn_aplicar = tk.Button(
            self._frame_fechas, text="Aplicar",
            bg=ACENTO, fg="#0A0A1A", font=("Segoe UI", 9, "bold"),
            relief="flat", padx=10, pady=3, cursor="hand2",
            command=self._refrescar_tabla
        )
        btn_aplicar.pack(side="left", padx=2)
        _hover(btn_aplicar, ACENTO, "#00B894")

        # ── Tabla ─────────────────────────────────────────────────────────────
        contenedor = tk.Frame(self, bg=FONDO_PANEL)
        contenedor.grid(row=3, column=0, sticky="nsew", padx=12, pady=8)
        contenedor.columnconfigure(0, weight=1)
        contenedor.rowconfigure(0, weight=1)

        # columna "id" oculta al inicio — almacena asistencia_id
        columnas = ("id", "nombre", "apellido", "fecha", "hora", "estado")
        self._tree = ttk.Treeview(
            contenedor, columns=columnas,
            show="headings", selectmode="browse"
        )

        # Columna oculta
        self._tree.heading("id", text="")
        self._tree.column("id", width=0, minwidth=0, stretch=False)

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

        scroll_v = ttk.Scrollbar(contenedor, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll_v.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        scroll_v.grid(row=0, column=1, sticky="ns")

        # Tags de color
        self._tree.tag_configure("par",      background=FILA_PAR,   foreground=TEXTO_CLARO)
        self._tree.tag_configure("impar",    background=FILA_IMPAR, foreground=TEXTO_CLARO)
        self._tree.tag_configure("presente", foreground=VERDE_OK)
        self._tree.tag_configure("ausente",  foreground=ROJO_ERROR)

        # Eventos de doble clic y clic derecho
        self._tree.bind("<Double-1>", self._on_doble_clic)
        self._tree.bind("<Button-3>", self._on_clic_derecho)

        # ── Stats bar ─────────────────────────────────────────────────────────
        barra_inf = tk.Frame(self, bg=PANEL_SECUNDARIO, padx=12, pady=4)
        barra_inf.grid(row=4, column=0, sticky="ew")

        self._lbl_stats = tk.Label(
            barra_inf, text="0 registros mostrados  ·  0 alumnos únicos  ·  Última detección: —",
            bg=PANEL_SECUNDARIO, fg=TEXTO_OPACO, font=("Segoe UI", 9)
        )
        self._lbl_stats.pack(side="left")

    # ── Chips y fechas ────────────────────────────────────────────────────────

    def _seleccionar_chip(self, key: str):
        """Activa el chip seleccionado y actualiza la tabla."""
        self._filtro_activo = key
        for k, btn in self._chip_btns.items():
            if k == key:
                btn.configure(bg=ACENTO, fg="#0A0A1A")
            else:
                btn.configure(bg=PANEL_SECUNDARIO, fg=TEXTO_CLARO)

        if key == "personalizado":
            self._frame_fechas.grid()
        else:
            self._frame_fechas.grid_remove()

        self._refrescar_tabla()

    def _rango_fechas_activo(self) -> tuple[str, str]:
        """Devuelve (fecha_inicio, fecha_fin) según el filtro activo."""
        hoy = datetime.now().date()
        if self._filtro_activo == "hoy":
            return str(hoy), str(hoy)
        elif self._filtro_activo == "ayer":
            ayer = hoy - timedelta(days=1)
            return str(ayer), str(ayer)
        elif self._filtro_activo == "semana":
            lunes = hoy - timedelta(days=hoy.weekday())
            return str(lunes), str(hoy)
        elif self._filtro_activo == "mes":
            primero = hoy.replace(day=1)
            return str(primero), str(hoy)
        else:  # personalizado
            return (
                self._entrada_desde.get().strip(),
                self._entrada_hasta.get().strip(),
            )

    # ── Carga de usuarios ─────────────────────────────────────────────────────

    def _cargar_usuarios(self):
        """Carga la lista de usuarios para el combobox de filtro."""
        try:
            usuarios = obtener_todos_los_usuarios()
        except Exception as e:
            logger.error(f"Error al cargar usuarios: {e}")
            return

        self._usuarios = usuarios
        self._mapa_usuarios = {
            f"{u['nombre']} {u['apellido']}": u["id"]
            for u in usuarios
        }

        nombres = ["Todos los alumnos"] + [
            f"{u['nombre']} {u['apellido']}" for u in usuarios
        ]
        self._combo_alumno["values"] = nombres

    # ── Refresco de datos ─────────────────────────────────────────────────────

    def _programar_refresco(self):
        """Programa el próximo refresco automático."""
        if self._refresco_activo:
            if not self._dialogo_abierto:
                self._refrescar_tabla()
            self.after(INTERVALO_REFRESCO_MS, self._programar_refresco)

    def _refrescar_tabla(self):
        """Actualiza los datos de la tabla según el filtro activo."""
        fecha_inicio, fecha_fin = self._rango_fechas_activo()

        # Validar fechas si es modo personalizado
        if self._filtro_activo == "personalizado":
            try:
                datetime.strptime(fecha_inicio, "%Y-%m-%d")
                datetime.strptime(fecha_fin, "%Y-%m-%d")
            except ValueError:
                return
            if fecha_inicio > fecha_fin:
                return

        try:
            registros = obtener_detecciones_con_id(500)
        except Exception as e:
            logger.error(f"Error al refrescar tabla: {e}")
            return

        # Filtrar por rango de fecha
        registros = [
            r for r in registros
            if fecha_inicio <= r["fecha"] <= fecha_fin
        ]

        # Filtrar por alumno seleccionado
        alumno_sel = self._var_alumno.get()
        if alumno_sel != "Todos los alumnos":
            registros = [
                r for r in registros
                if f"{r['nombre']} {r['apellido']}" == alumno_sel
            ]

        # Poblar tabla
        self._tree.delete(*self._tree.get_children())
        for idx, r in enumerate(registros):
            etiqueta_fila   = "par" if idx % 2 == 0 else "impar"
            etiqueta_estado = "presente" if r["estado"] == "Presente" else "ausente"
            self._tree.insert(
                "", "end",
                values=(
                    r["asistencia_id"],
                    r["nombre"],
                    r["apellido"],
                    r["fecha"],
                    r["hora"],
                    r["estado"],
                ),
                tags=(etiqueta_fila, etiqueta_estado)
            )

        # Calcular stats
        total = len(registros)
        alumnos_unicos = len({f"{r['nombre']} {r['apellido']}" for r in registros})
        ultima = registros[0]["hora"] if registros else "—"

        ahora = datetime.now().strftime("%H:%M:%S")
        self._lbl_actualizacion.configure(text=f"Actualizado: {ahora}")
        self._lbl_stats.configure(
            text=(
                f"{total} registros mostrados  ·  "
                f"{alumnos_unicos} alumnos únicos  ·  "
                f"Última detección: {ultima}"
            )
        )

    # ── Eventos de tabla ──────────────────────────────────────────────────────

    def _on_doble_clic(self, event):
        """Abre el diálogo de corrección al hacer doble clic en una fila."""
        item = self._tree.focus()
        if not item:
            return
        self._abrir_dialogo_correccion(item)

    def _on_clic_derecho(self, event):
        """Muestra menú contextual al hacer clic derecho."""
        item = self._tree.identify_row(event.y)
        if not item:
            return
        self._tree.selection_set(item)
        self._tree.focus(item)

        menu = tk.Menu(self, tearoff=0, bg=PANEL_SECUNDARIO, fg=TEXTO_CLARO,
                       activebackground=ACENTO, activeforeground="#0A0A1A",
                       font=("Segoe UI", 10))
        menu.add_command(
            label="✏️  Corregir detección",
            command=lambda: self._abrir_dialogo_correccion(item)
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ── Diálogo de corrección ─────────────────────────────────────────────────

    def _abrir_dialogo_correccion(self, item: str):
        """Abre el modal para corregir o eliminar una detección."""
        valores = self._tree.item(item, "values")
        if not valores:
            return

        asistencia_id = int(valores[0])
        nombre_actual = f"{valores[1]} {valores[2]}"
        fecha_hora    = f"{valores[3]}  {valores[4]}"

        self._dialogo_abierto = True

        ventana = tk.Toplevel(self)
        ventana.title("Corregir detección")
        ventana.configure(bg=FONDO_PANEL)
        ventana.resizable(False, False)

        # Centrar sobre la ventana principal
        self.update_idletasks()
        ancho, alto = 480, 280
        x = self.winfo_rootx() + (self.winfo_width()  - ancho) // 2
        y = self.winfo_rooty() + (self.winfo_height() - alto)  // 2
        ventana.geometry(f"{ancho}x{alto}+{x}+{y}")

        ventana.grab_set()
        ventana.protocol("WM_DELETE_WINDOW", lambda: self._cerrar_dialogo(ventana))

        # Título del modal
        tk.Label(
            ventana, text="✏️  Corregir detección",
            bg=FONDO_PANEL, fg=ACENTO, font=("Segoe UI", 13, "bold")
        ).pack(pady=(16, 6))

        # Alumno actual
        tk.Label(
            ventana, text=f"Actualmente registrado como:  {nombre_actual}",
            bg=FONDO_PANEL, fg=TEXTO_CLARO, font=("Segoe UI", 10)
        ).pack(pady=(0, 2))

        # Fecha/hora (solo lectura)
        tk.Label(
            ventana, text=f"Fecha y hora:  {fecha_hora}",
            bg=FONDO_PANEL, fg=TEXTO_OPACO, font=("Segoe UI", 9)
        ).pack(pady=(0, 12))

        # Combobox "Corregir a:"
        fila_combo = tk.Frame(ventana, bg=FONDO_PANEL)
        fila_combo.pack()

        tk.Label(
            fila_combo, text="Corregir a:",
            bg=FONDO_PANEL, fg=TEXTO_CLARO, font=("Segoe UI", 10)
        ).pack(side="left", padx=(0, 8))

        var_nuevo = tk.StringVar(value=nombre_actual)
        opciones_alumnos = [
            f"{u['nombre']} {u['apellido']}" for u in self._usuarios
        ]
        combo_nuevo = ttk.Combobox(
            fila_combo,
            textvariable=var_nuevo,
            values=opciones_alumnos,
            state="readonly",
            width=26,
            font=("Segoe UI", 10),
        )
        combo_nuevo.pack(side="left")

        # Botones
        fila_btns = tk.Frame(ventana, bg=FONDO_PANEL)
        fila_btns.pack(pady=20)

        def _guardar():
            nombre_nuevo = var_nuevo.get()
            nuevo_id = self._mapa_usuarios.get(nombre_nuevo)
            if nuevo_id is None:
                messagebox.showerror("Error", "Alumno no encontrado.", parent=ventana)
                return
            try:
                ok = actualizar_asistencia(asistencia_id, nuevo_id)
            except Exception as e:
                messagebox.showerror("Error al guardar", str(e), parent=ventana)
                return
            if ok:
                self._cerrar_dialogo(ventana)
                self._refrescar_tabla()
                self._lbl_stats.configure(
                    fg=VERDE_OK
                )
                self.after(
                    100,
                    lambda: self._lbl_stats.configure(fg=TEXTO_OPACO)
                )
            else:
                messagebox.showerror("Error", "No se pudo actualizar el registro.", parent=ventana)

        def _eliminar():
            confirmar = messagebox.askyesno(
                "Confirmar eliminación",
                f"¿Eliminar la detección de {nombre_actual}\nel {fecha_hora}?\n\nEsta acción no se puede deshacer.",
                parent=ventana,
                icon="warning"
            )
            if not confirmar:
                return
            try:
                ok = eliminar_asistencia(asistencia_id)
            except Exception as e:
                messagebox.showerror("Error al eliminar", str(e), parent=ventana)
                return
            if ok:
                self._cerrar_dialogo(ventana)
                self._refrescar_tabla()
            else:
                messagebox.showerror("Error", "No se pudo eliminar el registro.", parent=ventana)

        btn_guardar = tk.Button(
            fila_btns, text="Guardar cambio",
            bg=ACENTO, fg="#0A0A1A", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=14, pady=6, cursor="hand2",
            command=_guardar
        )
        btn_guardar.pack(side="left", padx=6)
        _hover(btn_guardar, ACENTO, "#00B894")

        btn_eliminar = tk.Button(
            fila_btns, text="Eliminar esta detección",
            bg=ROJO_ERROR, fg="#FFFFFF", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=14, pady=6, cursor="hand2",
            command=_eliminar
        )
        btn_eliminar.pack(side="left", padx=6)
        _hover(btn_eliminar, ROJO_ERROR, "#CC3333")

        btn_cancelar = tk.Button(
            fila_btns, text="Cancelar",
            bg=PANEL_SECUNDARIO, fg=TEXTO_CLARO, font=("Segoe UI", 10),
            relief="flat", padx=14, pady=6, cursor="hand2",
            command=lambda: self._cerrar_dialogo(ventana)
        )
        btn_cancelar.pack(side="left", padx=6)
        _hover(btn_cancelar, PANEL_SECUNDARIO, "#3A3A5E")

    def _cerrar_dialogo(self, ventana: tk.Toplevel):
        """Cierra el modal y reactiva el auto-refresco."""
        self._dialogo_abierto = False
        ventana.grab_release()
        ventana.destroy()

    # ── Exportación ───────────────────────────────────────────────────────────

    def _exportar_excel(self):
        """Exporta el rango de fechas activo a Excel."""
        fecha_desde, fecha_hasta = self._rango_fechas_activo()

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
