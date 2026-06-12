# Sistema de Asistencia por Reconocimiento Facial

Aplicación de escritorio nativa en Python que detecta e identifica rostros en tiempo real usando la cámara web, gestiona usuarios registrados, lleva un historial de detecciones y exporta listas de asistencia a Excel.

**Motor de IA:** InsightFace + ONNX — no requiere dlib, cmake ni Visual Studio.

---

## Inicio rápido (Windows)

```bat
cd face_attendance_system
run.bat
```

`run.bat` detecta si el entorno ya está configurado. Si no, ejecuta `setup.py` automáticamente y luego lanza la app.

---

## Instalación manual

### Requisitos del sistema

- **Python 3.10 o superior** (probado en Python 3.14 en Windows 10)
- **Cámara web** conectada
- **No se requiere** cmake, Visual Studio, dlib, ni TensorFlow

### 1. Diagnóstico previo (opcional)

```bash
python check.py
```

Muestra el estado de cada dependencia, cámaras detectadas, base de datos y modelos de IA. No instala nada.

Salida esperada:
```
=== Diagnóstico del Sistema de Asistencia Facial ===

Python:         ✓ 3.14.3
opencv-python:  ✓ 4.13.0
insightface:    ✓ 1.0.1
onnxruntime:    ✓ 1.20.0
Pillow:         ✓ 12.2.0
openpyxl:       ✓ 3.1.5
tkinter:        ✓ disponible

Cámaras detectadas: 1  (índices: 0)
Base de datos:  ✓ existe  (0 usuarios, 0 registros)
Modelos IA:     ✓ buffalo_sc descargado

Estado: LISTO para ejecutar. Usa: python main.py
```

### 2. Instalación automática con setup.py

```bash
python setup.py
```

Realiza 9 pasos automáticos:
1. Verifica versión de Python
2. Verifica pip
3. Crea entorno virtual en `venv/`
4. Instala dependencias desde `requirements.txt`
5. Verifica que cada paquete importa correctamente
6. Crea directorios necesarios (`data/users/`, `exports/`)
7. Inicializa la base de datos SQLite
8. Descarga modelos de InsightFace (~14 MB, solo la primera vez)
9. Muestra resumen y comando de inicio

### 3. Instalación manual paso a paso

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
python main.py
```

---

## Primer uso

### Registrar un usuario (captura manual)

1. Abre la pestaña **"Agregar Usuario"**
2. Selecciona la cámara en el selector desplegable
3. Ingresa **Nombre** y **Apellido**
4. Haz clic en **"▶ Iniciar Preview"** — verás el feed en vivo
5. Cuando aparezca el **recuadro azul** sobre tu rostro, haz clic en **"📸 Capturar Foto"**
6. Repite hasta tener ≥ 5 fotos (recomendado: 20, desde distintos ángulos e iluminaciones)
7. Haz clic en **"✅ Registrar Usuario"** — el usuario queda disponible de inmediato

> El botón "Capturar Foto" solo se habilita cuando hay un rostro detectado en el frame. Un flash blanco confirma que la foto se guardó.

### Reconocimiento en tiempo real

1. Abre la pestaña **"Vista en Vivo"**
2. Selecciona la cámara en el selector desplegable
3. Haz clic en **"▶ Iniciar Cámara"**
4. Rostros conocidos → recuadro **verde** con nombre
5. Rostros desconocidos → recuadro **rojo** con "No Identificado"
6. Las detecciones se registran automáticamente (máximo 1 vez por usuario cada 5 minutos)

### Cambiar de cámara

- El selector de cámara aparece en la barra superior de **Vista en Vivo** y de **Agregar Usuario**
- Usa el botón **"🔄"** para escanear nuevas cámaras conectadas
- El selector se deshabilita automáticamente mientras la cámara está activa

### Exportar asistencia a Excel

1. Abre la pestaña **"Últimas Detecciones"**
2. Selecciona el rango de fechas (formato `YYYY-MM-DD`)
3. Haz clic en **"📊 Exportar a Excel"**
4. El archivo `.xlsx` se guarda en `exports/` y se abre el explorador

---

## Estructura del proyecto

```
face_attendance_system/
│
├── main.py                   # Punto de entrada — ejecutar esto
├── database.py               # SQLite: tablas, índices, CRUD
├── face_engine.py            # InsightFace: encodings, caché, multi-cámara
├── export.py                 # Excel profesional con openpyxl
│
├── setup.py                  # Instalador automático paso a paso
├── check.py                  # Diagnóstico rápido sin instalar nada
├── run.bat                   # Lanzador Windows (configura + inicia)
├── run.sh                    # Lanzador Linux/macOS
├── requirements.txt          # Dependencias con versiones
│
├── ui/
│   ├── __init__.py
│   ├── main_window.py        # Ventana principal con pestañas
│   ├── camera_view.py        # Pestaña A: feed en vivo + selector multi-cámara
│   ├── recent_detections.py  # Pestaña B: historial + exportar Excel
│   └── add_user.py           # Pestaña C: captura manual con preview
│
├── data/
│   ├── users/                # Fotos de usuarios (subcarpeta por persona)
│   │   └── Juan_Perez/
│   │       ├── foto_001.jpg
│   │       └── ...
│   ├── attendance.db         # Base de datos SQLite
│   ├── encodings_cache.pkl   # Caché de embeddings faciales
│   └── app.log               # Log de la aplicación
│
└── exports/                  # Archivos Excel generados
    └── Asistencia_YYYY-MM-DD_HHmm.xlsx
