"""Two-word codes for throws, e.g. ``red-fox``.

Pure module: no framework, no I/O, no mutable global state.

The vocabulary is deliberately boring — short (3-6 letters), common English
words that a person can read off one screen and retype on a phone keyboard
without hesitating about the spelling. The two lists together yield well over
one million distinct codes (their Cartesian product).

Split invariant
---------------
A code typed without a separator (``redfox``) must split back to exactly one
pair. This is guaranteed structurally: :data:`ADJECTIVES` is *prefix-free* —
no adjective is a prefix of another (every entry is six letters except the
three-letter ``red``, and no six-letter adjective starts with ``red``). With a
prefix-free first list, at most one adjective can be a prefix of any run-together
code, so at most one split can succeed.
"""

from __future__ import annotations

import secrets
from typing import Final

SEPARATOR: Final = "-"

ADJECTIVES: Final[tuple[str, ...]] = (
    "abacus", "abates", "abhors", "ablaze", "aborts", "absent", "accept", "acidly",
    "action", "acuity", "addend", "adduce", "adjust", "adores", "adults", "advise",
    "affect", "afield", "agates", "aghast", "ailing", "airman", "albeit", "alibis",
    "alkali", "allies", "allude", "altars", "always", "ambled", "amulet", "angled",
    "animal", "anions", "annoys", "anoint", "antler", "anyway", "apiece", "appeal",
    "arable", "arched", "arcing", "argues", "armada", "armpit", "arrant", "arrows",
    "ascend", "asleep", "assert", "assist", "asthma", "asylum", "atoned", "attain",
    "attire", "augurs", "autumn", "averse", "awakes", "badges", "baited", "baldly",
    "ballet", "banana", "banish", "banned", "barbed", "baring", "barley", "barren",
    "basely", "basins", "basket", "basted", "bathes", "batter", "baying", "beagle",
    "beaned", "beater", "became", "bedded", "befall", "behalf", "belles", "beside",
    "better", "bidder", "biking", "billet", "binges", "births", "biting", "blades",
    "blanks", "blazed", "bleary", "blight", "blithe", "bloods", "blouse", "bluing",
    "blurts", "bobbed", "bodies", "boiled", "bombed", "boning", "booked", "booted",
    "borrow", "bother", "bottle", "bought", "bovine", "bowled", "boxers", "braces",
    "braked", "brassy", "bravos", "breaks", "breeds", "brewer", "bridal", "bridge",
    "briefs", "bright", "broken", "brooch", "browse", "brutes", "bucket", "budget",
    "bugged", "bulged", "bumble", "bumper", "bunted", "burial", "burner", "bursts",
    "busier", "busses", "butane", "butter", "buzzer", "byline", "cabins", "caller",
    "calmly", "camera", "camped", "canary", "candle", "cannon", "canopy", "capers",
    "career", "carrot", "carver", "cashes", "casket", "castle", "casual", "cattle",
    "caught", "caveat", "cavity", "celery", "census", "chalet", "change", "charms",
    "chases", "checks", "cheery", "cheese", "cherry", "chests", "chided", "chilly",
    "chocks", "choker", "choral", "chosen", "chunks", "church", "chutes", "cinema",
    "circle", "cities", "citrus", "clamps", "classy", "clears", "cleric", "client",
    "clinch", "cloaks", "closer", "closet", "clouds", "cloves", "clutch", "coaxes",
    "coddle", "coffee", "coffin", "cohere", "colder", "collar", "colons", "colony",
    "combed", "comets", "common", "confer", "convoy", "cookie", "cooler", "cooper",
    "copper", "coring", "corner", "corset", "cosmos", "cotton", "coughs", "county",
    "couple", "coupon", "cousin", "covert", "cowers", "cranks", "crawls", "creaky",
    "create", "credit", "creeps", "crewed", "crises", "crooks", "crowed", "crumbs",
    "crutch", "cuddle", "cupped", "curing", "curses", "curved", "cutesy", "cycled",
    "dabble", "dainty", "damage", "damper", "danger", "daring", "darned", "deacon",
    "dearly", "debate", "debunk", "decent", "decoys", "deemed", "deface", "defied",
    "deform", "degree", "delves", "demote", "dental", "depict", "depots", "deride",
    "desert", "design", "detail", "detour", "devoid", "dieter", "digits", "dimmer",
    "dinner", "dipper", "dished", "disown", "divert", "diving", "doctor", "dogmas",
    "dollar", "domain", "doomed", "doting", "downed", "drafty", "dragon", "drawer",
    "dreary", "driers", "driven", "driver", "droops", "drowns", "drying", "dulled",
    "dusted", "earned", "eating", "eddies", "editor", "ejects", "eldest", "eludes",
    "empire", "enamel", "encore", "energy", "engine", "engulf", "enrich", "entire",
    "envied", "equals", "equity", "escape", "estate", "evened", "evilly", "exacts",
    "except", "excuse", "exited", "expels", "expert", "export", "extent", "eyelet",
    "fabric", "facing", "faints", "falcon", "family", "fanned", "farmer", "father",
    "faults", "fedora", "feline", "female", "fennel", "fewest", "fiddle", "fiesta",
    "figure", "filled", "filmed", "finder", "finger", "firing", "fiscal", "fitful",
    "fixing", "flakes", "flanks", "flatly", "flicks", "flinch", "flocks", "floral",
    "flower", "flurry", "foamed", "folded", "fonder", "forage", "forces", "forest",
    "forger", "formal", "forums", "foully", "framed", "frauds", "freest", "friend",
    "frisks", "frosts", "fueled", "fungal", "furrow", "future", "gadget", "gained",
    "galled", "gambit", "garage", "garden", "garish", "garlic", "garter", "gassed",
    "gauges", "gazing", "gentle", "giggle", "ginger", "glassy", "glitch", "glossy",
    "glower", "golden", "gospel", "gouged", "graces", "grafts", "granny", "grassy",
    "gravel", "grayed", "greasy", "grieve", "grimes", "grocer", "groovy", "ground",
    "groups", "grower", "growth", "grumpy", "guises", "guitar", "gulped", "gunner",
    "halves", "hammer", "handle", "harder", "harmed", "hasten", "hauled", "havens",
    "hazard", "healed", "hearth", "heater", "hectic", "heeded", "helium", "herald",
    "herein", "heroes", "hidden", "hiking", "hinted", "hitter", "hockey", "hollow",
    "honest", "honors", "hoping", "horrid", "hotbed", "hourly", "howled", "huddle",
    "humbly", "hunger", "hurdle", "hurray", "husked", "hyphen", "icings", "impact",
    "impede", "impose", "inbred", "incise", "indeed", "indoor", "infant", "inflow",
    "ingest", "injury", "inlets", "inputs", "insect", "insert", "insult", "intent",
    "invade", "invoke", "irking", "island", "itself", "jacket", "jailed", "jaunty",
    "jester", "jigsaw", "jokers", "jotted", "joyous", "juices", "jumper", "jungle",
    "jurors", "karate", "kettle", "kindle", "kitten", "knocks", "labels", "lacked",
    "ladder", "ladies", "lancer", "lapels", "lasers", "lasted", "latter", "lavish",
    "layman", "lazier", "leader", "leaned", "leased", "legacy", "legend", "legion",
    "lemons", "lentil", "lesson", "letter", "likens", "limber", "linens", "lining",
    "liquid", "listen", "liters", "lively", "loaded", "loaned", "locate", "locust",
    "logger", "loners", "lookup", "looser", "lordly", "louder", "lovely", "lowest",
    "lumber", "lynxes", "madcap", "magnet", "magpie", "making", "mallet", "manage",
    "maniac", "mantis", "manure", "marble", "marker", "market", "maroon", "marvel",
    "masons", "master", "matted", "matter", "maxims", "meaner", "medial", "meeker",
    "melody", "melons", "member", "memory", "mental", "merged", "messed", "meters",
    "method", "mettle", "middle", "milder", "milker", "mimics", "mingle", "minnow",
    "minute", "mirror", "misfit", "misses", "mixers", "mocked", "modern", "months",
    "morals", "motels", "mother", "mounts", "movers", "muffin", "murmur", "muscle",
    "musing", "muster", "mutter", "mystic", "naming", "napkin", "native", "nature",
    "nearby", "neater", "nectar", "needle", "nephew", "nested", "neural", "newest",
    "nicely", "nickel", "nieces", "nobler", "nosing", "notion", "nugget", "number",
    "nursed", "nymphs", "object", "obtain", "oddest", "office", "oiling", "onions",
    "openly", "orange", "ordain", "ounces", "outlay", "outset", "oxford", "oxygen",
    "pacify", "packet", "paging", "paired", "palace", "panted", "pardon", "parent",
    "parked", "parody", "partly", "pasted", "pastry", "patrol", "pauper", "payday",
    "peaked", "pearly", "peeked", "peered", "pencil", "pended", "people", "pepper",
    "person", "petals", "phones", "picked", "pickup", "pieces", "pillar", "pillow",
    "pilots", "pinker", "piston", "pivots", "placid", "plaits", "planet", "planks",
    "plated", "pleads", "plenty", "pliant", "plumes", "pocket", "poetry", "points",
    "poison", "police", "poling", "pollen", "ponder", "poorly", "poring", "posers",
    "potato", "potter", "pouted", "powder", "pranks", "prided", "primed", "prince",
    "priory", "prison", "profit", "pronto", "prunes", "psyche", "public", "puller",
    "pulsed", "puppet", "purify", "purple", "pursed", "pushed", "puzzle", "quests",
    "quilts", "quotas", "rabbit", "rabble", "racing", "radios", "rained", "raking",
    "ranges", "ranted", "rascal", "ration", "ravine", "razors", "realms", "reared",
    "rebuff", "recede", "recite", "rector", "red", "reeled", "reflex", "refuse",
    "regard", "reigns", "relate", "relief", "reload", "remedy", "rename", "rental",
    "repels", "repute", "rescue", "resets", "resist", "retail", "retort", "revamp",
    "revert", "revive", "reward", "rhymed", "ribbon", "ridden", "rinses", "ripped",
    "risked", "roamed", "robber", "rocked", "rocket", "rodent", "roller", "rookie",
    "rooter", "rotate", "roused", "routes", "rubble", "rugged", "ruling", "runner",
    "rushes", "rustle", "sadden", "saddle", "safety", "sailed", "salads", "salary",
    "saliva", "salmon", "salted", "salves", "sample", "sanely", "sating", "savage",
    "savors", "saying", "scanty", "scarce", "scenes", "scenic", "school", "scolds",
    "scored", "scrawl", "script", "scurvy", "seamed", "season", "secret", "seeded",
    "seemly", "seldom", "senate", "senior", "senses", "serial", "series", "server",
    "settle", "sewage", "shaded", "shadow", "shaken", "shames", "shares", "shaves",
    "sheets", "shield", "shifts", "shiner", "shoals", "shoots", "shoved", "shower",
    "shrews", "shrimp", "shroud", "sicken", "siding", "sifted", "signal", "silent",
    "silver", "simple", "singed", "singer", "single", "sinker", "sister", "siting",
    "skated", "skewed", "skinny", "skunks", "sleeps", "sleigh", "slicks", "slings",
    "slopes", "slough", "sludge", "smears", "smiled", "smoked", "smooth", "snaked",
    "snares", "sneaky", "snippy", "snored", "snowed", "soaped", "soccer", "socked",
    "soiled", "solids", "somber", "soothe", "sourer", "spaces", "sparer", "spawns",
    "specks", "spells", "sphere", "spider", "spinal", "spirit", "spline", "spoken",
    "sponge", "spools", "sporty", "sprain", "spread", "spring", "sprint", "sprout",
    "spying", "square", "squash", "squeal", "squire", "stable", "staged", "stakes",
    "stance", "starch", "starts", "states", "staves", "steals", "steeps", "stereo",
    "sticky", "stills", "stitch", "stolen", "stones", "storey", "stoves", "strait",
    "strays", "stream", "street", "stress", "strife", "string", "strips", "strung",
    "studio", "stunts", "sturdy", "styles", "subset", "subtle", "subway", "suckle",
    "suited", "sulked", "summer", "sundry", "sunset", "suntan", "supper", "supple",
    "surged", "swears", "sweets", "system", "tablet", "tacked", "tailed", "talked",
    "target", "tasked", "tastes", "taught", "taxied", "teapot", "temple", "tempts",
    "tendon", "tenser", "termed", "thefts", "themes", "thesis", "thinly", "thorns",
    "thread", "thrice", "throat", "throbs", "thrown", "thumbs", "ticker", "ticket",
    "tidied", "tiller", "timely", "tingle", "toilet", "tomato", "tongue", "tosses",
    "toying", "tracts", "tragic", "tramps", "travel", "treads", "tremor", "tribal",
    "trifle", "trivia", "tropic", "truant", "trusty", "tucked", "tunics", "tunnel",
    "turnip", "turtle", "twined", "twitch", "typist", "undoes", "uneven", "unisex",
    "unjust", "unload", "unroll", "unsent", "untold", "unwind", "uphill", "uplift",
    "upshot", "upward", "urging", "ushers", "vacuum", "valley", "varies", "vaults",
    "velvet", "verges", "vertex", "vetoed", "victim", "violet", "vipers", "virtue",
    "vistas", "voided", "voting", "wafers", "wagons", "waiter", "waking", "wallet",
    "wallop", "walnut", "wander", "warily", "warned", "washed", "wastes", "waving",
    "weaker", "wearer", "wedded", "weighs", "welled", "whaler", "whence", "whites",
    "widows", "wildly", "wilted", "window", "windup", "winked", "winter", "wintry",
    "wisdom", "wisely", "wishes", "wizard", "wonder", "worded", "wormed", "writes",
    "yearly", "yellow", "yogurt", "zeroes", "zipper",
)

