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

## Reglas de Testing (OBLIGATORIAS)

- **SIEMPRE correr pruebas E2E completas con Playwright browser**, nunca solo unit tests
- **Flujo COMPLETO**: import → groups → matches → results → standings → bracket → champion
- **Verificar CADA paso visualmente** en el navegador — no asumir que funciona
- **Para equipos**: verificar encuentro con partidos individuales
- **NO usar curl para E2E** — usar Playwright browser
- **Limpiar cache Playwright si hay problemas**: `rm -rf ~/Library/Caches/ms-playwright/mcp-chromium-*`
- Después de cada cambio significativo, levantar el servidor y validar en browser

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

### Ejecutable (Windows + macOS)

**Construir:**
```bash
python build.py --clean
# O directamente:
python -m PyInstaller ettem.spec --clean --noconfirm
```

**Resultado:**
- Windows: `dist/ETTEM.exe` (~45 MB standalone)
- macOS: `dist/ETTEM.app` (bundle)

**Características:**
- No requiere Python instalado
- Doble clic abre navegador automáticamente
- Un solo `ettem.spec` cross-platform (detecta OS automáticamente)

**Datos de usuario:**
- Windows: `.ettem/` junto al ejecutable
- macOS (frozen): `~/Library/Application Support/ETTEM/`
- Dev mode (cualquier OS): `.ettem/` en directorio actual

**Nota macOS:** Para distribución sin warnings de Gatekeeper, firmar con Apple Developer ID ($99/año)

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

# Construir ejecutable (detecta OS automáticamente)
python build.py --clean
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

## Estado de Sesion (2026-02-07)

### Rama Actual
`main`

### Estado: V2.2 RELEASE COMPLETO + DOCUMENTACION COMPLETA

### Releases
- **v2.2.0** - Taggeado y pusheado (2026-02-06)
- Feature branch `feature/v2.2-live-display` mergeado a main
- Documentation branch `docs/v2.2-documentation` mergeado a main

### Landing Page en Vivo
- URL: http://ettem.boggdan.com
- Hosting: Bluehost (carpeta `website_157ed56a`)
- Contacto: ettem@boggdan.com

### Precios Definidos
- Mensual: $29 USD/mes
- Semestral: $22 USD/mes (pago unico $132 USD)
- Anual: $18 USD/mes (pago unico $216 USD)
- Soporte opcional: $10 USD/mes adicional
- Estrategia: price anchoring (equivalente mensual grande, total abajo)

### Documentacion Completa (en docs/)
- `landing_page.html` - Landing page profesional (HTML single-file)
- `ETTEM_Brochure.pdf` - PDF pixel-perfect desde landing page
- `SALES_BROCHURE.md` - Documento comercial fuente
- `SALES_BROCHURE.docx` - Version Word editable
- `CAPABILITIES.md` - Funcionalidades (client-safe, sin info interna)
- `TECHNICAL_GUIDE.md` - Arquitectura, BD, API reference
- `USER_GUIDE.md` - Manual de usuario final
- `MVP_PLAN.md` - Plan original del MVP
- `ettem_website.zip` - ZIP listo para deploy en hosting
- `screenshots/` - 24 screenshots + landing previews

### Tests (64 total)
- Pasando: 63
- Skipped: 1 (determinismo de bracket - esperado)
- Nota: test_webapp_smoke.py puede fallar por PIL/Pillow incompatible con Python 3.14

### Licencia de Prueba
`ETTEM-DEV1-0127-BC7CF281` (expira enero 2027)

### Sistema de Licencias
Verificado y funcionando correctamente:
- Licencias futuras: validas
- Licencias pasadas: expiradas con mensaje de error
- Expiracion: ultimo dia del mes (inclusive)

### Como Ejecutar
```bash
cd "C:\Users\boggd\Documents\Boggdan - Projects\Code\projects\personal\easy-table-tennis-event"
python -m uvicorn ettem.webapp.app:app --host 127.0.0.1 --port 8000 --reload
```

### Pruebas Manuales Pendientes
1. Sistema de bloqueo de mesas (2 dispositivos simultaneos)
2. Walkover completo desde marcador

### Siguiente Sesion
1. **BUILD macOS** (ver instrucciones abajo)
2. Considerar V2.3 segun ROADMAP.md (Roles de usuario, mejoras UX)
3. Probar bloqueo de mesas y walkover pendientes
4. Buscar clientes potenciales con landing page

---

## BUILD macOS - Instrucciones para crear ejecutable

### Contexto
El codigo ya es 100% cross-platform. Los cambios necesarios ya estan en la rama `feature/macos-support`:
- `paths.py` detecta macOS y usa `~/Library/Application Support/ETTEM/` para datos
- `launcher.py` maneja SIGTERM para cierre limpio del .app
- `ettem.spec` es cross-platform (detecta OS, genera .exe o .app segun corresponda)
- `build.py` script unificado para construir

### Pasos en la Mac

```bash
# 1. Clonar repo
git clone <repo-url>
cd easy-table-tennis-event
git checkout feature/macos-support

# 2. Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt
pip install pyinstaller

# 4. Verificar que funciona desde codigo fuente
python -m pytest --ignore=tests/test_webapp_smoke.py
python -m uvicorn ettem.webapp.app:app --host 127.0.0.1 --port 8000
# Abrir http://127.0.0.1:8000 - verificar que todo funciona

# 5. Construir .app
python build.py --clean
# Resultado esperado: dist/ETTEM.app

# 6. Probar el .app
open dist/ETTEM.app
# Debe abrir navegador automaticamente
# Verificar que la BD se crea en ~/Library/Application Support/ETTEM/
# Probar: crear torneo, importar jugadores, crear grupos

# 7. Licencia de prueba
# ETTEM-DEV1-0127-BC7CF281 (expira enero 2027)
```

### Que verificar en la Mac
- [ ] Tests pasan (`pytest --ignore=tests/test_webapp_smoke.py`)
- [ ] App desde codigo fuente funciona (`python -m uvicorn ...`)
- [ ] `build.py --clean` genera `dist/ETTEM.app` sin errores
- [ ] Doble clic en ETTEM.app abre el navegador
- [ ] Base de datos se crea en `~/Library/Application Support/ETTEM/ettem.sqlite`
- [ ] Licencia funciona (activar con clave de prueba)
- [ ] Crear torneo completo: importar CSV, grupos, partidos, standings, bracket
- [ ] QR codes y marcador de arbitro funcionan desde celular en red local

### Problemas conocidos
- **Gatekeeper**: macOS puede bloquear la app por no estar firmada. Solucion temporal: `xattr -cr dist/ETTEM.app` o abrir desde Finder con clic derecho > Abrir
- **Icono**: No hay icono .icns todavia. La app funciona sin el, pero se vera con icono generico
- **Python 3.14**: Si usas Python 3.14, `test_webapp_smoke.py` falla por incompatibilidad pycparser/cffi. Usar `--ignore=tests/test_webapp_smoke.py`
- **Apple Silicon**: El spec usa `target_arch=None` (nativo). Para universal binary cambiar a `target_arch='universal2'`

### Despues del build exitoso
1. Merge `feature/macos-support` a `main`
2. Crear release v2.2.1 con ambos ejecutables (ETTEM.exe + ETTEM.app)
3. (Opcional) Firmar con Apple Developer ID para distribucion profesional ($99/año)
