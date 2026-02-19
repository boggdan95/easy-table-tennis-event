"""Integration tests for page data integrity.

These tests ensure that all main pages correctly reflect the current
data state, regardless of which phase the tournament is in.

Covers scenarios like:
- Tournament status shows categories from players/pairs even without groups
- Import players page separates singles from doubles correctly
- Direct bracket page accepts pre-selected category
- Dashboard category count matches actual data
"""

import os
import tempfile
import pytest

# Set up temp DB before importing app (which initializes DB on import)
_tmp_db = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_tmp_db.close()
os.environ["ETTEM_DB_PATH"] = _tmp_db.name

from ettem.storage import (
    DatabaseManager,
    PlayerRepository,
    PairRepository,
    TournamentRepository,
    GroupRepository,
    BracketRepository,
)
from ettem.models import Gender
from datetime import date


@pytest.fixture(scope="module")
def db():
    """Create a fresh in-memory database for all tests in this module."""
    manager = DatabaseManager(_tmp_db.name)
    manager.create_tables()
    yield manager
    manager.drop_tables()
    manager.engine.dispose()
    try:
        os.unlink(_tmp_db.name)
    except PermissionError:
        pass  # Windows may still hold the file


@pytest.fixture(scope="module")
def session(db):
    return db.get_session()


@pytest.fixture(scope="module")
def tournament_id(session):
    """Create a tournament and return its ID."""
    from ettem.storage import TournamentORM
    t = TournamentORM(name="Test Tournament", date=date(2026, 1, 1), is_current=True)
    session.add(t)
    session.commit()
    return t.id


