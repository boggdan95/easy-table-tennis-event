"""Tests for table tennis validation rules."""

import pytest

from ettem.validation import (
    ValidationError,
    validate_match_sets,
    validate_tt_set,
    validate_walkover,
)


class TestValidateTTSet:
    """Test cases for validate_tt_set function."""

    def test_valid_normal_scores(self):
        """Test valid scores in normal situations (no deuce)."""
        # Standard wins
        assert validate_tt_set(11, 9) == (True, "")
        assert validate_tt_set(11, 7) == (True, "")
        assert validate_tt_set(11, 0) == (True, "")
        assert validate_tt_set(11, 5) == (True, "")

        # Reverse (player 2 wins)
        assert validate_tt_set(9, 11) == (True, "")
        assert validate_tt_set(3, 11) == (True, "")

    def test_valid_deuce_scores(self):
        """Test valid scores in deuce situations (≥10-10)."""
        # Basic deuce
        assert validate_tt_set(12, 10) == (True, "")
        assert validate_tt_set(10, 12) == (True, "")

        # Extended deuce
        assert validate_tt_set(13, 11) == (True, "")
        assert validate_tt_set(15, 13) == (True, "")
        assert validate_tt_set(20, 18) == (True, "")
        assert validate_tt_set(25, 23) == (True, "")

    def test_invalid_deuce_wrong_difference(self):
        """Test invalid deuce scores (difference != 2)."""
        # Difference of 1
        is_valid, msg = validate_tt_set(11, 10)
        assert is_valid is False
        assert "exactly +2 points" in msg

        is_valid, msg = validate_tt_set(13, 12)
        assert is_valid is False
        assert "exactly +2 points" in msg

        # Difference of 3 (too much in deuce)
        is_valid, msg = validate_tt_set(13, 10)
        assert is_valid is False
        assert "exactly +2 points" in msg

    def test_invalid_winner_below_11(self):
        """Test invalid scores where winner didn't reach 11."""
        is_valid, msg = validate_tt_set(10, 8)
        assert is_valid is False
        assert "at least 11 points" in msg

        is_valid, msg = validate_tt_set(9, 7)
        assert is_valid is False
        assert "at least 11 points" in msg

    def test_invalid_difference_too_small(self):
        """Test invalid scores with difference < 2 (non-deuce)."""
        is_valid, msg = validate_tt_set(11, 10)
        assert is_valid is False
        # This is caught by deuce rule since loser >= 10

    def test_invalid_negative_scores(self):
        """Test that negative scores are rejected."""
        is_valid, msg = validate_tt_set(-1, 11)
        assert is_valid is False
        assert "negative" in msg.lower()

        is_valid, msg = validate_tt_set(11, -5)
        assert is_valid is False
        assert "negative" in msg.lower()

    def test_invalid_tied_scores(self):
        """Test that tied scores are rejected."""
        is_valid, msg = validate_tt_set(11, 11)
        assert is_valid is False
        assert "tied" in msg.lower()

        is_valid, msg = validate_tt_set(10, 10)
        assert is_valid is False
        assert "tied" in msg.lower()


