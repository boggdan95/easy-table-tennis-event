"""Tests for CSV export functionality."""

import csv
from pathlib import Path
import tempfile

import pytest

from ettem.models import Gender, Player, Group, GroupStanding, Bracket, BracketSlot, RoundType
from ettem.io_csv import export_groups_csv, export_standings_csv, export_bracket_csv


class TestExportCSV:
    """Test CSV export functions."""

    def setup_method(self):
        """Set up test data."""
        # Create sample players
        self.players = [
            Player(
                id=1,
                nombre="Juan",
                apellido="Perez",
                genero=Gender.MALE,
                pais_cd="ESP",
                ranking_pts=1200,
                categoria="U13",
                seed=1,
                group_number=1,
                original_id=101,
            ),
            Player(
                id=2,
                nombre="Maria",
                apellido="Garcia",
                genero=Gender.FEMALE,
                pais_cd="MEX",
                ranking_pts=1150,
                categoria="U13",
                seed=2,
                group_number=2,
                original_id=102,
            ),
            Player(
                id=3,
                nombre="Carlos",
                apellido="Lopez",
                genero=Gender.MALE,
                pais_cd="ARG",
                ranking_pts=1100,
                categoria="U13",
                seed=3,
                group_number=1,
                original_id=103,
            ),
        ]
        self.players_by_id = {p.id: p for p in self.players}

    def test_export_groups_csv(self):
        """Test exporting groups to CSV."""
        # Create mock group with player_ids
        class MockGroup:
            def __init__(self, id, name, player_ids, category):
                self.id = id
                self.name = name
                self.player_ids = player_ids
                self.category = category

        groups = [
            MockGroup(id=1, name="Group A", player_ids=[1, 3], category="U13")
        ]

        # Export to temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as f:
            temp_path = f.name

        try:
            export_groups_csv(groups, self.players_by_id, {}, temp_path)

            # Verify file was created and has content
            assert Path(temp_path).exists()

            # Read and verify content
            with open(temp_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 2  # 2 players in the group
            assert rows[0]["Group"] == "Group A"
            assert rows[0]["Player_Name"] == "Juan Perez"
            assert rows[0]["Country"] == "ESP"
            assert rows[1]["Player_Name"] == "Carlos Lopez"
            assert rows[1]["Country"] == "ARG"

        finally:
            # Clean up
            Path(temp_path).unlink()

    def test_export_standings_csv(self):
        """Test exporting standings to CSV."""
        standings = [
            GroupStanding(
                group_id=1,
                player_id=1,
                position=1,
                wins=2,
                losses=0,
                sets_w=6,
                sets_l=1,
                points_w=66,
                points_l=45,
                points_total=4,
            ),
            GroupStanding(
                group_id=1,
                player_id=3,
                position=2,
                wins=0,
                losses=2,
                sets_w=1,
                sets_l=6,
                points_w=45,
                points_l=66,
                points_total=2,
            ),
        ]

        # Export to temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as f:
            temp_path = f.name

        try:
            export_standings_csv(standings, self.players_by_id, temp_path)

            # Verify file was created
            assert Path(temp_path).exists()

            # Read and verify content
            with open(temp_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 2
            assert rows[0]["Position"] == "1"
            assert rows[0]["Player_Name"] == "Juan Perez"
            assert rows[0]["Points"] == "4"
            assert rows[0]["Wins"] == "2"
            assert rows[0]["Losses"] == "0"

            assert rows[1]["Position"] == "2"
            assert rows[1]["Player_Name"] == "Carlos Lopez"
            assert rows[1]["Points"] == "2"

        finally:
            Path(temp_path).unlink()

    def test_export_bracket_csv(self):
        """Test exporting bracket to CSV."""
        # Create mock bracket
        class MockBracket:
            def __init__(self):
                self.slots = {
                    RoundType.FINAL: [
                        BracketSlot(
                            slot_number=1,
                            round_type=RoundType.FINAL,
                            player_id=1,
                            is_bye=False,
                            same_country_warning=False,
                        ),
                        BracketSlot(
                            slot_number=2,
                            round_type=RoundType.FINAL,
                            player_id=2,
                            is_bye=False,
                            same_country_warning=False,
                        ),
                    ]
                }

        bracket = MockBracket()

        # Export to temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as f:
            temp_path = f.name

        try:
            export_bracket_csv(bracket, self.players_by_id, temp_path)

            # Verify file was created
            assert Path(temp_path).exists()

            # Read and verify content
            with open(temp_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 2
            assert rows[0]["Round"] == "F"
            assert rows[0]["Player_Name"] == "Juan Perez"
            assert rows[0]["Is_BYE"] == "NO"

            assert rows[1]["Player_Name"] == "Maria Garcia"
            assert rows[1]["Country"] == "MEX"

        finally:
            Path(temp_path).unlink()

    def test_export_bracket_with_bye(self):
        """Test exporting bracket with BYE slots."""
        class MockBracket:
            def __init__(self):
                self.slots = {
                    RoundType.SEMIFINAL: [
                        BracketSlot(
                            slot_number=1,
                            round_type=RoundType.SEMIFINAL,
                            player_id=1,
                            is_bye=False,
                            same_country_warning=False,
                        ),
                        BracketSlot(
                            slot_number=2,
                            round_type=RoundType.SEMIFINAL,
                            player_id=None,
                            is_bye=True,
                            same_country_warning=False,
                        ),
                    ]
                }

        bracket = MockBracket()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as f:
            temp_path = f.name

        try:
            export_bracket_csv(bracket, self.players_by_id, temp_path)

            with open(temp_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 2
            assert rows[0]["Is_BYE"] == "NO"
            assert rows[1]["Is_BYE"] == "YES"
            assert rows[1]["Player_Name"] == ""

        finally:
            Path(temp_path).unlink()

    def test_export_bracket_same_country_warning(self):
        """Test exporting bracket with same country warning."""
        class MockBracket:
            def __init__(self):
                self.slots = {
                    RoundType.FINAL: [
                        BracketSlot(
                            slot_number=1,
                            round_type=RoundType.FINAL,
                            player_id=1,
                            is_bye=False,
                            same_country_warning=True,  # Warning flag
                        ),
                    ]
                }

        bracket = MockBracket()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as f:
            temp_path = f.name

        try:
            export_bracket_csv(bracket, self.players_by_id, temp_path)

            with open(temp_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert rows[0]["Same_Country_Warning"] == "YES"

        finally:
            Path(temp_path).unlink()
