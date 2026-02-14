"""Knockout bracket generator."""

import math
import random
from typing import Optional, Union

from ettem.models import Bracket, BracketSlot, GroupStanding, Pair, Player, RoundType
from ettem.storage import PairRepository, PlayerRepository


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
        bracket_size: Power of 2 (8, 16, 32, 64, etc.)

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
    elif bracket_size == 64:
        return RoundType.ROUND_OF_64
    elif bracket_size == 128:
        return RoundType.ROUND_OF_128
    else:
        # For larger brackets (256+), default to R128
        return RoundType.ROUND_OF_128


def get_bye_positions_for_bracket(num_qualifiers: int, bracket_size: int) -> set[int]:
    """Get the correct BYE positions for a bracket according to ITTF HTR 2021 Figure 3.1.

    BYE positions are placed in a specific order that:
    1. Gives priority to seeded entries (seeds get byes first)
    2. Distributes BYEs evenly throughout the draw
    3. Ensures BYEs never face each other

    The bye_order lists are from ITTF Handbook for Tournament Referees (HTR) 2021.
    """
    num_byes = bracket_size - num_qualifiers
    if num_byes <= 0:
        return set()

    bye_positions = set()

    if bracket_size == 8:
        # ITTF HTR 2021 - Draw of 8
        bye_order = [2, 7, 4, 5]
        for i in range(min(num_byes, len(bye_order))):
            bye_positions.add(bye_order[i])

    elif bracket_size == 16:
        # ITTF HTR 2021 - Draw of 16
        bye_order = [2, 15, 7, 10, 4, 13, 6, 11]
        for i in range(min(num_byes, len(bye_order))):
            bye_positions.add(bye_order[i])

    elif bracket_size == 32:
        # ITTF HTR 2021 - Draw of 32
        bye_order = [2, 31, 15, 18, 7, 26, 10, 23, 4, 29, 14, 19, 6, 27, 11, 22]
        for i in range(min(num_byes, len(bye_order))):
            bye_positions.add(bye_order[i])

    elif bracket_size == 64:
        # ITTF HTR 2021 - Draw of 64 (Figure 3.1)
        # Official ITTF bye placement order
        bye_order = [
            2, 63, 31, 34, 15, 50, 18, 47,   # Byes 1-8
            7, 58, 26, 39, 10, 55, 23, 42,   # Byes 9-16
            3, 62, 30, 35, 14, 51, 19, 46,   # Byes 17-24
            6, 59, 27, 38, 11, 54, 22, 43    # Byes 25-32
        ]
        for i in range(min(num_byes, len(bye_order))):
            bye_positions.add(bye_order[i])

    elif bracket_size == 128:
        # Extended from ITTF pattern for 128-draw
        # Following same distribution logic: spread across bracket, seeds get priority
        bye_order = [
            2, 127, 63, 66, 31, 98, 34, 95,    # Byes 1-8
            15, 114, 50, 79, 18, 111, 47, 82,  # Byes 9-16
            7, 122, 58, 71, 26, 103, 39, 90,   # Byes 17-24
            10, 119, 55, 74, 23, 106, 42, 87,  # Byes 25-32
            3, 126, 62, 67, 30, 99, 35, 94,    # Byes 33-40
            14, 115, 51, 78, 19, 110, 46, 83,  # Byes 41-48
            6, 123, 59, 70, 27, 102, 38, 91,   # Byes 49-56
            11, 118, 54, 75, 22, 107, 43, 86   # Byes 57-64
        ]
        for i in range(min(num_byes, len(bye_order))):
            bye_positions.add(bye_order[i])

    else:
        # Fallback for other sizes: distribute evenly
        all_even = [i for i in range(2, bracket_size + 1, 2)]
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


def get_seed_positions(bracket_size: int) -> list[int]:
    """Get ITTF standard seed positions for direct seeding.

    Returns a list of slot numbers in seed priority order:
    - Index 0 = seed #1 position, index 1 = seed #2 position, etc.

    Pattern ensures maximum separation of top seeds:
    - Seeds 1,2: top and bottom of draw
    - Seeds 3,4: midpoints of each half
    - Seeds 5-8: midpoints of each quarter
    - Seeds 9-16: midpoints of each eighth
    - etc.
    """
    if bracket_size <= 1:
        return [1]
    if bracket_size == 2:
        return [1, 2]

    positions = [1, bracket_size]

    # Seeds 3-4: midpoint of the draw
    half = bracket_size // 2
    positions.extend([half, half + 1])

    # Each subsequent level: midpoints of smaller segments
    divisor = 4
    while len(positions) < bracket_size:
        chunk = bracket_size // divisor
        for i in range(1, divisor, 2):  # odd multiples: 1, 3, 5, 7...
            pos = i * chunk
            positions.append(pos)
            positions.append(pos + 1)
        divisor *= 2

    return positions[:bracket_size]


