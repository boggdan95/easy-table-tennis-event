"""Knockout bracket generator."""

import math
import random
from typing import Optional

from ettem.models import Bracket, BracketSlot, GroupStanding, Player, RoundType
from ettem.storage import PlayerRepository


def next_power_of_2(n: int) -> int:
    """Return the next power of 2 >= n.

    Examples:
        >>> next_power_of_2(5)
        8
        >>> next_power_of_2(8)
        8
        >>> next_power_of_2(15)
        16
    """
    if n <= 0:
        return 1
    return 2 ** math.ceil(math.log2(n))


def get_round_type_for_size(bracket_size: int) -> RoundType:
    """Get the RoundType for a given bracket size.

    Args:
        bracket_size: Power of 2 (8, 16, 32, etc.)

    Returns:
        RoundType for the first round
    """
    if bracket_size == 2:
        return RoundType.FINAL
    elif bracket_size == 4:
        return RoundType.SEMIFINAL
    elif bracket_size == 8:
        return RoundType.QUARTERFINAL
    elif bracket_size == 16:
        return RoundType.ROUND_OF_16
    elif bracket_size == 32:
        return RoundType.ROUND_OF_32
    else:
        # For larger brackets, default to R32
        return RoundType.ROUND_OF_32


def get_bye_positions_for_bracket(num_qualifiers: int, bracket_size: int) -> set[int]:
    """Get the correct BYE positions for a bracket.

    BYE positions must be placed such that:
    1. BYEs never face each other (no BYE vs BYE matches)
    2. Each BYE faces a player who gets automatic advancement

    In a bracket, matches are formed by pairing slots: (1,2), (3,4), (5,6), etc.
    So BYEs should be in positions that pair with players, not other BYEs.

    Standard ITTF BYE placement: BYEs go in even positions first, spread across bracket.
    """
    num_byes = bracket_size - num_qualifiers
    if num_byes <= 0:
        return set()

    # BYE positions for different bracket sizes
    # Key insight: BYEs should be in positions 2, 4, 6, 8... (even) to pair with 1, 3, 5, 7... (odd)
    # But distributed across the bracket, not clustered

    bye_positions = set()

    if bracket_size == 8:
        # 8-slot bracket: matches (1,2), (3,4), (5,6), (7,8)
        # BYEs in positions: 2, 4, 6, 8 (even positions)
        bye_order = [2, 7, 4, 5]  # Spread across bracket
        for i in range(min(num_byes, len(bye_order))):
            bye_positions.add(bye_order[i])

    elif bracket_size == 16:
        # 16-slot bracket: matches (1,2), (3,4), ..., (15,16)
        # BYEs should pair players with BYEs, not BYE with BYE
        # Even positions that spread across: 2, 15, 7, 10, 4, 13, 6, 11
        bye_order = [2, 15, 7, 10, 4, 13, 6, 11]
        for i in range(min(num_byes, len(bye_order))):
            bye_positions.add(bye_order[i])

    elif bracket_size == 32:
        # 32-slot bracket
        bye_order = [2, 31, 7, 26, 10, 23, 15, 18, 4, 29, 6, 27, 11, 22, 14, 19]
        for i in range(min(num_byes, len(bye_order))):
            bye_positions.add(bye_order[i])

    else:
        # Fallback: use even positions spread across bracket
        all_even = [i for i in range(2, bracket_size + 1, 2)]
        # Interleave from ends
        bye_order = []
        left, right = 0, len(all_even) - 1
        while left <= right:
            if left == right:
                bye_order.append(all_even[left])
            else:
                bye_order.append(all_even[left])
                bye_order.append(all_even[right])
            left += 1
            right -= 1
        for i in range(min(num_byes, len(bye_order))):
            bye_positions.add(bye_order[i])

    return bye_positions


