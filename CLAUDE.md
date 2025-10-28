Crea un repositorio en Python llamado `easy-tt-event-manager` (V1 sin scheduler). 
Propósito: gestionar un evento de tenis de mesa (Singles) con inscripciones, construcción de grupos (round robin), standings con desempates, generación de llave (KO) y un panel local para ingresar resultados manualmente. 
No implementes aún asignación horaria/mesas (scheduler); deja hooks para V1.1.

## Project Overview
Easy Table Tennis Event — aplicación Python para gestionar torneos/eventos de tenis de mesa:
- Inscripciones desde CSV
- Motor deportivo (grupos RR → standings → llave KO)
- Panel local para ingresar resultados
- Exportables (CSV) para comunicación/operación
- Internacionalización ES/EN
- Windows-first, offline-first (SQLite)

## Development Setup (multi-herramienta)
El repo debe permitir trabajar con cualquiera de estos gestores (sin casarte con uno):
- pip (`requirements.txt`)
- poetry (`pyproject.toml`, `poetry.lock`)
- pipenv (`Pipfile`, `Pipfile.lock`)
- uv / pdm (soporte opcional)

Incluye:
- `.gitignore` listo para .venv y artefactos
- Instrucciones de entorno virtual en README
- Sección de “Common Commands” (pytest, ruff/flake8, black/ruff format)

## Alcance funcional (V1)
1) **Inscripciones**
   - Importar desde CSV con columnas: `id, nombre, apellido, genero, pais_cd, ranking_pts, categoria`
   - V1 trabaja sobre **una sola categoría** (filtrable por `--category`)
   - Validaciones básicas (campos obligatorios, genero M/F, ISO-3 en `pais_cd`, ranking numérico)

2) **Grupos (Round Robin)**
   - Crear grupos con `group_size_preference` en {3,4}; si N no cuadra, mezclar (preferir más grupos de 4 que de 3)
   - Distribución de seeds en “serpiente” (snake)
   - Generación de fixture RR por grupo con método del círculo (función genérica N>=3)

3) **Resultados y Standings**
   - Ingreso **manual** de resultados en panel local (nada de CSV en V1)
   - Puntuación:
     - victoria = 2 pts
     - derrota (jugado) = 1 pt
     - walkover (perdedor) = 0 pt (el ganador cuenta victoria)
   - Métricas por jugador: wins, losses, sets_w, sets_l, points_w, points_l, points_total
   - **Desempate de ≥3 empatados (solo entre los empatados)**:
     1) `sets_ratio = sets_w / sets_l` (si sets_l=0 → tratar como infinito/valor máximo)
     2) Si persiste: `points_ratio = points_w / points_l` (si points_l=0 → infinito/valor máximo)
     3) Si persiste: desempatar por `seed` ascendente (criterio determinista)

4) **Llave (Knockout)**
   - Tamaño = siguiente potencia de 2 ≥ clasificados (primeros y segundos de grupo)
   - Posiciones:
     - G1: tope del cuadro (slot 1)
     - G2: fondo del cuadro (último slot)
     - Resto de primeros: **sorteo** en slots predefinidos (usar `random_seed` para determinismo)
     - Segundos: a **mitad opuesta** de su primero; intentar evitar mismo cuarto si cabe
   - **Anotaciones** (no bloqueantes): marcar cruce de 1R con **mismo país** para revisión humana
   - Rellenar con **BYEs** si corresponde
   - Exportar `knockout_bracket.csv` con estructura por rondas (R16/QF/SF/F)

5) **Panel local (web app minimal)**
   - FastAPI + Jinja2 (o Starlette + Jinja2): 
     - Ver grupos y partidos
     - Form de carga de resultados (sets/puntos, flags `played`/`walkover`)
     - Botón “Recalcular standings”
   - Persistencia en **SQLite** (archivo en `.ettem/ettem.sqlite`)

6) **Internacionalización (i18n)**
   - Strings centralizados en `i18n/strings_es.yaml` y `i18n/strings_en.yaml`
   - Selección por flag CLI `--lang es|en` (y variable de entorno)

7) **CLI**
   - `ettem import-players --csv path.csv --category U13`
   - `ettem build-groups --config config.yaml --out out/`
   - `ettem open-panel`  # lanza http://127.0.0.1:8000
   - `ettem compute-standings --out out/`  # idem desde UI
   - `ettem build-bracket --out out/`
   - `ettem export --what groups|standings|bracket --format csv --out out/`
   - Todas las operaciones usan SQLite como estado fuente de la verdad

