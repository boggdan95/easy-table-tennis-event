#!/usr/bin/env python3
"""Script to fill all pending matches with random realistic results."""

import random
import sys
sys.path.insert(0, 'src')

from ettem.webapp.app import get_db_session
from ettem.storage import MatchRepository
from ettem.models import MatchStatus, Set


def generate_set_score(winner_advantage: float = 0.6) -> tuple[int, int]:
    """Generate a realistic set score (11-x or x-11).

    Args:
        winner_advantage: Probability that winner wins (0.5-1.0)

    Returns:
        Tuple of (player1_points, player2_points)
    """
    # Determine winner of this set
    p1_wins = random.random() < winner_advantage

    if p1_wins:
        # Player 1 wins: 11-x where x is typically 0-9
        p1_score = 11
        # More likely to be close games (7-9) than blowouts (0-3)
        weights = [1, 1, 1, 2, 3, 4, 5, 6, 7, 8]  # 0-9
        p2_score = random.choices(range(10), weights=weights)[0]

        # Handle deuce (10-10 → 12-10, 13-11, etc.)
        if p2_score >= 10:
            p1_score = p2_score + 2
    else:
        # Player 2 wins: x-11
        p2_score = 11
        weights = [1, 1, 1, 2, 3, 4, 5, 6, 7, 8]
        p1_score = random.choices(range(10), weights=weights)[0]

        if p1_score >= 10:
            p2_score = p1_score + 2

    return (p1_score, p2_score)


def generate_match_result(seed1: int, seed2: int) -> tuple[list[Set], int]:
    """Generate a realistic match result based on seeds.

    Lower seed (better player) has advantage.

    Args:
        seed1: Seed of player 1
        seed2: Seed of player 2

    Returns:
        Tuple of (sets, winner_id_offset) where offset is 0 for player1, 1 for player2
    """
    # Calculate advantage: lower seed = better player
    # If seeds are equal, 50/50 chance
    # If seed difference is large, strong favorite
    seed_diff = seed2 - seed1  # Positive = player1 is better

    # Convert seed difference to win probability
    # seed_diff of -10 → ~40% for player1
    # seed_diff of 0 → 50%
    # seed_diff of +10 → ~60% for player1
    p1_advantage = 0.5 + (seed_diff * 0.01)
    p1_advantage = max(0.3, min(0.7, p1_advantage))  # Clamp to 30-70%

    # Determine match winner (best of 5 sets, win 3)
    p1_sets_won = 0
    p2_sets_won = 0
    sets = []
    set_number = 1

    while p1_sets_won < 3 and p2_sets_won < 3:
        p1_score, p2_score = generate_set_score(p1_advantage)

        if p1_score > p2_score:
            p1_sets_won += 1
        else:
            p2_sets_won += 1

        sets.append(Set(
            set_number=set_number,
            player1_points=p1_score,
            player2_points=p2_score
        ))
        set_number += 1

    winner_offset = 0 if p1_sets_won == 3 else 1

    # Validate result (should never have 4-0, etc.)
    from ettem.validation import validate_match_sets
    sets_tuples = [(s.player1_points, s.player2_points) for s in sets]
    is_valid, error_msg = validate_match_sets(sets_tuples, best_of=5)
    if not is_valid:
        raise ValueError(f"Generated invalid match result: {error_msg}\nSets: {sets_tuples}")

    return (sets, winner_offset)


def main():
    """Fill all pending matches with results."""
    session = get_db_session()
    match_repo = MatchRepository(session)

    # Get all matches
    all_matches = match_repo.get_all()
    pending_matches = [m for m in all_matches if m.status == MatchStatus.PENDING]

    print(f"Found {len(pending_matches)} pending matches")
    print("Filling with random realistic results...\n")

    # Import PlayerRepository to get seeds
    from ettem.storage import PlayerRepository
    player_repo = PlayerRepository(session)

    filled_count = 0
    for match in pending_matches:
        # Get player seeds
        p1 = player_repo.get_by_id(match.player1_id)
        p2 = player_repo.get_by_id(match.player2_id)

        seed1 = p1.seed if p1 and p1.seed else 999
        seed2 = p2.seed if p2 and p2.seed else 999

        # Generate result
        sets, winner_offset = generate_match_result(seed1, seed2)
        winner_id = match.player1_id if winner_offset == 0 else match.player2_id

        # Convert sets to dicts
        sets_dicts = [
            {
                'set_number': s.set_number,
                'player1_points': s.player1_points,
                'player2_points': s.player2_points
            }
            for s in sets
        ]

        # Update match
        match.sets = sets_dicts
        match.winner_id = winner_id
        match.status = MatchStatus.COMPLETED
        match.is_walkover = False
        match.played = True

        match_repo.update(match)
        filled_count += 1

        if filled_count % 10 == 0:
            print(f"  Filled {filled_count}/{len(pending_matches)} matches...")

    print(f"\n[OK] Successfully filled {filled_count} matches!")
    print("\nYou can now:")
    print("  1. Calculate standings: http://127.0.0.1:8000/admin/calculate-standings")
    print("  2. Generate bracket: http://127.0.0.1:8000/admin/generate-bracket")


if __name__ == "__main__":
    main()