NOUNS: Final[tuple[str, ...]] = (
    "abbot", "able", "above", "aces", "acne", "acted", "add", "adorn",
    "ages", "agony", "aide", "aimed", "aisle", "album", "alias", "allay",
    "alms", "along", "alter", "amble", "amiss", "amp", "and", "angst",
    "annul", "ant", "antic", "apart", "aping", "apple", "aqua", "arm",
    "arose", "ash", "ask", "atom", "audit", "aura", "axing", "babes",
    "bacon", "bade", "bah", "baker", "balks", "balmy", "bane", "bans",
    "bare", "bark", "barks", "barn", "base", "basin", "bass", "baste",
    "bathe", "beach", "beam", "bean", "bear", "bears", "bee", "beer",
    "begs", "belts", "berg", "berry", "bests", "bias", "bike", "bill",
    "binge", "birch", "birds", "bits", "blank", "bleat", "blew", "bliss",
    "blocs", "bloom", "blow", "bluff", "blush", "boat", "body", "bolt",
    "bone", "bonus", "booms", "boot", "bough", "bowel", "boxed", "brace",
    "brake", "brass", "brat", "bray", "bread", "brew", "brief", "brink",
    "brood", "brows", "bud", "bug", "bulb", "bulbs", "bulls", "bun",
    "bunt", "burns", "burrs", "bush", "but", "buzz", "cages", "cake",
    "cal", "calf", "cam", "can", "candy", "canon", "caper", "care",
    "carry", "cased", "caste", "cat", "cave", "cease", "cedar", "cents",
    "chair", "chalk", "char", "chat", "chefs", "chic", "chili", "chip",
    "choke", "chose", "chunk", "cinch", "clams", "clash", "clay", "clean",
    "cliff", "clips", "cloud", "clout", "coal", "cocoa", "cod", "coke",
    "colon", "colt", "combs", "con", "coo", "cope", "coral", "cork",
    "corn", "corps", "couch", "court", "cow", "coy", "crab", "craft",
    "crane", "crawl", "cream", "creed", "crest", "crier", "crock", "cross",
    "crow", "crude", "crust", "cry", "cubic", "cuff", "cup", "curd",
    "curl", "curt", "cycle", "dad", "daisy", "dame", "dare", "darts",
    "dawn", "day", "deals", "debit", "decay", "deed", "deer", "demon",
    "dents", "desks", "dial", "died", "digs", "dimes", "diner", "dis",
    "disks", "dive", "docks", "dog", "doled", "dome", "dons", "doped",
    "doted", "dough", "dove", "drab", "dread", "drier", "drip", "droop",
    "drug", "dry", "duck", "due", "dug", "dumb", "dunce", "dusk",
    "dust", "dwarf", "dyes", "eagle", "earl", "earth", "easy", "eaves",
    "edged", "edits", "eggs", "eject", "elect", "elk", "elm", "else",
    "emery", "ended", "ensue", "epics", "eras", "erode", "evens", "evils",
    "exam", "exits", "eye", "faced", "fade", "faint", "faker", "famed",
    "fans", "farm", "fated", "fears", "feed", "fern", "ferry", "feud",
    "fib", "fills", "fin", "finch", "fined", "fire", "fish", "fits",
    "fixes", "flaps", "flaw", "fled", "flex", "flips", "flog", "floss",
    "flu", "flung", "foal", "fogs", "folds", "fonts", "fore", "forms",
    "forum", "fowl", "fox", "frame", "freak", "fret", "fries", "frock",
    "frog", "fudge", "fuel", "fume", "fungi", "fury", "fussy", "gaily",
    "gall", "gash", "gates", "geese", "gene", "genus", "giant", "gin",
    "glade", "glean", "glint", "gloss", "glues", "goat", "god", "golds",
    "good", "gore", "gouge", "grabs", "grain", "grape", "grass", "great",
    "grey", "grime", "grist", "grope", "grove", "growl", "grunt", "guild",
    "gull", "guns", "gym", "hacks", "hair", "hall", "ham", "hares",
    "harry", "haste", "hater", "have", "hawks", "hazy", "heap", "heath",
    "heed", "heir", "helps", "hen", "hens", "herb", "hero", "hiked",
    "hill", "hip", "hires", "hive", "hold", "holy", "honed", "honey",
    "hood", "hoops", "hopes", "horse", "hotel", "house", "hub", "huff",
    "hulls", "hums", "hunt", "husk", "icing", "idly", "iii", "impel",
    "incur", "inn", "into", "ire", "iron", "item", "ivy", "jab",
    "jail", "jam", "jars", "jeans", "jelly", "jets", "jog", "joint",
    "jolt", "jugs", "juice", "jumpy", "juror", "keep", "key", "kicks",
    "kinds", "kiss", "kitty", "kiwi", "kneel", "knit", "know", "koala",
    "label", "laces", "lads", "lain", "lake", "lam", "lamb", "lamp",
    "lane", "lank", "lark", "lasts", "laws", "lazed", "leaf", "leans",
    "least", "leek", "leg", "lend", "lest", "licks", "lift", "lilac",
    "lily", "lime", "lined", "links", "lion", "lips", "liter", "lives",
    "lobe", "logic", "lone", "loom", "loot", "lot", "love", "lowly",
    "lucky", "lumpy", "lurch", "lurks", "lyric", "mad", "maid", "main",
    "makes", "mango", "mania", "maple", "march", "mars", "masks", "match",
    "matte", "may", "meal", "meat", "medic", "melon", "mends", "merit",
    "met", "metro", "mid", "milk", "milky", "mind", "mini", "mints",
    "miss", "mitt", "moans", "mocks", "moist", "mole", "month", "moons",
    "moped", "moss", "motor", "mouse", "movie", "muck", "mud", "mug",
    "mule", "mull", "mural", "mush", "mute", "nab", "nails", "nap",
    "near", "need", "nest", "niece", "nines", "nobly", "nook", "noon",
    "norms", "notch", "numb", "nut", "nuts", "oaks", "oats", "odder",
    "odor", "often", "oils", "omega", "one", "onion", "open", "opted",
    "orbit", "otter", "our", "overt", "owl", "oxen", "pack", "pages",
    "paint", "paler", "palm", "panda", "pangs", "par", "park", "pass",
    "path", "patty", "pawn", "pea", "peach", "peals", "pear", "peek",
    "peer", "pen", "pent", "perch", "peril", "pet", "petal", "phony",
    "picky", "pie", "piety", "pig", "pikes", "pilot", "pine", "ping",
    "pints", "pipes", "pits", "pizza", "place", "plans", "plea", "plod",
    "ploy", "plum", "plume", "ply", "poems", "poise", "polar", "polls",
    "pond", "pony", "pooch", "pope", "pores", "poser", "posy", "pours",
    "prank", "prey", "pro", "prong", "proud", "prune", "puff", "pulls",
    "pun", "puny", "pure", "purse", "putt", "quart", "quest", "quilt",
    "quiz", "race", "radar", "rag", "raids", "rain", "raise", "ram",
    "rang", "rants", "rarer", "rated", "rays", "reads", "reap", "reed",
    "reef", "refer", "relay", "repel", "retry", "rhino", "rice", "rich",
    "ridge", "rigs", "rinds", "riots", "risen", "rite", "road", "roast",
    "robin", "robot", "rock", "rode", "role", "romps", "rooms", "root",
    "roped", "rose", "row", "ruddy", "ruins", "rummy", "rungs", "rut",
    "sacks", "sag", "said", "sale", "salt", "salty", "sand", "sandy",
    "sap", "sate", "sauce", "saucy", "saw", "scab", "scamp", "scarf",
    "scorn", "seal", "sect", "seed", "seeds", "seen", "seize", "sends",
    "set", "sewed", "shaky", "shank", "shark", "shave", "sheds", "shelf",
    "shin", "shirk", "shoed", "shop", "shout", "shred", "shuns", "sill",
    "sip", "sirs", "sited", "sixth", "skip", "skull", "sky", "slain",
    "slap", "slay", "sleet", "slide", "slips", "slop", "slots", "slump",
    "sly", "smear", "smock", "snail", "snap", "sneer", "snort", "snow",
    "soapy", "sock", "sofas", "sold", "solve", "sonic", "sop", "sorts",
    "soup", "sour", "spans", "sped", "spice", "spies", "spine", "spits",
    "spoof", "spots", "spurt", "stab", "stall", "star", "stare", "steak",
    "steam", "steel", "stem", "stems", "stew", "stick", "stink", "stoke",
    "stoop", "storm", "story", "stray", "stub", "stuff", "sucks", "sugar",
    "suing", "sulky", "sun", "sunk", "surf", "sushi", "swan", "swap",
    "swear", "swig", "swirl", "sworn", "syrup", "table", "tacky", "taco",
    "tails", "tally", "tames", "tanks", "tapes", "tart", "taxes", "tea",
    "teams", "tech", "teeth", "tempt", "tens", "test", "thank", "theft",
    "thorn", "throw", "thump", "tick", "tidy", "tiger", "till", "times",
    "tin", "tins", "tipsy", "tithe", "toast", "today", "toils", "tomb",
    "toned", "tons", "tooth", "torch", "toss", "tough", "towel", "toyed",
    "trail", "traps", "treat", "trot", "trout", "true", "truss", "tucks",
    "tulip", "tuna", "tunes", "tutor", "twice", "twig", "twins", "tying",
    "ulcer", "undo", "unite", "upend", "urged", "use", "using", "vague",
    "valor", "vans", "vast", "veer", "verb", "vests", "vexes", "vices",
    "views", "vine", "visa", "vital", "vogue", "vowed", "wafer", "wages",
    "waits", "waltz", "ware", "warps", "was", "wasp", "water", "waves",
    "way", "wears", "wedge", "weed", "week", "weird", "welt", "wet",
    "whale", "wharf", "wheat", "when", "whim", "whoa", "why", "widow",
    "wile", "wily", "windy", "wink", "wiper", "wiser", "witch", "wolf",
    "wood", "woos", "works", "worm", "worry", "wove", "wreak", "wrist",
    "wrung", "yam", "yard", "yarns", "year", "yelp", "yokes", "yours",
    "zeal", "zebra",
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
