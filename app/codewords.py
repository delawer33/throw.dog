"""Two-word codes for throws: ``adjective-noun``, e.g. ``red-fox``.

Pure module: no framework, no I/O, no mutable global state.

The vocabulary is deliberately boring — short (3-6 letters), common English
words that a person can read off one screen and retype on a phone keyboard
without hesitating about the spelling.
"""

from __future__ import annotations

import secrets
from typing import Final

SEPARATOR: Final = "-"

ADJECTIVES: Final[tuple[str, ...]] = (
    "agile", "alert", "amber", "ample", "angry", "azure", "basic", "black",
    "blank", "bland", "blue", "blunt", "bold", "bossy", "brave", "brief",
    "brisk", "broad", "brown", "bumpy", "busy", "calm", "cheap", "chill",
    "civic", "clean", "clear", "cosmic", "crisp", "curly", "cyan", "daily",
    "damp", "dark", "deep", "dense", "dizzy", "dull", "eager", "early",
    "easy", "empty", "equal", "exact", "extra", "fancy", "fast", "fine",
    "firm", "flat", "fluffy", "fond", "free", "fresh", "funny", "fuzzy",
    "glad", "good", "grand", "gray", "great", "green", "happy", "hardy",
    "hasty", "heavy", "high", "humble", "icy", "ideal", "idle", "jolly",
    "jumpy", "keen", "kind", "large", "late", "lazy", "light", "lively",
    "local", "long", "loud", "lucky", "magic", "major", "merry", "mighty",
    "mild", "minor", "misty", "modern", "narrow", "neat", "nice", "noble",
    "noisy", "novel", "olive", "open", "oval", "pale", "peppy", "pink",
    "plump", "polar", "prime", "proud", "pure", "purple", "quick", "quiet",
    "rapid", "rare", "ready", "red", "rich", "ripe", "rocky", "rosy", "rough",
    "round", "royal", "rural", "rusty", "sandy", "sharp", "shiny", "short",
    "silly", "silver", "simple", "slim", "slow", "small", "smart", "smooth",
    "snappy", "snowy", "soft", "solar", "solid", "sour", "spare", "spicy",
    "stark", "steady", "steep", "stern", "still", "stony", "stout", "sunny",
    "super", "sweet", "swift", "tall", "tame", "tasty", "teal", "tender",
    "tidy", "tiny", "tough", "true", "ultra", "upper", "urban", "vast",
    "vivid", "warm", "wavy", "wide", "wild", "windy", "wise", "witty",
    "young", "zesty",
)

NOUNS: Final[tuple[str, ...]] = (
    "acorn", "anchor", "apple", "arrow", "atlas", "badger", "bagel", "bamboo",
    "banjo", "barn", "basil", "beach", "beam", "bean", "beetle", "bell",
    "berry", "bike", "bird", "boat", "bolt", "bone", "book", "boot",
    "bowl", "branch", "brick", "bridge", "broom", "brush", "bubble", "bucket",
    "bugle", "bulb", "bunny", "bush", "cabin", "cable", "cactus", "cake",
    "camel", "candle", "canoe", "canyon", "card", "carpet", "carrot", "castle",
    "cave", "cedar", "chair", "cheese", "cherry", "chess", "cider", "city",
    "cliff", "cloud", "clover", "coast", "cobra", "cocoa", "coin", "comet",
    "cone", "corn", "couch", "crab", "crane", "crate", "crayon", "creek",
    "crown", "cube", "curve", "daisy", "dawn", "deck", "delta", "desert",
    "desk", "diary", "dime", "ditch", "dock", "dome", "donkey", "door",
    "dove", "dragon", "dream", "drum", "duck", "dune", "dusk", "eagle",
    "earth", "echo", "edge", "elbow", "ember", "engine", "fable", "falcon",
    "farm", "fawn", "fence", "fern", "ferry", "field", "film", "finch",
    "fire", "flame", "flask", "fleet", "flint", "flock", "floor", "flute",
    "foam", "forest", "fork", "fort", "fox", "frog", "fruit", "fudge",
    "garden", "gate", "ghost", "ginger", "glade", "glass", "globe", "glove",
    "goat", "goose", "grape", "grass", "grove", "gull", "hammer", "harbor",
    "harp", "hawk", "hazel", "heart", "hedge", "helmet", "herb", "hill",
    "hive", "honey", "hook", "horse", "house", "igloo", "iris", "iron",
    "island", "ivory", "jacket", "jelly", "jewel", "juice", "jungle", "kayak",
    "kettle", "kite", "kitten", "knot", "koala", "lace", "ladder", "lagoon",
    "lake", "lamp", "lark", "laser", "lava", "leaf", "ledge", "lemon",
    "lily", "lime", "lion", "lizard", "llama", "lock", "lotus", "lynx",
    "magnet", "maple", "marble", "market", "marsh", "mask", "meadow", "medal",
    "melon", "mesa", "meteor", "mint", "mirror", "mole", "monkey", "moon",
    "moss", "motor", "mound", "mouse", "muffin", "mule", "nest", "nickel",
    "noodle", "nugget", "oasis", "ocean", "onion", "orange", "orbit", "otter",
    "oyster", "paddle", "palm", "panda", "panel", "pantry", "paper", "parrot",
    "path", "patio", "peach", "pearl", "pebble", "pencil", "pepper", "petal",
    "phone", "piano", "pigeon", "pillow", "pilot", "pine", "pipe", "pizza",
    "planet", "plant", "plaza", "plum", "pocket", "pond", "pony", "poppy",
    "port", "potato", "prism", "puddle", "puppy", "purse", "quartz", "queen",
    "quill", "quilt", "rabbit", "radar", "radio", "raft", "rail", "ranch",
    "raven", "ribbon", "ridge", "ring", "river", "robin", "robot", "rocket",
    "rope", "rose", "ruler", "saddle", "safari", "salad", "salmon", "sand",
    "sauce", "scarf", "school", "seal", "seed", "shark", "sheep", "shelf",
    "shell", "shield", "ship", "shoe", "shore", "shrub", "silk", "siren",
    "skate", "sled", "sleeve", "slope", "smoke", "snail", "snake", "snow",
    "socket", "sofa", "soup", "spade", "spark", "spider", "spoon", "spring",
    "spruce", "square", "squid", "stable", "stage", "stair", "stamp", "star",
    "steam", "steel", "stone", "stork", "storm", "stove", "straw", "stream",
    "street", "string", "studio", "summit", "swan", "syrup", "table", "tank",
    "tape", "teapot", "temple", "tent", "thumb", "tiger", "timber", "toast",
    "token", "tomato", "tongue", "tooth", "torch", "tower", "town", "track",
    "train", "trail", "tram", "trout", "truck", "trunk", "tulip", "tunnel",
    "turtle", "twig", "valley", "vase", "velvet", "vessel", "vine", "violet",
    "violin", "wagon", "walnut", "walrus", "wasp", "water", "wave", "whale",
    "wheat", "wheel", "willow", "window", "wing", "winter", "wire", "wolf",
    "worm", "wrench", "yacht", "yard", "yarn", "zebra", "zone",
)