8) **Configuración**
   - `config/sample_config.yaml` con:
     - `random_seed`
     - `group_size_preference: 4`
     - `advance_per_group: 2`
     - `lang: es` (por defecto)
     - (nota: scheduler no está en V1; dejar `scheduling: {enabled: false}` como hook)

9) **Calidad**
   - Python 3.11+
   - Lint/format: ruff + black (o ruff format), flake8 opcional
   - Type hints + mypy (nivel básico)
   - Tests con pytest:
     - grupos con mezcla 3/4 + serpiente
     - triple empate (≥3) con ratios “solo entre empatados”
     - bracket con G1 top, G2 bottom, sorteos deterministas, BYEs
     - smoke test de webapp (ruta `/` responde 200)

## Estructura del repo
easy-tt-event-manager/
├─ README.md
├─ .gitignore
├─ requirements.txt            # mínimo viable (FastAPI/Jinja2/SQLAlchemy o equivalente, pydantic, pytest, ruff, black)
├─ pyproject.toml              # (si usas poetry/ruff/black/mypy)
├─ Pipfile                     # (opcional)
├─ config/
│  └─ sample_config.yaml
├─ data/
│  └─ samples/
│     ├─ players.csv
│     └─ results_fixture.csv   # solo de ejemplo; en V1 ingresar manualmente
├─ i18n/
│  ├─ strings_es.yaml
│  └─ strings_en.yaml
├─ src/
│  └─ ettem/
│     ├─ __init__.py
│     ├─ cli.py
│     ├─ models.py             # Player, Match, Group, GroupStanding, Bracket, Bye (dataclasses / pydantic)
│     ├─ storage.py            # repos SQLite: players, groups, matches, results, standings
│     ├─ group_builder.py
│     ├─ standings.py
│     ├─ bracket.py
│     ├─ io_csv.py             # import/export CSV
│     ├─ config_loader.py      # YAML + validaciones
│     ├─ i18n.py               # helpers de traducción
│     └─ webapp/
│        ├─ app.py             # FastAPI + rutas + inyección de storage
│        ├─ templates/
│        │  ├─ base.html
│        │  ├─ groups.html
│        │  ├─ matches.html
│        │  └─ standings.html
│        └─ static/
│           └─ styles.css
└─ tests/
   ├─ test_groups.py
   ├─ test_standings.py
   ├─ test_bracket.py
   ├─ test_storage.py
   └─ test_webapp_smoke.py

## Common Commands (README)
- Crear venv:
  - Linux/Mac: `python -m venv .venv && source .venv/bin/activate`
  - Windows: `.venv\Scripts\activate`
- Instalar deps:
  - pip: `pip install -r requirements.txt`
  - poetry: `poetry install`
  - pipenv: `pipenv install`
- Tests:
  - `pytest`
  - `pytest tests/test_standings.py::test_triple_tie`
- Lint/format:
  - `ruff check .`
  - `black .`  (o `ruff format .`)

## Documentación (README + docstrings)
- CSV de inscripciones (columnas/validaciones y ejemplo)
- Reglas de puntos (2/1/0) y **desempate ≥3** (ratios “solo entre empatados”, manejo de divisiones por cero)
- Política de cuadro (G1 top, G2 bottom, segundos mitad opuesta, BYEs, anotaciones por mismo país)
- Flujo recomendado:
  1) `import-players`
  2) `build-groups`
  3) `open-panel` (ingresar resultados)
  4) `compute-standings`
  5) `build-bracket`
  6) `export`

## Roadmap

Ver archivo **MVP_ROADMAP.md** para roadmap detallado y completo.

**Resumen:**
- **V1.1.1 (MVP):** Vista de resultados finales y podio → Correr evento completo
- **V1.2:** Mejoras de usabilidad (editar jugadores, eliminar categorías, etc.)
- **V1.3:** Exportación e impresión (PDFs, certificados, hojas de grupo)
- **V1.4:** Múltiples categorías simultáneas
- **V2.0:** Scheduler/asignación de mesas y horarios
- **V2.1:** Operación en vivo (displays, notificaciones, panel de mesa)
- **V3.0:** Funcionalidades avanzadas (roles, multi-tenant, API, app móvil)

---

## Estado Actual del Proyecto (V1.1.0 - Gestión Completa desde UI)

### ✅ Completado (V1.0.0 - V1.1.0)

**V1.0.0 - Core Funcional**
- ✅ CLI completo con todos los comandos
- ✅ Motor deportivo (grupos RR → standings → bracket KO)
- ✅ Validación de sets y partidos (reglas ITTF)
- ✅ Base de datos SQLite con ORM
- ✅ Tests completos (grupos, standings, bracket, validación)

