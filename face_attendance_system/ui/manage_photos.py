"""
Panel de gestión de fotos de usuarios registrados.
Permite subir nuevas fotos o eliminar las existentes sin romper el sistema.
Pestaña D de la ventana principal.
"""

import os
import shutil
import threading
import logging
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
import tkinter as tk
from PIL import Image, ImageTk

from database import obtener_todos_los_usuarios
from face_engine import MotorReconocimiento, USERS_DIR

logger = logging.getLogger(__name__)

# ─── Colores ──────────────────────────────────────────────────────────────────
FONDO_PANEL      = "#1E1E2E"
PANEL_SECUNDARIO = "#2A2A3E"
ACENTO           = "#00D4AA"
TEXTO_CLARO      = "#E0E0F0"
TEXTO_OPACO      = "#7878A0"
ROJO_ERROR       = "#FF4444"

# ─── Configuración de miniaturas ──────────────────────────────────────────────
THUMB_W          = 110
THUMB_H          = 88
THUMB_PAD        = 8
FOTOS_MINIMAS    = 3
EXTENSIONES      = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class GestionarFotos(ttk.Frame):
    """
    Frame de la pestaña 'Gestionar Fotos'.
    Panel izquierdo: lista de usuarios registrados.
    Panel derecho: cuadrícula de miniaturas con checkboxes para selección.
    Acciones: subir fotos nuevas, eliminar seleccionadas, abrir carpeta.
    """

    def __init__(self, parent, motor: MotorReconocimiento, **kwargs):
        super().__init__(parent, **kwargs)
        self.motor = motor

        self._usuario_sel: dict | None = None    # fila de la DB del usuario activo
        self._ruta_usuario: str       = ""
        self._fotos_en_disco: list[str] = []     # rutas absolutas en orden
        self._fotos_sel: set[int]       = set()  # índices seleccionados
        self._thumb_refs: list          = []      # evita GC en ImageTk
        self._check_vars: list          = []      # tk.BooleanVar por miniatura

        self.configure(style="Panel.TFrame")
        self._construir_ui()
        self._cargar_lista_usuarios()

    # ═════════════════════════════════════════════════════════════════════════
    # Construcción de la UI
    # ═════════════════════════════════════════════════════════════════════════

    def _construir_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Barra de título ───────────────────────────────────────────────────
        barra = tk.Frame(self, bg=PANEL_SECUNDARIO, padx=12, pady=8)
        barra.grid(row=0, column=0, sticky="ew")

        tk.Label(
            barra, text="Gestionar Fotos de Usuarios",
            bg=PANEL_SECUNDARIO, fg=ACENTO,
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left")

        # ── PanedWindow horizontal ────────────────────────────────────────────
        self._paned = tk.PanedWindow(
            self, orient="horizontal",
            bg="#0D0D1A", sashwidth=5, sashrelief="flat",
            handlesize=0,
        )
        self._paned.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        self._construir_panel_usuarios()
        self._construir_panel_fotos()

        # ── Barra de estado ───────────────────────────────────────────────────
        barra_est = tk.Frame(self, bg=PANEL_SECUNDARIO, padx=12, pady=5)
        barra_est.grid(row=2, column=0, sticky="ew")

        self._lbl_estado = tk.Label(
            barra_est,
            text="Seleccione un usuario de la lista para ver sus fotos.",
            bg=PANEL_SECUNDARIO, fg=TEXTO_OPACO,
            font=("Segoe UI", 10),
        )
        self._lbl_estado.pack(side="left")

    # ── Panel izquierdo: lista de usuarios ────────────────────────────────────

    def _construir_panel_usuarios(self):
        marco = tk.Frame(self._paned, bg=PANEL_SECUNDARIO)
        self._paned.add(marco, minsize=180, width=230)

        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(1, weight=1)

        # Encabezado con botón de refresco
        cab = tk.Frame(marco, bg=PANEL_SECUNDARIO, padx=8, pady=8)
        cab.grid(row=0, column=0, sticky="ew")

        tk.Label(
            cab, text="Usuarios",
            bg=PANEL_SECUNDARIO, fg=TEXTO_CLARO,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")

        tk.Button(
            cab, text="↺",
            bg=PANEL_SECUNDARIO, fg=ACENTO,
            font=("Segoe UI", 12, "bold"),
            relief="flat", padx=6, cursor="hand2",
            command=self._cargar_lista_usuarios,
            activebackground=FONDO_PANEL, activeforeground=ACENTO,
        ).pack(side="right")

        # Listbox + scrollbar
        contenedor = tk.Frame(marco, bg=PANEL_SECUNDARIO)
        contenedor.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        contenedor.columnconfigure(0, weight=1)
        contenedor.rowconfigure(0, weight=1)

        self._listbox = tk.Listbox(
            contenedor,
            bg=FONDO_PANEL, fg=TEXTO_CLARO,
            selectbackground=ACENTO, selectforeground="#0A0A1A",
            font=("Segoe UI", 10),
            relief="flat", highlightthickness=1,
            highlightbackground=PANEL_SECUNDARIO,
            highlightcolor=ACENTO,
            activestyle="none", cursor="hand2",
        )
        self._listbox.grid(row=0, column=0, sticky="nsew")
        self._listbox.bind("<<ListboxSelect>>", self._on_usuario_click)

        sc = ttk.Scrollbar(contenedor, orient="vertical", command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=sc.set)
        sc.grid(row=0, column=1, sticky="ns")

    # ── Panel derecho: fotos + acciones ──────────────────────────────────────

    def _construir_panel_fotos(self):
        self._marco_fotos = tk.Frame(self._paned, bg=FONDO_PANEL)
        self._paned.add(self._marco_fotos, minsize=400)

        self._marco_fotos.columnconfigure(0, weight=1)
        self._marco_fotos.rowconfigure(1, weight=1)

        # ── Encabezado con nombre de usuario y botones ────────────────────────
        cab_f = tk.Frame(self._marco_fotos, bg=FONDO_PANEL, padx=10, pady=8)
        cab_f.grid(row=0, column=0, sticky="ew")
        cab_f.columnconfigure(0, weight=1)

        self._lbl_usuario = tk.Label(
            cab_f,
            text="— Ningún usuario seleccionado —",
            bg=FONDO_PANEL, fg=TEXTO_OPACO,
            font=("Segoe UI", 11, "bold"),
        )
        self._lbl_usuario.grid(row=0, column=0, sticky="w")

        btn_marco = tk.Frame(cab_f, bg=FONDO_PANEL)
        btn_marco.grid(row=0, column=1, sticky="e")

        self._btn_carpeta = tk.Button(
            btn_marco, text="📂  Abrir carpeta",
            bg=PANEL_SECUNDARIO, fg=TEXTO_CLARO,
            font=("Segoe UI", 9), relief="flat",
            padx=10, pady=5, cursor="hand2",
            state="disabled", command=self._abrir_carpeta,
            activebackground=FONDO_PANEL, activeforeground=ACENTO,
        )
        self._btn_carpeta.pack(side="left", padx=(0, 6))

        self._btn_subir = tk.Button(
            btn_marco, text="⬆  Subir fotos",
            bg=ACENTO, fg="#0A0A1A",
            font=("Segoe UI", 9, "bold"), relief="flat",
            padx=10, pady=5, cursor="hand2",
            state="disabled", command=self._subir_fotos,
            activebackground="#00B894", activeforeground="#0A0A1A",
        )
        self._btn_subir.pack(side="left", padx=(0, 6))

        self._btn_eliminar = tk.Button(
            btn_marco, text="🗑  Eliminar seleccionadas",
            bg=ROJO_ERROR, fg="white",
            font=("Segoe UI", 9, "bold"), relief="flat",
            padx=10, pady=5, cursor="hand2",
            state="disabled", command=self._eliminar_seleccionadas,
            activebackground="#CC2222", activeforeground="white",
        )
        self._btn_eliminar.pack(side="left")

        # ── Canvas scrollable para miniaturas ─────────────────────────────────
        cont_canvas = tk.Frame(self._marco_fotos, bg=FONDO_PANEL)
        cont_canvas.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        cont_canvas.columnconfigure(0, weight=1)
        cont_canvas.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            cont_canvas, bg=FONDO_PANEL,
            bd=0, highlightthickness=0,
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")

        sc_f = ttk.Scrollbar(cont_canvas, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sc_f.set)
        sc_f.grid(row=0, column=1, sticky="ns")

        # Frame interior donde se colocan las miniaturas
        self._grid_thumbs = tk.Frame(self._canvas, bg=FONDO_PANEL)
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._grid_thumbs, anchor="nw"
        )
        self._grid_thumbs.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        )
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfig(self._canvas_window, width=e.width)
        )

        # Scroll con rueda del ratón
        self._canvas.bind("<MouseWheel>", lambda e: self._canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self._mostrar_placeholder("Seleccione un usuario\npara ver sus fotos.")

    # ═════════════════════════════════════════════════════════════════════════
    # Carga de datos
    # ═════════════════════════════════════════════════════════════════════════

    def _cargar_lista_usuarios(self):
        """Recarga la lista desde la DB."""
        self._listbox.delete(0, "end")
        self._usuarios: list[dict] = []

        try:
            self._usuarios = obtener_todos_los_usuarios()
        except Exception as e:
            logger.error(f"Error cargando usuarios: {e}")

        if not self._usuarios:
            self._listbox.insert("end", "  (sin usuarios registrados)")
            return

        for u in self._usuarios:
            self._listbox.insert("end", f"  {u['nombre']} {u['apellido']}")

    def _on_usuario_click(self, _event=None):
        sel = self._listbox.curselection()
        if not sel or not self._usuarios:
            return
        idx = sel[0]
        if idx >= len(self._usuarios):
            return

        self._usuario_sel = self._usuarios[idx]
        nombre = self._usuario_sel["nombre"]
        apellido = self._usuario_sel["apellido"]
        ruta = self._usuario_sel.get("ruta_carpeta") or ""

        # Si la ruta de la DB no existe, intentar la ruta por defecto
        if not ruta or not os.path.isdir(ruta):
            ruta = os.path.join(USERS_DIR, f"{nombre}_{apellido}")
        self._ruta_usuario = ruta

        self._lbl_usuario.configure(
            text=f"Fotos de:  {nombre} {apellido}", fg=TEXTO_CLARO
        )
        self._btn_carpeta.configure(state="normal")
        self._btn_subir.configure(state="normal")

        self._recargar_miniaturas()

    # ═════════════════════════════════════════════════════════════════════════
    # Miniaturas
    # ═════════════════════════════════════════════════════════════════════════

    def _recargar_miniaturas(self):
        """Limpia y redibuja las miniaturas del usuario activo."""
        self._fotos_sel.clear()
        self._btn_eliminar.configure(state="disabled")

        for w in self._grid_thumbs.winfo_children():
            w.destroy()
        self._thumb_refs.clear()
        self._check_vars.clear()
        self._fotos_en_disco.clear()

        if not os.path.isdir(self._ruta_usuario):
            self._mostrar_placeholder(
                f"Carpeta no encontrada:\n{self._ruta_usuario}\n\n"
                "Use 'Subir fotos' para crearla automáticamente."
            )
            self._actualizar_estado()
            return

        for archivo in sorted(os.listdir(self._ruta_usuario)):
            if Path(archivo).suffix.lower() in EXTENSIONES:
                self._fotos_en_disco.append(
                    os.path.join(self._ruta_usuario, archivo)
                )

        if not self._fotos_en_disco:
            self._mostrar_placeholder(
                "Esta carpeta no tiene fotos.\nUse 'Subir fotos' para añadir."
            )
            self._actualizar_estado()
            return

        self._dibujar_miniaturas()
        self._actualizar_estado()

    def _mostrar_placeholder(self, texto: str):
        for w in self._grid_thumbs.winfo_children():
            w.destroy()
        tk.Label(
            self._grid_thumbs,
            text=texto,
            bg=FONDO_PANEL, fg=TEXTO_OPACO,
            font=("Segoe UI", 12), justify="center",
        ).pack(expand=True, pady=50, padx=20)

    def _dibujar_miniaturas(self):
        """Dibuja todas las fotos como miniaturas seleccionables."""
        ancho_canvas = max(self._canvas.winfo_width(), 600)
        cols = max(1, (ancho_canvas - 16) // (THUMB_W + THUMB_PAD * 2 + 4))

        for i, ruta in enumerate(self._fotos_en_disco):
            fila_idx = i // cols
            col_idx  = i % cols

            # Cargar miniatura
            img_tk = None
            try:
                img = Image.open(ruta)
                img.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
                img_tk = ImageTk.PhotoImage(img)
                self._thumb_refs.append(img_tk)
            except Exception:
                self._thumb_refs.append(None)

            # Celda contenedora
            celda = tk.Frame(
                self._grid_thumbs,
                bg=FONDO_PANEL,
                padx=THUMB_PAD, pady=THUMB_PAD,
            )
            celda.grid(row=fila_idx, column=col_idx)

            # Marco con borde (cambia de color al seleccionar)
            borde = tk.Frame(
                celda, bg=PANEL_SECUNDARIO,
                padx=2, pady=2, cursor="hand2",
            )
            borde.pack()

            if img_tk:
                lbl_img = tk.Label(
                    borde, image=img_tk,
                    bg=PANEL_SECUNDARIO, cursor="hand2",
                )
                lbl_img.pack()
            else:
                tk.Label(
                    borde,
                    text="⚠ Error\nal cargar",
                    width=THUMB_W // 8, height=4,
                    bg=PANEL_SECUNDARIO, fg=ROJO_ERROR,
                    font=("Segoe UI", 8),
                ).pack()

            # Nombre de archivo (truncado)
            nombre_corto = Path(ruta).name
            if len(nombre_corto) > 18:
                nombre_corto = nombre_corto[:15] + "..."
            tk.Label(
                borde, text=nombre_corto,
                bg=PANEL_SECUNDARIO, fg=TEXTO_OPACO,
                font=("Segoe UI", 7),
            ).pack()

            # Variable para el checkbox
            var = tk.BooleanVar(value=False)
            self._check_vars.append(var)

            chk = tk.Checkbutton(
                celda, variable=var,
                text="Seleccionar",
                bg=FONDO_PANEL, fg=TEXTO_OPACO,
                selectcolor=FONDO_PANEL,
                activebackground=FONDO_PANEL,
                font=("Segoe UI", 7),
                relief="flat", cursor="hand2",
                command=lambda idx=i, v=var, b=borde: self._toggle_seleccion(idx, v, b),
            )
            chk.pack()

            # Click en la imagen también togglea
            def _on_click(e, idx=i, v=var, b=borde):
                v.set(not v.get())
                self._toggle_seleccion(idx, v, b)

            borde.bind("<Button-1>", _on_click)
            for child in borde.winfo_children():
                child.bind("<Button-1>", _on_click)

    def _toggle_seleccion(self, indice: int, var: tk.BooleanVar, borde: tk.Frame):
        """Actualiza la selección y cambia el color del borde."""
        if var.get():
            self._fotos_sel.add(indice)
            color = ACENTO
        else:
            self._fotos_sel.discard(indice)
            color = PANEL_SECUNDARIO

        borde.configure(bg=color)
        for child in borde.winfo_children():
            try:
                child.configure(bg=color)
            except Exception:
                pass

        tiene_sel = bool(self._fotos_sel)
        self._btn_eliminar.configure(state="normal" if tiene_sel else "disabled")
        self._actualizar_estado()

    # ═════════════════════════════════════════════════════════════════════════
    # Acciones
    # ═════════════════════════════════════════════════════════════════════════

    def _abrir_carpeta(self):
        ruta = os.path.normpath(self._ruta_usuario)
        if os.path.isdir(ruta):
            os.startfile(ruta)
        else:
            messagebox.showwarning(
                "Carpeta no encontrada",
                f"No existe la carpeta:\n{ruta}\n\nSuba fotos primero para crearla.",
            )

    def _subir_fotos(self):
        """Abre un diálogo para seleccionar imágenes y las copia a la carpeta del usuario."""
        rutas = filedialog.askopenfilenames(
            title="Seleccionar fotos para subir",
            filetypes=[
                ("Imágenes", "*.jpg *.jpeg *.png *.bmp *.webp"),
                ("Todos los archivos", "*.*"),
            ],
        )
        if not rutas:
            return

        os.makedirs(self._ruta_usuario, exist_ok=True)

        copiadas = 0
        omitidas = 0
        errores  = 0

        for ruta_origen in rutas:
            nombre_archivo = Path(ruta_origen).name
            destino = os.path.join(self._ruta_usuario, nombre_archivo)

            # Si ya existe ese nombre de archivo, añadir sufijo numérico
            if os.path.exists(destino):
                base, ext = os.path.splitext(nombre_archivo)
                contador = 1
                while os.path.exists(destino):
                    destino = os.path.join(self._ruta_usuario, f"{base}_{contador}{ext}")
                    contador += 1

            try:
                shutil.copy2(ruta_origen, destino)
                copiadas += 1
            except Exception as e:
                logger.error(f"Error copiando {ruta_origen}: {e}")
                errores += 1

        if copiadas:
            self._recargar_motor_bg()
            self._recargar_miniaturas()

        partes = [f"Se subieron {copiadas} foto(s)."]
        if omitidas:
            partes.append(f"{omitidas} ya existían y fueron renombradas.")
        if errores:
            partes.append(f"{errores} no se pudieron copiar (ver log).")
        messagebox.showinfo("Fotos subidas", "\n".join(partes))

    def _eliminar_seleccionadas(self):
        """Elimina permanentemente las fotos marcadas."""
        if not self._fotos_sel:
            return

        # Advertir si quedan pocas fotos
        restantes = len(self._fotos_en_disco) - len(self._fotos_sel)
        if restantes < FOTOS_MINIMAS:
            continuar = messagebox.askyesno(
                "Pocas fotos restantes",
                f"Tras eliminar, quedarán solo {restantes} foto(s).\n"
                f"Se recomiendan mínimo {FOTOS_MINIMAS} para un reconocimiento confiable.\n\n"
                "¿Continuar de todas formas?",
            )
            if not continuar:
                return

        n = len(self._fotos_sel)
        confirmar = messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Eliminar {n} foto(s) permanentemente?\n"
            "Esta acción no se puede deshacer.",
        )
        if not confirmar:
            return

        eliminadas = 0
        for idx in sorted(self._fotos_sel):
            ruta = self._fotos_en_disco[idx]
            try:
                os.remove(ruta)
                eliminadas += 1
                logger.info(f"Foto eliminada: {ruta}")
            except Exception as e:
                logger.error(f"Error eliminando {ruta}: {e}")

        if eliminadas:
            self._recargar_motor_bg()
            self._recargar_miniaturas()
            messagebox.showinfo(
                "Fotos eliminadas",
                f"Se eliminaron {eliminadas} foto(s) correctamente.\n"
                "El sistema de reconocimiento ha sido actualizado.",
            )

    def _recargar_motor_bg(self):
        """Invalida y recarga el caché de encodings en hilo secundario."""
        threading.Thread(target=self.motor.recargar, daemon=True).start()

    # ═════════════════════════════════════════════════════════════════════════
    # Estado
    # ═════════════════════════════════════════════════════════════════════════

    def _actualizar_estado(self):
        total = len(self._fotos_en_disco)
        sel   = len(self._fotos_sel)

        if self._usuario_sel:
            texto = f"{total} foto(s) en disco"
            if sel:
                texto += f"  ·  {sel} seleccionada(s)"
            if total < FOTOS_MINIMAS:
                texto += f"  ·  ⚠ se recomiendan al menos {FOTOS_MINIMAS}"
        else:
            texto = "Seleccione un usuario de la lista para ver sus fotos."

        self._lbl_estado.configure(text=texto)

    def destruir(self):
        pass
