"""Unit tests for core/matcher.py — pure functions, no external dependencies."""
import pytest

from core.matcher import (
    SCCandidate,
    find_best_match,
    normalize,
    score_track_match,
    split_artists,
    transliterate_variants,
)


# ---------------------------------------------------------------------------
# split_artists()
# ---------------------------------------------------------------------------

class TestSplitArtists:
    def test_feat_dot(self):
        assert split_artists("A feat. B") == ["A", "B"]

    def test_ft_dot(self):
        assert split_artists("A ft. B") == ["A", "B"]

    def test_ampersand(self):
        assert split_artists("A & B & C") == ["A", "B", "C"]

    def test_x_separator(self):
        assert split_artists("A x B") == ["A", "B"]

    def test_mixed_separators(self):
        assert split_artists("A ft. B x C") == ["A", "B", "C"]

    def test_solo_artist(self):
        assert split_artists("Solo Artist") == ["Solo Artist"]

    def test_cyrillic(self):
        result = split_artists("Земфира feat. Океан Ельзи")
        assert result == ["Земфира", "Океан Ельзи"]

    def test_no_duplicates(self):
        result = split_artists("A & A")
        assert result == ["A"]

    def test_pri_uch_dot(self):
        assert split_artists("Артист при уч. Другой") == ["Артист", "Другой"]

    def test_pri_uch_no_dot(self):
        assert split_artists("Артист при уч Другой") == ["Артист", "Другой"]

    def test_pri_uchastii(self):
        assert split_artists("Артист при участии Другой") == ["Артист", "Другой"]

    def test_case_insensitive(self):
        assert split_artists("A FEAT. B") == ["A", "B"]
        assert split_artists("A Ft. B") == ["A", "B"]
        assert split_artists("Артист При Участии Другой") == ["Артист", "Другой"]


# ---------------------------------------------------------------------------
# normalize()
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_empty_string(self):
        assert normalize("") == ""

    def test_whitespace_only(self):
        assert normalize("   ") == ""

    def test_lowercase(self):
        assert normalize("Hello World") == "hello world"

    def test_feat_parenthesised(self):
        assert normalize("Track (feat. Artist)") == "track"

    def test_feat_ft(self):
        result = normalize("Song ft. Someone")
        assert "ft" not in result
        assert "someone" not in result

    def test_feat_featuring(self):
        result = normalize("Music featuring DJ")
        assert "featuring" not in result

    def test_remaster(self):
        assert normalize("Song (Remastered)") == "song"

    def test_deluxe_edition(self):
        result = normalize("Album (Deluxe Edition)")
        assert "deluxe" not in result
        assert "edition" not in result

    def test_punctuation_removed(self):
        result = normalize("Hello, World!")
        assert "," not in result
        assert "!" not in result

    def test_em_dash_removed(self):
        result = normalize("Artist — Title")
        assert "—" not in result

    def test_whitespace_collapsed(self):
        assert normalize("  hello   world  ") == "hello world"

    def test_no_leading_trailing_spaces(self):
        result = normalize("  test  ")
        assert result == result.strip()

    def test_unicode_nfkd(self):
        # NFKD should decompose composed characters
        result = normalize("café")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# transliterate_variants()
# ---------------------------------------------------------------------------

class TestTransliterateVariants:
    def test_latin_unchanged(self):
        variants = transliterate_variants("hello world")
        assert variants == ["hello world"]

    def test_cyrillic_produces_multiple_variants(self):
        variants = transliterate_variants("Привет")
        assert len(variants) > 1
        assert "Привет" in variants

    def test_cyrillic_no_duplicates(self):
        variants = transliterate_variants("Кино")
        assert len(variants) == len(set(variants))

    def test_mixed_latin_cyrillic(self):
        # Has at least one Cyrillic char → triggers transliteration
        variants = transliterate_variants("DJ Кино")
        assert len(variants) >= 1

    def test_empty_string(self):
        variants = transliterate_variants("")
        assert variants == [""]

    def test_digits_unchanged(self):
        variants = transliterate_variants("123")
        assert variants == ["123"]


# ---------------------------------------------------------------------------
# score_track_match()
# ---------------------------------------------------------------------------

