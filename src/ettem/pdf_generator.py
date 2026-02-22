"""
PDF Generator Module for ETTEM
Generates printable PDFs for matches, groups, brackets, etc.
Uses xhtml2pdf for HTML to PDF conversion.
"""

import io
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    from xhtml2pdf import pisa
    HAS_PISA = True
except ImportError:
    pisa = None
    HAS_PISA = False
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


def _prepare_branding_for_pdf(branding: Dict[str, Any]) -> Dict[str, Any]:
    """Convert branding data for PDF rendering (file:// URI for logo)."""
    result = dict(branding)
    if "logo_file_path" in result:
        # xhtml2pdf needs file:// URI for local images
        result["logo_src"] = f"file://{result['logo_file_path']}"
    return result


def html_to_pdf(html_content: str) -> bytes:
    """Convert HTML string to PDF bytes."""
    if not HAS_PISA:
        raise ImportError("xhtml2pdf is not available (Python 3.14+ cffi issue). PDF generation disabled.")
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
    round_number: Optional[int] = None,
    is_doubles: bool = False,
    branding: Optional[Dict[str, Any]] = None
) -> bytes:
    """Generate a match sheet PDF for referees."""
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
        "is_doubles": is_doubles,
        "branding": _prepare_branding_for_pdf(branding) if branding else {},
        "country_colors": branding.get("country_colors", {}) if branding else {},
    }

    html = render_html("match_sheet.html", context)
    return html_to_pdf(html)


def generate_group_sheet_pdf(
    group: Dict[str, Any],
    players: List[Dict[str, Any]],
    matches: List[Dict[str, Any]],
    results_matrix: Dict[int, Dict[int, str]],
    tournament_name: Optional[str] = None,
    category: Optional[str] = None,
    branding: Optional[Dict[str, Any]] = None
) -> bytes:
    """Generate a group sheet PDF with all matches and result matrix."""
    context = {
        "group": group,
        "players": players,
        "matches": matches,
        "results_matrix": results_matrix,
        "tournament_name": tournament_name or "Torneo de Tenis de Mesa",
        "category": category,
        "branding": _prepare_branding_for_pdf(branding) if branding else {},
        "country_colors": branding.get("country_colors", {}) if branding else {},
    }

    html = render_html("group_sheet.html", context)
    return html_to_pdf(html)


def generate_match_list_pdf(
    matches: List[Dict[str, Any]],
    title: str = "Lista de Partidos",
    tournament_name: Optional[str] = None,
    category: Optional[str] = None,
    group_name: Optional[str] = None,
    branding: Optional[Dict[str, Any]] = None
) -> bytes:
    """Generate a match list PDF."""
    context = {
        "matches": matches,
        "title": title,
        "tournament_name": tournament_name or "Torneo de Tenis de Mesa",
        "category": category,
        "group_name": group_name,
        "branding": _prepare_branding_for_pdf(branding) if branding else {},
        "country_colors": branding.get("country_colors", {}) if branding else {},
    }

    html = render_html("match_list.html", context)
    return html_to_pdf(html)


def generate_all_match_sheets_pdf(
    matches_data: List[Dict[str, Any]],
    tournament_name: Optional[str] = None,
    category: Optional[str] = None,
    is_doubles: bool = False,
    branding: Optional[Dict[str, Any]] = None
) -> bytes:
    """Generate a single PDF with all match sheets (2 per page)."""
    context = {
        "matches_data": matches_data,
        "tournament_name": tournament_name or "Torneo de Tenis de Mesa",
        "category": category,
        "is_doubles": is_doubles,
        "branding": _prepare_branding_for_pdf(branding) if branding else {},
        "country_colors": branding.get("country_colors", {}) if branding else {},
    }

    html = render_html("all_match_sheets.html", context)
    return html_to_pdf(html)


def generate_bracket_tree_pdf(context: Dict[str, Any]) -> bytes:
    """Generate a bracket tree PDF."""
    if "branding" in context and context["branding"]:
        context["branding"] = _prepare_branding_for_pdf(context["branding"])
    if "branding" not in context:
        context["branding"] = {}
    if "country_colors" not in context:
        context["country_colors"] = context.get("branding", {}).get("country_colors", {})
    html = render_html("bracket_tree.html", context)
    return html_to_pdf(html)


def generate_scheduler_pdf(context: Dict[str, Any]) -> bytes:
    """Generate a scheduler grid PDF."""
    if "branding" in context and context["branding"]:
        context["branding"] = _prepare_branding_for_pdf(context["branding"])
    if "branding" not in context:
        context["branding"] = {}
    if "country_colors" not in context:
        context["country_colors"] = context.get("branding", {}).get("country_colors", {})
    html = render_html("scheduler_grid.html", context)
    return html_to_pdf(html)


def generate_certificate_pdf(
    certificates: List[Dict[str, Any]],
    tournament_name: Optional[str] = None,
    branding: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Generate certificate/diploma PDFs for podium finishers.

    Args:
        certificates: List of dicts with keys: player_name, pais_cd, position, category
        tournament_name: Tournament name fallback
        branding: Branding data (logo, organizer, etc.)
    """
    context = {
        "certificates": certificates,
        "tournament_name": tournament_name or "Torneo de Tenis de Mesa",
        "branding": _prepare_branding_for_pdf(branding) if branding else {},
    }
    html = render_html("certificate.html", context)
    return html_to_pdf(html)
