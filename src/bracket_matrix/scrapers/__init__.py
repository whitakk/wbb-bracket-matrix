from .cbssports import parse_cbssports
from .collegesportsmadness import parse_college_sports_madness
from .espn import parse_espn
from .herhoopstats import parse_her_hoop_stats
from .ncaa import parse_ncaa
from .theix import parse_the_ix
from .theathletic import parse_the_athletic
from .usatoday import parse_usatoday

PARSERS = {
    "herhoopstats": parse_her_hoop_stats,
    "espn": parse_espn,
    "collegesportsmadness": parse_college_sports_madness,
    "theix": parse_the_ix,
    "theathletic": parse_the_athletic,
    "cbssports": parse_cbssports,
    "usatoday": parse_usatoday,
    "ncaa": parse_ncaa,
}
