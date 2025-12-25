#!/usr/bin/env python3
"""Script to create bracket matches from bracket slots."""

import sys
sys.path.insert(0, 'src')

from ettem.webapp.app import get_db_session
from ettem.storage import BracketRepository, MatchRepository
from ettem.models import Match, MatchStatus, RoundType


def main():
    """Create bracket matches from slots."""
    session = get_db_session()
    bracket_repo = BracketRepository(session)
    match_repo = MatchRepository(session)

    print("=" * 60)
    print("Creando partidos del bracket desde los slots...")
    print("=" * 60)

    # Get all bracket slots for U13
    slots = bracket_repo.get_by_category("U13")

    if not slots:
        print("[ERROR] No se encontraron slots de bracket para U13")
        print("   Ejecuta 'build-bracket' primero")
        return

    print(f"[INFO] Encontrados {len(slots)} slots de bracket")

    # Group slots by round
    from collections import defaultdict
    slots_by_round = defaultdict(list)
    for slot in slots:
        slots_by_round[slot.round_type].append(slot)

    # Sort slots within each round by slot_number
    for round_type in slots_by_round:
        slots_by_round[round_type].sort(key=lambda s: s.slot_number)

    # Determine round order
    round_order = [
        RoundType.ROUND_OF_32,
        RoundType.ROUND_OF_16,
        RoundType.QUARTERFINAL,
        RoundType.SEMIFINAL,
        RoundType.FINAL
    ]

    # Get first round that has slots
    first_round = None
    for rt in round_order:
        if rt in slots_by_round and slots_by_round[rt]:
            first_round = rt
            break

    if not first_round:
        print("[ERROR] No se encontraron slots válidos")
        return

    print(f"[INFO] Primera ronda: {first_round.value}")

    # Create match ID mapping (will be populated after creating matches)
    match_id_map = {}  # (round_type, match_number) -> match_id

    # Calculate total rounds needed based on first round
    total_rounds = []
    if first_round == RoundType.ROUND_OF_32:
        total_rounds = [RoundType.ROUND_OF_32, RoundType.ROUND_OF_16, RoundType.QUARTERFINAL, RoundType.SEMIFINAL, RoundType.FINAL]
    elif first_round == RoundType.ROUND_OF_16:
        total_rounds = [RoundType.ROUND_OF_16, RoundType.QUARTERFINAL, RoundType.SEMIFINAL, RoundType.FINAL]
    elif first_round == RoundType.QUARTERFINAL:
        total_rounds = [RoundType.QUARTERFINAL, RoundType.SEMIFINAL, RoundType.FINAL]
    elif first_round == RoundType.SEMIFINAL:
        total_rounds = [RoundType.SEMIFINAL, RoundType.FINAL]
    elif first_round == RoundType.FINAL:
        total_rounds = [RoundType.FINAL]

    print(f"[INFO] Creando estructura completa: {' -> '.join([r.value for r in total_rounds])}")

    # Process each round in order
    total_matches = 0
    previous_matches_count = len(slots_by_round.get(first_round, [])) // 2

    for current_round_type in total_rounds:
        round_slots = slots_by_round.get(current_round_type, [])

        print(f"\n[BUILD] Creando partidos para {current_round_type.value}...")

        # Determine how many matches in this round
        if round_slots:
            # Has slots - create from slots
            num_matches = len(round_slots) // 2
        else:
            # No slots yet - calculate from previous round
            num_matches = previous_matches_count // 2

        for match_num in range(1, num_matches + 1):
            # Try to get players from slots if available
            player1_id = None
            player2_id = None

            if round_slots and (match_num - 1) * 2 + 1 < len(round_slots):
                slot1 = round_slots[(match_num - 1) * 2]
                slot2 = round_slots[(match_num - 1) * 2 + 1]
                player1_id = slot1.player_id if not slot1.is_bye else None
                player2_id = slot2.player_id if not slot2.is_bye else None

            round_name = f"{current_round_type.value}{match_num}"

            # Create match
            match = Match(
                id=0,  # Will be assigned by DB
                player1_id=player1_id,
                player2_id=player2_id,
                group_id=None,  # Bracket match
                round_type=current_round_type,
                round_name=round_name,
                match_number=match_num,
                status=MatchStatus.PENDING,
            )

            created_match = match_repo.create(match)
            match_id_map[(current_round_type, match_num)] = created_match.id
            total_matches += 1

            # Show match details
            p1_name = f"Player {player1_id}" if player1_id else "TBD"
            p2_name = f"Player {player2_id}" if player2_id else "TBD"
            print(f"  Match {match_num}: {p1_name} vs {p2_name}")

        previous_matches_count = num_matches

    # Now update matches with next_match_id pointers
    print(f"\n[UPDATE] Actualizando punteros next_match_id...")

    # Map: (round, match_num) -> next_round_match_num
    # In single elimination: match 1 & 2 -> next match 1, match 3 & 4 -> next match 2, etc.
    all_matches = match_repo.get_all()
    bracket_matches = [m for m in all_matches if m.round_type != RoundType.ROUND_ROBIN]

    for match in bracket_matches:
        # Handle both string and enum values
        round_type_str = match.round_type if isinstance(match.round_type, str) else match.round_type.value

        # Determine next round and match
        next_round = None
        if round_type_str in [RoundType.ROUND_OF_32, RoundType.ROUND_OF_32.value, "R32"]:
            next_round = RoundType.ROUND_OF_16
        elif round_type_str in [RoundType.ROUND_OF_16, RoundType.ROUND_OF_16.value, "R16"]:
            next_round = RoundType.QUARTERFINAL
        elif round_type_str in [RoundType.QUARTERFINAL, RoundType.QUARTERFINAL.value, "QF"]:
            next_round = RoundType.SEMIFINAL
        elif round_type_str in [RoundType.SEMIFINAL, RoundType.SEMIFINAL.value, "SF"]:
            next_round = RoundType.FINAL

        if next_round:
            # Calculate which match in the next round
            next_match_num = ((match.match_number - 1) // 2) + 1
            next_slot = 1 if (match.match_number % 2 == 1) else 2

            # Find the next match ID
            next_match_key = (next_round, next_match_num)
            if next_match_key in match_id_map:
                match.next_match_id = match_id_map[next_match_key]
                match.next_match_slot = next_slot
                match_repo.update(match)
                print(f"  Match {round_type_str}{match.match_number} -> {next_round.value}{next_match_num} (slot {next_slot})")

    print(f"\n[SUCCESS] Creados {total_matches} partidos de bracket!")
    print("\nPuedes revisar:")
    print("  - Bracket: http://127.0.0.1:8000/bracket/U13")
    print("  - Partidos: http://127.0.0.1:8000/bracket_matches/U13")


if __name__ == "__main__":
    main()
