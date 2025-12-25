#!/usr/bin/env python3
"""Script to fill bracket matches with results and advance winners."""

import sys
sys.path.insert(0, 'src')

from ettem.webapp.app import get_db_session
from ettem.storage import MatchRepository, PlayerRepository
from ettem.models import MatchStatus, RoundType
from fill_results import generate_match_result


def main():
    """Fill bracket matches with results."""
    session = get_db_session()
    match_repo = MatchRepository(session)
    player_repo = PlayerRepository(session)

    # Get all bracket matches
    all_matches = match_repo.get_all()
    bracket_matches = [
        m for m in all_matches
        if m.round_type != RoundType.ROUND_ROBIN
    ]

    print(f"Found {len(bracket_matches)} bracket matches")

    # Group by round for processing
    rounds_order = ['ROUND_OF_16', 'QUARTER_FINALS', 'SEMI_FINALS', 'FINAL']

    for round_name in rounds_order:
        round_matches = [
            m for m in bracket_matches
            if m.round_type == round_name and m.status == MatchStatus.PENDING
        ]

        if not round_matches:
            continue

        print(f"\nProcessing {round_name}: {len(round_matches)} matches")

        for match in round_matches:
            # Get player seeds
            p1 = player_repo.get_by_id(match.player1_id)
            p2 = player_repo.get_by_id(match.player2_id)

            if not p1 or not p2:
                print(f"  Skipping match {match.id}: missing players")
                continue

            seed1 = p1.seed if p1.seed else 999
            seed2 = p2.seed if p2.seed else 999

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

            winner = player_repo.get_by_id(winner_id)
            print(f"  {p1.nombre} {p1.apellido} vs {p2.nombre} {p2.apellido} -> Winner: {winner.nombre} {winner.apellido}")

            # Find next match and advance winner
            if match.next_match_id:
                next_match = match_repo.get_by_id(match.next_match_id)
                if next_match:
                    if match.next_match_slot == 1:
                        next_match.player1_id = winner_id
                    else:
                        next_match.player2_id = winner_id
                    match_repo.update(next_match)
                    print(f"    -> Advanced to next match (slot {match.next_match_slot})")

    print("\n[OK] All bracket matches completed!")
    print("View results: http://127.0.0.1:8000/category/U13")
    print("View final results: http://127.0.0.1:8000/category/U13/results")


if __name__ == "__main__":
    main()