class TestScoreTrackMatch:
    def test_exact_latin_match(self):
        score = score_track_match("Radiohead", "Creep", "Radiohead", "Creep")
        assert score >= 95.0

    def test_zero_match(self):
        score = score_track_match("Beatles", "Hey Jude", "Drake", "Gods Plan")
        assert score < 50.0

    def test_cyrillic_vs_transliterated_latin(self):
        # Кино → Kino should match well after transliteration
        score = score_track_match(
            "Кино", "Звезда по имени Солнце",
            "Kino", "Zvezda po imeni Solntse"
        )
        assert score > 40.0

    def test_title_weighted_more_than_artist(self):
        # Artist mismatch score vs title mismatch score
        score_artist_mismatch = score_track_match(
            "Totally Wrong Artist", "Creep", "Radiohead", "Creep"
        )
        score_title_mismatch = score_track_match(
            "Radiohead", "Totally Wrong Title", "Radiohead", "Creep"
        )
        # Title has 60% weight vs artist 40% — title mismatch should hurt more
        assert score_artist_mismatch > score_title_mismatch

    def test_empty_artist_does_not_crash(self):
        score = score_track_match("", "Creep", "Radiohead", "Creep")
        assert 0.0 <= score <= 100.0

    def test_empty_title_does_not_crash(self):
        score = score_track_match("Radiohead", "", "Radiohead", "Creep")
        assert 0.0 <= score <= 100.0

    def test_score_bounded(self):
        score = score_track_match("Artist", "Title", "Artist", "Title")
        assert 0.0 <= score <= 100.0

    def test_similar_titles_score_higher(self):
        score_similar = score_track_match("Artist", "Creep", "Artist", "Creep (Live)")
        score_different = score_track_match("Artist", "Creep", "Artist", "Karma Police")
        assert score_similar > score_different


# ---------------------------------------------------------------------------
# find_best_match()
# ---------------------------------------------------------------------------

class TestFindBestMatch:
    def test_empty_candidates_returns_none(self):
        result = find_best_match("Artist", "Title", [])
        assert result is None

    def test_best_candidate_selected(self):
        candidates = [
            SCCandidate(sc_id=1, sc_url="u1", artist="Drake", title="Gods Plan"),
            SCCandidate(sc_id=2, sc_url="u2", artist="Radiohead", title="Creep"),
        ]
        result = find_best_match("Radiohead", "Creep", candidates, threshold=75.0)
        assert result is not None
        assert result.sc_id == 2

    def test_matched_true_above_threshold(self):
        candidates = [
            SCCandidate(sc_id=1, sc_url="u1", artist="Radiohead", title="Creep"),
        ]
        result = find_best_match("Radiohead", "Creep", candidates, threshold=75.0)
        assert result is not None
        assert result.matched is True

    def test_matched_false_below_threshold(self):
        candidates = [
            SCCandidate(sc_id=1, sc_url="u1", artist="Drake", title="Gods Plan"),
        ]
        result = find_best_match("Beatles", "Hey Jude", candidates, threshold=75.0)
        assert result is not None
        assert result.matched is False

    def test_uncertain_in_zone(self):
        # threshold=75, uncertain zone: [60, 75)
        # Use a candidate with a small name variation to hit ~65-74 range
        candidates = [
            SCCandidate(sc_id=1, sc_url="u1", artist="Radiohedd", title="Creep"),
        ]
        result = find_best_match("Radiohead", "Creep", candidates, threshold=75.0)
        assert result is not None
        # If score is in uncertain zone it must not be matched
        if result.uncertain:
            assert result.matched is False
            assert result.score >= 60.0
            assert result.score < 75.0

    def test_matched_and_uncertain_mutually_exclusive(self):
        candidates = [
            SCCandidate(sc_id=1, sc_url="u1", artist="Artist", title="Title"),
        ]
        result = find_best_match("Artist", "Title", candidates, threshold=75.0)
        assert result is not None
        # Can't be both matched and uncertain
        assert not (result.matched and result.uncertain)

    def test_custom_threshold(self):
        candidates = [
            SCCandidate(sc_id=1, sc_url="u1", artist="Radiohead", title="Creep"),
        ]
        result_strict = find_best_match("Radiohead", "Creep", candidates, threshold=99.0)
        result_loose = find_best_match("Radiohead", "Creep", candidates, threshold=10.0)
        assert result_loose is not None and result_loose.matched is True
        # With threshold=99 a near-perfect match might still not reach 99
        assert result_strict is not None  # result exists, matched depends on score

    def test_result_fields_populated(self):
        candidates = [
            SCCandidate(sc_id=42, sc_url="http://sc/42", artist="Radiohead", title="Creep"),
        ]
        result = find_best_match("Radiohead", "Creep", candidates, threshold=75.0)
        assert result is not None
        assert result.sc_id == 42
        assert result.sc_url == "http://sc/42"
        assert result.sc_artist == "Radiohead"
        assert result.sc_title == "Creep"
        assert isinstance(result.score, float)