_ADJECTIVE_SET: Final[frozenset[str]] = frozenset(ADJECTIVES)
_NOUN_SET: Final[frozenset[str]] = frozenset(NOUNS)

_MIN_WORD_LEN: Final = min(len(w) for w in ADJECTIVES + NOUNS)
_MAX_WORD_LEN: Final = max(len(w) for w in ADJECTIVES + NOUNS)

#: Number of distinct codes the vocabulary can produce.
COMBINATIONS: Final = len(ADJECTIVES) * len(NOUNS)


def generate() -> str:
    """Return a fresh random code such as ``red-fox``.

    Uses :mod:`secrets` — codes are the only thing guarding a throw, so they
    must not come from a predictable PRNG.
    """
    return f"{secrets.choice(ADJECTIVES)}{SEPARATOR}{secrets.choice(NOUNS)}"


def normalize(raw: str) -> str | None:
    """Canonicalise user input to ``adjective-noun``, or return ``None``.

    Case, and any mix of hyphen / space / underscore / no separator at all,
    are treated as equivalent::

        red-fox, redfox, Red Fox, RED_FOX  ->  red-fox

    Anything that is not two known words (garbage, unknown words, an
    ambiguous run-together spelling) yields ``None``.
    """
    if not isinstance(raw, str):
        return None

    cleaned = raw.strip().lower()
    if not cleaned:
        return None

    for sep in ("-", "_", " ", "\t", "+", "."):
        cleaned = cleaned.replace(sep, " ")
    tokens = cleaned.split()

    if not tokens or not all(token.isascii() and token.isalpha() for token in tokens):
        return None

    if len(tokens) == 2:
        adjective, noun = tokens
        if adjective in _ADJECTIVE_SET and noun in _NOUN_SET:
            return f"{adjective}{SEPARATOR}{noun}"
        return None

    if len(tokens) == 1:
        return _split_joined(tokens[0])

    return None


def _split_joined(word: str) -> str | None:
    """Resolve a run-together code (``redfox``) against the vocabulary.

    Returns ``None`` when no split works, or when more than one split works —
    an ambiguous code is worse than an unreadable one.
    """
    matches = []
    upper = min(len(word) - _MIN_WORD_LEN, _MAX_WORD_LEN)
    for cut in range(_MIN_WORD_LEN, upper + 1):
        head, tail = word[:cut], word[cut:]
        if head in _ADJECTIVE_SET and tail in _NOUN_SET:
            matches.append(f"{head}{SEPARATOR}{tail}")
            if len(matches) > 1:
                return None
    return matches[0] if matches else None
