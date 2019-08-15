import re, os, sys, pdb
from domain_knowledge import Domain_Knowledge
knowledge_container = Domain_Knowledge()

LOWER = False
DELIM = "￨"
days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
signals = ['next', 'home', 'road', 'host', 'will', 'visit']
out = []
total = 0
discard = 0
discard_words = 0
nums = re.compile('[0-9]+')

contain_other_teams = []
contain_other_cities = []
alias2team = knowledge_container.alias2team

# ------ mask these (unwanted) numbers then check if anymore numbers left ------ #
years = re.compile(' [0-9]{4} - [0-9]{2} ')
months = re.compile('(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d+')
other_stats = re.compile(' [0-9]+ (?:games*|days*|man|men|ties*|lead|teams*|contests) ')
averages = re.compile(' averag[eing]* ')
ordinal = re.compile(' [0-9]+th ')
seed = re.compile(' [0-9]+( -) seed ')
homestead = re.compile(' [0-9] - game homestead')
num_patterns = [years, months, other_stats, averages, ordinal, homestead]

# ------ sentences talking about these topics: discard ------ #
streak = re.compile('(?:win[ing]*|los[ing]*|hot|a|the|\'s|) streak')
seconds = re.compile('[0-9]+ seconds ')  # (?:remain[ing]*|left|on the clock|to (:?play|go)(:? in the game)*)
straight = re.compile('straight (?:games*|seasons*) ')
in_a_row = re.compile('in a row')
per_sth = re.compile(' [0-9]+(?: \S+)* per ')
histories = '|'.join(['game', 'minute', 'contest', 'outing', 'week', 'shot', 'matchup', 'season', 'year', 'meeting'])
last_games_long = re.compile('[0-9]+(?: of)*(?: \S+)* (?:last|previous|first|past) [0-9]+ (?:{})s*'.format(histories))
last_games_short = re.compile('(?:last|previous|first|past) (?:[0-9]+ )*(?:{})s*'.format(histories))
division = re.compile('\S+ Division')
all_start_break = re.compile('the All-Star break')
filter_patterns = [seconds, streak, straight, in_a_row, per_sth, last_games_long, last_games_short, division, all_start_break]

# ---- patterns awaiting to be used of extract team schedules ---- #
will_next = re.compile(' [Nn]ext | previous | will | \'ll ')
on_the_road = re.compile('on the road')
nums = re.compile('[0-9]+')
weekdays = re.compile('|'.join(days))

# ---- aggregation patterns ---- #
key_words = ['combine', 'put together']


def _whats_next(inp):
    tmp = {}
    str2nextrcds = {}
    for rcd in inp.split():
        value, field, rcd_type, ha = rcd.split(DELIM)
        if rcd_type.startswith('TEAM-NEXT'):
            tmp[DELIM.join([rcd_type, ha])] = (value, field)
            str2nextrcds[value] = [rcd]

    upcomings = {
        'HOME': {'NAME': 'N/A', 'CITY': 'N/A', 'DAY': 'N/A'},
        'AWAY': {'NAME': 'N/A', 'CITY': 'N/A', 'DAY': 'N/A'}
    }

    for ha in ['HOME', 'AWAY']:
        for suffix in ['NAME', 'CITY', 'DAY']:
            upcomings[ha][suffix] = tmp[DELIM.join(['TEAM-NEXT_{}'.format(suffix), ha])]
    return upcomings, str2nextrcds


def _contain_number(s):
    return any([x.isdigit() for x in s.strip().split()])


def _talking_about_schecule(this, other_team, upcomings):

    # case 1: for regular seasons, different opponent
    lkt = {w: True for w in this.split()}
    if len(other_team) > 0 and any([i in lkt for i in signals]) and any([i in lkt for i in days]):
        return True

    # case 2: for playoffs, sometimes same opponent
    else:
        days_lkt = dict.fromkeys(days)
        schedule_info = [x for x in set(list(upcomings['HOME'].values()) + list(upcomings['AWAY'].values())) if not x in days_lkt]
        if len(other_team) == 0 and any([i in lkt for i in signals]) and any([i in lkt for i in schedule_info]):
            return True

    return False

def _build_buffer(buffer, this, str2rcds):
    buffer['text'] = this
    for idx, tk in enumerate(this.split()):
        if tk in str2rcds:
            buffer['plan'].append(str2rcds[tk][0])
            buffer['pointer'].append(idx)
    return buffer


def dont_extract_this_sent(sentences, cnt, buffer, inp, allstr2rcds, table, city2team, alias2team, team_vocab, city_vocab):

    # only allow one sentence in the buffer
    if buffer['text'] is not None:
        return buffer, 'go_check_content_plan'

    this = sentences[cnt]
    this_players = [x for x in this.split() if x in table['Players']]
    this_teams = [x for x in this.split() if x in table['Teams'] or x in city2team or x in alias2team]

    # discard sentences with unwanted topics, see above
    if any([re.search(x, this) is not None for x in filter_patterns]):
        buffer = {'plan': [], 'text': None, 'pointer': []}
        return buffer, 'skip'

    # mask out number patterns not interested in
    for p in num_patterns:
        this_masked = re.sub(p, ' dummystring ', this)

    oneteam = re.compile('(?:{}) \( [0-9]+ - [0-9]+ \)'.format('|'.join(this_teams)))
    if len(re.findall(oneteam, this_masked)) == 1:
        this_masked = re.sub(oneteam, ' dummystring ', this_masked)

    upcomings, str2nextrcds = _whats_next(inp)

    # no-number sentences
    if not _contain_number(this_masked):
        # case 1: a general statement on a group of players, followed by their individual performances
        next = sentences[cnt + 1] if cnt + 1 < len(sentences) else None
        if next is not None:
            next_players = [x for x in next.split() if x in table['Players']]

            buffer = _build_buffer(buffer, this, allstr2rcds)

            if len(this_players) > 0 and any([x in next_players for x in this_players]):
                cat = 'player'
            elif next.startswith('He') or next.startswith('They'):
                cat = 'player-coref'
            elif len(this_teams) > 0 and next.startswith('They'):
                cat = 'team-coref'
            else:
                buffer = {'plan': [], 'text': None, 'pointer': []}
                cat = 'skip'

        else:
            # case 2: team schedule
            other_team = []
            for tk in this.split():
                # resolve team alias
                if tk in alias2team:
                    tk = alias2team[tk]
                if len(other_team)==0 and tk in team_vocab and not tk in table['Teams']:
                    other_team.append(tk)
                    break
                if len(other_team)==0 and tk in city_vocab and not tk in city2team:
                    other_team.append(tk)
                    break

            if _talking_about_schecule(this, other_team, upcomings):
                buffer = _build_buffer(buffer, this, str2nextrcds)
                cat = 'schedule'
            else:
                cat = 'skip'

    else:
        # case 3: combined performance statistics, hard to capture, left to content plan to decide
        cat = 'go_check_content_plan'

    return buffer, cat