**V1.0.1 - Edición de Resultados**
- ✅ Editar/eliminar resultados de partidos
- ✅ Validación de scores de tenis de mesa
- ✅ Módulo de validación completo (`validation.py`)

**V1.0.2 - Internacionalización y UI Moderna**
- ✅ Sistema de i18n con archivos YAML (ES/EN)
- ✅ Comando `export` para grupos/standings/bracket a CSV
- ✅ Strings traducidos en español/inglés

**V1.0.2 - UI Moderna**
- ✅ **Interfaz moderna con sidebar navegable**
  - Diseño profesional con CSS moderno (variables, gradientes, sombras)
  - Sidebar con navegación por categorías
  - Topbar con selector de idioma
  - Sistema de cards, badges, alerts, toasts

- ✅ **JavaScript interactivo**
  - Sistema de notificaciones toast (success/error/warning/info)
  - Validación de formularios
  - Confirmaciones de acciones
  - Navegación activa resaltada

- ✅ **Templates completamente rediseñados**
  - `index.html` - Dashboard con stats y acciones
  - `category.html` - Vista de categoría con cards de grupos
  - `group_matches.html` - Tabla moderna de partidos
  - `enter_result.html` - Formulario horizontal de ingreso de sets
  - `standings.html` - Clasificación con medallas y badges
  - `bracket.html` - Visualización de llave eliminatoria
  - `group_sheet.html` - Matriz de resultados

- ✅ **Mejoras UX**
  - Errores de validación como toast popups (no page redirects)
  - Mensajes completamente en español
  - Valores del formulario se preservan en caso de error
  - Inputs numéricos sin flechas (spinners)
  - Tab order vertical en formulario de sets
  - Botones con solo íconos (tooltips para descripción)
  - Flash messages con SessionMiddleware

**V1.1.0 (Actual) - Gestión Completa desde UI**
- ✅ **Importar Jugadores** 📥
  - Upload de archivos CSV con validación
  - Formulario manual para agregar jugadores individualmente
  - Validación en tiempo real (género, país ISO-3, ranking)
  - Preview de jugadores importados
  - Auto-asignación de seeds

- ✅ **Crear Grupos** 👥
  - Página de configuración con selector de categoría
  - Configuración de tamaño preferido (3 o 4 jugadores)
  - Preview dinámico de distribución de grupos con serpenteo (snake seeding)
  - Drag-and-drop para ajustes manuales en preview
  - Random seed configurable para reproducibilidad
  - Eliminación de grupos existentes y creación de nuevos
  - **FIX (2025-10-28):** Corregido error al crear grupos desde preview modal
    * Ahora asigna correctamente group_number a jugadores en asignaciones manuales
    * Implementada generación de partidos usando generate_round_robin_fixtures()

- ✅ **Calcular Standings** 📊
  - Recalcular todas las categorías de una vez
  - Calcular por categoría individual
  - Vista previa de clasificaciones actuales
  - Notificaciones de éxito/error con toast
  - Redirección automática a vista de categoría

- ✅ **Generar Bracket** 🏅
  - Configuración de clasificados por grupo (1º, 1º-2º, 1º-2º-3º)
  - Preview de tamaño de bracket y BYEs
  - Random seed para sorteo de posiciones
  - Vista previa de jugadores clasificados
  - Generación automática y guardado de bracket en base de datos

- ✅ **Bracket Manual con Drag-and-Drop** 🎯
  - Interfaz completa de drag-and-drop para posicionamiento manual de jugadores
  - Listas separadas de 1º y 2º lugar ordenadas por grupo (G1, G2, G3...)
  - Arrastre desde listas hacia slots del bracket
  - Arrastre entre slots (mover/intercambiar jugadores dentro del bracket)
  - BYEs pre-colocados según reglas ITTF (posiciones exactas por cantidad de grupos)
  - Validaciones estrictas:
    * Prevención de jugadores duplicados
    * Error bloqueante si mismo grupo en misma mitad del bracket
    * Advertencia (no bloqueante) para mismo país
  - Preservación de formulario en errores de validación
  - Badges visuales con grupo de cada jugador
  - BYEs bloqueados (no se pueden mover ni eliminar)
  - Reglas ITTF implementadas:
    * 3 grupos (6 jugadores) → Bracket 8 → BYEs en [2, 7]
    * 5 grupos (10 jugadores) → Bracket 16 → BYEs en [2, 6, 7, 10, 11, 15]
    * ... hasta 20 grupos con posiciones predefinidas

### 🚧 Próxima Sesión (V1.1.1 - Completar MVP)

**OBJETIVO: Correr un evento completo de 1 categoría de principio a fin**

