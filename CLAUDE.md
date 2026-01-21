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

## Estado de Sesion (2026-01-21)

### Rama Actual
`feature/mvp-preparation`

### Objetivo
Preparar ETTEM para release MVP comercial.

### Plan de Trabajo
Ver `MVP_PLAN.md` para el plan detallado.

### Tareas Principales
1. **Documentacion de Usuario** - Crear `USER_GUIDE.md`
2. **Tests** - Arreglar 16 tests fallidos (standings, i18n, validation)
3. **Limpieza** - Actualizar version, revisar TODOs
4. **Validacion** - Checklist pre-release

### Estado de Tests (64 total)
- Pasando: 48
- Fallando: 16
  - Standings: 3 (cambio en estructura de retorno)
  - i18n: 2 (keys renombradas)
  - Validation: 10 (formato de errores)
  - Bracket: 1 (determinismo)

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
