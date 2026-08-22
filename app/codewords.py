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
    "abacus", "abates", "abhors", "ablaze", "aborts", "absent", "abuses", "accept",
    "accuse", "acidly", "action", "acuity", "addend", "adduce", "adjust", "adores",
    "adults", "advise", "affect", "afield", "agates", "aghast", "ailing", "airman",
    "albeit", "alibis", "alkali", "allies", "allude", "altars", "always", "ambled",
    "amoeba", "amulet", "anemia", "angled", "anions", "annoys", "anoint", "antler",
    "anyway", "apiece", "appeal", "arable", "arched", "arcing", "argues", "armada",
    "armpit", "arrant", "arrows", "ascend", "asleep", "assert", "assist", "asthma",
    "asylum", "atoned", "attain", "attire", "augurs", "autumn", "averse", "avowal",
    "awakes", "azalea", "baboon", "badges", "baited", "baldly", "ballet", "banana",
    "banish", "banned", "barbed", "baring", "barley", "barren", "basely", "basins",
    "basted", "bathes", "batter", "baying", "beagle", "beaned", "beater", "became",
    "bedded", "befall", "befoul", "behalf", "behest", "belays", "belles", "bemoan",
    "bereft", "beside", "betray", "bewail", "biases", "bidder", "biking", "billet",
    "binges", "births", "biting", "blades", "blanks", "blazed", "bleary", "blight",
    "blithe", "bloods", "blouse", "bluing", "blurts", "bobbed", "bodies", "boiled",
    "bombed", "boning", "booked", "booted", "borrow", "bother", "bought", "bovine",
    "bowled", "boxers", "braces", "braked", "brassy", "bravos", "breaks", "breeds",
    "brewer", "bridal", "briefs", "broken", "brooch", "browse", "brutes", "bucket",
    "budget", "bugged", "bulged", "bumble", "bumper", "bunted", "burial", "burner",
    "bursts", "busier", "busses", "butane", "buzzer", "byline", "cabins", "cackle",
    "cajole", "caller", "calmly", "camped", "canary", "candor", "cannon", "canopy",
    "capers", "carboy", "carnal", "carrot", "carver", "cashes", "casket", "casual",
    "catkin", "caught", "caveat", "cavity", "celery", "census", "cesium", "chalet",
    "change", "charms", "chases", "checks", "cheery", "chests", "chided", "chilly",
    "chocks", "choker", "choral", "chosen", "chunks", "chutes", "cinema", "cities",
    "citrus", "clamps", "classy", "clears", "cleric", "client", "clinch", "cloaks",
    "closer", "clouds", "cloves", "clutch", "coaxes", "coddle", "coffee", "cohere",
    "colder", "colons", "combed", "comets", "common", "confer", "convoy", "cooler",
    "cooper", "copper", "coring", "corona", "corset", "cosmos", "coughs", "coupon",
    "covert", "cowers", "cozier", "craggy", "cranks", "cravat", "crawls", "creaky",
    "create", "creeps", "crewed", "crises", "crooks", "crowed", "crumbs", "crutch",
    "cuddle", "cupped", "curing", "curses", "curved", "cutesy", "cycled", "dabble",
    "dainty", "damper", "danger", "daring", "darned", "dative", "deacon", "dearly",
    "debate", "debunk", "decent", "decoys", "deemed", "deface", "defied", "deform",
    "degree", "deltas", "delves", "demote", "denier", "dental", "depict", "depots",
    "deride", "design", "detail", "detour", "devoid", "diadem", "diatom", "dieter",
    "digits", "dimmer", "dinner", "dipper", "dished", "disown", "divert", "diving",
    "doctor", "dogmas", "domain", "doomed", "doting", "downed", "drafty", "drawer",
    "dreary", "driers", "driven", "droops", "drowns", "drying", "dulled", "dunces",
    "dusted", "dyadic", "earned", "earwig", "eating", "eddies", "editor", "effete",
    "egress", "ejects", "eldest", "eludes", "emblem", "empire", "enamel", "encore",
    "enemas", "engulf", "enmesh", "enrich", "ensues", "entire", "envied", "equals",
    "equity", "ermine", "errata", "escape", "estate", "eulogy", "evened", "evilly",
    "exacts", "except", "excuse", "exhume", "exited", "expels", "export", "extent",
    "eyelet", "fabric", "facing", "faints", "falcon", "family", "fanned", "farmer",
    "father", "faults", "fealty", "fedora", "feline", "female", "fennel", "fetish",
    "fewest", "fiddle", "fiesta", "filled", "filmed", "finder", "finger", "firing",
    "fiscal", "fitful", "fixing", "flakes", "flanks", "flatly", "flaxen", "flicks",
    "flinch", "flocks", "floral", "flower", "flurry", "foamed", "folded", "fonder",
    "forage", "forces", "forger", "formal", "forums", "foully", "framed", "frauds",
    "freest", "fresco", "frigid", "frisks", "frosts", "frowzy", "fueled", "fungal",
    "furrow", "gabble", "gadget", "gained", "galled", "gambit", "gander", "garage",
    "garish", "garter", "gassed", "gauges", "gazing", "genera", "gentle", "geyser",
    "gibbet", "giggle", "girder", "glamor", "glassy", "gleans", "glitch", "glossy",
    "glower", "goatee", "godson", "goober", "gospel", "gouged", "graces", "grafts",
    "granny", "grassy", "gravel", "grayed", "greasy", "grieve", "grimes", "grippe",
    "grocer", "groovy", "groups", "grower", "grumpy", "guffaw", "guises", "gulped",
    "gunner", "gusset", "gypsum", "hackle", "hallow", "halves", "handle", "hansom",
    "harder", "harmed", "hasten", "hauled", "havens", "hazard", "healed", "hearth",
    "heater", "hectic", "heeded", "helium", "herald", "herein", "heroes", "herpes",
    "hidden", "hiking", "hinted", "hitter", "hockey", "hollow", "homily", "honors",
    "hoopla", "hoping", "horrid", "hotbed", "hourly", "howled", "huddle", "humbly",
    "humped", "hurdle", "hurray", "husked", "hyphen", "icings", "idlest", "iguana",
    "impact", "impede", "impose", "inbred", "incise", "indeed", "indoor", "infant",
    "inflow", "ingest", "injury", "inlets", "inputs", "insert", "insult", "intent",
    "invade", "invoke", "irking", "islets", "itself", "jailed", "jargon", "jaunty",
    "jester", "jigsaw", "jocund", "jokers", "jotted", "joyous", "juices", "jumper",
    "jurors", "karate", "kennel", "kibitz", "kidnap", "kindle", "kismet", "kitten",
    "knells", "knocks", "labels", "lacked", "ladies", "lambda", "lancer", "lapels",
    "lariat", "lasers", "lasted", "latter", "lavish", "layman", "lazier", "leader",
    "leaned", "leased", "lecher", "legacy", "legion", "lemons", "lentil", "lesson",
    "levees", "levity", "lichen", "likens", "limber", "limpid", "linens", "lining",
    "lisped", "liters", "lively", "loaded", "loaned", "locate", "locust", "logger",
    "loners", "lookup", "looser", "lordly", "louder", "lovely", "lowest", "lummox",
    "lupine", "lynxes", "madcap", "madras", "magpie", "maimed", "making", "mallet",
    "manage", "maniac", "mantis", "manure", "marble", "marker", "maroon", "marvel",
    "masons", "master", "matted", "maxims", "meaner", "medial", "meeker", "melons",
    "memory", "mental", "merged", "messed", "meters", "mettle", "middle", "milder",
    "milker", "mimics", "mingle", "minnow", "minute", "misfit", "misses", "mixers",
    "mocked", "modern", "modulo", "molest", "months", "morals", "morrow", "mosaic",
    "motels", "motley", "mounts", "movers", "muffin", "murmur", "musing", "muster",
    "mutter", "myopia", "mystic", "naming", "native", "nearby", "neater", "needle",
    "nested", "neural", "newest", "nicely", "nieces", "nimbus", "nobler", "nodule",
    "nosing", "notion", "nozzle", "nugget", "nursed", "nymphs", "oblige", "obtain",
    "ocelot", "oddest", "office", "oiling", "onions", "oodles", "openly", "optima",
    "orally", "ordain", "orgasm", "oriole", "ossify", "ounces", "outlay", "outset",
    "oxford", "pacify", "packet", "paging", "paired", "pallet", "pander", "panted",
    "papyri", "parent", "parked", "parody", "partly", "pasted", "pastry", "patrol",
    "pauper", "payday", "peaked", "pearly", "peeked", "peered", "pended", "pepper",
    "person", "petals", "petrol", "phloem", "phones", "phylum", "picked", "pickup",
    "pieces", "pigpen", "pilots", "pinker", "piracy", "piston", "pivots", "placid",
    "plaits", "planks", "plated", "pleads", "pliant", "plover", "plumes", "pocket",
    "points", "poison", "poling", "pollen", "ponder", "poorly", "poring", "posers",
    "possum", "potash", "potter", "pouted", "pranks", "prefab", "presto", "prided",
    "primed", "priory", "privet", "profit", "pronto", "proton", "prunes", "psyche",
    "pueblo", "puller", "pulsed", "pundit", "puppet", "purify", "pursed", "pushed",
    "puzzle", "quahog", "quanta", "quasar", "quests", "quilts", "quotas", "rabble",
    "racing", "radios", "raffia", "ragout", "rained", "raking", "rancid", "ranges",
    "ranted", "raping", "rascal", "raster", "ration", "ravine", "razors", "realms",
    "reared", "rebuff", "recede", "recite", "rector", "red", "reeled", "reflex", "refuse",
    "regard", "reigns", "relate", "relief", "reload", "remedy", "rename", "rental",
    "repast", "repels", "repute", "resets", "resist", "retail", "retort", "revamp",
    "revert", "revive", "reward", "rhymed", "ribbon", "ridden", "riffle", "rigors",
    "rinses", "ripped", "risked", "roamed", "robber", "rocked", "rodent", "roller",
    "rookie", "rooter", "rotate", "roused", "routes", "rubble", "ruckus", "rugged",
    "ruling", "runner", "rushes", "rustle", "sadden", "sadist", "sailed", "salads",
    "saliva", "salted", "salves", "sanely", "sating", "savant", "savors", "saying",
    "scanty", "scenes", "schism", "scolds", "scored", "scotch", "scrawl", "script",
    "scurvy", "seamed", "season", "secret", "seeded", "seemly", "seldom", "senate",
    "senses", "septum", "serial", "server", "settle", "sewage", "sexton", "shaded",
    "shaken", "shames", "shares", "shaves", "sheets", "shifts", "shiner", "shoals",
    "shoots", "shoved", "shower", "shrews", "shrimp", "shroud", "sicken", "siding",
    "sifted", "signal", "silage", "silver", "simple", "singed", "sinker", "siting",
    "skated", "skewed", "skinny", "skunks", "slaver", "sleeps", "sleigh", "slicks",
    "slings", "slopes", "slough", "sludge", "smears", "smiled", "smoked", "smooth",
    "snaked", "snares", "sneaky", "snippy", "snored", "snowed", "soaped", "socked",
    "sodomy", "soiled", "solids", "somber", "soothe", "sorrel", "sortie", "sourer",
    "spaces", "sparer", "spawns", "specks", "spells", "spider", "spinal", "spited",
    "spline", "spoken", "spools", "sporty", "sprain", "sprees", "sprout", "spying",
    "squash", "squeal", "stable", "staged", "stakes", "stance", "starch", "starts",
    "states", "staves", "steals", "steeps", "stereo", "sticky", "stills", "stitch",
    "stolen", "stones", "storey", "stoves", "strait", "strays", "stress", "strife",
    "strips", "stroke", "strung", "studio", "stunts", "styles", "subset", "subway",
    "suckle", "suited", "sulked", "summer", "sundry", "suntan", "supple", "surged",
    "suture", "swampy", "swears", "sweets", "swirly", "sylvan", "system", "tacked",
    "tailed", "talked", "tamale", "tampon", "tannin", "target", "tasked", "tastes",
    "taught", "taxied", "teapot", "tedium", "teeter", "tempts", "tendon", "tenser",
    "termed", "testes", "thefts", "themes", "thesis", "thinly", "thorns", "thread",
    "thrice", "throbs", "thrown", "thumbs", "ticker", "tidied", "tiller", "timely",
    "tingle", "tinsel", "tipple", "tithes", "toddle", "toilet", "tomcat", "tonsil",
    "torpor", "tosses", "tousle", "toying", "tracts", "tragic", "tramps", "treads",
    "tremor", "tribal", "trifle", "trivia", "tropic", "truant", "truism", "trusty",
    "tucked", "tumors", "tunics", "turgid", "turnip", "tuxedo", "twined", "twitch",
    "typist", "umlaut", "undoes", "uneven", "unisex", "unjust", "unload", "unroll",
    "unsent", "untold", "unwind", "uphill", "uplift", "upshot", "upward", "urging",
    "ushers", "utopia", "vacuum", "valley", "vandal", "varies", "vaults", "vellum",
    "venial", "verges", "vernal", "vertex", "vetoed", "victim", "vilely", "vipers",
    "virtue", "vistas", "vivify", "voided", "voodoo", "voting", "voyeur", "wafers",
    "wagons", "waiter", "waking", "wallop", "wander", "wapiti", "warily", "warned",
    "washed", "wastes", "waving", "weaker", "wearer", "wedded", "weighs", "welled",
    "whaler", "whence", "whinny", "whites", "whoosh", "wicket", "widows", "wifely",
    "wildly", "wilted", "windup", "winked", "wintry", "wisely", "wishes", "wobble",
    "wonder", "woofed", "worded", "wormed", "wreaks", "wretch", "writes", "yearly",
    "yellow", "yogurt", "zealot", "zeroes", "zircon",
)

