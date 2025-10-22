"""Validation rules for table tennis matches.

This module implements ITTF (International Table Tennis Federation) rules
for set scoring and match formats.
"""

from typing import Optional


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


def validate_tt_set(score_a: int, score_b: int) -> tuple[bool, str]:
    """Validate a single table tennis set score.

    ITTF Rules:
    - A set is won by the first player to reach 11 points
    - If both players reach 10 points (deuce), the winner must have exactly 2 points more
    - No upper limit exists (e.g., 15-13, 20-18 are valid)

    Args:
        score_a: Points scored by player A
        score_b: Points scored by player B

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if the set score is valid
        - error_message: Empty string if valid, otherwise contains the error description

    Examples:
        >>> validate_tt_set(11, 9)
        (True, '')
        >>> validate_tt_set(12, 10)
        (True, '')
        >>> validate_tt_set(15, 13)
        (True, '')
        >>> validate_tt_set(11, 10)
        (False, 'In deuce (≥10-10), winner must have exactly +2 points (current difference: 1)')
        >>> validate_tt_set(10, 8)
        (False, 'Winner must reach at least 11 points (current: 10)')
        >>> validate_tt_set(13, 12)
        (False, 'In deuce (≥10-10), winner must have exactly +2 points (current difference: 1)')
    """
    # Validate inputs
    if score_a < 0 or score_b < 0:
        return False, "Los puntajes no pueden ser negativos"

    if score_a == score_b:
        return False, "El set no puede estar empatado (debe haber un ganador)"

    winner_score = max(score_a, score_b)
    loser_score = min(score_a, score_b)
    diff = winner_score - loser_score

    # Rule 1: Winner must reach at least 11 points
    if winner_score < 11:
        return False, f"El ganador debe alcanzar al menos 11 puntos (actual: {winner_score})"

    # Rule 2: In deuce situation (both players ≥ 10), difference must be exactly 2
    if loser_score >= 10:
        if diff != 2:
            return (
                False,
                f"En deuce (≥10-10), el ganador debe tener exactamente +2 puntos (diferencia actual: {diff})",
            )

    # Rule 3: Normal situation (loser < 10), difference must be at least 2
    elif diff < 2:
        return False, f"El ganador debe tener al menos +2 puntos (diferencia actual: {diff})"

    return True, ""


def validate_match_sets(
    sets: list[tuple[int, int]], best_of: int = 5
) -> tuple[bool, str]:
    """Validate all sets in a table tennis match.

    Args:
        sets: List of (player1_score, player2_score) tuples for each set
        best_of: Match format (3, 5, or 7). Common formats:
                 - Best of 3: First to win 2 sets
                 - Best of 5: First to win 3 sets (standard)
                 - Best of 7: First to win 4 sets

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_match_sets([(11, 9), (11, 7), (11, 5)])
        (True, '')
        >>> validate_match_sets([(11, 9), (8, 11), (12, 10), (11, 6)])
        (True, '')
        >>> validate_match_sets([(11, 9), (11, 10)])
        (False, 'Set 2: In deuce (≥10-10), winner must have exactly +2 points (current difference: 1)')
    """
    if not sets:
        return False, "El partido debe tener al menos un set"

    # Validate number of sets
    max_sets = best_of
    min_sets = (best_of // 2) + 1  # Minimum sets to win

    if len(sets) > max_sets:
        return False, f"Demasiados sets para formato mejor de {best_of} (máximo: {max_sets}, ingresados: {len(sets)})"

    if len(sets) < min_sets:
        return False, f"No hay suficientes sets jugados (mínimo {min_sets} para mejor de {best_of}, ingresados: {len(sets)})"

    # Validate each set individually
    for idx, (score_a, score_b) in enumerate(sets, start=1):
        is_valid, error_msg = validate_tt_set(score_a, score_b)
        if not is_valid:
            return False, f"Set {idx}: {error_msg}"

    # Validate that match is complete (one player won required sets)
    sets_to_win = (best_of // 2) + 1
    p1_sets_won = sum(1 for s_a, s_b in sets if s_a > s_b)
    p2_sets_won = sum(1 for s_a, s_b in sets if s_b > s_a)

    if p1_sets_won < sets_to_win and p2_sets_won < sets_to_win:
        return False, f"Partido incompleto: ningún jugador ha ganado {sets_to_win} sets (mejor de {best_of})"

    # Validate that match wasn't played beyond necessary
    if p1_sets_won == sets_to_win or p2_sets_won == sets_to_win:
        # Check if there are extra sets after someone already won
        sets_after_winner = len(sets) - (p1_sets_won + p2_sets_won)
        if sets_after_winner > 0:
            return False, "El partido tiene sets extras después de que se determinó un ganador"

    return True, ""


def validate_walkover(
    player1_id: int, player2_id: int, winner_id: int
) -> tuple[bool, str]:
    """Validate walkover data.

    Args:
        player1_id: ID of first player
        player2_id: ID of second player
        winner_id: ID of the player who won by walkover

    Returns:
        Tuple of (is_valid, error_message)
    """
    if winner_id not in (player1_id, player2_id):
        return False, "El ganador debe ser uno de los dos jugadores del partido"

    return True, ""
