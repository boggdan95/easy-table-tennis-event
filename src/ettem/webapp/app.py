"""FastAPI web application for Easy Table Tennis Event Manager."""

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
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
    PlayerRepository,
    StandingRepository,
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

# Setup static files directory
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Database manager (shared instance)
db_manager = DatabaseManager()


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

    # Add global data (categories for sidebar)
    session = None
    try:
        session = get_db_session()
        player_repo = PlayerRepository(session)
        all_players = player_repo.get_all()
        categories = sorted(set(p.categoria for p in all_players))
        context["categories"] = categories
    except Exception as e:
        print(f"[ERROR] Failed to load categories: {e}")
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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page - list all categories."""
    session = get_db_session()
    player_repo = PlayerRepository(session)

    # Get all unique categories
    all_players = player_repo.get_all()
    categories = sorted(set(p.categoria for p in all_players))

    return render_template(
        "index.html",
        {"request": request, "categories": categories}
    )


@app.get("/category/{category}", response_class=HTMLResponse)
async def view_category(request: Request, category: str):
    """View category dashboard."""
    session = get_db_session()
    group_repo = GroupRepository(session)
    player_repo = PlayerRepository(session)

    # Get groups for this category
    groups = group_repo.get_by_category(category)

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
            form_vals = {}
            for i in range(1, 6):
                p1_val = form_data.get(f"set{i}_p1", "").strip()
                p2_val = form_data.get(f"set{i}_p2", "").strip()
                form_vals[f"set{i}_p1"] = p1_val
                form_vals[f"set{i}_p2"] = p2_val
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
            form_vals = {}
            for i in range(1, 6):
                p1_val = form_data.get(f"set{i}_p1", "").strip()
                p2_val = form_data.get(f"set{i}_p2", "").strip()
                form_vals[f"set{i}_p1"] = p1_val
                form_vals[f"set{i}_p2"] = p2_val
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

    # Set success message
    request.session["flash_message"] = "Resultado guardado exitosamente"
    request.session["flash_type"] = "success"

    # Redirect back to group matches
    return RedirectResponse(url=f"/group/{match_orm.group_id}/matches", status_code=303)


@app.post("/match/{match_id}/delete-result")
async def delete_result(request: Request, match_id: int):
    """Delete match result and reset to pending status."""
    session = get_db_session()
    match_repo = MatchRepository(session)

    # Get match
    match_orm = match_repo.get_by_id(match_id)
    if not match_orm:
        request.session["flash_message"] = "Partido no encontrado"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/", status_code=303)

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

    # Redirect back to group matches
    return RedirectResponse(url=f"/group/{match_orm.group_id}/matches", status_code=303)


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

    return templates.TemplateResponse(
        "standings.html",
        {
            "request": request,
            "group": group,
            "standings": standings_data,
            "category": group.category
        }
    )


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

    return templates.TemplateResponse(
        "group_sheet.html",
        {
            "request": request,
            "group": group,
            "players": players_data,
            "results_matrix": results_matrix,
            "category": group.category,
        }
    )


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
    session = get_db_session()
    bracket_repo = BracketRepository(session)
    player_repo = PlayerRepository(session)
    group_repo = GroupRepository(session)
    standing_repo = StandingRepository(session)

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

    # Determine bracket size from first round
    first_round_slots = list(slots_by_round.values())[0] if slots_by_round else []
    bracket_size = len(first_round_slots)

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
    for round_type, slots in complete_bracket.items():
        slots_with_players[round_type] = []
        for slot in slots:
            player = None
            if slot.player_id:
                player = player_repo.get_by_id(slot.player_id)
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

    return templates.TemplateResponse(
        "bracket.html",
        {
            "request": request,
            "category": category,
            "slots_by_round": slots_with_players,
            "groups_dict": groups_dict,
            "standings_dict": standings_dict,
        }
    )


# ========================================
# ADMIN ROUTES
# ========================================

@app.get("/admin/import-players", response_class=HTMLResponse)
async def admin_import_players_form(request: Request):
    """Show import players form."""
    session = get_db_session()
    player_repo = PlayerRepository(session)

    # Get all players to show in the list
    players = player_repo.get_all()

    return render_template(
        "admin_import_players.html",
        {
            "request": request,
            "players": players
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

            imported_count = 0
            for player in players:
                try:
                    player_repo.create(player)
                    imported_count += 1
                except Exception as e:
                    print(f"[ERROR] Error saving player {player.full_name}: {e}")

            # Assign seeds if requested
            if assign_seeds == "true":
                categories = set(p.categoria for p in players)
                for cat in categories:
                    player_repo.assign_seeds(cat)

            request.session["flash_message"] = f"Se importaron exitosamente {imported_count} jugadores"
            request.session["flash_type"] = "success"

        except CSVImportError as e:
            request.session["flash_message"] = f"Error al importar CSV: {str(e)}"
            request.session["flash_type"] = "error"
        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)

        return RedirectResponse(url="/admin/import-players", status_code=303)

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
        player_repo.create(player)

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

    # Get all players grouped by category
    all_players = player_repo.get_all()
    categories_dict = {}
    for player in all_players:
        if player.categoria not in categories_dict:
            categories_dict[player.categoria] = 0
        categories_dict[player.categoria] += 1

    # Convert to list for template
    available_categories = [
        {"name": cat, "count": count}
        for cat, count in sorted(categories_dict.items())
    ]

    # Get existing groups
    all_groups = group_repo.get_all()
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


@app.post("/admin/create-groups/execute")
async def admin_create_groups_execute(
    request: Request,
    category: str = Form(...),
    group_size_preference: int = Form(...),
    random_seed: Optional[int] = Form(None)
):
    """Execute group creation."""
    from ettem.group_builder import create_groups

    try:
        # Initialize repositories
        session = get_db_session()
        player_repo = PlayerRepository(session)
        group_repo = GroupRepository(session)
        match_repo = MatchRepository(session)

        # Get players for this category
        player_orms = player_repo.get_by_category_sorted_by_seed(category)

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

        # Delete existing groups and matches for this category
        existing_groups = group_repo.get_by_category(category)
        for group in existing_groups:
            # Delete matches first
            matches = match_repo.get_by_group(group.id)
            for match in matches:
                match_repo.delete(match.id)
            # Then delete group
            group_repo.delete(group.id)

        # Create groups
        groups, matches = create_groups(
            players=players,
            category=category,
            group_size_preference=group_size_preference,
            random_seed=random_seed if random_seed else 42,
        )

        # Save to database
        for group in groups:
            # Save group
            group_orm = group_repo.create(group)

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

    # Get all groups grouped by category
    all_groups = group_repo.get_all()
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

        # Get all groups
        all_groups = group_repo.get_all()

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

    # Get all groups grouped by category with standings count
    all_groups = group_repo.get_all()
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

    # Get existing brackets
    all_players = player_repo.get_all()
    categories = list(set(p.categoria for p in all_players))
    existing_brackets = []

    for category in categories:
        bracket_slots = bracket_repo.get_by_category(category)
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
        bracket_repo.delete_by_category(category)  # Clear old bracket

        total_slots = 0
        for round_type, slots in bracket.slots.items():
            for slot in slots:
                bracket_repo.create_slot(slot, category)
                total_slots += 1

        request.session["flash_message"] = f"Bracket generado exitosamente con {total_slots} slots para {len(qualifiers)} clasificados"
        request.session["flash_type"] = "success"

        return RedirectResponse(url=f"/bracket/{category}", status_code=303)

    except Exception as e:
        request.session["flash_message"] = f"Error al generar bracket: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/admin/generate-bracket", status_code=303)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
