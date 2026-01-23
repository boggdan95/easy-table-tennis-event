# ETTEM - Easy Table Tennis Event Manager

## Project Overview

Aplicación Python para gestionar torneos de tenis de mesa:
- Inscripciones desde CSV o manualmente
- Motor deportivo (grupos RR → standings → llave KO)
- Panel web local para gestión completa
- Scheduler de mesas y horarios
- Ejecutable Windows standalone (PyInstaller)
- Sistema de licencias para distribución comercial
- Internacionalización ES/EN
- Windows-first, offline-first (SQLite)

## Estado Actual: V2.1.0 - Release Comercial

### ✅ Funcionalidades Completas

**Core (V1.0 - V1.1)**
- ✅ CLI completo con todos los comandos
- ✅ Motor deportivo (grupos RR → standings → bracket KO)
- ✅ Validación de sets y partidos (reglas ITTF)
- ✅ Gestión 100% desde UI web
- ✅ Importar jugadores (CSV + manual)
- ✅ Crear grupos con snake seeding y drag-and-drop
- ✅ Bracket automático y manual con validaciones ITTF
- ✅ Formato configurable por categoría (Bo3/Bo5/Bo7)

**Scheduler (V2.0)**
- ✅ Configuración de mesas y horarios
- ✅ Sesiones con time slots flexibles
- ✅ Asignación de partidos a mesa/hora
- ✅ Grid visual de asignaciones
- ✅ Finalizar/reabrir sesiones
- ✅ Impresión de scheduler

**Operación en Vivo (V2.1)**
- ✅ Live results panel
- ✅ Print center
- ✅ Sistema i18n completo (ES/EN)
- ✅ Tema claro/oscuro
- ✅ Ejecutable Windows (PyInstaller)
- ✅ **Sistema de licencias con claves firmadas**

### Sistema de Licencias

**Formato de clave:** `ETTEM-XXXX-MMYY-SSSSSSSS`
- XXXX: ID de cliente
- MMYY: Mes/año de expiración
- SSSSSSSS: Firma HMAC-SHA256

**Archivos (NO en repositorio remoto):**
- `tools/generate_license.py` - Generador de claves
- `LICENSE_ADMIN.md` - Guía de administración

**Generar licencia:**
```bash
python tools/generate_license.py --client XX01 --months 12
```

### Nomenclatura de Categorías (ITTF)

| Categoría | Descripción |
|-----------|-------------|
| U11BS / U11GS | Under 11 Boys/Girls Singles |
| U13BS / U13GS | Under 13 Boys/Girls Singles |
| U15BS / U15GS | Under 15 Boys/Girls Singles |
| U17BS / U17GS | Under 17 Boys/Girls Singles |
| U19BS / U19GS | Under 19 Boys/Girls Singles |
| U21BS / U21GS | Under 21 Boys/Girls Singles |
| MS / WS | Men's / Women's Singles |

### Ejecutable Windows

**Construir:**
```bash
python -m PyInstaller ettem.spec --clean --noconfirm
```

**Resultado:** `dist/ETTEM.exe` (~45 MB standalone)

**Características:**
- No requiere Python instalado
- Doble clic abre navegador automáticamente
- Base de datos en `.ettem/ettem.sqlite`
- Licencia en `.ettem/license.key`

### Arquitectura

```
src/ettem/
├── cli.py              # Comandos CLI
├── models.py           # Modelos de datos
├── storage.py          # Repositorios SQLite
├── licensing.py        # Sistema de licencias
├── validation.py       # Validación ITTF
├── i18n.py             # Internacionalización
├── paths.py            # Paths (dev/frozen)
└── webapp/
    ├── app.py          # FastAPI (~4500 líneas)
    ├── templates/      # Jinja2 templates
    └── static/         # CSS/JS
```

### Principios de Desarrollo

**Homologación de UI:**
- Si la misma información se muestra en múltiples vistas, DEBE verse igual en todas
- Ejemplo: Estado del partido (pending, in_progress, completed) debe usar los mismos badges/estilos en:
  - `/group/X/matches`
  - `/admin/live-results`
  - `/bracket/X/matches`
  - Cualquier otra vista que muestre partidos
- Cuando agregues un estado o estilo nuevo, buscar TODOS los lugares donde se usa y actualizarlos

**Vistas con datos en vivo:**
- Las páginas que muestran datos que pueden cambiar (resultados, estados) deben tener auto-refresh
- Usar JavaScript `setTimeout` con reload cada 10 segundos para vistas de monitoreo

### Comandos de Desarrollo

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar en desarrollo
python -m ettem open-panel

# Tests
pytest

# Lint
ruff check .
black .

