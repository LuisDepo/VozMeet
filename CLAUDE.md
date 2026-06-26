# CLAUDE.md — VozMeet

**Status:** active (app funcional e instalable)
**Goal (una línea):** Transcriptor 100% local de reuniones, con identificación
persistente de voces, exportable a NotebookLM.

---

## Context
App de escritorio para macOS (Python/FastAPI + ventana nativa con pywebview). Toma una
grabación MP3/MP4 (Teams, Zoom, etc.), detecta cuántas personas hablan (diarización),
transcribe con Whisper large-v3, identifica cada voz contra perfiles guardados y exporta
la transcripción (TXT/Markdown/JSON). Todo corre localmente, sin enviar datos a internet.

Stack: faster-whisper / mlx-whisper (transcripción), pyannote.audio 3.1 (diarización),
SpeechBrain ECAPA-TDNN (huellas vocales), FastAPI (servidor interno), SQLite (perfiles),
pywebview (ventana nativa), ffmpeg.

## Ubicación y duplicación (LEER — hay dos copias)
- **Código fuente real = ESTA carpeta:** `~/AppsBMS/VozMeet/VozMeet-claude-vozmeet-macos-app-EOB7u/`
  (local, **NO en iCloud** — el README advierte explícitamente no instalarlo en iCloud
  porque rompe el sandbox de macOS).
- En **iCloud** (`IA/Claude Apps/VozMeet/`) viven solo los *prompts* y el diseño, no el código.
- **Respaldos:** repo git local (creado 2026-06-26) + zip en la USB de migración
  (`Claude-Migracion-2026-06-26`). **Falta:** crear repo privado en GitHub y `git push`.

## Current state / where I left off
[archivo] App construida y funcional: `install.sh` arma el entorno, descarga modelos
(~6 GB) y genera `VozMeet.app`. README completo con instalación, uso y troubleshooting.
[2026-06-26] Se inicializó git local y se creó este CLAUDE.md. Pendiente: remoto en GitHub.

## Key files in this folder
- `app/main.py` — servidor FastAPI
- `app/core/` — audio, transcripción, diarización, embeddings de voz
- `app/database/` — SQLite (voces, grabaciones, segmentos)
- `app/api/` — endpoints
- `app/static/` — interfaz web (estilo Apple)
- `app/launcher.py` — abre la ventana nativa macOS
- `install.sh` / `build_dmg.sh` — instalador y empaquetado
- `requirements.txt` — dependencias Python
- `.env` — token de HuggingFace (privado, **fuera de git**); plantilla en `.env.example`
- `README.md` — documentación completa (autoritativa)

## Decisions & constraints
- [archivo] **100% local, sin telemetría.** Las grabaciones nunca salen del Mac.
- [archivo] Requiere un token **Read** de HuggingFace para pyannote → va en `.env` (gitignored).
- [archivo] **No instalar en iCloud Drive** (rompe el sandbox). El README sugiere `~/VozMeet/`.
- [archivo] Modelos (~6 GB) se descargan en la instalación; no van a git.
- [archivo] Datos de usuario (`data/`: grabaciones, transcripciones, `vozmeet.db`) son
  privados y están en `.gitignore`.

## Next steps
- [ ] Crear repo **privado** en GitHub y hacer el primer `push` (igual que `lottery-checker`).
- [ ] Decidir la ruta canónica: dejarlo en `~/AppsBMS/...` o moverlo a `~/VozMeet/`
      (lo que asume el README y los scripts).

---

*Hereda las reglas de trabajo, idioma y directorios protegidos del `CLAUDE.md` raíz de
`Claude Cowork Personal/`. No se repiten aquí.*
