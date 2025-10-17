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

## Roadmap (README)
- V1.1: Scheduler/mesas, breaks, buffers, PDF imprimibles, roles/credenciales, múltiples categorías simultáneas.