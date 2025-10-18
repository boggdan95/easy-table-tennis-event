"""CSV import/export utilities."""

import csv
from pathlib import Path
from typing import Optional

from ettem.models import Gender, Player


# ISO-3 country codes (common ones for table tennis)
VALID_COUNTRY_CODES = {
    "ARG", "AUS", "AUT", "BEL", "BRA", "CAN", "CHI", "CHN", "COL", "CRO",
    "CUB", "CZE", "DEN", "EGY", "ESP", "FRA", "GBR", "GER", "GRE", "HKG",
    "HUN", "IND", "IRL", "ISR", "ITA", "JPN", "KOR", "MEX", "NED", "NOR",
    "NZL", "POL", "POR", "ROU", "RUS", "SGP", "SRB", "SVK", "SWE", "SUI",
    "TPE", "TUR", "UKR", "USA", "VEN",
}


class CSVImportError(Exception):
    """Error during CSV import."""
    pass


def validate_player_row(row: dict, row_num: int) -> dict:
    """Validate a player row from CSV.

    Args:
        row: Dictionary with CSV columns
        row_num: Row number for error messages

    Returns:
        Validated dictionary with cleaned data

    Raises:
        CSVImportError: If validation fails
    """
    errors = []

    # Required fields
    required_fields = ["id", "nombre", "apellido", "genero", "pais_cd", "ranking_pts", "categoria"]
    for field in required_fields:
        if field not in row or not row[field].strip():
            errors.append(f"Missing required field '{field}'")

    if errors:
        raise CSVImportError(f"Row {row_num}: {', '.join(errors)}")

    # Validate and clean data
    validated = {}

    # ID (original_id from CSV)
    try:
        validated["original_id"] = int(row["id"])
    except ValueError:
        raise CSVImportError(f"Row {row_num}: 'id' must be a number, got '{row['id']}'")

    # Name fields
    validated["nombre"] = row["nombre"].strip()
    validated["apellido"] = row["apellido"].strip()

    # Gender
    genero = row["genero"].strip().upper()
    if genero not in ("M", "F"):
        raise CSVImportError(
            f"Row {row_num}: 'genero' must be 'M' or 'F', got '{row['genero']}'"
        )
    validated["genero"] = Gender.MALE if genero == "M" else Gender.FEMALE

    # Country code (ISO-3)
    pais_cd = row["pais_cd"].strip().upper()
    if len(pais_cd) != 3:
        raise CSVImportError(
            f"Row {row_num}: 'pais_cd' must be 3 characters (ISO-3), got '{row['pais_cd']}'"
        )
    if pais_cd not in VALID_COUNTRY_CODES:
        # Warning but allow - might be a less common country
        print(f"WARNING Row {row_num}: Country code '{pais_cd}' not in common list, but accepting it")
    validated["pais_cd"] = pais_cd

    # Ranking points
    try:
        validated["ranking_pts"] = float(row["ranking_pts"])
        if validated["ranking_pts"] < 0:
            raise CSVImportError(f"Row {row_num}: 'ranking_pts' cannot be negative")
    except ValueError:
        raise CSVImportError(
            f"Row {row_num}: 'ranking_pts' must be a number, got '{row['ranking_pts']}'"
        )

    # Category
    validated["categoria"] = row["categoria"].strip().upper()

    return validated