```

---

## Flujo de datos

```
Cámara (OpenCV — multi-cámara)
     │
     ▼
face_engine.py ──── encodings_cache.pkl
     │   (InsightFace buffalo_sc ONNX)
     │ detección + embeddings
     ▼
ui/camera_view.py          ui/add_user.py
  (reconocimiento vivo)      (captura manual)
     │                           │
     │ detección confirmada       │ foto guardada manualmente
     ▼                           ▼
database.py (SQLite) ─── data/attendance.db
     │
     ├──▶ ui/recent_detections.py (polling cada 3s)
     │
     └──▶ export.py ──▶ exports/Asistencia_YYYY-MM-DD_HHmm.xlsx
```

---

## Soporte multi-cámara

El sistema detecta automáticamente las cámaras disponibles al iniciar cada pestaña:

- Prueba índices 0–5 con 3 backends en orden: `CAP_DSHOW` → `default` → `CAP_MSMF`
- Muestra resolución detectada: `"Cámara 0 - 640x480"`, `"Cámara 1 - 1280x720"`
- Se puede usar una cámara para reconocimiento (Pestaña A) y otra para registrar usuarios (Pestaña C) simultáneamente
- Botón "🔄 Actualizar cámaras" para detectar dispositivos conectados en caliente

---

## Configuración avanzada

### Umbral de reconocimiento
En [face_engine.py](face_engine.py), línea `UMBRAL_SIMILITUD = 0.40`:
- Valor **mayor** (ej: 0.50) → más permisivo, mayor tasa de aciertos pero más falsos positivos
- Valor **menor** (ej: 0.30) → más estricto, solo acepta coincidencias muy claras

### Intervalo anti-duplicado de asistencia
En [database.py](database.py), función `insertar_asistencia()`, cambiar `timedelta(minutes=5)`.

### Número de fotos por registro
En la pestaña "Agregar Usuario", el spinbox permite elegir entre 10 y 60 fotos. Se recomiendan ≥ 20 fotos desde distintos ángulos para mejor reconocimiento.

---

## Dependencias

| Paquete | Versión mínima | Uso |
|---|---|---|
| `opencv-python` | 4.8.0 | Captura de cámara, dibujo de bboxes |
| `insightface` | 1.0.0 | Detección y reconocimiento facial |
| `onnxruntime` | 1.16.0 | Ejecución de modelos ONNX |
| `Pillow` | 10.0.0 | Conversión de frames para Tkinter |
| `openpyxl` | 3.1.2 | Generación de archivos Excel |
| `pandas` | 2.0.0 | Procesamiento de datos tabulares |
| `tkinter` | (stdlib) | Interfaz gráfica de escritorio |
| `sqlite3` | (stdlib) | Base de datos local |

---

## Solución de problemas

| Problema | Causa probable | Solución |
|---|---|---|
| Cámara no abre | Otro proceso la usa o índice incorrecto | Cerrar otras apps (Teams, Zoom); probar otro índice en el selector |
| "No se detectaron cámaras" | Drivers o permisos | Verificar en el Administrador de dispositivos; reconectar la cámara |
| Rostro no reconocido | Pocas fotos o variación insuficiente | Agregar más fotos desde distintos ángulos e iluminaciones |
| App lenta al procesar | CPU saturado | InsightFace usa CPU; cerrar apps pesadas en segundo plano |
| Error al importar insightface | No instalado | Ejecutar `python setup.py` o `pip install insightface onnxruntime` |
| Base de datos bloqueada | Otra instancia abierta | Cerrar la otra instancia de la app |
| Caché de encodings inválido | Fotos cambiadas manualmente | Eliminar `data/encodings_cache.pkl` y reiniciar |

---

## Desarrollo

Para ejecutar sin entorno virtual (si las dependencias están en el sistema):
```bash
python main.py
```

Para ver logs en tiempo real:
```bash
# El log se escribe en data/app.log
# También se imprime en consola al ejecutar desde terminal
```
