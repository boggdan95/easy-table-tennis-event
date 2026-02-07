# ETTEM - Guia Tecnica v2.2

Manual tecnico para desarrolladores y administradores de sistemas de **ETTEM - Easy Table Tennis Event Manager**.

---

## Tabla de Contenidos

1. [Resumen de Arquitectura](#resumen-de-arquitectura)
2. [Stack Tecnologico](#stack-tecnologico)
3. [Estructura del Proyecto](#estructura-del-proyecto)
4. [Esquema de Base de Datos](#esquema-de-base-de-datos)
5. [Referencia de API](#referencia-de-api)
6. [Sistema de Licencias](#sistema-de-licencias)
7. [Internacionalizacion (i18n)](#internacionalizacion-i18n)
8. [Configuracion del Entorno de Desarrollo](#configuracion-del-entorno-de-desarrollo)
9. [Despliegue y Ejecutable Windows](#despliegue-y-ejecutable-windows)
10. [Configuracion de Red](#configuracion-de-red)
11. [Tests](#tests)
12. [Resolucion de Problemas](#resolucion-de-problemas)

---

## Resumen de Arquitectura

ETTEM es una aplicacion monolitica de servidor local disenada para gestionar torneos de tenis de mesa. Se ejecuta como un servidor web en la maquina del organizador y es accesible desde cualquier dispositivo en la misma red local (celulares de arbitros, pantallas publicas, etc.).

### Diagrama de Componentes

```
+------------------------------------------------------------------+
|                      ETTEM Server (PC del organizador)            |
|                                                                   |
|  +-------------------+    +--------------------+                  |
|  |    FastAPI App     |    |   SQLite Database  |                  |
|  |  (app.py ~9200 L) |<-->|  (.ettem/ettem.db) |                  |
|  +-------------------+    +--------------------+                  |
|  |   Jinja2 Templates  |                                         |
|  |   Static CSS/JS     |                                         |
|  +---------------------+                                         |
+------------------------------------------------------------------+
        |               |                |
   [Navegador PC]  [Celular Arbitro]  [TV Display]
   /admin/*        /mesa/{n}          /display
```

### Flujo de Datos

1. **Organizador (PC):** Gestiona el torneo desde el navegador (`/admin/*`, `/category/*`, `/bracket/*`).
2. **Arbitros (celular):** Acceden a `/mesa/{n}` via WiFi para ingresar marcadores en tiempo real.
3. **Pantalla publica (TV):** Muestra `/display` con auto-refresh cada 5 segundos.
4. **API JSON:** Los endpoints `/api/*` proporcionan datos en vivo para sincronizacion.

### Principios de Diseno

- **Windows-first:** La plataforma principal es Windows. El ejecutable `.exe` no requiere Python instalado.
- **Offline-first:** Todo funciona sin conexion a internet. La base de datos es SQLite local.
- **Servidor unico:** Una sola instancia de FastAPI sirve todas las vistas (admin, arbitro, display).
- **Sin framework frontend:** Vanilla HTML/CSS/JS con Jinja2 templates. Sin React, Vue, ni similares.

---

## Stack Tecnologico

| Componente | Tecnologia | Version |
|------------|-----------|---------|
| Lenguaje | Python | 3.11+ (compatible con 3.14) |
| Framework web | FastAPI | >= 0.104.0 |
| ORM | SQLAlchemy | >= 2.0.0 |
| Base de datos | SQLite | (incluida en Python) |
| Templates | Jinja2 | >= 3.1.2 |
| Servidor ASGI | Uvicorn | >= 0.24.0 |
| CLI | Click | >= 8.1.0 |
| Validacion | Pydantic | >= 2.4.0 |
| Generacion PDF | xhtml2pdf | >= 0.2.17 |
| Configuracion | PyYAML | >= 6.0.1 |
| Sesiones web | itsdangerous | >= 2.1.0 |
| Ejecutable | PyInstaller | (para compilacion) |

### Dependencias de Desarrollo

| Herramienta | Proposito |
|-------------|-----------|
| pytest | Framework de tests |
| pytest-cov | Cobertura de codigo |
| httpx | Cliente HTTP para tests de FastAPI |
| black | Formateador de codigo |
| ruff | Linter rapido |
| mypy | Comprobacion de tipos |

Todas las dependencias estan listadas en `requirements.txt`.

---

## Estructura del Proyecto

```
easy-table-tennis-event/
|
|-- src/ettem/                      # Codigo fuente principal
|   |-- __init__.py
|   |-- cli.py                      # Comandos CLI (Click)
|   |-- models.py                   # Modelos de dominio (dataclasses)
|   |-- storage.py                  # ORM SQLAlchemy + repositorios (~1900 lineas)
|   |-- licensing.py                # Sistema de licencias HMAC-SHA256
|   |-- validation.py               # Validacion de scores ITTF
|   |-- i18n.py                     # Internacionalizacion (ES/EN)
|   |-- paths.py                    # Resolucion de rutas (dev/frozen)
|   |-- pdf_generator.py            # Generacion de PDFs (xhtml2pdf)
|   |-- group_builder.py            # Generacion de grupos con snake seeding
|   |-- standings.py                # Calculadora de standings con desempates
|   |-- bracket.py                  # Generador de brackets (reglas ITTF)
|   |-- io_csv.py                   # Importacion CSV
|   |-- config_loader.py            # Cargador de configuracion YAML
|   |
|   |-- webapp/
|       |-- __init__.py
|       |-- app.py                  # Aplicacion FastAPI (~9200 lineas, todas las rutas)
|       |-- templates/              # Templates Jinja2 (30 archivos HTML)
|       |-- static/
|           |-- styles.css          # Estilos CSS
|           |-- app.js              # JavaScript del cliente
|
|-- config/
|   |-- sample_config.yaml          # Configuracion de ejemplo
|
|-- i18n/
|   |-- strings_es.yaml             # Traducciones espanol
|   |-- strings_en.yaml             # Traducciones ingles
|
|-- tests/                          # Tests automatizados
|   |-- test_validation.py          # Tests de validacion ITTF
|   |-- test_standings.py           # Tests de standings
|   |-- test_bracket.py             # Tests de bracket
|   |-- test_groups.py              # Tests de grupos
|   |-- test_storage.py             # Tests de repositorios
|   |-- test_i18n.py                # Tests de internacionalizacion
|   |-- test_export.py              # Tests de exportacion
|   |-- test_webapp_smoke.py        # Tests de humo de la webapp
|
|-- docs/
|   |-- screenshots/                # Capturas de pantalla
|
|-- launcher.py                     # Entry point para PyInstaller
|-- ettem.spec                      # Configuracion de PyInstaller
|-- requirements.txt                # Dependencias Python
|-- CLAUDE.md                       # Instrucciones de desarrollo
|-- TECHNICAL_GUIDE.md              # Este archivo
```

### Modulos Clave

#### `models.py` - Modelos de Dominio

Define las entidades del sistema como dataclasses puras (sin dependencia de SQLAlchemy):

- **`Player`** - Jugador con nombre, pais, ranking, categoria
- **`Match`** - Partido con sets, estado, ganador
- **`Set`** - Un set individual (puntos de cada jugador)
- **`Group`** - Grupo de round robin
- **`GroupStanding`** - Posicion de un jugador en su grupo
- **`BracketSlot`** - Posicion en la llave de eliminacion
- **`Bracket`** - Estructura completa de la llave KO
- **`MatchResult`** - Modelo de entrada para registrar resultados

Enumeraciones importantes:
- **`MatchStatus`**: `pending`, `in_progress`, `completed`, `walkover`
- **`RoundType`**: `RR`, `R128`, `R64`, `R32`, `R16`, `QF`, `SF`, `F`
- **`Gender`**: `M`, `F`

#### `storage.py` - Capa de Persistencia

Contiene los modelos ORM de SQLAlchemy y el patron repositorio:

- **Modelos ORM:** `TournamentORM`, `PlayerORM`, `GroupORM`, `MatchORM`, `GroupStandingORM`, `BracketSlotORM`, `SessionORM`, `TimeSlotORM`, `ScheduleSlotORM`, `TableConfigORM`, `TableLockORM`, `LiveScoreORM`
- **`DatabaseManager`:** Gestiona la conexion a SQLite con `NullPool`
- **Repositorios:** `TournamentRepository`, `PlayerRepository`, `GroupRepository`, `MatchRepository`, `StandingRepository`, `BracketRepository`, `ScheduleSlotRepository`

#### `webapp/app.py` - Aplicacion Web

Archivo monolitico de ~9200 lineas que contiene:
- Middleware de licencias
- Middleware de idioma
- Todas las rutas HTTP (GET/POST)
- Logica de negocio integrada en las rutas
- Generacion de respuestas HTML y JSON

#### `paths.py` - Resolucion de Rutas

Maneja la diferencia entre ejecucion en desarrollo y modo congelado (PyInstaller):

| Funcion | Desarrollo | Ejecutable (frozen) |
|---------|-----------|---------------------|
| `get_base_path()` | Raiz del proyecto | Directorio temporal `_MEIPASS` |
| `get_templates_dir()` | `src/ettem/webapp/templates/` | `_MEIPASS/ettem/webapp/templates/` |
| `get_static_dir()` | `src/ettem/webapp/static/` | `_MEIPASS/ettem/webapp/static/` |
| `get_data_dir()` | `./. ettem/` | `./.ettem/` (directorio de trabajo) |
| `get_i18n_dir()` | `./i18n/` | `_MEIPASS/i18n/` |
| `get_config_dir()` | `./config/` | `_MEIPASS/config/` |

---

## Esquema de Base de Datos

La base de datos es un archivo SQLite ubicado en `.ettem/ettem.sqlite`. Se crea automaticamente al iniciar la aplicacion.

### Diagrama de Tablas

```
tournaments
    |-- players (tournament_id FK)
    |-- groups (tournament_id FK)
    |   |-- matches (group_id FK)
    |   |-- group_standings (group_id FK)
    |-- sessions (tournament_id FK)
    |   |-- time_slots (session_id FK)
    |   |-- schedule_slots (session_id FK)
    |-- table_configs (tournament_id FK)
    |   |-- table_locks (table_id FK)
    |-- bracket_slots (tournament_id FK)
    |-- live_scores (match_id FK, table_id FK)
```

### Tabla `tournaments`

Representa un torneo/evento completo.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | INTEGER PK | Identificador unico |
| `name` | VARCHAR(200) | Nombre del torneo |
| `date` | DATETIME | Fecha del torneo |
| `location` | VARCHAR(200) | Ubicacion |
| `status` | VARCHAR(20) | `active`, `completed`, `archived` |
| `is_current` | BOOLEAN | Solo un torneo puede ser el actual |
| `notes` | TEXT | Notas opcionales |
| `num_tables` | INTEGER | Numero de mesas disponibles (default: 4) |
| `default_match_duration` | INTEGER | Minutos por partido (default: 30) |
| `min_rest_time` | INTEGER | Descanso minimo entre partidos en minutos (default: 10) |
| `created_at` | DATETIME | Fecha de creacion |
| `updated_at` | DATETIME | Ultima modificacion |

### Tabla `players`

Jugadores inscritos en el torneo.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | INTEGER PK | ID de base de datos (auto) |
| `nombre` | VARCHAR(100) | Nombre |
| `apellido` | VARCHAR(100) | Apellido |
| `genero` | VARCHAR(1) | `M` o `F` |
| `pais_cd` | VARCHAR(3) | Codigo ISO-3 (ESP, MEX, ARG) |
| `ranking_pts` | FLOAT | Puntos de ranking |
| `categoria` | VARCHAR(20) | Categoria ITTF (U13BS, MS, etc.) |
| `seed` | INTEGER | Cabeza de serie (1 = mejor) |
| `original_id` | INTEGER | ID del CSV de origen |
| `tournament_number` | INTEGER | Numero de dorsal |
| `group_id` | INTEGER FK | Grupo asignado |
| `group_number` | INTEGER | Numero dentro del grupo (1-4) |
| `tournament_id` | INTEGER FK | Torneo al que pertenece |
| `checked_in` | BOOLEAN | Si se presento en la sede |
| `notes` | TEXT | Notas opcionales |
| `created_at` | DATETIME | Fecha de creacion |
| `updated_at` | DATETIME | Ultima modificacion |

### Tabla `groups`

Grupos de round robin.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | INTEGER PK | Identificador unico |
| `name` | VARCHAR(10) | Letra del grupo (A, B, C...) |
| `category` | VARCHAR(20) | Categoria |
| `tournament_id` | INTEGER FK | Torneo |
| `player_ids_json` | TEXT | IDs de jugadores como JSON array |
| `created_at` | DATETIME | Fecha de creacion |

### Tabla `matches`

Partidos (tanto de grupo como de bracket).

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | INTEGER PK | Identificador unico |
| `player1_id` | INTEGER FK | Jugador 1 (nullable para BYE) |
| `player2_id` | INTEGER FK | Jugador 2 (nullable para BYE) |
| `group_id` | INTEGER FK | Grupo (null si es bracket) |
| `tournament_id` | INTEGER FK | Torneo |
| `category` | VARCHAR(20) | Categoria (para partidos de bracket) |
| `round_type` | VARCHAR(10) | `RR`, `R16`, `QF`, `SF`, `F` |
| `round_name` | VARCHAR(50) | Nombre descriptivo |
| `match_number` | INTEGER | Orden dentro de la ronda |
| `status` | VARCHAR(20) | `pending`, `in_progress`, `completed`, `walkover` |
| `winner_id` | INTEGER | ID del ganador |
| `best_of` | INTEGER | Formato: 3, 5 o 7 sets |
| `sets_json` | TEXT | Sets como JSON array |
| `scheduled_time` | DATETIME | Hora programada |
| `table_number` | INTEGER | Mesa asignada |
| `created_at` | DATETIME | Fecha de creacion |
| `updated_at` | DATETIME | Ultima modificacion |

**Formato de `sets_json`:**
```json
[
  {"set_number": 1, "player1_points": 11, "player2_points": 9},
  {"set_number": 2, "player1_points": 7, "player2_points": 11},
  {"set_number": 3, "player1_points": 11, "player2_points": 5}
]
```

### Tabla `group_standings`

Posiciones calculadas dentro de cada grupo.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | INTEGER PK | Identificador unico |
| `player_id` | INTEGER FK | Jugador |
| `group_id` | INTEGER FK | Grupo |
| `points_total` | INTEGER | Puntos de torneo (2=victoria, 1=derrota, 0=walkover) |
| `wins` | INTEGER | Victorias |
| `losses` | INTEGER | Derrotas |
| `sets_w` | INTEGER | Sets ganados |
| `sets_l` | INTEGER | Sets perdidos |
| `points_w` | INTEGER | Puntos (game points) ganados |
| `points_l` | INTEGER | Puntos (game points) perdidos |
| `position` | INTEGER | Posicion final (1, 2, 3...) |
| `updated_at` | DATETIME | Ultima modificacion |

### Tabla `bracket_slots`

Posiciones en la llave de eliminacion directa.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | INTEGER PK | Identificador unico |
| `category` | VARCHAR(20) | Categoria |
| `tournament_id` | INTEGER FK | Torneo |
| `slot_number` | INTEGER | Posicion en el bracket (1 = arriba) |
| `round_type` | VARCHAR(10) | Ronda (R32, R16, QF, SF, F) |
| `player_id` | INTEGER FK | Jugador asignado |
| `is_bye` | BOOLEAN | Es un BYE |
| `same_country_warning` | BOOLEAN | Advertencia de mismo pais |
| `advanced_by_bye` | BOOLEAN | Avanzo por BYE |
| `created_at` | DATETIME | Fecha de creacion |

### Tabla `sessions`

Sesiones/bloques de tiempo del torneo.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | INTEGER PK | Identificador unico |
| `tournament_id` | INTEGER FK | Torneo |
| `name` | VARCHAR(100) | Nombre (ej: "Sabado Manana") |
| `date` | DATETIME | Fecha de la sesion |
| `start_time` | VARCHAR(5) | Hora de inicio (HH:MM) |
| `end_time` | VARCHAR(5) | Hora de fin (HH:MM) |
| `order` | INTEGER | Orden para clasificacion |
| `is_finalized` | INTEGER | 0 = borrador, 1 = finalizada |
| `created_at` | DATETIME | Fecha de creacion |

### Tabla `time_slots`

Bloques de tiempo dentro de una sesion.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | INTEGER PK | Identificador unico |
| `session_id` | INTEGER FK | Sesion |
| `slot_number` | INTEGER | Numero de orden (0, 1, 2...) |
| `start_time` | VARCHAR(5) | Hora de inicio calculada (HH:MM) |
| `duration_minutes` | INTEGER | Duracion en minutos |
| `created_at` | DATETIME | Fecha de creacion |

### Tabla `schedule_slots`

Asignacion de partidos a mesa y horario.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | INTEGER PK | Identificador unico |
| `session_id` | INTEGER FK | Sesion |
| `match_id` | INTEGER FK | Partido |
| `table_number` | INTEGER | Mesa (1, 2, 3...) |
| `start_time` | VARCHAR(5) | Hora de inicio (HH:MM) |
| `duration` | INTEGER | Duracion personalizada en minutos |
| `created_at` | DATETIME | Fecha de creacion |

### Tabla `table_configs`

Configuracion de mesas fisicas para el modo arbitro.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | INTEGER PK | Identificador unico |
| `tournament_id` | INTEGER FK | Torneo |
| `table_number` | INTEGER | Numero de mesa (1, 2, 3...) |
| `name` | VARCHAR(50) | Nombre visible (ej: "Mesa 1") |
| `mode` | VARCHAR(20) | `point_by_point` o `result_per_set` |
| `is_active` | BOOLEAN | Si la mesa esta disponible |
| `created_at` | DATETIME | Fecha de creacion |
| `updated_at` | DATETIME | Ultima modificacion |

### Tabla `table_locks`

Control de acceso por dispositivo a cada mesa.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | INTEGER PK | Identificador unico |
| `table_id` | INTEGER FK | Mesa (unique) |
| `session_token` | VARCHAR(64) | Token unico del dispositivo |
| `locked_at` | DATETIME | Cuando se bloqueo |
| `last_activity` | DATETIME | Ultima actividad (heartbeat) |
| `device_info` | VARCHAR(200) | Info del navegador/dispositivo |
| `current_match_id` | INTEGER FK | Partido actualmente en juego |

### Tabla `live_scores`

Marcadores en vivo de partidos en progreso.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | INTEGER PK | Identificador unico |
| `match_id` | INTEGER FK | Partido (unique) |
| `table_id` | INTEGER FK | Mesa |
| `current_set` | INTEGER | Set actual (1, 2, 3...) |
| `player1_points` | INTEGER | Puntos del J1 en set actual |
| `player2_points` | INTEGER | Puntos del J2 en set actual |
| `player1_sets` | INTEGER | Sets ganados por J1 |
| `player2_sets` | INTEGER | Sets ganados por J2 |
| `serving_player` | INTEGER | Quien saca (1 o 2) |
| `started_at` | DATETIME | Cuando comenzo el partido |
| `updated_at` | DATETIME | Ultima actualizacion |

---

## Referencia de API

### Endpoints JSON (API)

Estos endpoints devuelven JSON y son utilizados por el marcador del arbitro y la pantalla publica.

#### `GET /api/live-scores`

Devuelve todos los marcadores en vivo del torneo actual.

**Respuesta:**
```json
{
  "scores": [
    {
      "match_id": 42,
      "table_number": 1,
      "player1_name": "Juan Perez",
      "player2_name": "Pedro Lopez",
      "player1_sets": 2,
      "player2_sets": 1,
      "player1_points": 7,
      "player2_points": 5,
      "current_set": 4,
      "category": "U15BS",
      "round_type": "QF"
    }
  ]
}
```

**Notas:**
- Solo devuelve partidos del torneo activo (filtrado por `tournament_id`).
- Utilizado por `/display` para auto-refresh cada 5 segundos.

#### `POST /api/live-score/{match_id}`

Actualiza el marcador en vivo de un partido.

**Headers requeridos:**
- Cookie con `session_token` que coincida con el lock de la mesa.

**Body (JSON):**
```json
{
  "current_set": 2,
  "player1_points": 8,
  "player2_points": 6,
  "player1_sets": 1,
  "player2_sets": 0,
  "serving_player": 1
}
```

**Seguridad:** Valida el `session_token` contra el lock de la mesa antes de aceptar actualizaciones. Esto previene que clientes no autorizados envien marcadores falsos.

#### `POST /api/table/{table_id}/heartbeat`

Mantiene activo el bloqueo de una mesa. Debe enviarse periodicamente (cada ~30 segundos) para evitar que el lock expire por inactividad.

**Headers requeridos:**
- Cookie con `session_token`.

**Respuesta:**
```json
{
  "status": "ok",
  "locked": true
}
```

### Rutas Web Principales

#### Administracion

| Ruta | Metodo | Descripcion |
|------|--------|-------------|
| `/` | GET | Panel principal (dashboard) |
| `/tournaments` | GET | Lista de torneos |
| `/tournaments/create` | POST | Crear nuevo torneo |
| `/tournaments/{id}/set-current` | POST | Establecer torneo activo |
| `/admin/import-players` | GET | Formulario de importacion |
| `/admin/import-players/csv` | POST | Importar jugadores desde CSV |
| `/admin/import-players/manual` | POST | Agregar jugador manualmente |
| `/admin/create-groups` | GET | Formulario de creacion de grupos |
| `/admin/create-groups/preview` | POST | Vista previa de grupos |
| `/admin/create-groups/execute` | POST | Crear grupos definitivamente |
| `/admin/calculate-standings/all` | POST | Calcular standings de todas las categorias |
| `/admin/generate-bracket/execute` | POST | Generar bracket KO |
| `/admin/scheduler` | GET | Panel del scheduler |
| `/admin/live-results` | GET | Panel de resultados en vivo |
| `/admin/print-center` | GET | Centro de impresion |
| `/admin/table-config` | GET | Configuracion de mesas |
| `/admin/table-config/qr-codes` | GET | Codigos QR para mesas |

*Ver captura: `screenshots/01_dashboard.png`*

#### Categorias y Grupos

| Ruta | Metodo | Descripcion |
|------|--------|-------------|
| `/category/{category}` | GET | Vista de categoria |
| `/group/{group_id}/matches` | GET | Partidos del grupo |
| `/group/{group_id}/standings` | GET | Standings del grupo |
| `/group/{group_id}/sheet` | GET | Hoja del grupo (cross-table) |
| `/category/{category}/standings` | GET | Standings de toda la categoria |
| `/category/{category}/bracket` | GET | Vista del bracket |
| `/category/{category}/results` | GET | Resultados de la categoria |

*Ver capturas: `screenshots/04_category_overview.png`, `screenshots/07_group_matches.png`*

#### Partidos y Resultados

| Ruta | Metodo | Descripcion |
|------|--------|-------------|
| `/match/{match_id}/enter-result` | GET | Formulario de ingreso de resultado |
| `/match/{match_id}/save-result` | POST | Guardar resultado |
| `/match/{match_id}/delete-result` | POST | Eliminar resultado |

*Ver captura: `screenshots/24_enter_result.png`*

#### Scheduler

| Ruta | Metodo | Descripcion |
|------|--------|-------------|
| `/admin/scheduler` | GET | Panel del scheduler |
| `/admin/scheduler/config` | POST | Guardar configuracion |
| `/admin/scheduler/session/create` | POST | Crear nueva sesion |
| `/admin/scheduler/grid/{session_id}` | GET | Grid visual de asignaciones |
| `/admin/scheduler/slot/assign` | POST | Asignar partido a mesa/hora |

*Ver capturas: `screenshots/13_scheduler.png`, `screenshots/14_scheduler_grid.png`*

#### Marcador de Arbitro

| Ruta | Metodo | Descripcion |
|------|--------|-------------|
| `/mesa/{table_number}` | GET | Interfaz del marcador |
| `/mesa/{table_number}/select` | POST | Seleccionar partido |
| `/mesa/{table_number}/set` | POST | Enviar resultado de set |
| `/mesa/{table_number}/walkover` | GET/POST | Registrar walkover |
| `/mesa/{table_number}/clear` | POST | Liberar partido |

*Ver capturas: `screenshots/19_referee_scoreboard.png`, `screenshots/17b_marcador_activo.png`*

#### Pantalla Publica

| Ruta | Metodo | Descripcion |
|------|--------|-------------|
| `/display` | GET | Pantalla publica (optimizada para TV) |

*Ver captura: `screenshots/20_public_display.png`*

#### Impresion y Exportacion

| Ruta | Metodo | Descripcion |
|------|--------|-------------|
| `/print/match/{match_id}` | GET | Imprimir hoja de partido |
| `/print/group/{group_id}/sheet` | GET | Imprimir hoja de grupo |
| `/print/bracket/{category}/tree` | GET | Imprimir arbol de bracket |
| `/print/scheduler/grid/{session_id}` | GET | Imprimir grid del scheduler |
| `/export/bracket/{category}` | GET | Exportar bracket |
| `/export/standings/{category}` | GET | Exportar standings |

*Ver captura: `screenshots/16_print_center.png`*

#### Licencias

| Ruta | Metodo | Descripcion |
|------|--------|-------------|
| `/license/activate` | GET | Formulario de activacion |
| `/license/activate` | POST | Activar licencia |

---

## Sistema de Licencias

### Formato de Clave

```
ETTEM-CCCC-MMYY-SSSSSSSS
```

| Segmento | Descripcion | Ejemplo |
|----------|-------------|---------|
| `ETTEM` | Prefijo fijo | `ETTEM` |
| `CCCC` | ID del cliente (4 caracteres alfanumericos) | `JN01` |
| `MMYY` | Mes y ano de expiracion | `0726` (julio 2026) |
| `SSSSSSSS` | Firma HMAC-SHA256 (8 caracteres) | `K8M2X9P4` |

### Funcionamiento

1. **Generacion:** Se usa `tools/generate_license.py` con un secreto HMAC embebido.
2. **Validacion:** Cada request HTTP pasa por el middleware `license_middleware` en `app.py`.
3. **Almacenamiento:** La clave se guarda en `.ettem/license.key`.
4. **Expiracion:** La licencia es valida hasta el ultimo dia del mes indicado (inclusive).

### Flujo de Validacion

```
Request HTTP
    |
    v
license_middleware()
    |
    +-- Ruta exenta? (/license, /static, /mesa, /display, /api) --> Continuar
    |
    +-- Cargar .ettem/license.key
    |
    +-- Verificar firma HMAC
    |
    +-- Verificar expiracion
    |
    +-- Invalida? --> Redirect a /license/activate
    |
    +-- Valida --> Continuar con el request
```

**Nota:** Las rutas `/mesa/*`, `/display` y `/api/*` estan exentas de la verificacion de licencia para permitir que los dispositivos de arbitros y pantallas publicas funcionen sin necesidad de activar la licencia en cada uno.

### Generar una Licencia

```bash
python tools/generate_license.py --client XX01 --months 12
```

---

## Internacionalizacion (i18n)

### Idiomas Soportados

- **Espanol (`es`)** - Idioma por defecto
- **Ingles (`en`)**

### Archivos de Traduccion

- `i18n/strings_es.yaml` - Cadenas en espanol
- `i18n/strings_en.yaml` - Cadenas en ingles

### Como Funciona

1. El idioma se determina por: argumento CLI `--lang` > variable de entorno `ETTEM_LANG` > defecto (`es`).
2. Las cadenas se cargan desde archivos YAML y se cachean en memoria.
3. Las plantillas Jinja2 acceden a las cadenas a traves de una funcion helper.
4. Soporta notacion con puntos para claves anidadas: `"app.title"`, `"cli.import.success"`.
5. Si una clave no existe en el idioma seleccionado, se intenta con ingles como fallback.

### Ejemplo de Archivo YAML

```yaml
app:
  title: "Easy Table Tennis Event Manager"
  subtitle: "Gestor de Eventos de Tenis de Mesa"

match:
  status:
    pending: "Pendiente"
    in_progress: "En Juego"
    completed: "Completado"
    walkover: "Walkover"
```

### Uso en Codigo

```python
from ettem.i18n import get_string

# Cadena simple
titulo = get_string("app.title", lang="es")

# Cadena con parametros
mensaje = get_string("cli.import.success", lang="en", count=5)
# "Successfully imported 5 players"
```

---

## Configuracion del Entorno de Desarrollo

### Requisitos Previos

- Python 3.11 o superior (compatible con 3.14)
- pip (gestor de paquetes)
- Git

### Instalacion

```bash
# Clonar el repositorio
git clone <url-del-repositorio>
cd easy-table-tennis-event

# Crear entorno virtual (recomendado)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Instalar dependencias
pip install -r requirements.txt

# Instalar el paquete en modo editable
pip install -e .
```

### Ejecutar en Desarrollo

```bash
# Opcion 1: Con uvicorn directamente (recomendado para desarrollo)
python -m uvicorn ettem.webapp.app:app --host 127.0.0.1 --port 8000 --reload

# Opcion 2: Con el CLI
python -m ettem open-panel

# Opcion 3: Con el CLI y idioma especifico
python -m ettem --lang en open-panel
```

El flag `--reload` de uvicorn recarga automaticamente cuando se modifican archivos Python.

### Configuracion

El archivo `config/sample_config.yaml` contiene la configuracion del torneo:

```yaml
# Semilla para sorteos deterministas
random_seed: 42

# Preferencia de tamano de grupo (3 o 4 jugadores)
group_size_preference: 4

# Jugadores que avanzan de cada grupo al bracket
advance_per_group: 2

# Idioma (es o en)
lang: es
```

### Estructura de Datos Local

Al ejecutar la aplicacion, se crea el directorio `.ettem/` en el directorio de trabajo:

```
.ettem/
|-- ettem.sqlite     # Base de datos SQLite
|-- license.key      # Clave de licencia (si esta activada)
```

---

## Despliegue y Ejecutable Windows

### Compilar el Ejecutable

```bash
# Asegurarse de tener PyInstaller instalado
pip install pyinstaller

# Compilar
python -m PyInstaller ettem.spec --clean --noconfirm
```

**Resultado:** `dist/ETTEM.exe` (~45 MB, standalone)

### Que Incluye el Ejecutable

El archivo `ettem.spec` configura PyInstaller para incluir:

- **Datos empaquetados:**
  - Templates HTML (`src/ettem/webapp/templates/`)
  - Archivos estaticos CSS/JS (`src/ettem/webapp/static/`)
  - Archivos de traduccion (`i18n/`)
  - Configuracion de ejemplo (`config/`)

- **Hidden imports:** Uvicorn, FastAPI, Starlette, SQLAlchemy, Jinja2, xhtml2pdf, Pillow, etc.

- **Excluidos:** tkinter, matplotlib, numpy, pandas, cv2 (para reducir tamano).

### Funcionamiento del Ejecutable

1. Al ejecutar `ETTEM.exe`, PyInstaller extrae los archivos empaquetados a un directorio temporal (`_MEIPASS`).
2. `launcher.py` inicia el servidor uvicorn.
3. Se abre automaticamente el navegador del sistema.
4. La base de datos y la licencia se almacenan en `.ettem/` relativo al directorio de trabajo.
5. El usuario interactua a traves del navegador web.

### Distribucion

Para distribuir ETTEM:

1. Compilar el ejecutable.
2. Generar una clave de licencia para el cliente.
3. Entregar `ETTEM.exe` al cliente.
4. El cliente ejecuta el `.exe`, activa la licencia y comienza a usar la aplicacion.

---

## Configuracion de Red

Para que los dispositivos moviles (arbitros) y pantallas publicas accedan al servidor, todos deben estar en la misma red WiFi.

### Paso 1: Iniciar el Servidor en la Red Local

```bash
# IMPORTANTE: usar --host 0.0.0.0 para escuchar en todas las interfaces
python -m uvicorn ettem.webapp.app:app --host 0.0.0.0 --port 8000
```

### Paso 2: Abrir Puerto en Firewall de Windows

Ejecutar como administrador:

```bash
netsh advfirewall firewall add rule name="ETTEM Server" dir=in action=allow protocol=TCP localport=8000
```

Para eliminar la regla despues del torneo:

```bash
netsh advfirewall firewall delete rule name="ETTEM Server"
```

### Paso 3: Encontrar la IP Local

```bash
ipconfig
```

Buscar la direccion IPv4 del adaptador WiFi (ejemplo: `192.168.1.100`).

### Paso 4: Acceder desde Dispositivos

| Dispositivo | URL |
|-------------|-----|
| PC del organizador | `http://127.0.0.1:8000/` |
| Celular arbitro (Mesa 1) | `http://192.168.1.100:8000/mesa/1` |
| Celular arbitro (Mesa 2) | `http://192.168.1.100:8000/mesa/2` |
| TV/Pantalla publica | `http://192.168.1.100:8000/display` |

### Codigos QR

La pagina `/admin/table-config/qr-codes` genera codigos QR que los arbitros pueden escanear con su celular para acceder directamente al marcador de su mesa. Los QR apuntan a `http://<ip-local>:8000/mesa/{n}`.

*Ver captura: `screenshots/18_qr_codes.png`*

### Diagrama de Red

```
              Red WiFi Local (192.168.1.x)
                        |
    +-------------------+-------------------+
    |                   |                   |
[PC Organizador]   [Celular 1]        [TV Display]
 192.168.1.100     192.168.1.101      192.168.1.102
 ETTEM Server      /mesa/1            /display
 Puerto 8000       (Arbitro Mesa 1)   (Pantalla publica)
    |
    |-- Base de datos SQLite
    |-- Servidor web (uvicorn)
    |-- Todos los datos
```

### Sistema de Bloqueo de Mesas

Para evitar que dos dispositivos controlen la misma mesa simultaneamente:

1. Cuando un arbitro accede a `/mesa/{n}`, se genera un `session_token` unico en una cookie.
2. El servidor registra el lock en la tabla `table_locks`.
3. El dispositivo envia heartbeats periodicos (`/api/table/{id}/heartbeat`).
4. Si otro dispositivo intenta acceder a la misma mesa, ve un mensaje de "mesa ocupada".
5. El administrador puede desbloquear una mesa desde `/admin/table-config`.
6. Los locks expiran por inactividad si no se reciben heartbeats.

---

## Tests

### Ejecutar Tests

```bash
# Todos los tests
pytest

# Con cobertura
pytest --cov=ettem --cov-report=html

# Test especifico
pytest tests/test_validation.py

# Con salida detallada
pytest -v
```

### Suite de Tests

| Archivo | Tests | Descripcion |
|---------|-------|-------------|
| `test_validation.py` | Validacion de scores ITTF (sets y partidos) |
| `test_standings.py` | Calculo de standings con desempates |
| `test_bracket.py` | Generacion de brackets (seeding, BYEs) |
| `test_groups.py` | Creacion de grupos con snake seeding |
| `test_storage.py` | Operaciones CRUD de repositorios |
| `test_i18n.py` | Sistema de internacionalizacion |
| `test_export.py` | Exportacion de datos |
| `test_webapp_smoke.py` | Tests de humo de la aplicacion web |

**Estado actual:** 60 tests (59 pasan, 1 skip esperado por determinismo de bracket).

**Nota:** `test_webapp_smoke.py` puede fallar si PIL/Pillow no es compatible con la version de Python (ej: Python 3.14). Esto no afecta la funcionalidad de V2.2.

### Reglas de Validacion ITTF Testeadas

Las reglas de tenis de mesa implementadas en `validation.py` incluyen:

- Un set se gana al llegar a 11 puntos con al menos 2 de ventaja.
- En deuce (10-10 o mas), el ganador debe tener exactamente +2 puntos.
- No hay limite superior de puntuacion (ej: 15-13, 20-18 son validos).
- Formato de partido: mejor de 3, 5 o 7 sets.
- El partido termina cuando un jugador alcanza la mayoria de sets requerida.

---

## Resolucion de Problemas

### La aplicacion no inicia

**Sintoma:** Error al ejecutar `python -m uvicorn ...`

**Posibles causas:**
1. Python no esta en el PATH. Verificar con `python --version`.
2. Dependencias no instaladas. Ejecutar `pip install -r requirements.txt`.
3. Puerto 8000 ocupado. Probar con otro puerto: `--port 8001`.

### Los dispositivos moviles no pueden conectarse

**Sintoma:** El celular no puede acceder a `http://192.168.1.X:8000/mesa/1`

**Verificar:**
1. Que el servidor se inicio con `--host 0.0.0.0` (no `127.0.0.1`).
2. Que la regla de firewall esta creada (ver seccion de Configuracion de Red).
3. Que todos los dispositivos estan en la misma red WiFi.
4. Que la IP es correcta (ejecutar `ipconfig` en el PC del servidor).
5. Que no hay un VPN activo que interfiera con la red local.

### La pantalla publica no muestra datos

**Sintoma:** `/display` aparece vacio.

**Verificar:**
1. Que hay un torneo marcado como "actual" (bandera `is_current`).
2. Que hay partidos con estado `in_progress` y registros en `live_scores`.
3. Que el display esta accediendo al servidor correcto.

### Error de licencia

**Sintoma:** La aplicacion redirige constantemente a `/license/activate`.

**Verificar:**
1. Que existe el archivo `.ettem/license.key`.
2. Que la licencia no ha expirado.
3. Que el archivo no tiene espacios ni caracteres extra.
4. Regenerar la licencia si es necesario con `tools/generate_license.py`.

### La base de datos esta corrupta

**Sintoma:** Errores de SQLAlchemy al intentar operar.

**Solucion:**
1. Detener el servidor.
2. Hacer backup de `.ettem/ettem.sqlite`.
3. Eliminar el archivo de base de datos.
4. Reiniciar la aplicacion (se creara una base nueva y vacia).

### Problemas con el ejecutable (.exe)

**Sintoma:** `ETTEM.exe` no abre o muestra errores.

**Verificar:**
1. Que el antivirus no esta bloqueando el ejecutable. Agregar excepcion si es necesario.
2. Que se ejecuta desde un directorio donde el usuario tiene permisos de escritura (se crea `.ettem/`).
3. Revisar la consola para mensajes de error (el ejecutable se compila con `console=True`).

### Mesa bloqueada y no se puede acceder

**Sintoma:** Un arbitro no puede usar una mesa porque aparece como "ocupada".

**Solucion:**
1. Desde el PC del organizador, ir a `/admin/table-config`.
2. Hacer clic en "Desbloquear" en la mesa afectada.
3. El arbitro podra volver a acceder desde su dispositivo.

### Los scores en vivo no se actualizan en el display

**Sintoma:** La pantalla publica (`/display`) no refleja los cambios del marcador.

**Verificar:**
1. Que el arbitro esta enviando scores desde `/mesa/{n}` correctamente.
2. Que el partido tiene un registro en la tabla `live_scores`.
3. Que la pantalla publica tiene auto-refresh activo (JavaScript habilitado en el navegador).
4. Que el `session_token` del dispositivo del arbitro es valido (coincide con el lock de la mesa).

---

## Apendice: Nomenclatura de Categorias ITTF

| Codigo | Descripcion |
|--------|-------------|
| U11BS | Sub-11 Varones Singles |
| U11GS | Sub-11 Mujeres Singles |
| U13BS | Sub-13 Varones Singles |
| U13GS | Sub-13 Mujeres Singles |
| U15BS | Sub-15 Varones Singles |
| U15GS | Sub-15 Mujeres Singles |
| U17BS | Sub-17 Varones Singles |
| U17GS | Sub-17 Mujeres Singles |
| U19BS | Sub-19 Varones Singles |
| U19GS | Sub-19 Mujeres Singles |
| U21BS | Sub-21 Varones Singles |
| U21GS | Sub-21 Mujeres Singles |
| MS | Varones Singles (absoluto) |
| WS | Mujeres Singles (absoluto) |

---

## Apendice: Formato CSV de Jugadores

Columnas requeridas para la importacion de jugadores:

| Columna | Tipo | Descripcion | Ejemplo |
|---------|------|-------------|---------|
| `id` | Entero | Identificador unico | `1` |
| `nombre` | Texto | Nombre del jugador | `Juan` |
| `apellido` | Texto | Apellido del jugador | `Perez` |
| `genero` | Texto | `M` o `F` | `M` |
| `pais_cd` | Texto | Codigo ISO-3 del pais | `ESP` |
| `ranking_pts` | Decimal | Puntos de ranking (0 si no tiene) | `1200` |
| `categoria` | Texto | Categoria ITTF | `U15BS` |

**Ejemplo de archivo CSV:**
```csv
id,nombre,apellido,genero,pais_cd,ranking_pts,categoria
1,Juan,Perez,M,ESP,1200,U15BS
2,Maria,Garcia,F,ESP,1150,U15GS
3,Pedro,Lopez,M,MEX,0,U15BS
4,Ana,Martinez,F,ARG,980,U15GS
```
