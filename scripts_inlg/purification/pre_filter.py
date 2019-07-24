"""
    This script discards about 12% (#words)
"""

import re, io, copy, os, sys, argparse, pdb
from tqdm import tqdm
from collections import Counter, OrderedDict
from pprint import pprint
from domain_knowledge import Domain_Knowledge
knowledge_container = Domain_Knowledge()

LOWER = False
DELIM = "￨"

parser = argparse.ArgumentParser(description='clean')
parser.add_argument('--dir', type=str, default='../new_dataset/new_clean/',
                    help='directory of src/tgt_train/valid/test.txt files')
parser.add_argument('--dataset', type=str, required=True, help='train, valid test')
args = parser.parse_args()
DATASET = args.dataset

input_files = [
    "src_%s.norm.tk.txt" % DATASET,
    "tgt_%s.norm.tk.txt" % DATASET,
    "tgt_%s.norm.mwe.txt" % DATASET

]

fin_src_tk, fin_tgt_tk, fin_tgt_mwe = [os.path.join(args.dir, "{}/{}".format(DATASET, f)) for f in input_files]

output_files = [
    "tgt_%s.norm.filter.tk.txt" % DATASET,
    "tgt_%s.norm.filter.mwe.txt" % DATASET
]
# out_dir = "outputs/{}".format(DATASET)
fout_tgt_tk, fout_tgt_mwe = [os.path.join(args.dir, "{}/{}".format(DATASET, f)) for f in output_files]

out = []
total = 0
discard = 0
discard_words = 0

# ----------------------------------------------- #
# --- Filtering sentences without any numbers --- #
# ----------------------------------------------- #
# NOTE: constraint relaxed to include inference and aggregation types

nums = re.compile('[0-9]+')
temp_dir = os.path.join(args.dir, "{}/temp".format(DATASET))
os.makedirs(temp_dir, exist_ok=True)
tmpf = os.path.join(temp_dir, "noNumbers.txt")

'''
with io.open(fin_tgt_mwe, 'r', encoding='utf-8') as fin, io.open(tmpf, 'w+', encoding='utf-8') as fout:
    dataset = fin.read()
    dataset = dataset.strip().split('\n')
    for paragraph in dataset:
        remaining = []
        sents = [x.strip() for x in paragraph.split(' . ')]
        for s in sents:
            total += 1
            if not re.search(nums, s):
                out.append(s)
                continue
            remaining.append(s)
        remaining = ' . '.join(remaining)
        fout.write("{}\n".format(remaining))
#'''

# --------------------------------------------------------------------- #
# --- Filtering sentences talking about facts regarding other teams --- #
# --------------------------------------------------------------------- #

contain_other_teams = []
contain_other_cities = []
alias2team = knowledge_container.alias2team

days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
signals = ['next', 'home', 'road', 'host', 'will', 'visit']# + days

