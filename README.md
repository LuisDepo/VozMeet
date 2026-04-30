# VozMeet 🎙️

**Transcriptor inteligente de reuniones con identificación persistente de voces.**

VozMeet convierte grabaciones de Microsoft Teams, Zoom u otras plataformas en transcripciones completas con el nombre real de cada participante — todo de forma **100% local**, sin enviar ningún dato a internet.

---

## ¿Qué hace VozMeet?

1. **Sube** una grabación MP3 o MP4 de tu reunión
2. **Detecta** automáticamente cuántas personas hablan (diarización)
3. **Transcribe** el audio con reconocimiento de voz de alta precisión (Whisper large-v3)
4. **Identifica** las voces comparándolas con perfiles guardados
5. **Aprende** con cada grabación — mejora el reconocimiento con el tiempo
6. **Exporta** transcripciones listas para usar en Google NotebookLM

---

## Requisitos del sistema

| Requisito | Detalle |
|-----------|---------|
| Sistema operativo | macOS 12 Monterey o superior |
| Chip | Apple Silicon (M1/M2/M3) o Intel |
| RAM | Mínimo 8 GB (recomendado 16 GB) |
| Espacio en disco | ~6 GB libres para los modelos de IA |
| Conexión a internet | Solo en la instalación inicial |

---

## ⚠️ IMPORTANTE: Dónde instalar

**VozMeet debe estar en `~/VozMeet/`** — es decir, directamente en tu carpeta de inicio.

**NUNCA lo instales en iCloud Drive** (como `~/Library/Mobile Documents/` o `~/iCloud Drive/`). iCloud Drive interfiere con el sandbox de macOS y causa errores al ejecutar la app.

Si descargaste el proyecto en otro lugar, muévelo:

```bash
mv ~/Downloads/VozMeet ~/VozMeet
cd ~/VozMeet && ./install.sh
```

---

## Token gratuito de HuggingFace

VozMeet usa el modelo de diarización `pyannote/speaker-diarization-3.1`, que requiere un token gratuito de HuggingFace.

### Cómo obtenerlo (5 minutos):

