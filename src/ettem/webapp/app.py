"""FastAPI web application for Easy Table Tennis Event Manager."""

import math
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from ettem.models import Match, MatchStatus, Pair, Player, Set, Team, detect_event_type, is_doubles_category, is_teams_category
from ettem.standings import calculate_standings
from ettem.storage import (
    DatabaseManager,
    BracketRepository,
    GroupRepository,
    MatchRepository,
    MatchORM,
    PairORM,
    PairRepository,
    PlayerORM,
    PlayerRepository,
    ScheduleSlotRepository,
    StandingRepository,
    TournamentRepository,
    migrate_v24_doubles,
    migrate_v25_teams,
    TeamRepository,
    TeamMatchDetailRepository,
    TeamORM,
    TeamMatchDetailORM,
)
from ettem.webapp.helpers import CompetitorDisplay, get_competitor_display
from ettem.validation import validate_match_sets, validate_tt_set, validate_walkover
from ettem.i18n import load_strings, get_language_from_env, clear_cache as clear_i18n_cache

# Clear i18n cache on app reload to pick up translation changes
clear_i18n_cache()
from ettem import pdf_generator
from ettem.paths import get_templates_dir, get_static_dir
from ettem.licensing import get_current_license, get_current_license_with_online, validate_license_key, save_license, load_license, clear_license, LicenseInfo

# Initialize FastAPI app
app = FastAPI(title="Easy Table Tennis Event Manager")

# Add session middleware for flash messages
app.add_middleware(
    SessionMiddleware,
    secret_key="ettem-secret-key-change-in-production-2024"  # TODO: Move to config
)


# License verification middleware
@app.middleware("http")
async def license_middleware(request: Request, call_next):
    """Verify license on every request, redirect to activation if invalid."""
    # Allow these paths without license check
    allowed_paths = ["/license", "/static", "/favicon.ico"]

    path = request.url.path

    # Check if path is allowed without license
    if any(path.startswith(p) for p in allowed_paths):
        return await call_next(request)

    # Check license validity (with online validation when needed)
    is_valid, license_info, error = get_current_license_with_online()

    if not is_valid:
        # Redirect to license activation page
        return RedirectResponse(url="/license/activate", status_code=303)

    # License is valid, continue with request
    # Store license info in request state for use in templates
    request.state.license_info = license_info

    return await call_next(request)


# Setup templates directory (supports PyInstaller frozen mode)
templates_dir = get_templates_dir()
templates = Jinja2Templates(directory=str(templates_dir))

# Add custom Jinja2 filters
import json
templates.env.filters['from_json'] = json.loads

# Translation helper function for templates
def make_translation_function(strings: dict, lang: str):
    """Create a translation function with dot notation support.

    Usage in templates: {{ t('webapp.index.welcome') }}
    With formatting: {{ t('webapp.match.score', p1='Juan', p2='Pedro') }}
    """
    def t(key: str, **kwargs) -> str:
        value = strings
        for part in key.split('.'):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                # Return key if not found (for debugging)
                return f"[{key}]"

        if isinstance(value, str):
            if kwargs:
                try:
                    return value.format(**kwargs)
                except KeyError:
                    return value
            return value
        return f"[{key}]"

    return t

# Setup static files directory (supports PyInstaller frozen mode)
static_dir = get_static_dir()
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Database manager (shared instance)
db_manager = DatabaseManager()
db_manager.create_tables()  # Ensure tables exist


def migrate_matches_add_category():
    """
    Migration: Add 'category' column to matches table if it doesn't exist.
    Also migrates existing bracket matches by inferring category from players.
    """
    from sqlalchemy import text
    session = db_manager.get_session()

    try:
        # Check if column exists by trying to query it
        session.execute(text("SELECT category FROM matches LIMIT 1"))
        print("[MIGRATION] Column 'category' already exists in matches table")
    except Exception:
        # Column doesn't exist, add it
        print("[MIGRATION] Adding 'category' column to matches table...")
        session.execute(text("ALTER TABLE matches ADD COLUMN category VARCHAR(20)"))
        session.commit()
        print("[MIGRATION] Column 'category' added successfully")

        # Migrate existing bracket matches by inferring category from players
        print("[MIGRATION] Migrating existing bracket matches...")
        matches = session.execute(text("""
            SELECT m.id, m.player1_id, m.player2_id, m.group_id
            FROM matches m
            WHERE m.group_id IS NULL AND m.category IS NULL
        """)).fetchall()

        for match in matches:
            match_id = match[0]
            player1_id = match[1]
            player2_id = match[2]

            # Get category from player1 or player2
            category = None
            if player1_id:
                result = session.execute(text(f"SELECT categoria FROM players WHERE id = {player1_id}")).fetchone()
                if result:
                    category = result[0]
            if not category and player2_id:
                result = session.execute(text(f"SELECT categoria FROM players WHERE id = {player2_id}")).fetchone()
                if result:
                    category = result[0]

            if category:
                session.execute(text(f"UPDATE matches SET category = '{category}' WHERE id = {match_id}"))

        session.commit()
        print(f"[MIGRATION] Migrated {len(matches)} bracket matches")

    session.close()


def migrate_bracket_slots_add_tournament_id():
    """
    Migration: Clean up duplicate bracket slots by migrating data from old slots
    (without tournament_id) to new slots (with tournament_id).
    """
    from sqlalchemy import text
    from ettem.storage import BracketSlotORM, TournamentORM
    session = db_manager.get_session()

    # Get current tournament
    current_tournament = session.query(TournamentORM).filter(TournamentORM.is_current == True).first()
    if not current_tournament:
        session.close()
        return

    tournament_id = current_tournament.id

    # Find slots without tournament_id
    old_slots = session.query(BracketSlotORM).filter(BracketSlotORM.tournament_id == None).all()

    if not old_slots:
        session.close()
        return

    print(f"[MIGRATION] Found {len(old_slots)} bracket slots without tournament_id")
    migrated = 0

    for old_slot in old_slots:
        # Find matching new slot with tournament_id
        new_slot = session.query(BracketSlotORM).filter(
            BracketSlotORM.category == old_slot.category,
            BracketSlotORM.tournament_id == tournament_id,
            BracketSlotORM.round_type == old_slot.round_type,
            BracketSlotORM.slot_number == old_slot.slot_number
        ).first()

        if new_slot and old_slot.player_id:
            # Migrate player data to new slot
            new_slot.player_id = old_slot.player_id
            new_slot.is_bye = old_slot.is_bye
            new_slot.advanced_by_bye = old_slot.advanced_by_bye
            new_slot.same_country_warning = old_slot.same_country_warning
            migrated += 1

        # Delete old slot
        session.delete(old_slot)

    session.commit()
    print(f"[MIGRATION] Migrated {migrated} slots, deleted {len(old_slots)} old slots")
    session.close()


def migrate_scheduler_tables():
    """
    Migration: Add scheduler columns to tournaments table and create scheduler tables.
    """
    from sqlalchemy import text
    session = db_manager.get_session()

    # Add scheduler columns to tournaments table
    columns_to_add = [
        ("num_tables", "INTEGER DEFAULT 4"),
        ("default_match_duration", "INTEGER DEFAULT 30"),
        ("min_rest_time", "INTEGER DEFAULT 10"),
    ]

    for col_name, col_type in columns_to_add:
        try:
            session.execute(text(f"SELECT {col_name} FROM tournaments LIMIT 1"))
        except Exception:
            print(f"[MIGRATION] Adding '{col_name}' column to tournaments table...")
            session.execute(text(f"ALTER TABLE tournaments ADD COLUMN {col_name} {col_type}"))
            session.commit()

    # Create sessions table if not exists
    try:
        session.execute(text("SELECT id FROM sessions LIMIT 1"))
    except Exception:
        print("[MIGRATION] Creating 'sessions' table...")
        session.execute(text("""
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL REFERENCES tournaments(id),
                name VARCHAR(100) NOT NULL,
                date DATETIME NOT NULL,
                start_time VARCHAR(5) NOT NULL,
                end_time VARCHAR(5) NOT NULL,
                "order" INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        session.commit()
        print("[MIGRATION] Table 'sessions' created")

    # Create schedule_slots table if not exists
    try:
        session.execute(text("SELECT id FROM schedule_slots LIMIT 1"))
    except Exception:
        print("[MIGRATION] Creating 'schedule_slots' table...")
        session.execute(text("""
            CREATE TABLE schedule_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES sessions(id),
                match_id INTEGER NOT NULL REFERENCES matches(id),
                table_number INTEGER NOT NULL,
                start_time VARCHAR(5) NOT NULL,
                duration INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        session.commit()
        print("[MIGRATION] Table 'schedule_slots' created")

    # Add is_finalized column to sessions table if not exists
    try:
        session.execute(text("SELECT is_finalized FROM sessions LIMIT 1"))
    except Exception:
        print("[MIGRATION] Adding 'is_finalized' column to sessions table...")
        session.execute(text("ALTER TABLE sessions ADD COLUMN is_finalized INTEGER NOT NULL DEFAULT 0"))
        session.commit()
        print("[MIGRATION] Column 'is_finalized' added to sessions")

    # Create time_slots table if not exists
    try:
        session.execute(text("SELECT id FROM time_slots LIMIT 1"))
    except Exception:
        print("[MIGRATION] Creating 'time_slots' table...")
        session.execute(text("""
            CREATE TABLE time_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES sessions(id),
                slot_number INTEGER NOT NULL,
                start_time VARCHAR(5) NOT NULL,
                duration_minutes INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        session.commit()
        print("[MIGRATION] Table 'time_slots' created")

    session.close()


def migrate_matches_add_tournament_id():
    """
    Migration: Add 'tournament_id' column to matches table if it doesn't exist.
    Also migrates existing matches by inferring tournament_id from groups or bracket context.
    """
    from sqlalchemy import text
    from ettem.storage import TournamentORM, GroupORM
    session = db_manager.get_session()

    try:
        # Check if column exists by trying to query it
        session.execute(text("SELECT tournament_id FROM matches LIMIT 1"))
        print("[MIGRATION] Column 'tournament_id' already exists in matches table")
    except Exception:
        # Column doesn't exist, add it
        print("[MIGRATION] Adding 'tournament_id' column to matches table...")
        session.execute(text("ALTER TABLE matches ADD COLUMN tournament_id INTEGER REFERENCES tournaments(id)"))
        session.commit()
        print("[MIGRATION] Column 'tournament_id' added successfully")

        # Get current tournament
        current_tournament = session.query(TournamentORM).filter(TournamentORM.is_current == True).first()
        if current_tournament:
            # Migrate matches with group_id (RR matches) - get tournament from group
            print("[MIGRATION] Migrating RR matches tournament_id from groups...")
            session.execute(text("""
                UPDATE matches
                SET tournament_id = (SELECT tournament_id FROM groups WHERE groups.id = matches.group_id)
                WHERE group_id IS NOT NULL AND tournament_id IS NULL
            """))
            session.commit()

            # Migrate bracket matches (no group_id) - assign to current tournament
            print("[MIGRATION] Migrating bracket matches to current tournament...")
            session.execute(text(f"""
                UPDATE matches
                SET tournament_id = {current_tournament.id}
                WHERE group_id IS NULL AND tournament_id IS NULL
            """))
            session.commit()
            print("[MIGRATION] Match tournament_id migration complete")

    session.close()


def migrate_matches_add_best_of():
    """
    Migration: Add 'best_of' column to matches table if it doesn't exist.
    Default value is 5 (best of 5 sets).
    """
    from sqlalchemy import text
    session = db_manager.get_session()

    try:
        # Check if column exists by trying to query it
        session.execute(text("SELECT best_of FROM matches LIMIT 1"))
        print("[MIGRATION] Column 'best_of' already exists in matches table")
    except Exception:
        # Column doesn't exist, add it
        print("[MIGRATION] Adding 'best_of' column to matches table...")
        session.execute(text("ALTER TABLE matches ADD COLUMN best_of INTEGER NOT NULL DEFAULT 5"))
        session.commit()
        print("[MIGRATION] Column 'best_of' added successfully")

    session.close()


def migrate_matches_fill_category_from_group():
    """Fill category for matches that don't have it but belong to a group."""
    from sqlalchemy import text
    session = db_manager.get_session()

    try:
        # Find matches without category that have a group_id
        result = session.execute(text("""
            UPDATE matches
            SET category = (SELECT category FROM groups WHERE groups.id = matches.group_id)
            WHERE matches.category IS NULL
            AND matches.group_id IS NOT NULL
            AND EXISTS (SELECT 1 FROM groups WHERE groups.id = matches.group_id AND groups.category IS NOT NULL)
        """))
        session.commit()
        updated = result.rowcount
        if updated > 0:
            print(f"[MIGRATION] Updated {updated} matches with category from their group")
        else:
            print("[MIGRATION] All matches already have category assigned")
    except Exception as e:
        print(f"[MIGRATION] Error filling match categories: {e}")
        session.rollback()

    session.close()


# Run migrations on startup (order matters!)
migrate_matches_add_category()
migrate_matches_add_tournament_id()  # Add tournament_id to matches
migrate_matches_add_best_of()  # Add best_of format to matches
migrate_scheduler_tables()  # Must run before bracket_slots migration since it adds columns to tournaments
migrate_v24_doubles(db_manager.engine)  # Add doubles support (pairs table + nullable columns)
migrate_v25_teams(db_manager.engine)  # Add teams support (teams + team_match_details tables)
migrate_bracket_slots_add_tournament_id()
migrate_matches_fill_category_from_group()  # Fill missing categories from groups


def get_db_session():
    """Get database session."""
    return db_manager.get_session()


def get_local_ip() -> str:
    """Get the local IP address for network access."""
    import socket
    try:
        # Create a socket to determine the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def render_template(template_name: str, context: Dict[str, Any]) -> HTMLResponse:
    """
    Render a template with i18n support.

    Automatically adds i18n strings and global data to the context.

    Args:
        template_name: Name of the template file
        context: Template context (must include 'request')

    Returns:
        HTMLResponse with rendered template
    """
    # Get language from: 1) query param, 2) session, 3) environment
    request = context.get("request")
    lang = None

    if request:
        # Check query parameter first
        lang_param = request.query_params.get("lang")
        if lang_param in ["es", "en"]:
            lang = lang_param
            # Save to session for persistence
            if hasattr(request, "session"):
                request.session["lang"] = lang
        elif hasattr(request, "session"):
            # Check session
            lang = request.session.get("lang")

    # Fallback to environment
    if not lang:
        lang = get_language_from_env()

    try:
        i18n_strings = load_strings(lang)
    except (ValueError, FileNotFoundError):
        # Fallback to empty dict if strings can't be loaded
        i18n_strings = {}

    # Add i18n to context - t() function for dot notation access
    context["t"] = make_translation_function(i18n_strings, lang)
    context["lang"] = lang

    # Add global data (categories for sidebar) - filtered by current tournament
    session = None
    try:
        session = get_db_session()
        player_repo = PlayerRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Get players for current tournament only
        all_players = player_repo.get_all(tournament_id=tournament_id)
        categories = sorted(set(p.categoria for p in all_players))
        context["categories"] = categories

        # Add current tournament to context for all templates
        if "current_tournament" not in context:
            context["current_tournament"] = current_tournament

        # Add license info to context for display in UI
        _, license_info, _ = get_current_license()
        context["license_info"] = license_info

        print(f"[DEBUG] Categories loaded for tournament {tournament_id}: {categories}")
    except Exception as e:
        print(f"[ERROR] Failed to load categories: {e}")
        import traceback
        traceback.print_exc()
        context["categories"] = []
    finally:
        if session:
            session.close()

    # Extract flash message and form values from session if available
    request = context.get("request")
    if request and hasattr(request, "session"):
        flash_message = request.session.pop("flash_message", None)
        flash_type = request.session.pop("flash_type", "info")
        form_values = request.session.pop("form_values", None)

        if flash_message:
            # Use repr() to safely print any Unicode characters
            try:
                print(f"[DEBUG] Flash message found: {repr(flash_message)} (type: {flash_type})")
            except:
                print(f"[DEBUG] Flash message found (type: {flash_type})")
            context["flash_message"] = flash_message
            context["flash_type"] = flash_type

        if form_values:
            print(f"[DEBUG] Form values found: {form_values}")
            context["form_values"] = form_values

    return templates.TemplateResponse(context["request"], template_name, context)


# ============================================================================
# Tournament Management Routes
# ============================================================================


@app.get("/tournaments", response_class=HTMLResponse)
async def tournaments_page(request: Request):
    """Tournament management page."""
    session = get_db_session()
    tournament_repo = TournamentRepository(session)

    current_tournament = tournament_repo.get_current()
    active_tournaments = tournament_repo.get_active()
    archived_tournaments = tournament_repo.get_archived()

    return render_template(
        "tournaments.html",
        {
            "request": request,
            "current_tournament": current_tournament,
            "active_tournaments": active_tournaments,
            "archived_tournaments": archived_tournaments
        }
    )


@app.post("/tournaments/create")
async def create_tournament(
    request: Request,
    name: str = Form(...),
    date: str = Form(None),
    location: str = Form(None)
):
    """Create a new tournament."""
    from datetime import datetime as dt

    session = get_db_session()
    tournament_repo = TournamentRepository(session)

    # Parse date if provided
    parsed_date = None
    if date:
        try:
            parsed_date = dt.strptime(date, "%Y-%m-%d")
        except ValueError:
            pass

    # Create tournament
    tournament = tournament_repo.create(
        name=name,
        date=parsed_date,
        location=location if location else None
    )

    # If this is the first tournament, set it as current
    if len(tournament_repo.get_all()) == 1:
        tournament_repo.set_current(tournament.id)

    request.session["flash_message"] = f"Torneo '{name}' creado exitosamente"
    request.session["flash_type"] = "success"

    return RedirectResponse(url="/tournaments", status_code=303)


@app.post("/tournaments/{tournament_id}/set-current")
async def set_current_tournament(request: Request, tournament_id: int):
    """Set a tournament as the current active one."""
    session = get_db_session()
    tournament_repo = TournamentRepository(session)

    tournament = tournament_repo.get_by_id(tournament_id)
    if tournament:
        tournament_repo.set_current(tournament_id)
        request.session["flash_message"] = f"Torneo '{tournament.name}' seleccionado"
        request.session["flash_type"] = "success"
    else:
        request.session["flash_message"] = "Torneo no encontrado"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/tournaments", status_code=303)


@app.post("/tournaments/{tournament_id}/archive")
async def archive_tournament(request: Request, tournament_id: int):
    """Archive a tournament."""
    session = get_db_session()
    tournament_repo = TournamentRepository(session)

    tournament = tournament_repo.get_by_id(tournament_id)
    if tournament:
        # If archiving the current tournament, unset it
        if tournament.is_current:
            tournament_repo.set_current(0)  # This will unset all
        tournament_repo.update_status(tournament_id, "archived")
        request.session["flash_message"] = f"Torneo '{tournament.name}' archivado"
        request.session["flash_type"] = "success"
    else:
        request.session["flash_message"] = "Torneo no encontrado"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/tournaments", status_code=303)


@app.post("/tournaments/{tournament_id}/restore")
async def restore_tournament(request: Request, tournament_id: int):
    """Restore an archived tournament."""
    session = get_db_session()
    tournament_repo = TournamentRepository(session)

    tournament = tournament_repo.get_by_id(tournament_id)
    if tournament:
        tournament_repo.update_status(tournament_id, "active")
        request.session["flash_message"] = f"Torneo '{tournament.name}' restaurado"
        request.session["flash_type"] = "success"
    else:
        request.session["flash_message"] = "Torneo no encontrado"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/tournaments", status_code=303)


@app.post("/tournaments/{tournament_id}/delete")
async def delete_tournament(request: Request, tournament_id: int):
    """Delete a tournament permanently."""
    session = get_db_session()
    tournament_repo = TournamentRepository(session)

    tournament = tournament_repo.get_by_id(tournament_id)
    if tournament:
        name = tournament.name
        tournament_repo.delete(tournament_id)
        request.session["flash_message"] = f"Torneo '{name}' eliminado permanentemente"
        request.session["flash_type"] = "success"
    else:
        request.session["flash_message"] = "Torneo no encontrado"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/tournaments", status_code=303)


# ============================================================================
# License Routes
# ============================================================================


@app.get("/license/activate", response_class=HTMLResponse)
async def license_activate_page(request: Request):
    """Show license activation page."""
    # Get language from session or environment
    lang = None
    if hasattr(request, "session"):
        lang = request.session.get("lang")
    if not lang:
        lang = get_language_from_env()

    try:
        i18n_strings = load_strings(lang)
    except (ValueError, FileNotFoundError):
        i18n_strings = {}

    t = make_translation_function(i18n_strings, lang)

    # Check if there's an expired license to show info
    _, license_info, _ = get_current_license()

    context = {
        "request": request,
        "t": t,
        "lang": lang,
        "error": None,
        "expired_info": license_info if license_info and license_info.is_expired else None,
        "submitted_key": None
    }

    return templates.TemplateResponse(request, "license_activation.html", context)


@app.post("/license/activate")
async def license_activate(request: Request, license_key: str = Form(...)):
    """Process license activation."""
    # Get language from session or environment
    lang = None
    if hasattr(request, "session"):
        lang = request.session.get("lang")
    if not lang:
        lang = get_language_from_env()

    try:
        i18n_strings = load_strings(lang)
    except (ValueError, FileNotFoundError):
        i18n_strings = {}

    t = make_translation_function(i18n_strings, lang)

    # Validate the license key
    is_valid, license_info, error = validate_license_key(license_key)

    if not is_valid:
        # Show error
        context = {
            "request": request,
            "t": t,
            "lang": lang,
            "error": error or t("license.invalid_key"),
            "expired_info": license_info if license_info and license_info.is_expired else None,
            "submitted_key": license_key
        }
        return templates.TemplateResponse(request, "license_activation.html", context)

    # Try online activation BEFORE saving locally (to enforce machine limits)
    online_warning = None
    try:
        from ettem.license_online import activate_online
        ok, online_error, extra = activate_online(license_key)
        if not ok:
            if extra and extra.get("machines"):
                # Machine limit reached - do NOT save license locally
                context = {
                    "request": request,
                    "t": t,
                    "lang": lang,
                    "error": online_error,
                    "expired_info": None,
                    "submitted_key": license_key,
                    "machine_limit_info": extra,
                }
                return templates.TemplateResponse(request, "license_activation.html", context)
            online_warning = t("license.online_warning")
    except Exception:
        pass  # Online module unavailable, proceed offline

    # Save the license locally only after online check passed (or was skipped)
    save_license(license_key)

    # Set success flash message
    if hasattr(request, "session"):
        msg = t("license.activation_success")
        if online_warning:
            request.session["flash_message"] = f"{msg} ({online_warning})"
            request.session["flash_type"] = "warning"
        else:
            request.session["flash_message"] = msg
            request.session["flash_type"] = "success"

    # Redirect to home page
    return RedirectResponse(url="/", status_code=303)


@app.post("/license/deactivate-online")
async def license_deactivate_online(request: Request):
    """Deactivate this machine from online license (free a slot)."""
    try:
        from ettem.license_online import deactivate_online
        key = load_license()
        if key:
            deactivate_online(key)
    except Exception:
        pass

    # Clear local license
    clear_license()

    return RedirectResponse(url="/license/activate", status_code=303)


# ============================================================================
# Main Application Routes
# ============================================================================


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page - list all categories for current tournament."""
    session = get_db_session()
    player_repo = PlayerRepository(session)
    tournament_repo = TournamentRepository(session)

    # Get current tournament - redirect to tournaments page if none exists
    current_tournament = tournament_repo.get_current()
    if not current_tournament:
        return RedirectResponse(url="/tournaments", status_code=303)

    tournament_id = current_tournament.id

    # Get all unique categories for current tournament
    all_players = player_repo.get_all(tournament_id=tournament_id)
    categories = sorted(set(p.categoria for p in all_players))

    return render_template(
        "index.html",
        {
            "request": request,
            "categories": categories,
            "current_tournament": current_tournament
        }
    )


@app.get("/category/{category}", response_class=HTMLResponse)
async def view_category(request: Request, category: str):
    """View category dashboard."""
    session = get_db_session()
    group_repo = GroupRepository(session)
    player_repo = PlayerRepository(session)
    match_repo = MatchRepository(session)
    tournament_repo = TournamentRepository(session)
    team_repo = TeamRepository(session)

    # Get current tournament
    current_tournament = tournament_repo.get_current()
    tournament_id = current_tournament.id if current_tournament else None

    # Get groups for this category in current tournament
    groups = group_repo.get_by_category(category, tournament_id=tournament_id)

    is_teams_cat = is_teams_category(category)

    # Get players/teams and match stats for each group
    groups_data = []
    for group in groups:
        if is_teams_cat:
            # Group player_ids contain team IDs for teams categories
            players = [team_repo.get_by_id(tid) for tid in group.player_ids]
        else:
            players = [player_repo.get_by_id(pid) for pid in group.player_ids]

        # Get match progress
        matches = match_repo.get_by_group(group.id)
        total_matches = len(matches)
        completed_matches = len([m for m in matches if m.winner_id is not None])

        groups_data.append({
            "group": group,
            "players": [p for p in players if p],  # Filter out None
            "total_matches": total_matches,
            "completed_matches": completed_matches,
        })

    # Check if this category has a direct bracket (no groups)
    has_direct_bracket = False
    if not groups:
        bracket_repo = BracketRepository(session)
        bracket_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
        has_direct_bracket = len(bracket_slots) > 0

    return render_template(
        "category.html",
        {
            "request": request,
            "category": category,
            "groups": groups_data,
            "has_direct_bracket": has_direct_bracket,
        }
    )


@app.get("/group/{group_id}/matches", response_class=HTMLResponse)
async def view_group_matches(request: Request, group_id: int):
    """View matches for a specific group."""
    session = get_db_session()
    group_repo = GroupRepository(session)
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)
    pair_repo = PairRepository(session)
    team_repo = TeamRepository(session)
    schedule_repo = ScheduleSlotRepository(session)

    # Get group
    group = group_repo.get_by_id(group_id)
    if not group:
        return HTMLResponse(content="Group not found", status_code=404)

    # Get matches
    match_orms = match_repo.get_by_group(group_id)

    # Convert to domain models with competitor names
    matches_data = []
    for m_orm in match_orms:
        player1 = get_competitor_display(m_orm, 1, player_repo, pair_repo, team_repo)
        player2 = get_competitor_display(m_orm, 2, player_repo, pair_repo, team_repo)

        # Get schedule info
        schedule_slot = schedule_repo.get_by_match(m_orm.id)
        table_number = schedule_slot.table_number if schedule_slot else None
        scheduled_time = schedule_slot.start_time if schedule_slot else None

        # Convert sets
        sets = [
            Set(
                set_number=s["set_number"],
                player1_points=s["player1_points"],
                player2_points=s["player2_points"],
            )
            for s in m_orm.sets
        ]

        match = Match(
            id=m_orm.id,
            player1_id=m_orm.competitor1_id or 0,
            player2_id=m_orm.competitor2_id or 0,
            group_id=m_orm.group_id,
            round_type=m_orm.round_type,
            round_name=m_orm.round_name,
            match_number=m_orm.match_number,
            status=m_orm.status,
            sets=sets,
            winner_id=m_orm.winner_id,
        )

        matches_data.append({
            "match": match,
            "player1": player1,
            "player2": player2,
            "player1_sets": match.player1_sets_won,
            "player2_sets": match.player2_sets_won,
            "table_number": table_number,
            "scheduled_time": scheduled_time,
        })

    is_teams_cat = is_teams_category(group.category)

    return render_template(
        "group_matches.html",
        {
            "request": request,
            "group": group,
            "matches": matches_data,
            "category": group.category,
            "is_teams": is_teams_cat,
        }
    )


@app.get("/match/{match_id}/enter-result", response_class=HTMLResponse)
async def enter_result_form(request: Request, match_id: int, return_to: Optional[str] = None):
    """Show form to enter match result."""
    session = get_db_session()
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)
    pair_repo = PairRepository(session)
    team_repo = TeamRepository(session)
    schedule_repo = ScheduleSlotRepository(session)

    # Get match
    match_orm = match_repo.get_by_id(match_id)
    if not match_orm:
        return HTMLResponse(content="Match not found", status_code=404)

    player1 = player_repo.get_by_id(match_orm.player1_id) if match_orm.player1_id else None
    player2 = player_repo.get_by_id(match_orm.player2_id) if match_orm.player2_id else None

    # Get display objects (handles doubles pair names and team names)
    from ettem.webapp.helpers import get_competitor_display
    from ettem.models import is_doubles_category
    display1 = get_competitor_display(match_orm, 1, player_repo, pair_repo, team_repo)
    display2 = get_competitor_display(match_orm, 2, player_repo, pair_repo, team_repo)
    category = match_orm.category or (player1.categoria if player1 else "")
    _is_doubles = is_doubles_category(category)

    # Get match format (best_of) - stored directly on the match
    best_of = match_orm.best_of if hasattr(match_orm, 'best_of') and match_orm.best_of else 5

    # Get schedule info
    schedule_slot = schedule_repo.get_by_match(match_id)
    table_number = schedule_slot.table_number if schedule_slot else None
    scheduled_time = schedule_slot.start_time if schedule_slot else None

    # Validate that both players are defined (not TBD)
    if not player1 or not player2:
        request.session["flash_message"] = "No se puede ingresar resultado: ambos jugadores deben estar definidos"
        request.session["flash_type"] = "error"

        # Redirect to appropriate page
        if match_orm.group_id:
            return RedirectResponse(url=f"/group/{match_orm.group_id}/matches", status_code=303)
        else:
            if category:
                return RedirectResponse(url=f"/bracket/{category}", status_code=303)
            else:
                return RedirectResponse(url="/", status_code=303)

    # Get preserved form values (if any, from validation error)
    form_values = request.session.pop("form_values", None)
    if form_values:
        print(f"[DEBUG] Form values found: {form_values}")

    return render_template(
        "enter_result.html",
        {
            "request": request,
            "match": match_orm,
            "player1": player1,
            "player2": player2,
            "display1": display1,
            "display2": display2,
            "is_doubles": _is_doubles,
            "category": category,
            "form_values": form_values,
            "table_number": table_number,
            "scheduled_time": scheduled_time,
            "return_to": return_to,
            "best_of": best_of,
        }
    )


@app.post("/match/{match_id}/save-result")
async def save_result(
    request: Request,
    match_id: int,
    is_walkover: Optional[str] = Form(None),
    winner_id: Optional[str] = Form(None),
    set1_p1: Optional[str] = Form(None),
    set1_p2: Optional[str] = Form(None),
    set2_p1: Optional[str] = Form(None),
    set2_p2: Optional[str] = Form(None),
    set3_p1: Optional[str] = Form(None),
    set3_p2: Optional[str] = Form(None),
    set4_p1: Optional[str] = Form(None),
    set4_p2: Optional[str] = Form(None),
    set5_p1: Optional[str] = Form(None),
    set5_p2: Optional[str] = Form(None),
    set6_p1: Optional[str] = Form(None),
    set6_p2: Optional[str] = Form(None),
    set7_p1: Optional[str] = Form(None),
    set7_p2: Optional[str] = Form(None),
    return_to: Optional[str] = Form(None),
):
    """Save match result."""
    session = get_db_session()
    match_repo = MatchRepository(session)

    # Helper to build redirect URL preserving return_to parameter
    def enter_result_url():
        url = f"/match/{match_id}/enter-result"
        if return_to:
            url += f"?return_to={return_to}"
        return url

    # Get match
    match_orm = match_repo.get_by_id(match_id)
    if not match_orm:
        request.session["flash_message"] = "Partido no encontrado"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/", status_code=303)

    # Get match format (best_of) - stored directly on the match
    best_of = match_orm.best_of if hasattr(match_orm, 'best_of') and match_orm.best_of else 5

    # Validate that both players are defined (not TBD)
    if not match_orm.player1_id or not match_orm.player2_id:
        request.session["flash_message"] = "No se puede ingresar resultado: ambos jugadores deben estar definidos"
        request.session["flash_type"] = "error"
        if match_orm.group_id:
            return RedirectResponse(url=f"/group/{match_orm.group_id}/matches", status_code=303)
        else:
            return RedirectResponse(url="/", status_code=303)

    # For bracket matches, validate that previous rounds are complete
    if match_orm.group_id is None:  # Bracket match
        player_repo = PlayerRepository(session)
        player = player_repo.get_by_id(match_orm.player1_id)
        if player:
            is_valid, error_msg = validate_bracket_round_order(match_orm, player.categoria, session)
            if not is_valid:
                request.session["flash_message"] = error_msg
                request.session["flash_type"] = "error"
                return RedirectResponse(url=enter_result_url(), status_code=303)

    # Helper function to parse integer or None
    def parse_int(value: Optional[str]) -> Optional[int]:
        if value is None or value == "" or value.strip() == "":
            return None
        try:
            return int(value)
        except (ValueError, AttributeError):
            return None

    # Convert form data
    is_wo = is_walkover == "true" if is_walkover else False
    winner_id_int = parse_int(winner_id)
    winner_id_final = None  # Initialize winner_id_final

    if is_wo:
        # Walkover - validate and set winner
        is_valid, error_msg = validate_walkover(
            match_orm.player1_id, match_orm.player2_id, winner_id_int
        )
        if not is_valid:
            request.session["flash_message"] = f"Error en walkover: {error_msg}"
            request.session["flash_type"] = "error"
            return RedirectResponse(url=enter_result_url(), status_code=303)

        match_orm.status = MatchStatus.WALKOVER.value
        match_orm.winner_id = winner_id_int
        winner_id_final = winner_id_int  # Set winner_id_final for bracket advancement

        # Record 3-0 sets for the winner (11-0 in each set)
        wo_sets = []
        for i in range(1, 4):  # 3 sets
            if winner_id_int == match_orm.player1_id:
                wo_sets.append({"set_number": i, "player1_points": 11, "player2_points": 0})
            else:
                wo_sets.append({"set_number": i, "player1_points": 0, "player2_points": 11})

        match_repo.update_result(
            match_id=match_id,
            sets=wo_sets,
            winner_id=winner_id_int,
            status=MatchStatus.WALKOVER.value
        )
    else:
        # Normal match - collect sets
        sets_data = []
        set_inputs = [
            (parse_int(set1_p1), parse_int(set1_p2)),
            (parse_int(set2_p1), parse_int(set2_p2)),
            (parse_int(set3_p1), parse_int(set3_p2)),
            (parse_int(set4_p1), parse_int(set4_p2)),
            (parse_int(set5_p1), parse_int(set5_p2)),
            (parse_int(set6_p1), parse_int(set6_p2)),
            (parse_int(set7_p1), parse_int(set7_p2)),
        ]

        # Collect valid sets and validate each one
        for idx, (p1_points, p2_points) in enumerate(set_inputs, start=1):
            if p1_points is not None and p2_points is not None:
                # Validate this set
                is_valid, error_msg = validate_tt_set(p1_points, p2_points)
                if not is_valid:
                    request.session["flash_message"] = f"Error en Set {idx}: {error_msg}"
                    request.session["flash_type"] = "error"
                    # Preserve form values for re-display
                    form_vals = {
                        "set1_p1": set1_p1, "set1_p2": set1_p2,
                        "set2_p1": set2_p1, "set2_p2": set2_p2,
                        "set3_p1": set3_p1, "set3_p2": set3_p2,
                        "set4_p1": set4_p1, "set4_p2": set4_p2,
                        "set5_p1": set5_p1, "set5_p2": set5_p2,
                        "set6_p1": set6_p1, "set6_p2": set6_p2,
                        "set7_p1": set7_p1, "set7_p2": set7_p2,
                    }
                    request.session["form_values"] = form_vals
                    print(f"[DEBUG] Set error - saved form values: {form_vals}")
                    return RedirectResponse(url=enter_result_url(), status_code=303)

                sets_data.append({
                    "set_number": idx,
                    "player1_points": p1_points,
                    "player2_points": p2_points,
                })

        # Check if we have any sets at all
        if not sets_data:
            request.session["flash_message"] = "Error: Debe ingresar al menos un set"
            request.session["flash_type"] = "error"
            # Save form values even when no sets were entered
            raw_inputs = [set1_p1, set1_p2, set2_p1, set2_p2, set3_p1, set3_p2, set4_p1, set4_p2, set5_p1, set5_p2, set6_p1, set6_p2, set7_p1, set7_p2]
            form_vals = {}
            for i in range(1, 8):
                form_vals[f"set{i}_p1"] = raw_inputs[(i-1)*2] or ""
                form_vals[f"set{i}_p2"] = raw_inputs[(i-1)*2 + 1] or ""
            request.session["form_values"] = form_vals
            return RedirectResponse(url=enter_result_url(), status_code=303)

        # Validate the complete match
        sets_tuples = [(s["player1_points"], s["player2_points"]) for s in sets_data]
        is_valid, error_msg = validate_match_sets(sets_tuples, best_of=best_of)
        if not is_valid:
            error_text = f"Error en el partido: {error_msg}"
            print(f"[DEBUG] Saving flash message to session: {error_text}")
            request.session["flash_message"] = error_text
            request.session["flash_type"] = "error"
            # Save RAW form values (as submitted by user) to preserve them on error
            raw_inputs = [set1_p1, set1_p2, set2_p1, set2_p2, set3_p1, set3_p2, set4_p1, set4_p2, set5_p1, set5_p2, set6_p1, set6_p2, set7_p1, set7_p2]
            form_vals = {}
            for i in range(1, 8):
                form_vals[f"set{i}_p1"] = raw_inputs[(i-1)*2] or ""
                form_vals[f"set{i}_p2"] = raw_inputs[(i-1)*2 + 1] or ""
            request.session["form_values"] = form_vals
            print(f"[DEBUG] Saved form values: {form_vals}")
            return RedirectResponse(url=enter_result_url(), status_code=303)

        # Determine winner based on sets won
        p1_sets = sum(1 for s in sets_data if s["player1_points"] > s["player2_points"])
        p2_sets = sum(1 for s in sets_data if s["player2_points"] > s["player1_points"])

        if p1_sets > p2_sets:
            winner_id_final = match_orm.player1_id
        elif p2_sets > p1_sets:
            winner_id_final = match_orm.player2_id
        else:
            # Shouldn't happen in valid match
            winner_id_final = None

        match_repo.update_result(
            match_id=match_id,
            sets=sets_data,
            winner_id=winner_id_final,
            status=MatchStatus.COMPLETED.value
        )

    # For bracket matches, advance the winner to the next round
    if match_orm.group_id is None and winner_id_final:
        # This is a bracket match - get category from match directly or from player
        tournament_repo = TournamentRepository(session)
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None
        category = match_orm.category
        if not category:
            player_repo = PlayerRepository(session)
            player = player_repo.get_by_id(match_orm.player1_id)
            category = player.categoria if player else None
        if category:
            advance_bracket_winner(match_orm, winner_id_final, category, session, tournament_id=tournament_id)

    # For group matches, recalculate standings automatically
    if match_orm.group_id is not None:
        player_repo = PlayerRepository(session)
        standing_repo = StandingRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)

        # Detect event type from category
        group_repo = GroupRepository(session)
        group_obj = group_repo.get_by_id(match_orm.group_id)
        event_type = detect_event_type(group_obj.category) if group_obj else "singles"

        # Get all matches for this group
        group_match_orms = match_repo.get_by_group(match_orm.group_id)

        # Convert to domain models
        matches = []
        for m_orm in group_match_orms:
            sets = [
                Set(
                    set_number=s["set_number"],
                    player1_points=s["player1_points"],
                    player2_points=s["player2_points"],
                )
                for s in m_orm.sets
            ]
            match = Match(
                id=m_orm.id,
                player1_id=m_orm.competitor1_id,
                player2_id=m_orm.competitor2_id,
                group_id=m_orm.group_id,
                round_type=m_orm.round_type,
                status=m_orm.status,
                sets=sets,
                winner_id=m_orm.winner_id,
            )
            matches.append(match)

        # Calculate standings
        standings, _ = calculate_standings(
            matches, match_orm.group_id, player_repo,
            event_type=event_type, pair_repo=pair_repo, team_repo=team_repo,
        )

        # Delete old standings and save new ones
        standing_repo.delete_by_group(match_orm.group_id)
        for standing in standings:
            standing_repo.create(standing)

    # Set success message
    request.session["flash_message"] = "Resultado guardado exitosamente"
    request.session["flash_type"] = "success"

    # Redirect based on return_to parameter or match type
    if return_to == "live":
        return RedirectResponse(url="/admin/live-results", status_code=303)
    elif match_orm.group_id is not None:
        # Group match - redirect to group matches page
        return RedirectResponse(url=f"/group/{match_orm.group_id}/matches", status_code=303)
    else:
        # Bracket match - use match category field directly (works for singles, doubles, teams)
        if hasattr(match_orm, 'category') and match_orm.category:
            return RedirectResponse(url=f"/bracket/{match_orm.category}", status_code=303)
        else:
            # Fallback: get category from player
            player_repo = PlayerRepository(session)
            player = player_repo.get_by_id(match_orm.player1_id)
            if player:
                return RedirectResponse(url=f"/bracket/{player.categoria}", status_code=303)
            else:
                return RedirectResponse(url="/", status_code=303)


@app.post("/match/{match_id}/delete-result")
async def delete_result(request: Request, match_id: int):
    """Delete match result and reset to pending status."""
    from ettem.models import RoundType

    session = get_db_session()
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)

    # Get match
    match_orm = match_repo.get_by_id(match_id)
    if not match_orm:
        request.session["flash_message"] = "Partido no encontrado"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/", status_code=303)

    # For bracket matches, check if the winner has already played in the next round
    category = None
    if match_orm.group_id is None and match_orm.winner_id is not None:
        # This is a bracket match with a result
        tournament_repo = TournamentRepository(session)
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None
        player = player_repo.get_by_id(match_orm.player1_id)
        if player:
            category = player.categoria

            # Check if winner has played in next round
            round_progression = {
                RoundType.ROUND_OF_128.value: RoundType.ROUND_OF_64.value,
                RoundType.ROUND_OF_64.value: RoundType.ROUND_OF_32.value,
                RoundType.ROUND_OF_32.value: RoundType.ROUND_OF_16.value,
                RoundType.ROUND_OF_16.value: RoundType.QUARTERFINAL.value,
                RoundType.QUARTERFINAL.value: RoundType.SEMIFINAL.value,
                RoundType.SEMIFINAL.value: RoundType.FINAL.value,
                RoundType.FINAL.value: None,
            }
            next_round = round_progression.get(match_orm.round_type)

            if next_round:
                # Check if there's a completed match in next round with this winner
                next_round_match = session.query(MatchORM).filter(
                    MatchORM.category == category,
                    MatchORM.group_id == None,
                    MatchORM.round_type == next_round,
                    MatchORM.status == MatchStatus.COMPLETED.value,
                    (MatchORM.player1_id == match_orm.winner_id) | (MatchORM.player2_id == match_orm.winner_id)
                ).first()

                if next_round_match:
                    request.session["flash_message"] = f"No se puede eliminar: el ganador ya tiene resultado en {next_round}. Elimina primero ese resultado."
                    request.session["flash_type"] = "error"
                    return RedirectResponse(url=f"/bracket/{category}", status_code=303)

            # Safe to rollback
            rollback_bracket_advancement(match_orm, match_orm.winner_id, category, session, tournament_id=tournament_id)

    # Reset match to pending state
    match_repo.update_result(
        match_id=match_id,
        sets=[],  # Clear all sets
        winner_id=None,
        status=MatchStatus.PENDING.value
    )

    # For group matches, recalculate standings after deleting result
    if match_orm.group_id is not None:
        standing_repo = StandingRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)

        # Detect event type from category
        group_repo = GroupRepository(session)
        group_obj = group_repo.get_by_id(match_orm.group_id)
        event_type = detect_event_type(group_obj.category) if group_obj else "singles"

        # Get all matches for this group
        group_match_orms = match_repo.get_by_group(match_orm.group_id)

        # Convert to domain models
        matches = []
        for m_orm in group_match_orms:
            sets = [
                Set(
                    set_number=s["set_number"],
                    player1_points=s["player1_points"],
                    player2_points=s["player2_points"],
                )
                for s in m_orm.sets
            ]
            match = Match(
                id=m_orm.id,
                player1_id=m_orm.competitor1_id,
                player2_id=m_orm.competitor2_id,
                group_id=m_orm.group_id,
                round_type=m_orm.round_type,
                status=m_orm.status,
                sets=sets,
                winner_id=m_orm.winner_id,
            )
            matches.append(match)

        # Calculate standings
        standings, _ = calculate_standings(
            matches, match_orm.group_id, player_repo,
            event_type=event_type, pair_repo=pair_repo, team_repo=team_repo,
        )

        # Delete old standings and save new ones
        standing_repo.delete_by_group(match_orm.group_id)
        for standing in standings:
            standing_repo.create(standing)

    # Set success message
    request.session["flash_message"] = "Resultado eliminado exitosamente"
    request.session["flash_type"] = "success"

    # Redirect based on match type (group or bracket)
    if match_orm.group_id is not None:
        # Group match - redirect to group matches page
        return RedirectResponse(url=f"/group/{match_orm.group_id}/matches", status_code=303)
    else:
        # Bracket match - redirect to bracket page
        if category is None:
            player = player_repo.get_by_id(match_orm.player1_id)
            if player:
                category = player.categoria
        if category:
            return RedirectResponse(url=f"/bracket/{category}", status_code=303)
        else:
            return RedirectResponse(url="/", status_code=303)


@app.get("/group/{group_id}/standings", response_class=HTMLResponse)
async def view_standings(request: Request, group_id: int):
    """View standings for a group."""
    session = get_db_session()
    group_repo = GroupRepository(session)
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)
    pair_repo = PairRepository(session)
    team_repo = TeamRepository(session)
    standing_repo = StandingRepository(session)

    # Get group
    group = group_repo.get_by_id(group_id)
    if not group:
        return HTMLResponse(content="Group not found", status_code=404)

    # Detect event type from category
    event_type = detect_event_type(group.category)

    # Get matches and calculate standings
    match_orms = match_repo.get_by_group(group_id)

    # Convert to domain models using competitor IDs
    matches = []
    for m_orm in match_orms:
        sets = [
            Set(
                set_number=s["set_number"],
                player1_points=s["player1_points"],
                player2_points=s["player2_points"],
            )
            for s in m_orm.sets
        ]
        match = Match(
            id=m_orm.id,
            player1_id=m_orm.competitor1_id or 0,
            player2_id=m_orm.competitor2_id or 0,
            group_id=m_orm.group_id,
            round_type=m_orm.round_type,
            status=m_orm.status,
            sets=sets,
            winner_id=m_orm.winner_id,
        )
        matches.append(match)

    # Calculate standings
    standings, tiebreaker_info = calculate_standings(
        matches, group_id, player_repo,
        event_type=event_type, pair_repo=pair_repo, team_repo=team_repo,
    )

    # Get competitor details
    standings_data = []
    for standing in standings:
        if event_type == "teams":
            team_orm = team_repo.get_by_id(standing.player_id)
            if team_orm:
                competitor = CompetitorDisplay.from_team(team_orm, player_repo=player_repo)
            else:
                competitor = CompetitorDisplay.tbd()
        elif event_type == "doubles":
            pair_orm = pair_repo.get_by_id(standing.player_id)
            if pair_orm:
                p1 = player_repo.get_by_id(pair_orm.player1_id)
                p2 = player_repo.get_by_id(pair_orm.player2_id)
                competitor = CompetitorDisplay.from_pair(pair_orm, p1, p2)
            else:
                competitor = CompetitorDisplay.tbd()
        else:
            player = player_repo.get_by_id(standing.player_id)
            if player:
                competitor = CompetitorDisplay.from_player(player)
            else:
                competitor = CompetitorDisplay.tbd()
        tb_info = tiebreaker_info.get(standing.player_id)
        standings_data.append({
            "standing": standing,
            "player": competitor,
            "tiebreaker": tb_info
        })

    return render_template("standings.html", {
        "request": request,
        "group": group,
        "standings": standings_data,
        "category": group.category,
        "has_tiebreaker": len(tiebreaker_info) > 0
    })


@app.get("/category/{category}/standings", response_class=HTMLResponse)
async def view_category_standings(request: Request, category: str):
    """View standings for all groups in a category."""
    session = get_db_session()
    group_repo = GroupRepository(session)
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)
    pair_repo = PairRepository(session)
    team_repo = TeamRepository(session)
    tournament_repo = TournamentRepository(session)

    # Get current tournament
    current_tournament = tournament_repo.get_current()
    tournament_id = current_tournament.id if current_tournament else None

    # Get all groups for this category
    groups = group_repo.get_by_category(category, tournament_id=tournament_id)

    if not groups:
        return render_template("category_standings.html", {
            "request": request,
            "category": category,
            "groups_standings": [],
            "total_groups": 0
        })

    event_type = detect_event_type(category)

    # Calculate standings for each group
    groups_standings = []
    for group in groups:
        match_orms = match_repo.get_by_group(group.id)

        # Convert to domain models using competitor IDs
        matches = []
        for m_orm in match_orms:
            sets = [
                Set(
                    set_number=s["set_number"],
                    player1_points=s["player1_points"],
                    player2_points=s["player2_points"],
                )
                for s in m_orm.sets
            ]
            match = Match(
                id=m_orm.id,
                player1_id=m_orm.competitor1_id or 0,
                player2_id=m_orm.competitor2_id or 0,
                group_id=m_orm.group_id,
                round_type=m_orm.round_type,
                status=m_orm.status,
                sets=sets,
                winner_id=m_orm.winner_id,
            )
            matches.append(match)

        # Calculate standings
        standings, tiebreakers = calculate_standings(
            matches, group.id, player_repo,
            event_type=event_type, pair_repo=pair_repo, team_repo=team_repo,
        )

        # tiebreakers is already a dict with player_id as key
        tiebreaker_lookup = tiebreakers if tiebreakers else {}

        # Get competitor details
        standings_data = []
        for standing in standings:
            if event_type == "teams":
                team_orm = team_repo.get_by_id(standing.player_id)
                if team_orm:
                    standings_data.append({
                        "standing": standing,
                        "player": team_orm,
                        "tiebreaker": tiebreaker_lookup.get(standing.player_id)
                    })
            elif event_type == "doubles":
                pair_orm = pair_repo.get_by_id(standing.player_id)
                if pair_orm:
                    p1 = player_repo.get_by_id(pair_orm.player1_id)
                    p2 = player_repo.get_by_id(pair_orm.player2_id)
                    display = CompetitorDisplay.from_pair(pair_orm, p1, p2)
                    standings_data.append({
                        "standing": standing,
                        "player": display,
                        "tiebreaker": tiebreaker_lookup.get(standing.player_id)
                    })
            else:
                player = player_repo.get_by_id(standing.player_id)
                if player:
                    standings_data.append({
                        "standing": standing,
                        "player": player,
                        "tiebreaker": tiebreaker_lookup.get(standing.player_id)
                    })

        # Count completed matches
        completed = sum(1 for m in match_orms if m.status != "pending")
        total = len(match_orms)

        groups_standings.append({
            "group": group,
            "standings": standings_data,
            "completed_matches": completed,
            "total_matches": total,
            "is_complete": completed == total and total > 0,
            "has_tiebreaker": len(tiebreakers) > 0 if tiebreakers else False
        })

    return render_template("category_standings.html", {
        "request": request,
        "category": category,
        "groups_standings": groups_standings,
        "total_groups": len(groups)
    })


@app.get("/group/{group_id}/sheet", response_class=HTMLResponse)
async def view_group_sheet(request: Request, group_id: int):
    """View group sheet with results matrix (original seeding order)."""
    session = get_db_session()
    group_repo = GroupRepository(session)
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)
    pair_repo = PairRepository(session)
    team_repo = TeamRepository(session)
    schedule_repo = ScheduleSlotRepository(session)

    # Get group
    group = group_repo.get_by_id(group_id)
    if not group:
        return HTMLResponse(content="Group not found", status_code=404)

    event_type = detect_event_type(group.category)

    # Get competitors sorted by group_number (original seeding order)
    def _get_competitor(pid):
        if event_type == "teams":
            return team_repo.get_by_id(pid)
        elif event_type == "doubles":
            return pair_repo.get_by_id(pid)
        return player_repo.get_by_id(pid)

    all_players = [_get_competitor(pid) for pid in group.player_ids]
    players = sorted([p for p in all_players if p], key=lambda p: p.group_number or 999)

    # Get all matches for this group
    match_orms = match_repo.get_by_group(group_id)

    # Build play order list with schedule info
    play_order = []
    for m_orm in match_orms:
        p1 = _get_competitor(m_orm.competitor1_id)
        p2 = _get_competitor(m_orm.competitor2_id)
        if p1 and p2:
            schedule_slot = schedule_repo.get_by_match(m_orm.id)
            play_order.append({
                "match_id": m_orm.id,
                "p1_num": p1.group_number,
                "p2_num": p2.group_number,
                "table": schedule_slot.table_number if schedule_slot else None,
                "time": schedule_slot.start_time if schedule_slot else None,
                "status": m_orm.status,
            })

    # Build results matrix: matrix[player1_group_num][player2_group_num] = result
    # Result format: "3-1" or "WO" or None if not played
    results_matrix = {}
    for p in players:
        results_matrix[p.group_number] = {}

    for m_orm in match_orms:
        if not m_orm.status or m_orm.status == MatchStatus.PENDING.value:
            continue

        p1 = _get_competitor(m_orm.competitor1_id)
        p2 = _get_competitor(m_orm.competitor2_id)

        if not p1 or not p2:
            continue

        # Convert to domain model to get sets
        sets = [
            Set(
                set_number=s["set_number"],
                player1_points=s["player1_points"],
                player2_points=s["player2_points"],
            )
            for s in m_orm.sets
        ]
        match = Match(
            id=m_orm.id,
            player1_id=m_orm.competitor1_id,
            player2_id=m_orm.competitor2_id,
            group_id=m_orm.group_id,
            round_type=m_orm.round_type,
            status=m_orm.status,
            sets=sets,
            winner_id=m_orm.winner_id,
        )

        # Determine result string
        if m_orm.status == MatchStatus.WALKOVER.value:
            p1_result = "WO" if match.winner_id == p1.id else "WO"
            p2_result = "WO" if match.winner_id == p2.id else "WO"
        else:
            p1_sets = match.player1_sets_won
            p2_sets = match.player2_sets_won
            p1_result = f"{p1_sets}-{p2_sets}"
            p2_result = f"{p2_sets}-{p1_sets}"

        # Store in matrix
        results_matrix[p1.group_number][p2.group_number] = p1_result
        results_matrix[p2.group_number][p1.group_number] = p2_result

    # Calculate stats for each player
    standings, _ = calculate_standings(
        [
            Match(
                id=m.id,
                player1_id=m.competitor1_id,
                player2_id=m.competitor2_id,
                group_id=m.group_id,
                round_type=m.round_type,
                status=m.status,
                sets=[
                    Set(
                        set_number=s["set_number"],
                        player1_points=s["player1_points"],
                        player2_points=s["player2_points"],
                    )
                    for s in m.sets
                ],
                winner_id=m.winner_id,
            )
            for m in match_orms
        ],
        group_id,
        player_repo,
        event_type=event_type, pair_repo=pair_repo, team_repo=team_repo,
    )

    # Create dict for quick lookup
    standings_dict = {s.player_id: s for s in standings}

    # Build player data with stats
    players_data = []
    for player in players:
        standing = standings_dict.get(player.id)
        players_data.append({
            "player": player,
            "standing": standing,
        })

    return render_template("group_sheet.html", {
        "request": request,
        "group": group,
        "players": players_data,
        "results_matrix": results_matrix,
        "category": group.category,
        "play_order": play_order,
    })


@app.post("/category/{category}/recalculate-standings")
async def recalculate_standings(category: str):
    """Recalculate standings for all groups in a category."""
    session = get_db_session()
    group_repo = GroupRepository(session)
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)
    standing_repo = StandingRepository(session)
    pair_repo = PairRepository(session)
    team_repo = TeamRepository(session)

    event_type = detect_event_type(category)

    # Get all groups for category
    groups = group_repo.get_by_category(category)

    for group in groups:
        # Get matches
        match_orms = match_repo.get_by_group(group.id)

        # Convert to domain models
        matches = []
        for m_orm in match_orms:
            sets = [
                Set(
                    set_number=s["set_number"],
                    player1_points=s["player1_points"],
                    player2_points=s["player2_points"],
                )
                for s in m_orm.sets
            ]
            match = Match(
                id=m_orm.id,
                player1_id=m_orm.competitor1_id,
                player2_id=m_orm.competitor2_id,
                group_id=m_orm.group_id,
                round_type=m_orm.round_type,
                status=m_orm.status,
                sets=sets,
                winner_id=m_orm.winner_id,
            )
            matches.append(match)

        # Calculate standings
        standings, _ = calculate_standings(
            matches, group.id, player_repo,
            event_type=event_type, pair_repo=pair_repo, team_repo=team_repo,
        )

        # Delete old standings
        standing_repo.delete_by_group(group.id)

        # Save new standings
        for standing in standings:
            standing_repo.create(standing)

    # Redirect back to category page
    return RedirectResponse(url=f"/category/{category}", status_code=303)


@app.get("/category/{category}/bracket", response_class=HTMLResponse)
async def view_bracket(request: Request, category: str):
    """View knockout bracket for a category."""
    import traceback
    import sys
    try:
        sys.stderr.write(f"[DEBUG] view_bracket called for category: {category}\n")
        sys.stderr.flush()
        session = get_db_session()
        sys.stderr.write("[DEBUG] Database session created\n")
        sys.stderr.flush()
        bracket_repo = BracketRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        group_repo = GroupRepository(session)
        standing_repo = StandingRepository(session)
        tournament_repo = TournamentRepository(session)
        sys.stderr.write("[DEBUG] Repositories initialized\n")
        sys.stderr.flush()

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Get bracket slots for this category filtered by tournament
        bracket_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)

        if not bracket_slots:
            groups = group_repo.get_by_category(category, tournament_id=tournament_id)
            return render_template(
                "no_bracket.html",
                {"request": request, "category": category, "num_groups": len(groups)}
            )

        # Group slots by round
        from collections import defaultdict, namedtuple
        from ettem.models import RoundType

        slots_by_round = defaultdict(list)
        for slot_orm in bracket_slots:
            slots_by_round[slot_orm.round_type].append(slot_orm)

        # Sort each round by slot_number
        for round_type in slots_by_round:
            slots_by_round[round_type].sort(key=lambda s: s.slot_number)

        # Determine bracket size from the largest round (first round of tournament)
        # Priority: R128 > R64 > R32 > R16 > QF > SF > F
        bracket_size = 0
        round_priority = ['R128', 'R64', 'R32', 'R16', 'QF', 'SF', 'F']
        for round_type in round_priority:
            if round_type in slots_by_round:
                bracket_size = len(slots_by_round[round_type])
                break

        # Determine which rounds should exist based on bracket size
        required_rounds = []
        if bracket_size >= 128:
            required_rounds = ['R128', 'R64', 'R32', 'R16', 'QF', 'SF', 'F']
        elif bracket_size >= 64:
            required_rounds = ['R64', 'R32', 'R16', 'QF', 'SF', 'F']
        elif bracket_size >= 32:
            required_rounds = ['R32', 'R16', 'QF', 'SF', 'F']
        elif bracket_size >= 16:
            required_rounds = ['R16', 'QF', 'SF', 'F']
        elif bracket_size >= 8:
            required_rounds = ['QF', 'SF', 'F']
        elif bracket_size >= 4:
            required_rounds = ['SF', 'F']
        elif bracket_size >= 2:
            required_rounds = ['F']

        # Create dummy slots for rounds that don't exist yet
        DummySlot = namedtuple('DummySlot', ['slot_number', 'round_type', 'player_id', 'is_bye', 'same_country_warning', 'id'])

        complete_bracket = {}
        current_slots = bracket_size

        for round_type in required_rounds:
            if round_type in slots_by_round:
                # Round exists in database
                complete_bracket[round_type] = slots_by_round[round_type]
            else:
                # Create empty slots for this round
                current_slots = current_slots // 2
                complete_bracket[round_type] = []
                for i in range(current_slots):
                    dummy = DummySlot(
                        slot_number=i + 1,
                        round_type=round_type,
                        player_id=None,
                        is_bye=False,
                        same_country_warning=False,
                        id=None
                    )
                    complete_bracket[round_type].append(dummy)

        # Get player details for each slot
        slots_with_players = {}
        sys.stderr.write(f"[DEBUG] complete_bracket keys: {list(complete_bracket.keys())}\n")
        sys.stderr.flush()
        for round_type, slots in complete_bracket.items():
            sys.stderr.write(f"[DEBUG] Round {round_type}: {len(slots)} slots\n")
            sys.stderr.flush()
            slots_with_players[round_type] = []
            for slot in slots:
                from ettem.webapp.helpers import get_bracket_slot_display
                competitor = get_bracket_slot_display(slot, category, player_repo, pair_repo, team_repo)
                slots_with_players[round_type].append({
                    "slot": slot,
                    "player": competitor
                })

        # Get groups dict for lookups (filtered by tournament)
        groups = group_repo.get_by_category(category, tournament_id=tournament_id)
        groups_dict = {g.id: g for g in groups}
        current_group_ids = set(groups_dict.keys())

        # Get standings dict for lookups (filtered by tournament via group_id)
        all_standings = standing_repo.get_all()
        standings_dict = {}
        for standing_orm in all_standings:
            # Only include standings from current tournament's groups
            if standing_orm.group_id not in current_group_ids:
                continue
            # Use group category to match (works for singles, doubles, and teams)
            group = groups_dict.get(standing_orm.group_id)
            if group and group.category == category:
                standings_dict[standing_orm.player_id] = standing_orm

        # Check if there's a champion (final match completed)
        match_repo = MatchRepository(session)
        from ettem.models import MatchStatus
        champion_id = None
        from ettem.models import is_doubles_category
        final_matches = [
            m for m in match_repo.get_all()
            if m.round_type == RoundType.FINAL.value
            and m.group_id is None  # bracket match
        ]
        for m in final_matches:
            # Check category via player or pair
            if is_doubles_category(category) and m.pair1_id:
                p = pair_repo.get_by_id(m.pair1_id)
                if p and p.categoria == category and m.winner_id:
                    champion_id = m.winner_id
                    break
            elif m.player1_id:
                p1 = player_repo.get_by_id(m.player1_id)
                if p1 and p1.categoria == category and m.winner_id:
                    champion_id = m.winner_id
                    break

        # Get all bracket matches with scores for this category
        all_bracket_matches = [
            m for m in match_repo.get_all()
            if m.group_id is None  # bracket match
        ]

        # Filter matches for this category and build matches dict
        matches_by_round = {}
        bracket_best_of = 5  # default
        has_played_matches = False
        from ettem.webapp.helpers import get_competitor_display
        for match in all_bracket_matches:
            # Determine if this match belongs to this category
            match_in_category = False
            if is_doubles_category(category) and match.pair1_id:
                p = pair_repo.get_by_id(match.pair1_id)
                if p and p.categoria == category:
                    match_in_category = True
            elif match.player1_id:
                p1_check = player_repo.get_by_id(match.player1_id)
                if p1_check and p1_check.categoria == category:
                    match_in_category = True

            if match_in_category:
                if match.round_type not in matches_by_round:
                    matches_by_round[match.round_type] = []

                p1 = get_competitor_display(match, 1, player_repo, pair_repo, team_repo)
                p2 = get_competitor_display(match, 2, player_repo, pair_repo, team_repo)
                matches_by_round[match.round_type].append({
                    "match": match,
                    "player1": p1,
                    "player2": p2,
                })

                # Track best_of and if any matches have been played
                bracket_best_of = match.best_of or 5
                if match.winner_id is not None:
                    has_played_matches = True

        sys.stderr.write("[DEBUG] About to render template\n")
        sys.stderr.flush()
        # Check if this category has groups
        all_groups = group_repo.get_all(tournament_id=tournament_id)
        has_groups = any(g.category == category for g in all_groups)

        return render_template("bracket.html", {
            "request": request,
            "category": category,
            "slots_by_round": slots_with_players,
            "champion_id": champion_id,
            "groups_dict": groups_dict,
            "standings_dict": standings_dict,
            "matches_by_round": matches_by_round,
            "bracket_best_of": bracket_best_of,
            "has_played_matches": has_played_matches,
            "has_groups": has_groups,
        })
    except Exception as e:
        sys.stderr.write(f"[ERROR] Exception in view_bracket: {e}\n")
        sys.stderr.flush()
        traceback.print_exc()
        raise


@app.get("/bracket/{category}", response_class=HTMLResponse)
async def view_bracket_matches(request: Request, category: str):
    """View knockout bracket with matches for a category."""
    from ettem.models import RoundType, is_teams_category
    from collections import defaultdict

    session = get_db_session()
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)
    pair_repo = PairRepository(session)
    team_repo = TeamRepository(session)
    bracket_repo = BracketRepository(session)
    tournament_repo = TournamentRepository(session)

    # Get current tournament
    current_tournament = tournament_repo.get_current()
    tournament_id = current_tournament.id if current_tournament else None

    # Get bracket slots for this category in current tournament
    bracket_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
    if not bracket_slots:
        group_repo = GroupRepository(session)
        groups = group_repo.get_by_category(category, tournament_id=tournament_id)
        return render_template(
            "no_bracket.html",
            {"request": request, "category": category, "num_groups": len(groups)}
        )

    # Get all bracket matches for this category directly (filtered by category and tournament)
    bracket_matches = match_repo.get_bracket_matches_by_category(category, tournament_id=tournament_id)

    # Group matches by round
    matches_by_round = defaultdict(list)
    for match_orm in bracket_matches:
        matches_by_round[match_orm.round_type].append(match_orm)

    # Sort matches within each round by match_number
    for round_type in matches_by_round:
        matches_by_round[round_type].sort(key=lambda m: m.match_number)

    # Prepare matches with player details (using CompetitorDisplay for doubles/teams support)
    from ettem.webapp.helpers import get_competitor_display as _get_cd
    matches_with_players = {}
    for round_type, matches in matches_by_round.items():
        matches_with_players[round_type] = []
        for match_orm in matches:
            player1 = _get_cd(match_orm, 1, player_repo, pair_repo, team_repo=team_repo)
            player2 = _get_cd(match_orm, 2, player_repo, pair_repo, team_repo=team_repo)

            # Parse sets from JSON
            sets = []
            if match_orm.sets_json:
                import json
                sets = json.loads(match_orm.sets_json)

            matches_with_players[round_type].append({
                "match": match_orm,
                "player1": player1,
                "player2": player2,
                "sets": sets
            })

    # Determine round display order
    round_order = []
    if matches_by_round:
        # Determine which rounds exist
        all_round_types = [RoundType.ROUND_OF_128, RoundType.ROUND_OF_64, RoundType.ROUND_OF_32, RoundType.ROUND_OF_16,
                          RoundType.QUARTERFINAL, RoundType.SEMIFINAL, RoundType.FINAL]
        for rt in all_round_types:
            if rt.value in matches_by_round:
                round_order.append(rt.value)

    # Check if there's a champion (final match completed)
    from ettem.webapp.helpers import get_champion_display
    champion = None
    champion_id = None
    if RoundType.FINAL.value in matches_by_round:
        for match_data in matches_with_players[RoundType.FINAL.value]:
            if match_data["match"].winner_id:
                champion_id = match_data["match"].winner_id
                champion = get_champion_display(champion_id, category, player_repo, pair_repo, team_repo=team_repo)
                break

    # Determine active round (first round with incomplete matches)
    # Priority: first round with playable matches (both players, no winner)
    # Fallback: first round with incomplete matches (no winner yet)
    active_round = None
    fallback_round = None

    for rt in round_order:
        if rt in matches_with_players:
            for match_data in matches_with_players[rt]:
                match_orm = match_data["match"]
                # A match is playable if it has both players but no winner
                if (match_orm.player1_id and match_orm.player2_id and
                    not match_orm.winner_id):
                    active_round = rt
                    break
                # Track first round with incomplete match (no winner)
                if not match_orm.winner_id and not fallback_round:
                    fallback_round = rt
        if active_round:
            break

    # Use fallback if no playable matches found
    if not active_round:
        active_round = fallback_round

    # Final fallback: last round (most advanced)
    if not active_round and round_order:
        active_round = round_order[-1]

    # Count pending BYEs for the "Process BYEs" button
    pending_byes = count_pending_byes(category, bracket_repo, tournament_id)
    bye_matches_count = count_bye_matches(category, match_repo, bracket_repo, tournament_id)
    total_pending = pending_byes + bye_matches_count
    print(f"[DEBUG] pending_byes for {category}: {pending_byes}, bye_matches: {bye_matches_count}")

    # Check if this category has groups (to conditionally show "Groups" button)
    group_repo = GroupRepository(session)
    all_groups = group_repo.get_all(tournament_id=tournament_id)
    has_groups = any(g.category == category for g in all_groups)

    is_teams_cat = is_teams_category(category)

    return render_template("bracket_matches.html", {
        "request": request,
        "category": category,
        "matches_by_round": matches_with_players,
        "round_order": round_order,
        "active_round": active_round,
        "champion": champion,
        "champion_id": champion_id,
        "pending_byes": total_pending,  # Combined count for button display
        "has_groups": has_groups,
        "is_teams": is_teams_cat,
    })


@app.get("/category/{category}/results", response_class=HTMLResponse)
async def view_final_results(request: Request, category: str):
    """View final results and podium for a category."""
    from ettem.models import RoundType, MatchStatus, is_doubles_category, is_teams_category
    from ettem.webapp.helpers import get_competitor_display, CompetitorDisplay

    session = get_db_session()
    player_repo = PlayerRepository(session)
    match_repo = MatchRepository(session)
    bracket_repo = BracketRepository(session)
    tournament_repo = TournamentRepository(session)
    pair_repo = PairRepository(session)
    team_repo = TeamRepository(session)
    _is_doubles = is_doubles_category(category)
    _is_teams = is_teams_category(category)

    # Get current tournament
    current_tournament = tournament_repo.get_current()
    tournament_id = current_tournament.id if current_tournament else None

    # Verify bracket exists
    bracket_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
    if not bracket_slots:
        group_repo = GroupRepository(session)
        groups = group_repo.get_by_category(category, tournament_id=tournament_id)
        return render_template(
            "no_bracket.html",
            {"request": request, "category": category, "num_groups": len(groups)}
        )

    # Get the final match (filtered by tournament)
    final_matches = [
        m for m in match_repo.get_all()
        if m.round_type == RoundType.FINAL.value
        and m.group_id is None  # bracket match
        and m.tournament_id == tournament_id
        and m.category == category
    ]

    final_match = final_matches[0] if final_matches else None

    champion = None
    second_place = None
    third_fourth = []
    all_players = []

    if final_match and final_match.winner_id:
        # Tournament is complete
        if _is_teams or _is_doubles:
            # For teams/doubles, use competitor display
            if final_match.winner_id == final_match.player1_id:
                champion = get_competitor_display(final_match, 1, player_repo, pair_repo, team_repo)
                second_place = get_competitor_display(final_match, 2, player_repo, pair_repo, team_repo)
            else:
                champion = get_competitor_display(final_match, 2, player_repo, pair_repo, team_repo)
                second_place = get_competitor_display(final_match, 1, player_repo, pair_repo, team_repo)
        else:
            champion = player_repo.get_by_id(final_match.winner_id)
            loser_id = final_match.player2_id if final_match.winner_id == final_match.player1_id else final_match.player1_id
            second_place = player_repo.get_by_id(loser_id)

        # Get semifinal losers (3rd/4th place)
        semifinal_matches = [
            m for m in match_repo.get_all()
            if m.round_type == RoundType.SEMIFINAL.value
            and m.group_id is None
            and m.tournament_id == tournament_id
            and m.category == category
        ]

        for sf_match in semifinal_matches:
            if not sf_match.winner_id:
                continue
            if _is_teams or _is_doubles:
                # Determine loser side and get display
                if sf_match.winner_id == sf_match.player1_id:
                    loser_display = get_competitor_display(sf_match, 2, player_repo, pair_repo, team_repo)
                else:
                    loser_display = get_competitor_display(sf_match, 1, player_repo, pair_repo, team_repo)
                if loser_display.id != 0:
                    third_fourth.append(loser_display)
            else:
                p1 = player_repo.get_by_id(sf_match.player1_id)
                if p1 and p1.categoria == category:
                    loser_id = sf_match.player2_id if sf_match.winner_id == sf_match.player1_id else sf_match.player1_id
                    if loser_id:
                        loser = player_repo.get_by_id(loser_id)
                        if loser:
                            third_fourth.append(loser)

    # Build complete ranking
    player_rankings = []

    # Helper to determine position from rounds reached
    def _get_position_and_round(competitor_id, rounds_reached):
        if champion and competitor_id == champion.id:
            return 1, 'Campeón'
        elif second_place and competitor_id == second_place.id:
            return 2, 'Subcampeón'
        elif any(competitor_id == p.id for p in third_fourth):
            return 3, 'Semifinal'
        elif RoundType.SEMIFINAL.value in rounds_reached:
            return 3, 'Semifinal'
        elif RoundType.QUARTERFINAL.value in rounds_reached:
            return 5, 'Cuartos de Final'
        elif RoundType.ROUND_OF_16.value in rounds_reached:
            return 9, 'Ronda de 16'
        elif RoundType.ROUND_OF_32.value in rounds_reached:
            return 17, 'Ronda de 32'
        else:
            return 20, 'Primera Ronda'

    if _is_teams:
        # For teams, iterate over teams
        all_teams = [t for t in team_repo.get_by_category(category)]
        all_bracket_matches = [
            m for m in match_repo.get_all()
            if m.group_id is None and m.tournament_id == tournament_id and m.category == category
        ]

        for team in all_teams:
            team_display = CompetitorDisplay.from_team(team, player_repo=player_repo)

            # Check if team is in bracket
            team_in_bracket = any(
                (getattr(slot, 'team_id', None) == team.id or slot.player_id == team.id)
                for slot in bracket_slots if slot.player_id
            )

            if not team_in_bracket:
                player_rankings.append({
                    'player': team_display,
                    'final_position': 99,
                    'elimination_round': 'Fase de Grupos'
                })
                continue

            # Find bracket matches for this team
            team_matches = [
                m for m in all_bracket_matches
                if (m.team1_id == team.id or m.team2_id == team.id)
                and m.status == MatchStatus.COMPLETED.value
            ]

            if not team_matches:
                player_rankings.append({
                    'player': team_display,
                    'final_position': 50,
                    'elimination_round': 'Por Jugar'
                })
                continue

            rounds_reached = [m.round_type for m in team_matches]
            position, round_name = _get_position_and_round(team_display.id, rounds_reached)

            player_rankings.append({
                'player': team_display,
                'final_position': position,
                'elimination_round': round_name
            })

    elif _is_doubles:
        # For doubles, iterate over pairs
        all_pairs = [p for p in pair_repo.get_all() if p.categoria == category]
        all_bracket_matches = [
            m for m in match_repo.get_all()
            if m.group_id is None and m.tournament_id == tournament_id
        ]

        for pair in all_pairs:
            p1 = player_repo.get_by_id(pair.player1_id)
            p2 = player_repo.get_by_id(pair.player2_id)
            pair_display = CompetitorDisplay.from_pair(pair, p1, p2)

            # Check if pair is in bracket
            pair_in_bracket = any(
                (getattr(slot, 'pair_id', None) == pair.id or slot.player_id == pair.id)
                for slot in bracket_slots if slot.player_id
            )

            if not pair_in_bracket:
                player_rankings.append({
                    'player': pair_display,
                    'final_position': 99,
                    'elimination_round': 'Fase de Grupos'
                })
                continue

            # Find matches for this pair
            pair_matches = [
                m for m in all_bracket_matches
                if (m.pair1_id == pair.id or m.pair2_id == pair.id)
                and m.status == MatchStatus.COMPLETED.value
            ]

            if not pair_matches:
                player_rankings.append({
                    'player': pair_display,
                    'final_position': 50,
                    'elimination_round': 'Por Jugar'
                })
                continue

            rounds_reached = [m.round_type for m in pair_matches]
            position, round_name = _get_position_and_round(pair_display.id, rounds_reached)

            player_rankings.append({
                'player': pair_display,
                'final_position': position,
                'elimination_round': round_name
            })
    else:
        # Singles: iterate over individual players
        all_category_players = [
            p for p in player_repo.get_all(tournament_id=tournament_id)
            if p.categoria == category
        ]

        for player in all_category_players:
            player_in_bracket = any(
                slot.player_id == player.id for slot in bracket_slots if slot.player_id
            )

            if not player_in_bracket:
                player_rankings.append({
                    'player': player,
                    'final_position': 99,
                    'elimination_round': 'Fase de Grupos'
                })
                continue

            player_matches = [
                m for m in match_repo.get_all()
                if m.group_id is None
                and m.tournament_id == tournament_id
                and (m.player1_id == player.id or m.player2_id == player.id)
                and m.status == MatchStatus.COMPLETED.value
            ]

            if not player_matches:
                player_rankings.append({
                    'player': player,
                    'final_position': 50,
                    'elimination_round': 'Por Jugar'
                })
                continue

            rounds_reached = [m.round_type for m in player_matches]
            position, round_name = _get_position_and_round(player.id, rounds_reached)

            player_rankings.append({
                'player': player,
                'final_position': position,
                'elimination_round': round_name
            })

    # Sort by position
    player_rankings.sort(key=lambda x: (x['final_position'], getattr(x['player'], 'seed', None) or 99))

    return render_template("results.html", {
        "request": request,
        "category": category,
        "champion": champion,
        "second_place": second_place,
        "third_fourth": third_fourth,
        "all_players": player_rankings,
    })


# ========================================
# HELPER FUNCTIONS
# ========================================

def create_groups_from_manual_assignments(players, category, assignments):
    """
    Create groups from manual drag-and-drop assignments.

    Args:
        players: List of Player objects
        category: Category name
        assignments: Dict mapping group names to lists of player IDs

    Returns:
        Tuple of (groups, matches)
    """
    from ettem.models import Group, Match, MatchStatus, RoundType
    from ettem.group_builder import generate_round_robin_fixtures

    groups = []
    all_matches = []
    match_counter = 1

    for group_name, player_ids in assignments.items():
        # Create group
        group = Group(
            id=None,  # Will be assigned by database
            name=group_name,
            category=category,
            player_ids=player_ids
        )
        groups.append(group)

        # Get players for this group and assign group numbers
        group_players = [p for p in players if p.id in player_ids]

        # IMPORTANT: Assign group_number to each player (1-indexed position within group)
        for pos, player in enumerate(group_players, start=1):
            player.group_number = pos

        # Generate matches for this group using fixtures
        fixtures = generate_round_robin_fixtures(len(group_players))

        for fixture_idx, (p1_num, p2_num) in enumerate(fixtures, start=1):
            # Map group numbers to player IDs
            player1 = group_players[p1_num - 1]  # Convert to 0-indexed
            player2 = group_players[p2_num - 1]

            match = Match(
                id=0,  # Will be set by database
                player1_id=player1.id,
                player2_id=player2.id,
                group_id=0,  # Will be set when group is saved to DB
                round_type=RoundType.ROUND_ROBIN,
                round_name=f"Group {group_name} Match {fixture_idx}",
                match_number=match_counter,
                status=MatchStatus.PENDING,
                sets=[],
            )
            all_matches.append(match)
            match_counter += 1

    return groups, all_matches


# ========================================
# ADMIN ROUTES
# ========================================

@app.get("/admin/import-players", response_class=HTMLResponse)
async def admin_import_players_form(request: Request):
    """Show import players form."""
    session = get_db_session()
    player_repo = PlayerRepository(session)
    tournament_repo = TournamentRepository(session)

    # Get current tournament - show empty state if none exists
    current_tournament = tournament_repo.get_current()
    if not current_tournament:
        return render_template("admin_import_players.html", {
            "request": request,
            "tournament": None,
            "teams_display": [],
            "teams_categories": {},
            "team_categories": [],
            "all_players": [],
        })

    tournament_id = current_tournament.id

    # Get all players for current tournament
    all_players = player_repo.get_all(tournament_id=tournament_id)

    # Get pairs for doubles categories with player names resolved
    pair_repo = PairRepository(session)
    pairs_orm = pair_repo.get_all(tournament_id=tournament_id)

    # Build set of player IDs that are members of pairs
    pair_member_ids = set()
    for p in pairs_orm:
        pair_member_ids.add(p.player1_id)
        pair_member_ids.add(p.player2_id)

    # Separate singles players from doubles pair members and team members
    # A player shows in "Jugadores" only if:
    # - Their category is NOT doubles and NOT teams, OR
    # - They are NOT a member of any pair (orphan doubles player)
    singles_players = [
        p for p in all_players
        if not is_teams_category(p.categoria) and (
            not is_doubles_category(p.categoria) or p.id not in pair_member_ids
        )
    ]

    # Build player lookup for pair display
    players_by_id = {p.id: p for p in all_players}

    # Build enriched pairs list and categories summary
    singles_categories = {}
    for p in singles_players:
        cat = p.categoria
        singles_categories[cat] = singles_categories.get(cat, 0) + 1

    doubles_categories = {}
    pairs_display = []
    for p in pairs_orm:
        cat = p.categoria
        doubles_categories[cat] = doubles_categories.get(cat, 0) + 1
        p1 = players_by_id.get(p.player1_id)
        p2 = players_by_id.get(p.player2_id)
        pairs_display.append({
            "id": p.id,
            "player1_name": f"{p1.nombre} {p1.apellido}" if p1 else f"ID {p.player1_id}",
            "player1_pais": p1.pais_cd if p1 else "???",
            "player2_name": f"{p2.nombre} {p2.apellido}" if p2 else f"ID {p.player2_id}",
            "player2_pais": p2.pais_cd if p2 else "???",
            "ranking_pts": p.ranking_pts,
            "categoria": p.categoria,
            "seed": p.seed,
            "group_id": p.group_id,
            "group_number": p.group_number,
        })

    # Get teams for team categories
    team_repo = TeamRepository(session)
    teams_orm = team_repo.get_by_tournament(tournament_id)

    teams_categories = {}
    teams_display = []
    for team_orm in teams_orm:
        cat = team_orm.categoria
        teams_categories[cat] = teams_categories.get(cat, 0) + 1
        player_names = []
        for pid in team_orm.player_ids:
            p = players_by_id.get(pid)
            if p:
                player_names.append(f"{p.nombre} {p.apellido}")
        group_name = None
        if team_orm.group_id:
            group_repo = GroupRepository(session)
            grp = group_repo.get_by_id(team_orm.group_id)
            if grp:
                group_name = grp.name
        teams_display.append({
            "id": team_orm.id,
            "name": team_orm.name,
            "pais_cd": team_orm.pais_cd,
            "categoria": team_orm.categoria,
            "ranking_pts": team_orm.ranking_pts,
            "seed": team_orm.seed,
            "group_id": team_orm.group_id,
            "group_name": group_name,
            "player_names": player_names,
        })

    # Get existing team categories for manual form dropdown
    team_categories = sorted(set(t.categoria for t in teams_orm))

    return render_template(
        "admin_import_players.html",
        {
            "request": request,
            "players": singles_players,
            "pairs_display": pairs_display,
            "singles_categories": singles_categories,
            "doubles_categories": doubles_categories,
            "teams_display": teams_display,
            "teams_categories": teams_categories,
            "team_categories": team_categories,
            "all_players": all_players,
            "current_tournament": current_tournament,
            "tournament": current_tournament
        }
    )


@app.post("/admin/import-players/csv")
async def admin_import_players_csv(
    request: Request,
    csv_file: UploadFile = File(...),
    category: Optional[str] = Form(None),
    assign_seeds: Optional[str] = Form(None)
):
    """Import players from CSV file."""
    import tempfile
    from pathlib import Path
    from ettem.io_csv import import_players_csv, CSVImportError

    try:
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.csv') as tmp:
            content = await csv_file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Import players from CSV
        try:
            players = import_players_csv(
                tmp_path,
                category_filter=category if category and category.strip() else None
            )

            if not players:
                request.session["flash_message"] = "No se encontraron jugadores para importar (revisa el filtro de categoría)"
                request.session["flash_type"] = "warning"
                return RedirectResponse(url="/admin/import-players", status_code=303)

            # Save players to database
            session = get_db_session()
            player_repo = PlayerRepository(session)
            tournament_repo = TournamentRepository(session)

            # Get current tournament
            current_tournament = tournament_repo.get_current()
            tournament_id = current_tournament.id if current_tournament else None

            # Build dict of existing original_ids per category to detect duplicates
            existing_players = player_repo.get_all(tournament_id=tournament_id)
            existing_ids_by_cat = {}
            for p in existing_players:
                if p.original_id is not None:
                    existing_ids_by_cat.setdefault(p.categoria, set()).add(p.original_id)

            imported_count = 0
            skipped_count = 0
            for player in players:
                # Skip duplicates by (original_id, categoria)
                cat_ids = existing_ids_by_cat.get(player.categoria, set())
                if player.original_id is not None and player.original_id in cat_ids:
                    skipped_count += 1
                    continue
                try:
                    player_repo.create(player, tournament_id=tournament_id)
                    imported_count += 1
                    if player.original_id is not None:
                        existing_ids_by_cat.setdefault(player.categoria, set()).add(player.original_id)
                except Exception as e:
                    print(f"[ERROR] Error saving player {player.full_name}: {e}")

            # Assign seeds if requested
            if assign_seeds == "true":
                categories = set(p.categoria for p in players)
                for cat in categories:
                    player_repo.assign_seeds(cat)

            # Get imported category for redirect
            imported_category = players[0].categoria if players else None

            if skipped_count > 0:
                request.session["flash_message"] = f"✅ Se importaron {imported_count} jugadores para {imported_category}. Se omitieron {skipped_count} duplicados (mismo ID)."
            else:
                request.session["flash_message"] = f"✅ Se importaron exitosamente {imported_count} jugadores para la categoría {imported_category}"
            request.session["flash_type"] = "success"

        except CSVImportError as e:
            request.session["flash_message"] = f"Error al importar CSV: {str(e)}"
            request.session["flash_type"] = "error"
        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)

        # Redirect to home page to see the new category
        return RedirectResponse(url="/", status_code=303)

    except Exception as e:
        request.session["flash_message"] = f"Error inesperado: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/admin/import-players", status_code=303)


@app.post("/admin/import-players/manual")
async def admin_import_players_manual(
    request: Request,
    original_id: int = Form(...),
    nombre: str = Form(...),
    apellido: str = Form(...),
    genero: str = Form(...),
    pais_cd: str = Form(...),
    ranking_pts: float = Form(...),
    categoria: str = Form(...)
):
    """Add a player manually."""
    from ettem.models import Gender

    try:
        # Validate inputs
        if genero not in ("M", "F"):
            request.session["flash_message"] = "El género debe ser M o F"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-players", status_code=303)

        if len(pais_cd.strip()) != 3:
            request.session["flash_message"] = "El código de país debe tener 3 caracteres (ISO-3)"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-players", status_code=303)

        if ranking_pts < 0:
            request.session["flash_message"] = "Los puntos de ranking no pueden ser negativos"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-players", status_code=303)

        categoria_upper = categoria.strip().upper()

        # Check for duplicate original_id in the same category/tournament
        session = get_db_session()
        player_repo = PlayerRepository(session)
        tournament_repo = TournamentRepository(session)

        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Check for duplicate original_id within the SAME category
        all_players = player_repo.get_all(tournament_id=tournament_id)
        for p in all_players:
            if p.original_id is not None and p.original_id == original_id and p.categoria == categoria_upper:
                request.session["flash_message"] = f"Ya existe un jugador con ID {original_id} en {categoria_upper} ({p.nombre} {p.apellido})"
                request.session["flash_type"] = "error"
                return RedirectResponse(url="/admin/import-players", status_code=303)

        # Create player (seed will be auto-assigned)
        player = Player(
            id=0,  # Auto-generated
            nombre=nombre.strip(),
            apellido=apellido.strip(),
            genero=Gender.MALE if genero == "M" else Gender.FEMALE,
            pais_cd=pais_cd.strip().upper(),
            ranking_pts=ranking_pts,
            categoria=categoria_upper,
            original_id=original_id,
            seed=None  # Will be calculated after save
        )

        # Save to database
        player_repo.create(player, tournament_id=tournament_id)

        # Always recalculate seeds based on ranking
        player_repo.assign_seeds(categoria_upper)

        request.session["flash_message"] = f"Jugador {player.full_name} agregado (seed asignado automáticamente)"
        request.session["flash_type"] = "success"

    except Exception as e:
        request.session["flash_message"] = f"Error al agregar jugador: {str(e)}"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/admin/import-players", status_code=303)


@app.post("/admin/player/edit")
async def admin_edit_player(
    request: Request,
    player_id: int = Form(...),
    nombre: str = Form(...),
    apellido: str = Form(...),
    genero: str = Form(...),
    pais_cd: str = Form(...),
    ranking_pts: float = Form(...),
    categoria: str = Form(...),
    original_id: Optional[int] = Form(None)
):
    """Edit an existing player."""
    try:
        session = get_db_session()
        player_repo = PlayerRepository(session)

        player = player_repo.get_by_id(player_id)
        if not player:
            request.session["flash_message"] = "Jugador no encontrado"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-players", status_code=303)

        # Validate inputs
        if genero not in ("M", "F"):
            request.session["flash_message"] = "El género debe ser M o F"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-players", status_code=303)

        if len(pais_cd.strip()) != 3:
            request.session["flash_message"] = "El código de país debe tener 3 caracteres (ISO-3)"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-players", status_code=303)

        # Track if category changed
        old_category = player.categoria
        new_category = categoria.strip().upper()

        # Check for duplicate original_id within the same category (excluding self)
        if original_id:
            tournament_repo = TournamentRepository(session)
            current_tournament = tournament_repo.get_current()
            tid = current_tournament.id if current_tournament else None
            all_players = player_repo.get_all(tournament_id=tid)
            for p in all_players:
                if p.id != player_id and p.original_id == original_id and p.categoria == new_category:
                    request.session["flash_message"] = f"Ya existe un jugador con ID {original_id} en {new_category} ({p.nombre} {p.apellido})"
                    request.session["flash_type"] = "error"
                    return RedirectResponse(url="/admin/import-players", status_code=303)

        # Update player
        player.nombre = nombre.strip()
        player.apellido = apellido.strip()
        player.genero = genero
        player.pais_cd = pais_cd.strip().upper()
        player.ranking_pts = ranking_pts
        player.categoria = new_category
        player.original_id = original_id if original_id else None

        player_repo.update(player)

        # Recalculate seeds for affected categories
        player_repo.assign_seeds(new_category)
        if old_category != new_category:
            player_repo.assign_seeds(old_category)

        request.session["flash_message"] = f"Jugador {nombre} {apellido} actualizado (seeds recalculados)"
        request.session["flash_type"] = "success"

    except Exception as e:
        request.session["flash_message"] = f"Error al actualizar jugador: {str(e)}"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/admin/import-players", status_code=303)


@app.post("/admin/player/{player_id}/delete")
async def admin_delete_player(request: Request, player_id: int):
    """Delete a player with validation."""
    try:
        session = get_db_session()
        player_repo = PlayerRepository(session)
        match_repo = MatchRepository(session)

        player = player_repo.get_by_id(player_id)
        if not player:
            request.session["flash_message"] = "Jugador no encontrado"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-players", status_code=303)

        player_name = f"{player.nombre} {player.apellido}"
        player_category = player.categoria

        # Check if player has played any matches
        player_matches = match_repo.get_by_player(player_id)
        completed_matches = [m for m in player_matches if m.status == "completed"]

        if completed_matches:
            request.session["flash_message"] = f"No se puede eliminar a {player_name}: tiene {len(completed_matches)} partidos jugados. Elimina primero los resultados."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-players", status_code=303)

        # Delete pending matches where this player participates
        for match in player_matches:
            match_repo.delete(match.id)

        # Delete the player
        player_repo.delete(player_id)

        # Recalculate seeds for the category
        player_repo.assign_seeds(player_category)

        request.session["flash_message"] = f"Jugador {player_name} eliminado (seeds recalculados)"
        request.session["flash_type"] = "success"

    except Exception as e:
        request.session["flash_message"] = f"Error al eliminar jugador: {str(e)}"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/admin/import-players", status_code=303)


@app.post("/admin/category/{category}/delete")
async def admin_delete_category(request: Request, category: str):
    """Delete an entire category with all its data."""
    try:
        session = get_db_session()
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        group_repo = GroupRepository(session)
        match_repo = MatchRepository(session)
        standing_repo = StandingRepository(session)
        bracket_repo = BracketRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Get all groups for this category
        groups = group_repo.get_by_category(category, tournament_id=tournament_id)

        # Count what we're deleting
        deleted_matches = 0
        deleted_standings = 0
        deleted_groups = 0
        deleted_players = 0
        deleted_teams = 0
        deleted_pairs = 0

        # Delete matches and standings for each group
        for group in groups:
            # Delete matches
            matches = match_repo.get_by_group(group.id)
            for match in matches:
                match_repo.delete(match.id)
                deleted_matches += 1

            # Delete standings
            standings = standing_repo.get_by_group(group.id)
            for standing in standings:
                standing_repo.delete(standing.id)
                deleted_standings += 1

            # Delete group
            group_repo.delete(group.id)
            deleted_groups += 1

        # Delete bracket
        bracket_repo.delete_by_category(category, tournament_id=tournament_id)

        # Delete bracket matches (matches with no group_id)
        all_matches = match_repo.get_all()
        for match in all_matches:
            if match.group_id is None and getattr(match, 'category', None) == category:
                match_repo.delete(match.id)
                deleted_matches += 1

        # Delete teams
        teams = team_repo.get_by_category(category, tournament_id=tournament_id)
        for team in teams:
            team_repo.delete(team.id)
            deleted_teams += 1

        # Delete pairs
        pairs = pair_repo.get_by_category(category, tournament_id=tournament_id)
        for pair in pairs:
            pair_repo.delete(pair.id)
            deleted_pairs += 1

        # Delete players
        players = player_repo.get_by_category(category, tournament_id=tournament_id)
        for player in players:
            player_repo.delete(player.id)
            deleted_players += 1

        # Build result message
        event_type = detect_event_type(category)
        if event_type == "teams":
            entity_msg = f"{deleted_teams} equipos, {deleted_players} jugadores"
        elif event_type == "doubles":
            entity_msg = f"{deleted_pairs} parejas, {deleted_players} jugadores"
        else:
            entity_msg = f"{deleted_players} jugadores"

        request.session["flash_message"] = f"Categoría {category} eliminada: {entity_msg}, {deleted_groups} grupos, {deleted_matches} partidos"
        request.session["flash_type"] = "success"

    except Exception as e:
        request.session["flash_message"] = f"Error al eliminar categoría: {str(e)}"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/admin/import-players", status_code=303)


# ============================================================================
# Pair Import Routes (Doubles)
# ============================================================================


@app.get("/admin/import-pairs", response_class=HTMLResponse)
async def admin_import_pairs_form(request: Request):
    """Show import pairs form."""
    session = get_db_session()
    player_repo = PlayerRepository(session)
    pair_repo = PairRepository(session)
    tournament_repo = TournamentRepository(session)

    current_tournament = tournament_repo.get_current()
    if not current_tournament:
        return RedirectResponse(url="/tournaments", status_code=303)

    tournament_id = current_tournament.id

    # Get all pairs for current tournament
    pairs = pair_repo.get_by_tournament(tournament_id)

    # Populate player info for each pair
    pairs_display = []
    for pair_orm in pairs:
        p1 = player_repo.get_by_id(pair_orm.player1_id)
        p2 = player_repo.get_by_id(pair_orm.player2_id)
        pairs_display.append({
            "id": pair_orm.id,
            "player1": p1,
            "player2": p2,
            "categoria": pair_orm.categoria,
            "ranking_pts": pair_orm.ranking_pts,
            "seed": pair_orm.seed,
            "group_id": pair_orm.group_id,
        })

    # Get all players for current tournament (for manual pair creation)
    players = player_repo.get_all(tournament_id=tournament_id)

    # Get doubles categories that have players
    doubles_categories = set()
    for p in players:
        if is_doubles_category(p.categoria):
            doubles_categories.add(p.categoria)

    return render_template(
        "admin_import_pairs.html",
        {
            "request": request,
            "pairs": pairs_display,
            "players": players,
            "doubles_categories": sorted(doubles_categories),
            "current_tournament": current_tournament,
        }
    )


@app.post("/admin/import-pairs/csv")
async def admin_import_pairs_csv(
    request: Request,
    csv_file: UploadFile = File(...),
    assign_seeds: Optional[str] = Form(None),
):
    """Import pairs from CSV file.

    CSV format: player1_id,player2_id,ranking_pts,categoria
    player1_id and player2_id reference original_id of imported players.
    """
    import csv
    import io
    import tempfile
    from pathlib import Path

    try:
        content = await csv_file.read()
        text = content.decode("utf-8-sig")

        session = get_db_session()
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        tournament_repo = TournamentRepository(session)

        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        reader = csv.DictReader(io.StringIO(text))
        imported_count = 0
        skipped_count = 0
        errors = []

        # Pre-load all players and existing pairs to avoid repeated queries
        all_players = player_repo.get_all(tournament_id=tournament_id)
        existing_pairs = pair_repo.get_all(tournament_id=tournament_id)
        existing_pair_keys = {(p.player1_id, p.player2_id) for p in existing_pairs}

        for row_num, row in enumerate(reader, start=2):
            try:
                p1_orig_id = int(row.get("player1_id", "").strip())
                p2_orig_id = int(row.get("player2_id", "").strip())
                ranking = float(row.get("ranking_pts", "0").strip() or "0")
                categoria = row.get("categoria", "").strip().upper()

                if not categoria:
                    errors.append(f"Row {row_num}: missing categoria")
                    continue

                if not is_doubles_category(categoria):
                    errors.append(f"Row {row_num}: {categoria} is not a doubles category")
                    continue

                # Find players by original_id (warn if ambiguous across categories)
                p1_matches = [p for p in all_players if p.original_id == p1_orig_id]
                p2_matches = [p for p in all_players if p.original_id == p2_orig_id]

                if not p1_matches:
                    errors.append(f"Row {row_num}: player1_id {p1_orig_id} not found")
                    continue
                if not p2_matches:
                    errors.append(f"Row {row_num}: player2_id {p2_orig_id} not found")
                    continue

                if len(p1_matches) > 1:
                    cats = ", ".join(p.categoria for p in p1_matches)
                    errors.append(f"Row {row_num}: player1_id {p1_orig_id} is ambiguous (exists in: {cats})")
                    continue
                if len(p2_matches) > 1:
                    cats = ", ".join(p.categoria for p in p2_matches)
                    errors.append(f"Row {row_num}: player2_id {p2_orig_id} is ambiguous (exists in: {cats})")
                    continue

                p1 = p1_matches[0]
                p2 = p2_matches[0]

                # Skip if pair already exists (either order)
                if (p1.id, p2.id) in existing_pair_keys or (p2.id, p1.id) in existing_pair_keys:
                    skipped_count += 1
                    continue

                pair = Pair(
                    id=0,
                    player1_id=p1.id,
                    player2_id=p2.id,
                    categoria=categoria,
                    ranking_pts=ranking,
                )
                pair_repo.create(pair, tournament_id=tournament_id)
                imported_count += 1
                existing_pair_keys.add((p1.id, p2.id))

            except (ValueError, KeyError) as e:
                errors.append(f"Row {row_num}: {str(e)}")

        if assign_seeds == "true":
            categories = pair_repo.get_all(tournament_id=tournament_id)
            cats = set(p.categoria for p in categories)
            for cat in cats:
                pair_repo.assign_seeds(cat, tournament_id=tournament_id)

        msg = f"Se importaron {imported_count} parejas exitosamente."
        if skipped_count > 0:
            msg += f" Se omitieron {skipped_count} duplicadas."
        if errors:
            msg += f" ({len(errors)} errores)"
        request.session["flash_message"] = msg
        request.session["flash_type"] = "success" if imported_count > 0 else "warning"

    except Exception as e:
        request.session["flash_message"] = f"Error al importar CSV: {str(e)}"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/admin/import-pairs", status_code=303)


@app.post("/admin/import-pairs/csv-unified")
async def admin_import_pairs_csv_unified(
    request: Request,
    csv_file: UploadFile = File(...),
    assign_seeds: Optional[str] = Form(None),
):
    """Import pairs from a unified CSV where each row has both players' data.

    CSV format: nombre1,apellido1,pais1,nombre2,apellido2,pais2,ranking_pts,categoria
    Optional columns: genero1, genero2 (auto-detected from category if missing)
    """
    import csv
    import io
    from ettem.models import Player, Gender, Pair

    try:
        content = await csv_file.read()
        text = content.decode("utf-8-sig")

        session = get_db_session()
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        tournament_repo = TournamentRepository(session)

        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        reader = csv.DictReader(io.StringIO(text))
        imported_pairs = 0
        skipped_pairs = 0
        created_players = 0
        errors = []

        # Pre-load existing players and pairs for duplicate detection
        all_players = player_repo.get_all(tournament_id=tournament_id)
        existing_pairs = pair_repo.get_all(tournament_id=tournament_id)
        existing_pair_keys = {(p.player1_id, p.player2_id) for p in existing_pairs}

        # Index players by (nombre, apellido, pais_cd) for fast lookup
        player_index = {}
        for p in all_players:
            key = (p.nombre.strip().lower(), p.apellido.strip().lower(), p.pais_cd.strip().upper())
            player_index[key] = p

        def infer_gender(category: str, suffix_num: str) -> str:
            """Infer gender from doubles category convention."""
            cat = category.upper().strip()
            if cat.endswith("WD") or cat.endswith("GD"):
                return "F"
            elif cat.endswith("MD") or cat.endswith("BD"):
                return "M"
            # XD = mixed, can't infer
            return suffix_num  # fallback to explicit value

        def find_or_create_player(nombre, apellido, pais_cd, genero, categoria, tournament_id):
            nonlocal created_players
            key = (nombre.strip().lower(), apellido.strip().lower(), pais_cd.strip().upper())
            if key in player_index:
                return player_index[key]
            # Create new player
            player = Player(
                id=0,
                nombre=nombre.strip(),
                apellido=apellido.strip(),
                genero=Gender.MALE if genero == "M" else Gender.FEMALE,
                pais_cd=pais_cd.strip().upper(),
                ranking_pts=0,
                categoria=categoria.strip().upper(),
            )
            player_orm = player_repo.create(player, tournament_id=tournament_id)
            player_index[key] = player_orm
            created_players += 1
            return player_orm

        for row_num, row in enumerate(reader, start=2):
            try:
                nombre1 = row.get("nombre1", "").strip()
                apellido1 = row.get("apellido1", "").strip()
                pais1 = row.get("pais1", "").strip().upper()
                nombre2 = row.get("nombre2", "").strip()
                apellido2 = row.get("apellido2", "").strip()
                pais2 = row.get("pais2", "").strip().upper()
                ranking = float(row.get("ranking_pts", "0").strip() or "0")
                categoria = row.get("categoria", "").strip().upper()

                # Validate required fields
                if not all([nombre1, apellido1, pais1, nombre2, apellido2, pais2, categoria]):
                    errors.append(f"Fila {row_num}: campos vacíos")
                    continue

                if not is_doubles_category(categoria):
                    errors.append(f"Fila {row_num}: {categoria} no es categoría de dobles")
                    continue

                if len(pais1) != 3 or len(pais2) != 3:
                    errors.append(f"Fila {row_num}: código de país debe ser 3 letras")
                    continue

                # Determine gender
                genero1 = row.get("genero1", "").strip().upper()
                genero2 = row.get("genero2", "").strip().upper()
                if not genero1 or genero1 not in ("M", "F"):
                    genero1 = infer_gender(categoria, "M")
                if not genero2 or genero2 not in ("M", "F"):
                    genero2 = infer_gender(categoria, "M")

                # Find or create players
                p1 = find_or_create_player(nombre1, apellido1, pais1, genero1, categoria, tournament_id)
                p2 = find_or_create_player(nombre2, apellido2, pais2, genero2, categoria, tournament_id)

                # Skip if pair already exists (either order)
                if (p1.id, p2.id) in existing_pair_keys or (p2.id, p1.id) in existing_pair_keys:
                    skipped_pairs += 1
                    continue

                # Create pair
                pair = Pair(
                    id=0,
                    player1_id=p1.id,
                    player2_id=p2.id,
                    categoria=categoria,
                    ranking_pts=ranking,
                )
                pair_repo.create(pair, tournament_id=tournament_id)
                imported_pairs += 1
                existing_pair_keys.add((p1.id, p2.id))

            except (ValueError, KeyError) as e:
                errors.append(f"Fila {row_num}: {str(e)}")

        # Assign seeds if requested
        if assign_seeds == "true" and imported_pairs > 0:
            all_pairs = pair_repo.get_all(tournament_id=tournament_id)
            cats = set(p.categoria for p in all_pairs)
            for cat in cats:
                pair_repo.assign_seeds(cat, tournament_id=tournament_id)

        # Build message
        parts = []
        if imported_pairs > 0:
            parts.append(f"{imported_pairs} parejas importadas")
        if created_players > 0:
            parts.append(f"{created_players} jugadores creados")
        if skipped_pairs > 0:
            parts.append(f"{skipped_pairs} parejas duplicadas omitidas")
        msg = ", ".join(parts) + "." if parts else "No se importaron parejas."
        if errors:
            msg += f" ({len(errors)} errores)"

        request.session["flash_message"] = msg
        request.session["flash_type"] = "success" if imported_pairs > 0 else "warning"

    except Exception as e:
        request.session["flash_message"] = f"Error al importar CSV: {str(e)}"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/admin/import-players", status_code=303)


@app.post("/admin/import-pairs/manual")
async def admin_import_pairs_manual(
    request: Request,
    player1_id: int = Form(...),
    player2_id: int = Form(...),
    ranking_pts: float = Form(0),
    categoria: str = Form(...),
):
    """Create a pair manually."""
    try:
        session = get_db_session()
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        tournament_repo = TournamentRepository(session)

        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Validate players exist
        p1 = player_repo.get_by_id(player1_id)
        p2 = player_repo.get_by_id(player2_id)

        if not p1 or not p2:
            request.session["flash_message"] = "Uno o ambos jugadores no existen."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-pairs", status_code=303)

        if player1_id == player2_id:
            request.session["flash_message"] = "Los dos jugadores deben ser diferentes."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-pairs", status_code=303)

        categoria = categoria.strip().upper()
        if not is_doubles_category(categoria):
            request.session["flash_message"] = f"{categoria} no es una categoría de dobles (debe terminar en BD, GD, o ser MD/WD/XD)."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-pairs", status_code=303)

        # For XD (mixed doubles), validate genders
        if categoria.upper() in ("XD",) or categoria.upper().endswith("XD"):
            genders = set()
            if hasattr(p1, "genero"):
                g1 = p1.genero.value if hasattr(p1.genero, "value") else str(p1.genero)
                genders.add(g1)
            if hasattr(p2, "genero"):
                g2 = p2.genero.value if hasattr(p2.genero, "value") else str(p2.genero)
                genders.add(g2)
            if genders != {"M", "F"}:
                request.session["flash_message"] = "Para dobles mixtos (XD), la pareja debe ser un hombre y una mujer."
                request.session["flash_type"] = "error"
                return RedirectResponse(url="/admin/import-pairs", status_code=303)

        pair = Pair(
            id=0,
            player1_id=player1_id,
            player2_id=player2_id,
            categoria=categoria,
            ranking_pts=ranking_pts,
        )
        pair_repo.create(pair, tournament_id=tournament_id)

        # Auto-assign seeds for the category
        pair_repo.assign_seeds(categoria, tournament_id=tournament_id)

        request.session["flash_message"] = f"Pareja {p1.apellido}/{p2.apellido} creada exitosamente en {categoria}."
        request.session["flash_type"] = "success"

    except Exception as e:
        request.session["flash_message"] = f"Error al crear pareja: {str(e)}"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/admin/import-pairs", status_code=303)


@app.post("/admin/pair/{pair_id}/delete")
async def admin_delete_pair(request: Request, pair_id: int):
    """Delete a pair."""
    try:
        session = get_db_session()
        pair_repo = PairRepository(session)

        pair = pair_repo.get_by_id(pair_id)
        if not pair:
            request.session["flash_message"] = "Pareja no encontrada."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-pairs", status_code=303)

        categoria = pair.categoria
        pair_repo.delete(pair_id)

        # Recalculate seeds
        tournament_repo = TournamentRepository(session)
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None
        pair_repo.assign_seeds(categoria, tournament_id=tournament_id)

        request.session["flash_message"] = "Pareja eliminada exitosamente."
        request.session["flash_type"] = "success"

    except Exception as e:
        request.session["flash_message"] = f"Error al eliminar pareja: {str(e)}"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/admin/import-pairs", status_code=303)


# ============================================================
# TEAMS IMPORT ROUTES
# ============================================================

@app.get("/admin/import-teams")
async def admin_import_teams_form(request: Request):
    """Redirect to unified import page."""
    return RedirectResponse(url="/admin/import-players", status_code=302)


@app.post("/admin/import-teams/csv")
async def admin_import_teams_csv(
    request: Request,
    csv_file: UploadFile = File(...),
    auto_seeds: Optional[str] = Form(None),
    team_match_system: str = Form("swaythling"),
):
    """Import teams from CSV. Creates players automatically if they don't exist.

    CSV format: team_name,pais_cd,nombre1,apellido1,pais1,nombre2,apellido2,pais2,
                nombre3,apellido3,pais3,ranking_pts,categoria
    Optional: nombre4,apellido4,pais4,nombre5,apellido5,pais5
    """
    import csv
    import io
    from ettem.models import Player, Gender, Team, is_teams_category

    try:
        content = await csv_file.read()
        text = content.decode("utf-8-sig")

        session = get_db_session()
        player_repo = PlayerRepository(session)
        team_repo = TeamRepository(session)
        tournament_repo = TournamentRepository(session)

        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        reader = csv.DictReader(io.StringIO(text))
        imported_teams = 0
        created_players = 0
        errors = []

        # Pre-load existing players for dedup
        all_players = player_repo.get_all(tournament_id=tournament_id)
        player_index = {}
        for p in all_players:
            key = (p.nombre.strip().lower(), p.apellido.strip().lower(), p.pais_cd.strip().upper())
            player_index[key] = p

        # Pre-load existing teams for dedup
        existing_teams = team_repo.get_all(tournament_id=tournament_id)
        existing_team_names = {(t.name.strip().lower(), t.categoria.strip().upper()) for t in existing_teams}

        def infer_gender(categoria: str) -> str:
            cat = categoria.upper().strip()
            if cat.endswith("WT") or cat.endswith("GT"):
                return "F"
            return "M"

        def find_or_create_player(nombre, apellido, pais_cd, categoria, tournament_id):
            nonlocal created_players
            key = (nombre.strip().lower(), apellido.strip().lower(), pais_cd.strip().upper())
            if key in player_index:
                return player_index[key]
            genero = infer_gender(categoria)
            player = Player(
                id=0,
                nombre=nombre.strip(),
                apellido=apellido.strip(),
                genero=Gender.MALE if genero == "M" else Gender.FEMALE,
                pais_cd=pais_cd.strip().upper(),
                ranking_pts=0,
                categoria=categoria.strip().upper(),
            )
            player_orm = player_repo.create(player, tournament_id=tournament_id)
            player_index[key] = player_orm
            created_players += 1
            return player_orm

        for row_num, row in enumerate(reader, start=2):
            try:
                team_name = row.get("team_name", "").strip()
                pais_cd = row.get("pais_cd", "").strip().upper()
                categoria = row.get("categoria", "").strip().upper()
                ranking_pts = float(row.get("ranking_pts", "0").strip() or "0")

                if not all([team_name, pais_cd, categoria]):
                    errors.append(f"Fila {row_num}: campos requeridos vacíos (team_name, pais_cd, categoria)")
                    continue

                if not is_teams_category(categoria):
                    errors.append(f"Fila {row_num}: {categoria} no es categoría de equipos (debe terminar en BT, GT, MT o WT)")
                    continue

                if len(pais_cd) != 3:
                    errors.append(f"Fila {row_num}: código de país debe ser 3 letras")
                    continue

                # Skip if team already exists
                if (team_name.lower(), categoria) in existing_team_names:
                    errors.append(f"Fila {row_num}: equipo '{team_name}' ya existe en {categoria}")
                    continue

                # Find or create 3-5 players
                player_ids = []
                for j in range(1, 6):
                    nombre_key = f"nombre{j}"
                    apellido_key = f"apellido{j}"
                    pais_key = f"pais{j}"

                    nombre = row.get(nombre_key, "").strip()
                    apellido = row.get(apellido_key, "").strip()
                    pais = row.get(pais_key, "").strip().upper()

                    if nombre and apellido and pais:
                        p = find_or_create_player(nombre, apellido, pais, categoria, tournament_id)
                        player_ids.append(p.id)

                if len(player_ids) < 3:
                    errors.append(f"Fila {row_num}: se requieren al menos 3 jugadores, solo se encontraron {len(player_ids)}")
                    continue

                # Create team
                team = Team(
                    id=0,
                    name=team_name,
                    categoria=categoria,
                    pais_cd=pais_cd,
                    ranking_pts=ranking_pts,
                    player_ids=player_ids,
                )
                team_repo.create(team, tournament_id=tournament_id)
                imported_teams += 1
                existing_team_names.add((team_name.lower(), categoria))

            except (ValueError, KeyError) as e:
                errors.append(f"Fila {row_num}: {str(e)}")

        # Assign seeds if requested
        if auto_seeds == "1" and imported_teams > 0:
            all_teams = team_repo.get_all(tournament_id=tournament_id)
            cats = set(t.categoria for t in all_teams)
            for cat in cats:
                team_repo.assign_seeds(cat, tournament_id=tournament_id)

        # Build message
        parts = []
        if imported_teams > 0:
            parts.append(f"{imported_teams} equipos importados")
        if created_players > 0:
            parts.append(f"{created_players} jugadores creados")
        msg = ", ".join(parts) + "." if parts else "No se importaron equipos."
        if errors:
            msg += f" ({len(errors)} errores: {'; '.join(errors[:5])})"

        request.session["flash_message"] = msg
        request.session["flash_type"] = "success" if imported_teams > 0 else "warning"
        # Store team match system for use when creating groups
        if imported_teams > 0 and team_match_system:
            request.session["team_match_system"] = team_match_system

    except Exception as e:
        request.session["flash_message"] = f"Error al importar CSV: {str(e)}"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/admin/import-players", status_code=303)


@app.post("/admin/import-teams/manual")
async def admin_import_teams_manual(
    request: Request,
    team_name: str = Form(...),
    pais_cd: str = Form(...),
    categoria: str = Form(...),
    ranking_pts: float = Form(0),
    player1_id: int = Form(...),
    player2_id: int = Form(...),
    player3_id: int = Form(...),
    player4_id: Optional[int] = Form(None),
    player5_id: Optional[int] = Form(None),
):
    """Create a team manually from form data."""
    from ettem.models import Team, is_teams_category

    try:
        session = get_db_session()
        player_repo = PlayerRepository(session)
        team_repo = TeamRepository(session)
        tournament_repo = TournamentRepository(session)

        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        categoria = categoria.strip().upper()
        if not is_teams_category(categoria):
            request.session["flash_message"] = f"{categoria} no es una categoría de equipos."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-players", status_code=303)

        # Collect player IDs
        player_ids = [player1_id, player2_id, player3_id]
        if player4_id:
            player_ids.append(player4_id)
        if player5_id:
            player_ids.append(player5_id)

        # Validate all players exist
        for pid in player_ids:
            p = player_repo.get_by_id(pid)
            if not p:
                request.session["flash_message"] = f"Jugador con ID {pid} no encontrado."
                request.session["flash_type"] = "error"
                return RedirectResponse(url="/admin/import-players", status_code=303)

        # Check no duplicate player IDs
        if len(set(player_ids)) != len(player_ids):
            request.session["flash_message"] = "Un jugador no puede aparecer dos veces en el mismo equipo."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-players", status_code=303)

        team = Team(
            id=0,
            name=team_name.strip(),
            categoria=categoria,
            pais_cd=pais_cd.strip().upper(),
            ranking_pts=ranking_pts,
            player_ids=player_ids,
        )
        team_repo.create(team, tournament_id=tournament_id)

        # Auto-assign seeds for the category
        team_repo.assign_seeds(categoria, tournament_id=tournament_id)

        request.session["flash_message"] = f"Equipo '{team_name}' creado exitosamente en {categoria}."
        request.session["flash_type"] = "success"

    except Exception as e:
        request.session["flash_message"] = f"Error al crear equipo: {str(e)}"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/admin/import-players", status_code=303)


@app.post("/admin/team/{team_id}/delete")
async def admin_delete_team(request: Request, team_id: int):
    """Delete a team."""
    try:
        session = get_db_session()
        team_repo = TeamRepository(session)

        team = team_repo.get_by_id(team_id)
        if not team:
            request.session["flash_message"] = "Equipo no encontrado."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-players", status_code=303)

        # Don't allow deleting teams that are already in groups
        if team.group_id:
            request.session["flash_message"] = "No se puede eliminar un equipo que ya está en un grupo."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/import-players", status_code=303)

        categoria = team.categoria
        team_repo.delete(team_id)

        # Recalculate seeds
        tournament_repo = TournamentRepository(session)
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None
        team_repo.assign_seeds(categoria, tournament_id=tournament_id)

        request.session["flash_message"] = "Equipo eliminado exitosamente."
        request.session["flash_type"] = "success"

    except Exception as e:
        request.session["flash_message"] = f"Error al eliminar equipo: {str(e)}"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/admin/import-players", status_code=303)


# ============================================================
# TEAM MATCH (ENCOUNTER) ROUTES
# ============================================================

@app.get("/team-match/{match_id}", response_class=HTMLResponse)
async def team_match_view(request: Request, match_id: int):
    """View a team encounter with its individual matches."""
    from ettem.models import TEAM_MATCH_ORDERS, TeamMatchSystem, get_team_match_majority

    session = get_db_session()
    match_repo = MatchRepository(session)
    team_repo = TeamRepository(session)
    player_repo = PlayerRepository(session)
    detail_repo = TeamMatchDetailRepository(session)

    match_orm = match_repo.get_by_id(match_id)
    if not match_orm:
        return HTMLResponse(content="Encuentro no encontrado", status_code=404)

    # Get teams
    team1 = team_repo.get_by_id(match_orm.team1_id) if match_orm.team1_id else None
    team2 = team_repo.get_by_id(match_orm.team2_id) if match_orm.team2_id else None
    team1_name = team1.name if team1 else "Equipo 1"
    team2_name = team2.name if team2 else "Equipo 2"
    team1_pais = team1.pais_cd if team1 else "---"
    team2_pais = team2.pais_cd if team2 else "---"

    # Team match system
    system = match_orm.team_match_system or TeamMatchSystem.SWAYTHLING
    system_labels = {
        TeamMatchSystem.SWAYTHLING: "Swaythling (5S)",
        TeamMatchSystem.CORBILLON: "Corbillon (4S+1D)",
        TeamMatchSystem.OLYMPIC: "Olimpico (4S+1D)",
        TeamMatchSystem.BEST_OF_7: "Best of 7 (6S+1D)",
        TeamMatchSystem.BEST_OF_9: "Best of 9 (9S)",
    }
    system_label = system_labels.get(system, system)
    order = TEAM_MATCH_ORDERS.get(system, [])
    total_matches = len(order)
    majority = get_team_match_majority(system)

    # Get individual match details
    detail_orms = detail_repo.get_by_parent_match(match_id)

    # Check if players are assigned
    players_assigned = len(detail_orms) > 0 and any(d.player1_id for d in detail_orms)

    # Build details display
    details = []
    for d in detail_orms:
        p1 = player_repo.get_by_id(d.player1_id) if d.player1_id else None
        p2 = player_repo.get_by_id(d.player2_id) if d.player2_id else None
        p1b = player_repo.get_by_id(d.player1b_id) if d.player1b_id else None
        p2b = player_repo.get_by_id(d.player2b_id) if d.player2b_id else None

        details.append({
            "id": d.id,
            "match_number": d.match_number,
            "match_type": d.match_type,
            "home_label": d.label_home or "",
            "away_label": d.label_away or "",
            "player1_name": f"{p1.nombre} {p1.apellido}" if p1 else None,
            "player2_name": f"{p2.nombre} {p2.apellido}" if p2 else None,
            "player1b_name": f"{p1b.nombre} {p1b.apellido}" if p1b else None,
            "player2b_name": f"{p2b.nombre} {p2b.apellido}" if p2b else None,
            "status": d.status,
            "winner_side": d.winner_side,
            "sets": [{"player1_points": s["player1_points"], "player2_points": s["player2_points"]} for s in d.sets],
        })

    # Team scores
    team1_score = match_orm.team1_score or 0
    team2_score = match_orm.team2_score or 0

    # Winner name
    winner_name = ""
    if match_orm.winner_id:
        winner_team = team_repo.get_by_id(match_orm.winner_id)
        winner_name = winner_team.name if winner_team else ""

    # Get player labels needed for assignment
    home_labels = sorted(set(lbl for _, _, lbl, _ in order if lbl != "doubles"))
    away_labels = sorted(set(lbl for _, _, _, lbl in order if lbl != "doubles"))
    # For compound labels like "B&C", split into individual letters
    all_home_letters = set()
    for lbl in home_labels:
        for part in lbl.split("&"):
            all_home_letters.add(part.strip())
    all_away_letters = set()
    for lbl in away_labels:
        for part in lbl.split("&"):
            all_away_letters.add(part.strip())
    home_labels = sorted(all_home_letters)
    away_labels = sorted(all_away_letters)

    # Get team players for assignment dropdowns
    team1_players = []
    team2_players = []
    if team1:
        for pid in team1.player_ids:
            p = player_repo.get_by_id(pid)
            if p:
                team1_players.append(p)
    if team2:
        for pid in team2.player_ids:
            p = player_repo.get_by_id(pid)
            if p:
                team2_players.append(p)

    return render_template(
        "team_match.html",
        {
            "request": request,
            "match": match_orm,
            "match_status": match_orm.status,
            "team1_name": team1_name,
            "team2_name": team2_name,
            "team1_pais": team1_pais,
            "team2_pais": team2_pais,
            "team1_score": team1_score,
            "team2_score": team2_score,
            "winner_name": winner_name,
            "system": system,
            "system_label": system_label,
            "total_matches": total_matches,
            "majority": majority,
            "players_assigned": players_assigned,
            "details": details,
            "home_labels": home_labels,
            "away_labels": away_labels,
            "team1_players": team1_players,
            "team2_players": team2_players,
            "match_order": order,
        },
    )


@app.post("/team-match/{match_id}/assign-players")
async def team_match_assign_players(request: Request, match_id: int):
    """Assign players to positions and create individual match details."""
    from ettem.models import TEAM_MATCH_ORDERS, TeamMatchSystem

    session = get_db_session()
    match_repo = MatchRepository(session)
    team_repo = TeamRepository(session)
    detail_repo = TeamMatchDetailRepository(session)

    match_orm = match_repo.get_by_id(match_id)
    if not match_orm:
        request.session["flash_message"] = "Encuentro no encontrado."
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/", status_code=303)

    form = await request.form()
    system = match_orm.team_match_system or TeamMatchSystem.SWAYTHLING
    order = TEAM_MATCH_ORDERS.get(system, [])

    # Parse player assignments from form: home_A=player_id, away_X=player_id, etc.
    home_assignments = {}
    away_assignments = {}
    for key, value in form.items():
        if key.startswith("home_") and value:
            label = key[5:]  # "A", "B", "C", etc.
            home_assignments[label] = int(value)
        elif key.startswith("away_") and value:
            label = key[5:]
            away_assignments[label] = int(value)

    # Validate no duplicate players within the same team
    home_ids = list(home_assignments.values())
    away_ids = list(away_assignments.values())
    if len(home_ids) != len(set(home_ids)):
        request.session["flash_message"] = "Error: Un jugador no puede ocupar dos posiciones en el mismo equipo."
        request.session["flash_type"] = "error"
        return RedirectResponse(url=f"/team-match/{match_id}", status_code=303)
    if len(away_ids) != len(set(away_ids)):
        request.session["flash_message"] = "Error: Un jugador no puede ocupar dos posiciones en el mismo equipo."
        request.session["flash_type"] = "error"
        return RedirectResponse(url=f"/team-match/{match_id}", status_code=303)

    # Delete existing details (in case of re-assignment)
    detail_repo.delete_by_parent_match(match_id)

    # Create individual match details
    details = []
    for match_num, match_type, home_label, away_label in order:
        d = TeamMatchDetailORM(
            parent_match_id=match_id,
            match_number=match_num,
            match_type=match_type,
            label_home=home_label,
            label_away=away_label,
            best_of=5,
            status="pending",
        )

        if match_type == "singles":
            d.player1_id = home_assignments.get(home_label)
            d.player2_id = away_assignments.get(away_label)
        elif match_type == "doubles":
            # Parse compound labels like "B&C" -> assign both players
            if "&" in home_label:
                parts = home_label.split("&")
                d.player1_id = home_assignments.get(parts[0].strip())
                d.player1b_id = home_assignments.get(parts[1].strip())
            else:
                # Generic "doubles" label — use first two available home players
                home_players = list(home_assignments.values())
                if len(home_players) >= 2:
                    d.player1_id = home_players[0]
                    d.player1b_id = home_players[1]

            if "&" in away_label:
                parts = away_label.split("&")
                d.player2_id = away_assignments.get(parts[0].strip())
                d.player2b_id = away_assignments.get(parts[1].strip())
            else:
                away_players = list(away_assignments.values())
                if len(away_players) >= 2:
                    d.player2_id = away_players[0]
                    d.player2b_id = away_players[1]

        details.append(d)

    detail_repo.create_bulk(details)

    # Mark the encounter as in_progress
    if match_orm.status == "pending":
        match_orm.status = "in_progress"
        match_repo.update(match_orm)

    request.session["flash_message"] = f"Jugadores asignados. {len(details)} partidos individuales creados."
    request.session["flash_type"] = "success"

    return RedirectResponse(url=f"/team-match/{match_id}", status_code=303)


@app.get("/team-match/{match_id}/detail/{detail_id}/enter-result", response_class=HTMLResponse)
async def team_match_detail_result_form(request: Request, match_id: int, detail_id: int):
    """Show form to enter result for an individual team match."""
    session = get_db_session()
    match_repo = MatchRepository(session)
    team_repo = TeamRepository(session)
    player_repo = PlayerRepository(session)
    detail_repo = TeamMatchDetailRepository(session)

    match_orm = match_repo.get_by_id(match_id)
    detail = detail_repo.get_by_id(detail_id)
    if not match_orm or not detail:
        return HTMLResponse(content="Partido no encontrado", status_code=404)

    team1 = team_repo.get_by_id(match_orm.team1_id) if match_orm.team1_id else None
    team2 = team_repo.get_by_id(match_orm.team2_id) if match_orm.team2_id else None

    # Build player names
    p1 = player_repo.get_by_id(detail.player1_id) if detail.player1_id else None
    p2 = player_repo.get_by_id(detail.player2_id) if detail.player2_id else None
    p1b = player_repo.get_by_id(detail.player1b_id) if detail.player1b_id else None
    p2b = player_repo.get_by_id(detail.player2b_id) if detail.player2b_id else None

    home_name = f"{p1.nombre} {p1.apellido}" if p1 else "Home"
    if p1b:
        home_name += f" / {p1b.nombre} {p1b.apellido}"
    away_name = f"{p2.nombre} {p2.apellido}" if p2 else "Away"
    if p2b:
        away_name += f" / {p2b.nombre} {p2b.apellido}"

    from ettem.models import get_team_match_best_of
    total_matches = get_team_match_best_of(match_orm.team_match_system or "swaythling")
    max_sets = detail.best_of

    return render_template(
        "team_match_detail_result.html",
        {
            "request": request,
            "parent_match_id": match_id,
            "detail": detail,
            "team1_name": team1.name if team1 else "Equipo 1",
            "team2_name": team2.name if team2 else "Equipo 2",
            "home_name": home_name,
            "away_name": away_name,
            "max_sets": max_sets,
            "total_matches": total_matches,
            "existing_sets": detail.sets,
        },
    )


@app.post("/team-match/{match_id}/detail/{detail_id}/save-result")
async def team_match_detail_save_result(request: Request, match_id: int, detail_id: int):
    """Save result for an individual match within a team encounter."""
    from ettem.models import get_team_match_majority

    session = get_db_session()
    match_repo = MatchRepository(session)
    team_repo = TeamRepository(session)
    detail_repo = TeamMatchDetailRepository(session)

    match_orm = match_repo.get_by_id(match_id)
    detail = detail_repo.get_by_id(detail_id)
    if not match_orm or not detail or detail.parent_match_id != match_id:
        request.session["flash_message"] = "Partido no encontrado."
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/", status_code=303)

    form = await request.form()

    # Check for walkover
    is_walkover = form.get("is_walkover") == "true"
    if is_walkover:
        wo_winner_side = form.get("winner_side", "")
        if wo_winner_side not in ("1", "2"):
            request.session["flash_message"] = "Error: Para walkover debes seleccionar un ganador."
            request.session["flash_type"] = "error"
            return RedirectResponse(url=f"/team-match/{match_id}/detail/{detail_id}/enter-result", status_code=303)
        winner_side = int(wo_winner_side)
        detail.sets = []
        detail.winner_side = winner_side
        detail.status = "completed"
        detail_repo.update(detail)
    else:
        # Parse sets from form
        sets_data = []
        p1_sets_won = 0
        p2_sets_won = 0
        for i in range(1, detail.best_of + 1):
            p1_raw = form.get(f"set{i}_p1", "")
            p2_raw = form.get(f"set{i}_p2", "")
            if p1_raw == "" or p2_raw == "":
                break
            p1_pts = int(p1_raw)
            p2_pts = int(p2_raw)
            if p1_pts == 0 and p2_pts == 0:
                break
            sets_data.append({
                "set_number": i,
                "player1_points": p1_pts,
                "player2_points": p2_pts,
            })
            if p1_pts > p2_pts:
                p1_sets_won += 1
            elif p2_pts > p1_pts:
                p2_sets_won += 1

        # Determine winner of individual match
        sets_to_win = (detail.best_of // 2) + 1
        winner_side = None
        if p1_sets_won >= sets_to_win:
            winner_side = 1
        elif p2_sets_won >= sets_to_win:
            winner_side = 2

        # Update detail
        detail.sets = sets_data
        detail.winner_side = winner_side
        detail.status = "completed" if winner_side else "in_progress"
    detail_repo.update(detail)

    # Recalculate team scores from all completed details
    all_details = detail_repo.get_by_parent_match(match_id)
    team1_score = sum(1 for d in all_details if d.winner_side == 1)
    team2_score = sum(1 for d in all_details if d.winner_side == 2)

    match_orm.team1_score = team1_score
    match_orm.team2_score = team2_score

    # Check if encounter is decided
    system = match_orm.team_match_system or "swaythling"
    majority = get_team_match_majority(system)

    if team1_score >= majority or team2_score >= majority:
        # Encounter decided
        if team1_score >= majority:
            match_orm.winner_id = match_orm.team1_id
        else:
            match_orm.winner_id = match_orm.team2_id
        match_orm.status = "completed"

        # Store individual match wins as sets on parent MatchORM (for standings)
        parent_sets = []
        for d in all_details:
            if d.winner_side:
                parent_sets.append({
                    "set_number": d.match_number,
                    "player1_points": 1 if d.winner_side == 1 else 0,
                    "player2_points": 1 if d.winner_side == 2 else 0,
                })
        match_orm.sets_json = __import__("json").dumps(parent_sets)

        # Mark remaining pending matches as not_needed
        for d in all_details:
            if d.status == "pending":
                d.status = "not_needed"
                detail_repo.update(d)

        match_repo.update(match_orm)

        # Recalculate and persist group standings for team matches
        if match_orm.group_id is not None:
            standing_repo = StandingRepository(session)
            player_repo = PlayerRepository(session)
            pair_repo = PairRepository(session)
            team_repo_standings = TeamRepository(session)
            event_type = detect_event_type(match_orm.category) if match_orm.category else "teams"
            group_matches_orm = match_repo.get_by_group(match_orm.group_id)
            matches_domain = []
            for gm in group_matches_orm:
                sets_list = [
                    Set(set_number=s["set_number"], player1_points=s["player1_points"], player2_points=s["player2_points"])
                    for s in gm.sets
                ]
                matches_domain.append(Match(
                    id=gm.id, player1_id=gm.competitor1_id, player2_id=gm.competitor2_id,
                    group_id=gm.group_id, round_type=gm.round_type, status=gm.status,
                    sets=sets_list, winner_id=gm.winner_id,
                ))
            standings, _ = calculate_standings(
                matches_domain, match_orm.group_id, player_repo,
                event_type=event_type, pair_repo=pair_repo, team_repo=team_repo_standings,
            )
            standing_repo.delete_by_group(match_orm.group_id)
            for standing in standings:
                standing_repo.create(standing)

        # For bracket matches, advance the winner to the next round
        if match_orm.group_id is None and match_orm.winner_id:
            tournament_repo = TournamentRepository(session)
            current_tournament = tournament_repo.get_current()
            tournament_id = current_tournament.id if current_tournament else None
            category = match_orm.category
            if category:
                advance_bracket_winner(match_orm, match_orm.winner_id, category, session, tournament_id=tournament_id)
    else:
        match_orm.status = "in_progress"
        match_repo.update(match_orm)

    request.session["flash_message"] = f"Resultado guardado. Marcador: {team1_score}-{team2_score}"
    request.session["flash_type"] = "success"

    return RedirectResponse(url=f"/team-match/{match_id}", status_code=303)


@app.get("/admin/create-groups", response_class=HTMLResponse)
async def admin_create_groups_form(request: Request):
    """Show create groups form."""
    session = get_db_session()
    player_repo = PlayerRepository(session)
    group_repo = GroupRepository(session)
    match_repo = MatchRepository(session)
    tournament_repo = TournamentRepository(session)
    team_repo = TeamRepository(session)

    # Get current tournament - show empty state if none exists
    current_tournament = tournament_repo.get_current()
    if not current_tournament:
        return render_template("admin_create_groups.html", {
            "request": request,
            "tournament": None,
        })

    tournament_id = current_tournament.id

    # Get all players grouped by category for current tournament
    all_players = player_repo.get_all(tournament_id=tournament_id)
    categories_dict = {}
    countries_by_category = {}  # Track country distribution per category

    # Collect team categories first so we can skip individual players in those categories
    all_teams = team_repo.get_all(tournament_id=tournament_id)
    team_categories = set()
    for team_orm in all_teams:
        team_categories.add(team_orm.categoria)

    for player in all_players:
        # Skip individual players in team categories (teams are counted separately)
        if player.categoria in team_categories:
            continue
        if player.categoria not in categories_dict:
            categories_dict[player.categoria] = 0
            countries_by_category[player.categoria] = {}
        categories_dict[player.categoria] += 1

        # Count countries per category
        if player.pais_cd not in countries_by_category[player.categoria]:
            countries_by_category[player.categoria][player.pais_cd] = 0
        countries_by_category[player.categoria][player.pais_cd] += 1

    # Add teams categories (count teams, not individual players)
    for team_orm in all_teams:
        cat = team_orm.categoria
        if cat not in categories_dict:
            categories_dict[cat] = 0
            countries_by_category[cat] = {}
        categories_dict[cat] += 1
        pais = team_orm.pais_cd or "---"
        if pais not in countries_by_category[cat]:
            countries_by_category[cat][pais] = 0
        countries_by_category[cat][pais] += 1

    # Convert to list for template with country stats
    import json
    available_categories = [
        {
            "name": cat,
            "count": count,
            "countries": json.dumps(countries_by_category.get(cat, {}))
        }
        for cat, count in sorted(categories_dict.items())
    ]

    # Get existing groups for current tournament
    all_groups = group_repo.get_all(tournament_id=tournament_id)
    existing_groups = []
    for group in all_groups:
        match_count = len(match_repo.get_by_group(group.id))
        existing_groups.append({
            "category": group.category,
            "name": group.name,
            "player_count": len(group.player_ids),
            "match_count": match_count
        })

    return render_template(
        "admin_create_groups.html",
        {
            "request": request,
            "available_categories": available_categories,
            "existing_groups": existing_groups,
            "tournament": current_tournament
        }
    )


@app.post("/admin/create-groups/preview")
async def admin_create_groups_preview(
    request: Request,
    category: str = Form(...),
    group_size_preference: int = Form(...),
    random_seed: Optional[int] = Form(None)
):
    """Generate preview of group distribution with snake seeding."""
    from ettem.group_builder import create_groups

    try:
        session = get_db_session()
        player_repo = PlayerRepository(session)
        tournament_repo = TournamentRepository(session)
        team_repo = TeamRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        event_type = detect_event_type(category)

        if event_type == "teams":
            # Get teams for this category
            team_orms = team_repo.get_by_category_sorted_by_seed(category, tournament_id=tournament_id)
            if not team_orms:
                return JSONResponse({"error": f"No se encontraron equipos para la categoría {category}."}, status_code=400)

            # Auto-assign seeds if needed
            if any(t.seed is None for t in team_orms):
                team_repo.assign_seeds(category, tournament_id=tournament_id)
                team_orms = team_repo.get_by_category_sorted_by_seed(category, tournament_id=tournament_id)

            # Convert to domain models (Team has .id, .seed, .pais_cd — works with create_groups)
            competitors = []
            for t_orm in team_orms:
                t = Team(
                    id=t_orm.id,
                    name=t_orm.name,
                    categoria=t_orm.categoria,
                    pais_cd=t_orm.pais_cd,
                    ranking_pts=t_orm.ranking_pts,
                    seed=t_orm.seed,
                    player_ids=t_orm.player_ids,
                )
                competitors.append(t)

            groups, _ = create_groups(
                players=competitors,
                category=category,
                group_size_preference=group_size_preference,
                random_seed=random_seed if random_seed else 42,
                event_type=event_type,
            )

            groups_preview = []
            for group in groups:
                group_items = []
                for team_id in group.player_ids:
                    team = next((t for t in competitors if t.id == team_id), None)
                    if team:
                        group_items.append({
                            "id": team.id,
                            "nombre": team.name,
                            "apellido": "",
                            "pais_cd": team.pais_cd,
                            "ranking_pts": team.ranking_pts,
                            "seed": team.seed,
                        })
                groups_preview.append({"name": group.name, "players": group_items})

            return JSONResponse({
                "category": category,
                "group_size_preference": group_size_preference,
                "random_seed": random_seed if random_seed else 42,
                "groups": groups_preview,
                "total_players": len(competitors),
            })

        # Singles / Doubles — original logic
        # Get players for this category in current tournament
        player_orms = player_repo.get_by_category_sorted_by_seed(category, tournament_id=tournament_id)

        if not player_orms:
            request.session["flash_message"] = f"No se encontraron jugadores para la categoría {category}."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/create-groups", status_code=303)

        # Auto-assign seeds if not already assigned
        if any(p.seed is None for p in player_orms):
            player_repo.assign_seeds(category)
            player_orms = player_repo.get_by_category_sorted_by_seed(category, tournament_id=tournament_id)

        # Convert ORM to domain models
        players = []
        for p_orm in player_orms:
            player = Player(
                id=p_orm.id,
                nombre=p_orm.nombre,
                apellido=p_orm.apellido,
                genero=p_orm.genero,
                pais_cd=p_orm.pais_cd,
                ranking_pts=p_orm.ranking_pts,
                categoria=p_orm.categoria,
                seed=p_orm.seed,
                original_id=p_orm.original_id,
                tournament_number=p_orm.tournament_number,
                group_id=p_orm.group_id,
                group_number=p_orm.group_number,
                checked_in=p_orm.checked_in,
                notes=p_orm.notes,
            )
            players.append(player)

        # Create groups (preview only, not saved)
        groups, _ = create_groups(
            players=players,
            category=category,
            group_size_preference=group_size_preference,
            random_seed=random_seed if random_seed else 42,
        )

        # Organize groups for display
        groups_preview = []
        for group in groups:
            group_players = []
            for player_id in group.player_ids:
                player = next((p for p in players if p.id == player_id), None)
                if player:
                    group_players.append({
                        "id": player.id,
                        "nombre": player.nombre,
                        "apellido": player.apellido,
                        "pais_cd": player.pais_cd,
                        "ranking_pts": player.ranking_pts,
                        "seed": player.seed
                    })

            groups_preview.append({
                "name": group.name,
                "players": group_players
            })

        # Return JSON for modal rendering
        return JSONResponse({
            "category": category,
            "group_size_preference": group_size_preference,
            "random_seed": random_seed if random_seed else 42,
            "groups": groups_preview,
            "total_players": len(players)
        })

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/admin/create-groups/execute")
async def admin_create_groups_execute(
    request: Request,
    category: str = Form(...),
    group_size_preference: int = Form(...),
    random_seed: Optional[int] = Form(None),
    manual_assignments: Optional[str] = Form(None),
    best_of: int = Form(5),
    team_match_system: Optional[str] = Form(None)
):
    """Execute group creation. Supports singles, doubles, and teams categories."""
    from ettem.group_builder import create_groups
    import json

    try:
        # Initialize repositories
        session = get_db_session()
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        group_repo = GroupRepository(session)
        match_repo = MatchRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Detect event type from category
        event_type = detect_event_type(category)

        # Resolve team match system: form param > session > default
        if not team_match_system:
            team_match_system = request.session.get("team_match_system", "swaythling")

        if event_type == "teams":
            # Get teams for this teams category
            team_orms = team_repo.get_by_category_sorted_by_seed(category, tournament_id=tournament_id)
            if not team_orms:
                request.session["flash_message"] = f"No se encontraron equipos para la categoría {category}. Importa equipos primero."
                request.session["flash_type"] = "error"
                return RedirectResponse(url="/admin/create-groups", status_code=303)

            # Auto-assign seeds if needed
            if any(t.seed is None for t in team_orms):
                team_repo.assign_seeds(category, tournament_id=tournament_id)
                team_orms = team_repo.get_by_category_sorted_by_seed(category, tournament_id=tournament_id)

            # Convert ORM to domain Team models
            competitors = []
            for t_orm in team_orms:
                t = Team(
                    id=t_orm.id,
                    name=t_orm.name,
                    categoria=t_orm.categoria,
                    pais_cd=t_orm.pais_cd,
                    ranking_pts=t_orm.ranking_pts,
                    seed=t_orm.seed,
                    group_id=t_orm.group_id,
                    group_number=t_orm.group_number,
                    player_ids=t_orm.player_ids,
                )
                competitors.append(t)

        elif event_type == "doubles":
            # Get pairs for this doubles category
            pair_orms = pair_repo.get_by_category_sorted_by_seed(category, tournament_id=tournament_id)
            if not pair_orms:
                request.session["flash_message"] = f"No se encontraron parejas para la categoría {category}. Importa parejas primero."
                request.session["flash_type"] = "error"
                return RedirectResponse(url="/admin/create-groups", status_code=303)

            # Auto-assign seeds if not already assigned
            if any(p.seed is None for p in pair_orms):
                pair_repo.assign_seeds(category, tournament_id=tournament_id)
                pair_orms = pair_repo.get_by_category_sorted_by_seed(category, tournament_id=tournament_id)

            # Convert ORM to domain Pair models
            competitors = []
            for pair_orm in pair_orms:
                pair = Pair(
                    id=pair_orm.id,
                    player1_id=pair_orm.player1_id,
                    player2_id=pair_orm.player2_id,
                    categoria=pair_orm.categoria,
                    ranking_pts=pair_orm.ranking_pts,
                    seed=pair_orm.seed,
                    group_id=pair_orm.group_id,
                    group_number=pair_orm.group_number,
                    notes=pair_orm.notes,
                )
                # Populate player info for display
                pair.player1 = player_repo.get_by_id(pair_orm.player1_id)
                pair.player2 = player_repo.get_by_id(pair_orm.player2_id)
                competitors.append(pair)
        else:
            # Get players for this singles category
            player_orms = player_repo.get_by_category_sorted_by_seed(category, tournament_id=tournament_id)
            if not player_orms:
                request.session["flash_message"] = f"No se encontraron jugadores para la categoría {category}. Importa jugadores primero."
                request.session["flash_type"] = "error"
                return RedirectResponse(url="/admin/create-groups", status_code=303)

            # Auto-assign seeds if not already assigned
            if any(p.seed is None for p in player_orms):
                player_repo.assign_seeds(category)
                player_orms = player_repo.get_by_category_sorted_by_seed(category, tournament_id=tournament_id)

            # Convert ORM to domain Player models
            competitors = []
            for p_orm in player_orms:
                player = Player(
                    id=p_orm.id,
                    nombre=p_orm.nombre,
                    apellido=p_orm.apellido,
                    genero=p_orm.genero,
                    pais_cd=p_orm.pais_cd,
                    ranking_pts=p_orm.ranking_pts,
                    categoria=p_orm.categoria,
                    seed=p_orm.seed,
                    original_id=p_orm.original_id,
                    tournament_number=p_orm.tournament_number,
                    group_id=p_orm.group_id,
                    group_number=p_orm.group_number,
                    checked_in=p_orm.checked_in,
                    notes=p_orm.notes,
                )
                competitors.append(player)

        # Delete existing groups and matches for this category in current tournament
        existing_groups = group_repo.get_by_category(category, tournament_id=tournament_id)
        for group in existing_groups:
            matches = match_repo.get_by_group(group.id)
            for match in matches:
                match_repo.delete(match.id)
            group_repo.delete(group.id)

        # Check if we have manual assignments
        if manual_assignments and manual_assignments.strip() and event_type not in ("doubles", "teams"):
            assignments = json.loads(manual_assignments)
            groups, matches = create_groups_from_manual_assignments(
                players=competitors,
                category=category,
                assignments=assignments
            )
        else:
            groups, matches = create_groups(
                players=competitors,
                category=category,
                group_size_preference=group_size_preference,
                random_seed=random_seed if random_seed else 42,
                event_type=event_type,
            )

        # Save to database
        for group in groups:
            group_orm = group_repo.create(group, tournament_id=tournament_id)

            # Update group assignment on competitors
            for entity_id in group.player_ids:
                if event_type == "teams":
                    t_orm = team_repo.get_by_id(entity_id)
                    if t_orm:
                        t_orm.group_id = group_orm.id
                        for c in competitors:
                            if c.id == entity_id:
                                t_orm.group_number = c.group_number
                                break
                    team_repo.session.commit()
                elif event_type == "doubles":
                    pair_orm = pair_repo.get_by_id(entity_id)
                    if pair_orm:
                        pair_orm.group_id = group_orm.id
                        for c in competitors:
                            if c.id == entity_id:
                                pair_orm.group_number = c.group_number
                                break
                    pair_repo.session.commit()
                else:
                    player_orm = player_repo.get_by_id(entity_id)
                    if player_orm:
                        player_orm.group_id = group_orm.id
                        for c in competitors:
                            if c.id == entity_id:
                                player_orm.group_number = c.group_number
                                break
                    player_repo.session.commit()

            # Save matches for this group
            for match in matches:
                if match.player1_id in group.player_ids and match.player2_id in group.player_ids:
                    match.group_id = group_orm.id
                    # For teams, also set team1_id/team2_id and default match system
                    match_orm = match_repo.create(match, category=category, tournament_id=tournament_id, best_of=best_of, event_type=event_type)
                    if event_type == "teams" and match_orm:
                        match_orm.team1_id = match.player1_id
                        match_orm.team2_id = match.player2_id
                        match_orm.team_match_system = team_match_system
                        match_repo.session.commit()

        # Create empty bracket structure
        advance_per_group = 2
        bracket_repo = BracketRepository(session)
        slots_created, bracket_matches = create_empty_bracket_structure(
            category=category,
            num_groups=len(groups),
            advance_per_group=advance_per_group,
            bracket_repo=bracket_repo,
            match_repo=match_repo,
            tournament_id=tournament_id
        )

        entity_label = "equipos" if event_type == "teams" else "jugadores"
        request.session["flash_message"] = f"Se crearon {len(groups)} grupos con {len(matches)} partidos + {bracket_matches} partidos de bracket para {category}"
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/category/{category}", status_code=303)

    except Exception as e:
        request.session["flash_message"] = f"Error al crear grupos: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/admin/create-groups", status_code=303)


@app.get("/admin/calculate-standings", response_class=HTMLResponse)
async def admin_calculate_standings_form(request: Request):
    """Show calculate standings form."""
    session = get_db_session()
    group_repo = GroupRepository(session)
    match_repo = MatchRepository(session)
    standing_repo = StandingRepository(session)
    player_repo = PlayerRepository(session)
    tournament_repo = TournamentRepository(session)

    # Get current tournament - redirect if none exists
    current_tournament = tournament_repo.get_current()
    if not current_tournament:
        return RedirectResponse(url="/tournaments", status_code=303)

    tournament_id = current_tournament.id

    # Get all groups grouped by category for current tournament
    all_groups = group_repo.get_all(tournament_id=tournament_id)
    categories_dict = {}
    for group in all_groups:
        if group.category not in categories_dict:
            categories_dict[group.category] = {
                "groups": 0,
                "matches": 0
            }
        categories_dict[group.category]["groups"] += 1
        categories_dict[group.category]["matches"] += len(match_repo.get_by_group(group.id))

    # Convert to list for template
    available_categories = [
        {
            "name": cat,
            "groups": data["groups"],
            "matches": data["matches"]
        }
        for cat, data in sorted(categories_dict.items())
    ]

    # Get current standings summary (filtered by tournament via group_ids)
    current_group_ids = set(g.id for g in all_groups)
    all_standings = standing_repo.get_all()
    standings_by_group = {}
    for standing in all_standings:
        # Only include standings from current tournament's groups
        if standing.group_id not in current_group_ids:
            continue
        if standing.group_id not in standings_by_group:
            standings_by_group[standing.group_id] = []
        standings_by_group[standing.group_id].append(standing)

    standings_summary = []
    for group in all_groups:
        if group.id in standings_by_group:
            standings_summary.append({
                "category": group.category,
                "group_name": group.name,
                "count": len(standings_by_group[group.id]),
                "last_updated": None  # Could add timestamp to standings in future
            })

    return render_template(
        "admin_calculate_standings.html",
        {
            "request": request,
            "available_categories": available_categories,
            "standings_summary": standings_summary
        }
    )


@app.post("/admin/calculate-standings/all")
async def admin_calculate_standings_all(request: Request):
    """Calculate standings for all categories."""
    try:
        session = get_db_session()
        group_repo = GroupRepository(session)
        match_repo = MatchRepository(session)
        standing_repo = StandingRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Get all groups for current tournament
        all_groups = group_repo.get_all(tournament_id=tournament_id)

        if not all_groups:
            request.session["flash_message"] = "No hay grupos creados. Crea grupos primero."
            request.session["flash_type"] = "warning"
            return RedirectResponse(url="/admin/calculate-standings", status_code=303)

        total_standings = 0
        categories_processed = set()

        for group_orm in all_groups:
            categories_processed.add(group_orm.category)
            event_type = detect_event_type(group_orm.category)

            # Get matches for this group
            match_orms = match_repo.get_by_group(group_orm.id)

            # Convert to domain models
            matches = []
            for m_orm in match_orms:
                sets = [
                    Set(
                        set_number=s["set_number"],
                        player1_points=s["player1_points"],
                        player2_points=s["player2_points"],
                    )
                    for s in m_orm.sets
                ]
                match = Match(
                    id=m_orm.id,
                    player1_id=m_orm.competitor1_id,
                    player2_id=m_orm.competitor2_id,
                    group_id=m_orm.group_id,
                    round_type=m_orm.round_type,
                    round_name=m_orm.round_name,
                    match_number=m_orm.match_number,
                    status=m_orm.status,
                    sets=sets,
                    winner_id=m_orm.winner_id,
                )
                matches.append(match)

            # Calculate standings
            standings, _ = calculate_standings(
                matches, group_orm.id, player_repo,
                event_type=event_type, pair_repo=pair_repo, team_repo=team_repo,
            )

            # Delete old standings for this group
            standing_repo.delete_by_group(group_orm.id)

            # Save new standings
            for standing in standings:
                standing_repo.create(standing)

            total_standings += len(standings)

        request.session["flash_message"] = f"Se calcularon {total_standings} clasificaciones para {len(categories_processed)} categorías"
        request.session["flash_type"] = "success"

    except Exception as e:
        request.session["flash_message"] = f"Error al calcular clasificaciones: {str(e)}"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/admin/calculate-standings", status_code=303)


@app.post("/admin/calculate-standings/category")
async def admin_calculate_standings_category(
    request: Request,
    category: str = Form(...)
):
    """Calculate standings for a specific category."""
    try:
        session = get_db_session()
        group_repo = GroupRepository(session)
        match_repo = MatchRepository(session)
        standing_repo = StandingRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)

        event_type = detect_event_type(category)

        # Get all groups for this category
        group_orms = group_repo.get_by_category(category)

        if not group_orms:
            request.session["flash_message"] = f"No hay grupos para la categoría {category}"
            request.session["flash_type"] = "warning"
            return RedirectResponse(url="/admin/calculate-standings", status_code=303)

        total_standings = 0

        for group_orm in group_orms:
            # Get matches for this group
            match_orms = match_repo.get_by_group(group_orm.id)

            # Convert to domain models
            matches = []
            for m_orm in match_orms:
                sets = [
                    Set(
                        set_number=s["set_number"],
                        player1_points=s["player1_points"],
                        player2_points=s["player2_points"],
                    )
                    for s in m_orm.sets
                ]
                match = Match(
                    id=m_orm.id,
                    player1_id=m_orm.competitor1_id,
                    player2_id=m_orm.competitor2_id,
                    group_id=m_orm.group_id,
                    round_type=m_orm.round_type,
                    round_name=m_orm.round_name,
                    match_number=m_orm.match_number,
                    status=m_orm.status,
                    sets=sets,
                    winner_id=m_orm.winner_id,
                )
                matches.append(match)

            # Calculate standings
            standings, _ = calculate_standings(
                matches, group_orm.id, player_repo,
                event_type=event_type, pair_repo=pair_repo, team_repo=team_repo,
            )

            # Delete old standings for this group
            standing_repo.delete_by_group(group_orm.id)

            # Save new standings
            for standing in standings:
                standing_repo.create(standing)

            total_standings += len(standings)

        request.session["flash_message"] = f"Se calcularon {total_standings} clasificaciones para la categoría {category}"
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/category/{category}", status_code=303)

    except Exception as e:
        request.session["flash_message"] = f"Error al calcular clasificaciones: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/admin/calculate-standings", status_code=303)


# ─── Direct Bracket (KO Directo) ────────────────────────────────────────────

@app.get("/admin/direct-bracket", response_class=HTMLResponse)
async def admin_direct_bracket_form(request: Request):
    """Show form for generating a bracket directly from ranking (no group stage)."""
    import json as json_module
    selected_category = request.query_params.get("category", "")

    session = get_db_session()
    player_repo = PlayerRepository(session)
    pair_repo = PairRepository(session)
    group_repo = GroupRepository(session)
    bracket_repo = BracketRepository(session)
    tournament_repo = TournamentRepository(session)

    current_tournament = tournament_repo.get_current()
    if not current_tournament:
        return RedirectResponse(url="/tournaments", status_code=303)

    tournament_id = current_tournament.id

    # Build category list with competitor counts
    all_players = player_repo.get_all(tournament_id=tournament_id)
    all_pairs = pair_repo.get_all(tournament_id=tournament_id)

    # Group by category
    categories_map = {}
    for p in all_players:
        if p.categoria not in categories_map:
            categories_map[p.categoria] = {"players": [], "pairs": []}
        categories_map[p.categoria]["players"].append(p)
    for p in all_pairs:
        if p.categoria not in categories_map:
            categories_map[p.categoria] = {"players": [], "pairs": []}
        categories_map[p.categoria]["pairs"].append(p)

    available_categories = []
    competitors_json = {}

    for cat_name in sorted(categories_map.keys()):
        event_type = detect_event_type(cat_name)
        cat_data = categories_map[cat_name]

        if event_type == "doubles":
            competitors = cat_data["pairs"]
            count = len(competitors)
            # Build display data for JS
            comp_list = []
            for pair_orm in sorted(competitors, key=lambda p: (-p.ranking_pts, p.id)):
                p1 = player_repo.get_by_id(pair_orm.player1_id)
                p2 = player_repo.get_by_id(pair_orm.player2_id)
                name = f"{p1.nombre} {p1.apellido} / {p2.nombre} {p2.apellido}" if p1 and p2 else f"Pair {pair_orm.id}"
                country = f"{p1.pais_cd}/{p2.pais_cd}" if p1 and p2 else "?"
                comp_list.append({"name": name, "country": country, "ranking_pts": pair_orm.ranking_pts})
        else:
            competitors = cat_data["players"]
            count = len(competitors)
            comp_list = []
            for player_orm in sorted(competitors, key=lambda p: (-p.ranking_pts, p.id)):
                comp_list.append({
                    "name": f"{player_orm.nombre} {player_orm.apellido}",
                    "country": player_orm.pais_cd,
                    "ranking_pts": player_orm.ranking_pts,
                })

        if count < 2:
            continue

        # Check if groups/bracket already exist
        groups = group_repo.get_by_category(cat_name, tournament_id=tournament_id)
        bracket_slots = bracket_repo.get_by_category(cat_name, tournament_id=tournament_id)

        available_categories.append({
            "name": cat_name,
            "count": count,
            "event_type": event_type.value if hasattr(event_type, 'value') else event_type,
            "has_groups": len(groups) > 0,
            "has_bracket": len(bracket_slots) > 0,
        })
        competitors_json[cat_name] = comp_list

    return render_template(
        "admin_direct_bracket.html",
        {
            "request": request,
            "available_categories": available_categories,
            "competitors_json": json_module.dumps(competitors_json).replace("</", "<\\/"),
            "selected_category": selected_category,
        }
    )


@app.get("/admin/direct-bracket/manual/{category}", response_class=HTMLResponse)
async def admin_direct_bracket_manual(request: Request, category: str):
    """Show manual bracket positioning for direct bracket (no group stage)."""
    import math as _math
    from ettem.models import is_doubles_category
    from ettem.bracket import get_bye_positions_for_bracket, next_power_of_2

    session = get_db_session()
    try:
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        tournament_repo = TournamentRepository(session)

        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        best_of = int(request.query_params.get("best_of", "5"))
        event_type = detect_event_type(category)
        _is_doubles = is_doubles_category(category)

        # Build competitors list
        competitors = []
        if _is_doubles:
            pair_orms = pair_repo.get_by_category(category, tournament_id=tournament_id)
            for po in sorted(pair_orms, key=lambda p: (-p.ranking_pts, p.id)):
                p1 = player_repo.get_by_id(po.player1_id)
                p2 = player_repo.get_by_id(po.player2_id)
                name = f"{p1.nombre} {p1.apellido} / {p2.nombre} {p2.apellido}" if p1 and p2 else f"Pareja {po.id}"
                country = f"{p1.pais_cd}/{p2.pais_cd}" if p1 and p2 else "?"
                competitors.append({
                    "player_id": po.id,
                    "nombre": name,
                    "apellido": "",
                    "pais_cd": country,
                    "ranking_pts": po.ranking_pts,
                    "seed": po.seed or len(competitors) + 1,
                })
        else:
            player_orms = player_repo.get_by_category(category, tournament_id=tournament_id)
            for po in sorted(player_orms, key=lambda p: (-p.ranking_pts, p.id)):
                competitors.append({
                    "player_id": po.id,
                    "nombre": po.nombre,
                    "apellido": po.apellido,
                    "pais_cd": po.pais_cd,
                    "ranking_pts": po.ranking_pts,
                    "seed": po.seed or len(competitors) + 1,
                })

        if len(competitors) < 2:
            request.session["flash_message"] = f"Se necesitan al menos 2 competidores."
            request.session["flash_type"] = "error"
            return RedirectResponse(url=f"/admin/direct-bracket?category={category}", status_code=303)

        # Calculate bracket size and BYEs
        bracket_size = next_power_of_2(len(competitors))
        bye_positions = set(get_bye_positions_for_bracket(len(competitors), bracket_size))

        slots = []
        for i in range(1, bracket_size + 1):
            slots.append({
                "slot_number": i,
                "player_id": None,
                "is_bye": i in bye_positions,
            })

        unit = "parejas" if _is_doubles else "jugadores"

        return render_template(
            "admin_direct_bracket_manual.html",
            {
                "request": request,
                "category": category,
                "best_of": best_of,
                "competitors": competitors,
                "bracket_size": bracket_size,
                "slots": slots,
                "is_doubles": _is_doubles,
                "unit": unit,
            }
        )
    finally:
        session.close()


@app.post("/admin/direct-bracket/manual/{category}/save")
async def admin_direct_bracket_manual_save(request: Request, category: str):
    """Save manually positioned direct bracket."""
    from ettem.models import BracketSlot, RoundType, is_doubles_category
    from ettem.bracket import get_round_type_for_size

    form_data = await request.form()
    best_of = int(form_data.get("best_of", 5))

    session = get_db_session()
    try:
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        bracket_repo = BracketRepository(session)
        match_repo = MatchRepository(session)
        tournament_repo = TournamentRepository(session)

        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        event_type = detect_event_type(category)
        _is_doubles = is_doubles_category(category)

        # Parse slot assignments from form
        slot_data = {}
        for key, value in form_data.items():
            if key.startswith("slot_") and value:
                slot_num = int(key.replace("slot_", ""))
                slot_data[slot_num] = value

        if not slot_data:
            request.session["flash_message"] = "No se asignaron competidores al bracket."
            request.session["flash_type"] = "error"
            return RedirectResponse(url=f"/admin/direct-bracket/manual/{category}?best_of={best_of}", status_code=303)

        # Determine bracket size from max slot number
        bracket_size = max(slot_data.keys())
        # Round up to power of 2
        bracket_size = 2 ** math.ceil(math.log2(bracket_size)) if bracket_size > 1 else 2
        first_round = get_round_type_for_size(bracket_size)

        # Delete existing bracket
        existing_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
        if existing_slots:
            for slot in existing_slots:
                session.delete(slot)
            bracket_matches = match_repo.get_bracket_matches_by_category(category, tournament_id=tournament_id)
            for m in bracket_matches:
                session.delete(m)
            session.commit()

        # Create first round bracket slots
        for slot_num in range(1, bracket_size + 1):
            value = slot_data.get(slot_num, "")
            is_bye = (value == "BYE")
            player_id = int(value) if value and value != "BYE" else None

            bracket_repo.create_slot(
                BracketSlot(
                    slot_number=slot_num,
                    round_type=first_round,
                    player_id=player_id,
                    is_bye=is_bye,
                ),
                category,
                tournament_id=tournament_id,
            )

        # Create subsequent round slots (empty placeholders for winners to advance into)
        round_progression = {
            RoundType.ROUND_OF_128: RoundType.ROUND_OF_64,
            RoundType.ROUND_OF_64: RoundType.ROUND_OF_32,
            RoundType.ROUND_OF_32: RoundType.ROUND_OF_16,
            RoundType.ROUND_OF_16: RoundType.QUARTERFINAL,
            RoundType.QUARTERFINAL: RoundType.SEMIFINAL,
            RoundType.SEMIFINAL: RoundType.FINAL,
        }
        current_round = first_round
        current_size = bracket_size
        while current_round in round_progression:
            next_round = round_progression[current_round]
            next_size = current_size // 2
            if next_size < 1:
                break
            for slot_num in range(1, next_size + 1):
                bracket_repo.create_slot(
                    BracketSlot(
                        slot_number=slot_num,
                        round_type=next_round,
                        player_id=None,
                        is_bye=False,
                    ),
                    category,
                    tournament_id=tournament_id,
                )
            current_round = next_round
            current_size = next_size

        # For doubles/teams, set pair_id/team_id on bracket slots
        if event_type in ("doubles", "teams"):
            saved_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
            for slot_orm in saved_slots:
                if slot_orm.player_id and not slot_orm.is_bye:
                    if event_type == "doubles":
                        slot_orm.pair_id = slot_orm.player_id
                    elif event_type == "teams":
                        slot_orm.team_id = slot_orm.player_id
            session.commit()

        # Create matches
        matches_created = create_bracket_matches(
            category, bracket_repo, match_repo,
            tournament_id=tournament_id, best_of=best_of, event_type=event_type
        )

        # Set event_type on matches
        bracket_matches = match_repo.get_bracket_matches_by_category(category, tournament_id=tournament_id)
        for m in bracket_matches:
            m.event_type = event_type
            if event_type == "doubles":
                if m.player1_id:
                    m.pair1_id = m.player1_id
                if m.player2_id:
                    m.pair2_id = m.player2_id
            elif event_type == "teams":
                if m.player1_id:
                    m.team1_id = m.player1_id
                if m.player2_id:
                    m.team2_id = m.player2_id
        session.commit()

        # Process BYE advancements
        process_bye_advancements(category, bracket_repo, session, tournament_id=tournament_id, match_repo=match_repo)

        # Sync matches
        sync_bracket_matches_with_slots(category, bracket_repo, match_repo, session, tournament_id=tournament_id, event_type=event_type)

        request.session["flash_message"] = f"Bracket manual generado: {matches_created} partidos creados para {category}."
        request.session["flash_type"] = "success"
        return RedirectResponse(url=f"/category/{category}", status_code=303)

    except Exception as e:
        import traceback
        traceback.print_exc()
        request.session["flash_message"] = f"Error: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url=f"/admin/direct-bracket/manual/{category}?best_of={best_of}", status_code=303)
    finally:
        session.close()


@app.post("/admin/direct-bracket/preview")
async def admin_direct_bracket_preview(
    request: Request,
    category: str = Form(...),
    best_of: int = Form(5),
    random_seed: Optional[int] = Form(None),
    draw_mode: str = Form("seeded"),
    manual_order: Optional[str] = Form(""),
):
    """Preview bracket draw before generating (sorteo)."""
    from ettem.bracket import build_bracket_direct
    from ettem.models import is_doubles_category
    from ettem.webapp.helpers import CompetitorDisplay

    # Manual mode → redirect to manual draw page
    if draw_mode == "manual":
        return RedirectResponse(
            url=f"/admin/direct-bracket/manual/{category}?best_of={best_of}",
            status_code=303
        )

    try:
        session = get_db_session()
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        tournament_repo = TournamentRepository(session)

        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        event_type = detect_event_type(category)
        _is_doubles = is_doubles_category(category)

        # Fetch competitors sorted by ranking_pts
        if event_type == "doubles":
            pair_orms = pair_repo.get_by_category(category, tournament_id=tournament_id)
            if not pair_orms:
                request.session["flash_message"] = f"No hay parejas para la categoría {category}."
                request.session["flash_type"] = "error"
                return RedirectResponse(url="/admin/direct-bracket", status_code=303)

            competitors = []
            for po in pair_orms:
                competitors.append(Pair(
                    id=po.id,
                    player1_id=po.player1_id,
                    player2_id=po.player2_id,
                    ranking_pts=po.ranking_pts,
                    categoria=po.categoria,
                    seed=po.seed,
                ))
        else:
            player_orms = player_repo.get_by_category(category, tournament_id=tournament_id)
            if not player_orms:
                request.session["flash_message"] = f"No hay jugadores para la categoría {category}."
                request.session["flash_type"] = "error"
                return RedirectResponse(url="/admin/direct-bracket", status_code=303)

            competitors = []
            for po in player_orms:
                competitors.append(Player(
                    id=po.id,
                    nombre=po.nombre,
                    apellido=po.apellido,
                    genero=po.genero,
                    pais_cd=po.pais_cd,
                    ranking_pts=po.ranking_pts,
                    categoria=po.categoria,
                    seed=po.seed,
                ))

        if len(competitors) < 2:
            request.session["flash_message"] = f"Se necesitan al menos 2 competidores (hay {len(competitors)})."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/direct-bracket", status_code=303)

        # Reorder competitors for manual mode
        if draw_mode == "manual" and manual_order:
            import json as json_mod
            try:
                order = json_mod.loads(manual_order)
                # Sort by ranking first (same as server-side data)
                sorted_comps = sorted(competitors, key=lambda c: (-c.ranking_pts, c.id))
                competitors = [sorted_comps[i] for i in order if i < len(sorted_comps)]
            except (json_mod.JSONDecodeError, IndexError):
                pass  # Fall back to original order

        # Build bracket IN MEMORY (not saved to DB)
        bracket = build_bracket_direct(
            competitors=competitors,
            category=category,
            random_seed=random_seed if random_seed else 42,
            player_repo=player_repo,
            event_type=event_type,
            pair_repo=pair_repo,
            draw_mode=draw_mode,
        )

        # Extract first round matchups
        first_round = None
        round_priority = ['R128', 'R64', 'R32', 'R16', 'QF', 'SF', 'F']
        for rt in round_priority:
            if rt in bracket.slots:
                first_round = rt
                break

        matchups = []
        if first_round:
            slots = bracket.slots[first_round]
            for i in range(0, len(slots), 2):
                slot1 = slots[i]
                slot2 = slots[i + 1] if i + 1 < len(slots) else None

                # Resolve competitor display
                def resolve_slot(slot):
                    if not slot:
                        return CompetitorDisplay.tbd()
                    if slot.is_bye:
                        return CompetitorDisplay.bye()
                    if slot.player_id:
                        if _is_doubles:
                            pair_orm = pair_repo.get_by_id(slot.player_id)
                            if pair_orm:
                                p1 = player_repo.get_by_id(pair_orm.player1_id)
                                p2 = player_repo.get_by_id(pair_orm.player2_id)
                                return CompetitorDisplay.from_pair(pair_orm, p1, p2)
                        else:
                            player = player_repo.get_by_id(slot.player_id)
                            if player:
                                return CompetitorDisplay.from_player(player)
                    return CompetitorDisplay.tbd()

                c1 = resolve_slot(slot1)
                c2 = resolve_slot(slot2)
                is_bye_match = (slot1 and slot1.is_bye) or (slot2 and slot2.is_bye)

                matchups.append({
                    "seed1": slot1.slot_number if slot1 else "-",
                    "seed2": slot2.slot_number if slot2 else "-",
                    "competitor1": c1,
                    "competitor2": c2,
                    "is_bye": is_bye_match,
                    "same_country": (slot1 and slot1.same_country_warning) or (slot2 and slot2 and slot2.same_country_warning),
                })

        bracket_size = len(bracket.slots.get(first_round, []))
        num_byes = sum(1 for s in bracket.slots.get(first_round, []) if s.is_bye)

        round_names = {
            "R128": "Ronda de 128",
            "R64": "Ronda de 64",
            "R32": "Ronda de 32",
            "R16": "Ronda de 16",
            "QF": "Cuartos de Final",
            "SF": "Semifinal",
            "F": "Final",
        }

        context = {
            "request": request,
            "category": category,
            "best_of": best_of,
            "random_seed": random_seed if random_seed else 42,
            "draw_mode": draw_mode,
            "draw_mode_label": {"seeded": "Seeding por ranking", "random": "Sorteo aleatorio", "manual": "Orden manual"}.get(draw_mode, draw_mode),
            "manual_order": manual_order or "",
            "num_competitors": len(competitors),
            "bracket_size": bracket_size,
            "num_byes": num_byes,
            "first_round": round_names.get(first_round, first_round),
            "matchups": matchups,
            "is_doubles": _is_doubles,
            "unit": "parejas" if _is_doubles else "jugadores",
        }

        return render_template("admin_direct_bracket_preview.html", context)

    except Exception as e:
        import traceback
        traceback.print_exc()
        request.session["flash_message"] = f"Error en preview: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/admin/direct-bracket", status_code=303)


@app.post("/admin/direct-bracket/execute")
async def admin_direct_bracket_execute(
    request: Request,
    category: str = Form(...),
    best_of: int = Form(5),
    random_seed: Optional[int] = Form(None),
    draw_mode: str = Form("seeded"),
    manual_order: Optional[str] = Form(""),
):
    """Generate bracket directly from ranking_pts (no group stage)."""
    from ettem.bracket import build_bracket_direct

    try:
        session = get_db_session()
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        bracket_repo = BracketRepository(session)
        match_repo = MatchRepository(session)
        tournament_repo = TournamentRepository(session)

        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        event_type = detect_event_type(category)

        # Fetch competitors sorted by ranking_pts
        if event_type == "doubles":
            pair_orms = pair_repo.get_by_category(category, tournament_id=tournament_id)
            if not pair_orms:
                request.session["flash_message"] = f"No hay parejas para la categoría {category}."
                request.session["flash_type"] = "error"
                return RedirectResponse(url="/admin/direct-bracket", status_code=303)

            competitors = []
            for po in pair_orms:
                competitors.append(Pair(
                    id=po.id,
                    player1_id=po.player1_id,
                    player2_id=po.player2_id,
                    ranking_pts=po.ranking_pts,
                    categoria=po.categoria,
                    seed=po.seed,
                ))
        else:
            player_orms = player_repo.get_by_category(category, tournament_id=tournament_id)
            if not player_orms:
                request.session["flash_message"] = f"No hay jugadores para la categoría {category}."
                request.session["flash_type"] = "error"
                return RedirectResponse(url="/admin/direct-bracket", status_code=303)

            competitors = []
            for po in player_orms:
                competitors.append(Player(
                    id=po.id,
                    nombre=po.nombre,
                    apellido=po.apellido,
                    genero=po.genero,
                    pais_cd=po.pais_cd,
                    ranking_pts=po.ranking_pts,
                    categoria=po.categoria,
                    seed=po.seed,
                ))

        if len(competitors) < 2:
            request.session["flash_message"] = f"Se necesitan al menos 2 competidores (hay {len(competitors)})."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/direct-bracket", status_code=303)

        # Reorder competitors for manual mode
        if draw_mode == "manual" and manual_order:
            import json as json_mod
            try:
                order = json_mod.loads(manual_order)
                sorted_comps = sorted(competitors, key=lambda c: (-c.ranking_pts, c.id))
                competitors = [sorted_comps[i] for i in order if i < len(sorted_comps)]
            except (json_mod.JSONDecodeError, IndexError):
                pass

        # Delete existing bracket for this category if it exists
        existing_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
        if existing_slots:
            for slot in existing_slots:
                session.delete(slot)
            # Delete existing bracket matches
            bracket_matches = match_repo.get_bracket_matches_by_category(category, tournament_id=tournament_id)
            for m in bracket_matches:
                session.delete(m)
            session.commit()

        # Build bracket
        bracket = build_bracket_direct(
            competitors=competitors,
            category=category,
            random_seed=random_seed if random_seed else 42,
            player_repo=player_repo,
            event_type=event_type,
            pair_repo=pair_repo,
            draw_mode=draw_mode,
        )

        # Save bracket slots
        total_slots = 0
        for round_type, slots in bracket.slots.items():
            for slot in slots:
                bracket_repo.create_slot(slot, category, tournament_id=tournament_id)
                total_slots += 1

        # For doubles/teams, set pair_id/team_id on the bracket slots
        if event_type in ("doubles", "teams"):
            saved_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
            for slot_orm in saved_slots:
                if slot_orm.player_id and not slot_orm.is_bye:
                    if event_type == "doubles":
                        slot_orm.pair_id = slot_orm.player_id
                    elif event_type == "teams":
                        slot_orm.team_id = slot_orm.player_id
            session.commit()

        # Create matches from bracket slots
        matches_created = create_bracket_matches(
            category, bracket_repo, match_repo,
            tournament_id=tournament_id, best_of=best_of, event_type=event_type
        )

        # Set event_type on created matches
        bracket_matches = match_repo.get_bracket_matches_by_category(category, tournament_id=tournament_id)
        for m in bracket_matches:
            m.event_type = event_type
            if event_type == "doubles":
                if m.player1_id:
                    m.pair1_id = m.player1_id
                if m.player2_id:
                    m.pair2_id = m.player2_id
            elif event_type == "teams":
                if m.player1_id:
                    m.team1_id = m.player1_id
                if m.player2_id:
                    m.team2_id = m.player2_id
        session.commit()

        # Process BYE advancements
        process_bye_advancements(category, bracket_repo, session, tournament_id=tournament_id, match_repo=match_repo)

        # Sync matches with updated slots
        sync_bracket_matches_with_slots(category, bracket_repo, match_repo, session, tournament_id=tournament_id, event_type=event_type)

        # For doubles/teams, refresh IDs after BYE advancement (BYEs may have
        # populated player1_id/player2_id in downstream rounds without setting
        # pair1_id/pair2_id or team1_id/team2_id).
        if event_type in ("doubles", "teams"):
            bracket_matches = match_repo.get_bracket_matches_by_category(category, tournament_id=tournament_id)
            for m in bracket_matches:
                if event_type == "doubles":
                    if m.player1_id and not m.pair1_id:
                        m.pair1_id = m.player1_id
                    if m.player2_id and not m.pair2_id:
                        m.pair2_id = m.player2_id
                elif event_type == "teams":
                    if m.player1_id and not m.team1_id:
                        m.team1_id = m.player1_id
                    if m.player2_id and not m.team2_id:
                        m.team2_id = m.player2_id
            saved_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
            for slot_orm in saved_slots:
                if slot_orm.player_id and not slot_orm.is_bye:
                    if event_type == "doubles" and not slot_orm.pair_id:
                        slot_orm.pair_id = slot_orm.player_id
                    elif event_type == "teams" and not slot_orm.team_id:
                        slot_orm.team_id = slot_orm.player_id
            session.commit()

        request.session["flash_message"] = f"KO Directo generado: {len(competitors)} competidores, {total_slots} slots, {matches_created} partidos"
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/bracket/{category}", status_code=303)

    except Exception as e:
        import traceback
        traceback.print_exc()
        request.session["flash_message"] = f"Error al generar KO Directo: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/admin/direct-bracket", status_code=303)


@app.get("/admin/generate-bracket", response_class=HTMLResponse)
async def admin_generate_bracket_form(request: Request):
    """Show generate bracket form."""
    from ettem.models import RoundType
    session = get_db_session()
    group_repo = GroupRepository(session)
    standing_repo = StandingRepository(session)
    player_repo = PlayerRepository(session)
    bracket_repo = BracketRepository(session)
    tournament_repo = TournamentRepository(session)

    # Get current tournament - redirect if none exists
    current_tournament = tournament_repo.get_current()
    if not current_tournament:
        return RedirectResponse(url="/tournaments", status_code=303)

    tournament_id = current_tournament.id

    # Get all groups grouped by category with standings count for current tournament
    all_groups = group_repo.get_all(tournament_id=tournament_id)
    current_group_ids = set(g.id for g in all_groups)
    all_standings = standing_repo.get_all()

    # Count standings per category (filter by current tournament via group_id)
    # Build group_id -> category map for quick lookup
    group_category_map = {g.id: g.category for g in all_groups}
    pair_repo = PairRepository(session)
    team_repo = TeamRepository(session)

    standings_by_category = {}
    for standing in all_standings:
        # Only include standings from current tournament's groups
        if standing.group_id not in current_group_ids:
            continue
        # Determine category from the group
        cat = group_category_map.get(standing.group_id)
        if cat:
            if cat not in standings_by_category:
                standings_by_category[cat] = 0
            standings_by_category[cat] += 1

    # Count groups per category
    groups_by_category = {}
    for group in all_groups:
        if group.category not in groups_by_category:
            groups_by_category[group.category] = 0
        groups_by_category[group.category] += 1

    # Get existing brackets info for current tournament
    match_repo = MatchRepository(session)
    all_players = player_repo.get_all(tournament_id=tournament_id)
    categories = list(set(p.categoria for p in all_players))
    existing_brackets = []
    brackets_info = {}  # category -> {has_bracket, is_completed, size, players}

    for category in categories:
        bracket_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
        if bracket_slots:
            # Count non-BYE players
            players_count = sum(1 for slot in bracket_slots if not slot.is_bye and slot.player_id)
            # Get bracket size from R1 (first round)
            r1_slots = [s for s in bracket_slots if s.round_type == "R1"]
            size = len(r1_slots) if r1_slots else 0

            # Check if bracket is completed (final match has winner)
            final_matches = [
                m for m in match_repo.get_all()
                if m.round_type == RoundType.FINAL.value
                and m.group_id is None
                and m.tournament_id == tournament_id
                and m.category == category
            ]
            is_completed = bool(final_matches and final_matches[0].winner_id)

            brackets_info[category] = {
                "has_bracket": True,
                "is_completed": is_completed,
                "size": size,
                "players": players_count
            }

            existing_brackets.append({
                "category": category,
                "size": size,
                "players": players_count,
                "is_completed": is_completed
            })

    # Available categories with bracket status
    available_categories = [
        {
            "name": cat,
            "groups": groups_by_category.get(cat, 0),
            "standings": count,
            "has_bracket": brackets_info.get(cat, {}).get("has_bracket", False),
            "is_completed": brackets_info.get(cat, {}).get("is_completed", False)
        }
        for cat, count in sorted(standings_by_category.items())
    ]

    return render_template(
        "admin_generate_bracket.html",
        {
            "request": request,
            "available_categories": available_categories,
            "existing_brackets": existing_brackets
        }
    )


@app.post("/admin/generate-bracket/execute")
async def admin_generate_bracket_execute(
    request: Request,
    category: str = Form(...),
    advance_per_group: int = Form(...),
    random_seed: Optional[int] = Form(None),
    best_of: int = Form(5)
):
    """Execute bracket generation."""
    from ettem.bracket import build_bracket
    from ettem.models import GroupStanding

    try:
        # Initialize repositories
        session = get_db_session()
        standing_repo = StandingRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        bracket_repo = BracketRepository(session)
        tournament_repo = TournamentRepository(session)
        group_repo = GroupRepository(session)
        match_repo = MatchRepository(session)

        event_type = detect_event_type(category)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # VALIDATION: Check that all group matches are completed
        groups = group_repo.get_by_category(category, tournament_id=tournament_id)
        pending_matches = []
        for group in groups:
            matches = match_repo.get_by_group(group.id)
            for match in matches:
                if match.status == MatchStatus.PENDING.value or match.status == MatchStatus.PENDING:
                    pending_matches.append((group.name, match.id))

        if pending_matches:
            groups_with_pending = sorted(set(str(g) for g, _ in pending_matches))
            request.session["flash_message"] = f"No se puede generar bracket: hay {len(pending_matches)} partidos pendientes en los grupos: {', '.join(groups_with_pending)}. Completa todos los partidos de grupo primero."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/generate-bracket", status_code=303)

        # Get all standings for this category, filtered by CURRENT TOURNAMENT
        # First get the group IDs for the current tournament
        current_group_ids = set(g.id for g in groups)

        all_standings = standing_repo.get_all()

        # Helper to look up competitor by event_type
        def _get_competitor_orm(competitor_id):
            if event_type == "teams":
                return team_repo.get_by_id(competitor_id)
            elif event_type == "doubles":
                return pair_repo.get_by_id(competitor_id)
            return player_repo.get_by_id(competitor_id)

        # Filter by category, tournament (via group_id), and get top N per group
        category_standings = []
        groups_processed = set()

        for standing_orm in all_standings:
            # IMPORTANT: Only include standings from current tournament's groups
            if standing_orm.group_id not in current_group_ids:
                continue

            competitor_orm = _get_competitor_orm(standing_orm.player_id)
            if not competitor_orm or competitor_orm.categoria != category:
                continue

            if standing_orm.group_id not in groups_processed:
                groups_processed.add(standing_orm.group_id)

            # Get qualifiers (top N positions)
            if standing_orm.position and standing_orm.position <= advance_per_group:
                category_standings.append(standing_orm)

        if not category_standings:
            request.session["flash_message"] = f"No hay clasificaciones para la categoría {category}. Calcula standings primero."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/generate-bracket", status_code=303)

        # Convert to domain models with competitors
        qualifiers = []
        for standing_orm in category_standings:
            competitor_orm = _get_competitor_orm(standing_orm.player_id)
            if competitor_orm:
                if event_type == "teams":
                    competitor = Team(
                        id=competitor_orm.id,
                        name=competitor_orm.name,
                        categoria=competitor_orm.categoria,
                        pais_cd=competitor_orm.pais_cd,
                        ranking_pts=competitor_orm.ranking_pts,
                        seed=competitor_orm.seed,
                    )
                elif event_type == "doubles":
                    competitor = Pair(
                        id=competitor_orm.id,
                        player1_id=competitor_orm.player1_id,
                        player2_id=competitor_orm.player2_id,
                        categoria=competitor_orm.categoria,
                        ranking_pts=competitor_orm.ranking_pts,
                        seed=competitor_orm.seed,
                    )
                else:
                    competitor = Player(
                        id=competitor_orm.id,
                        nombre=competitor_orm.nombre,
                        apellido=competitor_orm.apellido,
                        genero=competitor_orm.genero,
                        pais_cd=competitor_orm.pais_cd,
                        ranking_pts=competitor_orm.ranking_pts,
                        categoria=competitor_orm.categoria,
                        seed=competitor_orm.seed,
                    )
                standing = GroupStanding(
                    player_id=standing_orm.player_id,
                    group_id=standing_orm.group_id,
                    points_total=standing_orm.points_total,
                    wins=standing_orm.wins,
                    losses=standing_orm.losses,
                    sets_w=standing_orm.sets_w,
                    sets_l=standing_orm.sets_l,
                    points_w=standing_orm.points_w,
                    points_l=standing_orm.points_l,
                    position=standing_orm.position,
                )
                qualifiers.append((competitor, standing))

        # Build bracket (creates in-memory structure with player placements)
        bracket = build_bracket(
            qualifiers=qualifiers,
            category=category,
            random_seed=random_seed if random_seed else 42,
            player_repo=player_repo,
            event_type=event_type,
            pair_repo=pair_repo,
        )

        match_repo = MatchRepository(session)

        # Check if empty bracket structure already exists (created when groups were made)
        existing_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)

        if existing_slots:
            # UPDATE existing slots with player IDs (preserves schedule)
            print(f"[DEBUG generate_bracket] Found {len(existing_slots)} existing slots, updating with players")

            # Group existing slots by round_type for easier lookup
            existing_by_round = {}
            for slot in existing_slots:
                if slot.round_type not in existing_by_round:
                    existing_by_round[slot.round_type] = {}
                existing_by_round[slot.round_type][slot.slot_number] = slot

            total_updated = 0
            for round_type, slots in bracket.slots.items():
                round_key = round_type.value if hasattr(round_type, 'value') else round_type
                if round_key in existing_by_round:
                    for slot in slots:
                        if slot.slot_number in existing_by_round[round_key]:
                            db_slot = existing_by_round[round_key][slot.slot_number]
                            db_slot.player_id = slot.player_id
                            if event_type == "teams":
                                db_slot.team_id = slot.player_id
                            elif event_type == "doubles":
                                db_slot.pair_id = slot.player_id
                            db_slot.is_bye = slot.is_bye
                            db_slot.same_country_warning = slot.same_country_warning
                            total_updated += 1

            session.commit()

            # Update best_of and event_type on existing bracket matches
            bracket_matches = match_repo.get_bracket_matches_by_category(category, tournament_id=tournament_id)
            for match_orm in bracket_matches:
                if match_orm.best_of != best_of:
                    match_orm.best_of = best_of
                if match_orm.event_type != event_type:
                    match_orm.event_type = event_type
            session.commit()

            # Sync matches with updated slots (updates player IDs in existing matches)
            sync_bracket_matches_with_slots(category, bracket_repo, match_repo, session, tournament_id=tournament_id, event_type=event_type)

            # Process BYE advancements (and delete BYE matches)
            process_bye_advancements(category, bracket_repo, session, tournament_id=tournament_id, match_repo=match_repo)

            # Sync again after BYE processing
            sync_bracket_matches_with_slots(category, bracket_repo, match_repo, session, tournament_id=tournament_id, event_type=event_type)

            request.session["flash_message"] = f"Bracket actualizado: {total_updated} slots con jugadores asignados"
        else:
            # No existing structure - create from scratch (legacy behavior)
            print(f"[DEBUG generate_bracket] No existing slots, creating new bracket")

            total_slots = 0
            for round_type, slots in bracket.slots.items():
                for slot in slots:
                    slot_orm = bracket_repo.create_slot(slot, category, tournament_id=tournament_id)
                    if event_type == "teams" and slot.player_id:
                        slot_orm.team_id = slot.player_id
                    elif event_type == "doubles" and slot.player_id:
                        slot_orm.pair_id = slot.player_id
                    total_slots += 1
            if event_type in ("teams", "doubles"):
                session.commit()

            # Create matches from bracket slots
            matches_created = create_bracket_matches(category, bracket_repo, match_repo, tournament_id=tournament_id, best_of=best_of, event_type=event_type)

            # Process BYE advancements (and delete BYE matches)
            process_bye_advancements(category, bracket_repo, session, tournament_id=tournament_id, match_repo=match_repo)

            # Sync matches with updated slots
            sync_bracket_matches_with_slots(category, bracket_repo, match_repo, session, tournament_id=tournament_id, event_type=event_type)

            request.session["flash_message"] = f"Bracket generado: {total_slots} slots, {matches_created} partidos creados"
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/bracket/{category}", status_code=303)

    except Exception as e:
        request.session["flash_message"] = f"Error al generar bracket: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/admin/generate-bracket", status_code=303)


@app.post("/admin/regenerate-matches/{category}")
async def regenerate_bracket_matches(request: Request, category: str):
    """Regenerate matches for an existing bracket (useful after updates)."""
    session = get_db_session()
    try:
        bracket_repo = BracketRepository(session)
        match_repo = MatchRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Verify bracket exists
        bracket_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
        if not bracket_slots:
            request.session["flash_message"] = f"No hay bracket para la categoría {category}"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/", status_code=303)

        # Get best_of from existing bracket matches before deleting
        existing_bracket_matches = match_repo.get_bracket_matches_by_category(category, tournament_id=tournament_id)
        best_of = 5  # Default
        if existing_bracket_matches:
            best_of = existing_bracket_matches[0].best_of or 5

        # Delete existing bracket matches for this category
        all_matches = match_repo.get_all()
        for match_orm in all_matches:
            if match_orm.group_id is None:  # Bracket match
                # Check if belongs to this category by checking player
                from ettem.storage import PlayerRepository
                player_repo = PlayerRepository(session)
                player = player_repo.get_by_id(match_orm.player1_id)
                if player and player.categoria == category:
                    session.delete(match_orm)
        session.commit()

        # Create matches from bracket slots with preserved best_of format
        matches_created = create_bracket_matches(category, bracket_repo, match_repo, tournament_id=tournament_id, best_of=best_of)

        # Process BYE advancements (and delete BYE matches)
        process_bye_advancements(category, bracket_repo, session, tournament_id=tournament_id, match_repo=match_repo)

        # Sync matches with updated slots
        sync_bracket_matches_with_slots(category, bracket_repo, match_repo, session)

        request.session["flash_message"] = f"Partidos regenerados: {matches_created} partidos creados"
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/bracket/{category}", status_code=303)

    except Exception as e:
        request.session["flash_message"] = f"Error al regenerar partidos: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/", status_code=303)


@app.post("/admin/bracket/{category}/process-byes")
async def admin_process_byes(request: Request, category: str):
    """
    Manually process BYE advancements for a category.

    This allows the user to verify BYE placements before advancing players.
    """
    from ettem.models import RoundType

    session = get_db_session()
    try:
        bracket_repo = BracketRepository(session)
        match_repo = MatchRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Verify bracket exists
        bracket_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
        if not bracket_slots:
            request.session["flash_message"] = f"No hay bracket para la categoría {category}"
            request.session["flash_type"] = "error"
            return RedirectResponse(url=f"/category/{category}", status_code=303)

        # Count pending BYEs before processing
        pending_byes = count_pending_byes(category, bracket_repo, tournament_id)

        # Also count BYE matches that need to be deleted (only first round)
        bye_matches_count = count_bye_matches(category, match_repo, bracket_repo, tournament_id)

        if pending_byes == 0 and bye_matches_count == 0:
            request.session["flash_message"] = "No hay BYEs pendientes de procesar"
            request.session["flash_type"] = "info"
            return RedirectResponse(url=f"/bracket/{category}", status_code=303)

        # Process BYE advancements (and delete BYE matches)
        process_bye_advancements(category, bracket_repo, session, tournament_id=tournament_id, match_repo=match_repo)

        # Sync matches with updated slots
        sync_bracket_matches_with_slots(category, bracket_repo, match_repo, session)

        message_parts = []
        if pending_byes > 0:
            message_parts.append(f"{pending_byes} jugadores avanzaron")
        if bye_matches_count > 0:
            message_parts.append(f"{bye_matches_count} partidos BYE eliminados")

        request.session["flash_message"] = f"BYEs procesados: {', '.join(message_parts)}"
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/bracket/{category}", status_code=303)

    except Exception as e:
        request.session["flash_message"] = f"Error al procesar BYEs: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url=f"/bracket/{category}", status_code=303)
    finally:
        session.close()


def count_bye_matches(category: str, match_repo, bracket_repo=None, tournament_id: int = None) -> int:
    """
    Count BYE matches (matches where one player is a BYE slot) in the FIRST ROUND only.

    BYEs only exist in the first round of the bracket. Empty slots in later rounds
    are waiting for winners from previous rounds, not BYEs.

    These matches should be deleted since BYE matches don't need
    to be played - the player advances automatically.
    """
    from ettem.models import RoundType

    # Determine the first round of the bracket for this category
    first_round = None
    if bracket_repo:
        slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
        # Find the first (largest) round
        for rt in [RoundType.ROUND_OF_128, RoundType.ROUND_OF_64, RoundType.ROUND_OF_32,
                   RoundType.ROUND_OF_16, RoundType.QUARTERFINAL, RoundType.SEMIFINAL]:
            if any(s.round_type == rt.value for s in slots):
                first_round = rt.value
                break

    count = 0
    all_matches = match_repo.get_all()
    player_repo = PlayerRepository(match_repo.session)

    for match_orm in all_matches:
        # Only count bracket matches (group_id is None)
        if match_orm.group_id is not None:
            continue

        # Only count matches from the first round (BYEs only exist there)
        if first_round and match_orm.round_type != first_round:
            continue

        # Check if this is a BYE match (one player is None)
        if match_orm.player1_id is None or match_orm.player2_id is None:
            # Verify this match belongs to our category
            player_id = match_orm.player1_id or match_orm.player2_id
            if player_id:
                player = player_repo.get_by_id(player_id)
                if player and player.categoria == category:
                    count += 1
    return count


def count_pending_byes(category: str, bracket_repo, tournament_id: int = None) -> int:
    """
    Count how many BYE advancements are pending (not yet processed).

    A BYE is pending when:
    - One slot in a pair is a BYE
    - The other slot has a player
    - The player hasn't been advanced to the next round yet

    Note: BYEs only exist in the FIRST round of the bracket.
    """
    from ettem.models import RoundType

    round_progression = {
        RoundType.ROUND_OF_128: RoundType.ROUND_OF_64,
        RoundType.ROUND_OF_64: RoundType.ROUND_OF_32,
        RoundType.ROUND_OF_32: RoundType.ROUND_OF_16,
        RoundType.ROUND_OF_16: RoundType.QUARTERFINAL,
        RoundType.QUARTERFINAL: RoundType.SEMIFINAL,
        RoundType.SEMIFINAL: RoundType.FINAL,
    }

    all_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)

    # Group by round
    slots_by_round = {}
    for slot_orm in all_slots:
        round_type = slot_orm.round_type
        if round_type not in slots_by_round:
            slots_by_round[round_type] = []
        slots_by_round[round_type].append(slot_orm)

    # Determine the first round (earliest round that exists in the bracket)
    first_round = None
    for rt in [RoundType.ROUND_OF_128, RoundType.ROUND_OF_64, RoundType.ROUND_OF_32,
               RoundType.ROUND_OF_16, RoundType.QUARTERFINAL, RoundType.SEMIFINAL]:
        if rt in slots_by_round:
            first_round = rt
            break

    if not first_round:
        return 0  # No rounds to check

    pending_count = 0

    # Only check the FIRST round (BYEs only exist in the first round)
    for current_round in [first_round]:

        if current_round not in slots_by_round:
            continue

        next_round = round_progression.get(current_round)
        if not next_round or next_round not in slots_by_round:
            continue

        slots = sorted(slots_by_round[current_round], key=lambda s: s.slot_number)
        next_slots = {s.slot_number: s for s in slots_by_round[next_round]}

        for i in range(0, len(slots), 2):
            if i + 1 >= len(slots):
                break

            slot1 = slots[i]
            slot2 = slots[i + 1]

            # Check if this is a BYE match
            advancing_player_id = None
            if slot1.is_bye and slot2.player_id:
                advancing_player_id = slot2.player_id
            elif slot2.is_bye and slot1.player_id:
                advancing_player_id = slot1.player_id

            if advancing_player_id:
                # Check if player already advanced
                match_number = (i // 2) + 1
                next_slot = next_slots.get(match_number)

                if next_slot and next_slot.player_id != advancing_player_id:
                    # Player hasn't advanced yet - this is a pending BYE
                    pending_count += 1

    return pending_count


@app.post("/admin/bracket/{category}/reset")
async def admin_reset_bracket(request: Request, category: str):
    """Reset bracket for a category: delete bracket slots and bracket matches, keep group phase."""
    session = get_db_session()
    try:
        # Get current tournament
        tournament_repo = TournamentRepository(session)
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        bracket_repo = BracketRepository(session)
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)

        # Verify bracket exists
        bracket_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
        if not bracket_slots:
            request.session["flash_message"] = f"No hay bracket para resetear en la categoría {category}"
            request.session["flash_type"] = "warning"
            return RedirectResponse(url=f"/category/{category}", status_code=303)

        # Count what will be deleted
        deleted_matches = 0
        deleted_slots = 0

        # Delete bracket matches (non-RR matches for this category)
        all_matches = match_repo.get_all()
        for match_orm in all_matches:
            if match_orm.group_id is None:  # Bracket match (no group = knockout phase)
                # Check if belongs to this category by checking player
                if match_orm.player1_id:
                    player = player_repo.get_by_id(match_orm.player1_id)
                    if player and player.categoria == category:
                        session.delete(match_orm)
                        deleted_matches += 1
        session.commit()

        # Delete bracket slots
        deleted_slots = bracket_repo.delete_by_category(category, tournament_id=tournament_id)

        request.session["flash_message"] = f"Bracket reseteado: {deleted_slots} posiciones y {deleted_matches} partidos eliminados. Los grupos y partidos de grupo se mantienen."
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/admin/generate-bracket?category={category}", status_code=303)

    except Exception as e:
        request.session["flash_message"] = f"Error al resetear bracket: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url=f"/category/{category}", status_code=303)


@app.post("/admin/bracket/{category}/update-format")
async def admin_update_bracket_format(request: Request, category: str):
    """Update the best_of format for all bracket matches in a category (only if no matches played)."""
    session = get_db_session()
    try:
        form = await request.form()
        new_best_of = int(form.get("best_of", 5))

        if new_best_of not in [3, 5, 7]:
            request.session["flash_message"] = "Formato inválido. Debe ser 3, 5 o 7."
            request.session["flash_type"] = "error"
            return RedirectResponse(url=f"/category/{category}/bracket", status_code=303)

        tournament_repo = TournamentRepository(session)
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)

        # Get all bracket matches for this category
        all_matches = match_repo.get_all()
        bracket_matches = []
        has_played_matches = False

        for match_orm in all_matches:
            if match_orm.group_id is None:  # Bracket match
                if match_orm.player1_id:
                    player = player_repo.get_by_id(match_orm.player1_id)
                    if player and player.categoria == category:
                        bracket_matches.append(match_orm)
                        if match_orm.winner_id is not None:
                            has_played_matches = True

        if has_played_matches:
            request.session["flash_message"] = "No se puede cambiar el formato: ya hay partidos jugados en la llave."
            request.session["flash_type"] = "error"
            return RedirectResponse(url=f"/category/{category}/bracket", status_code=303)

        # Update all bracket matches
        updated_count = 0
        for match_orm in bracket_matches:
            match_orm.best_of = new_best_of
            updated_count += 1

        session.commit()

        format_names = {3: "Mejor de 3", 5: "Mejor de 5", 7: "Mejor de 7"}
        request.session["flash_message"] = f"Formato actualizado a {format_names[new_best_of]} para {updated_count} partidos de llave."
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/category/{category}/bracket", status_code=303)

    except Exception as e:
        request.session["flash_message"] = f"Error al actualizar formato: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url=f"/category/{category}/bracket", status_code=303)


def get_bye_positions(num_qualifiers: int, bracket_size: int) -> list[int]:
    """
    Get the exact BYE positions using ITTF HTR 2021 standards.

    This is a wrapper around the ITTF-compliant function in bracket.py.

    Args:
        num_qualifiers: Number of qualified players
        bracket_size: Bracket size (power of 2)

    Returns:
        List of positions where BYEs should be placed (1-indexed)
    """
    from ettem.bracket import get_bye_positions_for_bracket
    return sorted(list(get_bye_positions_for_bracket(num_qualifiers, bracket_size)))


def validate_bracket_round_order(match_orm, category, session) -> tuple[bool, str]:
    """
    Validate that all matches in previous rounds are completed before allowing
    a result in the current round.

    Args:
        match_orm: The match to validate
        category: Category name
        session: Database session

    Returns:
        Tuple of (is_valid, error_message)
    """
    from ettem.models import RoundType

    # Define round order (from first to last)
    round_order = [
        RoundType.ROUND_OF_32.value,
        RoundType.ROUND_OF_16.value,
        RoundType.QUARTERFINAL.value,
        RoundType.SEMIFINAL.value,
        RoundType.FINAL.value,
    ]

    round_names = {
        RoundType.ROUND_OF_32.value: "Ronda de 32",
        RoundType.ROUND_OF_16.value: "Ronda de 16",
        RoundType.QUARTERFINAL.value: "Cuartos de Final",
        RoundType.SEMIFINAL.value: "Semifinales",
        RoundType.FINAL.value: "Final",
    }

    current_round = match_orm.round_type

    # Find position of current round
    try:
        current_index = round_order.index(current_round)
    except ValueError:
        # RR or unknown round, allow
        return (True, "")

    # Get all bracket matches for this category
    match_repo = MatchRepository(session)

    all_matches = match_repo.get_all()
    bracket_matches = []
    for m in all_matches:
        if m.group_id is None:  # Bracket match
            # Use the match's category field directly (more reliable than player lookup
            # which fails for doubles/teams where player1_id is a pair/team ID)
            if hasattr(m, 'category') and m.category:
                if m.category == category:
                    bracket_matches.append(m)
            elif m.player1_id:
                # Fallback: lookup player category (legacy)
                player_repo = PlayerRepository(session)
                player = player_repo.get_by_id(m.player1_id)
                if player and player.categoria == category:
                    bracket_matches.append(m)

    # Check all previous rounds
    for i in range(current_index):
        prev_round = round_order[i]
        prev_round_matches = [m for m in bracket_matches if m.round_type == prev_round]

        # Only check if matches exist for that round
        if prev_round_matches:
            # Check if any match is pending
            pending_matches = [m for m in prev_round_matches if m.status == "pending"]
            if pending_matches:
                # Check if any pending match has both players assigned (not BYE scenarios)
                real_pending = [m for m in pending_matches if m.player1_id and m.player2_id]
                if real_pending:
                    return (False, f"Debe completar todos los partidos de {round_names.get(prev_round, prev_round)} antes de ingresar resultados de {round_names.get(current_round, current_round)}.")

    return (True, "")


def advance_bracket_winner(match_orm, winner_id, category, session, tournament_id=None):
    """
    Advance the winner of a bracket match to the next round.

    Args:
        match_orm: The completed match
        winner_id: ID of the winner (player_id for singles, pair_id for doubles)
        category: Category name
        session: Database session
        tournament_id: Tournament ID to filter by

    Returns:
        True if advancement was successful, False if this is the final
    """
    from ettem.models import RoundType, Match, MatchStatus, is_doubles_category, is_teams_category
    from ettem.storage import BracketSlotORM

    is_doubles = is_doubles_category(category)
    is_teams = is_teams_category(category)

    # Map rounds to next round
    round_progression = {
        RoundType.ROUND_OF_128.value: RoundType.ROUND_OF_64.value,
        RoundType.ROUND_OF_64.value: RoundType.ROUND_OF_32.value,
        RoundType.ROUND_OF_32.value: RoundType.ROUND_OF_16.value,
        RoundType.ROUND_OF_16.value: RoundType.QUARTERFINAL.value,
        RoundType.QUARTERFINAL.value: RoundType.SEMIFINAL.value,
        RoundType.SEMIFINAL.value: RoundType.FINAL.value,
        RoundType.FINAL.value: None,  # No next round after final
    }

    current_round = match_orm.round_type
    next_round = round_progression.get(current_round)

    if next_round is None:
        # This is the final, no advancement needed
        return False

    # Get the match number (1-based)
    match_number = match_orm.match_number

    # Calculate which slot in the next round the winner should go to
    # Match 1 (slots 1-2) → next slot 1
    # Match 2 (slots 3-4) → next slot 2
    # Match N → next slot N
    next_slot_number = match_number

    # Update or create the bracket slot for the next round
    bracket_repo = BracketRepository(session)
    match_repo = MatchRepository(session)

    # Check if slot exists in next round (filter by tournament_id)
    next_round_slots = bracket_repo.get_by_category_and_round(category, next_round, tournament_id=tournament_id)

    # Find the specific slot
    target_slot = None
    for slot in next_round_slots:
        if slot.slot_number == next_slot_number:
            target_slot = slot
            break

    if target_slot:
        # Update existing slot with winner
        update_data = {"player_id": winner_id, "is_bye": False}
        if is_doubles:
            update_data["pair_id"] = winner_id
        if is_teams:
            update_data["team_id"] = winner_id
        bracket_repo.session.query(BracketSlotORM).filter(
            BracketSlotORM.id == target_slot.id
        ).update(update_data)
        bracket_repo.session.commit()
    else:
        # Create new slot in next round
        new_slot_orm = BracketSlotORM(
            category=category,
            tournament_id=tournament_id,
            slot_number=next_slot_number,
            round_type=next_round,
            player_id=winner_id,
            is_bye=False,
            same_country_warning=False,
            advanced_by_bye=False
        )
        if is_doubles:
            new_slot_orm.pair_id = winner_id
        if is_teams:
            new_slot_orm.team_id = winner_id
        bracket_repo.session.add(new_slot_orm)
        bracket_repo.session.commit()
        next_round_slots = bracket_repo.get_by_category_and_round(category, next_round, tournament_id=tournament_id)  # Refresh slots list

    # Now check if this creates a new match (if both players are now filled)
    # Find the pair slot (odd slots pair with even+1, even slots pair with odd-1)
    if next_slot_number % 2 == 1:
        pair_slot_number = next_slot_number + 1
    else:
        pair_slot_number = next_slot_number - 1

    pair_slot = None
    for slot in next_round_slots:
        if slot.slot_number == pair_slot_number:
            pair_slot = slot
            break

    # Create pair slot if it doesn't exist
    if not pair_slot:
        new_pair_slot_orm = BracketSlotORM(
            category=category,
            tournament_id=tournament_id,
            slot_number=pair_slot_number,
            round_type=next_round,
            player_id=None,
            is_bye=False,
            same_country_warning=False,
            advanced_by_bye=False
        )
        bracket_repo.session.add(new_pair_slot_orm)
        bracket_repo.session.commit()
        next_round_slots = bracket_repo.get_by_category_and_round(category, next_round, tournament_id=tournament_id)  # Refresh slots list
        for slot in next_round_slots:
            if slot.slot_number == pair_slot_number:
                pair_slot = slot
                break

    # Update the match in the next round (should already exist from create_bracket_matches)
    if pair_slot:
        # Determine which is player1 and player2 (lower slot number is player1)
        if next_slot_number < pair_slot_number:
            player1_id = winner_id
            player2_id = pair_slot.player_id  # Can be None if not yet determined
        else:
            player1_id = pair_slot.player_id  # Can be None if not yet determined
            player2_id = winner_id

        # Calculate match number
        next_match_number = (min(next_slot_number, pair_slot_number) + 1) // 2

        # Find existing match (should always exist from create_bracket_matches)
        existing_match = match_repo.get_bracket_match_by_round_and_number(category, next_round, next_match_number, tournament_id=tournament_id)

        if existing_match:
            # Update existing match with the new player(s)
            update_data = {
                "player1_id": player1_id,
                "player2_id": player2_id,
                "status": MatchStatus.PENDING.value
            }
            if is_doubles:
                update_data["pair1_id"] = player1_id
                update_data["pair2_id"] = player2_id
                update_data["event_type"] = "doubles"
            if is_teams:
                update_data["team1_id"] = player1_id
                update_data["team2_id"] = player2_id
                update_data["event_type"] = "teams"
                if not existing_match.team_match_system:
                    update_data["team_match_system"] = match_orm.team_match_system or "swaythling"
            match_repo.session.query(MatchORM).filter(
                MatchORM.id == existing_match.id
            ).update(update_data)
        else:
            # Match should exist but doesn't - create it (fallback)
            new_match = Match(
                id=0,
                player1_id=player1_id,
                player2_id=player2_id,
                group_id=None,
                round_type=RoundType(next_round),
                round_name=f"{next_round}{next_match_number}",
                match_number=next_match_number,
                status=MatchStatus.PENDING,
            )
            match_repo.create(new_match, category=category)
            if is_doubles:
                created = match_repo.get_bracket_match_by_round_and_number(category, next_round, next_match_number)
                if created:
                    created.pair1_id = player1_id
                    created.pair2_id = player2_id
                    created.event_type = "doubles"
            if is_teams:
                created = match_repo.get_bracket_match_by_round_and_number(category, next_round, next_match_number)
                if created:
                    created.team1_id = player1_id
                    created.team2_id = player2_id
                    created.event_type = "teams"
                    created.team_match_system = match_orm.team_match_system or "swaythling"

        match_repo.session.commit()

    return True


def rollback_bracket_advancement(match_orm, winner_id, category, session, tournament_id=None):
    """
    Rollback the advancement of a bracket winner when a result is deleted.

    This reverses the effect of advance_bracket_winner by:
    1. Finding the slot in the next round where the winner was placed
    2. Clearing that slot (setting player_id to None)
    3. Updating the corresponding match in the next round

    Args:
        match_orm: The match whose result is being deleted
        winner_id: ID of the winner who needs to be removed from next round
        category: Category name
        session: Database session
        tournament_id: Tournament ID to filter by

    Returns:
        True if rollback was successful, False if no rollback needed (e.g., final)
    """
    from ettem.models import RoundType, MatchStatus, is_doubles_category
    from ettem.storage import BracketSlotORM

    is_doubles = is_doubles_category(category)

    # Map rounds to next round (same as advance_bracket_winner)
    round_progression = {
        RoundType.ROUND_OF_128.value: RoundType.ROUND_OF_64.value,
        RoundType.ROUND_OF_64.value: RoundType.ROUND_OF_32.value,
        RoundType.ROUND_OF_32.value: RoundType.ROUND_OF_16.value,
        RoundType.ROUND_OF_16.value: RoundType.QUARTERFINAL.value,
        RoundType.QUARTERFINAL.value: RoundType.SEMIFINAL.value,
        RoundType.SEMIFINAL.value: RoundType.FINAL.value,
        RoundType.FINAL.value: None,
    }

    current_round = match_orm.round_type
    next_round = round_progression.get(current_round)

    if next_round is None:
        # This is the final, no rollback needed
        return False

    # Get the match number (1-based)
    match_number = match_orm.match_number

    # The winner was placed in slot number = match_number of the next round
    next_slot_number = match_number

    bracket_repo = BracketRepository(session)
    match_repo = MatchRepository(session)

    # Find the slot in the next round where the winner was placed
    next_round_slots = bracket_repo.get_by_category_and_round(category, next_round, tournament_id=tournament_id)

    target_slot = None
    for slot in next_round_slots:
        if slot.slot_number == next_slot_number:
            target_slot = slot
            break

    if target_slot and target_slot.player_id == winner_id:
        # Clear the slot (remove the winner)
        clear_data = {"player_id": None, "is_bye": False, "advanced_by_bye": False}
        if is_doubles:
            clear_data["pair_id"] = None
        session.query(BracketSlotORM).filter(
            BracketSlotORM.id == target_slot.id
        ).update(clear_data)
        session.commit()

        # Also update the match in the next round to remove this player
        # Find the pair slot
        if next_slot_number % 2 == 1:
            pair_slot_number = next_slot_number + 1
        else:
            pair_slot_number = next_slot_number - 1

        # Calculate match number in next round
        next_match_number = (min(next_slot_number, pair_slot_number) + 1) // 2

        # Find the match in the next round
        rollback_query = session.query(MatchORM).filter(
            MatchORM.category == category,
            MatchORM.group_id == None,
            MatchORM.round_type == next_round,
            MatchORM.match_number == next_match_number
        )
        if tournament_id is not None:
            rollback_query = rollback_query.filter(MatchORM.tournament_id == tournament_id)
        existing_match = rollback_query.first()

        if existing_match:
            # Determine which player position to clear based on slot number
            if next_slot_number < pair_slot_number:
                # Winner was player1
                update_data = {"player1_id": None}
                if is_doubles:
                    update_data["pair1_id"] = None
                session.query(MatchORM).filter(
                    MatchORM.id == existing_match.id
                ).update(update_data)
            else:
                # Winner was player2
                update_data = {"player2_id": None}
                if is_doubles:
                    update_data["pair2_id"] = None
                session.query(MatchORM).filter(
                    MatchORM.id == existing_match.id
                ).update(update_data)
            session.commit()

        return True

    return False


def create_bracket_matches(category: str, bracket_repo, match_repo, tournament_id: int = None, best_of: int = 5, event_type: str = "singles"):
    """
    Create Match objects for all bracket rounds based on bracket slots.

    Matches are created by pairing adjacent slots (1-2, 3-4, etc.) in each round.
    When a match has a result, the winner advances to the next round automatically.

    Args:
        category: Category name
        bracket_repo: BracketRepository instance
        match_repo: MatchRepository instance
        tournament_id: Optional tournament ID to filter by
        best_of: Match format (3, 5, or 7 sets)
        event_type: 'singles', 'doubles', or 'teams'

    Returns:
        Number of matches created
    """
    from ettem.models import Match, MatchStatus, RoundType

    # Get all slots for this category, grouped by round
    all_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
    print(f"[DEBUG create_bracket_matches] category={category}, tournament_id={tournament_id}, total slots={len(all_slots)}")

    # Group slots by round_type
    slots_by_round = {}
    for slot_orm in all_slots:
        round_type = slot_orm.round_type
        if round_type not in slots_by_round:
            slots_by_round[round_type] = []
        slots_by_round[round_type].append(slot_orm)

    # Get existing bracket matches for THIS category and tournament to avoid duplicates
    existing_bracket_matches = {}
    for match_orm in match_repo.get_bracket_matches_by_category(category, tournament_id=tournament_id):
        key = (match_orm.round_type, match_orm.match_number)
        existing_bracket_matches[key] = match_orm
        print(f"[DEBUG] Existing match found: {key}")

    matches_created = 0
    import sys
    sys.stderr.write(f"[DEBUG] slots_by_round keys: {list(slots_by_round.keys())}\n")
    sys.stderr.write(f"[DEBUG] existing_bracket_matches keys: {list(existing_bracket_matches.keys())}\n")
    sys.stderr.flush()

    # Create matches for each round
    for round_type in [RoundType.ROUND_OF_128, RoundType.ROUND_OF_64, RoundType.ROUND_OF_32, RoundType.ROUND_OF_16,
                       RoundType.QUARTERFINAL, RoundType.SEMIFINAL, RoundType.FINAL]:

        # Check both enum value and string key
        round_key = round_type.value if round_type.value in slots_by_round else round_type
        if round_key not in slots_by_round:
            print(f"[DEBUG] Skipping round {round_type.value} - not in slots_by_round")
            continue

        print(f"[DEBUG] Processing round {round_type.value} with {len(slots_by_round[round_key])} slots")
        slots = sorted(slots_by_round[round_key], key=lambda s: s.slot_number)

        # Create matches by pairing adjacent slots (1-2, 3-4, 5-6, etc.)
        for i in range(0, len(slots), 2):
            if i + 1 >= len(slots):
                break

            slot1 = slots[i]
            slot2 = slots[i + 1]

            # Skip if both slots are BYEs
            if slot1.is_bye and slot2.is_bye:
                continue

            # Determine player IDs (None for BYE or empty slot)
            player1_id = slot1.player_id if not slot1.is_bye else None
            player2_id = slot2.player_id if not slot2.is_bye else None

            match_number = (i // 2) + 1
            round_name = f"{round_type.value}{match_number}"

            # Handle BYE matches - don't create a match, just advance the player
            # If one player is BYE, the other advances automatically
            if (slot1.is_bye and not slot2.is_bye) or (slot2.is_bye and not slot1.is_bye):
                # One is BYE, one is player - skip creating match
                # The player advances via process_bye_advancements
                continue

            # Check if match already exists for this round and match number
            match_key = (round_type.value, match_number)
            if match_key in existing_bracket_matches:
                # Match already exists, skip creation
                continue

            # Create matches for all rounds:
            # - Both players present: ready to play
            # - One player present: waiting for opponent (BYE advancement)
            # - Both empty: future round placeholder
            match = Match(
                id=0,
                player1_id=player1_id,
                player2_id=player2_id,
                group_id=None,
                round_type=round_type,
                round_name=round_name,
                match_number=match_number,
                status=MatchStatus.PENDING,
            )
            match_repo.create(match, category=category, tournament_id=tournament_id, best_of=best_of, event_type=event_type)
            matches_created += 1

    return matches_created


def create_empty_bracket_structure(category: str, num_groups: int, advance_per_group: int,
                                    bracket_repo, match_repo, tournament_id: int = None, best_of: int = 5):
    """
    Create empty bracket structure (slots and matches) when groups are created.

    This allows scheduling bracket matches in advance, before group phase completes.
    When "Generate Bracket" is called later, the slots get updated with actual player IDs.

    Args:
        category: Category name (e.g., "OPEN", "SUB13")
        num_groups: Number of groups created
        advance_per_group: How many players advance per group (typically 2)
        bracket_repo: BracketRepository instance
        match_repo: MatchRepository instance
        tournament_id: Tournament ID
        best_of: Match format (3, 5, or 7 sets)

    Returns:
        Tuple of (slots_created, matches_created)
    """
    from ettem.bracket import next_power_of_2, get_round_type_for_size, get_bye_positions_for_bracket
    from ettem.models import BracketSlot, RoundType

    # Calculate bracket size
    num_qualifiers = num_groups * advance_per_group
    bracket_size = next_power_of_2(num_qualifiers)

    print(f"[DEBUG create_empty_bracket] category={category}, groups={num_groups}, advance={advance_per_group}")
    print(f"[DEBUG create_empty_bracket] qualifiers={num_qualifiers}, bracket_size={bracket_size}")

    # Get BYE positions
    bye_positions = get_bye_positions_for_bracket(num_qualifiers, bracket_size)
    print(f"[DEBUG create_empty_bracket] bye_positions={bye_positions}")

    # Get first round type
    first_round = get_round_type_for_size(bracket_size)

    # Delete any existing bracket slots and matches for this category/tournament
    deleted_slots = bracket_repo.delete_by_category(category, tournament_id=tournament_id)
    deleted_matches = match_repo.delete_bracket_matches_by_category(category, tournament_id=tournament_id)
    print(f"[DEBUG create_empty_bracket] Deleted {deleted_slots} existing slots, {deleted_matches} existing matches")

    slots_created = 0

    # Create slots for first round
    for slot_num in range(1, bracket_size + 1):
        slot = BracketSlot(
            slot_number=slot_num,
            round_type=first_round,
            player_id=None,  # Empty - will be filled when bracket is generated
            is_bye=slot_num in bye_positions,
        )
        bracket_repo.create_slot(slot, category, tournament_id=tournament_id)
        slots_created += 1

    # Create slots for subsequent rounds
    round_progression = {
        RoundType.ROUND_OF_128: RoundType.ROUND_OF_64,
        RoundType.ROUND_OF_64: RoundType.ROUND_OF_32,
        RoundType.ROUND_OF_32: RoundType.ROUND_OF_16,
        RoundType.ROUND_OF_16: RoundType.QUARTERFINAL,
        RoundType.QUARTERFINAL: RoundType.SEMIFINAL,
        RoundType.SEMIFINAL: RoundType.FINAL,
    }

    current_round = first_round
    current_size = bracket_size

    while current_round in round_progression:
        next_round = round_progression[current_round]
        next_size = current_size // 2

        # Create empty slots for next round
        for slot_num in range(1, next_size + 1):
            slot = BracketSlot(
                slot_number=slot_num,
                round_type=next_round,
                player_id=None,
                is_bye=False,
            )
            bracket_repo.create_slot(slot, category, tournament_id=tournament_id)
            slots_created += 1

        current_round = next_round
        current_size = next_size

    print(f"[DEBUG create_empty_bracket] Created {slots_created} slots")

    # Now create the matches using existing function
    matches_created = create_bracket_matches(category, bracket_repo, match_repo, tournament_id=tournament_id, best_of=best_of)

    print(f"[DEBUG create_empty_bracket] Created {matches_created} matches")

    return slots_created, matches_created


def sync_bracket_matches_with_slots(category: str, bracket_repo, match_repo, session, tournament_id: int = None, event_type: str = "singles"):
    """
    Synchronize bracket matches with their corresponding slots.

    After process_bye_advancements updates slots, this function updates
    the matches to have the correct player IDs from the slots.
    """
    from ettem.models import RoundType

    # Get all slots grouped by round
    all_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
    slots_by_round = {}
    for slot_orm in all_slots:
        round_type = slot_orm.round_type
        if round_type not in slots_by_round:
            slots_by_round[round_type] = []
        slots_by_round[round_type].append(slot_orm)

    # Get bracket matches for THIS category and tournament only
    all_matches = match_repo.get_bracket_matches_by_category(category, tournament_id=tournament_id)

    # For each round, update matches with players from slots
    for round_type in [RoundType.ROUND_OF_128, RoundType.ROUND_OF_64, RoundType.ROUND_OF_32, RoundType.ROUND_OF_16,
                       RoundType.QUARTERFINAL, RoundType.SEMIFINAL, RoundType.FINAL]:

        if round_type not in slots_by_round:
            continue

        slots = sorted(slots_by_round[round_type], key=lambda s: s.slot_number)

        # Process pairs of slots (1-2, 3-4, etc.)
        for i in range(0, len(slots), 2):
            if i + 1 >= len(slots):
                break

            slot1 = slots[i]
            slot2 = slots[i + 1]
            match_number = (i // 2) + 1

            # Find the corresponding match
            for match_orm in all_matches:
                if (match_orm.round_type == round_type.value and
                    match_orm.match_number == match_number):

                    # Update player IDs from slots
                    player1_id = slot1.player_id if not slot1.is_bye else None
                    player2_id = slot2.player_id if not slot2.is_bye else None

                    changed = False
                    if match_orm.player1_id != player1_id or match_orm.player2_id != player2_id:
                        match_orm.player1_id = player1_id
                        match_orm.player2_id = player2_id
                        changed = True
                    # Also set team/pair IDs for non-singles event types
                    if event_type == "teams":
                        match_orm.team1_id = player1_id
                        match_orm.team2_id = player2_id
                        if match_orm.event_type != "teams":
                            match_orm.event_type = "teams"
                            changed = True
                        if not match_orm.team_match_system:
                            match_orm.team_match_system = "swaythling"
                            changed = True
                    elif event_type == "doubles":
                        match_orm.pair1_id = player1_id
                        match_orm.pair2_id = player2_id
                        if match_orm.event_type != "doubles":
                            match_orm.event_type = "doubles"
                            changed = True
                    if changed:
                        session.commit()
                    break


@app.get("/admin/sync-bracket/{category}")
async def admin_sync_bracket(request: Request, category: str):
    """
    Manually sync bracket matches with slot data.

    This fixes the issue where matches show TBD when slots have players.
    """
    with get_db_session() as session:
        bracket_repo = BracketRepository(session)
        match_repo = MatchRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Check if bracket exists for this category
        slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
        if not slots:
            return RedirectResponse(
                url=f"/admin/print-center?error=No+hay+bracket+para+{category}",
                status_code=302
            )

        # Sync matches with slots
        sync_bracket_matches_with_slots(category, bracket_repo, match_repo, session, tournament_id=tournament_id)

        # Return to print center with success message
        return RedirectResponse(
            url=f"/admin/print-center?success=Bracket+sincronizado+para+{category}",
            status_code=302
        )


@app.get("/admin/sync-bracket-all")
async def admin_sync_bracket_all(request: Request):
    """
    Sync all bracket matches with slot data for all categories.
    """
    with get_db_session() as session:
        bracket_repo = BracketRepository(session)
        match_repo = MatchRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Get all categories with brackets
        all_slots = bracket_repo.get_all(tournament_id=tournament_id) if tournament_id else bracket_repo.get_all()
        categories = set(slot.category for slot in all_slots)

        synced_count = 0
        for category in categories:
            sync_bracket_matches_with_slots(category, bracket_repo, match_repo, session, tournament_id=tournament_id)
            synced_count += 1

        # Return to print center with success message
        return RedirectResponse(
            url=f"/admin/print-center?success=Brackets+sincronizados:+{synced_count}+categorías",
            status_code=302
        )


@app.get("/admin/repair-bracket/{category}")
async def admin_repair_bracket(request: Request, category: str):
    """
    Repair an existing bracket by creating missing slots for subsequent rounds.
    This preserves existing slots and results while adding missing QF/SF/F slots.
    """
    from ettem.models import BracketSlot, RoundType

    session = get_db_session()
    try:
        bracket_repo = BracketRepository(session)
        match_repo = MatchRepository(session)
        tournament_repo = TournamentRepository(session)

        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Get existing slots
        existing_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
        if not existing_slots:
            request.session["flash_message"] = f"No hay bracket para {category}"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/generate-bracket", status_code=303)

        # Group by round
        slots_by_round = {}
        for slot in existing_slots:
            if slot.round_type not in slots_by_round:
                slots_by_round[slot.round_type] = []
            slots_by_round[slot.round_type].append(slot)

        # Determine first round and bracket size
        first_round = None
        bracket_size = 0
        for rt in [RoundType.ROUND_OF_128, RoundType.ROUND_OF_64, RoundType.ROUND_OF_32, RoundType.ROUND_OF_16, RoundType.QUARTERFINAL, RoundType.SEMIFINAL]:
            if rt.value in slots_by_round:
                first_round = rt
                bracket_size = len(slots_by_round[rt.value])
                break

        if not first_round:
            request.session["flash_message"] = "No se pudo determinar la primera ronda"
            request.session["flash_type"] = "error"
            return RedirectResponse(url=f"/bracket/{category}", status_code=303)

        # Define round progression
        round_progression = {
            RoundType.ROUND_OF_128: (RoundType.ROUND_OF_64, 64),
            RoundType.ROUND_OF_64: (RoundType.ROUND_OF_32, 32),
            RoundType.ROUND_OF_32: (RoundType.ROUND_OF_16, 16),
            RoundType.ROUND_OF_16: (RoundType.QUARTERFINAL, 8),
            RoundType.QUARTERFINAL: (RoundType.SEMIFINAL, 4),
            RoundType.SEMIFINAL: (RoundType.FINAL, 2),
        }

        # Create missing slots for subsequent rounds
        slots_created = 0
        current_round = first_round
        while current_round in round_progression:
            next_round, next_size = round_progression[current_round]

            # Check if slots for next round already exist
            if next_round.value not in slots_by_round:
                # Create empty slots for this round
                for slot_num in range(1, next_size + 1):
                    slot = BracketSlot(
                        slot_number=slot_num,
                        round_type=next_round,
                        player_id=None,
                        is_bye=False,
                        same_country_warning=False
                    )
                    bracket_repo.create_slot(slot, category, tournament_id=tournament_id)
                    slots_created += 1

            current_round = next_round

        # Process BYE advancements (and delete BYE matches)
        process_bye_advancements(category, bracket_repo, session, tournament_id=tournament_id, match_repo=match_repo)

        # Delete bracket matches WITHOUT results for this category (preserve completed matches)
        # ONLY delete matches that have at least one player from this category
        player_repo = PlayerRepository(session)
        existing_matches = match_repo.get_all()
        deleted_matches = 0
        for match_orm in existing_matches:
            if match_orm.group_id is None:  # Bracket match
                # Only delete if no result (winner_id is None)
                if match_orm.winner_id is not None:
                    continue  # Has result, keep it

                # Check if belongs to this category BY PLAYER only
                # Ignore matches without players - they could be from another category
                belongs_to_category = False
                if match_orm.player1_id:
                    player = player_repo.get_by_id(match_orm.player1_id)
                    if player and player.categoria == category:
                        belongs_to_category = True
                if not belongs_to_category and match_orm.player2_id:
                    player = player_repo.get_by_id(match_orm.player2_id)
                    if player and player.categoria == category:
                        belongs_to_category = True

                if belongs_to_category:
                    session.delete(match_orm)
                    deleted_matches += 1
        session.commit()

        # Create matches for all rounds
        matches_created = create_bracket_matches(category, bracket_repo, match_repo, tournament_id=tournament_id)

        # Sync matches with slots
        sync_bracket_matches_with_slots(category, bracket_repo, match_repo, session, tournament_id=tournament_id)

        request.session["flash_message"] = f"Bracket reparado: {slots_created} slots, {deleted_matches} eliminados, {matches_created} partidos creados"
        request.session["flash_type"] = "success"
        return RedirectResponse(url=f"/bracket/{category}", status_code=303)

    except Exception as e:
        request.session["flash_message"] = f"Error al reparar bracket: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url=f"/bracket/{category}", status_code=303)
    finally:
        session.close()


def process_bye_advancements(category: str, bracket_repo, session, tournament_id: int = None, match_repo=None):
    """
    Automatically advance players who face BYEs to the next round.

    When a player faces a BYE (no opponent), they should automatically
    advance to the next round without needing to play a match.
    This function also removes any BYE matches that shouldn't exist.

    Args:
        category: Category name
        bracket_repo: BracketRepository instance
        session: Database session
        tournament_id: Optional tournament ID to filter by
        match_repo: Optional MatchRepository for deleting BYE matches
    """
    from ettem.models import RoundType

    # Map rounds to next round
    round_progression = {
        RoundType.ROUND_OF_128: RoundType.ROUND_OF_64,
        RoundType.ROUND_OF_64: RoundType.ROUND_OF_32,
        RoundType.ROUND_OF_32: RoundType.ROUND_OF_16,
        RoundType.ROUND_OF_16: RoundType.QUARTERFINAL,
        RoundType.QUARTERFINAL: RoundType.SEMIFINAL,
        RoundType.SEMIFINAL: RoundType.FINAL,
    }

    # Get all slots for this category
    all_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)

    # Group by round
    slots_by_round = {}
    for slot_orm in all_slots:
        round_type = slot_orm.round_type
        if round_type not in slots_by_round:
            slots_by_round[round_type] = []
        slots_by_round[round_type].append(slot_orm)

    # Determine the first round (earliest round that exists in the bracket)
    first_round = None
    for rt in [RoundType.ROUND_OF_128, RoundType.ROUND_OF_64, RoundType.ROUND_OF_32,
               RoundType.ROUND_OF_16, RoundType.QUARTERFINAL, RoundType.SEMIFINAL]:
        if rt in slots_by_round:
            first_round = rt
            break

    if not first_round:
        return True  # No rounds to process

    # Collect player IDs that advanced by BYE to delete their matches later
    bye_player_ids = []

    # Only process the FIRST round (BYEs only exist in the first round)
    for current_round in [first_round]:

        if current_round not in slots_by_round:
            continue

        next_round = round_progression.get(current_round)
        if not next_round:
            continue

        slots = sorted(slots_by_round[current_round], key=lambda s: s.slot_number)

        # Process pairs of slots (1-2, 3-4, etc.)
        for i in range(0, len(slots), 2):
            if i + 1 >= len(slots):
                break

            slot1 = slots[i]
            slot2 = slots[i + 1]

            # Skip if both are BYEs
            if slot1.is_bye and slot2.is_bye:
                continue

            # Determine which player advances
            advancing_player_id = None
            if slot1.is_bye and slot2.player_id:
                # Player 2 advances
                advancing_player_id = slot2.player_id
            elif slot2.is_bye and slot1.player_id:
                # Player 1 advances
                advancing_player_id = slot1.player_id

            # If we have a player to advance
            if advancing_player_id:
                bye_player_ids.append(advancing_player_id)

                # Calculate next round slot number (same as match number)
                match_number = (i // 2) + 1
                next_slot_number = match_number

                # Find or create the slot in next round
                next_round_slots = bracket_repo.get_by_category_and_round(category, next_round)

                # Find the specific slot
                target_slot = None
                for ns in next_round_slots:
                    if ns.slot_number == next_slot_number:
                        target_slot = ns
                        break

                # Update the slot with the advancing player
                if target_slot:
                    target_slot.player_id = advancing_player_id
                    target_slot.is_bye = False
                    target_slot.advanced_by_bye = True
                    session.commit()

    # Delete BYE matches (matches where one player is None) from the FIRST ROUND only
    # These matches shouldn't exist - players should advance automatically
    if match_repo and first_round:
        deleted_count = 0
        all_matches = match_repo.get_all()
        player_repo = PlayerRepository(session)
        first_round_value = first_round.value if hasattr(first_round, 'value') else first_round

        for match_orm in all_matches:
            # Only process bracket matches (group_id is None)
            if match_orm.group_id is not None:
                continue
            # Only process matches from the first round
            if match_orm.round_type != first_round_value:
                continue
            # Check if this is a BYE match (one player is None)
            if match_orm.player1_id is None or match_orm.player2_id is None:
                # Verify this match belongs to our category by checking the player
                player_id = match_orm.player1_id or match_orm.player2_id
                if player_id:
                    player = player_repo.get_by_id(player_id)
                    if player and player.categoria == category:
                        session.delete(match_orm)
                        deleted_count += 1
        if deleted_count > 0:
            session.commit()
            print(f"[DEBUG] Deleted {deleted_count} BYE matches for {category} (first round: {first_round_value})")

    return True


@app.get("/admin/manual-bracket/{category}", response_class=HTMLResponse)
async def admin_manual_bracket_form(request: Request, category: str):
    """Show manual bracket positioning form with drag-and-drop interface."""
    session = get_db_session()
    try:
        standing_repo = StandingRepository(session)
        player_repo = PlayerRepository(session)
        group_repo = GroupRepository(session)
        match_repo = MatchRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        tournament = tournament_repo.get_current()
        tournament_id = tournament.id if tournament else None

        # First, validate that groups exist for this category in current tournament
        all_groups = group_repo.get_all(tournament_id=tournament_id)
        category_groups = [g for g in all_groups if g.category == category]

        if not category_groups:
            request.session["flash_message"] = f"No hay grupos creados para la categoría {category}. Crea grupos primero."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/generate-bracket", status_code=303)

        # Validate that all matches are completed
        all_matches = match_repo.get_all()
        category_matches = [m for m in all_matches if m.group_id in [g.id for g in category_groups]]
        pending_matches = [m for m in category_matches if m.status == MatchStatus.PENDING]

        if pending_matches:
            request.session["flash_message"] = f"Hay {len(pending_matches)} partidos pendientes en {category}. Completa todos los partidos antes de generar el bracket."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/generate-bracket", status_code=303)

        # Get all standings for this category (filtered by tournament via group_id)
        current_group_ids = set(g.id for g in category_groups)
        all_standings = standing_repo.get_all()

        # Filter by category and separate by position
        firsts = []
        seconds = []

        # Create a lookup for group names
        group_name_lookup = {g.id: g.name for g in category_groups}

        for standing_orm in all_standings:
            # Only include standings from current tournament's groups
            if standing_orm.group_id not in current_group_ids:
                continue
            player_orm = player_repo.get_by_id(standing_orm.player_id)
            if not player_orm or player_orm.categoria != category:
                continue

            # Calculate ratios
            sets_ratio = standing_orm.sets_w / standing_orm.sets_l if standing_orm.sets_l > 0 else 999.0
            points_ratio = standing_orm.points_w / standing_orm.points_l if standing_orm.points_l > 0 else 999.0

            # Get group name (1, 2, 3...) instead of group_id (7, 8, 9...)
            group_name = group_name_lookup.get(standing_orm.group_id, str(standing_orm.group_id))

            if standing_orm.position == 1:
                firsts.append({
                    "player_id": player_orm.id,
                    "nombre": player_orm.nombre,
                    "apellido": player_orm.apellido,
                    "pais_cd": player_orm.pais_cd,
                    "group_id": standing_orm.group_id,
                    "group_name": group_name,
                    "points_total": standing_orm.points_total,
                    "sets_ratio": sets_ratio,
                    "points_ratio": points_ratio,
                    "seed": player_orm.seed or 999
                })
            elif standing_orm.position == 2:
                seconds.append({
                    "player_id": player_orm.id,
                    "nombre": player_orm.nombre,
                    "apellido": player_orm.apellido,
                    "pais_cd": player_orm.pais_cd,
                    "group_id": standing_orm.group_id,
                    "group_name": group_name,
                    "points_total": standing_orm.points_total,
                    "sets_ratio": sets_ratio,
                    "points_ratio": points_ratio,
                    "seed": player_orm.seed or 999
                })

        if not firsts and not seconds:
            request.session["flash_message"] = f"No hay clasificados para la categoría {category}. Calcula standings primero."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/generate-bracket", status_code=303)

        # Sort by group_name (1, 2, 3...) - this is the natural order for bracket positioning
        firsts.sort(key=lambda x: int(x["group_name"]) if x["group_name"].isdigit() else x["group_id"])
        seconds.sort(key=lambda x: int(x["group_name"]) if x["group_name"].isdigit() else x["group_id"])

        # Calculate bracket size and BYEs using ITTF HTR 2021 positions
        total_qualifiers = len(firsts) + len(seconds)
        bracket_size = 2 ** math.ceil(math.log2(total_qualifiers)) if total_qualifiers > 0 else 0

        # Get exact BYE positions using ITTF standard
        bye_positions = get_bye_positions(total_qualifiers, bracket_size)
        all_bye_positions = set(bye_positions)

        # DEBUG: Print to console
        print(f"DEBUG: total_qualifiers={total_qualifiers}, bye_positions={bye_positions}, bracket_size={bracket_size}")

        # Create bracket slots with pre-placed BYEs
        slots = []

        for i in range(1, bracket_size + 1):
            slots.append({
                "slot_number": i,
                "player_id": None,
                "is_bye": i in all_bye_positions
            })

        # Check if there's saved form data from a previous validation error
        saved_assignments = request.session.pop("bracket_form_data", None)

        return render_template(
            "admin_manual_bracket.html",
            {
                "request": request,
                "category": category,
                "firsts": firsts,
                "seconds": seconds,
                "bracket_size": bracket_size,
                "slots": slots,
                "saved_assignments": saved_assignments,
            }
        )
    finally:
        session.close()


@app.post("/admin/manual-bracket/{category}/save")
async def admin_manual_bracket_save(request: Request, category: str):
    """Save manually positioned bracket."""
    from ettem.models import BracketSlot, RoundType

    try:
        session = get_db_session()
        player_repo = PlayerRepository(session)
        bracket_repo = BracketRepository(session)
        standing_repo = StandingRepository(session)
        tournament_repo = TournamentRepository(session)
        group_repo = GroupRepository(session)
        match_repo = MatchRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # VALIDATION: Check that all group matches are completed
        groups = group_repo.get_by_category(category, tournament_id=tournament_id)
        pending_count = 0
        groups_with_pending = []
        for group in groups:
            matches = match_repo.get_by_group(group.id)
            group_pending = sum(1 for m in matches if m.status == MatchStatus.PENDING.value or m.status == MatchStatus.PENDING)
            if group_pending > 0:
                pending_count += group_pending
                groups_with_pending.append(str(group.name))

        if pending_count > 0:
            request.session["flash_message"] = f"No se puede guardar bracket: hay {pending_count} partidos pendientes en los grupos: {', '.join(sorted(groups_with_pending))}. Completa todos los partidos primero."
            request.session["flash_type"] = "error"
            return RedirectResponse(url=f"/admin/manual-bracket/{category}", status_code=303)

        # Get form data
        form_data = await request.form()

        # Parse slot assignments (slot_1=player_id, slot_2=BYE, etc.)
        slot_assignments = {}
        bye_slots = set()
        for key, value in form_data.items():
            if key.startswith("slot_") and value:
                slot_num = int(key.replace("slot_", ""))
                if value == "BYE":
                    bye_slots.add(slot_num)
                else:
                    try:
                        player_id = int(value)
                        slot_assignments[slot_num] = player_id
                    except ValueError:
                        pass  # Skip invalid values

        if not slot_assignments:
            request.session["flash_message"] = "Debes asignar al menos un jugador al bracket"
            request.session["flash_type"] = "error"
            # Save form state to preserve user's work
            request.session["bracket_form_data"] = dict(form_data)
            return RedirectResponse(url=f"/admin/manual-bracket/{category}", status_code=303)

        # Determine bracket size
        all_slots = set(slot_assignments.keys()) | bye_slots
        max_slot = max(all_slots) if all_slots else 1
        bracket_size = 2 ** math.ceil(math.log2(max_slot)) if max_slot > 0 else 2

        # Determine round type
        if bracket_size == 2:
            round_type = RoundType.FINAL
        elif bracket_size == 4:
            round_type = RoundType.SEMIFINAL
        elif bracket_size == 8:
            round_type = RoundType.QUARTERFINAL
        elif bracket_size == 16:
            round_type = RoundType.ROUND_OF_16
        else:
            round_type = RoundType.ROUND_OF_32

        # Validate same-group constraint
        # Build player -> group_id mapping (filtered by tournament via group_id)
        current_group_ids = set(g.id for g in groups)
        player_to_group = {}
        all_standings = standing_repo.get_all()
        for standing_orm in all_standings:
            # Only include standings from current tournament's groups
            if standing_orm.group_id not in current_group_ids:
                continue
            player_orm = player_repo.get_by_id(standing_orm.player_id)
            if player_orm and player_orm.categoria == category:
                player_to_group[standing_orm.player_id] = standing_orm.group_id

        # Check same-group in same half
        half_point = bracket_size // 2
        top_half_players = []
        bottom_half_players = []

        for slot_num, player_id in slot_assignments.items():
            if slot_num <= half_point:
                top_half_players.append(player_id)
            else:
                bottom_half_players.append(player_id)

        # Check for violations
        violations = []

        # Check top half
        groups_in_top = [player_to_group.get(pid) for pid in top_half_players if pid in player_to_group]
        if len(groups_in_top) != len(set(groups_in_top)):
            violations.append("Hay jugadores del mismo grupo en la mitad superior del bracket")

        # Check bottom half
        groups_in_bottom = [player_to_group.get(pid) for pid in bottom_half_players if pid in player_to_group]
        if len(groups_in_bottom) != len(set(groups_in_bottom)):
            violations.append("Hay jugadores del mismo grupo en la mitad inferior del bracket")

        if violations:
            request.session["flash_message"] = "; ".join(violations)
            request.session["flash_type"] = "error"
            # Save form state to preserve user's work
            request.session["bracket_form_data"] = dict(form_data)
            return RedirectResponse(url=f"/admin/manual-bracket/{category}", status_code=303)

        # Create bracket slots
        bracket_repo.delete_by_category(category, tournament_id=tournament_id)  # Clear old bracket

        # Create slots for first round (R16, R32, etc.) with players/BYEs
        for slot_num in range(1, bracket_size + 1):
            player_id = slot_assignments.get(slot_num)
            is_bye = slot_num in bye_slots or player_id is None

            slot = BracketSlot(
                slot_number=slot_num,
                round_type=round_type,
                player_id=player_id,
                is_bye=is_bye,
                same_country_warning=False
            )
            bracket_repo.create_slot(slot, category, tournament_id=tournament_id)

        # Create empty slots for subsequent rounds (QF, SF, F, etc.)
        # This is necessary for process_bye_advancements and winner advancement to work
        round_progression = {
            RoundType.ROUND_OF_128: (RoundType.ROUND_OF_64, 64),
            RoundType.ROUND_OF_64: (RoundType.ROUND_OF_32, 32),
            RoundType.ROUND_OF_32: (RoundType.ROUND_OF_16, 16),
            RoundType.ROUND_OF_16: (RoundType.QUARTERFINAL, 8),
            RoundType.QUARTERFINAL: (RoundType.SEMIFINAL, 4),
            RoundType.SEMIFINAL: (RoundType.FINAL, 2),
        }

        current_round = round_type
        while current_round in round_progression:
            next_round, next_size = round_progression[current_round]
            for slot_num in range(1, next_size + 1):
                slot = BracketSlot(
                    slot_number=slot_num,
                    round_type=next_round,
                    player_id=None,
                    is_bye=False,
                    same_country_warning=False
                )
                bracket_repo.create_slot(slot, category, tournament_id=tournament_id)
            current_round = next_round

        # Annotate same-country warnings
        # Check adjacent pairs
        for i in range(1, bracket_size, 2):
            slot1_player_id = slot_assignments.get(i)
            slot2_player_id = slot_assignments.get(i + 1)

            if slot1_player_id and slot2_player_id:
                player1 = player_repo.get_by_id(slot1_player_id)
                player2 = player_repo.get_by_id(slot2_player_id)

                if player1 and player2 and player1.pais_cd == player2.pais_cd:
                    # Update slots with warning
                    bracket_repo.update_slot_warning(category, round_type, i, True)
                    bracket_repo.update_slot_warning(category, round_type, i + 1, True)

        # Delete existing bracket matches for this category before creating new ones
        match_repo = MatchRepository(session)
        existing_matches = match_repo.get_all()
        for match_orm in existing_matches:
            if match_orm.group_id is None:  # Bracket match
                if match_orm.player1_id:
                    player = session.query(PlayerORM).filter(PlayerORM.id == match_orm.player1_id).first()
                    if player and player.categoria == category:
                        session.delete(match_orm)
                elif match_orm.player2_id:
                    player = session.query(PlayerORM).filter(PlayerORM.id == match_orm.player2_id).first()
                    if player and player.categoria == category:
                        session.delete(match_orm)
        session.commit()

        # Create matches from bracket slots
        matches_created = create_bracket_matches(category, bracket_repo, match_repo, tournament_id=tournament_id)

        # Process BYE advancements (and delete BYE matches)
        process_bye_advancements(category, bracket_repo, session, tournament_id=tournament_id, match_repo=match_repo)

        # Sync matches with updated slots
        sync_bracket_matches_with_slots(category, bracket_repo, match_repo, session, tournament_id=tournament_id)

        request.session["flash_message"] = f"Bracket manual guardado: {matches_created} partidos creados"
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/bracket/{category}", status_code=303)

    except Exception as e:
        request.session["flash_message"] = f"Error al guardar bracket: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url=f"/admin/manual-bracket/{category}", status_code=303)


# ==============================================================================
# PDF GENERATION ROUTES
# ==============================================================================


def get_tournament_name() -> str:
    """Get current tournament name for PDF headers."""
    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()
        if tournament:
            return tournament.name
        return "Torneo de Tenis de Mesa"


@app.get("/print/match/{match_id}")
async def print_match_sheet(match_id: int):
    """Generate PDF for a single match sheet."""
    with get_db_session() as session:
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        group_repo = GroupRepository(session)

        match_orm = match_repo.get_by_id(match_id)
        if not match_orm:
            return Response(content="Partido no encontrado", status_code=404)

        player1 = player_repo.get_by_id(match_orm.player1_id)
        player2 = player_repo.get_by_id(match_orm.player2_id)

        if not player1 or not player2:
            return Response(content="Jugadores no encontrados", status_code=404)

        # Get group name and calculate round number if this is a group match
        group_name = None
        round_number = None
        if match_orm.group_id:
            group = group_repo.get_by_id(match_orm.group_id)
            if group:
                group_name = group.name

                # Calculate round number
                all_players = player_repo.get_all()
                players_in_group = [p for p in all_players if p.group_id == match_orm.group_id]
                num_players = len(players_in_group)
                matches_per_round = max(1, num_players // 2)

                # Get all matches in this group to find the index
                all_group_matches = match_repo.get_by_group(match_orm.group_id)
                all_group_matches = sorted(all_group_matches, key=lambda m: m.match_number or 999)
                for idx, gm in enumerate(all_group_matches):
                    if gm.id == match_orm.id:
                        round_number = (idx // matches_per_round) + 1
                        break

        # Build match dict
        match_dict = {
            "id": match_orm.id,
            "match_order": match_orm.match_number,
            "round_type": match_orm.round_type,
        }

        # Build player dicts
        p1_dict = {
            "nombre": player1.nombre,
            "apellido": player1.apellido,
            "pais_cd": player1.pais_cd,
        }
        p2_dict = {
            "nombre": player2.nombre,
            "apellido": player2.apellido,
            "pais_cd": player2.pais_cd,
        }

        try:
            pdf_bytes = pdf_generator.generate_match_sheet_pdf(
                match=match_dict,
                player1=p1_dict,
                player2=p2_dict,
                group_name=group_name,
                tournament_name=get_tournament_name(),
                category=player1.categoria,
                round_number=round_number,
            )

            filename = f"partido_{match_id}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        except Exception as e:
            return Response(content=f"Error generando PDF: {str(e)}", status_code=500)


@app.get("/print/group/{group_id}/sheet")
async def print_group_sheet(group_id: int):
    """Generate PDF for a group sheet (matrix + matches)."""
    with get_db_session() as session:
        group_repo = GroupRepository(session)
        player_repo = PlayerRepository(session)
        match_repo = MatchRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)

        group = group_repo.get_by_id(group_id)
        if not group:
            return Response(content="Grupo no encontrado", status_code=404)

        event_type = detect_event_type(group.category)

        # Get entities in group (players, pairs, or teams depending on event type)
        if event_type == "teams":
            all_teams = team_repo.get_all()
            players_orm = [t for t in all_teams if t.group_id == group_id]
        elif event_type == "doubles":
            all_pairs = pair_repo.get_all()
            players_orm = [p for p in all_pairs if getattr(p, 'group_id', None) == group_id]
        else:
            all_players = player_repo.get_all()
            players_orm = [p for p in all_players if p.group_id == group_id]
        players_orm = sorted(players_orm, key=lambda p: p.group_number or 999)

        # Get matches
        matches_orm = match_repo.get_by_group(group_id)
        matches_orm = sorted(matches_orm, key=lambda m: m.match_number or 999)

        # Initialize player stats
        player_stats = {}
        for p in players_orm:
            player_stats[p.id] = {
                "wins": 0,
                "losses": 0,
                "sets_won": 0,
                "sets_lost": 0,
                "points": 0,
            }

        # Build results matrix from actual match results
        results_matrix = {}
        for p in players_orm:
            results_matrix[p.id] = {}

        # Build matches with player info and results
        from ettem.webapp.helpers import get_competitor_display
        matches = []
        for m in matches_orm:
            cd1 = get_competitor_display(m, 1, player_repo, pair_repo=pair_repo, team_repo=team_repo)
            cd2 = get_competitor_display(m, 2, player_repo, pair_repo=pair_repo, team_repo=team_repo)

            # Calculate result from sets
            result = None
            if m.sets and len(m.sets) > 0:
                sets_p1 = sum(1 for s in m.sets if s.get('player1_points', 0) > s.get('player2_points', 0))
                sets_p2 = sum(1 for s in m.sets if s.get('player2_points', 0) > s.get('player1_points', 0))
                result = f"{sets_p1}-{sets_p2}"
                # Fill results matrix (both directions)
                if m.player1_id in results_matrix:
                    results_matrix[m.player1_id][m.player2_id] = f"{sets_p1}-{sets_p2}"
                if m.player2_id in results_matrix:
                    results_matrix[m.player2_id][m.player1_id] = f"{sets_p2}-{sets_p1}"

                # Update player stats
                if m.player1_id in player_stats:
                    player_stats[m.player1_id]["sets_won"] += sets_p1
                    player_stats[m.player1_id]["sets_lost"] += sets_p2
                if m.player2_id in player_stats:
                    player_stats[m.player2_id]["sets_won"] += sets_p2
                    player_stats[m.player2_id]["sets_lost"] += sets_p1

                # Determine winner and update wins/losses/points
                if m.winner_id:
                    if m.winner_id in player_stats:
                        player_stats[m.winner_id]["wins"] += 1
                        player_stats[m.winner_id]["points"] += 2
                    loser_id = m.player2_id if m.winner_id == m.player1_id else m.player1_id
                    if loser_id in player_stats:
                        player_stats[loser_id]["losses"] += 1
                        # 1 point for playing (not walkover)
                        if m.status != "WALKOVER":
                            player_stats[loser_id]["points"] += 1

            # Determine winner's group number
            winner_group_number = None
            if m.winner_id:
                p1_orm = player_repo.get_by_id(m.player1_id)
                p2_orm = player_repo.get_by_id(m.player2_id)
                if m.winner_id == m.player1_id and p1_orm:
                    winner_group_number = p1_orm.group_number
                elif m.winner_id == m.player2_id and p2_orm:
                    winner_group_number = p2_orm.group_number

            matches.append({
                "match_order": m.match_number,
                "result": result,
                "winner_group_number": winner_group_number,
                "player1": {"nombre": cd1.nombre, "apellido": cd1.apellido},
                "player2": {"nombre": cd2.nombre, "apellido": cd2.apellido},
            })

        # Build player dicts with stats
        players = []
        for p in players_orm:
            stats = player_stats.get(p.id, {})
            # Calculate ratios for tiebreaker
            sets_won = stats.get("sets_won", 0)
            sets_lost = stats.get("sets_lost", 0)
            sets_ratio = sets_won / sets_lost if sets_lost > 0 else (float('inf') if sets_won > 0 else 0)

            # Resolve display name (team/pair-aware)
            if event_type == "teams" and team_repo:
                team_orm = team_repo.get_by_id(p.id)
                display_nombre = team_orm.name if team_orm else p.nombre
                display_apellido = ""
                display_pais = (team_orm.pais_cd if team_orm else p.pais_cd) or p.pais_cd
            elif event_type == "doubles" and pair_repo:
                pair_orm = pair_repo.get_by_id(p.id)
                if pair_orm:
                    p1_d = player_repo.get_by_id(pair_orm.player1_id)
                    p2_d = player_repo.get_by_id(pair_orm.player2_id)
                    cd = CompetitorDisplay.from_pair(pair_orm, p1_d, p2_d)
                    display_nombre = cd.nombre
                    display_apellido = cd.apellido
                    display_pais = cd.pais_cd
                else:
                    display_nombre = p.nombre
                    display_apellido = p.apellido
                    display_pais = p.pais_cd
            else:
                display_nombre = p.nombre
                display_apellido = p.apellido
                display_pais = p.pais_cd

            players.append({
                "player": {
                    "id": p.id,
                    "nombre": display_nombre,
                    "apellido": display_apellido,
                    "pais_cd": display_pais,
                    "group_number": p.group_number,
                },
                "stats": {
                    "points": stats.get("points", 0),
                    "wins": stats.get("wins", 0),
                    "losses": stats.get("losses", 0),
                    "sets_won": sets_won,
                    "sets_lost": sets_lost,
                    "sets_ratio": sets_ratio,
                    "position": None,
                }
            })

        # Calculate positions based on points and tiebreakers
        players_with_matches = [p for p in players if p["stats"]["wins"] + p["stats"]["losses"] > 0]
        if players_with_matches:
            sorted_players = sorted(
                players_with_matches,
                key=lambda x: (-x["stats"]["points"], -x["stats"]["sets_ratio"], x["player"]["group_number"])
            )
            for pos, p in enumerate(sorted_players, 1):
                for orig_p in players:
                    if orig_p["player"]["id"] == p["player"]["id"]:
                        orig_p["stats"]["position"] = pos
                        break

        try:
            pdf_bytes = pdf_generator.generate_group_sheet_pdf(
                group={"name": f"Grupo {group.name}"},
                players=players,
                matches=matches,
                results_matrix=results_matrix,
                tournament_name=get_tournament_name(),
                category=group.category,
            )

            filename = f"grupo_{group.name.replace(' ', '_')}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        except Exception as e:
            return Response(content=f"Error generando PDF: {str(e)}", status_code=500)


@app.get("/print/group/{group_id}/matches")
async def print_group_matches(group_id: int):
    """Generate PDF for group match list."""
    with get_db_session() as session:
        group_repo = GroupRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        match_repo = MatchRepository(session)
        schedule_repo = ScheduleSlotRepository(session)
        from ettem.webapp.helpers import get_competitor_display
        from ettem.models import is_doubles_category

        group = group_repo.get_by_id(group_id)
        if not group:
            return Response(content="Grupo no encontrado", status_code=404)

        _is_doubles = is_doubles_category(group.category)

        # Get matches
        matches_orm = match_repo.get_by_group(group_id)
        matches_orm = sorted(matches_orm, key=lambda m: m.match_number or 999)

        # Build matches with player info
        matches = []
        for m in matches_orm:
            p1 = get_competitor_display(m, 1, player_repo, pair_repo, team_repo)
            p2 = get_competitor_display(m, 2, player_repo, pair_repo, team_repo)

            # Get schedule info
            schedule_slot = schedule_repo.get_by_match(m.id)
            table_number = schedule_slot.table_number if schedule_slot else None
            scheduled_time = schedule_slot.start_time if schedule_slot else None

            # Calculate result from sets
            result = None
            if m.sets and len(m.sets) > 0:
                sets_p1 = sum(1 for s in m.sets if s.get('player1_points', 0) > s.get('player2_points', 0))
                sets_p2 = sum(1 for s in m.sets if s.get('player2_points', 0) > s.get('player1_points', 0))
                result = f"{sets_p1} - {sets_p2}"

            matches.append({
                "match_order": m.match_number,
                "status": m.status,
                "result": result,
                "table_number": table_number,
                "scheduled_time": scheduled_time,
                "player1": {
                    "nombre": p1.full_name if _is_doubles else p1.nombre,
                    "apellido": "" if _is_doubles else p1.apellido,
                    "pais_cd": p1.pais_cd,
                },
                "player2": {
                    "nombre": p2.full_name if _is_doubles else p2.nombre,
                    "apellido": "" if _is_doubles else p2.apellido,
                    "pais_cd": p2.pais_cd,
                },
            })

        try:
            pdf_bytes = pdf_generator.generate_match_list_pdf(
                matches=matches,
                title=f"Partidos - Grupo {group.name}",
                tournament_name=get_tournament_name(),
                category=group.category,
                group_name=f"Grupo {group.name}",
            )

            filename = f"partidos_grupo_{group.name.replace(' ', '_')}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        except Exception as e:
            return Response(content=f"Error generando PDF: {str(e)}", status_code=500)


@app.get("/print/group/{group_id}/all-match-sheets")
async def print_all_group_match_sheets(group_id: int):
    """Generate PDF with all match sheets for a group (one per page)."""
    with get_db_session() as session:
        group_repo = GroupRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        match_repo = MatchRepository(session)
        schedule_repo = ScheduleSlotRepository(session)
        from ettem.webapp.helpers import get_competitor_display
        from ettem.models import is_doubles_category

        group = group_repo.get_by_id(group_id)
        if not group:
            return Response(content="Grupo no encontrado", status_code=404)

        _is_doubles = is_doubles_category(group.category)

        # Get matches
        matches_orm = match_repo.get_by_group(group_id)
        matches_orm = sorted(matches_orm, key=lambda m: m.match_number or 999)

        # Get number of players in group to calculate rounds
        all_players = player_repo.get_all()
        players_in_group = [p for p in all_players if p.group_id == group_id]
        num_players = len(players_in_group)
        matches_per_round = max(1, num_players // 2)

        # Build matches data
        matches_data = []
        for idx, m in enumerate(matches_orm):
            p1 = get_competitor_display(m, 1, player_repo, pair_repo, team_repo)
            p2 = get_competitor_display(m, 2, player_repo, pair_repo, team_repo)

            # Get schedule info
            schedule_slot = schedule_repo.get_by_match(m.id)
            table_number = schedule_slot.table_number if schedule_slot else None
            scheduled_time = schedule_slot.start_time if schedule_slot else None

            # Calculate round number (1-based)
            round_number = (idx // matches_per_round) + 1

            matches_data.append({
                "match": {
                    "id": m.id,
                    "match_order": m.match_number,
                    "round_type": m.round_type,
                },
                "player1": {
                    "nombre": p1.full_name if _is_doubles else p1.nombre,
                    "apellido": "" if _is_doubles else p1.apellido,
                    "pais_cd": p1.pais_cd,
                },
                "player2": {
                    "nombre": p2.full_name if _is_doubles else p2.nombre,
                    "apellido": "" if _is_doubles else p2.apellido,
                    "pais_cd": p2.pais_cd,
                },
                "group_name": group.name,
                "round_number": round_number,
                "table_number": table_number,
                "scheduled_time": scheduled_time,
            })

        try:
            pdf_bytes = pdf_generator.generate_all_match_sheets_pdf(
                matches_data=matches_data,
                tournament_name=get_tournament_name(),
                category=group.category,
                is_doubles=_is_doubles,
            )

            filename = f"hojas_partido_{group.name.replace(' ', '_')}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        except Exception as e:
            return Response(content=f"Error generando PDF: {str(e)}", status_code=500)


@app.get("/print/category/{category}/all-match-sheets")
async def print_all_category_match_sheets(category: str):
    """Generate PDF with all match sheets for a category (groups only)."""
    with get_db_session() as session:
        group_repo = GroupRepository(session)
        player_repo = PlayerRepository(session)
        match_repo = MatchRepository(session)
        tournament_repo = TournamentRepository(session)
        schedule_repo = ScheduleSlotRepository(session)

        tournament = tournament_repo.get_current()
        tournament_id = tournament.id if tournament else None

        # Get all groups in category
        groups = group_repo.get_by_category(category, tournament_id=tournament_id)
        if not groups:
            return Response(content="No hay grupos en esta categoría", status_code=404)

        # Get all players once
        all_players = player_repo.get_all()

        # Build all matches data
        matches_data = []
        for group in sorted(groups, key=lambda g: int(g.name) if g.name.isdigit() else g.name):
            matches_orm = match_repo.get_by_group(group.id)
            matches_orm = sorted(matches_orm, key=lambda m: m.match_number or 999)

            # Get number of players in this group to calculate rounds
            players_in_group = [p for p in all_players if p.group_id == group.id]
            num_players = len(players_in_group)
            matches_per_round = max(1, num_players // 2)

            for idx, m in enumerate(matches_orm):
                p1 = player_repo.get_by_id(m.player1_id)
                p2 = player_repo.get_by_id(m.player2_id)

                # Get schedule info
                schedule_slot = schedule_repo.get_by_match(m.id)
                table_number = schedule_slot.table_number if schedule_slot else None
                scheduled_time = schedule_slot.start_time if schedule_slot else None

                # Calculate round number (1-based)
                round_number = (idx // matches_per_round) + 1

                matches_data.append({
                    "match": {
                        "id": m.id,
                        "match_order": m.match_number,
                        "round_type": m.round_type,
                    },
                    "player1": {
                        "nombre": p1.nombre if p1 else "?",
                        "apellido": p1.apellido if p1 else "?",
                        "pais_cd": p1.pais_cd if p1 else "?",
                    },
                    "player2": {
                        "nombre": p2.nombre if p2 else "?",
                        "apellido": p2.apellido if p2 else "?",
                        "pais_cd": p2.pais_cd if p2 else "?",
                    },
                    "group_name": group.name,
                    "round_number": round_number,
                    "table_number": table_number,
                    "scheduled_time": scheduled_time,
                })

        if not matches_data:
            return Response(content="No hay partidos en esta categoría", status_code=404)

        try:
            pdf_bytes = pdf_generator.generate_all_match_sheets_pdf(
                matches_data=matches_data,
                tournament_name=get_tournament_name(),
                category=category,
            )

            filename = f"hojas_partido_{category}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        except Exception as e:
            return Response(content=f"Error generando PDF: {str(e)}", status_code=500)


# =============================================================================
# TOURNAMENT STATUS ROUTE
# =============================================================================

@app.get("/tournament-status", response_class=HTMLResponse)
async def tournament_status(request: Request):
    """Show consolidated tournament status."""
    from ettem.models import RoundType, is_doubles_category, is_teams_category
    from ettem.webapp.helpers import get_champion_display

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        group_repo = GroupRepository(session)
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        bracket_repo = BracketRepository(session)
        standing_repo = StandingRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)

        current_tournament = tournament_repo.get_current()
        if not current_tournament:
            return render_template("tournament_status.html", {
                "request": request,
                "tournament": None,
                "categories_status": {}
            })

        tournament_id = current_tournament.id

        # Get all categories from groups, players, pairs, AND teams
        all_groups = group_repo.get_all(tournament_id=tournament_id)
        group_categories = set(g.category for g in all_groups)

        all_players = player_repo.get_all(tournament_id=tournament_id)
        player_categories = set(p.categoria for p in all_players if not is_doubles_category(p.categoria) and not is_teams_category(p.categoria))

        all_pairs = pair_repo.get_all(tournament_id=tournament_id)
        pair_categories = set(p.categoria for p in all_pairs)

        all_teams = team_repo.get_by_tournament(tournament_id)
        team_categories = set(t.categoria for t in all_teams)

        categories = sorted(group_categories | player_categories | pair_categories | team_categories)

        categories_status = {}
        for category in categories:
            cat_groups = [g for g in all_groups if g.category == category]
            _is_doubles = is_doubles_category(category)
            _is_teams = is_teams_category(category)

            # Competitor count
            if _is_teams:
                cat_competitors = [t for t in all_teams if t.categoria == category]
                competitor_count = len(cat_competitors)
                competitor_unit = "equipos"
            elif _is_doubles:
                cat_competitors = [p for p in all_pairs if p.categoria == category]
                competitor_count = len(cat_competitors)
                competitor_unit = "parejas"
            else:
                cat_competitors = [p for p in all_players if p.categoria == category]
                competitor_count = len(cat_competitors)
                competitor_unit = "jugadores"

            # Group stage status
            total_group_matches = 0
            completed_group_matches = 0
            for group in cat_groups:
                group_matches = match_repo.get_by_group(group.id)
                total_group_matches += len(group_matches)
                completed_group_matches += sum(1 for m in group_matches if m.status != "pending")

            groups_complete = total_group_matches > 0 and completed_group_matches == total_group_matches

            # Standings status
            has_standings = False
            for group in cat_groups:
                standings = standing_repo.get_by_group(group.id)
                if standings:
                    has_standings = True
                    break

            # Bracket status
            bracket_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
            has_bracket = len(bracket_slots) > 0

            # Bracket matches status
            bracket_matches = []
            champion = None
            rounds_status = {}

            if has_bracket:
                all_matches = match_repo.get_all()
                for m in all_matches:
                    if m.group_id is None and m.tournament_id == tournament_id:
                        # Use match's category field directly (avoids player/pair/team lookup issues)
                        if hasattr(m, 'category') and m.category == category:
                            bracket_matches.append(m)

                # Group by round
                round_order = [
                    (RoundType.ROUND_OF_32.value, "Ronda de 32"),
                    (RoundType.ROUND_OF_16.value, "Ronda de 16"),
                    (RoundType.QUARTERFINAL.value, "Cuartos de Final"),
                    (RoundType.SEMIFINAL.value, "Semifinales"),
                    (RoundType.FINAL.value, "Final"),
                ]

                for round_type, round_name in round_order:
                    round_matches = [m for m in bracket_matches if m.round_type == round_type]
                    if round_matches:
                        total = len(round_matches)
                        completed = sum(1 for m in round_matches if m.status != "pending")
                        rounds_status[round_name] = {
                            "total": total,
                            "completed": completed,
                            "complete": total == completed
                        }

                # Check for champion
                final_matches = [m for m in bracket_matches if m.round_type == RoundType.FINAL.value]
                if final_matches and final_matches[0].winner_id:
                    champion = get_champion_display(final_matches[0].winner_id, category, player_repo, pair_repo, team_repo=team_repo)

            # Determine phase
            if has_bracket:
                phase = "bracket"
            elif cat_groups:
                phase = "groups"
            else:
                phase = "inscripcion"

            categories_status[category] = {
                "competitors": competitor_count,
                "competitor_unit": competitor_unit,
                "phase": phase,
                "groups": {
                    "count": len(cat_groups),
                    "total_matches": total_group_matches,
                    "completed_matches": completed_group_matches,
                    "complete": groups_complete
                },
                "standings": has_standings,
                "bracket": {
                    "exists": has_bracket,
                    "rounds": rounds_status
                },
                "champion": champion
            }

        return render_template("tournament_status.html", {
            "request": request,
            "tournament": current_tournament,
            "categories_status": categories_status
        })


# =============================================================================
# CSV EXPORT ROUTES
# =============================================================================

@app.get("/export/bracket/{category}")
async def export_bracket_csv(category: str):
    """Export bracket matches to CSV."""
    import csv
    import io
    from ettem.models import RoundType

    with get_db_session() as session:
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)

        # Get all bracket matches for this category
        all_matches = match_repo.get_all()
        bracket_matches = []

        for m in all_matches:
            if m.group_id is None:  # Bracket match
                if m.player1_id:
                    player = player_repo.get_by_id(m.player1_id)
                    if player and player.categoria == category:
                        bracket_matches.append(m)
                elif m.player2_id:
                    player = player_repo.get_by_id(m.player2_id)
                    if player and player.categoria == category:
                        bracket_matches.append(m)

        # Sort by round order then match number
        round_order = {
            RoundType.ROUND_OF_32.value: 1,
            RoundType.ROUND_OF_16.value: 2,
            RoundType.QUARTERFINAL.value: 3,
            RoundType.SEMIFINAL.value: 4,
            RoundType.FINAL.value: 5,
        }
        bracket_matches.sort(key=lambda m: (round_order.get(m.round_type, 99), m.match_number or 0))

        # Round display names
        round_names = {
            RoundType.ROUND_OF_32.value: "Ronda de 32",
            RoundType.ROUND_OF_16.value: "Ronda de 16",
            RoundType.QUARTERFINAL.value: "Cuartos de Final",
            RoundType.SEMIFINAL.value: "Semifinales",
            RoundType.FINAL.value: "Final",
        }

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["Ronda", "Partido", "Jugador 1", "Jugador 2", "Ganador", "Sets", "Estado"])

        for m in bracket_matches:
            player1 = player_repo.get_by_id(m.player1_id) if m.player1_id else None
            player2 = player_repo.get_by_id(m.player2_id) if m.player2_id else None
            winner = player_repo.get_by_id(m.winner_id) if m.winner_id else None

            player1_name = f"{player1.nombre} {player1.apellido}" if player1 else "TBD"
            player2_name = f"{player2.nombre} {player2.apellido}" if player2 else "TBD"
            winner_name = f"{winner.nombre} {winner.apellido}" if winner else "-"

            # Parse sets
            sets_str = "-"
            if m.sets_json:
                import json
                sets = json.loads(m.sets_json)
                if sets:
                    p1_sets = sum(1 for s in sets if s.get("player1_points", 0) > s.get("player2_points", 0))
                    p2_sets = sum(1 for s in sets if s.get("player2_points", 0) > s.get("player1_points", 0))
                    sets_str = f"{p1_sets}-{p2_sets}"

            # Status
            status_map = {
                "pending": "Pendiente",
                "completed": "Completado",
                "WALKOVER": "Walkover",
            }
            status = status_map.get(m.status, m.status)

            writer.writerow([
                round_names.get(m.round_type, m.round_type),
                m.match_number or "-",
                player1_name,
                player2_name,
                winner_name,
                sets_str,
                status
            ])

        # Return CSV response with BOM for Excel UTF-8 compatibility
        csv_content = output.getvalue()
        filename = f"bracket_{category}.csv"
        csv_bytes = ('\ufeff' + csv_content).encode('utf-8')

        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


@app.get("/export/standings/{category}")
async def export_standings_csv(category: str):
    """Export standings to CSV."""
    import csv
    import io

    with get_db_session() as session:
        standing_repo = StandingRepository(session)
        player_repo = PlayerRepository(session)
        group_repo = GroupRepository(session)

        # Get all groups for this category
        groups = group_repo.get_by_category(category)

        if not groups:
            return Response(content="No hay grupos para esta categoría", status_code=404)

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["Grupo", "Posición", "Jugador", "País", "Puntos", "V", "D", "Sets+", "Sets-", "Pts+", "Pts-"])

        for group in groups:
            standings = standing_repo.get_by_group(group.id)
            for s in standings:
                player = player_repo.get_by_id(s.player_id)

                writer.writerow([
                    group.name if group else "-",
                    s.position,
                    f"{player.nombre} {player.apellido}" if player else "-",
                    player.pais_cd if player else "-",
                    s.points_total,
                    s.wins,
                    s.losses,
                    s.sets_w,
                    s.sets_l,
                    s.points_w,
                    s.points_l
                ])

        csv_content = output.getvalue()
        filename = f"standings_{category}.csv"

        # Add BOM for Excel UTF-8 compatibility
        csv_bytes = ('\ufeff' + csv_content).encode('utf-8')

        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


@app.get("/admin/print-center", response_class=HTMLResponse)
async def admin_print_center(request: Request):
    """Print center page with all print options."""
    with get_db_session() as session:
        group_repo = GroupRepository(session)
        tournament_repo = TournamentRepository(session)
        bracket_repo = BracketRepository(session)
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)

        tournament = tournament_repo.get_current()
        tournament_id = tournament.id if tournament else None

        # Get all groups organized by category
        all_groups = group_repo.get_all(tournament_id=tournament_id)

        # Organize by category
        categories_groups = {}
        for group in all_groups:
            if group.category not in categories_groups:
                categories_groups[group.category] = []
            categories_groups[group.category].append({
                "id": group.id,
                "name": group.name,
            })

        # Sort groups within each category
        for cat in categories_groups:
            categories_groups[cat] = sorted(categories_groups[cat], key=lambda g: g["name"])

        # Get bracket matches by category, grouped by round
        # Include ALL categories with brackets (not just those with groups — KO Directo has no groups)
        categories_brackets = {}
        bracket_categories = set()
        all_bracket_slots = bracket_repo.get_all(tournament_id=tournament_id)
        for slot in all_bracket_slots:
            if slot.category:
                bracket_categories.add(slot.category)

        all_bracket_matches = []
        for m in match_repo.get_all():
            if m.group_id is None and m.category in bracket_categories and m.tournament_id == tournament_id:
                all_bracket_matches.append(m)

        # Round display names
        round_names = {
            "R128": "Ronda de 128",
            "R64": "Ronda de 64",
            "R32": "Ronda de 32",
            "R16": "Octavos de Final",
            "QF": "Cuartos de Final",
            "SF": "Semifinal",
            "F": "Final",
        }
        round_order = {"R128": 0, "R64": 1, "R32": 2, "R16": 3, "QF": 4, "SF": 5, "F": 6}

        for match_orm in all_bracket_matches:
            # Use the match's stored category directly (already filtered)
            category = match_orm.category
            if not category:
                continue

            if category not in categories_brackets:
                categories_brackets[category] = {"rounds": {}, "total_matches": 0}

            round_type = match_orm.round_type
            if round_type not in categories_brackets[category]["rounds"]:
                categories_brackets[category]["rounds"][round_type] = {
                    "name": round_names.get(round_type, round_type),
                    "order": round_order.get(round_type, 99),
                    "matches": [],
                }

            # Get competitor names (handle singles, doubles, and teams)
            from ettem.models import is_doubles_category, is_teams_category
            p1_name = "TBD"
            p2_name = "TBD"
            is_ready = False  # Match is ready to play (both competitors known)

            is_doubles = is_doubles_category(category)
            is_teams = is_teams_category(category)
            if is_teams and match_orm.team1_id:
                team1 = team_repo.get_by_id(match_orm.team1_id)
                if team1:
                    p1_name = team1.name
            elif is_doubles and match_orm.pair1_id:
                pair1 = pair_repo.get_by_id(match_orm.pair1_id)
                if pair1:
                    pl1 = player_repo.get_by_id(pair1.player1_id)
                    pl2 = player_repo.get_by_id(pair1.player2_id)
                    p1_name = f"{pl1.apellido}/{pl2.apellido}" if pl1 and pl2 else "Pareja"
            elif match_orm.player1_id:
                p1 = player_repo.get_by_id(match_orm.player1_id)
                if p1:
                    p1_name = f"{p1.nombre} {p1.apellido}"

            if is_teams and match_orm.team2_id:
                team2 = team_repo.get_by_id(match_orm.team2_id)
                if team2:
                    p2_name = team2.name
            elif is_doubles and match_orm.pair2_id:
                pair2 = pair_repo.get_by_id(match_orm.pair2_id)
                if pair2:
                    pl1 = player_repo.get_by_id(pair2.player1_id)
                    pl2 = player_repo.get_by_id(pair2.player2_id)
                    p2_name = f"{pl1.apellido}/{pl2.apellido}" if pl1 and pl2 else "Pareja"
            elif match_orm.player2_id:
                p2 = player_repo.get_by_id(match_orm.player2_id)
                if p2:
                    p2_name = f"{p2.nombre} {p2.apellido}"

            if is_teams:
                if match_orm.team1_id and match_orm.team2_id:
                    is_ready = True
            elif is_doubles:
                if match_orm.pair1_id and match_orm.pair2_id:
                    is_ready = True
            else:
                if match_orm.player1_id and match_orm.player2_id:
                    is_ready = True

            categories_brackets[category]["rounds"][round_type]["matches"].append({
                "id": match_orm.id,
                "match_number": match_orm.match_number or 0,
                "round_type": round_type,
                "player1_name": p1_name,
                "player2_name": p2_name,
                "status": match_orm.status,
                "is_ready": is_ready,
            })
            categories_brackets[category]["total_matches"] += 1

        # Sort rounds within each category and matches within each round
        for cat in categories_brackets:
            # Sort rounds by order
            sorted_rounds = dict(sorted(
                categories_brackets[cat]["rounds"].items(),
                key=lambda x: x[1]["order"]
            ))
            # Sort matches within each round by match_number
            for round_type in sorted_rounds:
                sorted_rounds[round_type]["matches"] = sorted(
                    sorted_rounds[round_type]["matches"],
                    key=lambda m: m["match_number"]
                )
            categories_brackets[cat]["rounds"] = sorted_rounds

        context = {
            "request": request,
            "categories_groups": categories_groups,
            "categories_brackets": categories_brackets,
            "tournament_name": tournament.name if tournament else "Sin torneo",
        }

        return render_template("admin_print_center.html", context)


# ==============================================================================
# PREVIEW ROUTES (HTML preview before PDF download)
# ==============================================================================


@app.get("/preview/group/{group_id}/sheet", response_class=HTMLResponse)
async def preview_group_sheet(request: Request, group_id: int):
    """Preview group sheet before PDF download."""
    with get_db_session() as session:
        group_repo = GroupRepository(session)
        player_repo = PlayerRepository(session)
        match_repo = MatchRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)

        group = group_repo.get_by_id(group_id)
        if not group:
            return Response(content="Grupo no encontrado", status_code=404)

        event_type = detect_event_type(group.category)

        # Get entities in group (players, pairs, or teams depending on event type)
        if event_type == "teams":
            all_teams = team_repo.get_all()
            players_orm = [t for t in all_teams if t.group_id == group_id]
        elif event_type == "doubles":
            all_pairs = pair_repo.get_all()
            players_orm = [p for p in all_pairs if getattr(p, 'group_id', None) == group_id]
        else:
            all_players = player_repo.get_all()
            players_orm = [p for p in all_players if p.group_id == group_id]
        players_orm = sorted(players_orm, key=lambda p: p.group_number or 999)

        # Get matches
        matches_orm = match_repo.get_by_group(group_id)
        matches_orm = sorted(matches_orm, key=lambda m: m.match_number or 999)

        # Initialize player stats (keyed by entity ID: player/pair/team)
        player_stats = {}
        for p in players_orm:
            player_stats[p.id] = {
                "wins": 0,
                "losses": 0,
                "sets_won": 0,
                "sets_lost": 0,
                "points": 0,
            }

        # Build results matrix from actual match results
        # Matrix format: results_matrix[entity1_id][entity2_id] = "3-1" (sets won)
        results_matrix = {}
        for p in players_orm:
            results_matrix[p.id] = {}

        # Build matches with results and calculate stats
        from ettem.webapp.helpers import get_competitor_display
        matches = []
        for m in matches_orm:
            cd1 = get_competitor_display(m, 1, player_repo, pair_repo=pair_repo, team_repo=team_repo)
            cd2 = get_competitor_display(m, 2, player_repo, pair_repo=pair_repo, team_repo=team_repo)

            # Calculate result from sets
            result = None
            if m.sets and len(m.sets) > 0:
                sets_p1 = sum(1 for s in m.sets if s.get('player1_points', 0) > s.get('player2_points', 0))
                sets_p2 = sum(1 for s in m.sets if s.get('player2_points', 0) > s.get('player1_points', 0))
                result = f"{sets_p1}-{sets_p2}"

                # Fill results matrix (both directions)
                if m.player1_id in results_matrix:
                    results_matrix[m.player1_id][m.player2_id] = f"{sets_p1}-{sets_p2}"
                if m.player2_id in results_matrix:
                    results_matrix[m.player2_id][m.player1_id] = f"{sets_p2}-{sets_p1}"

                # Update player stats
                if m.player1_id in player_stats:
                    player_stats[m.player1_id]["sets_won"] += sets_p1
                    player_stats[m.player1_id]["sets_lost"] += sets_p2
                if m.player2_id in player_stats:
                    player_stats[m.player2_id]["sets_won"] += sets_p2
                    player_stats[m.player2_id]["sets_lost"] += sets_p1

                # Determine winner and update wins/losses/points
                if m.winner_id:
                    if m.winner_id in player_stats:
                        player_stats[m.winner_id]["wins"] += 1
                        player_stats[m.winner_id]["points"] += 2
                    loser_id = m.player2_id if m.winner_id == m.player1_id else m.player1_id
                    if loser_id in player_stats:
                        player_stats[loser_id]["losses"] += 1
                        # 1 point for playing (not walkover)
                        if m.status != "WALKOVER":
                            player_stats[loser_id]["points"] += 1

            # Determine winner's group number
            winner_group_number = None
            if m.winner_id:
                p1_orm = player_repo.get_by_id(m.player1_id)
                p2_orm = player_repo.get_by_id(m.player2_id)
                if m.winner_id == m.player1_id and p1_orm:
                    winner_group_number = p1_orm.group_number
                elif m.winner_id == m.player2_id and p2_orm:
                    winner_group_number = p2_orm.group_number

            matches.append({
                "match_order": m.match_number,
                "result": result,
                "winner_group_number": winner_group_number,
                "player1": {"nombre": cd1.nombre, "apellido": cd1.apellido},
                "player2": {"nombre": cd2.nombre, "apellido": cd2.apellido},
            })

        # Build player dicts with stats
        players = []
        for p in players_orm:
            stats = player_stats.get(p.id, {})
            # Calculate ratios for tiebreaker
            sets_won = stats.get("sets_won", 0)
            sets_lost = stats.get("sets_lost", 0)
            sets_ratio = sets_won / sets_lost if sets_lost > 0 else (float('inf') if sets_won > 0 else 0)

            # Resolve display name (team/pair-aware)
            if event_type == "teams" and team_repo:
                team_orm = team_repo.get_by_id(p.id)
                display_nombre = team_orm.name if team_orm else p.nombre
                display_apellido = ""
                display_pais = (team_orm.pais_cd if team_orm else p.pais_cd) or p.pais_cd
            elif event_type == "doubles" and pair_repo:
                pair_orm = pair_repo.get_by_id(p.id)
                if pair_orm:
                    p1_orm = player_repo.get_by_id(pair_orm.player1_id)
                    p2_orm = player_repo.get_by_id(pair_orm.player2_id)
                    cd = CompetitorDisplay.from_pair(pair_orm, p1_orm, p2_orm)
                    display_nombre = cd.nombre
                    display_apellido = cd.apellido
                    display_pais = cd.pais_cd
                else:
                    display_nombre = p.nombre
                    display_apellido = p.apellido
                    display_pais = p.pais_cd
            else:
                display_nombre = p.nombre
                display_apellido = p.apellido
                display_pais = p.pais_cd

            players.append({
                "player": {
                    "id": p.id,
                    "nombre": display_nombre,
                    "apellido": display_apellido,
                    "pais_cd": display_pais,
                    "group_number": p.group_number,
                },
                "stats": {
                    "points": stats.get("points", 0),
                    "wins": stats.get("wins", 0),
                    "losses": stats.get("losses", 0),
                    "sets_won": sets_won,
                    "sets_lost": sets_lost,
                    "sets_ratio": sets_ratio,
                    "position": None,  # Will be calculated below
                }
            })

        # Calculate positions based on points and tiebreakers
        # Only for players who have played at least one match
        players_with_matches = [p for p in players if p["stats"]["wins"] + p["stats"]["losses"] > 0]
        if players_with_matches:
            # Sort by: points (desc), sets_ratio (desc), group_number (asc as tiebreaker)
            sorted_players = sorted(
                players_with_matches,
                key=lambda x: (-x["stats"]["points"], -x["stats"]["sets_ratio"], x["player"]["group_number"])
            )
            # Assign positions
            for pos, p in enumerate(sorted_players, 1):
                # Find this player in the original list and update position
                for orig_p in players:
                    if orig_p["player"]["id"] == p["player"]["id"]:
                        orig_p["stats"]["position"] = pos
                        break

        context = {
            "request": request,
            "preview_title": f"Hoja de Grupo - Grupo {group.name}",
            "back_url": "/admin/print-center",
            "download_url": f"/print/group/{group_id}/sheet",
            "tournament_name": get_tournament_name(),
            "category": group.category,
            "group": {"name": f"Grupo {group.name}"},
            "players": players,
            "matches": matches,
            "results_matrix": results_matrix,
        }

        return render_template("print/preview_group_sheet.html", context)


@app.get("/preview/category/{category}/all-group-sheets", response_class=HTMLResponse)
async def preview_all_group_sheets(request: Request, category: str):
    """Preview all group sheets for a category."""
    with get_db_session() as session:
        group_repo = GroupRepository(session)
        player_repo = PlayerRepository(session)
        match_repo = MatchRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        tournament_repo = TournamentRepository(session)
        schedule_repo = ScheduleSlotRepository(session)

        event_type = detect_event_type(category)

        # Get current tournament
        tournament = tournament_repo.get_current()
        tournament_id = tournament.id if tournament else None
        # Get all groups for the category in current tournament
        all_groups = group_repo.get_all(tournament_id=tournament_id)
        groups_in_category = [g for g in all_groups if g.category == category]
        # Sort numerically (group names are "1", "2", ... "18")
        groups_in_category = sorted(groups_in_category, key=lambda g: int(g.name) if g.name.isdigit() else g.name)

        if not groups_in_category:
            return Response(content="No hay grupos en esta categoría", status_code=404)

        groups_data = []
        for group in groups_in_category:
            # Get entities in group (players, pairs, or teams depending on event type)
            if event_type == "teams":
                all_teams = team_repo.get_all()
                players_orm = [t for t in all_teams if t.group_id == group.id]
            elif event_type == "doubles":
                all_pairs = pair_repo.get_all()
                players_orm = [p for p in all_pairs if getattr(p, 'group_id', None) == group.id]
            else:
                all_players = player_repo.get_all()
                players_orm = [p for p in all_players if p.group_id == group.id]
            players_orm = sorted(players_orm, key=lambda p: p.group_number or 999)

            # Get matches
            matches_orm = match_repo.get_by_group(group.id)
            matches_orm = sorted(matches_orm, key=lambda m: m.match_number or 999)

            # Initialize player stats
            player_stats = {}
            for p in players_orm:
                player_stats[p.id] = {
                    "wins": 0,
                    "losses": 0,
                    "sets_won": 0,
                    "sets_lost": 0,
                    "points": 0,
                }

            # Build results matrix
            results_matrix = {}
            for p in players_orm:
                results_matrix[p.id] = {}

            # Build matches with results and calculate stats
            from ettem.webapp.helpers import get_competitor_display
            matches = []
            for m in matches_orm:
                cd1 = get_competitor_display(m, 1, player_repo, pair_repo=pair_repo, team_repo=team_repo)
                cd2 = get_competitor_display(m, 2, player_repo, pair_repo=pair_repo, team_repo=team_repo)

                result = None
                if m.sets and len(m.sets) > 0:
                    sets_p1 = sum(1 for s in m.sets if s.get('player1_points', 0) > s.get('player2_points', 0))
                    sets_p2 = sum(1 for s in m.sets if s.get('player2_points', 0) > s.get('player1_points', 0))
                    result = f"{sets_p1}-{sets_p2}"

                    if m.player1_id in results_matrix:
                        results_matrix[m.player1_id][m.player2_id] = f"{sets_p1}-{sets_p2}"
                    if m.player2_id in results_matrix:
                        results_matrix[m.player2_id][m.player1_id] = f"{sets_p2}-{sets_p1}"

                    if m.player1_id in player_stats:
                        player_stats[m.player1_id]["sets_won"] += sets_p1
                        player_stats[m.player1_id]["sets_lost"] += sets_p2
                    if m.player2_id in player_stats:
                        player_stats[m.player2_id]["sets_won"] += sets_p2
                        player_stats[m.player2_id]["sets_lost"] += sets_p1

                    if m.winner_id:
                        if m.winner_id in player_stats:
                            player_stats[m.winner_id]["wins"] += 1
                            player_stats[m.winner_id]["points"] += 2
                        loser_id = m.player2_id if m.winner_id == m.player1_id else m.player1_id
                        if loser_id in player_stats:
                            player_stats[loser_id]["losses"] += 1
                            if m.status != "WALKOVER":
                                player_stats[loser_id]["points"] += 1

                # Get schedule info for this match
                schedule_slot = schedule_repo.get_by_match(m.id)
                table_number = schedule_slot.table_number if schedule_slot else None
                scheduled_time = schedule_slot.start_time if schedule_slot else None

                matches.append({
                    "match_order": m.match_number,
                    "result": result,
                    "player1": {"nombre": cd1.nombre, "apellido": cd1.apellido},
                    "player2": {"nombre": cd2.nombre, "apellido": cd2.apellido},
                    "table_number": table_number,
                    "scheduled_time": scheduled_time,
                })

            # Build player dicts with stats
            players = []
            for p in players_orm:
                stats = player_stats.get(p.id, {})
                sets_won = stats.get("sets_won", 0)
                sets_lost = stats.get("sets_lost", 0)
                sets_ratio = sets_won / sets_lost if sets_lost > 0 else (float('inf') if sets_won > 0 else 0)

                # Resolve display name (team/pair-aware)
                if event_type == "teams" and team_repo:
                    team_orm = team_repo.get_by_id(p.id)
                    display_nombre = team_orm.name if team_orm else p.nombre
                    display_apellido = ""
                    display_pais = (team_orm.pais_cd if team_orm else p.pais_cd) or p.pais_cd
                elif event_type == "doubles" and pair_repo:
                    pair_orm = pair_repo.get_by_id(p.id)
                    if pair_orm:
                        p1_d = player_repo.get_by_id(pair_orm.player1_id)
                        p2_d = player_repo.get_by_id(pair_orm.player2_id)
                        cd = CompetitorDisplay.from_pair(pair_orm, p1_d, p2_d)
                        display_nombre = cd.nombre
                        display_apellido = cd.apellido
                        display_pais = cd.pais_cd
                    else:
                        display_nombre = p.nombre
                        display_apellido = p.apellido
                        display_pais = p.pais_cd
                else:
                    display_nombre = p.nombre
                    display_apellido = p.apellido
                    display_pais = p.pais_cd

                players.append({
                    "player": {
                        "id": p.id,
                        "nombre": display_nombre,
                        "apellido": display_apellido,
                        "pais_cd": display_pais,
                        "group_number": p.group_number,
                    },
                    "stats": {
                        "points": stats.get("points", 0),
                        "wins": stats.get("wins", 0),
                        "losses": stats.get("losses", 0),
                        "sets_won": sets_won,
                        "sets_lost": sets_lost,
                        "sets_ratio": sets_ratio,
                        "position": None,
                    }
                })

            # Calculate positions
            players_with_matches = [p for p in players if p["stats"]["wins"] + p["stats"]["losses"] > 0]
            if players_with_matches:
                sorted_players = sorted(
                    players_with_matches,
                    key=lambda x: (-x["stats"]["points"], -x["stats"]["sets_ratio"], x["player"]["group_number"])
                )
                for pos, p in enumerate(sorted_players, 1):
                    for orig_p in players:
                        if orig_p["player"]["id"] == p["player"]["id"]:
                            orig_p["stats"]["position"] = pos
                            break

            groups_data.append({
                "group": {"name": f"Grupo {group.name}"},
                "players": players,
                "matches": matches,
                "results_matrix": results_matrix,
            })

        context = {
            "request": request,
            "preview_title": f"Hojas de Grupo - {category}",
            "back_url": "/admin/print-center",
            "download_url": None,  # No PDF download for now
            "tournament_name": get_tournament_name(),
            "category": category,
            "groups": groups_data,
        }

        return render_template("print/preview_all_group_sheets.html", context)


@app.get("/preview/group/{group_id}/matches", response_class=HTMLResponse)
async def preview_group_matches(request: Request, group_id: int):
    """Preview match list before PDF download."""
    with get_db_session() as session:
        group_repo = GroupRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        match_repo = MatchRepository(session)
        schedule_repo = ScheduleSlotRepository(session)
        from ettem.webapp.helpers import get_competitor_display
        from ettem.models import is_doubles_category

        group = group_repo.get_by_id(group_id)
        if not group:
            return Response(content="Grupo no encontrado", status_code=404)

        _is_doubles = is_doubles_category(group.category)

        # Get matches
        matches_orm = match_repo.get_by_group(group_id)
        matches_orm = sorted(matches_orm, key=lambda m: m.match_number or 999)

        # Build matches with player info
        matches = []
        for m in matches_orm:
            p1 = get_competitor_display(m, 1, player_repo, pair_repo, team_repo)
            p2 = get_competitor_display(m, 2, player_repo, pair_repo, team_repo)

            # Get schedule info
            schedule_slot = schedule_repo.get_by_match(m.id)
            table_number = schedule_slot.table_number if schedule_slot else None
            scheduled_time = schedule_slot.start_time if schedule_slot else None

            # Calculate result from sets
            result = None
            if m.sets and len(m.sets) > 0:
                sets_p1 = sum(1 for s in m.sets if s.get('player1_points', 0) > s.get('player2_points', 0))
                sets_p2 = sum(1 for s in m.sets if s.get('player2_points', 0) > s.get('player1_points', 0))
                result = f"{sets_p1} - {sets_p2}"

            matches.append({
                "match_order": m.match_number,
                "status": m.status,
                "result": result,
                "table_number": table_number,
                "scheduled_time": scheduled_time,
                "player1": {
                    "nombre": p1.full_name if _is_doubles else p1.nombre,
                    "apellido": "" if _is_doubles else p1.apellido,
                    "pais_cd": p1.pais_cd,
                },
                "player2": {
                    "nombre": p2.full_name if _is_doubles else p2.nombre,
                    "apellido": "" if _is_doubles else p2.apellido,
                    "pais_cd": p2.pais_cd,
                },
            })

        context = {
            "request": request,
            "preview_title": f"Lista de Partidos - Grupo {group.name}",
            "back_url": "/admin/print-center",
            "download_url": f"/print/group/{group_id}/matches",
            "tournament_name": get_tournament_name(),
            "title": f"Partidos - Grupo {group.name}",
            "category": group.category,
            "group_name": f"Grupo {group.name}",
            "matches": matches,
        }

        return render_template("print/preview_match_list.html", context)


@app.get("/preview/group/{group_id}/all-match-sheets", response_class=HTMLResponse)
async def preview_all_group_match_sheets(request: Request, group_id: int):
    """Preview all match sheets for a group before PDF download."""
    with get_db_session() as session:
        group_repo = GroupRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        match_repo = MatchRepository(session)
        schedule_repo = ScheduleSlotRepository(session)
        from ettem.webapp.helpers import get_competitor_display
        from ettem.models import is_doubles_category

        group = group_repo.get_by_id(group_id)
        if not group:
            return Response(content="Grupo no encontrado", status_code=404)

        _is_doubles = is_doubles_category(group.category)

        # Get matches
        matches_orm = match_repo.get_by_group(group_id)
        matches_orm = sorted(matches_orm, key=lambda m: m.match_number or 999)

        # Get number of players in group to calculate rounds
        all_players = player_repo.get_all()
        players_in_group = [p for p in all_players if p.group_id == group_id]
        num_players = len(players_in_group)
        matches_per_round = max(1, num_players // 2)

        # Build matches data
        matches_data = []
        for idx, m in enumerate(matches_orm):
            p1 = get_competitor_display(m, 1, player_repo, pair_repo, team_repo)
            p2 = get_competitor_display(m, 2, player_repo, pair_repo, team_repo)

            # Get schedule info
            schedule_slot = schedule_repo.get_by_match(m.id)
            table_number = schedule_slot.table_number if schedule_slot else None
            scheduled_time = schedule_slot.start_time if schedule_slot else None

            # Calculate round number (1-based)
            round_number = (idx // matches_per_round) + 1

            matches_data.append({
                "match": {
                    "id": m.id,
                    "match_order": m.match_number,
                    "round_type": m.round_type,
                },
                "player1": {
                    "nombre": p1.full_name if _is_doubles else p1.nombre,
                    "apellido": "" if _is_doubles else p1.apellido,
                    "pais_cd": p1.pais_cd,
                },
                "player2": {
                    "nombre": p2.full_name if _is_doubles else p2.nombre,
                    "apellido": "" if _is_doubles else p2.apellido,
                    "pais_cd": p2.pais_cd,
                },
                "group_name": group.name,
                "round_number": round_number,
                "table_number": table_number,
                "scheduled_time": scheduled_time,
            })

        # Group matches in pairs (2 per page)
        matches_pairs = []
        for i in range(0, len(matches_data), 2):
            pair = matches_data[i:i+2]
            matches_pairs.append(pair)

        context = {
            "request": request,
            "preview_title": f"Hojas de Partido - {group.name}",
            "back_url": "/admin/print-center",
            "download_url": f"/print/group/{group_id}/all-match-sheets",
            "tournament_name": get_tournament_name(),
            "category": group.category,
            "matches_pairs": matches_pairs,
            "is_doubles": _is_doubles,
        }

        return render_template("print/preview_match_sheets.html", context)


@app.get("/preview/category/{category}/all-match-sheets", response_class=HTMLResponse)
async def preview_all_category_match_sheets(request: Request, category: str):
    """Preview all match sheets for a category before PDF download."""
    with get_db_session() as session:
        group_repo = GroupRepository(session)
        player_repo = PlayerRepository(session)
        match_repo = MatchRepository(session)
        tournament_repo = TournamentRepository(session)
        schedule_repo = ScheduleSlotRepository(session)

        tournament = tournament_repo.get_current()
        tournament_id = tournament.id if tournament else None

        # Get all groups in category
        groups = group_repo.get_by_category(category, tournament_id=tournament_id)
        if not groups:
            return Response(content="No hay grupos en esta categoría", status_code=404)

        # Get all players once
        all_players = player_repo.get_all()

        # Build all matches data
        matches_data = []
        for group in sorted(groups, key=lambda g: int(g.name) if g.name.isdigit() else g.name):
            matches_orm = match_repo.get_by_group(group.id)
            matches_orm = sorted(matches_orm, key=lambda m: m.match_number or 999)

            # Get number of players in this group to calculate rounds
            players_in_group = [p for p in all_players if p.group_id == group.id]
            num_players = len(players_in_group)
            matches_per_round = max(1, num_players // 2)

            for idx, m in enumerate(matches_orm):
                p1 = player_repo.get_by_id(m.player1_id)
                p2 = player_repo.get_by_id(m.player2_id)

                # Get schedule info
                schedule_slot = schedule_repo.get_by_match(m.id)
                table_number = schedule_slot.table_number if schedule_slot else None
                scheduled_time = schedule_slot.start_time if schedule_slot else None

                # Calculate round number (1-based)
                round_number = (idx // matches_per_round) + 1

                matches_data.append({
                    "match": {
                        "id": m.id,
                        "match_order": m.match_number,
                        "round_type": m.round_type,
                    },
                    "player1": {
                        "nombre": p1.nombre if p1 else "?",
                        "apellido": p1.apellido if p1 else "?",
                        "pais_cd": p1.pais_cd if p1 else "?",
                    },
                    "player2": {
                        "nombre": p2.nombre if p2 else "?",
                        "apellido": p2.apellido if p2 else "?",
                        "pais_cd": p2.pais_cd if p2 else "?",
                    },
                    "group_name": group.name,
                    "round_number": round_number,
                    "table_number": table_number,
                    "scheduled_time": scheduled_time,
                })

        if not matches_data:
            return Response(content="No hay partidos en esta categoría", status_code=404)

        # Group matches in pairs (2 per page)
        matches_pairs = []
        for i in range(0, len(matches_data), 2):
            pair = matches_data[i:i+2]
            matches_pairs.append(pair)

        context = {
            "request": request,
            "preview_title": f"Hojas de Partido - {category}",
            "back_url": "/admin/print-center",
            "download_url": f"/print/category/{category}/all-match-sheets",
            "tournament_name": get_tournament_name(),
            "category": category,
            "matches_pairs": matches_pairs,
        }

        return render_template("print/preview_match_sheets.html", context)


# ==============================================================================
# BRACKET PRINT ROUTES
# ==============================================================================


@app.get("/preview/bracket/match/{match_id}", response_class=HTMLResponse)
async def preview_bracket_match_sheet(request: Request, match_id: int):
    """Preview a single bracket match sheet."""
    with get_db_session() as session:
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)

        match_orm = match_repo.get_by_id(match_id)
        if not match_orm:
            return Response(content="Partido no encontrado", status_code=404)

        from ettem.webapp.helpers import get_competitor_display
        from ettem.models import is_doubles_category

        # Determine category
        category = match_orm.category or "?"
        if category == "?" and match_orm.pair1_id:
            pair = pair_repo.get_by_id(match_orm.pair1_id)
            if pair:
                category = pair.categoria
        if category == "?" and match_orm.player1_id:
            player = player_repo.get_by_id(match_orm.player1_id)
            if player:
                category = player.categoria

        _is_doubles = is_doubles_category(category)
        p1 = get_competitor_display(match_orm, 1, player_repo, pair_repo, team_repo)
        p2 = get_competitor_display(match_orm, 2, player_repo, pair_repo, team_repo)

        # Round type display names
        round_names = {
            "R32": "Ronda de 32",
            "R16": "Octavos de Final",
            "QF": "Cuartos de Final",
            "SF": "Semifinal",
            "F": "Final",
        }

        match_data = {
            "match": {
                "id": match_orm.id,
                "match_order": match_orm.match_number or 1,
                "round_type": match_orm.round_type,
            },
            "player1": {
                "nombre": p1.full_name if _is_doubles else p1.nombre,
                "apellido": "" if _is_doubles else p1.apellido,
                "pais_cd": p1.pais_cd,
            },
            "player2": {
                "nombre": p2.full_name if _is_doubles else p2.nombre,
                "apellido": "" if _is_doubles else p2.apellido,
                "pais_cd": p2.pais_cd,
            },
            "group_name": round_names.get(match_orm.round_type, match_orm.round_type),
            "round_number": 1,
        }

        matches_pairs = [[match_data]]

        context = {
            "request": request,
            "preview_title": f"Hoja de Partido - {round_names.get(match_orm.round_type, match_orm.round_type)}",
            "back_url": "/admin/print-center",
            "download_url": f"/print/bracket/match/{match_id}",
            "tournament_name": get_tournament_name(),
            "category": category,
            "matches_pairs": matches_pairs,
            "is_doubles": _is_doubles,
        }

        return render_template("print/preview_match_sheets.html", context)


@app.get("/preview/bracket/{category}/all-match-sheets", response_class=HTMLResponse)
async def preview_bracket_all_match_sheets(request: Request, category: str):
    """Preview all bracket match sheets for a category."""
    with get_db_session() as session:
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)

        from ettem.webapp.helpers import get_competitor_display
        from ettem.models import is_doubles_category

        _is_doubles = is_doubles_category(category)

        # Get all bracket matches for this category
        all_matches = [m for m in match_repo.get_all()
                       if m.group_id is None and m.category == category]

        # Round type display names
        round_names = {
            "R32": "Ronda de 32",
            "R16": "Octavos de Final",
            "QF": "Cuartos de Final",
            "SF": "Semifinal",
            "F": "Final",
        }
        round_order = {"R32": 0, "R16": 1, "QF": 2, "SF": 3, "F": 4}

        matches_data = []
        for match_orm in all_matches:
            p1 = get_competitor_display(match_orm, 1, player_repo, pair_repo, team_repo)
            p2 = get_competitor_display(match_orm, 2, player_repo, pair_repo, team_repo)

            # Only include matches with both competitors defined
            if p1.id == 0 or p2.id == 0:
                continue

            matches_data.append({
                "match": {
                    "id": match_orm.id,
                    "match_order": match_orm.match_number or 1,
                    "round_type": match_orm.round_type,
                },
                "player1": {
                    "nombre": p1.full_name if _is_doubles else p1.nombre,
                    "apellido": "" if _is_doubles else p1.apellido,
                    "pais_cd": p1.pais_cd,
                },
                "player2": {
                    "nombre": p2.full_name if _is_doubles else p2.nombre,
                    "apellido": "" if _is_doubles else p2.apellido,
                    "pais_cd": p2.pais_cd,
                },
                "group_name": round_names.get(match_orm.round_type, match_orm.round_type),
                "round_number": 1,
                "sort_key": round_order.get(match_orm.round_type, 99),
            })

        if not matches_data:
            return Response(content="No hay partidos definidos en el bracket", status_code=404)

        # Sort by round
        matches_data = sorted(matches_data, key=lambda m: (m["sort_key"], m["match"]["id"]))

        # Group matches in pairs (2 per page)
        matches_pairs = []
        for i in range(0, len(matches_data), 2):
            pair = matches_data[i:i+2]
            matches_pairs.append(pair)

        context = {
            "request": request,
            "preview_title": f"Hojas de Partido - Bracket {category}",
            "back_url": "/admin/print-center",
            "download_url": f"/print/bracket/{category}/all-match-sheets",
            "tournament_name": get_tournament_name(),
            "category": category,
            "matches_pairs": matches_pairs,
            "is_doubles": _is_doubles,
        }

        return render_template("print/preview_match_sheets.html", context)


@app.get("/print/bracket/match/{match_id}")
async def print_bracket_match_sheet(match_id: int):
    """Download PDF for a single bracket match sheet."""
    with get_db_session() as session:
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)

        match_orm = match_repo.get_by_id(match_id)
        if not match_orm:
            return Response(content="Partido no encontrado", status_code=404)

        from ettem.webapp.helpers import get_competitor_display
        p1 = get_competitor_display(match_orm, 1, player_repo, pair_repo, team_repo)
        p2 = get_competitor_display(match_orm, 2, player_repo, pair_repo, team_repo)

        # Determine category from pair or player
        from ettem.models import is_doubles_category
        category = "Bracket"
        if match_orm.pair1_id:
            pair = pair_repo.get_by_id(match_orm.pair1_id)
            if pair:
                category = pair.categoria
        elif match_orm.player1_id:
            player = player_repo.get_by_id(match_orm.player1_id)
            if player:
                category = player.categoria

        _is_doubles = is_doubles_category(category)

        round_names = {
            "R32": "Ronda de 32",
            "R16": "Octavos de Final",
            "QF": "Cuartos de Final",
            "SF": "Semifinal",
            "F": "Final",
        }

        match_data = {
            "match": {
                "id": match_orm.id,
                "match_order": match_orm.match_number or 1,
                "round_type": match_orm.round_type,
            },
            "player1": {
                "nombre": (p1.full_name if _is_doubles else p1.nombre) if p1 else "TBD",
                "apellido": ("" if _is_doubles else p1.apellido) if p1 else "",
                "pais_cd": p1.pais_cd if p1 else "?",
            },
            "player2": {
                "nombre": (p2.full_name if _is_doubles else p2.nombre) if p2 else "TBD",
                "apellido": ("" if _is_doubles else p2.apellido) if p2 else "",
                "pais_cd": p2.pais_cd if p2 else "?",
            },
            "group_name": round_names.get(match_orm.round_type, match_orm.round_type),
            "round_number": 1,
        }

        matches_pairs = [[match_data]]

        try:
            # Flatten matches_pairs to matches_data for the PDF generator
            matches_data = [m for pair in matches_pairs for m in pair]
            pdf_bytes = pdf_generator.generate_all_match_sheets_pdf(
                matches_data=matches_data,
                tournament_name=get_tournament_name(),
                category=category,
                is_doubles=_is_doubles,
            )

            filename = f"partido_bracket_{match_orm.round_type}_{match_id}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
        except Exception as e:
            return Response(content=f"Error generando PDF: {str(e)}", status_code=500)


@app.post("/print/bracket/selected")
async def print_bracket_selected_matches(
    request: Request,
    category: str = Form(...),
    match_ids: list[int] = Form(default=[])
):
    """Preview selected bracket match sheets before printing."""
    from ettem.storage import ScheduleSlotRepository

    # Check if any matches were selected
    if not match_ids:
        request.session["flash_message"] = "Debes seleccionar al menos un partido"
        request.session["flash_type"] = "warning"
        return RedirectResponse(url="/admin/print-center", status_code=303)

    with get_db_session() as session:
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        schedule_repo = ScheduleSlotRepository(session)

        from ettem.webapp.helpers import get_competitor_display
        from ettem.models import is_doubles_category

        _is_doubles = is_doubles_category(category)

        # Build schedule lookup
        all_slots = schedule_repo.get_all()
        schedule_lookup = {slot.match_id: slot for slot in all_slots}

        round_names = {
            "R128": "Ronda de 128",
            "R64": "Ronda de 64",
            "R32": "Ronda de 32",
            "R16": "Octavos de Final",
            "QF": "Cuartos de Final",
            "SF": "Semifinal",
            "F": "Final",
        }
        round_order = {"R128": -1, "R64": 0, "R32": 1, "R16": 2, "QF": 3, "SF": 4, "F": 5}

        matches_data = []
        for match_id in match_ids:
            match_orm = match_repo.get_by_id(match_id)
            if not match_orm:
                continue

            p1 = get_competitor_display(match_orm, 1, player_repo, pair_repo, team_repo)
            p2 = get_competitor_display(match_orm, 2, player_repo, pair_repo, team_repo)

            # Get schedule info
            schedule_slot = schedule_lookup.get(match_id)
            table_number = schedule_slot.table_number if schedule_slot else None
            start_time = schedule_slot.start_time if schedule_slot else None

            matches_data.append({
                "match": {
                    "id": match_orm.id,
                    "match_order": match_orm.match_number or 1,
                    "round_type": match_orm.round_type,
                },
                "player1": {
                    "nombre": p1.full_name if _is_doubles else p1.nombre,
                    "apellido": "" if _is_doubles else p1.apellido,
                    "pais_cd": p1.pais_cd,
                },
                "player2": {
                    "nombre": p2.full_name if _is_doubles else p2.nombre,
                    "apellido": "" if _is_doubles else p2.apellido,
                    "pais_cd": p2.pais_cd,
                },
                "group_name": round_names.get(match_orm.round_type, match_orm.round_type),
                "round_number": 1,
                "sort_key": round_order.get(match_orm.round_type, 99),
                "table_number": table_number,
                "scheduled_time": start_time,
            })

        if not matches_data:
            request.session["flash_message"] = "No se seleccionaron partidos válidos"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/print-center", status_code=303)

        # Sort by round
        matches_data = sorted(matches_data, key=lambda m: (m["sort_key"], m["match"]["id"]))

        # Group in pairs (2 per page)
        matches_pairs = []
        for i in range(0, len(matches_data), 2):
            pair = matches_data[i:i+2]
            matches_pairs.append(pair)

        context = {
            "request": request,
            "tournament_name": get_tournament_name(),
            "category": category,
            "matches_pairs": matches_pairs,
            "total_matches": len(matches_data),
            "back_url": "/admin/print-center",
            "preview_title": f"Hojas de Partido - Bracket {category}",
            "is_doubles": _is_doubles,
        }

        return render_template("print/preview_match_sheets.html", context)


@app.get("/print/bracket/{category}/all-match-sheets")
async def print_bracket_all_match_sheets(category: str):
    """Download PDF for all bracket match sheets in a category."""
    from ettem.models import is_doubles_category

    with get_db_session() as session:
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)

        _is_doubles = is_doubles_category(category)
        bracket_matches = match_repo.get_bracket_matches_by_category(category)

        round_names = {
            "R32": "Ronda de 32",
            "R16": "Octavos de Final",
            "QF": "Cuartos de Final",
            "SF": "Semifinal",
            "F": "Final",
        }
        round_order = {"R32": 0, "R16": 1, "QF": 2, "SF": 3, "F": 4}

        from ettem.webapp.helpers import get_competitor_display
        matches_data = []
        for match_orm in bracket_matches:
            p1 = get_competitor_display(match_orm, 1, player_repo, pair_repo, team_repo)
            p2 = get_competitor_display(match_orm, 2, player_repo, pair_repo, team_repo)

            if p1.id == 0 and p2.id == 0:
                continue

            matches_data.append({
                "match": {
                    "id": match_orm.id,
                    "match_order": match_orm.match_number or 1,
                    "round_type": match_orm.round_type,
                },
                "player1": {
                    "nombre": p1.full_name if _is_doubles else p1.nombre,
                    "apellido": "" if _is_doubles else p1.apellido,
                    "pais_cd": p1.pais_cd,
                },
                "player2": {
                    "nombre": p2.full_name if _is_doubles else p2.nombre,
                    "apellido": "" if _is_doubles else p2.apellido,
                    "pais_cd": p2.pais_cd,
                },
                "group_name": round_names.get(match_orm.round_type, match_orm.round_type),
                "round_number": 1,
                "sort_key": round_order.get(match_orm.round_type, 99),
            })

        if not matches_data:
            return Response(content="No hay partidos definidos en el bracket", status_code=404)

        matches_data = sorted(matches_data, key=lambda m: (m["sort_key"], m["match"]["id"]))

        matches_pairs = []
        for i in range(0, len(matches_data), 2):
            pair = matches_data[i:i+2]
            matches_pairs.append(pair)

        try:
            # Flatten matches_pairs to matches_data for the PDF generator
            matches_data_flat = [m for pair in matches_pairs for m in pair]
            pdf_bytes = pdf_generator.generate_all_match_sheets_pdf(
                matches_data=matches_data_flat,
                tournament_name=get_tournament_name(),
                category=category,
                is_doubles=_is_doubles,
            )

            filename = f"partidos_bracket_{category}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
        except Exception as e:
            return Response(content=f"Error generando PDF: {str(e)}", status_code=500)


@app.get("/preview/bracket/{category}/tree", response_class=HTMLResponse)
async def preview_bracket_tree(request: Request, category: str):
    """Preview the bracket tree visualization for printing."""
    from collections import defaultdict, namedtuple
    from datetime import datetime
    from ettem.models import is_doubles_category
    from ettem.webapp.helpers import get_bracket_slot_display, get_competitor_display, get_champion_display

    with get_db_session() as session:
        bracket_repo = BracketRepository(session)
        player_repo = PlayerRepository(session)
        match_repo = MatchRepository(session)
        team_repo = TeamRepository(session)
        pair_repo = PairRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Get bracket slots for this category
        bracket_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)

        if not bracket_slots:
            return Response(content="No hay bracket generado para esta categoria", status_code=404)

        # Group slots by round
        slots_by_round = defaultdict(list)
        for slot_orm in bracket_slots:
            slots_by_round[slot_orm.round_type].append(slot_orm)

        # Sort each round by slot_number
        for round_type in slots_by_round:
            slots_by_round[round_type].sort(key=lambda s: s.slot_number)

        # Determine bracket size and required rounds
        bracket_size = 0
        round_priority = ['R128', 'R64', 'R32', 'R16', 'QF', 'SF', 'F']
        for round_type in round_priority:
            if round_type in slots_by_round:
                bracket_size = len(slots_by_round[round_type])
                break

        required_rounds = []
        if bracket_size >= 128:
            required_rounds = ['R128', 'R64', 'R32', 'R16', 'QF', 'SF', 'F']
        elif bracket_size >= 64:
            required_rounds = ['R64', 'R32', 'R16', 'QF', 'SF', 'F']
        elif bracket_size >= 32:
            required_rounds = ['R32', 'R16', 'QF', 'SF', 'F']
        elif bracket_size >= 16:
            required_rounds = ['R16', 'QF', 'SF', 'F']
        elif bracket_size >= 8:
            required_rounds = ['QF', 'SF', 'F']
        elif bracket_size >= 4:
            required_rounds = ['SF', 'F']
        elif bracket_size >= 2:
            required_rounds = ['F']

        # Create dummy slots for missing rounds
        DummySlot = namedtuple('DummySlot', ['slot_number', 'round_type', 'player_id', 'is_bye', 'same_country_warning', 'id'])

        complete_bracket = {}
        current_slots = bracket_size

        for round_type in required_rounds:
            if round_type in slots_by_round:
                complete_bracket[round_type] = slots_by_round[round_type]
            else:
                current_slots = current_slots // 2
                complete_bracket[round_type] = []
                for i in range(current_slots):
                    dummy = DummySlot(
                        slot_number=i + 1,
                        round_type=round_type,
                        player_id=None,
                        is_bye=False,
                        same_country_warning=False,
                        id=None
                    )
                    complete_bracket[round_type].append(dummy)

        # Get competitor details for each slot (doubles-aware)
        _is_doubles = is_doubles_category(category)
        slots_with_players = {}
        for round_type, slots in complete_bracket.items():
            slots_with_players[round_type] = []
            for slot in slots:
                competitor = get_bracket_slot_display(slot, category, player_repo, pair_repo, team_repo)
                slots_with_players[round_type].append({
                    "slot": slot,
                    "player": competitor
                })

        # Get bracket matches with scores
        all_bracket_matches = [m for m in match_repo.get_all() if m.group_id is None]

        matches_by_round = {}
        bracket_best_of = 5
        champion = None

        for match in all_bracket_matches:
            # Category filter: for doubles check pair, for singles check player
            if _is_doubles and match.pair1_id:
                pair = pair_repo.get_by_id(match.pair1_id)
                if not pair:
                    continue
                p1_player = player_repo.get_by_id(pair.player1_id)
                if not p1_player or p1_player.categoria != category:
                    continue
            else:
                p1 = player_repo.get_by_id(match.player1_id) if match.player1_id else None
                if not p1 or p1.categoria != category:
                    continue

            if match.round_type not in matches_by_round:
                matches_by_round[match.round_type] = []

            cd1 = get_competitor_display(match, 1, player_repo, pair_repo, team_repo)
            cd2 = get_competitor_display(match, 2, player_repo, pair_repo, team_repo)
            matches_by_round[match.round_type].append({
                "match": match,
                "player1": cd1,
                "player2": cd2,
            })

            bracket_best_of = match.best_of or 5

            # Check for champion (final match winner)
            if match.round_type == 'F' and match.winner_id:
                champion = get_champion_display(match.winner_id, category, player_repo, pair_repo, team_repo=team_repo)

        # Round display names
        round_names = {
            "R128": "Ronda 128",
            "R64": "Ronda 64",
            "R32": "Ronda 32",
            "R16": "Octavos",
            "QF": "Cuartos",
            "SF": "Semifinal",
            "F": "Final"
        }

        # Build schedule info for bracket matches (time/table)
        schedule_repo = ScheduleSlotRepository(session)
        schedule_info = {}
        for ss in schedule_repo.get_all():
            schedule_info[ss.match_id] = {
                "time": ss.start_time,
                "table": ss.table_number,
            }

        context = {
            "request": request,
            "preview_title": f"Llave - {category}",
            "back_url": f"/category/{category}/bracket",
            "download_url": f"/print/bracket/{category}/tree",
            "tournament_name": get_tournament_name(),
            "category": category,
            "slots_by_round": slots_with_players,
            "matches_by_round": matches_by_round,
            "round_order": required_rounds,
            "round_names": round_names,
            "best_of": bracket_best_of,
            "champion": champion,
            "is_doubles": _is_doubles,
            "schedule_info": schedule_info,
            "generation_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        return render_template("print/preview_bracket_tree.html", context)


@app.get("/print/bracket/{category}/tree")
async def print_bracket_tree(category: str):
    """Download PDF for bracket tree visualization."""
    from collections import defaultdict, namedtuple
    from datetime import datetime
    from ettem.models import is_doubles_category
    from ettem.webapp.helpers import get_bracket_slot_display, get_competitor_display, get_champion_display

    with get_db_session() as session:
        bracket_repo = BracketRepository(session)
        player_repo = PlayerRepository(session)
        match_repo = MatchRepository(session)
        team_repo = TeamRepository(session)
        pair_repo = PairRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Get bracket slots for this category
        bracket_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)

        if not bracket_slots:
            return Response(content="No hay bracket generado para esta categoria", status_code=404)

        # Group slots by round
        slots_by_round = defaultdict(list)
        for slot_orm in bracket_slots:
            slots_by_round[slot_orm.round_type].append(slot_orm)

        # Sort each round by slot_number
        for round_type in slots_by_round:
            slots_by_round[round_type].sort(key=lambda s: s.slot_number)

        # Determine bracket size and required rounds
        bracket_size = 0
        round_priority = ['R128', 'R64', 'R32', 'R16', 'QF', 'SF', 'F']
        for round_type in round_priority:
            if round_type in slots_by_round:
                bracket_size = len(slots_by_round[round_type])
                break

        required_rounds = []
        if bracket_size >= 128:
            required_rounds = ['R128', 'R64', 'R32', 'R16', 'QF', 'SF', 'F']
        elif bracket_size >= 64:
            required_rounds = ['R64', 'R32', 'R16', 'QF', 'SF', 'F']
        elif bracket_size >= 32:
            required_rounds = ['R32', 'R16', 'QF', 'SF', 'F']
        elif bracket_size >= 16:
            required_rounds = ['R16', 'QF', 'SF', 'F']
        elif bracket_size >= 8:
            required_rounds = ['QF', 'SF', 'F']
        elif bracket_size >= 4:
            required_rounds = ['SF', 'F']
        elif bracket_size >= 2:
            required_rounds = ['F']

        # Create dummy slots for missing rounds
        DummySlot = namedtuple('DummySlot', ['slot_number', 'round_type', 'player_id', 'is_bye', 'same_country_warning', 'id'])

        complete_bracket = {}
        current_slots = bracket_size

        for round_type in required_rounds:
            if round_type in slots_by_round:
                complete_bracket[round_type] = slots_by_round[round_type]
            else:
                current_slots = current_slots // 2
                complete_bracket[round_type] = []
                for i in range(current_slots):
                    dummy = DummySlot(
                        slot_number=i + 1,
                        round_type=round_type,
                        player_id=None,
                        is_bye=False,
                        same_country_warning=False,
                        id=None
                    )
                    complete_bracket[round_type].append(dummy)

        # Get competitor details for each slot (doubles-aware)
        _is_doubles = is_doubles_category(category)
        slots_with_players = {}
        for round_type, slots in complete_bracket.items():
            slots_with_players[round_type] = []
            for slot in slots:
                competitor = get_bracket_slot_display(slot, category, player_repo, pair_repo, team_repo)
                slots_with_players[round_type].append({
                    "slot": slot,
                    "player": competitor
                })

        # Get bracket matches with scores
        all_bracket_matches = [m for m in match_repo.get_all() if m.group_id is None]

        matches_by_round = {}
        bracket_best_of = 5
        champion = None

        for match in all_bracket_matches:
            # Category filter: for doubles check pair, for singles check player
            if _is_doubles and match.pair1_id:
                pair = pair_repo.get_by_id(match.pair1_id)
                if not pair:
                    continue
                p1_player = player_repo.get_by_id(pair.player1_id)
                if not p1_player or p1_player.categoria != category:
                    continue
            else:
                p1 = player_repo.get_by_id(match.player1_id) if match.player1_id else None
                if not p1 or p1.categoria != category:
                    continue

            if match.round_type not in matches_by_round:
                matches_by_round[match.round_type] = []

            cd1 = get_competitor_display(match, 1, player_repo, pair_repo, team_repo)
            cd2 = get_competitor_display(match, 2, player_repo, pair_repo, team_repo)
            matches_by_round[match.round_type].append({
                "match": match,
                "player1": cd1,
                "player2": cd2,
            })

            bracket_best_of = match.best_of or 5

            # Check for champion (final match winner)
            if match.round_type == 'F' and match.winner_id:
                champion = get_champion_display(match.winner_id, category, player_repo, pair_repo, team_repo=team_repo)

        # Round display names
        round_names = {
            "R128": "Ronda 128",
            "R64": "Ronda 64",
            "R32": "Ronda 32",
            "R16": "Octavos",
            "QF": "Cuartos",
            "SF": "Semifinal",
            "F": "Final"
        }

        # Build schedule info for bracket matches (time/table)
        schedule_repo = ScheduleSlotRepository(session)
        schedule_info = {}
        for ss in schedule_repo.get_all():
            schedule_info[ss.match_id] = {
                "time": ss.start_time,
                "table": ss.table_number,
            }

        context = {
            "tournament_name": get_tournament_name(),
            "category": category,
            "slots_by_round": slots_with_players,
            "matches_by_round": matches_by_round,
            "round_order": required_rounds,
            "round_names": round_names,
            "best_of": bracket_best_of,
            "champion": champion,
            "is_doubles": _is_doubles,
            "schedule_info": schedule_info,
            "generation_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        try:
            pdf_bytes = pdf_generator.generate_bracket_tree_pdf(context)
            filename = f"llave_{category}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
        except Exception as e:
            return Response(content=f"Error generando PDF: {str(e)}", status_code=500)


# ==============================================================================
# SCHEDULER ROUTES
# ==============================================================================


@app.get("/admin/scheduler", response_class=HTMLResponse)
async def admin_scheduler(request: Request):
    """Main scheduler page - configure sessions and view schedule overview."""
    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        from ettem.storage import SessionRepository

        tournament = tournament_repo.get_current()
        if not tournament:
            return render_template("admin_scheduler.html", {
                "request": request,
                "tournament": None,
            })

        session_repo = SessionRepository(session)
        sessions = session_repo.get_by_tournament(tournament.id)

        # Get match counts - only for current tournament
        match_repo = MatchRepository(session)
        group_repo = GroupRepository(session)
        bracket_repo = BracketRepository(session)

        # Get categories that belong to current tournament (groups + brackets)
        tournament_categories = set()
        all_groups = group_repo.get_all(tournament_id=tournament.id)
        for g in all_groups:
            tournament_categories.add(g.category)
        all_bracket_slots = bracket_repo.get_all(tournament_id=tournament.id)
        for bs in all_bracket_slots:
            tournament_categories.add(bs.category)

        # Get categories with brackets in current tournament
        bracket_categories = set()
        for cat in tournament_categories:
            bracket_slots = bracket_repo.get_by_category(cat, tournament_id=tournament.id)
            if bracket_slots:
                bracket_categories.add(cat)

        # Count matches for current tournament only
        all_matches = match_repo.get_all()
        tournament_matches = []
        for m in all_matches:
            if m.group_id:
                group = group_repo.get_by_id(m.group_id)
                if group and group.tournament_id == tournament.id:
                    tournament_matches.append(m)
            else:
                # Bracket match - only include if bracket exists for this category in current tournament
                if m.category in bracket_categories:
                    tournament_matches.append(m)

        # Count scheduled vs unscheduled
        from ettem.storage import ScheduleSlotRepository
        schedule_repo = ScheduleSlotRepository(session)
        scheduled_match_ids = set()
        for sess in sessions:
            for slot in schedule_repo.get_by_session(sess.id):
                scheduled_match_ids.add(slot.match_id)

        total_matches = len(tournament_matches)
        scheduled_count = len([m for m in tournament_matches if m.id in scheduled_match_ids])
        unscheduled_count = total_matches - scheduled_count

        # Config is locked if there are sessions created
        config_locked = len(sessions) > 0

        context = {
            "request": request,
            "tournament": tournament,
            "sessions": sessions,
            "total_matches": total_matches,
            "scheduled_count": scheduled_count,
            "unscheduled_count": unscheduled_count,
            "config_locked": config_locked,
        }

        flash_message = request.session.pop("flash_message", None)
        flash_type = request.session.pop("flash_type", "info")
        if flash_message:
            context["flash_message"] = flash_message
            context["flash_type"] = flash_type

        return render_template("admin_scheduler.html", context)


@app.post("/admin/scheduler/config")
async def save_scheduler_config(
    request: Request,
    num_tables: int = Form(...),
    default_match_duration: int = Form(...),
    min_rest_time: int = Form(...)
):
    """Save scheduler configuration for the tournament."""
    from ettem.storage import TableConfigRepository

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()

        if not tournament:
            return RedirectResponse(url="/tournaments", status_code=303)

        tournament.num_tables = num_tables
        tournament.default_match_duration = default_match_duration
        tournament.min_rest_time = min_rest_time

        # Sync TableConfig with num_tables
        table_config_repo = TableConfigRepository(session)
        table_config_repo.sync_tables(tournament.id, num_tables)

        session.commit()

        request.session["flash_message"] = "Configuración guardada y mesas sincronizadas"
        request.session["flash_type"] = "success"
        return RedirectResponse(url="/admin/scheduler", status_code=303)


@app.post("/admin/scheduler/session/create")
async def create_session(
    request: Request,
    name: str = Form(...),
    date: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...)
):
    """Create a new tournament session."""
    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        from ettem.storage import SessionRepository

        tournament = tournament_repo.get_current()
        if not tournament:
            return RedirectResponse(url="/tournaments", status_code=303)

        session_repo = SessionRepository(session)

        # Parse date
        from datetime import datetime as dt
        try:
            session_date = dt.strptime(date, "%Y-%m-%d")
        except ValueError:
            request.session["flash_message"] = "Formato de fecha inválido"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/scheduler", status_code=303)

        # Get existing sessions and check for overlaps
        existing_sessions = session_repo.get_by_tournament(tournament.id)
        next_order = len(existing_sessions)

        # Check for overlapping sessions on the same date
        def time_to_minutes(t: str) -> int:
            h, m = map(int, t.split(':'))
            return h * 60 + m

        new_start = time_to_minutes(start_time)
        new_end = time_to_minutes(end_time)

        for existing in existing_sessions:
            # Check if same date
            if existing.date.date() == session_date.date():
                existing_start = time_to_minutes(existing.start_time)
                existing_end = time_to_minutes(existing.end_time)

                # Check for overlap: start1 < end2 AND start2 < end1
                if new_start < existing_end and existing_start < new_end:
                    request.session["flash_message"] = f"La jornada se traslapa con '{existing.name}' ({existing.start_time}-{existing.end_time})"
                    request.session["flash_type"] = "error"
                    return RedirectResponse(url="/admin/scheduler", status_code=303)

        session_repo.create(
            tournament_id=tournament.id,
            name=name,
            date=session_date,
            start_time=start_time,
            end_time=end_time,
            order=next_order
        )

        request.session["flash_message"] = f"Jornada '{name}' creada"
        request.session["flash_type"] = "success"
        return RedirectResponse(url="/admin/scheduler", status_code=303)


@app.post("/admin/scheduler/session/{session_id}/delete")
async def delete_session(request: Request, session_id: int):
    """Delete a tournament session."""
    with get_db_session() as session:
        from ettem.storage import SessionRepository, ScheduleSlotRepository

        session_repo = SessionRepository(session)
        schedule_repo = ScheduleSlotRepository(session)

        # First delete all schedule slots in this session
        schedule_repo.delete_by_session(session_id)

        # Then delete the session
        session_repo.delete(session_id)

        request.session["flash_message"] = "Jornada eliminada"
        request.session["flash_type"] = "success"
        return RedirectResponse(url="/admin/scheduler", status_code=303)


@app.get("/admin/scheduler/grid/{session_id}", response_class=HTMLResponse)
async def scheduler_grid(request: Request, session_id: int):
    """Scheduling grid for a specific session - drag and drop matches to table/time slots."""
    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        from ettem.storage import SessionRepository, ScheduleSlotRepository, TimeSlotRepository

        tournament = tournament_repo.get_current()
        if not tournament:
            return RedirectResponse(url="/tournaments", status_code=303)

        session_repo = SessionRepository(session)
        schedule_repo = ScheduleSlotRepository(session)
        time_slot_repo = TimeSlotRepository(session)
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        group_repo = GroupRepository(session)

        # Get session info
        session_obj = session_repo.get_by_id(session_id)
        if not session_obj:
            request.session["flash_message"] = "Jornada no encontrada"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/scheduler", status_code=303)

        num_tables = tournament.num_tables or 4
        match_duration = tournament.default_match_duration or 30

        # Get or initialize time slots for this session
        db_time_slots = time_slot_repo.get_by_session(session_id)
        if not db_time_slots:
            # Initialize time slots with default duration
            db_time_slots = time_slot_repo.initialize_for_session(
                session_id=session_id,
                start_time=session_obj.start_time,
                end_time=session_obj.end_time,
                default_duration=match_duration
            )

        # Build time slots list with duration info
        time_slots = []
        time_slots_info = {}  # {start_time: {slot_number, duration}}
        for ts in db_time_slots:
            time_slots.append(ts.start_time)
            time_slots_info[ts.start_time] = {
                "slot_number": ts.slot_number,
                "duration": ts.duration_minutes,
            }

        # Get scheduled slots for this session (for grid display)
        scheduled_slots = schedule_repo.get_by_session(session_id)

        # Get ALL scheduled match IDs across ALL sessions (to filter unscheduled list)
        all_scheduled_match_ids = schedule_repo.get_all_scheduled_match_ids()

        # Build grid data: {time_slot: {table: match_data or None}}
        grid_data = {}
        for time_slot in time_slots:
            grid_data[time_slot] = {}
            for table in range(1, num_tables + 1):
                grid_data[time_slot][table] = None

        # Fill in scheduled matches
        from ettem.webapp.helpers import get_competitor_display
        for slot in scheduled_slots:
            match_orm = match_repo.get_by_id(slot.match_id)
            if match_orm and slot.start_time in grid_data:
                display1 = get_competitor_display(match_orm, 1, player_repo, pair_repo, team_repo)
                display2 = get_competitor_display(match_orm, 2, player_repo, pair_repo, team_repo)

                # Get group/round info
                if match_orm.group_id:
                    group = group_repo.get_by_id(match_orm.group_id)
                    match_label = f"G{group.name}" if group else "Grupo"
                    category = group.category if group else "?"
                else:
                    match_label = match_orm.round_type or "Bracket"
                    category = match_orm.category or "?"

                # Determine round type for scheduled match
                if match_orm.group_id:
                    group_matches_list = sorted(match_repo.get_by_group(match_orm.group_id), key=lambda x: x.match_number or 0)
                    players_in_group = len(set([gm.player1_id for gm in group_matches_list] + [gm.player2_id for gm in group_matches_list]))
                    matches_per_round = max(1, players_in_group // 2)
                    match_index = next((i for i, gm in enumerate(group_matches_list) if gm.id == match_orm.id), 0)
                    group_round = (match_index // matches_per_round) + 1
                    round_type = f"R{group_round}"
                else:
                    round_type = match_orm.round_type or "Bracket"

                grid_data[slot.start_time][slot.table_number] = {
                    "slot_id": slot.id,
                    "match_id": match_orm.id,
                    "player1": display1.full_name if display1 else "TBD",
                    "player2": display2.full_name if display2 else "TBD",
                    "player1_id": match_orm.player1_id,
                    "player2_id": match_orm.player2_id,
                    "player1_country": display1.pais_cd if display1 else "",
                    "player2_country": display2.pais_cd if display2 else "",
                    "label": match_label,
                    "category": category,
                    "round_type": round_type,
                }

        # Get unscheduled matches - only from current tournament
        # Build valid categories from groups AND brackets
        tournament_categories = set()
        all_groups = group_repo.get_all(tournament_id=tournament.id)
        for g in all_groups:
            tournament_categories.add(g.category)

        # Also include categories that have brackets (KO Directo without groups)
        bracket_repo = BracketRepository(session)
        all_bracket_slots = bracket_repo.get_all(tournament_id=tournament.id)
        for bs in all_bracket_slots:
            tournament_categories.add(bs.category)

        # Build set of categories that have brackets in current tournament
        bracket_categories = set()
        for cat in tournament_categories:
            bracket_slots = bracket_repo.get_by_category(cat, tournament_id=tournament.id)
            if bracket_slots:
                bracket_categories.add(cat)

        all_matches = match_repo.get_all()

        unscheduled_matches = []
        for m in all_matches:
            # Skip matches already scheduled in ANY session
            if m.id in all_scheduled_match_ids:
                continue

            # Filter: only include matches from current tournament
            if m.group_id:
                group = group_repo.get_by_id(m.group_id)
                if not group:
                    continue
                if group.tournament_id != tournament.id:
                    continue  # Skip matches from other tournaments
                match_label = f"G{group.name}"
                category = group.category
                # Calculate group round number from match position within group
                group_matches_list = sorted(match_repo.get_by_group(m.group_id), key=lambda x: x.match_number or 0)
                players_in_group = len(set([gm.player1_id for gm in group_matches_list] + [gm.player2_id for gm in group_matches_list]))
                matches_per_round = max(1, players_in_group // 2)
                match_index = next((i for i, gm in enumerate(group_matches_list) if gm.id == m.id), 0)
                group_round = (match_index // matches_per_round) + 1
                round_type = f"R{group_round}"  # R1, R2, R3...
            else:
                # Bracket match - must have a bracket created for this category in current tournament
                if not m.category:
                    continue  # Skip bracket matches without category
                if m.category not in bracket_categories:
                    continue  # Skip bracket matches from other tournaments
                match_label = m.round_type or "Bracket"
                category = m.category
                round_type = m.round_type or "Bracket"

            d1 = get_competitor_display(m, 1, player_repo, pair_repo, team_repo)
            d2 = get_competitor_display(m, 2, player_repo, pair_repo, team_repo)

            unscheduled_matches.append({
                "id": m.id,
                "player1": d1.full_name if d1 else "TBD",
                "player2": d2.full_name if d2 else "TBD",
                "player1_id": m.player1_id,
                "player2_id": m.player2_id,
                "player1_country": d1.pais_cd if d1 else "",
                "player2_country": d2.pais_cd if d2 else "",
                "label": match_label,
                "category": category,
                "round_type": round_type,
                "group_id": m.group_id,
            })

        # Build list of all players for search functionality
        all_players = player_repo.get_all(tournament_id=tournament.id)
        players_list = [
            {
                "id": p.id,
                "name": f"{p.nombre} {p.apellido}",
                "category": p.categoria or "",
            }
            for p in all_players
        ]

        # Get categories for filter dropdown
        categories = sorted(tournament_categories)

        context = {
            "request": request,
            "tournament": tournament,
            "session": session_obj,
            "time_slots": time_slots,
            "time_slots_info": time_slots_info,
            "num_tables": num_tables,
            "match_duration": match_duration,
            "grid_data": grid_data,
            "unscheduled_matches": unscheduled_matches,
            "players_list": players_list,
            "categories": categories,
        }

        flash_message = request.session.pop("flash_message", None)
        flash_type = request.session.pop("flash_type", "info")
        if flash_message:
            context["flash_message"] = flash_message
            context["flash_type"] = flash_type

        return render_template("admin_scheduler_grid.html", context)


@app.get("/admin/scheduler/grid/{session_id}/print", response_class=HTMLResponse)
async def scheduler_grid_print(request: Request, session_id: int):
    """Printable version of the scheduling grid."""
    from datetime import datetime

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        from ettem.storage import SessionRepository, ScheduleSlotRepository, TimeSlotRepository

        tournament = tournament_repo.get_current()
        if not tournament:
            return RedirectResponse(url="/", status_code=303)

        session_repo = SessionRepository(session)
        schedule_repo = ScheduleSlotRepository(session)
        time_slot_repo = TimeSlotRepository(session)
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        group_repo = GroupRepository(session)

        session_obj = session_repo.get_by_id(session_id)
        if not session_obj:
            return RedirectResponse(url="/admin/scheduler", status_code=303)

        num_tables = tournament.num_tables or 4
        match_duration = tournament.default_match_duration or 30

        # Get or initialize time slots for this session
        db_time_slots = time_slot_repo.get_by_session(session_id)
        if not db_time_slots:
            db_time_slots = time_slot_repo.initialize_for_session(
                session_id=session_id,
                start_time=session_obj.start_time,
                end_time=session_obj.end_time,
                default_duration=match_duration
            )

        # Build time slots list
        time_slots = [ts.start_time for ts in db_time_slots]

        # Get scheduled slots for this session
        scheduled_slots = schedule_repo.get_by_session(session_id)

        # Build grid data and collect categories
        grid_data = {}
        categories = set()
        total_matches = 0

        for time_slot in time_slots:
            grid_data[time_slot] = {}
            for table in range(1, num_tables + 1):
                grid_data[time_slot][table] = None

        from ettem.webapp.helpers import get_competitor_display
        for slot in scheduled_slots:
            match_orm = match_repo.get_by_id(slot.match_id)
            if match_orm and slot.start_time in grid_data:
                display1 = get_competitor_display(match_orm, 1, player_repo, pair_repo, team_repo)
                display2 = get_competitor_display(match_orm, 2, player_repo, pair_repo, team_repo)

                if match_orm.group_id:
                    group = group_repo.get_by_id(match_orm.group_id)
                    match_label = f"G{group.name}" if group else "Grupo"
                    category = group.category if group else "?"
                else:
                    match_label = match_orm.round_type or "Bracket"
                    category = match_orm.category or "?"

                categories.add(category)
                total_matches += 1

                grid_data[slot.start_time][slot.table_number] = {
                    "match_id": match_orm.id,
                    "player1": display1.full_name if display1 else "TBD",
                    "player2": display2.full_name if display2 else "TBD",
                    "player1_country": display1.pais_cd if display1 else "",
                    "player2_country": display2.pais_cd if display2 else "",
                    "label": match_label,
                    "category": category,
                }

        # Filter out empty time slots (rows with no matches)
        non_empty_time_slots = []
        for time_slot in time_slots:
            has_match = any(grid_data[time_slot][table] is not None for table in range(1, num_tables + 1))
            if has_match:
                non_empty_time_slots.append(time_slot)

        # Category colors for legend
        category_colors = {}
        color_palette = ['#4a90d9', '#48bb78', '#ed8936', '#e53e3e', '#9f7aea', '#38b2ac', '#d69e2e', '#667eea']
        for i, cat in enumerate(sorted(categories)):
            category_colors[cat] = color_palette[i % len(color_palette)]

        context = {
            "request": request,
            "tournament": tournament,
            "session": session_obj,
            "time_slots": non_empty_time_slots,
            "num_tables": num_tables,
            "grid_data": grid_data,
            "total_matches": total_matches,
            "categories": sorted(categories),
            "category_colors": category_colors,
            "generation_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        return render_template("admin_scheduler_print.html", context)


@app.get("/print/scheduler/grid/{session_id}")
async def print_scheduler_grid_pdf(session_id: int):
    """Download PDF for scheduler grid."""
    from datetime import datetime

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        from ettem.storage import SessionRepository, ScheduleSlotRepository, TimeSlotRepository

        tournament = tournament_repo.get_current()
        if not tournament:
            return Response(content="No hay torneo activo", status_code=404)

        session_repo = SessionRepository(session)
        schedule_repo = ScheduleSlotRepository(session)
        time_slot_repo = TimeSlotRepository(session)
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        group_repo = GroupRepository(session)

        session_obj = session_repo.get_by_id(session_id)
        if not session_obj:
            return Response(content="Sesion no encontrada", status_code=404)

        num_tables = tournament.num_tables or 4
        match_duration = tournament.default_match_duration or 30

        # Get or initialize time slots for this session
        db_time_slots = time_slot_repo.get_by_session(session_id)
        if not db_time_slots:
            db_time_slots = time_slot_repo.initialize_for_session(
                session_id=session_id,
                start_time=session_obj.start_time,
                end_time=session_obj.end_time,
                default_duration=match_duration
            )

        # Build time slots list
        time_slots = [ts.start_time for ts in db_time_slots]

        # Get scheduled slots for this session
        scheduled_slots = schedule_repo.get_by_session(session_id)

        # Build grid data and collect categories
        grid_data = {}
        categories = set()
        total_matches = 0

        for time_slot in time_slots:
            grid_data[time_slot] = {}
            for table in range(1, num_tables + 1):
                grid_data[time_slot][table] = None

        from ettem.webapp.helpers import get_competitor_display
        for slot in scheduled_slots:
            match_orm = match_repo.get_by_id(slot.match_id)
            if match_orm and slot.start_time in grid_data:
                display1 = get_competitor_display(match_orm, 1, player_repo, pair_repo, team_repo)
                display2 = get_competitor_display(match_orm, 2, player_repo, pair_repo, team_repo)

                if match_orm.group_id:
                    group = group_repo.get_by_id(match_orm.group_id)
                    match_label = f"G{group.name}" if group else "Grupo"
                    category = group.category if group else "?"
                else:
                    match_label = match_orm.round_type or "Bracket"
                    category = match_orm.category or "?"

                categories.add(category)
                total_matches += 1

                grid_data[slot.start_time][slot.table_number] = {
                    "match_id": match_orm.id,
                    "player1": display1.full_name if display1 else "TBD",
                    "player2": display2.full_name if display2 else "TBD",
                    "player1_country": display1.pais_cd if display1 else "",
                    "player2_country": display2.pais_cd if display2 else "",
                    "label": match_label,
                    "category": category,
                }

        # Filter out empty time slots
        non_empty_time_slots = []
        for time_slot in time_slots:
            has_match = any(grid_data[time_slot][table] is not None for table in range(1, num_tables + 1))
            if has_match:
                non_empty_time_slots.append(time_slot)

        # Category colors for legend
        category_colors = {}
        color_palette = ['#4a90d9', '#48bb78', '#ed8936', '#e53e3e', '#9f7aea', '#38b2ac', '#d69e2e', '#667eea']
        for i, cat in enumerate(sorted(categories)):
            category_colors[cat] = color_palette[i % len(color_palette)]

        context = {
            "tournament_name": tournament.name,
            "session": session_obj,
            "time_slots": non_empty_time_slots,
            "num_tables": num_tables,
            "grid_data": grid_data,
            "total_matches": total_matches,
            "categories": sorted(categories),
            "category_colors": category_colors,
            "generation_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        try:
            pdf_bytes = pdf_generator.generate_scheduler_pdf(context)
            filename = f"programacion_{session_obj.name.replace(' ', '_')}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
        except Exception as e:
            return Response(content=f"Error generando PDF: {str(e)}", status_code=500)


@app.post("/admin/scheduler/timeslot/update-duration")
async def update_timeslot_duration(
    request: Request,
    session_id: int = Form(...),
    slot_number: int = Form(...),
    duration: int = Form(...)
):
    """Update the duration of a time slot and recalculate subsequent slots."""
    with get_db_session() as session:
        from ettem.storage import TimeSlotRepository

        time_slot_repo = TimeSlotRepository(session)

        # Validate duration (minimum 5 minutes, maximum 120 minutes)
        if duration < 5 or duration > 120:
            request.session["flash_message"] = "La duración debe estar entre 5 y 120 minutos"
            request.session["flash_type"] = "error"
            return RedirectResponse(url=f"/admin/scheduler/grid/{session_id}", status_code=303)

        success = time_slot_repo.update_duration(session_id, slot_number, duration)

        if success:
            request.session["flash_message"] = f"Duración actualizada a {duration} minutos"
            request.session["flash_type"] = "success"
        else:
            request.session["flash_message"] = "Error al actualizar la duración"
            request.session["flash_type"] = "error"

        return RedirectResponse(url=f"/admin/scheduler/grid/{session_id}", status_code=303)


@app.post("/admin/scheduler/session/{session_id}/finalize")
async def finalize_session(request: Request, session_id: int):
    """Finalize a scheduling session - marks it as complete and cleans up empty time slots."""
    with get_db_session() as session:
        from ettem.storage import SessionRepository, TimeSlotRepository, ScheduleSlotRepository

        session_repo = SessionRepository(session)
        time_slot_repo = TimeSlotRepository(session)
        schedule_repo = ScheduleSlotRepository(session)

        session_obj = session_repo.get_by_id(session_id)
        if not session_obj:
            request.session["flash_message"] = "Jornada no encontrada"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/scheduler", status_code=303)

        # Get all time slots and scheduled matches
        time_slots = time_slot_repo.get_by_session(session_id)
        scheduled_slots = schedule_repo.get_by_session(session_id)

        # Build set of time slots that have matches
        used_time_slots = {slot.start_time for slot in scheduled_slots}

        # Delete empty time slots
        deleted_count = 0
        for ts in time_slots:
            if ts.start_time not in used_time_slots:
                session.delete(ts)
                deleted_count += 1

        # Mark session as finalized
        session_obj.is_finalized = 1
        session.commit()

        msg = f"Jornada finalizada"
        if deleted_count > 0:
            msg += f" ({deleted_count} bloques vacíos eliminados)"
        request.session["flash_message"] = msg
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/admin/scheduler/grid/{session_id}", status_code=303)


@app.post("/admin/scheduler/session/{session_id}/reopen")
async def reopen_session(request: Request, session_id: int):
    """Reopen a finalized scheduling session for further editing."""
    with get_db_session() as session:
        from ettem.storage import SessionRepository

        session_repo = SessionRepository(session)
        session_obj = session_repo.get_by_id(session_id)

        if not session_obj:
            request.session["flash_message"] = "Jornada no encontrada"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/scheduler", status_code=303)

        session_obj.is_finalized = 0
        session.commit()

        request.session["flash_message"] = "Jornada reabierta para edición"
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/admin/scheduler/grid/{session_id}", status_code=303)


@app.post("/admin/scheduler/session/{session_id}/add-timeslot")
async def add_timeslot(request: Request, session_id: int):
    """Add a new time slot at the end of the session."""
    with get_db_session() as session:
        from ettem.storage import SessionRepository, TimeSlotRepository

        session_repo = SessionRepository(session)
        time_slot_repo = TimeSlotRepository(session)
        tournament_repo = TournamentRepository(session)

        session_obj = session_repo.get_by_id(session_id)
        if not session_obj:
            request.session["flash_message"] = "Jornada no encontrada"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/scheduler", status_code=303)

        tournament = tournament_repo.get_current()
        default_duration = tournament.default_match_duration or 30 if tournament else 30

        # Get existing time slots
        existing_slots = time_slot_repo.get_by_session(session_id)

        if existing_slots:
            # Calculate new slot start time based on last slot
            last_slot = existing_slots[-1]
            last_h, last_m = map(int, last_slot.start_time.split(":"))
            new_start_minutes = last_h * 60 + last_m + last_slot.duration_minutes
            new_slot_number = last_slot.slot_number + 1
        else:
            # No slots exist, start from session start time
            start_h, start_m = map(int, session_obj.start_time.split(":"))
            new_start_minutes = start_h * 60 + start_m
            new_slot_number = 0

        new_h = new_start_minutes // 60
        new_m = new_start_minutes % 60
        new_start_time = f"{new_h:02d}:{new_m:02d}"

        # Create the new time slot
        time_slot_repo.create(
            session_id=session_id,
            slot_number=new_slot_number,
            start_time=new_start_time,
            duration_minutes=default_duration
        )

        request.session["flash_message"] = f"Bloque añadido: {new_start_time}"
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/admin/scheduler/grid/{session_id}", status_code=303)


@app.post("/admin/scheduler/slot/assign")
async def assign_match_to_slot(
    request: Request,
    session_id: int = Form(...),
    match_id: int = Form(...),
    table_number: int = Form(...),
    start_time: str = Form(...)
):
    """Assign a match to a specific table and time slot."""
    with get_db_session() as session:
        from ettem.storage import ScheduleSlotRepository

        schedule_repo = ScheduleSlotRepository(session)

        # Check if match is already scheduled
        existing = schedule_repo.get_by_match(match_id)
        if existing:
            # Update existing slot
            existing.session_id = session_id
            existing.table_number = table_number
            existing.start_time = start_time
            schedule_repo.update(existing)
        else:
            # Create new slot
            schedule_repo.create(
                session_id=session_id,
                match_id=match_id,
                table_number=table_number,
                start_time=start_time
            )

        return {"status": "ok"}


@app.post("/admin/scheduler/slot/{slot_id}/remove")
async def remove_slot_assignment(request: Request, slot_id: int):
    """Remove a match from its scheduled slot (back to unscheduled)."""
    with get_db_session() as session:
        from ettem.storage import ScheduleSlotRepository

        schedule_repo = ScheduleSlotRepository(session)
        schedule_repo.delete(slot_id)

        return {"status": "ok"}


# ============================================================================
# Live Results Entry (Panel de Operación)
# ============================================================================


@app.get("/admin/live-results", response_class=HTMLResponse)
async def admin_live_results(request: Request, category: Optional[str] = None):
    """Live results entry panel - shows matches grouped by scheduled time."""
    from ettem.storage import SessionRepository, ScheduleSlotRepository

    session = get_db_session()
    try:
        tournament_repo = TournamentRepository(session)
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        group_repo = GroupRepository(session)
        schedule_repo = ScheduleSlotRepository(session)
        session_repo = SessionRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        if not current_tournament:
            return render_template("admin_live_results.html", {
                "request": request,
                "error": "No hay torneo activo",
                "time_slots": [],
                "categories": [],
                "selected_category": None,
            })

        tournament_id = current_tournament.id

        # Get categories
        all_players = player_repo.get_all(tournament_id=tournament_id)
        categories = sorted(set(p.categoria for p in all_players))

        # Get all scheduled slots
        all_slots = schedule_repo.get_all()

        # Build a lookup of match_id -> schedule info
        schedule_lookup = {}
        for slot in all_slots:
            schedule_lookup[slot.match_id] = {
                "table_number": slot.table_number,
                "start_time": slot.start_time,
                "session_id": slot.session_id,
            }

        # Get all group matches for the tournament (filtered by category if provided)
        groups = group_repo.get_all(tournament_id=tournament_id)
        if category:
            groups = [g for g in groups if g.category == category]

        group_ids = {g.id for g in groups}
        group_lookup = {g.id: g for g in groups}

        # Get all matches for these groups
        from ettem.webapp.helpers import get_competitor_display
        pair_repo = PairRepository(session)
        matches_data = []
        for group in groups:
            group_matches = match_repo.get_by_group(group.id)
            for match in group_matches:
                player1 = get_competitor_display(match, 1, player_repo, pair_repo, team_repo)
                player2 = get_competitor_display(match, 2, player_repo, pair_repo, team_repo)

                schedule_info = schedule_lookup.get(match.id)

                matches_data.append({
                    "match": match,
                    "player1": player1,
                    "player2": player2,
                    "group": group,
                    "schedule": schedule_info,
                    "is_scheduled": schedule_info is not None,
                    "is_bracket": False,
                })

        # Also include bracket matches (knockout phase)
        bracket_repo = BracketRepository(session)
        all_bracket_matches = match_repo.get_all()

        # Get categories from groups for filtering
        group_categories = set(g.category for g in groups)

        for match in all_bracket_matches:
            # Only bracket matches (no group_id) for current tournament
            if match.group_id is not None:
                continue
            if match.tournament_id != tournament_id:
                continue
            # Filter by category if provided
            if category and match.category != category:
                continue
            # Skip if category not in our groups (shouldn't happen but safety check)
            if match.category not in group_categories and category is None:
                continue

            player1 = get_competitor_display(match, 1, player_repo, pair_repo, team_repo)
            player2 = get_competitor_display(match, 2, player_repo, pair_repo, team_repo)

            schedule_info = schedule_lookup.get(match.id)

            # Create a display name for bracket round
            round_names = {
                'R128': 'R128', 'R64': 'R64', 'R32': 'R32', 'R16': 'R16',
                'QF': 'Cuartos', 'SF': 'Semifinal', 'F': 'Final'
            }
            round_display = round_names.get(match.round_type, match.round_type)

            matches_data.append({
                "match": match,
                "player1": player1,
                "player2": player2,
                "group": None,  # No group for bracket matches
                "bracket_round": round_display,
                "bracket_category": match.category,
                "schedule": schedule_info,
                "is_scheduled": schedule_info is not None,
                "is_bracket": True,
            })

        # Group matches by session and time slot
        # Structure: { session_id: { time_str: [matches] } }
        sessions_time_slots = {}
        unscheduled = []

        for md in matches_data:
            if md["is_scheduled"]:
                session_id = md["schedule"]["session_id"]
                time_key = md["schedule"]["start_time"]

                if session_id not in sessions_time_slots:
                    sessions_time_slots[session_id] = {}
                if time_key not in sessions_time_slots[session_id]:
                    sessions_time_slots[session_id][time_key] = []
                sessions_time_slots[session_id][time_key].append(md)
            else:
                unscheduled.append(md)

        # Get session info for display
        session_lookup = {}
        for slot in all_slots:
            if slot.session_id not in session_lookup:
                sess = session_repo.get_by_id(slot.session_id)
                if sess:
                    session_lookup[slot.session_id] = sess

        # Build data structure grouped by session
        time_slots_data = []

        for session_id in sorted(sessions_time_slots.keys()):
            session_slots = sessions_time_slots[session_id]
            session_info = session_lookup.get(session_id)
            session_name = session_info.name if session_info else f"Sesión {session_id}"

            # Sort time slots within this session
            sorted_slots = sorted(session_slots.items(), key=lambda x: x[0])

            # Build slot data for this session
            session_slot_data = []
            for time_str, matches in sorted_slots:
                # Sort by table number
                matches.sort(key=lambda x: x["schedule"]["table_number"])
                completed_count = sum(1 for m in matches if m["match"].status != MatchStatus.PENDING.value and m["match"].status != MatchStatus.PENDING)
                total_count = len(matches)
                session_slot_data.append({
                    "time": time_str,
                    "matches": matches,
                    "completed": completed_count,
                    "total": total_count,
                    "status": "pending",
                    "session_id": session_id,
                    "session_name": session_name,
                })

            # Determine status based on completion pattern WITHIN THIS SESSION ONLY
            # Logic: If a later slot has completions but an earlier slot has pending matches,
            #        the earlier slot is "delayed"

            # Find the latest slot index that has any completions (within this session)
            latest_with_completion = -1
            for i, slot in enumerate(session_slot_data):
                if slot["completed"] > 0:
                    latest_with_completion = i

            # Find the first slot that has pending matches (within this session)
            first_with_pending = -1
            for i, slot in enumerate(session_slot_data):
                if slot["completed"] < slot["total"]:
                    first_with_pending = i
                    break

            # Assign statuses (within this session)
            for i, slot in enumerate(session_slot_data):
                if slot["completed"] == slot["total"]:
                    slot["status"] = "completed"
                elif i < latest_with_completion:
                    # Has pending but a later slot in SAME SESSION has completions = delayed
                    slot["status"] = "delayed"
                elif i == first_with_pending:
                    slot["status"] = "current"
                else:
                    slot["status"] = "future"

            # Add all slots from this session to the main list
            time_slots_data.extend(session_slot_data)

        # Find current slot index for display focus (first "current" or first with pending)
        current_slot_index = 0
        for i, slot in enumerate(time_slots_data):
            if slot["status"] == "current":
                current_slot_index = i
                break
            elif slot["completed"] < slot["total"]:
                current_slot_index = i
                break

        return render_template("admin_live_results.html", {
            "request": request,
            "time_slots": time_slots_data,
            "unscheduled": unscheduled,
            "categories": categories,
            "selected_category": category,
            "current_slot_index": current_slot_index,
            "tournament": current_tournament,
        })

    finally:
        session.close()


# ============================================================================
# Table Configuration Routes (V2.2 - Live Display / Referee Scoreboard)
# ============================================================================


@app.get("/admin/table-config", response_class=HTMLResponse)
async def admin_table_config(request: Request):
    """Table configuration page - configure tables for referees and public display."""
    from ettem.storage import TableConfigRepository, TableLockRepository

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()

        if not tournament:
            return render_template("admin_table_config.html", {
                "request": request,
                "tournament": None,
            })

        table_config_repo = TableConfigRepository(session)
        table_lock_repo = TableLockRepository(session)

        tables = table_config_repo.get_by_tournament(tournament.id)

        # Count available vs locked tables
        available_count = 0
        locked_count = 0
        for table in tables:
            if not table.is_active:
                continue
            if table.lock:
                locked_count += 1
            else:
                available_count += 1

        # Get base URL with local IP for network access
        local_ip = get_local_ip()
        port = request.url.port or 8000
        base_url = f"http://{local_ip}:{port}"

        context = {
            "request": request,
            "tournament": tournament,
            "tables": tables,
            "available_count": available_count,
            "locked_count": locked_count,
            "base_url": base_url,
        }

        flash_message = request.session.pop("flash_message", None)
        if flash_message:
            context["flash_message"] = flash_message
            context["flash_type"] = request.session.pop("flash_type", "info")

        return render_template("admin_table_config.html", context)


@app.post("/admin/table-config/initialize")
async def admin_table_config_initialize(request: Request, num_tables: int = Form(...), default_mode: str = Form("result_per_set")):
    """Initialize tables for the tournament."""
    from ettem.storage import TableConfigRepository

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()

        if not tournament:
            return RedirectResponse(url="/tournaments", status_code=303)

        table_config_repo = TableConfigRepository(session)
        table_config_repo.initialize_tables(tournament.id, num_tables, default_mode)

        request.session["flash_message"] = "Mesas inicializadas correctamente"
        request.session["flash_type"] = "success"

    return RedirectResponse(url="/admin/table-config", status_code=303)


@app.post("/admin/table-config/add")
async def admin_table_config_add(request: Request, name: str = Form(None), mode: str = Form("result_per_set")):
    """Add a new table."""
    from ettem.storage import TableConfigRepository

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()

        if not tournament:
            return RedirectResponse(url="/tournaments", status_code=303)

        table_config_repo = TableConfigRepository(session)
        existing_tables = table_config_repo.get_by_tournament(tournament.id)

        # Determine next table number
        next_number = 1
        if existing_tables:
            next_number = max(t.table_number for t in existing_tables) + 1

        table_config_repo.create(tournament.id, next_number, name or f"Mesa {next_number}", mode)

        request.session["flash_message"] = f"Mesa {next_number} creada"
        request.session["flash_type"] = "success"

    return RedirectResponse(url="/admin/table-config", status_code=303)


@app.post("/admin/table-config/{table_id}/mode")
async def admin_table_config_mode(request: Request, table_id: int, mode: str = Form(...)):
    """Update table mode."""
    from ettem.storage import TableConfigRepository

    with get_db_session() as session:
        table_config_repo = TableConfigRepository(session)
        table = table_config_repo.get_by_id(table_id)

        if table:
            table.mode = mode
            table_config_repo.update(table)
            request.session["flash_message"] = "Modo actualizado"
            request.session["flash_type"] = "success"

    return RedirectResponse(url="/admin/table-config", status_code=303)


@app.post("/admin/table-config/{table_id}/unlock")
async def admin_table_config_unlock(request: Request, table_id: int):
    """Force unlock a table (admin action)."""
    from ettem.storage import TableLockRepository

    with get_db_session() as session:
        table_lock_repo = TableLockRepository(session)
        if table_lock_repo.force_release(table_id):
            request.session["flash_message"] = "Mesa desbloqueada"
            request.session["flash_type"] = "success"
        else:
            request.session["flash_message"] = "La mesa no estaba bloqueada"
            request.session["flash_type"] = "info"

    return RedirectResponse(url="/admin/table-config", status_code=303)


@app.post("/admin/table-config/{table_id}/toggle")
async def admin_table_config_toggle(request: Request, table_id: int):
    """Toggle table active status."""
    from ettem.storage import TableConfigRepository

    with get_db_session() as session:
        table_config_repo = TableConfigRepository(session)
        table = table_config_repo.get_by_id(table_id)

        if table:
            table.is_active = not table.is_active
            table_config_repo.update(table)
            status = "activada" if table.is_active else "desactivada"
            request.session["flash_message"] = f"Mesa {status}"
            request.session["flash_type"] = "success"

    return RedirectResponse(url="/admin/table-config", status_code=303)


@app.get("/admin/table-config/qr-codes", response_class=HTMLResponse)
async def admin_table_config_qr_codes(request: Request):
    """Print page for QR codes."""
    from ettem.storage import TableConfigRepository

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()

        if not tournament:
            return RedirectResponse(url="/tournaments", status_code=303)

        table_config_repo = TableConfigRepository(session)
        tables = table_config_repo.get_by_tournament(tournament.id, active_only=True)

        # Generate base URL for QR codes using local IP for network access
        local_ip = get_local_ip()
        port = request.url.port or 8000
        base_url = f"http://{local_ip}:{port}"

        tables_data = []
        for table in tables:
            tables_data.append({
                "table": table,
                "url": f"{base_url}/mesa/{table.table_number}",
            })

        return render_template("admin_table_qr_codes.html", {
            "request": request,
            "tournament": tournament,
            "tables": tables_data,
            "base_url": base_url,
        })


# ============================================================================
# Referee Scoreboard Routes (V2.2 - /mesa/{n})
# ============================================================================


def generate_session_token():
    """Generate a unique session token for table lock."""
    import secrets
    return secrets.token_hex(32)


@app.get("/mesa/{table_number}", response_class=HTMLResponse)
async def referee_scoreboard(request: Request, table_number: int):
    """Referee scoreboard page for a specific table."""
    from ettem.storage import TableConfigRepository, TableLockRepository, LiveScoreRepository, ScheduleSlotRepository, SessionRepository

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()

        if not tournament:
            return render_template("referee_scoreboard.html", {
                "request": request,
                "error": "No hay torneo activo",
                "table": None,
                "match": None,
            })

        table_config_repo = TableConfigRepository(session)
        table = table_config_repo.get_by_tournament_and_number(tournament.id, table_number)

        if not table:
            return render_template("referee_scoreboard.html", {
                "request": request,
                "error": f"Mesa {table_number} no encontrada",
                "table": None,
                "match": None,
            })

        if not table.is_active:
            return render_template("referee_scoreboard.html", {
                "request": request,
                "error": "Esta mesa está desactivada",
                "table": table,
                "match": None,
            })

        # Try to acquire lock or check existing lock
        table_lock_repo = TableLockRepository(session)

        # Get or create session token from cookie
        session_token = request.cookies.get(f"mesa_{table_number}_token")
        if not session_token:
            session_token = generate_session_token()

        # Try to acquire lock
        device_info = request.headers.get("User-Agent", "Unknown")[:200]
        lock = table_lock_repo.acquire_lock(table.id, session_token, device_info)

        if not lock:
            # Table is locked by another device
            return render_template("referee_scoreboard.html", {
                "request": request,
                "table": table,
                "match": None,
                "locked": True,
                "session_token": session_token,
            })

        # Find current match for this table
        match = None
        player1 = None
        player2 = None
        live_score = None
        completed_sets = []
        available_matches = []

        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        schedule_repo = ScheduleSlotRepository(session)
        group_repo = GroupRepository(session)
        from ettem.webapp.helpers import get_competitor_display

        # First check if there's a match assigned via lock
        if lock.current_match_id:
            match = match_repo.get_by_id(lock.current_match_id)
            # If match is completed, clear it from lock
            if match and match.status in (MatchStatus.COMPLETED.value, MatchStatus.WALKOVER.value, "completed", "walkover"):
                lock.current_match_id = None
                table_lock_repo.update_activity(table.id, session_token)
                match = None

        # If no match from lock, get all available matches for this table
        if not match:
            # Get today's date for filtering sessions
            from datetime import date
            today = date.today()

            # Get sessions for today only
            session_repo = SessionRepository(session)
            today_sessions = [s for s in session_repo.get_by_tournament(tournament.id)
                              if s.date and s.date.date() == today]
            today_session_ids = {s.id for s in today_sessions}

            # Find all matches scheduled for this table that are pending or in progress (today only)
            all_slots = schedule_repo.get_all()
            for slot in all_slots:
                # Filter by table number and today's sessions
                if slot.table_number == table_number and slot.session_id in today_session_ids:
                    m = match_repo.get_by_id(slot.match_id)
                    # Only show matches with both players assigned (no TBD/BYE)
                    if m and m.player1_id and m.player2_id and m.status in (MatchStatus.PENDING.value, MatchStatus.IN_PROGRESS.value, "pending", "in_progress"):
                        cd1 = get_competitor_display(m, 1, player_repo, pair_repo, team_repo)
                        cd2 = get_competitor_display(m, 2, player_repo, pair_repo, team_repo)

                        # Get group/round info
                        round_name = m.round_name or ""
                        if m.group_id:
                            group = group_repo.get_by_id(m.group_id)
                            if group:
                                round_name = f"Grupo {group.name}"

                        available_matches.append({
                            "id": m.id,
                            "player1_name": cd1.full_name,
                            "player1_country": cd1.pais_cd,
                            "player2_name": cd2.full_name,
                            "player2_country": cd2.pais_cd,
                            "category": m.category or "",
                            "round_name": round_name,
                            "start_time": slot.start_time,
                        })

        if match:
            player1 = get_competitor_display(match, 1, player_repo, pair_repo, team_repo)
            player2 = get_competitor_display(match, 2, player_repo, pair_repo, team_repo)

            # If match doesn't have category, try to get it from the group
            if not match.category and match.group_id:
                group = group_repo.get_by_id(match.group_id)
                if group and group.category:
                    match.category = group.category

            # Get live score
            live_score_repo = LiveScoreRepository(session)
            live_score = live_score_repo.get_by_match(match.id)

            # If no live score exists and match is pending, create one
            if not live_score and match.status in (MatchStatus.PENDING.value, "pending"):
                live_score = live_score_repo.create(match.id, table.id)
                # Update match status to in_progress
                match.status = MatchStatus.IN_PROGRESS.value
                match_repo.update(match)

            # Get completed sets from match
            if match.sets:
                for s in match.sets:
                    completed_sets.append({
                        "set_number": s.get("set_number", len(completed_sets) + 1),
                        "player1_points": s.get("player1_points", 0),
                        "player2_points": s.get("player2_points", 0),
                    })

        response = render_template("referee_scoreboard.html", {
            "request": request,
            "table": table,
            "match": match,
            "player1": player1,
            "player2": player2,
            "live_score": live_score,
            "completed_sets": completed_sets,
            "session_token": session_token,
            "locked": False,
            "available_matches": available_matches,
        })

        # Set cookie with session token
        response.set_cookie(f"mesa_{table_number}_token", session_token, max_age=86400)  # 24 hours
        return response


@app.post("/mesa/{table_number}/select")
async def referee_select_match(request: Request, table_number: int, match_id: int = Form(...)):
    """Select a match to referee."""
    from ettem.storage import TableConfigRepository, TableLockRepository, LiveScoreRepository

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()

        if not tournament:
            return RedirectResponse(url=f"/mesa/{table_number}", status_code=303)

        table_config_repo = TableConfigRepository(session)
        table = table_config_repo.get_by_tournament_and_number(tournament.id, table_number)

        if not table:
            return RedirectResponse(url=f"/mesa/{table_number}", status_code=303)

        # Get session token from cookie
        session_token = request.cookies.get(f"mesa_{table_number}_token")
        if not session_token:
            return RedirectResponse(url=f"/mesa/{table_number}", status_code=303)

        # Verify lock ownership
        table_lock_repo = TableLockRepository(session)
        lock = table_lock_repo.get_by_table(table.id)

        if not lock or lock.session_token != session_token:
            return RedirectResponse(url=f"/mesa/{table_number}", status_code=303)

        # Verify match exists and is pending
        match_repo = MatchRepository(session)
        match = match_repo.get_by_id(match_id)

        if not match or match.status not in (MatchStatus.PENDING.value, MatchStatus.IN_PROGRESS.value, "pending", "in_progress"):
            return RedirectResponse(url=f"/mesa/{table_number}", status_code=303)

        # Set current match on lock
        table_lock_repo.set_current_match(table.id, session_token, match_id)

        # Create live score if needed
        live_score_repo = LiveScoreRepository(session)
        live_score = live_score_repo.get_by_match(match_id)
        if not live_score:
            live_score_repo.create(match_id, table.id)

        # Update match status
        if match.status in (MatchStatus.PENDING.value, "pending"):
            match.status = MatchStatus.IN_PROGRESS.value
            match_repo.update(match)

    return RedirectResponse(url=f"/mesa/{table_number}", status_code=303)


@app.post("/mesa/{table_number}/clear")
async def referee_clear_match(request: Request, table_number: int, session_token: str = Form(None)):
    """Clear current match and return to match selection."""
    from datetime import datetime
    from ettem.storage import TableConfigRepository, TableLockRepository

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()

        if not tournament:
            return {"success": False}

        table_config_repo = TableConfigRepository(session)
        table = table_config_repo.get_by_tournament_and_number(tournament.id, table_number)

        if not table:
            return {"success": False}

        # Get session token from form or cookie
        if not session_token:
            session_token = request.cookies.get(f"mesa_{table_number}_token")

        if not session_token:
            return {"success": False}

        # Verify lock ownership
        table_lock_repo = TableLockRepository(session)
        lock = table_lock_repo.get_by_table(table.id)

        if not lock or lock.session_token != session_token:
            return {"success": False}

        # Clear current match from lock
        lock.current_match_id = None
        lock.last_activity = datetime.utcnow()
        session.commit()

    return {"success": True}


@app.post("/mesa/{table_number}/set")
async def referee_save_set(
    request: Request,
    table_number: int,
    p1_score: int = Form(...),
    p2_score: int = Form(...),
    session_token: str = Form(None)
):
    """Save a completed set result."""
    from ettem.storage import TableConfigRepository, TableLockRepository, LiveScoreRepository
    from ettem.validation import validate_tt_set
    import json

    # Validate set score
    is_valid, error = validate_tt_set(p1_score, p2_score)
    if not is_valid:
        return {"success": False, "error": error}

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()

        if not tournament:
            return {"success": False, "error": "No hay torneo activo"}

        table_config_repo = TableConfigRepository(session)
        table = table_config_repo.get_by_tournament_and_number(tournament.id, table_number)

        if not table:
            return {"success": False, "error": "Mesa no encontrada"}

        # Verify session token
        table_lock_repo = TableLockRepository(session)
        lock = table_lock_repo.get_by_table(table.id)

        if not lock:
            return {"success": False, "error": "Mesa no está bloqueada"}

        # Get token from form or cookie
        if not session_token:
            session_token = request.cookies.get(f"mesa_{table_number}_token")

        if lock.session_token != session_token:
            return {"success": False, "error": "Token de sesión inválido"}

        if not lock.current_match_id:
            return {"success": False, "error": "No hay partido activo"}

        # Get match and update
        match_repo = MatchRepository(session)
        match = match_repo.get_by_id(lock.current_match_id)

        if not match:
            return {"success": False, "error": "Partido no encontrado"}

        # Get current sets
        current_sets = match.sets or []
        set_number = len(current_sets) + 1

        # Add new set
        new_set = {
            "set_number": set_number,
            "player1_points": p1_score,
            "player2_points": p2_score,
        }
        current_sets.append(new_set)

        # Update match
        match.sets_json = json.dumps(current_sets)

        # Count sets won
        p1_sets = sum(1 for s in current_sets if s["player1_points"] > s["player2_points"])
        p2_sets = sum(1 for s in current_sets if s["player2_points"] > s["player1_points"])

        # Check if match is complete
        sets_to_win = (match.best_of // 2) + 1
        match_complete = False

        if p1_sets >= sets_to_win:
            match.winner_id = match.player1_id
            match.status = MatchStatus.COMPLETED.value
            match_complete = True
        elif p2_sets >= sets_to_win:
            match.winner_id = match.player2_id
            match.status = MatchStatus.COMPLETED.value
            match_complete = True

        match_repo.update(match)

        # Update live score
        live_score_repo = LiveScoreRepository(session)
        live_score = live_score_repo.get_by_match(match.id)

        if live_score:
            if match_complete:
                # Delete live score when match is complete
                live_score_repo.delete(match.id)
            else:
                # Update live score for next set
                live_score_repo.complete_set(match.id, p1_score, p2_score)

        # If match complete, clear current match from lock
        if match_complete:
            lock.current_match_id = None
            table_lock_repo.update_activity(table.id, session_token)

        return {
            "success": True,
            "match_complete": match_complete,
            "p1_sets": p1_sets,
            "p2_sets": p2_sets,
        }


@app.get("/mesa/{table_number}/walkover", response_class=HTMLResponse)
async def referee_walkover_page(request: Request, table_number: int):
    """Walkover confirmation page."""
    from ettem.storage import TableConfigRepository, TableLockRepository

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()

        if not tournament:
            return RedirectResponse(url=f"/mesa/{table_number}", status_code=303)

        table_config_repo = TableConfigRepository(session)
        table = table_config_repo.get_by_tournament_and_number(tournament.id, table_number)

        if not table:
            return RedirectResponse(url=f"/mesa/{table_number}", status_code=303)

        table_lock_repo = TableLockRepository(session)
        lock = table_lock_repo.get_by_table(table.id)

        if not lock or not lock.current_match_id:
            return RedirectResponse(url=f"/mesa/{table_number}", status_code=303)

        match_repo = MatchRepository(session)
        match = match_repo.get_by_id(lock.current_match_id)

        player_repo = PlayerRepository(session)
        player1 = player_repo.get_by_id(match.player1_id) if match and match.player1_id else None
        player2 = player_repo.get_by_id(match.player2_id) if match and match.player2_id else None

        # Simple walkover selection page
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Walkover - Mesa {table_number}</title>
            <style>
                body {{ font-family: sans-serif; padding: 1rem; max-width: 500px; margin: 0 auto; }}
                h1 {{ font-size: 1.25rem; }}
                .btn {{ display: block; width: 100%; padding: 1rem; margin: 0.5rem 0; font-size: 1rem; border: none; border-radius: 8px; cursor: pointer; }}
                .btn-primary {{ background: #2563eb; color: white; }}
                .btn-secondary {{ background: #e5e7eb; color: #1f2937; }}
            </style>
        </head>
        <body>
            <h1>Seleccionar Ganador por Walkover</h1>
            <p>Selecciona quién gana porque el oponente no se presentó:</p>
            <form action="/mesa/{table_number}/walkover" method="post">
                <button type="submit" name="winner_id" value="{match.player1_id}" class="btn btn-primary">
                    {player1.full_name if player1 else 'Jugador 1'} gana
                </button>
                <button type="submit" name="winner_id" value="{match.player2_id}" class="btn btn-primary">
                    {player2.full_name if player2 else 'Jugador 2'} gana
                </button>
                <a href="/mesa/{table_number}" class="btn btn-secondary" style="text-align: center; text-decoration: none;">Cancelar</a>
            </form>
        </body>
        </html>
        """)


@app.post("/mesa/{table_number}/walkover")
async def referee_walkover_submit(request: Request, table_number: int, winner_id: int = Form(...)):
    """Submit walkover result."""
    from ettem.storage import TableConfigRepository, TableLockRepository, LiveScoreRepository

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()

        if not tournament:
            return RedirectResponse(url=f"/mesa/{table_number}", status_code=303)

        table_config_repo = TableConfigRepository(session)
        table = table_config_repo.get_by_tournament_and_number(tournament.id, table_number)

        if not table:
            return RedirectResponse(url=f"/mesa/{table_number}", status_code=303)

        table_lock_repo = TableLockRepository(session)
        lock = table_lock_repo.get_by_table(table.id)

        if not lock or not lock.current_match_id:
            return RedirectResponse(url=f"/mesa/{table_number}", status_code=303)

        match_repo = MatchRepository(session)
        match = match_repo.get_by_id(lock.current_match_id)

        if match:
            # Update match as walkover
            match.winner_id = winner_id
            match.status = MatchStatus.WALKOVER.value
            match_repo.update(match)

            # Delete live score
            live_score_repo = LiveScoreRepository(session)
            live_score_repo.delete(match.id)

            # Clear current match from lock
            lock.current_match_id = None
            table_lock_repo.update_activity(table.id, lock.session_token)

    return RedirectResponse(url=f"/mesa/{table_number}", status_code=303)


# ============================================================================
# Live Score API Routes (V2.2)
# ============================================================================


@app.post("/api/live-score/{match_id}")
async def api_update_live_score(request: Request, match_id: int):
    """Update live score for public display (point-by-point mode)."""
    from ettem.storage import LiveScoreRepository, TableLockRepository

    try:
        data = await request.json()
        session_token = data.get("session_token")
        p1_points = data.get("p1_points", 0)
        p2_points = data.get("p2_points", 0)

        with get_db_session() as session:
            live_score_repo = LiveScoreRepository(session)
            live_score = live_score_repo.get_by_match(match_id)

            if not live_score:
                return {"success": False, "error": "Live score not found"}

            # Validate table lock token
            if live_score.table_id:
                table_lock_repo = TableLockRepository(session)
                lock = table_lock_repo.get_by_table(live_score.table_id)

                if not lock:
                    return {"success": False, "error": "Mesa no está bloqueada"}

                if not session_token:
                    session_token = request.cookies.get(f"mesa_{live_score.table_id}_token")

                if lock.session_token != session_token:
                    return {"success": False, "error": "Token de sesión inválido"}

            result = live_score_repo.update_score(match_id, p1_points, p2_points)

            if result:
                return {"success": True}
            return {"success": False, "error": "Failed to update score"}

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/table/{table_id}/heartbeat")
async def api_table_heartbeat(request: Request, table_id: int):
    """Keep table lock alive."""
    from ettem.storage import TableLockRepository

    try:
        data = await request.json()
        session_token = data.get("session_token")

        if not session_token:
            return {"success": False, "error": "No session token"}

        with get_db_session() as session:
            table_lock_repo = TableLockRepository(session)
            if table_lock_repo.update_activity(table_id, session_token):
                return {"success": True}
            return {"success": False, "error": "Lock not found or token mismatch"}

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/display", response_class=HTMLResponse)
async def public_display(request: Request):
    """Public display page for TV/monitors."""
    from ettem.storage import LiveScoreRepository, ScheduleSlotRepository, TableConfigRepository
    from datetime import datetime

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()

        if not tournament:
            return render_template("public_display.html", {
                "request": request,
                "tournament": None,
                "live_matches": [],
                "recent_results": [],
                "upcoming_matches": [],
                "now": datetime.now(),
            })

        live_score_repo = LiveScoreRepository(session)
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)
        group_repo = GroupRepository(session)
        table_config_repo = TableConfigRepository(session)

        # Get live matches
        live_scores = live_score_repo.get_all_active()
        live_matches = []

        for score in live_scores:
            match = match_repo.get_by_id(score.match_id)
            if not match:
                continue

            # Filter by current tournament
            if match.tournament_id != tournament.id:
                continue

            c1 = get_competitor_display(match, 1, player_repo, pair_repo, team_repo)
            c2 = get_competitor_display(match, 2, player_repo, pair_repo, team_repo)

            # Get table number
            table_number = None
            if score.table_id:
                table = table_config_repo.get_by_id(score.table_id)
                if table:
                    table_number = table.table_number

            live_matches.append({
                "match_id": match.id,
                "table_number": table_number or match.table_number,
                "player1": {
                    "name": c1.full_name,
                    "country": c1.pais_cd,
                },
                "player2": {
                    "name": c2.full_name,
                    "country": c2.pais_cd,
                },
                "p1_sets": score.player1_sets,
                "p2_sets": score.player2_sets,
                "p1_points": score.player1_points,
                "p2_points": score.player2_points,
                "current_set": score.current_set,
                "category": match.category or "",
                "round": match.round_name,
            })

        # Get recent results (last 10 completed matches)
        all_matches = match_repo.get_all()
        completed = [m for m in all_matches if m.status in (MatchStatus.COMPLETED.value, MatchStatus.WALKOVER.value, "completed", "walkover")]
        completed.sort(key=lambda m: m.updated_at if m.updated_at else m.created_at, reverse=True)
        recent_results = []

        for match in completed[:10]:
            c1 = get_competitor_display(match, 1, player_repo, pair_repo, team_repo)
            c2 = get_competitor_display(match, 2, player_repo, pair_repo, team_repo)

            # Calculate score
            sets = match.sets or []
            p1_sets = sum(1 for s in sets if s.get("player1_points", 0) > s.get("player2_points", 0))
            p2_sets = sum(1 for s in sets if s.get("player2_points", 0) > s.get("player1_points", 0))

            recent_results.append({
                "match_id": match.id,
                "player1_id": match.competitor1_id,
                "player2_id": match.competitor2_id,
                "player1_name": c1.full_name,
                "player2_name": c2.full_name,
                "winner_id": match.winner_id,
                "score": f"{p1_sets}-{p2_sets}",
                "category": match.category or "",
                "round": match.round_name,
            })

        # Get upcoming matches (pending, scheduled)
        schedule_repo = ScheduleSlotRepository(session)
        pending = [m for m in all_matches if m.status in (MatchStatus.PENDING.value, "pending")]
        upcoming_matches = []

        for match in pending[:15]:
            c1 = get_competitor_display(match, 1, player_repo, pair_repo, team_repo)
            c2 = get_competitor_display(match, 2, player_repo, pair_repo, team_repo)

            # Get schedule info
            schedule = schedule_repo.get_by_match(match.id)

            upcoming_matches.append({
                "match_id": match.id,
                "player1_name": c1.full_name,
                "player2_name": c2.full_name,
                "category": match.category or "",
                "round": match.round_name,
                "table_number": schedule.table_number if schedule else None,
                "time": schedule.start_time if schedule else None,
            })

        # Rotate content every 5 seconds (matches the auto-refresh)
        # This shows different results/upcoming if there are more than fit on screen
        now = datetime.now()
        rotation_cycle = (now.second // 5) % 3  # 0, 1, or 2

        results_per_page = 5
        upcoming_per_page = 5

        # Rotate results if there are more than one page
        results_offset = (rotation_cycle * results_per_page) % max(len(recent_results), 1)
        results_to_show = recent_results[results_offset:results_offset + results_per_page]
        if len(results_to_show) < results_per_page:
            results_to_show = recent_results[:results_per_page]

        # Rotate upcoming if there are more than one page
        upcoming_offset = (rotation_cycle * upcoming_per_page) % max(len(upcoming_matches), 1)
        upcoming_to_show = upcoming_matches[upcoming_offset:upcoming_offset + upcoming_per_page]
        if len(upcoming_to_show) < upcoming_per_page:
            upcoming_to_show = upcoming_matches[:upcoming_per_page]

        return render_template("public_display.html", {
            "request": request,
            "tournament": tournament,
            "live_matches": live_matches[:4],  # Max 4 live matches on display
            "recent_results": results_to_show,
            "upcoming_matches": upcoming_to_show,
            "now": now,
        })


@app.get("/api/live-scores")
async def api_get_live_scores():
    """Get all live scores for public display."""
    from ettem.storage import LiveScoreRepository

    with get_db_session() as session:
        tournament_repo = TournamentRepository(session)
        tournament = tournament_repo.get_current()
        live_score_repo = LiveScoreRepository(session)
        match_repo = MatchRepository(session)
        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        team_repo = TeamRepository(session)

        scores = live_score_repo.get_all_active()

        result = []
        for score in scores:
            match = match_repo.get_by_id(score.match_id)
            if not match:
                continue

            # Filter by current tournament
            if tournament and match.tournament_id != tournament.id:
                continue

            c1 = get_competitor_display(match, 1, player_repo, pair_repo, team_repo)
            c2 = get_competitor_display(match, 2, player_repo, pair_repo, team_repo)

            result.append({
                "match_id": score.match_id,
                "table_id": score.table_id,
                "player1": {
                    "id": c1.id,
                    "name": c1.full_name,
                    "country": c1.pais_cd,
                },
                "player2": {
                    "id": c2.id,
                    "name": c2.full_name,
                    "country": c2.pais_cd,
                },
                "current_set": score.current_set,
                "p1_points": score.player1_points,
                "p2_points": score.player2_points,
                "p1_sets": score.player1_sets,
                "p2_sets": score.player2_sets,
                "category": match.category,
                "round": match.round_name or match.round_type,
            })

        return {"scores": result}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