**Estado Actual (2025-10-28):**
- ✅ Fix aplicado a creación de grupos con preview modal
- ✅ Commit realizado: `4366ea4 Fix group creation with manual assignments from preview`
- ⚠️ **Pendiente:** Probar flujo completo de creación de grupos desde UI con preview

**Tareas Críticas para MVP:**
1. **Testing de Creación de Grupos** (PRÓXIMO)
   - Probar creación directa sin preview
   - Probar creación con preview y sin drag-and-drop
   - Probar creación con preview y drag-and-drop de jugadores
   - Verificar que group_number se asigna correctamente
   - Verificar que los partidos se generan correctamente

2. **Vista de Resultados Finales** (`/category/{category}/results`)
   - Mostrar campeón (ganador de Final)
   - Mostrar podio completo (1°, 2°, 3°/4°)
   - Mostrar clasificación final de bracket
   - Navegación desde página de categoría

3. **Mejoras UX para Completar Torneo:**
   - Botón "Ver Resultados Finales" en navbar cuando bracket está completo
   - Indicador de progreso del torneo (Grupos → Bracket → Finalizado)
   - Badge de "CAMPEÓN" en vista de bracket cuando hay ganador

4. **Testing End-to-End:**
   - Test manual de flujo completo (12+ jugadores)
   - Validar partidos de grupos
   - Validar partidos de bracket
   - Validar avance automático
   - Validar identificación de campeón

**Mejoras Futuras (V1.2+):**
- Edición de jugadores desde UI
- Eliminación de categorías completas
- Exportación a CSV desde UI
- Impresión de hojas de grupo (PDF)
- Mejoras al bracket manual (auto-sugerencias, rellenar BYEs)

### Flujo de Trabajo Actual

**Por CLI (funciona perfectamente):**
```bash
# 1. Importar jugadores
ettem import-players --csv data/samples/players.csv --category U13

# 2. Crear grupos
ettem build-groups --config config/sample_config.yaml --category U13

# 3. Abrir panel web
ettem open-panel

# 4. Ingresar resultados en http://127.0.0.1:8000

# 5. Calcular standings
ettem compute-standings --category U13

# 6. Generar bracket
ettem build-bracket --category U13 --config config/sample_config.yaml

# 7. Exportar
ettem export --what standings --format csv --out out/
```

**Por UI Web (✅ COMPLETO en V1.1.0):**
- ✅ Ver categorías y grupos
- ✅ Ver partidos y standings
- ✅ Ingresar/editar/eliminar resultados
- ✅ Ver bracket generado
- ✅ **Importar jugadores (CSV + manual)**
- ✅ **Crear grupos con configuración**
- ✅ **Calcular standings (todas o por categoría)**
- ✅ **Generar bracket con configuración**

### Objetivo V1.1 ✅ CUMPLIDO

**UI como interfaz principal completa:**
- ✅ Todas las operaciones del CLI disponibles en la UI web
- ✅ Usuario puede gestionar torneo 100% desde navegador
- ✅ CLI queda como herramienta avanzada/scripts

### Notas Técnicas

**Arquitectura Actual:**
- Frontend: FastAPI + Jinja2 templates + JavaScript vanilla
- Backend: SQLAlchemy ORM + SQLite
- Validación: Módulo dedicado con reglas ITTF
- i18n: YAML con dot notation
- Sesiones: SessionMiddleware para flash messages

**Archivos Principales:**
- `src/ettem/webapp/app.py` - Rutas y endpoints (~1700 líneas con admin + manual bracket)
- `src/ettem/webapp/static/styles.css` - Sistema de diseño (686 líneas)
- `src/ettem/webapp/static/app.js` - Interactividad (293 líneas)
- `src/ettem/validation.py` - Reglas de validación (en español)
- `src/ettem/i18n.py` - Sistema de traducción
- `src/ettem/storage.py` - Repositorios SQLite con método update_slot_warning

**Nuevos Templates Admin (V1.1.0):**
- `admin_import_players.html` - Upload CSV + formulario manual
- `admin_create_groups.html` - Configuración de grupos con preview
- `admin_calculate_standings.html` - Recalcular clasificaciones
- `admin_generate_bracket.html` - Configuración de bracket (auto + acceso a manual)
- `admin_manual_bracket.html` - Interfaz drag-and-drop para bracket manual (~640 líneas)

## Workflow de Desarrollo

### Ramas de Git
- `main` - Código estable y probado (V1.0.0, V1.0.1, V1.0.2, V1.1.0)
- `feature/*` - Nuevas funcionalidades en desarrollo (se mergean a main cuando están listas)
5. Testing de flujo completo desde UI