def import_players_csv(
    csv_path: str,
    category_filter: Optional[str] = None,
    skip_duplicates: bool = True
) -> list[Player]:
    """Import players from CSV file.

    CSV format:
        id,nombre,apellido,genero,pais_cd,ranking_pts,categoria
        1,Juan,Perez,M,ESP,1200,U13

    Args:
        csv_path: Path to CSV file
        category_filter: Only import players from this category (None = all)
        skip_duplicates: Skip rows with duplicate original_id

    Returns:
        List of Player objects ready to be saved to database

    Raises:
        CSVImportError: If file not found or validation fails
    """
    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise CSVImportError(f"CSV file not found: {csv_path}")

    players = []
    seen_ids = set()
    skipped_count = 0

    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Validate header
        required_cols = {"id", "nombre", "apellido", "genero", "pais_cd", "ranking_pts", "categoria"}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            missing = required_cols - set(reader.fieldnames or [])
            raise CSVImportError(f"CSV missing required columns: {missing}")

        for row_num, row in enumerate(reader, start=2):  # Start at 2 (row 1 is header)
            try:
                # Validate row
                validated = validate_player_row(row, row_num)

                # Filter by category if requested
                if category_filter and validated["categoria"] != category_filter.upper():
                    skipped_count += 1
                    continue

                # Check for duplicates
                if skip_duplicates and validated["original_id"] in seen_ids:
                    print(f"WARNING Row {row_num}: Duplicate ID {validated['original_id']}, skipping")
                    skipped_count += 1
                    continue

                seen_ids.add(validated["original_id"])

                # Create Player object (id will be auto-generated by DB)
                player = Player(
                    id=0,  # Will be auto-generated
                    nombre=validated["nombre"],
                    apellido=validated["apellido"],
                    genero=validated["genero"],
                    pais_cd=validated["pais_cd"],
                    ranking_pts=validated["ranking_pts"],
                    categoria=validated["categoria"],
                    original_id=validated["original_id"],
                )
                players.append(player)

            except CSVImportError as e:
                print(f"ERROR: {e}")
                raise

    print(f"SUCCESS: Validated {len(players)} players from CSV")
    if skipped_count > 0:
        print(f"INFO: Skipped {skipped_count} rows (category filter or duplicates)")

    return players


def export_groups_csv(groups: list, players_by_id: dict, matches_by_group: dict, path: str):
    """Export groups to CSV.

    Args:
        groups: List of Group ORM objects
        players_by_id: Dictionary mapping player_id to Player ORM
        matches_by_group: Dictionary mapping group_id to list of Match ORMs
        path: Output CSV path
    """
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Group", "Player_ID", "Player_Name", "Country", "Seed", "Group_Number"])

        for group in groups:
            for player_id in group.player_ids:
                player = players_by_id.get(player_id)
                if player:
                    writer.writerow([
                        group.name,
                        player.id,
                        f"{player.nombre} {player.apellido}",
                        player.pais_cd,
                        player.seed or "",
                        player.group_number or "",
                    ])


def export_standings_csv(standings: list, players_by_id: dict, path: str):
    """Export standings to CSV.

    Args:
        standings: List of GroupStanding ORM objects
        players_by_id: Dictionary mapping player_id to Player ORM
        path: Output CSV path
    """
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Group_ID", "Position", "Player_ID", "Player_Name", "Country",
            "Points", "Wins", "Losses", "Sets_W", "Sets_L", "Points_W", "Points_L"
        ])

        for standing in standings:
            player = players_by_id.get(standing.player_id)
            if player:
                writer.writerow([
                    standing.group_id,
                    standing.position or "",
                    player.id,
                    f"{player.nombre} {player.apellido}",
                    player.pais_cd,
                    standing.points_total,
                    standing.wins,
                    standing.losses,
                    standing.sets_w,
                    standing.sets_l,
                    standing.points_w,
                    standing.points_l,
                ])


def export_bracket_csv(bracket, players_by_id: dict, path: str):
    """Export bracket to CSV.

    Args:
        bracket: Bracket object with slots
        players_by_id: Dictionary mapping player_id to Player ORM
        path: Output CSV path
    """
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Round", "Slot_Number", "Player_ID", "Player_Name", "Country", "Is_BYE", "Same_Country_Warning"])

        for round_type, slots in bracket.slots.items():
            for slot in slots:
                player_name = ""
                country = ""
                if slot.player_id and not slot.is_bye:
                    player = players_by_id.get(slot.player_id)
                    if player:
                        player_name = f"{player.nombre} {player.apellido}"
                        country = player.pais_cd

                writer.writerow([
                    round_type.value if hasattr(round_type, "value") else round_type,
                    slot.slot_number,
                    slot.player_id or "",
                    player_name,
                    country,
                    "YES" if slot.is_bye else "NO",
                    "YES" if slot.same_country_warning else "NO",
                ])
