"""FastAPI web application for Easy Table Tennis Event Manager."""

import math
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from ettem.models import Match, MatchStatus, Player, Set
from ettem.standings import calculate_standings
from ettem.storage import (
    DatabaseManager,
    BracketRepository,
    GroupRepository,
    MatchRepository,
    MatchORM,
    PlayerRepository,
    StandingRepository,
    TournamentRepository,
)
from ettem.validation import validate_match_sets, validate_tt_set, validate_walkover
from ettem.i18n import load_strings, get_language_from_env

# Initialize FastAPI app
app = FastAPI(title="Easy Table Tennis Event Manager")

# Add session middleware for flash messages
app.add_middleware(
    SessionMiddleware,
    secret_key="ettem-secret-key-change-in-production-2024"  # TODO: Move to config
)

# Setup templates directory
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Add custom Jinja2 filters
import json
templates.env.filters['from_json'] = json.loads

# Setup static files directory
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Database manager (shared instance)
db_manager = DatabaseManager()
db_manager.create_tables()  # Ensure tables exist


def get_db_session():
    """Get database session."""
    return db_manager.get_session()


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
    # Load i18n strings based on environment language
    lang = get_language_from_env()
    try:
        i18n_strings = load_strings(lang)
    except (ValueError, FileNotFoundError):
        # Fallback to empty dict if strings can't be loaded
        i18n_strings = {}

    # Add i18n to context
    context["t"] = i18n_strings
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

    return templates.TemplateResponse(template_name, context)


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
# Main Application Routes
# ============================================================================


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page - list all categories for current tournament."""
    session = get_db_session()
    player_repo = PlayerRepository(session)
    tournament_repo = TournamentRepository(session)

    # Get current tournament
    current_tournament = tournament_repo.get_current()
    tournament_id = current_tournament.id if current_tournament else None

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
    tournament_repo = TournamentRepository(session)

    # Get current tournament
    current_tournament = tournament_repo.get_current()
    tournament_id = current_tournament.id if current_tournament else None

    # Get groups for this category in current tournament
    groups = group_repo.get_by_category(category, tournament_id=tournament_id)

    # Get players for each group
    groups_data = []
    for group in groups:
        players = [player_repo.get_by_id(pid) for pid in group.player_ids]
        groups_data.append({
            "group": group,
            "players": [p for p in players if p]  # Filter out None
        })

    return render_template(
        "category.html",
        {
            "request": request,
            "category": category,
            "groups": groups_data
        }
    )


@app.get("/group/{group_id}/matches", response_class=HTMLResponse)
async def view_group_matches(request: Request, group_id: int):
    """View matches for a specific group."""
    session = get_db_session()
    group_repo = GroupRepository(session)
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)

    # Get group
    group = group_repo.get_by_id(group_id)
    if not group:
        return HTMLResponse(content="Group not found", status_code=404)

    # Get matches
    match_orms = match_repo.get_by_group(group_id)

    # Convert to domain models with player names
    matches_data = []
    for m_orm in match_orms:
        player1 = player_repo.get_by_id(m_orm.player1_id)
        player2 = player_repo.get_by_id(m_orm.player2_id)

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
            player1_id=m_orm.player1_id,
            player2_id=m_orm.player2_id,
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
        })

    return render_template(
        "group_matches.html",
        {
            "request": request,
            "group": group,
            "matches": matches_data,
            "category": group.category
        }
    )


@app.get("/match/{match_id}/enter-result", response_class=HTMLResponse)
async def enter_result_form(request: Request, match_id: int):
    """Show form to enter match result."""
    session = get_db_session()
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)

    # Get match
    match_orm = match_repo.get_by_id(match_id)
    if not match_orm:
        return HTMLResponse(content="Match not found", status_code=404)

    player1 = player_repo.get_by_id(match_orm.player1_id)
    player2 = player_repo.get_by_id(match_orm.player2_id)

    return render_template(
        "enter_result.html",
        {
            "request": request,
            "match": match_orm,
            "player1": player1,
            "player2": player2
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
):
    """Save match result."""
    session = get_db_session()
    match_repo = MatchRepository(session)

    # Get match
    match_orm = match_repo.get_by_id(match_id)
    if not match_orm:
        request.session["flash_message"] = "Partido no encontrado"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/", status_code=303)

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
            return RedirectResponse(url=f"/match/{match_id}/enter-result", status_code=303)

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
        ]

        # Collect valid sets and validate each one
        for idx, (p1_points, p2_points) in enumerate(set_inputs, start=1):
            if p1_points is not None and p2_points is not None:
                # Validate this set
                is_valid, error_msg = validate_tt_set(p1_points, p2_points)
                if not is_valid:
                    request.session["flash_message"] = f"Error en Set {idx}: {error_msg}"
                    request.session["flash_type"] = "error"
                    return RedirectResponse(url=f"/match/{match_id}/enter-result", status_code=303)

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
            raw_inputs = [set1_p1, set1_p2, set2_p1, set2_p2, set3_p1, set3_p2, set4_p1, set4_p2, set5_p1, set5_p2]
            form_vals = {}
            for i in range(1, 6):
                form_vals[f"set{i}_p1"] = raw_inputs[(i-1)*2] or ""
                form_vals[f"set{i}_p2"] = raw_inputs[(i-1)*2 + 1] or ""
            request.session["form_values"] = form_vals
            return RedirectResponse(url=f"/match/{match_id}/enter-result", status_code=303)

        # Validate the complete match
        sets_tuples = [(s["player1_points"], s["player2_points"]) for s in sets_data]
        is_valid, error_msg = validate_match_sets(sets_tuples, best_of=5)
        if not is_valid:
            error_text = f"Error en el partido: {error_msg}"
            print(f"[DEBUG] Saving flash message to session: {error_text}")
            request.session["flash_message"] = error_text
            request.session["flash_type"] = "error"
            # Save RAW form values (as submitted by user) to preserve them on error
            raw_inputs = [set1_p1, set1_p2, set2_p1, set2_p2, set3_p1, set3_p2, set4_p1, set4_p2, set5_p1, set5_p2]
            form_vals = {}
            for i in range(1, 6):
                form_vals[f"set{i}_p1"] = raw_inputs[(i-1)*2] or ""
                form_vals[f"set{i}_p2"] = raw_inputs[(i-1)*2 + 1] or ""
            request.session["form_values"] = form_vals
            print(f"[DEBUG] Saved form values: {form_vals}")
            return RedirectResponse(url=f"/match/{match_id}/enter-result", status_code=303)

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
        # This is a bracket match
        player_repo = PlayerRepository(session)
        player = player_repo.get_by_id(match_orm.player1_id)
        if player:
            category = player.categoria
            advance_bracket_winner(match_orm, winner_id_final, category, session)

    # Set success message
    request.session["flash_message"] = "Resultado guardado exitosamente"
    request.session["flash_type"] = "success"

    # Redirect based on match type (group or bracket)
    if match_orm.group_id is not None:
        # Group match - redirect to group matches page
        return RedirectResponse(url=f"/group/{match_orm.group_id}/matches", status_code=303)
    else:
        # Bracket match - get category from player and redirect to bracket page
        player_repo = PlayerRepository(session)
        player = player_repo.get_by_id(match_orm.player1_id)
        if player:
            return RedirectResponse(url=f"/bracket/{player.categoria}", status_code=303)
        else:
            # Fallback to home if player not found
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
        player = player_repo.get_by_id(match_orm.player1_id)
        if player:
            category = player.categoria

            # Check if winner has played in next round
            round_progression = {
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
            rollback_bracket_advancement(match_orm, match_orm.winner_id, category, session)

    # Reset match to pending state
    match_repo.update_result(
        match_id=match_id,
        sets=[],  # Clear all sets
        winner_id=None,
        status=MatchStatus.PENDING.value
    )

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
    standing_repo = StandingRepository(session)

    # Get group
    group = group_repo.get_by_id(group_id)
    if not group:
        return HTMLResponse(content="Group not found", status_code=404)

    # Get matches and calculate standings
    match_orms = match_repo.get_by_group(group_id)

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
            player1_id=m_orm.player1_id,
            player2_id=m_orm.player2_id,
            group_id=m_orm.group_id,
            round_type=m_orm.round_type,
            status=m_orm.status,
            sets=sets,
            winner_id=m_orm.winner_id,
        )
        matches.append(match)

    # Calculate standings
    standings = calculate_standings(matches, group_id, player_repo)

    # Get player details
    standings_data = []
    for standing in standings:
        player = player_repo.get_by_id(standing.player_id)
        if player:
            standings_data.append({
                "standing": standing,
                "player": player
            })

    return render_template("standings.html", {
        "request": request,
        "group": group,
        "standings": standings_data,
        "category": group.category
    })


@app.get("/group/{group_id}/sheet", response_class=HTMLResponse)
async def view_group_sheet(request: Request, group_id: int):
    """View group sheet with results matrix (original seeding order)."""
    session = get_db_session()
    group_repo = GroupRepository(session)
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)

    # Get group
    group = group_repo.get_by_id(group_id)
    if not group:
        return HTMLResponse(content="Group not found", status_code=404)

    # Get players sorted by group_number (original seeding order)
    all_players = [player_repo.get_by_id(pid) for pid in group.player_ids]
    players = sorted([p for p in all_players if p], key=lambda p: p.group_number or 999)

    # Get all matches for this group
    match_orms = match_repo.get_by_group(group_id)

    # Build results matrix: matrix[player1_group_num][player2_group_num] = result
    # Result format: "3-1" or "WO" or None if not played
    results_matrix = {}
    for p in players:
        results_matrix[p.group_number] = {}

    for m_orm in match_orms:
        if not m_orm.status or m_orm.status == MatchStatus.PENDING.value:
            continue

        p1 = player_repo.get_by_id(m_orm.player1_id)
        p2 = player_repo.get_by_id(m_orm.player2_id)

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
            player1_id=m_orm.player1_id,
            player2_id=m_orm.player2_id,
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
    standings = calculate_standings(
        [
            Match(
                id=m.id,
                player1_id=m.player1_id,
                player2_id=m.player2_id,
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
    })


@app.post("/category/{category}/recalculate-standings")
async def recalculate_standings(category: str):
    """Recalculate standings for all groups in a category."""
    session = get_db_session()
    group_repo = GroupRepository(session)
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)
    standing_repo = StandingRepository(session)

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
                player1_id=m_orm.player1_id,
                player2_id=m_orm.player2_id,
                group_id=m_orm.group_id,
                round_type=m_orm.round_type,
                status=m_orm.status,
                sets=sets,
                winner_id=m_orm.winner_id,
            )
            matches.append(match)

        # Calculate standings
        standings = calculate_standings(matches, group.id, player_repo)

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
        group_repo = GroupRepository(session)
        standing_repo = StandingRepository(session)
        sys.stderr.write("[DEBUG] Repositories initialized\n")
        sys.stderr.flush()

        # Get bracket slots for this category
        bracket_slots = bracket_repo.get_by_category(category)

        if not bracket_slots:
            return HTMLResponse(content="No bracket found for this category. Run 'build-bracket' first.", status_code=404)

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
        # Priority: R32 > R16 > QF > SF > F
        bracket_size = 0
        round_priority = ['R32', 'R16', 'QF', 'SF', 'F']
        for round_type in round_priority:
            if round_type in slots_by_round:
                bracket_size = len(slots_by_round[round_type])
                break

        # Determine which rounds should exist based on bracket size
        required_rounds = []
        if bracket_size >= 32:
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
                player = None
                if slot.player_id:
                    player = player_repo.get_by_id(slot.player_id)
                    sys.stderr.write(f"[DEBUG]   Slot {slot.slot_number}: player {player.nombre if player else 'None'}\n")
                    sys.stderr.flush()
                slots_with_players[round_type].append({
                    "slot": slot,
                    "player": player
                })

        # Get groups dict for lookups
        groups = group_repo.get_by_category(category)
        groups_dict = {g.id: g for g in groups}

        # Get standings dict for lookups
        all_standings = standing_repo.get_all()
        standings_dict = {}
        for standing_orm in all_standings:
            player_orm = player_repo.get_by_id(standing_orm.player_id)
            if player_orm and player_orm.categoria == category:
                standings_dict[standing_orm.player_id] = standing_orm

        # Check if there's a champion (final match completed)
        match_repo = MatchRepository(session)
        from ettem.models import MatchStatus
        champion_id = None
        final_matches = [
            m for m in match_repo.get_all()
            if m.round_type == RoundType.FINAL.value
            and m.group_id is None  # bracket match
        ]
        for m in final_matches:
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
        for match in all_bracket_matches:
            p1 = player_repo.get_by_id(match.player1_id) if match.player1_id else None
            if p1 and p1.categoria == category:
                if match.round_type not in matches_by_round:
                    matches_by_round[match.round_type] = []

                p2 = player_repo.get_by_id(match.player2_id) if match.player2_id else None
                matches_by_round[match.round_type].append({
                    "match": match,
                    "player1": p1,
                    "player2": p2,
                })

        sys.stderr.write("[DEBUG] About to render template\n")
        sys.stderr.flush()
        return render_template("bracket.html", {
            "request": request,
            "category": category,
            "slots_by_round": slots_with_players,
            "champion_id": champion_id,
            "groups_dict": groups_dict,
            "standings_dict": standings_dict,
            "matches_by_round": matches_by_round,
        })
    except Exception as e:
        sys.stderr.write(f"[ERROR] Exception in view_bracket: {e}\n")
        sys.stderr.flush()
        traceback.print_exc()
        raise


@app.get("/bracket/{category}", response_class=HTMLResponse)
async def view_bracket_matches(request: Request, category: str):
    """View knockout bracket with matches for a category."""
    from ettem.models import RoundType
    from collections import defaultdict

    session = get_db_session()
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)
    bracket_repo = BracketRepository(session)
    tournament_repo = TournamentRepository(session)

    # Get current tournament
    current_tournament = tournament_repo.get_current()
    tournament_id = current_tournament.id if current_tournament else None

    # Get bracket slots for this category in current tournament
    bracket_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
    if not bracket_slots:
        return HTMLResponse(content="No bracket found for this category. Generate bracket first.", status_code=404)

    # Get all bracket matches (group_id is None) filtered by category
    # We need to get all matches with group_id=None and filter by players in this category
    all_matches = match_repo.session.query(MatchORM).filter(MatchORM.group_id == None).all()

    # Filter matches by category (check if players belong to category)
    bracket_matches = []
    for match_orm in all_matches:
        player1 = player_repo.get_by_id(match_orm.player1_id)
        player2 = player_repo.get_by_id(match_orm.player2_id)
        if player1 and player1.categoria == category:
            bracket_matches.append(match_orm)

    # Group matches by round
    matches_by_round = defaultdict(list)
    for match_orm in bracket_matches:
        matches_by_round[match_orm.round_type].append(match_orm)

    # Sort matches within each round by match_number
    for round_type in matches_by_round:
        matches_by_round[round_type].sort(key=lambda m: m.match_number)

    # Prepare matches with player details
    matches_with_players = {}
    for round_type, matches in matches_by_round.items():
        matches_with_players[round_type] = []
        for match_orm in matches:
            player1 = player_repo.get_by_id(match_orm.player1_id)
            player2 = player_repo.get_by_id(match_orm.player2_id)

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
        all_round_types = [RoundType.ROUND_OF_32, RoundType.ROUND_OF_16,
                          RoundType.QUARTERFINAL, RoundType.SEMIFINAL, RoundType.FINAL]
        for rt in all_round_types:
            if rt.value in matches_by_round:
                round_order.append(rt.value)

    # Check if there's a champion (final match completed)
    champion = None
    champion_id = None
    if RoundType.FINAL.value in matches_by_round:
        for match_data in matches_with_players[RoundType.FINAL.value]:
            if match_data["match"].winner_id:
                champion_id = match_data["match"].winner_id
                champion = player_repo.get_by_id(champion_id)
                break

    return render_template("bracket_matches.html", {
        "request": request,
        "category": category,
        "matches_by_round": matches_with_players,
        "round_order": round_order,
        "champion": champion,
        "champion_id": champion_id,
    })


@app.get("/category/{category}/results", response_class=HTMLResponse)
async def view_final_results(request: Request, category: str):
    """View final results and podium for a category."""
    from ettem.models import RoundType, MatchStatus

    session = get_db_session()
    player_repo = PlayerRepository(session)
    match_repo = MatchRepository(session)
    bracket_repo = BracketRepository(session)

    # Verify bracket exists
    bracket_slots = bracket_repo.get_by_category(category)
    if not bracket_slots:
        return HTMLResponse(
            content="No bracket found for this category. Generate bracket first.",
            status_code=404
        )

    # Get the final match
    final_matches = [
        m for m in match_repo.get_all()
        if m.round_type == RoundType.FINAL.value
        and m.group_id is None  # bracket match
    ]

    # Filter by category
    final_match = None
    for m in final_matches:
        p1 = player_repo.get_by_id(m.player1_id)
        if p1 and p1.categoria == category:
            final_match = m
            break

    champion = None
    second_place = None
    third_fourth = []
    all_players = []

    if final_match and final_match.winner_id:
        # Tournament is complete
        champion = player_repo.get_by_id(final_match.winner_id)
        loser_id = final_match.player2_id if final_match.winner_id == final_match.player1_id else final_match.player1_id
        second_place = player_repo.get_by_id(loser_id)

        # Get semifinal losers (3rd/4th place)
        semifinal_matches = [
            m for m in match_repo.get_all()
            if m.round_type == RoundType.SEMIFINAL.value
            and m.group_id is None
        ]

        for sf_match in semifinal_matches:
            p1 = player_repo.get_by_id(sf_match.player1_id)
            if p1 and p1.categoria == category and sf_match.winner_id:
                loser_id = sf_match.player2_id if sf_match.winner_id == sf_match.player1_id else sf_match.player1_id
                if loser_id:
                    loser = player_repo.get_by_id(loser_id)
                    if loser:
                        third_fourth.append(loser)

    # Build complete ranking
    # Get all players in this category
    all_category_players = [p for p in player_repo.get_all() if p.categoria == category]

    # Determine elimination round for each player
    player_rankings = []

    for player in all_category_players:
        # Check if player is in bracket
        player_in_bracket = any(
            slot.player_id == player.id for slot in bracket_slots if slot.player_id
        )

        if not player_in_bracket:
            # Player didn't qualify for bracket
            player_rankings.append({
                'player': player,
                'final_position': 99,  # Group stage only
                'elimination_round': 'Fase de Grupos'
            })
            continue

        # Find last match for this player
        player_matches = [
            m for m in match_repo.get_all()
            if m.group_id is None  # bracket matches
            and (m.player1_id == player.id or m.player2_id == player.id)
            and m.status == MatchStatus.COMPLETED.value
        ]

        if not player_matches:
            # In bracket but no matches played yet
            player_rankings.append({
                'player': player,
                'final_position': 50,
                'elimination_round': 'Por Jugar'
            })
            continue

        # Find the highest round reached
        rounds_reached = [m.round_type for m in player_matches]

        # Determine final position based on elimination round
        if player.id == champion.id if champion else None:
            position = 1
            round_name = 'Campeón'
        elif player.id == second_place.id if second_place else None:
            position = 2
            round_name = 'Subcampeón'
        elif any(player.id == p.id for p in third_fourth):
            position = 3
            round_name = 'Semifinal'
        elif RoundType.SEMIFINAL.value in rounds_reached:
            # Lost in semifinal
            position = 3
            round_name = 'Semifinal'
        elif RoundType.QUARTERFINAL.value in rounds_reached:
            # Lost in quarterfinal
            position = 5
            round_name = 'Cuartos de Final'
        elif RoundType.ROUND_OF_16.value in rounds_reached:
            # Lost in R16
            position = 9
            round_name = 'Ronda de 16'
        elif RoundType.ROUND_OF_32.value in rounds_reached:
            # Lost in R32
            position = 17
            round_name = 'Ronda de 32'
        else:
            # First round
            position = 20
            round_name = 'Primera Ronda'

        player_rankings.append({
            'player': player,
            'final_position': position,
            'elimination_round': round_name
        })

    # Sort by position
    player_rankings.sort(key=lambda x: (x['final_position'], x['player'].seed))

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

    # Get current tournament
    current_tournament = tournament_repo.get_current()
    tournament_id = current_tournament.id if current_tournament else None

    # Get all players for current tournament
    players = player_repo.get_all(tournament_id=tournament_id)

    return render_template(
        "admin_import_players.html",
        {
            "request": request,
            "players": players,
            "current_tournament": current_tournament
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

            imported_count = 0
            for player in players:
                try:
                    player_repo.create(player, tournament_id=tournament_id)
                    imported_count += 1
                except Exception as e:
                    print(f"[ERROR] Error saving player {player.full_name}: {e}")

            # Assign seeds if requested
            if assign_seeds == "true":
                categories = set(p.categoria for p in players)
                for cat in categories:
                    player_repo.assign_seeds(cat)

            # Get imported category for redirect
            imported_category = players[0].categoria if players else None

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
    categoria: str = Form(...),
    seed: Optional[int] = Form(None)
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

        # Create player
        player = Player(
            id=0,  # Auto-generated
            nombre=nombre.strip(),
            apellido=apellido.strip(),
            genero=Gender.MALE if genero == "M" else Gender.FEMALE,
            pais_cd=pais_cd.strip().upper(),
            ranking_pts=ranking_pts,
            categoria=categoria.strip().upper(),
            original_id=original_id,
            seed=seed if seed and seed > 0 else None
        )

        # Save to database
        session = get_db_session()
        player_repo = PlayerRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        player_repo.create(player, tournament_id=tournament_id)

        # If seed wasn't provided, auto-assign
        if not seed:
            player_repo.assign_seeds(player.categoria)

        request.session["flash_message"] = f"Jugador {player.full_name} agregado exitosamente"
        request.session["flash_type"] = "success"

    except Exception as e:
        request.session["flash_message"] = f"Error al agregar jugador: {str(e)}"
        request.session["flash_type"] = "error"

    return RedirectResponse(url="/admin/import-players", status_code=303)


@app.get("/admin/create-groups", response_class=HTMLResponse)
async def admin_create_groups_form(request: Request):
    """Show create groups form."""
    session = get_db_session()
    player_repo = PlayerRepository(session)
    group_repo = GroupRepository(session)
    match_repo = MatchRepository(session)
    tournament_repo = TournamentRepository(session)

    # Get current tournament
    current_tournament = tournament_repo.get_current()
    tournament_id = current_tournament.id if current_tournament else None

    # Get all players grouped by category for current tournament
    all_players = player_repo.get_all(tournament_id=tournament_id)
    categories_dict = {}
    countries_by_category = {}  # Track country distribution per category

    for player in all_players:
        if player.categoria not in categories_dict:
            categories_dict[player.categoria] = 0
            countries_by_category[player.categoria] = {}
        categories_dict[player.categoria] += 1

        # Count countries per category
        if player.pais_cd not in countries_by_category[player.categoria]:
            countries_by_category[player.categoria][player.pais_cd] = 0
        countries_by_category[player.categoria][player.pais_cd] += 1

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
            "existing_groups": existing_groups
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

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Get players for this category in current tournament
        player_orms = player_repo.get_by_category_sorted_by_seed(category, tournament_id=tournament_id)

        if not player_orms:
            request.session["flash_message"] = f"No se encontraron jugadores para la categoría {category}."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/create-groups", status_code=303)

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
    manual_assignments: Optional[str] = Form(None)
):
    """Execute group creation."""
    from ettem.group_builder import create_groups
    import json

    try:
        # Initialize repositories
        session = get_db_session()
        player_repo = PlayerRepository(session)
        group_repo = GroupRepository(session)
        match_repo = MatchRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Get players for this category in current tournament
        player_orms = player_repo.get_by_category_sorted_by_seed(category, tournament_id=tournament_id)

        if not player_orms:
            request.session["flash_message"] = f"No se encontraron jugadores para la categoría {category}. Importa jugadores primero."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/create-groups", status_code=303)

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

        # Delete existing groups and matches for this category in current tournament
        existing_groups = group_repo.get_by_category(category, tournament_id=tournament_id)
        for group in existing_groups:
            # Delete matches first
            matches = match_repo.get_by_group(group.id)
            for match in matches:
                match_repo.delete(match.id)
            # Then delete group
            group_repo.delete(group.id)

        # Check if we have manual assignments
        if manual_assignments and manual_assignments.strip():
            # Use manual assignments from preview
            assignments = json.loads(manual_assignments)
            groups, matches = create_groups_from_manual_assignments(
                players=players,
                category=category,
                assignments=assignments
            )
        else:
            # Create groups automatically
            groups, matches = create_groups(
                players=players,
                category=category,
                group_size_preference=group_size_preference,
                random_seed=random_seed if random_seed else 42,
            )

        # Save to database
        for group in groups:
            # Save group with tournament_id
            group_orm = group_repo.create(group, tournament_id=tournament_id)

            # Update players' group assignment
            for player_id in group.player_ids:
                player_orm = player_repo.get_by_id(player_id)
                if player_orm:
                    player_orm.group_id = group_orm.id
                    # Find group_number from players list
                    for p in players:
                        if p.id == player_id:
                            player_orm.group_number = p.group_number
                            break
            player_repo.session.commit()

            # Save matches for this group
            for match in matches:
                if match.player1_id in group.player_ids and match.player2_id in group.player_ids:
                    match.group_id = group_orm.id
                    match_repo.create(match)

        request.session["flash_message"] = f"Se crearon exitosamente {len(groups)} grupos con {len(matches)} partidos para la categoría {category}"
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

    # Get current tournament
    current_tournament = tournament_repo.get_current()
    tournament_id = current_tournament.id if current_tournament else None

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

    # Get current standings summary
    all_standings = standing_repo.get_all()
    standings_by_group = {}
    for standing in all_standings:
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
                    player1_id=m_orm.player1_id,
                    player2_id=m_orm.player2_id,
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
            standings = calculate_standings(matches, group_orm.id, player_repo)

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
                    player1_id=m_orm.player1_id,
                    player2_id=m_orm.player2_id,
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
            standings = calculate_standings(matches, group_orm.id, player_repo)

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


@app.get("/admin/generate-bracket", response_class=HTMLResponse)
async def admin_generate_bracket_form(request: Request):
    """Show generate bracket form."""
    session = get_db_session()
    group_repo = GroupRepository(session)
    standing_repo = StandingRepository(session)
    player_repo = PlayerRepository(session)
    bracket_repo = BracketRepository(session)
    tournament_repo = TournamentRepository(session)

    # Get current tournament
    current_tournament = tournament_repo.get_current()
    tournament_id = current_tournament.id if current_tournament else None

    # Get all groups grouped by category with standings count for current tournament
    all_groups = group_repo.get_all(tournament_id=tournament_id)
    all_standings = standing_repo.get_all()

    # Count standings per category
    standings_by_category = {}
    for standing in all_standings:
        player = player_repo.get_by_id(standing.player_id)
        if player:
            if player.categoria not in standings_by_category:
                standings_by_category[player.categoria] = 0
            standings_by_category[player.categoria] += 1

    # Count groups per category
    groups_by_category = {}
    for group in all_groups:
        if group.category not in groups_by_category:
            groups_by_category[group.category] = 0
        groups_by_category[group.category] += 1

    # Available categories
    available_categories = [
        {
            "name": cat,
            "groups": groups_by_category.get(cat, 0),
            "standings": count
        }
        for cat, count in sorted(standings_by_category.items())
    ]

    # Get existing brackets for current tournament
    all_players = player_repo.get_all(tournament_id=tournament_id)
    categories = list(set(p.categoria for p in all_players))
    existing_brackets = []

    for category in categories:
        bracket_slots = bracket_repo.get_by_category(category, tournament_id=tournament_id)
        if bracket_slots:
            # Count non-BYE players
            players_count = sum(1 for slot in bracket_slots if not slot.is_bye and slot.player_id)
            # Get bracket size from R1 (first round)
            r1_slots = [s for s in bracket_slots if s.round_type == "R1"]
            size = len(r1_slots) if r1_slots else 0

            existing_brackets.append({
                "category": category,
                "size": size,
                "players": players_count
            })

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
    random_seed: Optional[int] = Form(None)
):
    """Execute bracket generation."""
    from ettem.bracket import build_bracket
    from ettem.models import GroupStanding

    try:
        # Initialize repositories
        session = get_db_session()
        standing_repo = StandingRepository(session)
        player_repo = PlayerRepository(session)
        bracket_repo = BracketRepository(session)
        tournament_repo = TournamentRepository(session)

        # Get current tournament
        current_tournament = tournament_repo.get_current()
        tournament_id = current_tournament.id if current_tournament else None

        # Get all standings for this category
        all_standings = standing_repo.get_all()

        # Filter by category and get top N per group
        category_standings = []
        groups_processed = set()

        for standing_orm in all_standings:
            player_orm = player_repo.get_by_id(standing_orm.player_id)
            if not player_orm or player_orm.categoria != category:
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

        # Convert to domain models with players
        qualifiers = []
        for standing_orm in category_standings:
            player_orm = player_repo.get_by_id(standing_orm.player_id)
            if player_orm:
                player = Player(
                    id=player_orm.id,
                    nombre=player_orm.nombre,
                    apellido=player_orm.apellido,
                    genero=player_orm.genero,
                    pais_cd=player_orm.pais_cd,
                    ranking_pts=player_orm.ranking_pts,
                    categoria=player_orm.categoria,
                    seed=player_orm.seed,
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
                qualifiers.append((player, standing))

        # Build bracket
        bracket = build_bracket(
            qualifiers=qualifiers,
            category=category,
            random_seed=random_seed if random_seed else 42,
            player_repo=player_repo,
        )

        # Save bracket to database
        bracket_repo.delete_by_category(category, tournament_id=tournament_id)  # Clear old bracket

        total_slots = 0
        for round_type, slots in bracket.slots.items():
            for slot in slots:
                bracket_repo.create_slot(slot, category, tournament_id=tournament_id)
                total_slots += 1

        # Create matches from bracket slots
        match_repo = MatchRepository(session)
        matches_created = create_bracket_matches(category, bracket_repo, match_repo)

        # Process BYE advancements
        process_bye_advancements(category, bracket_repo, session)

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

        # Verify bracket exists
        bracket_slots = bracket_repo.get_by_category(category)
        if not bracket_slots:
            request.session["flash_message"] = f"No hay bracket para la categoría {category}"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/", status_code=303)

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

        # Create matches from bracket slots
        matches_created = create_bracket_matches(category, bracket_repo, match_repo)

        # Process BYE advancements
        process_bye_advancements(category, bracket_repo, session)

        request.session["flash_message"] = f"Partidos regenerados: {matches_created} partidos creados"
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/bracket/{category}", status_code=303)

    except Exception as e:
        request.session["flash_message"] = f"Error al regenerar partidos: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/", status_code=303)


def get_bye_positions(num_groups: int) -> list[int]:
    """
    Get the exact BYE positions based on the number of groups.

    BYE positions are predefined for each configuration to ensure proper tournament structure.
    The fewer groups, the more BYEs needed to fill the draw to the next power of 2.

    Args:
        num_groups: Number of groups in the category

    Returns:
        List of positions where BYEs should be placed (1-indexed)
    """
    # Map: num_groups -> BYE positions
    # Each group contributes 2 qualifiers (1st and 2nd place)
    bye_map = {
        3: [2, 7],  # 6 players -> draw of 8
        5: [2, 6, 7, 10, 11, 15],  # 10 players -> draw of 16
        6: [2, 7, 10, 15],  # 12 players -> draw of 16
        7: [2, 15],  # 14 players -> draw of 16
        8: [],  # 16 players -> draw of 16, no BYEs
        9: [2, 3, 6, 7, 10, 11, 15, 18, 22, 23, 26, 27, 30, 31],  # 18 players -> draw of 32
        10: [2, 6, 7, 10, 11, 15, 18, 22, 23, 26, 27, 31],  # 20 players -> draw of 32
        11: [2, 6, 7, 10, 11, 15, 18, 22, 23, 26],  # 22 players -> draw of 32
        12: [2, 7, 10, 11, 15, 18, 23, 26],  # 24 players -> draw of 32
        13: [2, 7, 15, 18, 26, 31],  # 26 players -> draw of 32
        14: [2, 15, 18, 31],  # 28 players -> draw of 32
        15: [2, 31],  # 30 players -> draw of 32
        16: [],  # 32 players -> draw of 32, no BYEs
        17: [2, 3, 6, 7, 10, 11, 14, 15, 18, 22, 23, 26, 27, 30, 31, 34,
             35, 38, 39, 42, 43, 47, 50, 51, 54, 55, 58, 59, 62, 63],  # 34 players -> draw of 64
        18: [2, 3, 6, 7, 10, 11, 14, 15, 18, 22, 23, 26, 27, 30, 31, 34,
             35, 38, 39, 42, 43, 47, 50, 51, 54, 55, 58, 59],  # 36 players -> draw of 64
        19: [2, 6, 7, 10, 11, 15, 18, 22, 23, 26, 27, 30, 31, 34, 35, 38,
             39, 42, 43, 47, 50, 54, 55, 58, 59, 63],  # 38 players -> draw of 64
        20: [2, 6, 7, 10, 11, 15, 18, 22, 23, 26, 27, 30, 31, 34, 38, 39,
             42, 43, 47, 50, 54, 55, 58, 59],  # 40 players -> draw of 64
    }

    return bye_map.get(num_groups, [])


def advance_bracket_winner(match_orm, winner_id, category, session):
    """
    Advance the winner of a bracket match to the next round.

    Args:
        match_orm: The completed match
        winner_id: ID of the winner
        category: Category name
        session: Database session

    Returns:
        True if advancement was successful, False if this is the final
    """
    from ettem.models import RoundType, Match, MatchStatus
    from ettem.storage import BracketSlotORM

    # Map rounds to next round
    round_progression = {
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

    # Check if slot exists in next round
    next_round_slots = bracket_repo.get_by_category_and_round(category, next_round)

    # Find the specific slot
    target_slot = None
    for slot in next_round_slots:
        if slot.slot_number == next_slot_number:
            target_slot = slot
            break

    if target_slot:
        # Update existing slot with winner
        bracket_repo.session.query(BracketSlotORM).filter(
            BracketSlotORM.id == target_slot.id
        ).update({
            "player_id": winner_id,
            "is_bye": False
        })
        bracket_repo.session.commit()
    else:
        # Create new slot in next round
        new_slot_orm = BracketSlotORM(
            category=category,
            slot_number=next_slot_number,
            round_type=next_round,
            player_id=winner_id,
            is_bye=False,
            same_country_warning=False,
            advanced_by_bye=False
        )
        bracket_repo.session.add(new_slot_orm)
        bracket_repo.session.commit()
        next_round_slots = bracket_repo.get_by_category_and_round(category, next_round)  # Refresh slots list

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
            slot_number=pair_slot_number,
            round_type=next_round,
            player_id=None,
            is_bye=False,
            same_country_warning=False,
            advanced_by_bye=False
        )
        bracket_repo.session.add(new_pair_slot_orm)
        bracket_repo.session.commit()
        next_round_slots = bracket_repo.get_by_category_and_round(category, next_round)  # Refresh slots list
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
        existing_matches = match_repo.session.query(MatchORM).filter(
            MatchORM.group_id == None,
            MatchORM.round_type == next_round,
            MatchORM.match_number == next_match_number
        ).all()

        if existing_matches:
            # Update existing match with the new player(s)
            match_repo.session.query(MatchORM).filter(
                MatchORM.id == existing_matches[0].id
            ).update({
                "player1_id": player1_id,
                "player2_id": player2_id,
                "status": MatchStatus.PENDING.value
            })
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
            match_repo.create(new_match)

        match_repo.session.commit()

    return True


def rollback_bracket_advancement(match_orm, winner_id, category, session):
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

    Returns:
        True if rollback was successful, False if no rollback needed (e.g., final)
    """
    from ettem.models import RoundType, MatchStatus
    from ettem.storage import BracketSlotORM

    # Map rounds to next round (same as advance_bracket_winner)
    round_progression = {
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
    next_round_slots = bracket_repo.get_by_category_and_round(category, next_round)

    target_slot = None
    for slot in next_round_slots:
        if slot.slot_number == next_slot_number:
            target_slot = slot
            break

    if target_slot and target_slot.player_id == winner_id:
        # Clear the slot (remove the winner)
        session.query(BracketSlotORM).filter(
            BracketSlotORM.id == target_slot.id
        ).update({
            "player_id": None,
            "is_bye": False,
            "advanced_by_bye": False
        })
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
        existing_match = session.query(MatchORM).filter(
            MatchORM.group_id == None,
            MatchORM.round_type == next_round,
            MatchORM.match_number == next_match_number
        ).first()

        if existing_match:
            # Determine which player position to clear based on slot number
            if next_slot_number < pair_slot_number:
                # Winner was player1
                session.query(MatchORM).filter(
                    MatchORM.id == existing_match.id
                ).update({
                    "player1_id": None
                })
            else:
                # Winner was player2
                session.query(MatchORM).filter(
                    MatchORM.id == existing_match.id
                ).update({
                    "player2_id": None
                })
            session.commit()

        return True

    return False


def create_bracket_matches(category: str, bracket_repo, match_repo):
    """
    Create Match objects for all bracket rounds based on bracket slots.

    Matches are created by pairing adjacent slots (1-2, 3-4, etc.) in each round.
    When a match has a result, the winner advances to the next round automatically.

    Args:
        category: Category name
        bracket_repo: BracketRepository instance
        match_repo: MatchRepository instance

    Returns:
        Number of matches created
    """
    from ettem.models import Match, MatchStatus, RoundType

    # Get all slots for this category, grouped by round
    all_slots = bracket_repo.get_by_category(category)

    # Group slots by round_type
    slots_by_round = {}
    for slot_orm in all_slots:
        round_type = slot_orm.round_type
        if round_type not in slots_by_round:
            slots_by_round[round_type] = []
        slots_by_round[round_type].append(slot_orm)

    # Delete existing bracket matches for this category (cleanup)
    existing_matches = match_repo.get_all()
    for match_orm in existing_matches:
        if match_orm.group_id is None:  # Bracket match (not group match)
            # Check if it belongs to this category by checking player's category
            # For now, we'll just delete all bracket matches
            # TODO: Add category field to Match model for better filtering
            pass

    matches_created = 0

    # Create matches for each round
    for round_type in [RoundType.ROUND_OF_32, RoundType.ROUND_OF_16,
                       RoundType.QUARTERFINAL, RoundType.SEMIFINAL, RoundType.FINAL]:

        if round_type not in slots_by_round:
            continue

        slots = sorted(slots_by_round[round_type], key=lambda s: s.slot_number)

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

            # Skip if both slots are BYEs (shouldn't happen but safety check)
            # But DO create matches even if one or both players are None (will be filled later)

            match_number = (i // 2) + 1
            round_name = f"{round_type.value}{match_number}"

            # Create match regardless of whether players are assigned yet
            # This allows future rounds to exist and be updated when winners advance
            match = Match(
                id=0,  # Will be assigned by DB
                player1_id=player1_id,  # Can be None
                player2_id=player2_id,  # Can be None
                group_id=None,  # Bracket match
                round_type=round_type,
                round_name=round_name,
                match_number=match_number,
                status=MatchStatus.PENDING,
            )

            match_repo.create(match)
            matches_created += 1

    return matches_created


def process_bye_advancements(category: str, bracket_repo, session):
    """
    Automatically advance players who face BYEs to the next round.

    When a player faces a BYE (no opponent), they should automatically
    advance to the next round without needing to play a match.

    Args:
        category: Category name
        bracket_repo: BracketRepository instance
        session: Database session
    """
    from ettem.models import RoundType

    # Map rounds to next round
    round_progression = {
        RoundType.ROUND_OF_32: RoundType.ROUND_OF_16,
        RoundType.ROUND_OF_16: RoundType.QUARTERFINAL,
        RoundType.QUARTERFINAL: RoundType.SEMIFINAL,
        RoundType.SEMIFINAL: RoundType.FINAL,
    }

    # Get all slots for this category
    all_slots = bracket_repo.get_by_category(category)

    # Group by round
    slots_by_round = {}
    for slot_orm in all_slots:
        round_type = slot_orm.round_type
        if round_type not in slots_by_round:
            slots_by_round[round_type] = []
        slots_by_round[round_type].append(slot_orm)

    # Process each round
    for current_round in [RoundType.ROUND_OF_32, RoundType.ROUND_OF_16,
                          RoundType.QUARTERFINAL, RoundType.SEMIFINAL]:

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

        # First, validate that groups exist for this category
        all_groups = group_repo.get_all()
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

        # Get all standings for this category
        all_standings = standing_repo.get_all()

        # Filter by category and separate by position
        firsts = []
        seconds = []

        for standing_orm in all_standings:
            player_orm = player_repo.get_by_id(standing_orm.player_id)
            if not player_orm or player_orm.categoria != category:
                continue

            # Calculate ratios
            sets_ratio = standing_orm.sets_w / standing_orm.sets_l if standing_orm.sets_l > 0 else 999.0
            points_ratio = standing_orm.points_w / standing_orm.points_l if standing_orm.points_l > 0 else 999.0

            if standing_orm.position == 1:
                firsts.append({
                    "player_id": player_orm.id,
                    "nombre": player_orm.nombre,
                    "apellido": player_orm.apellido,
                    "pais_cd": player_orm.pais_cd,
                    "group_id": standing_orm.group_id,
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
                    "points_total": standing_orm.points_total,
                    "sets_ratio": sets_ratio,
                    "points_ratio": points_ratio,
                    "seed": player_orm.seed or 999
                })

        if not firsts and not seconds:
            request.session["flash_message"] = f"No hay clasificados para la categoría {category}. Calcula standings primero."
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/admin/generate-bracket", status_code=303)

        # Sort by group_id (G1, G2, G3...) - this is the natural order for bracket positioning
        firsts.sort(key=lambda x: x["group_id"])
        seconds.sort(key=lambda x: x["group_id"])

        # Calculate bracket size and BYEs using predefined positions
        num_groups = len(category_groups)
        total_qualifiers = len(firsts) + len(seconds)
        bracket_size = 2 ** math.ceil(math.log2(total_qualifiers)) if total_qualifiers > 0 else 0

        # Get exact BYE positions based on number of groups
        bye_positions = get_bye_positions(num_groups)
        all_bye_positions = set(bye_positions)

        # DEBUG: Print to console
        print(f"DEBUG: num_groups={num_groups}, bye_positions={bye_positions}, bracket_size={bracket_size}")

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

        # Get form data
        form_data = await request.form()

        # Parse slot assignments (slot_1=player_id, slot_2=player_id, etc.)
        slot_assignments = {}
        for key, value in form_data.items():
            if key.startswith("slot_") and value:
                slot_num = int(key.replace("slot_", ""))
                player_id = int(value) if value else None
                if player_id:
                    slot_assignments[slot_num] = player_id

        if not slot_assignments:
            request.session["flash_message"] = "Debes asignar al menos un jugador al bracket"
            request.session["flash_type"] = "error"
            # Save form state to preserve user's work
            request.session["bracket_form_data"] = dict(form_data)
            return RedirectResponse(url=f"/admin/manual-bracket/{category}", status_code=303)

        # Determine bracket size
        max_slot = max(slot_assignments.keys())
        bracket_size = 2 ** math.ceil(math.log2(max_slot))

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
        # Build player -> group_id mapping
        player_to_group = {}
        all_standings = standing_repo.get_all()
        for standing_orm in all_standings:
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
        bracket_repo.delete_by_category(category)  # Clear old bracket

        for slot_num in range(1, bracket_size + 1):
            player_id = slot_assignments.get(slot_num)
            is_bye = player_id is None

            slot = BracketSlot(
                slot_number=slot_num,
                round_type=round_type,
                player_id=player_id,
                is_bye=is_bye,
                same_country_warning=False
            )
            bracket_repo.create_slot(slot, category)

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

        # Create matches from bracket slots
        match_repo = MatchRepository(session)
        matches_created = create_bracket_matches(category, bracket_repo, match_repo)

        # Process BYE advancements
        process_bye_advancements(category, bracket_repo, session)

        request.session["flash_message"] = f"Bracket manual guardado: {matches_created} partidos creados"
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/bracket/{category}", status_code=303)

    except Exception as e:
        request.session["flash_message"] = f"Error al guardar bracket: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url=f"/admin/manual-bracket/{category}", status_code=303)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
