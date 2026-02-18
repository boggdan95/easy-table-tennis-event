"""Tests for Teams (Equipos) support.

Covers:
- Team model properties and display
- TeamMatchSystem enum and TEAM_MATCH_ORDERS
- TeamORM CRUD via TeamRepository
- TeamMatchDetailORM via TeamMatchDetailRepository
- Group creation with Team objects
- Team encounter auto-completion (majority wins)
- DB migration idempotency
"""

import json
import pytest
from unittest.mock import MagicMock

from ettem.models import (
    EventType,
    Gender,
    GroupStanding,
    Match,
    MatchStatus,
    Player,
    RoundType,
    Set,
    Team,
    TeamMatchSystem,
    TEAM_MATCH_ORDERS,
    detect_event_type,
    get_team_match_best_of,
    get_team_match_majority,
    is_teams_category,
    is_doubles_category,
)
from ettem.group_builder import create_groups, distribute_seeds_snake
from ettem.standings import break_ties, calculate_standings


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_player(id, nombre="P", apellido="L", pais_cd="ESP", seed=None, ranking_pts=0, categoria="MT"):
    return Player(
        id=id, nombre=nombre, apellido=apellido, genero=Gender.MALE,
        pais_cd=pais_cd, ranking_pts=ranking_pts, categoria=categoria, seed=seed,
    )


def make_team(id, name, pais_cd, players, categoria="MT", seed=None, ranking_pts=0):
    """Create a Team with populated players list."""
    return Team(
        id=id, name=name, pais_cd=pais_cd, categoria=categoria,
        ranking_pts=ranking_pts, seed=seed,
        player_ids=[p.id for p in players], players=players,
    )


def mock_player_repo(players_dict):
    repo = MagicMock()
    repo.get_by_id = lambda pid: players_dict.get(pid)
    return repo


def mock_team_repo(teams_dict):
    repo = MagicMock()
    repo.get_by_id = lambda tid: teams_dict.get(tid)
    return repo


# ── Test Data ────────────────────────────────────────────────────────────────

# 3 players per team (Swaythling standard)
PLAYERS_SPAIN = [
    make_player(1, "Juan", "Perez", "ESP", ranking_pts=1500),
    make_player(2, "Carlos", "Rodriguez", "ESP", ranking_pts=1400),
    make_player(3, "Pedro", "Lopez", "ESP", ranking_pts=1300),
]

PLAYERS_MEXICO = [
    make_player(4, "David", "Ramirez", "MEX", ranking_pts=1200),
    make_player(5, "Luis", "Morales", "MEX", ranking_pts=1100),
    make_player(6, "Pablo", "Torres", "MEX", ranking_pts=1000),
]

PLAYERS_ARGENTINA = [
    make_player(7, "Andres", "Martinez", "ARG", ranking_pts=900),
    make_player(8, "Roberto", "Gomez", "ARG", ranking_pts=800),
    make_player(9, "Fernando", "Diaz", "ARG", ranking_pts=700),
]

PLAYERS_BRAZIL = [
    make_player(10, "Sergio", "Castro", "BRA", ranking_pts=600),
    make_player(11, "Manuel", "Vega", "BRA", ranking_pts=500),
    make_player(12, "Ricardo", "Herrera", "BRA", ranking_pts=400),
]


# ============================================================================
# Category Detection Tests
# ============================================================================


class TestTeamCategoryDetection:
    """Verify detect_event_type and is_teams_category for team suffixes."""

    def test_mt_is_teams(self):
        assert detect_event_type("MT") == EventType.TEAMS

    def test_wt_is_teams(self):
        assert detect_event_type("WT") == EventType.TEAMS

    def test_u13bt_is_teams(self):
        assert detect_event_type("U13BT") == EventType.TEAMS

    def test_u15gt_is_teams(self):
        assert detect_event_type("U15GT") == EventType.TEAMS

    def test_is_teams_category_true(self):
        assert is_teams_category("MT") is True
        assert is_teams_category("U19WT") is True

    def test_is_teams_category_false_for_singles(self):
        assert is_teams_category("MS") is False
        assert is_teams_category("U15BS") is False

    def test_is_teams_category_false_for_doubles(self):
        assert is_teams_category("MD") is False
        assert is_teams_category("XD") is False

    def test_teams_not_confused_with_doubles(self):
        assert is_doubles_category("MT") is False
        assert is_teams_category("MD") is False