def _adjust_seed_positions_for_byes(
    seed_positions: list[int],
    bye_positions: set[int],
    bracket_size: int,
) -> list[int]:
    """Adjust seed positions so seeds land on non-BYE slots.

    When a seed position falls on a BYE, redirect the seed to the
    BYE's match partner (the other slot in the same first-round match).
    This ensures top seeds get BYE advancement per ITTF rules.
    """
    result = []
    used = set()

    for pos in seed_positions:
        if pos in bye_positions:
            # Redirect to match partner
            partner = pos - 1 if pos % 2 == 0 else pos + 1
            if partner not in used and partner not in bye_positions:
                result.append(partner)
                used.add(partner)
            else:
                # Partner conflict, find next available
                for p in range(1, bracket_size + 1):
                    if p not in bye_positions and p not in used:
                        result.append(p)
                        used.add(p)
                        break
        elif pos not in used:
            result.append(pos)
            used.add(pos)
        else:
            # Position already used, find next available
            for p in range(1, bracket_size + 1):
                if p not in bye_positions and p not in used:
                    result.append(p)
                    used.add(p)
                    break

    return result


def build_bracket_direct(
    competitors: list[Union[Player, Pair]],
    category: str,
    random_seed: Optional[int] = None,
    player_repo: Optional[PlayerRepository] = None,
    event_type: str = "singles",
    pair_repo: Optional[PairRepository] = None,
    draw_mode: str = "seeded",
) -> Bracket:
    """Build knockout bracket directly from competitors (no group stage).

    Two draw modes:
    - "seeded": Competitors placed by ranking_pts with ITTF seed separation
    - "random": Fully random draw (lottery), all positions shuffled

    Args:
        competitors: List of Player or Pair objects
        category: Category name
        random_seed: Optional random seed for deterministic draws
        player_repo: Optional PlayerRepository for same-country checks
        event_type: 'singles' or 'doubles'
        pair_repo: Optional PairRepository (needed for doubles)
        draw_mode: 'seeded' (by ranking) or 'random' (lottery)

    Returns:
        Bracket object with slots filled
    """
    if not competitors:
        raise ValueError("Cannot build bracket with no competitors")

    if random_seed is not None:
        random.seed(random_seed)

    num_competitors = len(competitors)
    bracket_size = next_power_of_2(num_competitors)
    bye_positions = get_bye_positions_for_bracket(num_competitors, bracket_size)
    first_round = get_round_type_for_size(bracket_size)

    # Initialize bracket with BYEs
    bracket = Bracket(category=category)
    bracket.slots[first_round] = []
    for slot_num in range(1, bracket_size + 1):
        bracket.slots[first_round].append(BracketSlot(
            slot_number=slot_num,
            round_type=first_round,
            player_id=None,
            is_bye=slot_num in bye_positions,
        ))

    if draw_mode == "random":
        # Random draw: shuffle competitors, place in non-BYE slots sequentially
        shuffled = list(competitors)
        random.shuffle(shuffled)
        non_bye_slots = [s for s in bracket.slots[first_round] if not s.is_bye]
        for competitor, slot in zip(shuffled, non_bye_slots):
            slot.player_id = competitor.id
    else:
        # Seeded draw: sort by ranking_pts, place using ITTF seed positions
        sorted_competitors = sorted(competitors, key=lambda c: (-c.ranking_pts, c.id))

        raw_positions = get_seed_positions(bracket_size)
        adjusted_positions = _adjust_seed_positions_for_byes(
            raw_positions, bye_positions, bracket_size
        )

        # Shuffle within ITTF seeding tiers (seeds 1-2 fixed, 3-4 shuffled, etc.)
        tier_start = 2
        tier_size = 2
        while tier_start < len(adjusted_positions):
            tier_end = min(tier_start + tier_size, len(adjusted_positions))
            tier_slice = adjusted_positions[tier_start:tier_end]
            random.shuffle(tier_slice)
            adjusted_positions[tier_start:tier_end] = tier_slice
            tier_start = tier_end
            tier_size *= 2

        for i, competitor in enumerate(sorted_competitors):
            if i < len(adjusted_positions):
                pos = adjusted_positions[i]
                bracket.slots[first_round][pos - 1].player_id = competitor.id

    # Annotate same-country matches
    if player_repo:
        annotate_same_country_matches(
            bracket, first_round, player_repo,
            event_type=event_type, pair_repo=pair_repo,
        )

    # Create subsequent rounds (empty slots for winners to advance into)
    round_progression = {
        RoundType.ROUND_OF_128: RoundType.ROUND_OF_64,
        RoundType.ROUND_OF_64: RoundType.ROUND_OF_32,
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
            bracket.slots[next_round].append(BracketSlot(
                slot_number=slot_num,
                round_type=next_round,
                player_id=None,
                is_bye=False,
            ))
        current_round = next_round
        current_size = next_size

    return bracket


def build_bracket(
    qualifiers: list[tuple[Union[Player, Pair], GroupStanding]],
    category: str,
    random_seed: Optional[int] = None,
    player_repo: Optional[PlayerRepository] = None,
    event_type: str = "singles",
    pair_repo: Optional[PairRepository] = None,
) -> Bracket:
    """Build knockout bracket from group stage qualifiers.

    Works with both Player (singles) and Pair (doubles) qualifiers.

    Placement strategy:
    1. First, determine BYE positions (ensuring no BYE vs BYE matches)
    2. G1 (best 1st place): top slot (#1)
    3. G2 (second best 1st place): bottom slot (last)
    4. Other 1st place finishers: random draw in predefined slots
    5. 2nd place finishers: opposite half from their group's 1st place
    6. Annotate same-country 1st round matches (non-blocking)

    Args:
        qualifiers: List of (Player/Pair, GroupStanding) tuples
        category: Category name
        random_seed: Optional random seed for deterministic draws
        player_repo: Optional PlayerRepository for fetching player country codes
        event_type: 'singles' or 'doubles'
        pair_repo: Optional PairRepository (needed for doubles same-country check)

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
        annotate_same_country_matches(
            bracket, first_round, player_repo,
            event_type=event_type, pair_repo=pair_repo,
        )

    # Create subsequent rounds (empty slots for winners to advance into)
    # This is needed for process_bye_advancements to work
    round_progression = {
        RoundType.ROUND_OF_128: RoundType.ROUND_OF_64,
        RoundType.ROUND_OF_64: RoundType.ROUND_OF_32,
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
    bracket: Bracket,
    round_type: RoundType,
    player_repo: PlayerRepository,
    event_type: str = "singles",
    pair_repo: Optional[PairRepository] = None,
) -> None:
    """Mark 1st round matches with same-country competitors.

    This is a non-blocking annotation for organizers to review.
    For doubles, checks countries of all players in both pairs.

    Args:
        bracket: Bracket object to annotate
        round_type: The round type to check (typically first round)
        player_repo: PlayerRepository for fetching country codes
        event_type: 'singles' or 'doubles'
        pair_repo: PairRepository (needed for doubles)
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

        if event_type == "doubles" and pair_repo:
            # For doubles, get countries from pair members
            pair1 = pair_repo.get_by_id(slot1.player_id)
            pair2 = pair_repo.get_by_id(slot2.player_id)
            if pair1 and pair2:
                p1a = player_repo.get_by_id(pair1.player1_id)
                p1b = player_repo.get_by_id(pair1.player2_id)
                p2a = player_repo.get_by_id(pair2.player1_id)
                p2b = player_repo.get_by_id(pair2.player2_id)
                countries1 = {p.pais_cd for p in [p1a, p1b] if p}
                countries2 = {p.pais_cd for p in [p2a, p2b] if p}
                if countries1 & countries2:
                    slot1.same_country_warning = True
                    slot2.same_country_warning = True
        else:
            # Singles: direct player comparison
            player1 = player_repo.get_by_id(slot1.player_id)
            player2 = player_repo.get_by_id(slot2.player_id)
            if player1 and player2 and player1.pais_cd == player2.pais_cd:
                slot1.same_country_warning = True
                slot2.same_country_warning = True
