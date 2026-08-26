"""Closed addresses must never be mistaken for a two-word code, or vice versa.

That disjointness is not a nicety: the receiver page decides "this throw needs a
key" from the shape of the address alone, *before* it asks the server for
anything. If a closed address could normalise to a real code, a keyless arrival
would consume a throw nobody can decrypt; if a code could pass as a closed
address, an honest reader would be asked for a key that does not exist.

So the central test below is exhaustive over the whole vocabulary, not a
sample — a probabilistic argument is not good enough for the one guarantee the
mode rests on.
"""

import re

import pytest

from app.closedaddress import (
    ALPHABET,
    JS_PATTERN,
    LENGTH,
    generate,
    is_closed_address,
)
from app.codewords import ADJECTIVES, NOUNS, SEPARATOR, normalize

#: The QR budget: 'https://throw.dog/' (18) + '#' + a 43-char base64url key
#: leaves this much for the address inside a version-4 byte-mode symbol.
QR_ADDRESS_BUDGET = 16


def test_generated_addresses_are_recognised():
    for _ in range(200):
        assert is_closed_address(generate())


def test_generated_addresses_fit_the_qr_budget():
    assert LENGTH <= QR_ADDRESS_BUDGET


def test_generated_addresses_are_not_predictable():
    # A closed address is the only thing guarding a closed throw, so it must
    # come from a CSPRNG-sized space, not a handful of values.
    assert len({generate() for _ in range(500)}) == 500


def test_address_space_is_large_enough_to_forbid_enumeration():
    # Enumerating closed addresses must be hopeless, since a miss on one is
    # deliberately not charged to anyone's miss budget.
    assert len(ALPHABET) ** (LENGTH - 1) > 2**60


def test_no_closed_address_ever_normalises_to_a_code():
    for _ in range(2000):
        assert normalize(generate()) is None


def test_no_two_word_code_ever_looks_like_a_closed_address():
    # Exhaustive over the vocabulary: every word that can appear in a code, in
    # every shape a reader might type it (hyphenated, joined, spaced, upper).
    for word in ADJECTIVES + NOUNS:
        assert not is_closed_address(word)
    for adjective in ADJECTIVES:
        for noun in NOUNS:
            code = f"{adjective}{SEPARATOR}{noun}"
            assert not is_closed_address(code)
            assert not is_closed_address(adjective + noun)
            assert not is_closed_address(code.upper())
            assert not is_closed_address(f"{adjective} {noun}")


def test_junk_is_not_a_closed_address():
    for raw in ("", " ", "-", "x", "0" * LENGTH, "!" * LENGTH, "a" * LENGTH):
        assert not is_closed_address(raw)


def test_wrong_length_is_not_a_closed_address():
    address = generate()
    assert not is_closed_address(address[:-1])
    assert not is_closed_address(address + address[0])


def test_non_string_input_is_rejected():
    for raw in (None, 42, b"x" * LENGTH, ["a"]):
        assert not is_closed_address(raw)


def test_recognition_is_exact_not_lenient():
    # Unlike a two-word code, a closed address is never typed by hand, so there
    # is nothing to be forgiving about: case and whitespace are not equivalent.
    address = generate()
    assert not is_closed_address(address.upper())
    assert not is_closed_address(" " + address)
    assert not is_closed_address(address + " ")


def test_js_pattern_agrees_with_python_recognition():
    # The receiver page needs the same rule in the browser, and one drifting
    # copy of it would break the guarantee silently. The page is generated from
    # this pattern, so the two must decide identically.
    pattern = re.compile(JS_PATTERN)
    for _ in range(500):
        address = generate()
        assert bool(pattern.match(address)) is is_closed_address(address)
    for adjective in ADJECTIVES[:40]:
        for noun in NOUNS[:40]:
            code = f"{adjective}{SEPARATOR}{noun}"
            assert pattern.match(code) is None
            assert pattern.match(adjective + noun) is None


@pytest.mark.parametrize("bad", ["\n", " ", "a", "-"])
def test_js_pattern_is_anchored(bad):
    # Anchored at both ends, so a code with a closed address glued to it does
    # not pass in the browser.
    assert re.compile(JS_PATTERN).match(bad + generate()) is None