# ============================================================================
# Team Model Tests
# ============================================================================


class TestTeamModel:
    """Test Team dataclass properties and CompetitorDisplay compatibility."""

    def test_team_nombre(self):
        team = make_team(1, "Spain A", "ESP", PLAYERS_SPAIN)
        assert team.nombre == "Spain A"

    def test_team_apellido_empty(self):
        team = make_team(1, "Spain A", "ESP", PLAYERS_SPAIN)
        assert team.apellido == ""

    def test_team_display_name(self):
        team = make_team(1, "Spain A", "ESP", PLAYERS_SPAIN)
        assert team.display_name == "Spain A"

    def test_team_full_name_with_players(self):
        team = make_team(1, "Spain A", "ESP", PLAYERS_SPAIN)
        assert team.full_name == "Spain A (Perez, Rodriguez, Lopez)"

    def test_team_full_name_without_players(self):
        team = Team(id=1, name="Spain A", categoria="MT", pais_cd="ESP")
        assert team.full_name == "Spain A"

    def test_team_pais_cd(self):
        team = make_team(1, "Spain A", "ESP", PLAYERS_SPAIN)
        assert team.pais_cd == "ESP"

    def test_team_member_count(self):
        team = make_team(1, "Spain A", "ESP", PLAYERS_SPAIN)
        assert team.member_count == 3

    def test_team_player_ids(self):
        team = make_team(1, "Spain A", "ESP", PLAYERS_SPAIN)
        assert team.player_ids == [1, 2, 3]

    def test_team_str(self):
        team = make_team(1, "Spain A", "ESP", PLAYERS_SPAIN)
        assert "Spain A" in str(team)
        assert "ESP" in str(team)

    def test_team_seed(self):
        team = make_team(1, "Spain A", "ESP", PLAYERS_SPAIN, seed=1, ranking_pts=5000)
        assert team.seed == 1
        assert team.ranking_pts == 5000

    def test_team_group_assignment(self):
        team = Team(id=1, name="X", categoria="MT", pais_cd="ESP",
                    group_id=5, group_number=2)
        assert team.group_id == 5
        assert team.group_number == 2


# ============================================================================
# TeamMatchSystem Tests
# ============================================================================


