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


def build_bracket(
    qualifiers: list[tuple[Player, GroupStanding]],
    category: str,
    random_seed: Optional[int] = None,
    player_repo: Optional[PlayerRepository] = None,
) -> Bracket:
    """Build knockout bracket from group stage qualifiers.

    Placement strategy:
    1. G1 (best 1st place): top slot (#1)
    2. G2 (second best 1st place): bottom slot (last)
    3. Other 1st place finishers: random draw in predefined slots
    4. 2nd place finishers: opposite half from their group's 1st place
    5. Fill remaining slots with BYEs
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
    num_byes = bracket_size - num_qualifiers

    # Determine starting round type
    first_round = get_round_type_for_size(bracket_size)

    # Initialize bracket
    bracket = Bracket(category=category)
    bracket.slots[first_round] = []

    # Create slots (1-indexed for top-to-bottom positioning)
    for slot_num in range(1, bracket_size + 1):
        slot = BracketSlot(
            slot_number=slot_num,
            round_type=first_round,
            player_id=None,
            is_bye=False,
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

    # Place G1 at top
    if sorted_firsts:
        g1_player, g1_standing = sorted_firsts[0]
        bracket.slots[first_round][0].player_id = g1_player.id

    # Place G2 at bottom
    if len(sorted_firsts) > 1:
        g2_player, g2_standing = sorted_firsts[1]
        bracket.slots[first_round][-1].player_id = g2_player.id

    # Remaining firsts (if any)
    remaining_firsts = sorted_firsts[2:]

    # Predefined slots for remaining firsts (avoid top and bottom which are taken)
    # Strategy: place in quarters of the bracket
    # For 16-player bracket: slots 1, 16 are taken; good slots: 5, 8, 9, 12, etc.
    available_slots_for_firsts = []
    if bracket_size >= 8:
        # For 8: slots 1, 8 taken; available: 3, 4, 5, 6
        quarter = bracket_size // 4
        for i in range(1, 4):  # 3 quarters (skip first and last)
            slot_idx = i * quarter
            # Avoid already taken slots
            if bracket.slots[first_round][slot_idx - 1].player_id is None:
                available_slots_for_firsts.append(slot_idx - 1)  # Convert to 0-indexed

    # If not enough predefined slots, add more
    if len(available_slots_for_firsts) < len(remaining_firsts):
        for i in range(1, bracket_size - 1):
            if i - 1 not in available_slots_for_firsts and bracket.slots[first_round][i - 1].player_id is None:
                available_slots_for_firsts.append(i - 1)

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
            # Just place in any available slot
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

        # Find available slot in target range
        placed = False
        for slot_num in target_range:
            slot = bracket.slots[first_round][slot_num]
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

    # Fill remaining slots with BYEs
    for slot in bracket.slots[first_round]:
        if slot.player_id is None:
            slot.is_bye = True

    # Annotate same-country matches (non-blocking warnings)
    if player_repo:
        annotate_same_country_matches(bracket, first_round, player_repo)

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
