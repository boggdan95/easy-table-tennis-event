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
    GroupRepository,
    MatchRepository,
    PlayerRepository,
    StandingRepository,
)

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
        # Walkover - just set winner
        match_orm.status = MatchStatus.WALKOVER.value
        match_orm.winner_id = winner_id_int
        match_orm.sets_json = "[]"
        match_repo.update(match_orm)
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

        for idx, (p1_points, p2_points) in enumerate(set_inputs, start=1):
            if p1_points is not None and p2_points is not None:
                sets_data.append({
                    "set_number": idx,
                    "player1_points": p1_points,
                    "player2_points": p2_points,
                })

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