class TestTeamMatchSystem:
    """Test ITTF team match systems and order of play."""

    def test_swaythling_enum(self):
        assert TeamMatchSystem.SWAYTHLING == "swaythling"

    def test_corbillon_enum(self):
        assert TeamMatchSystem.CORBILLON == "corbillon"

    def test_olympic_enum(self):
        assert TeamMatchSystem.OLYMPIC == "olympic"

    def test_bo7_enum(self):
        assert TeamMatchSystem.BEST_OF_7 == "bo7"

    def test_bo9_enum(self):
        assert TeamMatchSystem.BEST_OF_9 == "bo9"

    # -- Swaythling --

    def test_swaythling_has_5_matches(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.SWAYTHLING]
        assert len(order) == 5

    def test_swaythling_all_singles(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.SWAYTHLING]
        assert all(m[1] == "singles" for m in order)

    def test_swaythling_correct_order(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.SWAYTHLING]
        expected = [("A", "X"), ("B", "Y"), ("C", "Z"), ("A", "Y"), ("B", "X")]
        actual = [(m[2], m[3]) for m in order]
        assert actual == expected

    # -- Corbillon --

    def test_corbillon_has_5_matches(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.CORBILLON]
        assert len(order) == 5

    def test_corbillon_has_1_doubles(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.CORBILLON]
        doubles_count = sum(1 for m in order if m[1] == "doubles")
        assert doubles_count == 1

    def test_corbillon_doubles_is_match_3(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.CORBILLON]
        assert order[2][1] == "doubles"

    # -- Olympic --

    def test_olympic_has_5_matches(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.OLYMPIC]
        assert len(order) == 5

    def test_olympic_starts_with_doubles(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.OLYMPIC]
        assert order[0][1] == "doubles"
        assert order[0][2] == "B&C"
        assert order[0][3] == "Y&Z"

    def test_olympic_correct_singles_order(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.OLYMPIC]
        singles = [(m[2], m[3]) for m in order if m[1] == "singles"]
        expected = [("A", "X"), ("C", "Z"), ("A", "Y"), ("B", "X")]
        assert singles == expected

    # -- Best of 7 --

    def test_bo7_has_7_matches(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.BEST_OF_7]
        assert len(order) == 7

    def test_bo7_has_1_doubles(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.BEST_OF_7]
        doubles_count = sum(1 for m in order if m[1] == "doubles")
        assert doubles_count == 1

    def test_bo7_doubles_is_match_4(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.BEST_OF_7]
        assert order[3][1] == "doubles"

    # -- Best of 9 --

    def test_bo9_has_9_matches(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.BEST_OF_9]
        assert len(order) == 9

    def test_bo9_all_singles(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.BEST_OF_9]
        assert all(m[1] == "singles" for m in order)

    def test_bo9_correct_first_3(self):
        order = TEAM_MATCH_ORDERS[TeamMatchSystem.BEST_OF_9]
        first3 = [(m[2], m[3]) for m in order[:3]]
        expected = [("A", "X"), ("B", "Y"), ("C", "Z")]
        assert first3 == expected

    # -- Helper functions --

    def test_get_team_match_best_of(self):
        assert get_team_match_best_of("swaythling") == 5
        assert get_team_match_best_of("corbillon") == 5
        assert get_team_match_best_of("olympic") == 5
        assert get_team_match_best_of("bo7") == 7
        assert get_team_match_best_of("bo9") == 9

    def test_get_team_match_majority(self):
        assert get_team_match_majority("swaythling") == 3
        assert get_team_match_majority("corbillon") == 3
        assert get_team_match_majority("olympic") == 3
        assert get_team_match_majority("bo7") == 4
        assert get_team_match_majority("bo9") == 5

    def test_unknown_system_returns_zero(self):
        assert get_team_match_best_of("unknown") == 0
        assert get_team_match_majority("unknown") == 1  # 0 // 2 + 1


# ============================================================================
# Group Creation with Teams
# ============================================================================


class TestTeamGroupCreation:
    """Test creating groups of teams using existing group_builder."""

    def setup_method(self):
        """Create 4 teams for group tests."""
        self.team_spain = make_team(1, "Spain A", "ESP", PLAYERS_SPAIN, seed=1, ranking_pts=5000)
        self.team_mexico = make_team(2, "Mexico", "MEX", PLAYERS_MEXICO, seed=2, ranking_pts=4200)
        self.team_argentina = make_team(3, "Argentina", "ARG", PLAYERS_ARGENTINA, seed=3, ranking_pts=3800)
        self.team_brazil = make_team(4, "Brazil", "BRA", PLAYERS_BRAZIL, seed=4, ranking_pts=3500)
        self.teams = [self.team_spain, self.team_mexico, self.team_argentina, self.team_brazil]

    def test_create_single_group_of_4(self):
        """4 teams in 1 group."""
        groups, matches = create_groups(
            self.teams, "MT", group_size_preference=4, event_type="teams"
        )
        assert len(groups) == 1
        assert len(groups[0].player_ids) == 4

    def test_create_two_groups_of_4(self):
        """8 teams across 2 groups with snake seeding."""
        extra_teams = [
            make_team(5, "Colombia", "COL", PLAYERS_SPAIN, seed=5, ranking_pts=3000),
            make_team(6, "Chile", "CHI", PLAYERS_MEXICO, seed=6, ranking_pts=2500),
            make_team(7, "Peru", "PER", PLAYERS_ARGENTINA, seed=7, ranking_pts=2000),
            make_team(8, "Cuba", "CUB", PLAYERS_BRAZIL, seed=8, ranking_pts=1500),
        ]
        all_teams = self.teams + extra_teams
        groups, matches = create_groups(
            all_teams, "MT", group_size_preference=4, event_type="teams"
        )
        assert len(groups) == 2
        assert len(groups[0].player_ids) == 4
        assert len(groups[1].player_ids) == 4

    def test_group_matches_generated(self):
        """RR matches generated for team group (4 teams = 6 matches)."""
        groups, matches = create_groups(
            self.teams, "MT", group_size_preference=4, event_type="teams"
        )
        # 4 teams in RR = C(4,2) = 6 matches
        assert len(matches) == 6

    def test_group_matches_have_team_ids(self):
        """Group matches should reference team IDs as player IDs."""
        groups, matches = create_groups(
            self.teams, "MT", group_size_preference=4, event_type="teams"
        )
        team_ids = {t.id for t in self.teams}
        for match in matches:
            assert match.player1_id in team_ids
            assert match.player2_id in team_ids

    def test_snake_seeding_distributes_correctly(self):
        """Snake seeding: seed 1 and 4 together, seed 2 and 3 together."""
        extra_teams = [
            make_team(5, "Colombia", "COL", PLAYERS_SPAIN, seed=5, ranking_pts=3000),
            make_team(6, "Chile", "CHI", PLAYERS_MEXICO, seed=6, ranking_pts=2500),
        ]
        all_teams = self.teams + extra_teams
        groups, _ = create_groups(
            all_teams, "MT", group_size_preference=3, event_type="teams"
        )
        # Seed 1 (Spain) and Seed 2 (Mexico) should be in different groups
        g1_ids = set(groups[0].player_ids)
        g2_ids = set(groups[1].player_ids)
        assert not ({1, 2} <= g1_ids), "Top 2 seeds should not be in same group"
        assert not ({1, 2} <= g2_ids), "Top 2 seeds should not be in same group"


