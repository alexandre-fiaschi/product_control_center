"""Tests for SFTP folder name normalization and parsing."""

import pytest

from app.integrations.sftp.product_parsers import (
    normalize_patch_id,
    parse_track_from,
    parse_v73_patch,
    parse_v80_patch,
    parse_v80_version,
    parse_v81_patch,
    parse_v81_version,
    version_from_patch_id,
)


# --- normalize_patch_id ---

class TestNormalizePatchId:
    def test_v73_underscore(self):
        assert normalize_patch_id("ACARS_V7_3", "7_3_27_7") == "7.3.27.7"

    def test_v73_another(self):
        assert normalize_patch_id("ACARS_V7_3", "7_3_28_0") == "7.3.28.0"

    def test_v80_underscore(self):
        assert normalize_patch_id("ACARS_V8_0", "8_0_28_1") == "8.0.28.1"

    def test_v81_with_v_prefix(self):
        assert normalize_patch_id("ACARS_V8_1", "v8.1.0.0") == "8.1.0.0"

    def test_v81_without_v_prefix(self):
        assert normalize_patch_id("ACARS_V8_1", "8.1.11.0") == "8.1.11.0"

    def test_v81_with_v_high_numbers(self):
        assert normalize_patch_id("ACARS_V8_1", "v8.1.9.1") == "8.1.9.1"

    def test_garbage_returns_none(self):
        assert normalize_patch_id("ACARS_V8_1", "not_a_patch") is None

    def test_wrong_product_returns_none(self):
        assert normalize_patch_id("ACARS_V7_3", "8_0_28_1") is None

    def test_unknown_product_returns_none(self):
        assert normalize_patch_id("UNKNOWN", "anything") is None


# --- version_from_patch_id ---

class TestVersionFromPatchId:
    def test_v81(self):
        assert version_from_patch_id("8.1.9.1") == "8.1.9"

    def test_v80(self):
        assert version_from_patch_id("8.0.28.1") == "8.0.28"

    def test_v73(self):
        assert version_from_patch_id("7.3.27.7") == "7.3.27"


# --- parse_v81_version ---

class TestParseV81Version:
    def test_valid(self):
        assert parse_v81_version("ACARS_V8_1_0") == 0

    def test_double_digit(self):
        assert parse_v81_version("ACARS_V8_1_12") == 12

    def test_garbage(self):
        assert parse_v81_version("not_a_version") is None


# --- parse_v81_patch ---

class TestParseV81Patch:
    def test_with_v_prefix(self):
        assert parse_v81_patch("v8.1.0.0") == (0, 0)

    def test_without_v_prefix(self):
        assert parse_v81_patch("8.1.11.0") == (11, 0)

    def test_garbage(self):
        assert parse_v81_patch("garbage") is None


# --- parse_v80_version ---

class TestParseV80Version:
    def test_valid(self):
        assert parse_v80_version("8_0_28") == 28

    def test_low_number(self):
        assert parse_v80_version("8_0_4") == 4

    def test_garbage(self):
        assert parse_v80_version("ACARS_V8_0_28") is None


# --- parse_v80_patch ---

class TestParseV80Patch:
    def test_valid(self):
        assert parse_v80_patch("8_0_28_1") == (28, 1)

    def test_garbage(self):
        assert parse_v80_patch("garbage") is None


# --- parse_v73_patch ---

class TestParseV73Patch:
    def test_valid(self):
        assert parse_v73_patch("7_3_27_7") == (27, 7)

    def test_garbage(self):
        assert parse_v73_patch("garbage") is None


# --- parse_track_from ---

class TestParseTrackFrom:
    def test_none_returns_none(self):
        assert parse_track_from(None, "ACARS_V8_0") is None

    def test_v80(self):
        assert parse_track_from("8_0_28", "ACARS_V8_0") == 28

    def test_v73(self):
        assert parse_track_from("7_3_27_0", "ACARS_V7_3") == (27, 0)

    def test_v81_returns_none(self):
        # V8.1 has no track_from in config
        assert parse_track_from("anything", "ACARS_V8_1") is None