class TestValidateMatchSets:
    """Test cases for validate_match_sets function."""

    def test_valid_best_of_5_matches(self):
        """Test valid best-of-5 matches."""
        # 3-0 win
        assert validate_match_sets([(11, 9), (11, 7), (11, 5)]) == (True, "")

        # 3-1 win
        assert validate_match_sets([(11, 9), (8, 11), (11, 7), (11, 5)]) == (True, "")

        # 3-2 win (full distance)
        assert validate_match_sets(
            [(11, 9), (8, 11), (11, 7), (5, 11), (11, 9)]
        ) == (True, "")

    def test_valid_best_of_3_matches(self):
        """Test valid best-of-3 matches."""
        # 2-0 win
        assert validate_match_sets([(11, 9), (11, 7)], best_of=3) == (True, "")

        # 2-1 win
        assert validate_match_sets([(11, 9), (8, 11), (11, 7)], best_of=3) == (True, "")

    def test_valid_best_of_7_matches(self):
        """Test valid best-of-7 matches."""
        # 4-0 win
        assert validate_match_sets(
            [(11, 9), (11, 7), (11, 5), (11, 3)], best_of=7
        ) == (True, "")

        # 4-3 win (full distance)
        assert validate_match_sets(
            [(11, 9), (8, 11), (11, 7), (5, 11), (11, 9), (7, 11), (11, 8)],
            best_of=7,
        ) == (True, "")

    def test_invalid_match_set_score(self):
        """Test match with invalid individual set score."""
        # Second set has invalid score (11-10 in deuce)
        is_valid, msg = validate_match_sets([(11, 9), (11, 10), (11, 7)])
        assert is_valid is False
        assert "Set 2" in msg
        assert "exactly +2 points" in msg

    def test_invalid_too_many_sets(self):
        """Test match with too many sets."""
        is_valid, msg = validate_match_sets(
            [(11, 9), (11, 7), (11, 5), (11, 3), (11, 2), (11, 1)]  # 6 sets in bo5
        )
        assert is_valid is False
        assert "Too many sets" in msg

    def test_invalid_too_few_sets(self):
        """Test match with too few sets."""
        # Only 1 set in bo5 (minimum is 3)
        is_valid, msg = validate_match_sets([(11, 9)])
        assert is_valid is False
        assert "Not enough sets" in msg

        # Only 2 sets in bo5 (minimum is 3)
        is_valid, msg = validate_match_sets([(11, 9), (11, 7)])
        assert is_valid is False
        assert "Not enough sets" in msg

    def test_invalid_incomplete_match(self):
        """Test match where neither player won enough sets."""
        # Best of 5, both players won 1 set each (need 3 to win)
        is_valid, msg = validate_match_sets([(11, 9), (7, 11)])
        assert is_valid is False
        assert "incomplete" in msg.lower()

    def test_invalid_empty_sets(self):
        """Test match with no sets."""
        is_valid, msg = validate_match_sets([])
        assert is_valid is False
        assert "at least one set" in msg


class TestValidateWalkover:
    """Test cases for validate_walkover function."""

    def test_valid_walkover(self):
        """Test valid walkover scenarios."""
        assert validate_walkover(1, 2, 1) == (True, "")
        assert validate_walkover(1, 2, 2) == (True, "")
        assert validate_walkover(100, 200, 100) == (True, "")

    def test_invalid_walkover_winner_not_in_match(self):
        """Test invalid walkover where winner is not one of the players."""
        is_valid, msg = validate_walkover(1, 2, 3)
        assert is_valid is False
        assert "must be one of the two players" in msg

        is_valid, msg = validate_walkover(10, 20, 999)
        assert is_valid is False
        assert "must be one of the two players" in msg


class TestRealWorldScenarios:
    """Test real-world match scenarios."""

    def test_close_deuce_match(self):
        """Test a realistic close match with multiple deuces."""
        # Match with deuce sets
        sets = [
            (12, 10),  # Deuce in set 1
            (10, 12),  # Deuce in set 2
            (11, 8),  # Normal set 3
            (14, 12),  # Extended deuce in set 4
        ]
        is_valid, msg = validate_match_sets(sets)
        assert is_valid is True

    def test_dominant_victory(self):
        """Test a dominant 3-0 victory."""
        sets = [(11, 3), (11, 5), (11, 2)]
        assert validate_match_sets(sets) == (True, "")

    def test_comeback_victory(self):
        """Test a comeback from 0-2 to win 3-2."""
        sets = [
            (5, 11),  # Lost set 1
            (8, 11),  # Lost set 2
            (11, 9),  # Won set 3
            (11, 7),  # Won set 4
            (11, 6),  # Won set 5
        ]
        assert validate_match_sets(sets) == (True, "")