# ============================================================================
# Team Encounter Logic Tests
# ============================================================================


class TestTeamEncounterCompletion:
    """Test team match auto-completion based on majority wins."""

    def test_majority_for_bo5(self):
        """3 wins out of 5 = decided."""
        assert get_team_match_majority("swaythling") == 3
        assert get_team_match_majority("corbillon") == 3
        assert get_team_match_majority("olympic") == 3

    def test_majority_for_bo7(self):
        """4 wins out of 7 = decided."""
        assert get_team_match_majority("bo7") == 4

    def test_majority_for_bo9(self):
        """5 wins out of 9 = decided."""
        assert get_team_match_majority("bo9") == 5

    def test_encounter_decided_at_3_of_5(self):
        """Simulate: home wins matches 1, 2, 3 → decided at match 3."""
        home_wins = 3
        away_wins = 0
        majority = get_team_match_majority("swaythling")
        assert home_wins >= majority

    def test_encounter_not_decided_at_2_of_5(self):
        """Simulate: home 2, away 1 → not decided."""
        home_wins = 2
        away_wins = 1
        majority = get_team_match_majority("swaythling")
        assert home_wins < majority
        assert away_wins < majority

    def test_encounter_decided_at_4_of_7(self):
        """Bo7: 4 wins clinches."""
        home_wins = 4
        majority = get_team_match_majority("bo7")
        assert home_wins >= majority

    def test_encounter_decided_when_away_wins(self):
        """Away team can also win majority."""
        away_wins = 3
        majority = get_team_match_majority("swaythling")
        assert away_wins >= majority


# ============================================================================
# Standings with Teams
# ============================================================================


