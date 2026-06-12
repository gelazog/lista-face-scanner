# Sistema de Asistencia por Reconocimiento Facial

Aplicación de escritorio nativa en Python que detecta e identifica rostros en tiempo real usando la cámara web, gestiona alumnos registrados, lleva un historial de asistencia y exporta listas a Excel. Diseñada principalmente para entornos escolares (alumnos de primaria y secundaria).

**Motor de IA:** InsightFace + ONNX — no requiere dlib, cmake ni Visual Studio.

---

## Requisitos del sistema

- **Windows 10 / 11** (en Linux/macOS ver `run.sh`)
- **Python 3.10 o superior** (probado en Python 3.14.3)
- **Camara web** conectada
- No se requiere cmake, Visual Studio, dlib ni TensorFlow

### Dependencias Python

| Paquete | Version minima | Uso |
|---|---|---|
| `opencv-python` | 4.8.0 | Captura de camara, dibujo de bboxes |
| `insightface` | 1.0.0 | Deteccion y reconocimiento facial |
| `onnxruntime` | 1.16.0 | Ejecucion de modelos ONNX |
| `Pillow` | 10.0.0 | Conversion de frames para Tkinter |
| `openpyxl` | 3.1.2 | Generacion de archivos Excel |
| `pandas` | 2.0.0 | Procesamiento de datos tabulares |
| `tkinter` | (stdlib) | Interfaz grafica de escritorio |
| `sqlite3` | (stdlib) | Base de datos local |

---

## Inicio rapido

**Windows** — doble clic en `run.bat`, o desde la terminal:

```bat
cd face_attendance_system
run.bat
```

`run.bat` verifica si el entorno virtual existe. Si no existe, ejecuta `setup.py` automaticamente antes de lanzar la app.

**Linux / macOS:**

```bash
bash run.sh
```

**Instalacion manual:**

```bash
python setup.py   # configura venv, instala dependencias, descarga modelos
python main.py
```

**Diagnostico previo (no instala nada):**

```bash
python check.py
```

---

## Descripcion de la interfaz (pestanas)

### Pestana A — Vista en Vivo

Feed de camara en tiempo real con deteccion de rostros superpuesta:

- **Recuadro verde** — alumno identificado (muestra nombre)
- **Recuadro azul/rojo** — persona no identificada
- Panel lateral con la lista de alumnos detectados en el momento
- Selector de camara (combobox) para elegir entre dispositivos disponibles
- La primera camara disponible se inicia automaticamente al abrir la pestana; si no llegan frames en 60 segundos, el sistema cambia a la siguiente camara disponible
- Registro automatico de asistencia con proteccion anti-duplicado de **5 minutos** por alumno

### Pestana B — Ultimas Detecciones

Historial de registros de asistencia con actualizacion automatica cada 3 segundos:

- **Filtros rapidos:** Hoy / Ayer / Esta semana / Este mes / Personalizado (rango de fechas)
- **Filtro por alumno:** dropdown para ver solo los registros de un alumno especifico
- **Estadisticas:** total de registros, alumnos unicos y hora de la ultima deteccion
- **Correccion de errores:** doble clic sobre cualquier fila para corregir un alumno mal identificado o eliminar el registro — especialmente util cuando alumnos con rasgos similares se confunden entre si
- **Exportar a Excel:** genera un archivo `.xlsx` con formato oscuro en la carpeta `exports/`

### Pestana C — Agregar Usuario (alumno)

Registro de nuevos alumnos con captura de fotos desde la camara:

- Preview en vivo de la camara durante la captura
- Captura manual de fotos con deteccion de rostro activa
- El boton **"Capturar Foto"** solo se habilita cuando hay un rostro visible en el frame
- Se requieren **minimo 5 fotos** para registrar al alumno (recomendado: 20 desde distintos angulos e iluminaciones)
- Validacion del nombre antes de guardar

### Pestana D — Gestionar Fotos

Administracion de fotos y datos de alumnos registrados:

