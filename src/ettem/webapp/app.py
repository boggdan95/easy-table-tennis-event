"""FastAPI web application for Easy Table Tennis Event Manager."""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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

# Initialize FastAPI app
app = FastAPI(title="Easy Table Tennis Event Manager")

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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page - list all categories."""
    session = get_db_session()
    player_repo = PlayerRepository(session)

    # Get all unique categories
    all_players = player_repo.get_all()
    categories = sorted(set(p.categoria for p in all_players))

    return templates.TemplateResponse(
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

    return templates.TemplateResponse(
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

    return templates.TemplateResponse(
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

    return templates.TemplateResponse(
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
        return HTMLResponse(content="Match not found", status_code=404)

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
            return HTMLResponse(
                content=f"Error en walkover: {error_msg}",
                status_code=400
            )

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
                    return HTMLResponse(
                        content=f"Error en Set {idx}: {error_msg}",
                        status_code=400
                    )

                sets_data.append({
                    "set_number": idx,
                    "player1_points": p1_points,
                    "player2_points": p2_points,
                })

        # Check if we have any sets at all
        if not sets_data:
            return HTMLResponse(
                content="Error: Debe ingresar al menos un set",
                status_code=400
            )

        # Validate the complete match
        sets_tuples = [(s["player1_points"], s["player2_points"]) for s in sets_data]
        is_valid, error_msg = validate_match_sets(sets_tuples, best_of=5)
        if not is_valid:
            return HTMLResponse(
                content=f"Error en el partido: {error_msg}",
                status_code=400
            )

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

    # Redirect back to group matches
    return RedirectResponse(url=f"/group/{match_orm.group_id}/matches", status_code=303)


@app.post("/match/{match_id}/delete-result")
async def delete_result(match_id: int):
    """Delete match result and reset to pending status."""
    session = get_db_session()
    match_repo = MatchRepository(session)

    # Get match
    match_orm = match_repo.get_by_id(match_id)
    if not match_orm:
        return HTMLResponse(content="Match not found", status_code=404)

    # Reset match to pending state
    match_repo.update_result(
        match_id=match_id,
        sets=[],  # Clear all sets
        winner_id=None,
        status=MatchStatus.PENDING.value
    )

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
