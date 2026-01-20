"""
PDF Generator Module for ETTEM
Generates printable PDFs for matches, groups, brackets, etc.
Uses xhtml2pdf for HTML to PDF conversion.
"""

import io
from pathlib import Path
from typing import Optional, List, Dict, Any

from xhtml2pdf import pisa
from jinja2 import Environment, FileSystemLoader


# Path to print templates
TEMPLATES_DIR = Path(__file__).parent / "webapp" / "templates" / "print"


def get_template_env() -> Environment:
    """Get Jinja2 environment for print templates."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True
    )


def render_html(template_name: str, context: Dict[str, Any]) -> str:
    """Render a template with the given context."""
    env = get_template_env()
    template = env.get_template(template_name)
    return template.render(**context)


def html_to_pdf(html_content: str) -> bytes:
    """Convert HTML string to PDF bytes."""
    result = io.BytesIO()

    # Convert HTML to PDF
    pisa_status = pisa.CreatePDF(
        src=html_content,
        dest=result,
        encoding='utf-8'
    )

    if pisa_status.err:
        raise Exception(f"Error generating PDF: {pisa_status.err}")

    result.seek(0)
    return result.read()


def generate_match_sheet_pdf(
    match: Dict[str, Any],
    player1: Dict[str, Any],
    player2: Dict[str, Any],
    group_name: Optional[str] = None,
    table_number: Optional[int] = None,
    scheduled_time: Optional[str] = None,
    tournament_name: Optional[str] = None,
    category: Optional[str] = None,
    round_number: Optional[int] = None
) -> bytes:
    """
    Generate a match sheet PDF for referees.

    Args:
        match: Match data dict
        player1: Player 1 data dict
        player2: Player 2 data dict
        group_name: Optional group name (e.g., "Grupo A")
        table_number: Optional table number
        scheduled_time: Optional scheduled time string
        tournament_name: Optional tournament name
        category: Optional category name
        round_number: Optional round number for group matches

    Returns:
        PDF as bytes
    """
    context = {
        "match": match,
        "player1": player1,
        "player2": player2,
        "group_name": group_name,
        "table_number": table_number,
        "scheduled_time": scheduled_time,
        "tournament_name": tournament_name or "Torneo de Tenis de Mesa",
        "category": category,
        "round_number": round_number,
    }

    html = render_html("match_sheet.html", context)
    return html_to_pdf(html)


def generate_group_sheet_pdf(
    group: Dict[str, Any],
    players: List[Dict[str, Any]],
    matches: List[Dict[str, Any]],
    results_matrix: Dict[int, Dict[int, str]],
    tournament_name: Optional[str] = None,
    category: Optional[str] = None
) -> bytes:
    """
    Generate a group sheet PDF with all matches and result matrix.

    Args:
        group: Group data dict
        players: List of player dicts with group_number
        matches: List of match dicts
        results_matrix: Results matrix for display
        tournament_name: Optional tournament name
        category: Optional category name

    Returns:
        PDF as bytes
    """
    context = {
        "group": group,
        "players": players,
        "matches": matches,
        "results_matrix": results_matrix,
        "tournament_name": tournament_name or "Torneo de Tenis de Mesa",
        "category": category,
    }

    html = render_html("group_sheet.html", context)
    return html_to_pdf(html)


def generate_match_list_pdf(
    matches: List[Dict[str, Any]],
    title: str = "Lista de Partidos",
    tournament_name: Optional[str] = None,
    category: Optional[str] = None,
    group_name: Optional[str] = None
) -> bytes:
    """
    Generate a match list PDF.

    Args:
        matches: List of match dicts with player info
        title: Title for the document
        tournament_name: Optional tournament name
        category: Optional category name
        group_name: Optional group name

    Returns:
        PDF as bytes
    """
    context = {
        "matches": matches,
        "title": title,
        "tournament_name": tournament_name or "Torneo de Tenis de Mesa",
        "category": category,
        "group_name": group_name,
    }

    html = render_html("match_list.html", context)
    return html_to_pdf(html)


def generate_all_match_sheets_pdf(
    matches_data: List[Dict[str, Any]],
    tournament_name: Optional[str] = None,
    category: Optional[str] = None
) -> bytes:
    """
    Generate a single PDF with all match sheets (one per page).

    Args:
        matches_data: List of dicts with match, player1, player2, group_name
        tournament_name: Optional tournament name
        category: Optional category name

    Returns:
        PDF as bytes
    """
    context = {
        "matches_data": matches_data,
        "tournament_name": tournament_name or "Torneo de Tenis de Mesa",
        "category": category,
    }

    html = render_html("all_match_sheets.html", context)
    return html_to_pdf(html)


def generate_bracket_tree_pdf(context: Dict[str, Any]) -> bytes:
    """
    Generate a bracket tree PDF (visual bracket visualization).

    Args:
        context: Dict with bracket data including:
            - tournament_name: Tournament name
            - category: Category name
            - slots_by_round: Dict[round_type, List[{slot, player}]]
            - matches_by_round: Dict[round_type, List[{match, player1, player2}]]
            - round_order: List of round types in order
            - round_names: Dict mapping round types to display names
            - best_of: Match format (3, 5, or 7)
            - champion: Champion player object or None
            - generation_date: Date string

    Returns:
        PDF as bytes
    """
    html = render_html("bracket_tree.html", context)
    return html_to_pdf(html)


def generate_scheduler_pdf(context: Dict[str, Any]) -> bytes:
    """
    Generate a scheduler grid PDF.

    Args:
        context: Dict with scheduler data including:
            - tournament_name: Tournament name
            - session: Session object
            - time_slots: List of time slots
            - tables: List of table numbers
            - schedule_grid: Dict mapping (time, table) to match data
            - generation_date: Date string

    Returns:
        PDF as bytes
    """
    html = render_html("scheduler_grid.html", context)
    return html_to_pdf(html)