1. **Crea una cuenta gratuita** en [https://huggingface.co/join](https://huggingface.co/join)

2. **Obtén un token de tipo "Read"** en [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
   - Haz click en "New token"
   - Nombre: `vozmeet` (o cualquiera)
   - Tipo: **Read**
   - Copia el token (empieza con `hf_...`)

3. **Acepta los términos** de los modelos (obligatorio, gratis):
   - [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) → click en "Agree and access repository"
   - [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0) → click en "Agree and access repository"

4. **El instalador te pedirá el token** — solo pégalo cuando lo solicite.

---

## Instalación

```bash
# 1. Asegúrate de estar en ~/VozMeet
cd ~/VozMeet

# 2. Dale permisos al instalador
chmod +x install.sh

# 3. Ejecuta el instalador (sigue las instrucciones en pantalla)
./install.sh
```

El instalador:
- Instala Homebrew (si no está)
- Instala Python 3.11+ y ffmpeg
- Crea el entorno virtual Python
- Instala todas las dependencias
- Descarga los modelos de IA (~6 GB, una sola vez)
- Construye `VozMeet.app`
- Ofrece instalarlo en `/Applications`

---

## Uso

### Abrir la app

- **Doble click** en `VozMeet.app` (en la carpeta `~/VozMeet/`)
- O desde Launchpad / Finder si la instalaste en `/Applications`

No necesitas abrir Terminal. La app se abre como cualquier otra app de macOS.

### Guía rápida (5 pasos)

**Paso 1 — Seleccionar grabación**
Arrastra un archivo MP3 o MP4 a la ventana, o haz click en "Seleccionar archivo".

**Paso 2 — Procesar**
Haz click en "Procesar grabación →". Verás el progreso en tiempo real:
- Extracción de audio
- Transcripción con Whisper
- Identificación de hablantes con pyannote
- Generación de huellas vocales

*(La primera vez puede tardar 5-15 minutos. Las siguientes veces son más rápidas.)*

**Paso 3 — Identificar voces**
Para cada voz detectada:
- Reproduce la muestra de 8 segundos con el botón ▶
- Si VozMeet reconoce la voz (≥75% confianza), confirma con un click
- Si no la reconoce, escribe el nombre de la persona
- La próxima vez que aparezca esa voz, se identificará automáticamente

**Paso 4 — Ver la transcripción**
- Navega por el texto con timestamps
- Filtra por participante
- Busca palabras clave

**Paso 5 — Exportar**
Descarga la transcripción en el formato que necesites:
- **TXT**: formato limpio para NotebookLM
- **Markdown**: para Notion, Obsidian, etc.
- **JSON**: para procesamiento programático

---

## Usar con Google NotebookLM

1. Exporta la transcripción en formato **TXT**
2. Ve a [notebooklm.google.com](https://notebooklm.google.com)
3. Crea un nuevo notebook o abre uno existente
4. Haz click en "+ Agregar fuente" → "Subir archivo"
5. Selecciona el archivo `.txt` exportado por VozMeet
6. ¡Listo! Ahora puedes hacer preguntas sobre tu reunión

---

## Historial y perfiles

- **Historial**: Accede a todas las grabaciones procesadas desde el panel izquierdo
- **Perfiles de voz**: Edita los nombres de las personas registradas. Los cambios se reflejan en todas las transcripciones asociadas
- Los perfiles mejoran automáticamente con cada nueva grabación de la misma persona

---

## Solución de problemas

### La app no abre con doble click
```bash
# Quitar atributo de cuarentena manualmente:
xattr -dr com.apple.quarantine ~/VozMeet/VozMeet.app
```

### Error "Token HuggingFace inválido"
1. Verifica que el token sea de tipo "Read" (no "Write" ni "Fine-grained")
2. Verifica que aceptaste los términos en ambos modelos pyannote
3. Genera un token nuevo en [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
4. Edita `~/VozMeet/.env` y reemplaza el token

### Error "ffmpeg no está instalado"
```bash
brew install ffmpeg
```

### La transcripción es incorrecta en español
VozMeet usa detección automática de idioma. Si la grabación tiene mucho ruido de fondo o el audio es de baja calidad, la precisión puede bajar. Whisper large-v3 tiene muy buena precisión para español.

### El proceso se interrumpió a mitad
Al reabrir la app y entrar al historial, las grabaciones interrumpidas aparecen con estado "Procesando". Puedes eliminarlas y volver a subirlas.

### pywebview no funciona
```bash
cd ~/VozMeet
.venv/bin/pip install --upgrade pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-WebKit pywebview
```

---

## Privacidad

🔒 **VozMeet es 100% local.**

- Tus grabaciones **nunca salen de tu Mac**
- Los modelos de IA se descargan una sola vez y funcionan sin internet
- La base de datos de voces se guarda solo en `~/VozMeet/data/vozmeet.db`
- No hay telemetría, no hay analytics, no hay conexiones a servidores externos

---

## Estructura del proyecto

```
~/VozMeet/
├── install.sh          # Instalador automático
├── requirements.txt    # Dependencias Python
├── .env                # Tu token HuggingFace (privado, no en git)
├── app/
│   ├── core/           # Audio, transcripción, diarización, embeddings
│   ├── database/       # SQLite: voces, grabaciones, segmentos
│   ├── api/            # Endpoints FastAPI
│   ├── static/         # Interfaz web (HTML/CSS/JS estilo Apple)
│   ├── main.py         # Servidor FastAPI
│   └── launcher.py     # Abre ventana nativa macOS
├── data/               # Base de datos y archivos procesados
└── VozMeet.app/        # Bundle macOS generado por install.sh
```

---

## Créditos tecnológicos

| Tecnología | Uso |
|-----------|-----|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Transcripción de voz (Whisper large-v3) |
| [pyannote.audio](https://github.com/pyannote/pyannote-audio) | Diarización de hablantes |
| [SpeechBrain ECAPA-TDNN](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb) | Huellas vocales |
| [FastAPI](https://fastapi.tiangolo.com) | Servidor interno |
| [pywebview](https://pywebview.flowrl.com) | Ventana nativa macOS |
| [ffmpeg](https://ffmpeg.org) | Procesamiento de audio/video |

---

*VozMeet — Hecho para equipos que valoran su privacidad.*