def build_bracket(
    qualifiers: list[tuple[Player, GroupStanding]],
    category: str,
    random_seed: Optional[int] = None,
    player_repo: Optional[PlayerRepository] = None,
) -> Bracket:
    """Build knockout bracket from group stage qualifiers.

    Placement strategy:
    1. First, determine BYE positions (ensuring no BYE vs BYE matches)
    2. G1 (best 1st place): top slot (#1)
    3. G2 (second best 1st place): bottom slot (last)
    4. Other 1st place finishers: random draw in predefined slots
    5. 2nd place finishers: opposite half from their group's 1st place
    6. Annotate same-country 1st round matches (non-blocking)

    Args:
        qualifiers: List of (Player, GroupStanding) tuples
        category: Category name
        random_seed: Optional random seed for deterministic draws
        player_repo: Optional PlayerRepository for fetching player country codes

    Returns:
        Bracket object with slots filled
    """
    if not qualifiers:
        raise ValueError("Cannot build bracket with no qualifiers")

    if random_seed is not None:
        random.seed(random_seed)

    # Separate 1st and 2nd place finishers
    firsts = [(p, s) for p, s in qualifiers if s.position == 1]
    seconds = [(p, s) for p, s in qualifiers if s.position == 2]

    # Determine bracket size
    num_qualifiers = len(qualifiers)
    bracket_size = next_power_of_2(num_qualifiers)

    # Get BYE positions FIRST (this is the key fix)
    bye_positions = get_bye_positions_for_bracket(num_qualifiers, bracket_size)

    # Determine starting round type
    first_round = get_round_type_for_size(bracket_size)

    # Initialize bracket with BYEs already placed
    bracket = Bracket(category=category)
    bracket.slots[first_round] = []

    # Create slots (1-indexed for top-to-bottom positioning)
    for slot_num in range(1, bracket_size + 1):
        slot = BracketSlot(
            slot_number=slot_num,
            round_type=first_round,
            player_id=None,
            is_bye=slot_num in bye_positions,  # Pre-place BYEs
        )
        bracket.slots[first_round].append(slot)

    # Sort firsts by their group standing stats to determine G1 and G2
    # Best 1st = highest points_total, then tiebreak by sets_ratio, points_ratio, seed
    def first_place_sort_key(item):
        player, standing = item
        return (
            -standing.points_total,
            -standing.sets_ratio,
            -standing.points_ratio,
            player.seed if player.seed else 999,
        )

    sorted_firsts = sorted(firsts, key=first_place_sort_key)

    # Place G1 at top (slot 1, but check if it's a BYE position)
    if sorted_firsts:
        g1_player, g1_standing = sorted_firsts[0]
        # Find first non-BYE slot starting from slot 1
        for slot in bracket.slots[first_round]:
            if not slot.is_bye and slot.player_id is None:
                slot.player_id = g1_player.id
                break

    # Place G2 at bottom (last slot, but check if it's a BYE position)
    if len(sorted_firsts) > 1:
        g2_player, g2_standing = sorted_firsts[1]
        # Find first non-BYE slot starting from the end
        for slot in reversed(bracket.slots[first_round]):
            if not slot.is_bye and slot.player_id is None:
                slot.player_id = g2_player.id
                break

    # Remaining firsts (if any)
    remaining_firsts = sorted_firsts[2:]

    # Get available non-BYE slots for remaining firsts
    available_slots_for_firsts = []
    if bracket_size >= 8:
        # Prefer quarter positions
        quarter = bracket_size // 4
        for i in range(1, 4):  # 3 quarters (skip first and last)
            slot_idx = i * quarter - 1  # 0-indexed
            slot = bracket.slots[first_round][slot_idx]
            if not slot.is_bye and slot.player_id is None:
                available_slots_for_firsts.append(slot_idx)

    # If not enough predefined slots, add more non-BYE slots
    for i, slot in enumerate(bracket.slots[first_round]):
        if i not in available_slots_for_firsts and not slot.is_bye and slot.player_id is None:
            available_slots_for_firsts.append(i)
            if len(available_slots_for_firsts) >= len(remaining_firsts) + len(seconds):
                break

    # Randomly assign remaining firsts to available slots
    random.shuffle(available_slots_for_firsts)
    for (player, standing), slot_idx in zip(remaining_firsts, available_slots_for_firsts):
        bracket.slots[first_round][slot_idx].player_id = player.id

    # Track which half/quarter each first-place player is in
    first_to_slot = {}
    for slot in bracket.slots[first_round]:
        if slot.player_id:
            for player, standing in firsts:
                if player.id == slot.player_id:
                    first_to_slot[standing.group_id] = slot.slot_number
                    break

    # Place seconds in opposite half from their group's first
    for player, standing in seconds:
        group_id = standing.group_id

        if group_id not in first_to_slot:
            # No first-place from this group (shouldn't happen in normal flow)
            # Just place in any available non-BYE slot
            for slot in bracket.slots[first_round]:
                if slot.player_id is None and not slot.is_bye:
                    slot.player_id = player.id
                    break
            continue

        first_slot = first_to_slot[group_id]

        # Determine opposite half
        # If first is in top half (slot <= bracket_size/2), put second in bottom half
        half_point = bracket_size // 2

        if first_slot <= half_point:
            # First is in top half, place second in bottom half
            target_range = range(half_point, bracket_size)
        else:
            # First is in bottom half, place second in top half
            target_range = range(0, half_point)

        # Find available non-BYE slot in target range
        placed = False
        for slot_idx in target_range:
            slot = bracket.slots[first_round][slot_idx]
            if slot.player_id is None and not slot.is_bye:
                slot.player_id = player.id
                placed = True
                break

        # If no slot available in preferred half, place anywhere
        if not placed:
            for slot in bracket.slots[first_round]:
                if slot.player_id is None and not slot.is_bye:
                    slot.player_id = player.id
                    break

    # Annotate same-country matches (non-blocking warnings)
    if player_repo:
        annotate_same_country_matches(bracket, first_round, player_repo)

    # Create subsequent rounds (empty slots for winners to advance into)
    # This is needed for process_bye_advancements to work
    round_progression = {
        RoundType.ROUND_OF_32: RoundType.ROUND_OF_16,
        RoundType.ROUND_OF_16: RoundType.QUARTERFINAL,
        RoundType.QUARTERFINAL: RoundType.SEMIFINAL,
        RoundType.SEMIFINAL: RoundType.FINAL,
    }

    current_round = first_round
    current_size = bracket_size

    while current_round in round_progression:
        next_round = round_progression[current_round]
        next_size = current_size // 2

        if next_size < 1:
            break

        bracket.slots[next_round] = []
        for slot_num in range(1, next_size + 1):
            slot = BracketSlot(
                slot_number=slot_num,
                round_type=next_round,
                player_id=None,
                is_bye=False,
            )
            bracket.slots[next_round].append(slot)

        current_round = next_round
        current_size = next_size

    return bracket


def annotate_same_country_matches(
    bracket: Bracket, round_type: RoundType, player_repo: PlayerRepository
) -> None:
    """Mark 1st round matches with same-country players.

    This is a non-blocking annotation for organizers to review.

    Args:
        bracket: Bracket object to annotate
        round_type: The round type to check (typically first round)
        player_repo: PlayerRepository for fetching country codes
    """
    slots = bracket.slots.get(round_type, [])

    # Matches are formed by pairing adjacent slots (1-2, 3-4, etc.)
    for i in range(0, len(slots), 2):
        if i + 1 >= len(slots):
            break

        slot1 = slots[i]
        slot2 = slots[i + 1]

        # Skip BYEs
        if slot1.is_bye or slot2.is_bye:
            continue

        if slot1.player_id is None or slot2.player_id is None:
            continue

        # Fetch players
        player1 = player_repo.get_by_id(slot1.player_id)
        player2 = player_repo.get_by_id(slot2.player_id)

        if player1 and player2 and player1.pais_cd == player2.pais_cd:
            # Same country! Flag both slots
            slot1.same_country_warning = True
            slot2.same_country_warning = True