with io.open(fin_src_tk, 'r', encoding='utf-8') as fin_src, \
        io.open(tmpf, 'r', encoding='utf-8') as fin_tgt, \
        io.open("{}.noOtherTeams.txt".format(tmpf[:-4]), 'w+', encoding='utf-8') as fout:

    targets = fin_tgt.read()
    targets = targets.strip().split('\n')

    inputs = fin_src.read()
    inputs = inputs.strip().split('\n')

    if LOWER:
        targets = [x.lower() for x in targets]
        inputs = [x.lower() for x in inputs]

    team_names = []
    city_names = []
    for sample in inputs:
        for rcd in sample.split():
            a, b, c, d = rcd.strip().split(DELIM)
            if 'TEAM' in c:
                team_names.append(b)
            if c == 'TEAM-CITY':
                city_names.append(a)
    team_vocab = Counter(team_names)
    city_vocab = Counter(city_names)

    assert len(inputs) == len(targets)
    for inp, para in tqdm(zip(inputs, targets)):
        remaining = []

        # ------ get what this summary paragraph is taking about: team + city ------ #
        thisteams = {}
        thiscities = {}
        thisinputs = inp.split()
        thisinputs.reverse()
        for rcd in thisinputs:
            a, b, c, d = rcd.strip().split(DELIM)
            if 'TEAM' in c:
                if not b in thisteams:
                    thisteams[b] = True
            if c == 'TEAM-CITY':
                if not b in thiscities:
                    thiscities[a] = True
            if len(thisteams.items()) == 2 and len(thiscities) == 2:
                break

        # ------ filter out sentences talking about team/city other than this pair ------ #
        sents = [x.strip() for x in para.split(' . ')]
        for s in sents:
            total += 1
            flag = False
            # check every single word
            for tk in s.split():
                # resolve team alias
                if tk in alias2team:
                    tk = alias2team[tk]
                if not flag and tk in team_vocab and not tk in thisteams:
                    contain_other_teams.append(s)
                    flag = True
                if not flag and tk in city_vocab and not tk in thiscities:
                    contain_other_cities.append(s)
                    flag = True
                if flag:
                    check_sigs = [i in s for i in signals]
                    if any(check_sigs):
                        # print(s)
                        try:
                            contain_other_teams.pop()
                        except:
                            pass
                        try:
                            contain_other_cities.pop()
                        except:
                            pass
                        # pdb.set_trace()
                        flag = False
                    break
            if not flag:
                remaining.append(s)
        remaining = ' . '.join(remaining)
        fout.write("{}\n".format(remaining))

l1 = len(contain_other_teams)
print(contain_other_teams)
words = sum([len(x.split()) for x in contain_other_teams])
print("{} sentences with {} words out of {} sentences are discarded".format(l1, words, total))
print("Some discarded sentences:")
print(contain_other_teams[-10:])
l2 = len(contain_other_cities)
words = sum([len(x.split()) for x in contain_other_cities])
print(contain_other_cities)
print("{} sentences with {} words out of {} sentences are discarded".format(l2, words, total))
print("Some discarded sentences:")
print(contain_other_cities[-10:])
print("{} + {} = {} sentences are discarded".format(l1, l2, l1 + l2))

discard += l1+l2
discard_words += words

# ----------------------------------- #
# --- Remaining bulk of filtering --- #
# ----------------------------------- #

def get_player_name_one(sample):
    names = []
    records = sample.strip().split()
    for rcd in records:
        _, name, _, _ = rcd.strip().split(DELIM)
        names.append(name)
    all_names = list(set(names))
    try:
        all_names.remove('N/A')
    except:
        pass

    return all_names


def contain_number(s):
    return any([x.isdigit() for x in s.strip().split()])


# ------ mask these (unwanted) numbers then check if anymore left: no, discard ------ #
years = re.compile(' [0-9]{4} - [0-9]{2} ')
months = re.compile('(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d+')
other_stats = re.compile(' [0-9]+ (?:games*|days*|man|men|ties*|lead|teams*|contests) ')
averages = re.compile(' averag[eing]* [0-9]+ ')
per_sth = re.compile(' [0-9]+(?: \S+)* per ')
ordinal = re.compile(' [0-9]+th ')
seed = re.compile(' [0-9]+( -) seed ')
homestead = re.compile(' [0-9] - game homestead')

num_patterns = [years, months, other_stats, averages, per_sth, ordinal, homestead]

# ------ sentences talking about these topics: discard ------ #
streak = re.compile('(?:win[ing]*|los[ing]*|hot|a|the|\'s|) streak')
seconds = re.compile('[0-9]+ seconds ')  # (?:remain[ing]*|left|on the clock|to (:?play|go)(:? in the game)*)
will_next = re.compile(' [Nn]ext | previous | will | \'ll ')
on_the_road = re.compile('on the road')
straight = re.compile('straight (?:games*|seasons*) ')
histories = '|'.join(['game', 'minute', 'contest', 'outing', 'week', 'shot', 'matchup', 'season', 'year', 'meeting'])
last_games = re.compile('[0-9]+(?: of)*(?: \S+)* (?:last|previous|first|past) [0-9]+ (?:{})s*'.format(histories))

