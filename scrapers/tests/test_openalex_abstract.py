"""
Tests for scrapers.openalex.abstract_utils.reconstruct_abstract.

Does NOT call the OpenAlex API.  All inputs are local Python objects.
"""
import pytest

from scrapers.openalex.abstract_utils import reconstruct_abstract


class TestReconstructAbstract:
    def test_none_input_returns_none(self):
        assert reconstruct_abstract(None) is None

    def test_empty_dict_returns_none(self):
        assert reconstruct_abstract({}) is None

    def test_normal_inverted_index(self):
        index = {
            "Open": [0],
            "Access": [1],
            "is": [2],
            "growing": [3],
        }
        result = reconstruct_abstract(index)
        assert result == "Open Access is growing"

    def test_multiple_positions_per_word(self):
        index = {
            "the": [0, 4],
            "cat": [1],
            "sat": [2],
            "on": [3],
            "mat": [5],
        }
        result = reconstruct_abstract(index)
        assert result == "the cat sat on the mat"

    def test_out_of_order_keys(self):
        # Dict keys are not in position order — must sort
        index = {
            "world": [1],
            "hello": [0],
        }
        result = reconstruct_abstract(index)
        assert result == "hello world"

    def test_plain_string_input(self):
        result = reconstruct_abstract("This is a plain abstract.")
        assert result == "This is a plain abstract."

    def test_plain_string_empty_returns_none(self):
        assert reconstruct_abstract("   ") is None

    def test_malformed_non_list_positions(self):
        # Positions value is not a list — the entry should be skipped
        index = {
            "valid": [0],
            "bad": "not-a-list",
        }
        result = reconstruct_abstract(index)
        assert result == "valid"

    def test_malformed_non_int_position(self):
        index = {
            "hello": [0],
            "world": ["not-an-int"],
        }
        result = reconstruct_abstract(index)
        assert result == "hello"

    def test_negative_position_skipped(self):
        index = {
            "good": [0],
            "bad": [-1],
        }
        result = reconstruct_abstract(index)
        assert result == "good"

    def test_non_dict_input_returns_none(self):
        assert reconstruct_abstract(12345) is None
        assert reconstruct_abstract([1, 2, 3]) is None

    def test_large_inverted_index(self):
        # Real-world example from work_normal fixture
        index = {
            "Despite": [0],
            "growing": [1],
            "interest": [2],
            "in": [3],
            "Open": [4],
            "Access": [5],
        }
        result = reconstruct_abstract(index)
        assert result == "Despite growing interest in Open Access"

    def test_empty_string_word(self):
        # Edge case: empty string as a word key
        index = {
            "": [0],
            "valid": [1],
        }
        result = reconstruct_abstract(index)
        # Empty string is still a valid word, just empty
        assert result is not None
        assert "valid" in result
