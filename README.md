# Easy Table Tennis Event Manager (ettem)

Python application for managing table tennis tournaments with round robin groups and knockout brackets.

## Features (V1)

- Player registration from CSV with validation
- Round Robin group generation with snake seeding
- Automatic fixture generation using circle method
- Local web panel for manual result entry
- Standings calculation with advanced tie-breaking
- Knockout bracket generation with strategic placement
- SQLite persistence (offline-first)
- Internationalization (Spanish/English)
- CSV export for groups, standings, and brackets

**Note:** V1 does NOT include scheduling/table assignment. This is planned for V1.1.

## Quick Start

### Installation

1. Create and activate a virtual environment:
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Basic Usage

```bash
# Import players from CSV
ettem import-players --csv data/samples/players.csv --category U13

# Build groups
ettem build-groups --config config/sample_config.yaml --out out/

# Launch web panel to enter results
ettem open-panel

# Calculate standings
ettem compute-standings --out out/

# Generate knockout bracket
ettem build-bracket --out out/

# Export data
ettem export --what standings --format csv --out out/
```

## CSV Format

Players CSV must include these columns:
- `id`: Unique player identifier
- `nombre`: First name
- `apellido`: Last name
- `genero`: Gender (M or F)
- `pais_cd`: ISO-3 country code (ESP, MEX, ARG, etc.)
- `ranking_pts`: Numeric ranking points
- `categoria`: Category (e.g., U13, U15, etc.)

See `data/samples/players.csv` for an example.

## Scoring Rules

- **Win:** 2 tournament points
- **Loss (played):** 1 tournament point
- **Walkover (loser):** 0 tournament points

## Tie-Breaking Rules

When 3+ players are tied on tournament points, the following criteria are applied **only among the tied players**:

1. **Sets ratio:** `sets_won / sets_lost` (if sets_lost = 0, treated as infinity)
2. **Points ratio:** `points_won / points_lost` (if points_lost = 0, treated as infinity)
3. **Seed:** Lower seed number wins (deterministic final tie-breaker)

## Bracket Generation

### Automatic Bracket Generation

- Bracket size: next power of 2 ≥ number of qualifiers
- **G1 (best 1st place):** top slot
- **G2 (second best 1st place):** bottom slot
- **Other 1st place finishers:** random draw in predefined slots (deterministic with `random_seed`)
- **2nd place finishers:** placed in opposite half from their group's 1st place
- **BYEs:** filled automatically according to ITTF positioning rules
- **Same-country annotation:** 1st round matches with same country are flagged for review (non-blocking)

### Manual Bracket (Drag & Drop)

The web UI includes a manual bracket builder with:
- **Drag-and-drop interface:** Move players between slots or from lists to slots
- **ITTF-compliant BYE positioning:** BYEs are pre-placed according to official ITTF rules based on number of groups
  - 3 groups (6 players → 8 bracket): BYEs at positions [2, 7]
  - 5 groups (10 players → 16 bracket): BYEs at positions [2, 6, 7, 10, 11, 15]
  - Supports up to 20 groups with predefined positions
- **Removable/repositionable BYEs:** Click X to remove, drag from pool to reposition
- **Group constraint validation:** Same group cannot be in same half of bracket
- **Same-country warnings:** Visual alerts for same-country first-round matches
- **Player swap support:** Drag occupied slots to swap players

## Configuration

Edit `config/sample_config.yaml`:

```yaml
random_seed: 42              # For deterministic draws
group_size_preference: 4     # Preferred group size (3 or 4)
advance_per_group: 2         # Players advancing to knockout
lang: es                     # Language (es or en)
```

## Development Commands

```bash
# Run all tests
pytest

# Run specific test
pytest tests/test_standings.py::test_triple_tie

# Run with coverage
pytest --cov=ettem --cov-report=html

# Lint code
ruff check .
ruff check --fix .

# Format code
black .

# Type checking
mypy src/ettem
```

## Project Structure

```
easy-table-tennis-event/
├── config/
│   └── sample_config.yaml       # Configuration template
├── data/
│   └── samples/
│       └── players.csv          # Sample player data
├── i18n/
│   ├── strings_es.yaml          # Spanish translations
│   └── strings_en.yaml          # English translations
├── src/
│   └── ettem/
│       ├── cli.py               # CLI commands
│       ├── models.py            # Data models
│       ├── storage.py           # SQLite repositories
│       ├── group_builder.py     # Group generation
│       ├── standings.py         # Standings calculator
│       ├── bracket.py           # Bracket generator
│       ├── io_csv.py            # CSV import/export
│       ├── config_loader.py     # Config validation
│       ├── i18n.py              # Translation helpers
│       └── webapp/
│           ├── app.py           # FastAPI application
│           ├── templates/       # HTML templates
│           └── static/          # CSS/JS files
├── tests/                       # Test suite
├── requirements.txt             # Dependencies
├── pyproject.toml               # Project configuration
├── README.md                    # This file
└── CLAUDE.md                    # Claude Code guidance
```

## Roadmap

See **MVP_ROADMAP.md** for detailed roadmap and version planning.

### Current Focus: V1.1.1 (Complete MVP)

**Goal:** Run a complete tournament for 1 category from start to finish.

**What's Missing:**
- [ ] Final results and podium view
- [ ] Champion identification
- [ ] Tournament completion status

**Everything else works!** You can already:
- ✅ Import players
- ✅ Create groups
- ✅ Enter group results
- ✅ Calculate standings
- ✅ Generate bracket (auto + manual)
- ✅ Enter bracket results
- ✅ Auto-advance winners

### Future Versions

- **V1.2:** Usability improvements (edit players, delete categories, etc.)
- **V1.3:** Export & print (PDFs, certificates, group sheets)
- **V1.4:** Multiple simultaneous categories
- **V2.0:** Scheduler with table/time assignments
- **V2.1:** Live operation (displays, notifications, table panels)
- **V3.0:** Advanced features (roles, multi-tenant, API, mobile app)

## Contributing

Private project. For bugs or feature requests, create an issue or contact the maintainer.

## License

Private project
