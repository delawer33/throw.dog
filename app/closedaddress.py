"""Addresses for closed (end-to-end encrypted) throws.

Pure module: no framework, no I/O, no mutable global state.

A closed throw has no two-word code. Its key travels in the fragment of the
link, which no hand types, so the address is not built for hands either — it is
built for one job the words cannot do:

    the receiver page must know a key is required from the *shape of the
    address alone*, before it asks the server for anything.

Everything else here follows from that. If a keyless arrival had to ask the
server "is this closed?", the ask would consume the throw and the correct link,
sent a minute later, would open onto nothing. So recognition has to be local,
and for local recognition to be safe the two address spaces must not overlap.

Disjointness invariant
----------------------
Guaranteed structurally, in both directions, not by luck:

- **No closed address normalises to a code.** :data:`ALPHABET` contains digits
  and :func:`generate` always places one first, while
  :func:`app.codewords.normalize` accepts only alphabetic tokens — one digit is
  enough to make a code impossible.
- **No code passes as a closed address.** A code carries a separator or runs two
  alphabetic words together; either way it has no leading digit, and the
  hyphen is not in the alphabet.

Unlike a code, an address is never retyped, so recognition is exact: no case
folding, no separator tolerance, no trimming. Being lenient here would buy
nothing and could only blur the boundary above.
"""

from __future__ import annotations

import secrets
from typing import Final

#: Digits an address may start with. ``0`` and ``1`` are left out for the same
#: reason as ``l``/``o`` below — a human occasionally has to read an address off
#: a screen to check it matches, even though they never type it.
_LEADING_DIGITS: Final = "23456789"

#: Lowercase letters and digits, minus the four that read as each other
#: (``0``/``o``, ``1``/``l``). 32 symbols, so every character past the first is
#: worth exactly five bits.
ALPHABET: Final = "23456789abcdefghijkmnpqrstuvwxyz"

#: Total address length. The ceiling is the QR budget: a version-4 byte-mode
#: symbol holds 78 characters, and ``https://throw.dog/`` plus ``#`` plus a
#: 43-character base64url key already spends 62 of them. 14 fits with room to
#: spare and still buys ~68 bits, which is what matters — a miss on a closed
#: address is deliberately not charged to any miss budget, so enumeration must
#: be hopeless on its own terms rather than because something throttles it.
LENGTH: Final = 14

#: The same rule as :func:`is_closed_address`, as a regular expression, so the
#: receiver page can decide identically in the browser. Generated from the
#: constants above rather than written twice: one drifting copy of this rule
#: would break the guarantee silently, and a test pins them together.
JS_PATTERN: Final = "^[%s][%s]{%d}$" % (_LEADING_DIGITS, ALPHABET, LENGTH - 1)


def generate() -> str:
    """A fresh closed address.

    Uses :mod:`secrets`: like a code, the address is all that stands between a
    stranger and a throw — except here it also cannot be rate-limited, so a
    predictable PRNG would be the whole attack.
    """
    first = secrets.choice(_LEADING_DIGITS)
    rest = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH - 1))
    return first + rest


def is_closed_address(raw: object) -> bool:
    """Whether ``raw`` is exactly a closed address.

    Exact by design (see the module docstring): the caller is a machine reading
    a link it was handed, never a person typing.
    """
    if not isinstance(raw, str) or len(raw) != LENGTH:
        return False
    if raw[0] not in _LEADING_DIGITS:
        return False
    return all(char in ALPHABET for char in raw)