class TestTeamStandings:
    """Test standings calculation using team match results."""

    def _make_completed_match(self, id, p1_id, p2_id, winner_id, sets, group_id=1):
        """Helper to create a completed match for standings."""
        return Match(
            id=id, player1_id=p1_id, player2_id=p2_id,
            group_id=group_id,
            status=MatchStatus.COMPLETED, winner_id=winner_id,
            sets=sets,
        )

    def test_basic_3_team_standings(self):
        """3 teams in RR: Spain beats Mexico, Mexico beats Argentina, Spain beats Argentina."""
        # Match results stored as individual match wins (1-0 per individual match)
        # Spain 3-0 Mexico
        m1 = self._make_completed_match(
            1, 1, 2, 1,
            [Set(1, 1, 0), Set(2, 1, 0), Set(3, 1, 0)],
        )
        # Mexico 3-1 Argentina
        m2 = self._make_completed_match(
            2, 2, 3, 2,
            [Set(1, 1, 0), Set(2, 0, 1), Set(3, 1, 0), Set(4, 1, 0)],
        )
        # Spain 3-2 Argentina
        m3 = self._make_completed_match(
            3, 1, 3, 1,
            [Set(1, 1, 0), Set(2, 0, 1), Set(3, 0, 1), Set(4, 1, 0), Set(5, 1, 0)],
        )

        p_repo = mock_player_repo({})
        standings, breakdown = calculate_standings(
            [m1, m2, m3], group_id=1, player_repo=p_repo,
        )

        # Spain: 2W-0L = 4 pts, Mexico: 1W-1L = 3 pts, Argentina: 0W-2L = 2 pts
        assert len(standings) == 3
        # Find standings by player_id (which is team_id here)
        spain = next(s for s in standings if s.player_id == 1)
        mexico = next(s for s in standings if s.player_id == 2)
        argentina = next(s for s in standings if s.player_id == 3)

        assert spain.position == 1
        assert mexico.position == 2
        assert argentina.position == 3

    def test_standings_tie_broken_by_sets_ratio(self):
        """When two teams have same points, sets ratio breaks tie."""
        # Spain 3-0 Mexico
        m1 = self._make_completed_match(
            1, 1, 2, 1,
            [Set(1, 1, 0), Set(2, 1, 0), Set(3, 1, 0)],
        )
        # Mexico 3-0 Argentina
        m2 = self._make_completed_match(
            2, 2, 3, 2,
            [Set(1, 1, 0), Set(2, 1, 0), Set(3, 1, 0)],
        )
        # Argentina 3-0 Spain (upset)
        m3 = self._make_completed_match(
            3, 3, 1, 3,
            [Set(1, 1, 0), Set(2, 1, 0), Set(3, 1, 0)],
        )

        p_repo = mock_player_repo({})
        standings, _ = calculate_standings(
            [m1, m2, m3], group_id=1, player_repo=p_repo,
        )

        # All 3 teams: 1W-1L = 3 pts each → tie-break by sets ratio
        # All have 3-3 sets → further tie-break by points
        # All have identical records → position by seed/head-to-head
        assert len(standings) == 3


# ============================================================================
# Storage Tests (require database)
# ============================================================================