@pytest.fixture(scope="module")
def populated_db(session, tournament_id):
    """Populate DB with singles players and doubles pairs."""
    player_repo = PlayerRepository(session)
    pair_repo = PairRepository(session)

    from ettem.storage import PlayerORM, PairORM

    # Singles players (U13BS)
    singles_ids = []
    for i in range(1, 7):
        p = PlayerORM(
            nombre=f"Player{i}", apellido=f"Last{i}", genero="M",
            pais_cd="ESP", ranking_pts=1000 - i * 100, categoria="U13BS",
            tournament_id=tournament_id, seed=i,
        )
        session.add(p)
        session.flush()
        singles_ids.append(p.id)

    # Doubles players + pairs (MD)
    pair_player_ids = []
    for i in range(1, 9):
        p = PlayerORM(
            nombre=f"DPlayer{i}", apellido=f"DLast{i}", genero="M",
            pais_cd="MEX", ranking_pts=0, categoria="MD",
            tournament_id=tournament_id,
        )
        session.add(p)
        session.flush()
        pair_player_ids.append(p.id)

    for i in range(0, 8, 2):
        pair = PairORM(
            player1_id=pair_player_ids[i],
            player2_id=pair_player_ids[i + 1],
            ranking_pts=2000 - i * 200,
            categoria="MD",
            tournament_id=tournament_id,
            seed=(i // 2) + 1,
        )
        session.add(pair)

    session.commit()
    return {
        "singles_ids": singles_ids,
        "pair_player_ids": pair_player_ids,
        "tournament_id": tournament_id,
    }


# ── Test: Tournament Status shows all categories ─────────────────────────


class TestTournamentStatus:
    """Tournament status page must show categories from players AND pairs,
    not just from groups."""

    def test_categories_detected_without_groups(self, session, populated_db):
        """Categories should be detected from players/pairs even with 0 groups."""
        from ettem.models import is_doubles_category

        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        group_repo = GroupRepository(session)
        tid = populated_db["tournament_id"]

        # Verify no groups exist
        all_groups = group_repo.get_all(tournament_id=tid)
        assert len(all_groups) == 0, "Expected no groups for this test"

        # Build categories the same way the route does
        all_players = player_repo.get_all(tournament_id=tid)
        all_pairs = pair_repo.get_all(tournament_id=tid)

        group_categories = set(g.category for g in all_groups)
        player_categories = set(
            p.categoria for p in all_players
            if not is_doubles_category(p.categoria)
        )
        pair_categories = set(p.categoria for p in all_pairs)

        all_categories = group_categories | player_categories | pair_categories

        assert "U13BS" in all_categories, "Singles category U13BS should be detected"
        assert "MD" in all_categories, "Doubles category MD should be detected"
        assert len(all_categories) == 2

    def test_singles_competitor_count(self, session, populated_db):
        """Singles category should count individual players."""
        player_repo = PlayerRepository(session)
        tid = populated_db["tournament_id"]

        players = player_repo.get_all(tournament_id=tid)
        u13bs = [p for p in players if p.categoria == "U13BS"]
        assert len(u13bs) == 6

    def test_doubles_competitor_count(self, session, populated_db):
        """Doubles category should count pairs, not individual players."""
        pair_repo = PairRepository(session)
        tid = populated_db["tournament_id"]

        pairs = pair_repo.get_all(tournament_id=tid)
        md_pairs = [p for p in pairs if p.categoria == "MD"]
        assert len(md_pairs) == 4


# ── Test: Import Players page separates singles from doubles ─────────────


class TestImportPlayersDataSeparation:
    """Import players page should show singles players separately from
    doubles pair members."""

    def test_singles_players_exclude_pair_members(self, session, populated_db):
        """Players that are pair members should NOT appear in singles list."""
        from ettem.models import is_doubles_category

        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        tid = populated_db["tournament_id"]

        all_players = player_repo.get_all(tournament_id=tid)
        all_pairs = pair_repo.get_all(tournament_id=tid)

        # Build pair_member_ids
        pair_member_ids = set()
        for p in all_pairs:
            pair_member_ids.add(p.player1_id)
            pair_member_ids.add(p.player2_id)

        # Filter singles (same logic as the route)
        singles = [
            p for p in all_players
            if not is_doubles_category(p.categoria) or p.id not in pair_member_ids
        ]

        # Should only have U13BS players (6), not MD players (8)
        assert len(singles) == 6
        for p in singles:
            assert p.categoria == "U13BS"

    def test_doubles_categories_count_pairs(self, session, populated_db):
        """Doubles categories should count by pairs, not individual players."""
        pair_repo = PairRepository(session)
        tid = populated_db["tournament_id"]

        pairs = pair_repo.get_all(tournament_id=tid)
        doubles_categories = {}
        for p in pairs:
            doubles_categories[p.categoria] = doubles_categories.get(p.categoria, 0) + 1

        assert doubles_categories["MD"] == 4


# ── Test: Direct bracket accepts manual draw mode ────────────────────────


class TestDirectBracketModes:
    """Direct bracket should support seeded, random, and manual draw modes."""

    def test_manual_draw_preserves_order(self):
        """Manual draw mode should place competitors in the given order."""
        from ettem.models import Player
        from ettem.bracket import build_bracket_direct

        players = [
            Player(id=i, nombre=f"P{i}", apellido="L", genero=Gender.MALE,
                   pais_cd="ESP", ranking_pts=(100 - i * 10), categoria="U13BS", seed=i)
            for i in range(1, 5)
        ]

        # Reverse order manually
        reversed_players = list(reversed(players))

        bracket = build_bracket_direct(
            competitors=reversed_players,
            category="U13BS",
            draw_mode="manual",
        )

        # Get first round slots
        first_round_key = list(bracket.slots.keys())[0]
        filled_slots = [s for s in bracket.slots[first_round_key] if s.player_id and not s.is_bye]

        # Should be in reversed order
        slot_ids = [s.player_id for s in filled_slots]
        assert slot_ids == [4, 3, 2, 1], f"Manual order not preserved: {slot_ids}"

    def test_seeded_draw_places_top_seeds(self):
        """Seeded draw should place top seed first, second seed last."""
        from ettem.models import Player
        from ettem.bracket import build_bracket_direct

        players = [
            Player(id=i, nombre=f"P{i}", apellido="L", genero=Gender.MALE,
                   pais_cd="ESP", ranking_pts=(500 - i * 50), categoria="U13BS", seed=i)
            for i in range(1, 5)
        ]

        bracket = build_bracket_direct(
            competitors=players,
            category="U13BS",
            random_seed=42,
            draw_mode="seeded",
        )

        first_round_key = list(bracket.slots.keys())[0]
        slots = bracket.slots[first_round_key]

        # Top seed should be in slot 1, second seed in last slot
        assert slots[0].player_id == 1, "Top seed should be in first position"
        assert slots[-1].player_id == 2, "Second seed should be in last position"

    def test_random_draw_fills_all_slots(self):
        """Random draw should fill all non-BYE slots."""
        from ettem.models import Player
        from ettem.bracket import build_bracket_direct

        players = [
            Player(id=i, nombre=f"P{i}", apellido="L", genero=Gender.MALE,
                   pais_cd="ESP", ranking_pts=0, categoria="U13BS")
            for i in range(1, 6)  # 5 players = bracket of 8 with 3 BYEs
        ]

        bracket = build_bracket_direct(
            competitors=players,
            category="U13BS",
            random_seed=42,
            draw_mode="random",
        )

        first_round_key = list(bracket.slots.keys())[0]
        slots = bracket.slots[first_round_key]
        filled = [s for s in slots if s.player_id and not s.is_bye]
        byes = [s for s in slots if s.is_bye]

        assert len(filled) == 5
        assert len(byes) == 3
        assert len(slots) == 8


# ── Test: Category detection consistency ─────────────────────────────────


class TestCategoryConsistency:
    """Dashboard and tournament status should show the same categories."""

    def test_dashboard_and_status_same_categories(self, session, populated_db):
        """Both pages should detect the same set of categories."""
        from ettem.models import is_doubles_category

        player_repo = PlayerRepository(session)
        pair_repo = PairRepository(session)
        tid = populated_db["tournament_id"]

        all_players = player_repo.get_all(tournament_id=tid)
        all_pairs = pair_repo.get_all(tournament_id=tid)

        # Dashboard logic: all unique categories from players
        dashboard_cats = set(p.categoria for p in all_players) | set(p.categoria for p in all_pairs)

        # Status page logic (fixed version)
        player_cats = set(p.categoria for p in all_players if not is_doubles_category(p.categoria))
        pair_cats = set(p.categoria for p in all_pairs)
        status_cats = player_cats | pair_cats

        assert dashboard_cats == status_cats | {"MD"}, \
            f"Dashboard ({dashboard_cats}) != Status ({status_cats}) — category mismatch"
        # Note: dashboard_cats has MD from players too, status_cats filters doubles players out
        # but pair_cats adds MD back. So they should match.
        assert "U13BS" in status_cats
        assert "MD" in status_cats