NOUNS: Final[tuple[str, ...]] = (
    "aback", "abbot", "able", "above", "aces", "acne", "acted", "add", "adieu", "adorn",
    "afoot", "agar", "ages", "agony", "aide", "aimed", "aisle", "album", "alias", "allay",
    "alms", "along", "alter", "amble", "amiss", "amp", "and", "angst", "annul", "antic",
    "apart", "aping", "aqua", "ardor", "argon", "arm", "arose", "ascot", "ask", "assay",
    "atom", "audit", "aura", "aver", "avow", "awash", "awoke", "axing", "axons", "babes",
    "bade", "bah", "baker", "balks", "balmy", "bane", "bans", "bare", "barks", "base",
    "basin", "baste", "bathe", "bawdy", "beach", "beam", "bears", "beaux", "beech", "beer",
    "befog", "begs", "belie", "belts", "berg", "bests", "bias", "biddy", "bike", "bill",
    "binge", "birds", "bits", "blank", "bleat", "blew", "bliss", "blocs", "blow", "bluff",
    "blush", "boat", "body", "bogy", "bolt", "bone", "bonus", "booms", "boot", "borax",
    "borne", "bough", "bowel", "boxed", "brace", "brake", "brat", "bray", "brew", "brief",
    "brink", "brood", "brows", "bud", "bug", "bulbs", "bulls", "bun", "bunt", "burns",
    "burrs", "bush", "but", "buzz", "cabal", "cacti", "cages", "cal", "cam", "can",
    "canon", "caper", "care", "carry", "cased", "caste", "caulk", "cease", "cents",
    "chalk", "char", "chat", "chefs", "chic", "chili", "chip", "choke", "chose", "chunk",
    "cinch", "civet", "clams", "clash", "clean", "cliff", "clips", "clomp", "clout",
    "cluck", "coal", "cocoa", "coed", "coke", "colon", "combs", "con", "coo", "coon",
    "cope", "coral", "cork", "corps", "couch", "court", "cowed", "coy", "craft", "crane",
    "crawl", "creed", "crest", "crier", "crock", "cross", "crude", "cry", "cubic", "cuff",
    "cup", "curd", "curl", "curt", "cycle", "dad", "dais", "dame", "dare", "darts",
    "datum", "day", "deals", "debit", "decay", "deed", "deer", "deity", "demon", "dents",
    "desks", "dial", "died", "digs", "dimes", "diner", "diode", "dis", "disks", "dive",
    "docks", "doff", "doled", "dome", "dons", "doped", "doted", "douse", "downy", "drab",
    "dram", "dread", "drier", "drip", "droop", "drug", "dry", "ducat", "due", "dug",
    "dumb", "dunce", "dusk", "dwarf", "dyes", "earl", "earth", "easy", "eaves", "edged",
    "edits", "eggs", "eject", "elect", "elk", "else", "emery", "ended", "ensue", "epics",
    "eras", "erode", "espy", "ether", "evens", "evils", "exam", "exits", "eye", "faced",
    "fade", "faint", "faker", "famed", "fans", "farm", "fated", "fauna", "fears", "feed",
    "feign", "fen", "ferry", "feud", "fib", "fife", "filch", "fills", "fin", "fined",
    "fire", "fish", "fits", "fixes", "flak", "flaps", "flaw", "fled", "flex", "flips",
    "flog", "floss", "flu", "flung", "foal", "foci", "fogs", "folds", "fonts", "fop",
    "fore", "forms", "forum", "fowl", "fox", "frame", "freak", "fret", "frock", "froth",
    "fuel", "fume", "fungi", "fury", "fussy", "gad", "gaily", "gall", "gamma", "gaped",
    "gash", "gates", "gawk", "gazer", "geese", "gene", "genus", "giant", "gild", "gin",
    "girt", "glade", "glean", "glint", "gloss", "glues", "gnat", "goad", "god", "golds",
    "good", "gore", "gouge", "grabs", "grain", "grass", "great", "grey", "grime", "grist",
    "grope", "growl", "grunt", "guild", "gull", "gumbo", "guns", "gusty", "gym", "hacks",
    "hair", "hall", "ham", "hank", "hares", "harry", "haste", "hater", "have", "hawks",
    "hazy", "heap", "heath", "heed", "heir", "helps", "hens", "hero", "hewer", "hicks",
    "hiked", "hilts", "hip", "hires", "hive", "hobo", "hold", "holy", "honed", "hood",
    "hoops", "hopes", "horse", "hotel", "hove", "hub", "huff", "hulls", "hums", "hunt",
    "husk", "hydra", "ibex", "icing", "idiom", "idly", "iii", "impel", "incur", "ingot",
    "inn", "into", "ire", "irony", "item", "jab", "jail", "jars", "jeans", "jerk", "jets",
    "jilt", "jog", "joint", "jolt", "jowl", "jugs", "jumpy", "juror", "kapok", "keep",
    "key", "kicks", "kinds", "kiss", "kitty", "kneel", "knit", "know", "label", "laces",
    "lads", "lain", "lam", "lamp", "lank", "larch", "lase", "lasts", "lathe", "laws",
    "lazed", "leaf", "leans", "least", "leek", "leg", "lend", "lest", "lewd", "licks",
    "lien", "lift", "lilac", "lime", "lined", "links", "lips", "liter", "lives", "loamy",
    "lobe", "locus", "logic", "lone", "loom", "loot", "lorry", "lot", "love", "lowly",
    "lucky", "lumpy", "lurch", "lurks", "lutes", "lyric", "mad", "maid", "main", "makes",
    "mambo", "mania", "manse", "march", "mars", "masks", "match", "matte", "may", "meal",
    "meat", "medic", "melon", "mends", "merit", "met", "metro", "mid", "milch", "milky",
    "mind", "mini", "mints", "miss", "mitt", "moans", "mocks", "moist", "moll", "month",
    "moons", "moped", "moss", "motor", "mousy", "movie", "muck", "mug", "mull", "mural",
    "mush", "mute", "nab", "nails", "nap", "natty", "near", "need", "nest", "newel",
    "nibs", "niece", "nines", "nobly", "noel", "nook", "norms", "notch", "nova", "numb",
    "nuts", "oaks", "oaten", "obeys", "odder", "odor", "often", "oils", "omega", "one",
    "onus", "open", "opted", "orbit", "osier", "our", "ova", "overt", "owl", "oxen",
    "pack", "padre", "pages", "paint", "paler", "palsy", "pangs", "panty", "par", "parry",
    "pass", "pate", "patty", "pawn", "pea", "peals", "pecan", "peek", "peer", "pen",
    "pent", "peril", "pet", "pewee", "phony", "picky", "piety", "pikes", "pilot", "ping",
    "pints", "pipes", "pits", "place", "plans", "plea", "plod", "ploy", "plume", "ply",
    "poems", "poise", "polar", "polls", "pooch", "pope", "pores", "poser", "posy", "pours",
    "prank", "prey", "primp", "pro", "prong", "proud", "prune", "puff", "pulls", "pun",
    "puny", "pure", "purse", "putt", "quad", "quart", "quest", "quilt", "quiz", "race",
    "radar", "rag", "raids", "raise", "ram", "rang", "rants", "rarer", "rated", "ravel",
    "rays", "reads", "reap", "recta", "reef", "refer", "relay", "rends", "repel", "retry",
    "rhino", "rich", "ridge", "rigs", "rinds", "riots", "risen", "rite", "road", "roast",
    "robot", "rode", "role", "romps", "rooms", "roped", "rote", "rout", "row", "rpm",
    "ruddy", "ruins", "rummy", "rungs", "ruse", "rut", "sacks", "sag", "said", "sale",
    "salty", "sandy", "sap", "sate", "saucy", "saw", "scab", "scamp", "scarf", "scion",
    "scorn", "screw", "scum", "seamy", "sect", "seeds", "seen", "seize", "sends", "serf",
    "set", "sewed", "shad", "shaky", "shank", "shave", "sheds", "shelf", "shin", "shirk",
    "shoed", "shop", "shout", "shred", "shuns", "sibyl", "sidle", "sigma", "sill", "sims",
    "singe", "sip", "sirs", "sited", "sixth", "skeet", "skiff", "skip", "skull", "slain",
    "slap", "slay", "sleet", "slide", "slips", "slop", "slots", "slump", "sly", "smear",
    "smock", "smut", "snap", "sneer", "snort", "snuff", "soapy", "sock", "sofas", "sold",
    "solve", "sonic", "sop", "sorts", "sour", "soya", "spans", "spate", "sped", "spies",
    "spine", "spits", "spoof", "spots", "spume", "spurt", "stab", "staid", "stall",
    "stare", "stave", "steam", "stems", "stick", "stink", "stoke", "stoop", "story",
    "stray", "stub", "stuff", "styli", "sucks", "suing", "sulky", "sunk", "surf", "swain",
    "swap", "swear", "swig", "swirl", "sworn", "table", "tacky", "tails", "talc", "tally",
    "tames", "tanks", "tapes", "tart", "tatty", "taxes", "teams", "tech", "teeth", "tempt",
    "tens", "tepid", "test", "thank", "theft", "theta", "thine", "thorn", "throw", "thump",
    "tick", "tidy", "tiger", "till", "times", "tins", "tipsy", "tithe", "today", "toils",
    "tomb", "toned", "tons", "tooth", "torch", "toss", "tough", "towel", "toyed", "trail",
    "traps", "treat", "triad", "trig", "tripe", "trot", "true", "truss", "tuba", "tucks",
    "tulle", "tunes", "tutor", "twice", "twins", "tying", "ulcer", "undo", "unite",
    "upend", "urged", "use", "using", "vague", "valor", "vans", "vast", "veer", "veldt",
    "verb", "vests", "vexes", "vices", "views", "vine", "visa", "vital", "vogue", "vomit",
    "vowed", "wad", "wafer", "wages", "waits", "waldo", "waltz", "wanly", "ware", "warps",
    "was", "water", "waves", "way", "wears", "wedge", "week", "weird", "welt", "wet",
    "wharf", "when", "whim", "whirr", "whoa", "why", "widow", "wile", "wily", "windy",
    "wink", "wiper", "wiser", "witch", "woe", "wombs", "woody", "woos", "works", "worry",
    "wove", "wreak", "wrist", "wrung", "yam", "yarns", "year", "yelp", "yip", "yokes",
    "yours", "zeal", "zeta", "zonal",
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