# Construir ejecutable
python -m PyInstaller ettem.spec --clean --noconfirm
```

### CSV de Jugadores

Columnas requeridas:
- `id` - Identificador único
- `nombre` - Nombre
- `apellido` - Apellido
- `genero` - M o F
- `pais_cd` - Código ISO-3 (ESP, MEX, ARG, etc.)
- `ranking_pts` - Puntos de ranking (0 si no tiene)
- `categoria` - Categoría (U13BS, MS, etc.)

**Ejemplo:**
```csv
id,nombre,apellido,genero,pais_cd,ranking_pts,categoria
1,Juan,Perez,M,ESP,1200,U15BS
2,Maria,Garcia,F,ESP,1150,U15GS
3,Pedro,Lopez,M,MEX,0,U15BS
```

### Roadmap Futuro

- **V3.0:** Roles de usuario, multi-tenant, API REST
- **V3.1:** App móvil para árbitros
- **V4.0:** Torneos en la nube, rankings federativos

## Workflow de Git

- `main` - Código estable y probado
- `feature/*` - Nuevas funcionalidades

### Commits Recientes (V2.1)
- Sistema de licencias con claves firmadas HMAC
- Ejecutable PyInstaller para Windows
- i18n completo (ES/EN) con tema claro/oscuro
- CSVs de ejemplo con nomenclatura ITTF estándar

---

## Estado de Sesion (2026-01-22)

### Rama Actual
`feature/v2.2-live-display`

### Objetivo
Implementar V2.2: Pantalla Pública + Marcador de Árbitro

### Estado: PROBADO PARCIALMENTE - FALTA UI PUNTO POR PUNTO

### Pruebas Realizadas (2026-01-22)
- ✅ Ingreso de resultados desde teléfono (`/mesa/1`) - FUNCIONA
- ✅ Modo resultado por set - FUNCIONA
- ✅ Sincronización con servidor - FUNCIONA
- ✅ Estado `in_progress` homologado en todas las vistas
- ⏳ Modo punto por punto - UI PENDIENTE (requiere diseño diferente con +/-)

### Cambios de Hoy
- Homologación de estado `in_progress` con badge pulsante azul
- Fix caché i18n (clear on reload)
- Auto-refresh en vistas de partidos (10s)
- Fix referee_scoreboard: botón back, displays None, formato nombres
- Migración para categoría en partidos existentes

### Lo Implementado en V2.2

**1. Configuración de Mesas (`/admin/table-config`)**
- Inicializar y configurar mesas para el torneo
- Dos modos: `point_by_point` o `result_per_set`
- Generar códigos QR para cada mesa
- Activar/desactivar mesas
- Ver estado de bloqueo

**2. Marcador de Árbitro (`/mesa/{n}`)**
- Interfaz móvil optimizada
- Modo punto por punto con estado local
- Modo resultado por set
- Sincronización al servidor por set completado
- Soporte para walkover

**3. Pantalla Pública (`/display`)**
- Vista optimizada para TV/monitores
- Partidos en vivo con marcador actual
- Resultados recientes (últimos 10)
- Próximos partidos programados
- Auto-refresh cada 5 segundos
- Tema oscuro

**4. Sistema de Bloqueo de Mesas**
- Un dispositivo por mesa a la vez
- Bloqueo basado en sesión con cookies
- Admin puede desbloquear desde panel
- Timeout automático por inactividad

**5. API de Scores en Vivo**
- `GET /api/live-scores` - todos los partidos activos
- `POST /api/live-score/{id}` - actualizar score
- `POST /api/table/{id}/heartbeat` - mantener lock activo

### Archivos Nuevos/Modificados
```
src/ettem/storage.py                    # +3 ORM models, +3 repositories
src/ettem/webapp/app.py                 # +774 líneas (rutas V2.2)
src/ettem/webapp/templates/
├── admin_table_config.html             # Configuración de mesas
├── admin_table_qr_codes.html           # Imprimir QR codes
├── referee_scoreboard.html             # Marcador de árbitro
├── public_display.html                 # Pantalla pública
└── base.html                           # +link navegación
i18n/strings_es.yaml                    # +91 líneas traducciones
i18n/strings_en.yaml                    # +91 líneas traducciones
```

### Tests Automatizados
- 64 total: 63 passed, 1 skipped
- App importa sin errores
- Modelos de BD se crean correctamente

### Pruebas Manuales Pendientes
1. `/admin/table-config` - Configurar mesas, cambiar modos, QR
2. `/mesa/1` - Marcador de árbitro (ambos modos)
3. `/display` - Pantalla pública con partidos en vivo
4. Sistema de bloqueo - Abrir misma mesa en dos dispositivos
5. Sincronización - Puntos aparezcan en pantalla pública

### Cómo Probar
```bash
# Iniciar servidor (accesible desde red local)
python -m uvicorn ettem.webapp.app:app --host 0.0.0.0 --port 8000

# Encontrar IP local
ipconfig  # Windows
# Buscar IPv4 de WiFi (ej: 192.168.1.X)

# URLs para probar:
# PC: http://127.0.0.1:8000/admin/table-config
# PC: http://127.0.0.1:8000/display
# Celular: http://192.168.1.X:8000/mesa/1
```

### Siguiente Sesión
1. Probar manualmente las funcionalidades de V2.2
2. Corregir bugs encontrados
3. Merge a main
4. Crear release v2.2.0

### Licencia de Prueba
`ETTEM-DEV1-0127-BC7CF281` (expira enero 2027)

### Estado de Tests (64 total)
- Pasando: 63
- Skipped: 1 (determinismo de bracket - esperado)

### Sistema de Licencias
Verificado y funcionando correctamente:
- Licencias futuras: validas
- Licencias pasadas: expiradas con mensaje de error
- Expiracion: ultimo dia del mes (inclusive)

### Documentacion Existente
- `README.md` - Completo (tecnico)
- `LICENSE_ADMIN.md` - Completo (admin)
- `CLAUDE.md` - Completo (desarrollo)

### Documentacion Faltante
- `USER_GUIDE.md` - Manual para usuarios finales (organizadores)
- Capturas de pantalla (usuario agregara progresivamente)

### Como Ejecutar
```bash
cd "C:\Users\boggd\Documents\Boggdan - Projects\Code\projects\personal\easy-table-tennis-event"
python -m uvicorn ettem.webapp.app:app --host 127.0.0.1 --port 8000 --reload
```

### Licencia de Prueba
`ETTEM-DEV1-0127-BC7CF281` (expira enero 2027, 375 dias restantes)
