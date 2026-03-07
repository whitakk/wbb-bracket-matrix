from .collegesportsmadness import parse_college_sports_madness
from .espn import parse_espn
from .herhoopstats import parse_her_hoop_stats

PARSERS = {
    "herhoopstats": parse_her_hoop_stats,
    "espn": parse_espn,
    "collegesportsmadness": parse_college_sports_madness,
}