division = re.compile('\S+ Division')
filter_patterns = [seconds, streak, straight, last_games, division]

nums = re.compile('[0-9]+')
weekdays = re.compile('|'.join(days))

out = []
no_nums = []
with io.open(fin_src_tk, 'r', encoding='utf-8') as fin_src, \
        io.open("{}.noOtherTeams.txt".format(tmpf[:-4]), 'r', encoding='utf-8') as fin_tgt, \
        io.open(fout_tgt_tk, 'w+', encoding='utf-8') as fout_tk, \
        io.open(fout_tgt_mwe, 'w+', encoding='utf-8') as fout_mwe:

    targets = fin_tgt.read()
    targets = targets.strip().split('\n')
    inputs = fin_src.read()
    inputs = inputs.strip().split('\n')

    if LOWER:
        targets = [x.lower() for x in targets]
        inputs = [x.lower() for x in inputs]

    for inp, para in tqdm(zip(inputs, targets)):

        player_names = get_player_name_one(inp)
        thisgameplayers = dict.fromkeys(player_names, True)

        remaining = []
        thisteams = {}
        thiscities = {}
        thisinputs = inp.split()
        thisinputs.reverse()
        for rcd in thisinputs:
            a, b, c, d = rcd.strip().split(DELIM)
            if 'TEAM' in c:
                if not b in thisteams:
                    thisteams[b] = True
            if c == 'TEAM-CITY':
                if not b in thiscities:
                    thiscities[a] = True
            if len(thisteams.items()) == 2 and len(thiscities) == 2:
                break

        thisgame = list(thisteams.keys()) + list(thiscities.keys())
        sents = [x.strip() for x in para.split(' . ') if len(x.strip()) > 0]
        oneteam = re.compile('(?:{}) \( [0-9]+ - [0-9]+ \)'.format('|'.join(thisgame)))

        # do not filter the 1st sentence
        remaining.append(sents[0])

        # loop through
        day_of_week = re.findall(weekdays, sents[0])
        for idx, s in enumerate(sents[1:]):
            temp = copy.deepcopy(s)
            if len(re.findall(oneteam, temp)) == 1:
                temp = re.sub(oneteam, ' dummystring ', temp)
                # after filtering out team stats, if no other number left, this sentence is talking about some fact of team not available from table
                if not contain_number(temp):
                    out.append(s)
                    continue

            # discard sentences with unwanted topics, see above
            tofilter = [re.search(x, temp) is not None for x in filter_patterns]
            if any(tofilter):
                out.append(s)
                continue

            # mask out number patterns not interested in
            for p in num_patterns:
                temp = re.sub(p, ' dummystring ', temp)

            # discard if no numbers in sentence after masking out unwanted ones
            if not contain_number(temp):
                no_nums.append(s)
                continue

            # if we know which day_of_week this game was played, discard any other sentences mentioning other days of week
            if len(day_of_week) > 0:
                thisday = day_of_week[0]
                otherdays = [x for x in days if x != thisday]
                tmp_pattern = re.compile('|'.join(otherdays))
                if re.search(tmp_pattern, temp):
                    out.append(s)
                    continue

            remaining.append(s)

        remaining = ' . '.join([x.strip() for x in remaining if len(x.strip()) > 0])
        remaining = remaining.replace('..', '.')
        if remaining.endswith('.'):
            remaining = remaining[:-1].strip()
        fout_mwe.write("{} .\n".format(remaining))
        remaining = ' '.join(remaining.split('_'))
        fout_tk.write("{} .\n".format(remaining))

for i in no_nums: print("{}\n".format(i))
print(len(no_nums))
words = sum([len(x.split()) for x in out])
print("{} sentences with {} words out of {} sentences are discarded".format(len(out), words, total))
print("Some discarded sentences:")
print(out[-10:])
discard += len(out)
discard_words += words
print("[TOTAl] {} sentences with {} words out of {} sentences are discarded".format(discard, discard_words, total))