- Lista de todos los alumnos registrados con sus fotos
- **Subir fotos:** dialogo de archivo (admite jpg, png, bmp, webp)
- **Eliminar fotos:** con aviso si el alumno queda con menos de 3 fotos
- **Editar datos del alumno:** corregir errores de ortografia en nombre o apellido; la carpeta y el cache de reconocimiento facial se actualizan automaticamente
- **Abrir carpeta:** abre la carpeta del alumno en el Explorador de Windows

---

## Instalacion manual paso a paso

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
python main.py
```

---

## Estructura del proyecto

```
face_attendance_system/
|
+-- main.py                   # Punto de entrada
+-- database.py               # SQLite: tablas, indices, CRUD
+-- face_engine.py            # InsightFace: encodings, cache, multi-camara
+-- export.py                 # Excel con formato oscuro (openpyxl)
|
+-- setup.py                  # Instalador automatico paso a paso
+-- check.py                  # Diagnostico rapido sin instalar nada
+-- run.bat                   # Lanzador Windows
+-- run.sh                    # Lanzador Linux/macOS
+-- requirements.txt          # Dependencias con versiones minimas
|
+-- ui/
|   +-- __init__.py
|   +-- main_window.py        # Ventana principal con pestanas
|   +-- camera_view.py        # Pestana A: feed en vivo + selector multi-camara
|   +-- recent_detections.py  # Pestana B: historial, filtros, correccion, export
|   +-- add_user.py           # Pestana C: captura de fotos con preview
|   \-- manage_photos.py      # Pestana D: gestion de fotos y edicion de datos
|
+-- data/
|   +-- users/                # Fotos de alumnos (subcarpeta por persona)
|   |   \-- Juan_Perez/
|   |       +-- foto_001.jpg
|   |       \-- ...
|   +-- attendance.db         # Base de datos SQLite (modo WAL)
|   +-- encodings_cache.pkl   # Cache de embeddings faciales
|   \-- app.log               # Log de la aplicacion
|
\-- exports/                  # Archivos Excel generados
    \-- Asistencia_YYYY-MM-DD_HHmm.xlsx
```

---

## Detalles tecnicos

| Aspecto | Valor |
|---|---|
| Backend de camara | MSMF (DirectShow/DSHOW deshabilitado intencionalmente — provoca crashes en Python 3.14 / Windows 10) |
| Modelo de reconocimiento | InsightFace `buffalo_sc` (~14 MB, se descarga automaticamente en el primer uso) |
| Umbral de similitud coseno | 0.40 (ajustable en `face_engine.py`) |
| Base de datos | SQLite con modo WAL |
| Intervalo anti-duplicado | 5 minutos por alumno |

---

## Configuracion avanzada

**Umbral de reconocimiento** — en `face_engine.py`, variable `UMBRAL_SIMILITUD`:
- Valor mayor (ej. 0.50) → mas permisivo, mayor tasa de aciertos pero mas falsos positivos
- Valor menor (ej. 0.30) → mas estricto, solo acepta coincidencias muy claras

**Intervalo anti-duplicado** — en `database.py`, funcion `insertar_asistencia()`, cambiar `timedelta(minutes=5)`.

---

## Solucion de problemas

| Problema | Causa probable | Solucion |
|---|---|---|
| Camara no abre | Otro proceso la usa o indice incorrecto | Cerrar otras apps (Teams, Zoom); probar otro indice en el selector |
| "No se detectaron camaras" | Drivers o permisos | Verificar en el Administrador de dispositivos; reconectar la camara |
| Rostro no reconocido | Pocas fotos o variacion insuficiente | Agregar mas fotos desde distintos angulos e iluminaciones |
| App lenta | CPU saturado | InsightFace usa CPU; cerrar apps pesadas en segundo plano |
| Error al importar insightface | No instalado | Ejecutar `python setup.py` o `pip install insightface onnxruntime` |
| Base de datos bloqueada | Otra instancia abierta | Cerrar la otra instancia de la app |
| Cache de encodings invalido | Fotos cambiadas manualmente | Eliminar `data/encodings_cache.pkl` y reiniciar |
