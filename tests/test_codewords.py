import pytest

from app import codewords


def test_generated_code_is_adjective_dash_noun():
    for _ in range(200):
        code = codewords.generate()
        adjective, separator, noun = code.partition("-")
        assert separator == "-"
        assert adjective in codewords.ADJECTIVES
        assert noun in codewords.NOUNS


def test_generated_codes_survive_a_round_trip_through_normalize():
    for _ in range(200):
        code = codewords.generate()
        assert codewords.normalize(code) == code


def test_vocabulary_is_typeable_on_a_phone():
    words = codewords.ADJECTIVES + codewords.NOUNS
    assert all(word.isascii() and word.isalpha() and word.islower() for word in words)
    assert all(3 <= len(word) <= 6 for word in words)
    assert len(set(words)) == len(words), "no word appears twice, in either list"


def test_vocabulary_has_enough_entropy():
    assert len(codewords.ADJECTIVES) >= 100
    assert len(codewords.NOUNS) >= 100
    assert codewords.COMBINATIONS >= 10_000


def test_code_space_is_at_least_a_million():
    """Slice 1 target: the vocabulary must span >= 1e6 distinct codes."""
    assert len(codewords.ADJECTIVES) * len(codewords.NOUNS) >= 1_000_000
    assert codewords.COMBINATIONS >= 1_000_000


def test_generator_spreads_across_the_vocabulary():
    codes = {codewords.generate() for _ in range(500)}
    assert len(codes) > 450, "500 draws should almost never collide"


@pytest.mark.parametrize(
    "raw",
    [
        "red-fox",
        "redfox",
        "Red Fox",
        "RED_FOX",
        "  red-fox  ",
        "ReDfOx",
        "red_fox",
        "red fox",
        "red+fox",
        "red.fox",
        "RedFox",
    ],
)
def test_every_spelling_of_a_code_normalizes_to_one_form(raw):
    assert codewords.normalize(raw) == "red-fox"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "red",
        "fox",
        "fox-red",  # noun-adjective order is not a code
        "red-fox-blue",
        "purple-dinosaur",
        "zzz-qqq",
        "red-fox!",
        "red/fox",
        "12345",
        "red-fox1",
        "красный-лис",
    ],
)
def test_garbage_and_unknown_words_are_rejected(raw):
    assert codewords.normalize(raw) is None


def test_normalize_rejects_non_strings():
    assert codewords.normalize(None) is None  # type: ignore[arg-type]


def test_no_run_together_code_is_ambiguous():
    """Every generatable code must survive being typed without a separator."""
    for adjective in codewords.ADJECTIVES:
        for noun in codewords.NOUNS:
            joined = adjective + noun
            assert codewords.normalize(joined) == f"{adjective}-{noun}"