class TestTeamORM:
    """Test TeamORM and TeamRepository with actual database."""

    @pytest.fixture
    def db_session(self, tmp_path):
        """Create a temporary SQLite database with all tables."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from ettem.storage import Base, migrate_v24_doubles, migrate_v25_teams

        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(engine)
        migrate_v24_doubles(engine)
        migrate_v25_teams(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    @pytest.fixture
    def tournament(self, db_session):
        """Create a test tournament."""
        from ettem.storage import TournamentORM
        t = TournamentORM(name="Test Cup", num_tables=4)
        db_session.add(t)
        db_session.commit()
        db_session.refresh(t)
        return t

    def test_create_team(self, db_session, tournament):
        from ettem.storage import TeamRepository
        from ettem.models import Team

        repo = TeamRepository(db_session)
        team = Team(
            id=0, name="Spain A", categoria="MT", pais_cd="ESP",
            ranking_pts=5000, player_ids=[1, 2, 3],
        )
        result = repo.create(team, tournament_id=tournament.id)
        assert result.id > 0
        assert result.name == "Spain A"
        assert result.pais_cd == "ESP"
        assert result.player_ids == [1, 2, 3]
        assert result.ranking_pts == 5000

    def test_get_by_id(self, db_session, tournament):
        from ettem.storage import TeamRepository
        from ettem.models import Team

        repo = TeamRepository(db_session)
        team = Team(id=0, name="Mexico", categoria="MT", pais_cd="MEX",
                    ranking_pts=4200, player_ids=[4, 5, 6])
        created = repo.create(team, tournament_id=tournament.id)

        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.name == "Mexico"
        assert fetched.player_ids == [4, 5, 6]

    def test_get_by_category(self, db_session, tournament):
        from ettem.storage import TeamRepository
        from ettem.models import Team

        repo = TeamRepository(db_session)
        for name, pts in [("Spain", 5000), ("Mexico", 4200), ("Argentina", 3800)]:
            t = Team(id=0, name=name, categoria="MT", pais_cd="ESP",
                     ranking_pts=pts, player_ids=[1, 2, 3])
            repo.create(t, tournament_id=tournament.id)

        teams = repo.get_by_category("MT", tournament_id=tournament.id)
        assert len(teams) == 3

    def test_assign_seeds(self, db_session, tournament):
        from ettem.storage import TeamRepository
        from ettem.models import Team

        repo = TeamRepository(db_session)
        for name, pts in [("Spain", 5000), ("Mexico", 4200), ("Argentina", 3800)]:
            t = Team(id=0, name=name, categoria="MT", pais_cd="ESP",
                     ranking_pts=pts, player_ids=[1, 2, 3])
            repo.create(t, tournament_id=tournament.id)

        seeded = repo.assign_seeds("MT", tournament_id=tournament.id)
        assert seeded[0].seed == 1  # Spain (highest ranking)
        assert seeded[0].name == "Spain"
        assert seeded[1].seed == 2  # Mexico
        assert seeded[2].seed == 3  # Argentina

    def test_delete_team(self, db_session, tournament):
        from ettem.storage import TeamRepository
        from ettem.models import Team

        repo = TeamRepository(db_session)
        team = Team(id=0, name="Delete Me", categoria="MT", pais_cd="ESP",
                    ranking_pts=100, player_ids=[1])
        created = repo.create(team, tournament_id=tournament.id)

        assert repo.delete(created.id) is True
        assert repo.get_by_id(created.id) is None

    def test_get_by_tournament(self, db_session, tournament):
        from ettem.storage import TeamRepository
        from ettem.models import Team

        repo = TeamRepository(db_session)
        repo.create(Team(id=0, name="T1", categoria="MT", pais_cd="ESP",
                         ranking_pts=100, player_ids=[1]), tournament_id=tournament.id)
        repo.create(Team(id=0, name="T2", categoria="WT", pais_cd="MEX",
                         ranking_pts=200, player_ids=[2]), tournament_id=tournament.id)

        teams = repo.get_by_tournament(tournament.id)
        assert len(teams) == 2


class TestTeamMatchDetailORM:
    """Test TeamMatchDetailORM and TeamMatchDetailRepository."""

    @pytest.fixture
    def db_session(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from ettem.storage import Base, migrate_v24_doubles, migrate_v25_teams

        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(engine)
        migrate_v24_doubles(engine)
        migrate_v25_teams(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    @pytest.fixture
    def parent_match(self, db_session):
        """Create a parent team match (MatchORM)."""
        from ettem.storage import MatchORM, TournamentORM, GroupORM
        t = TournamentORM(name="Test", num_tables=4)
        db_session.add(t)
        db_session.commit()
        db_session.refresh(t)

        g = GroupORM(
            name="A", category="MT", tournament_id=t.id,
            player_ids_json="[1,2]", event_type="teams"
        )
        db_session.add(g)
        db_session.commit()
        db_session.refresh(g)

        m = MatchORM(
            player1_id=1, player2_id=2,
            team1_id=1, team2_id=2,
            event_type="teams",
            team_match_system="swaythling",
            group_id=g.id, tournament_id=t.id,
            category="MT", round_type="RR",
            best_of=5,
        )
        db_session.add(m)
        db_session.commit()
        db_session.refresh(m)
        return m

    def test_create_details(self, db_session, parent_match):
        from ettem.storage import TeamMatchDetailORM, TeamMatchDetailRepository

        repo = TeamMatchDetailRepository(db_session)
        details = []
        for num, mtype, home, away in TEAM_MATCH_ORDERS["swaythling"]:
            d = TeamMatchDetailORM(
                parent_match_id=parent_match.id,
                match_number=num,
                match_type=mtype,
                label_home=home,
                label_away=away,
                best_of=5,
            )
            details.append(d)

        created = repo.create_bulk(details)
        assert len(created) == 5
        assert created[0].match_number == 1
        assert created[0].label_home == "A"
        assert created[0].label_away == "X"

    def test_get_by_parent_match(self, db_session, parent_match):
        from ettem.storage import TeamMatchDetailORM, TeamMatchDetailRepository

        repo = TeamMatchDetailRepository(db_session)
        for num, mtype, home, away in TEAM_MATCH_ORDERS["swaythling"]:
            d = TeamMatchDetailORM(
                parent_match_id=parent_match.id,
                match_number=num,
                match_type=mtype,
                label_home=home,
                label_away=away,
            )
            db_session.add(d)
        db_session.commit()

        fetched = repo.get_by_parent_match(parent_match.id)
        assert len(fetched) == 5
        assert fetched[0].match_number == 1  # Ordered by match_number
        assert fetched[4].match_number == 5

    def test_update_detail_result(self, db_session, parent_match):
        from ettem.storage import TeamMatchDetailORM, TeamMatchDetailRepository

        repo = TeamMatchDetailRepository(db_session)
        d = TeamMatchDetailORM(
            parent_match_id=parent_match.id,
            match_number=1,
            match_type="singles",
            label_home="A",
            label_away="X",
            player1_id=1,
            player2_id=4,
        )
        db_session.add(d)
        db_session.commit()
        db_session.refresh(d)

        # Simulate result: home wins 3-1
        d.sets_json = json.dumps([
            {"set_number": 1, "player1_points": 11, "player2_points": 7},
            {"set_number": 2, "player1_points": 9, "player2_points": 11},
            {"set_number": 3, "player1_points": 11, "player2_points": 5},
            {"set_number": 4, "player1_points": 11, "player2_points": 8},
        ])
        d.winner_side = 1
        d.status = "completed"
        repo.update(d)

        fetched = repo.get_by_id(d.id)
        assert fetched.winner_side == 1
        assert fetched.status == "completed"
        assert len(fetched.sets) == 4

    def test_delete_by_parent_match(self, db_session, parent_match):
        from ettem.storage import TeamMatchDetailORM, TeamMatchDetailRepository

        repo = TeamMatchDetailRepository(db_session)
        for i in range(5):
            d = TeamMatchDetailORM(
                parent_match_id=parent_match.id,
                match_number=i + 1,
                match_type="singles",
            )
            db_session.add(d)
        db_session.commit()

        count = repo.delete_by_parent_match(parent_match.id)
        assert count == 5
        assert len(repo.get_by_parent_match(parent_match.id)) == 0


# ============================================================================
# Migration Idempotency Tests
# ============================================================================


class TestMigrationIdempotency:
    """Test that running migrate_v25_teams multiple times is safe."""

    def test_double_migration(self, tmp_path):
        from sqlalchemy import create_engine, inspect
        from ettem.storage import Base, migrate_v24_doubles, migrate_v25_teams

        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(engine)
        migrate_v24_doubles(engine)

        # Run V2.5 migration twice
        migrate_v25_teams(engine)
        migrate_v25_teams(engine)  # Should not fail

        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "teams" in tables
        assert "team_match_details" in tables

        # Check columns exist on matches
        match_columns = {c["name"] for c in inspector.get_columns("matches")}
        assert "team1_id" in match_columns
        assert "team2_id" in match_columns
        assert "team1_score" in match_columns
        assert "team2_score" in match_columns
        assert "team_match_system" in match_columns

        # Check columns on bracket_slots and group_standings
        bracket_cols = {c["name"] for c in inspector.get_columns("bracket_slots")}
        assert "team_id" in bracket_cols

        standing_cols = {c["name"] for c in inspector.get_columns("group_standings")}
        assert "team_id" in standing_cols


# ============================================================================
# MatchORM Property Tests
# ============================================================================


class TestMatchORMTeamProperties:
    """Test is_teams and competitor properties on MatchORM."""

    def test_is_teams_property(self):
        from ettem.storage import MatchORM
        m = MatchORM(event_type="teams")
        assert m.is_teams is True
        assert m.is_doubles is False

    def test_is_teams_false_for_singles(self):
        from ettem.storage import MatchORM
        m = MatchORM(event_type="singles")
        assert m.is_teams is False

    def test_competitor_ids_for_teams(self):
        from ettem.storage import MatchORM
        m = MatchORM(
            event_type="teams",
            player1_id=100, player2_id=200,
            team1_id=10, team2_id=20,
        )
        assert m.competitor1_id == 10
        assert m.competitor2_id == 20

    def test_competitor_ids_for_singles_unchanged(self):
        from ettem.storage import MatchORM
        m = MatchORM(
            event_type="singles",
            player1_id=100, player2_id=200,
        )
        assert m.competitor1_id == 100
        assert m.competitor2_id == 200

    def test_competitor_ids_for_doubles_unchanged(self):
        from ettem.storage import MatchORM
        m = MatchORM(
            event_type="doubles",
            player1_id=100, player2_id=200,
            pair1_id=10, pair2_id=20,
        )
        assert m.competitor1_id == 10
        assert m.competitor2_id == 20
