# Easy Table Tennis Event Manager (ETTEM)

Python application for managing table tennis tournaments with round robin groups and knockout brackets.

## Features

### Core Tournament Management
- Player registration from CSV with ITTF standard categories
- Round Robin group generation with snake seeding
- Automatic fixture generation using circle method
- Standings calculation with advanced tie-breaking
- Knockout bracket generation with strategic placement
- SQLite persistence (offline-first)

### Web Panel
- Modern responsive UI with sidebar navigation
- Complete tournament management from browser
- Real-time result entry and validation
- Drag-and-drop manual bracket builder
- Dark/Light theme toggle
- Internationalization (Spanish/English)

### Match Format
- Configurable format per category (Best of 3, 5, or 7)
- Different formats for groups vs knockout
- ITTF-compliant score validation

### Windows Executable
- Standalone `.exe` file (~39 MB)
- No Python installation required
- Double-click to launch web panel
- Full CLI available via terminal

### License System
- Offline license key validation
- Monthly, semestral, and annual plans
- Automatic expiration handling

## Quick Start

### Option 1: Windows Executable (Recommended)

1. Download `ETTEM.exe`
2. Double-click to open the web panel
3. Browser opens automatically at `http://127.0.0.1:8000`

For CLI access:
```cmd
ETTEM.exe --help
ETTEM.exe import-players --csv players.csv --category U13BS
```

### Option 2: From Source

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

3. Run the application:
```bash
# Open web panel (recommended)
ettem open-panel

# Or use CLI commands
ettem --help
```

## ITTF Standard Categories

ETTEM uses standard ITTF category nomenclature:

| Category | Description |
|----------|-------------|
| U11BS | Under 11 Boys Singles |
| U11GS | Under 11 Girls Singles |
| U13BS | Under 13 Boys Singles |
| U13GS | Under 13 Girls Singles |
| U15BS | Under 15 Boys Singles |
| U15GS | Under 15 Girls Singles |
| U17BS | Under 17 Boys Singles |
| U17GS | Under 17 Girls Singles |
| U19BS | Under 19 Boys Singles |
| U19GS | Under 19 Girls Singles |
| U21BS | Under 21 Boys Singles |
| U21GS | Under 21 Girls Singles |
| MS | Men's Singles |
| WS | Women's Singles |

## CSV Format

Players CSV must include these columns:

| Column | Description | Required |
|--------|-------------|----------|
| `id` | Unique player identifier | Yes |
| `nombre` | First name | Yes |
| `apellido` | Last name | Yes |
| `genero` | Gender (M or F) | Yes |
| `pais_cd` | ISO-3 country code | Yes |
| `ranking_pts` | Ranking points (0 if unranked) | Yes |
| `categoria` | Category code (e.g., U13BS, MS) | Yes |

Example:
```csv
id,nombre,apellido,genero,pais_cd,ranking_pts,categoria
1,Francisco,Alvarez,M,URU,1850,U17BS
2,Rodrigo,Benitez,M,ARG,1820,U17BS
3,Kevin,Quiroga,M,PAR,0,U17BS
```

**Note:** Players with `ranking_pts=0` are considered unranked and seeded by insertion order after ranked players.

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
- **Other 1st place finishers:** random draw in predefined slots
- **2nd place finishers:** placed in opposite half from their group's 1st place
- **BYEs:** filled automatically according to ITTF positioning rules
- **Same-country annotation:** 1st round matches flagged for review

### Manual Bracket (Drag & Drop)

The web UI includes a manual bracket builder with:
- **Drag-and-drop interface:** Move players between slots
- **ITTF-compliant BYE positioning:** Pre-placed according to official rules
- **Group constraint validation:** Same group cannot be in same half
- **Same-country warnings:** Visual alerts for first-round matches
- **Player swap support:** Drag occupied slots to swap players

## Configuration

Edit `config/sample_config.yaml`:

```yaml
random_seed: 42              # For deterministic draws
group_size_preference: 4     # Preferred group size (3 or 4)
advance_per_group: 2         # Players advancing to knockout
lang: es                     # Language (es or en)
best_of: 5                   # Match format (3, 5, or 7)
```

## CLI Commands

```bash
# Import players from CSV
ettem import-players --csv data/samples/players.csv --category U13BS

# Build groups
ettem build-groups --config config/sample_config.yaml --category U13BS

# Launch web panel
ettem open-panel

# Calculate standings
ettem compute-standings --category U13BS

# Generate knockout bracket
ettem build-bracket --category U13BS --config config/sample_config.yaml

# Export data
ettem export --what standings --format csv --out out/
```

## Web Panel Features

Access all functionality from the browser at `http://127.0.0.1:8000`:

### Tournament Management
- **Dashboard:** Overview of all categories and tournament status
- **Import Players:** Upload CSV or add players manually
- **Create Groups:** Configure and preview with snake seeding, drag-and-drop reordering
- **Enter Results:** Form with ITTF score validation (deuce rules, etc.)
- **View Standings:** Live standings with tie-breaker details
- **Generate Bracket:** Auto from standings or manual with drag-and-drop

### Scheduler System
- **Table Configuration:** Define available tables for the venue
- **Session Management:** Create sessions with flexible time slots
- **Match Assignment:** Assign matches to specific table and time
- **Visual Grid:** See all assignments at a glance
- **Print Scheduler:** Export schedule grid as PDF

### Live Operations
- **Live Results Panel:** Real-time result entry during tournament
- **Print Center:** Central hub for all printing needs
  - Match sheets (individual or batch)
  - Group sheets with result matrix
  - Bracket tree visualization
  - Scheduler grid

### Settings
- **Language:** Spanish / English toggle
- **Theme:** Light / Dark mode

## Development

### Commands

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ettem --cov-report=html

# Lint code
ruff check .

# Format code
black .

# Type checking
mypy src/ettem
```

### Build Executable

#### Windows
```bash
python -m PyInstaller ettem.spec --clean --noconfirm
```
Output: `dist/ETTEM.exe`

#### macOS
```bash
python -m PyInstaller ettem.spec --clean --noconfirm
```
Output: `dist/ETTEM.app`

The codebase is fully cross-platform. The same spec file works on both Windows and Mac.
PyInstaller automatically generates the appropriate format for each platform.

**Note for macOS distribution:** For wider distribution, consider code signing with an Apple Developer certificate to avoid Gatekeeper warnings.

## Project Structure

```
easy-table-tennis-event/
├── config/
│   └── sample_config.yaml       # Configuration template
├── data/
│   └── samples/                 # Sample CSV files
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
│       ├── validation.py        # Score validation
│       ├── licensing.py         # License system
│       ├── i18n.py              # Translation helpers
│       └── webapp/
│           ├── app.py           # FastAPI application
│           ├── templates/       # HTML templates
│           └── static/          # CSS/JS files
├── tests/                       # Test suite
├── launcher.py                  # PyInstaller entry point
├── ettem.spec                   # PyInstaller config
├── requirements.txt             # Dependencies
└── pyproject.toml               # Project configuration
```

## Version History

- **V2.1** - License system, i18n (ES/EN), dark theme, print center, bracket tree view, scheduler print, live results panel, Windows executable (PyInstaller)
- **V2.0** - Scheduler system with table/time assignments, session management
- **V1.1** - Complete UI management (import, groups, standings, bracket), configurable match format (Bo3/Bo5/Bo7)
- **V1.0** - Core tournament engine with CLI

## Roadmap

### V3.0 - Multi-user & API
- User authentication and roles (admin, referee, viewer)
- Multi-tenant support (multiple organizations)
- REST API for integrations

### V3.1 - Mobile
- Mobile app for referees (result entry)
- Push notifications

### V4.0 - Cloud
- Cloud deployment option
- Federation rankings integration
- Online tournament registration

### Future Considerations
- Doubles support
- Team events
- ITTF result export format

## License

Private project. Contact maintainer for licensing information.
