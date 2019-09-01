"""
Taking care of extra line score items:
(1) already captured by rules
['TEAM-BLK', 'TEAM-DREB', 'TEAM-FG3A', 'TEAM-FG3M', 'TEAM-FGA', 'TEAM-FGM', 'TEAM-FTA', 'TEAM-FTM', 'TEAM-OREB', 'TEAM-STL']
(2) captured by PTS:
['TEAM-PTS_SUM-BENCH', 'TEAM-PTS_SUM-START']
(3) added
['TEAM-PTS_HALF-FIRST', 'TEAM-PTS_HALF-SECOND', 'TEAM-PTS_QTR-1to3', 'TEAM-PTS_QTR-2to4']
(4) DONE:
    'TEAM-PTS_HALF_DIFF-FIRST', 'TEAM-PTS_HALF_DIFF-FIRST',
    'TEAM-PTS_QTR_DIFF-FIRST', 'TEAM-PTS_QTR_DIFF-SECOND', 'TEAM-PTS_QTR_DIFF-THIRD', 'TEAM-PTS_QTR_DIFF-FOURTH',
    'TEAM-PTS_TOTAL_DIFF'
"""
# [optional] align max/min sentence with records
# [optional] "a pair of \d+ - point effort/talli": include two records
# [done] fix home|team-next-ha bug
# TODO: first|second|third|fourth quarter, first|seond half
# grep -o -P "(first|second|third|fourth) (quarter|half)" tgt_train.norm.mwe.trim.txt | wc -l : 3252 in train

import re, io, copy, os, sys, argparse, json, pdb, jsonlines, shutil
from tqdm import tqdm
from pprint import pprint
from collections import Counter, OrderedDict
sys.path.insert(0, os.path.abspath('../purification'))
print(sys.path)
from domain_knowledge import Domain_Knowledge
knowledge_container = Domain_Knowledge()
from filter import dont_extract_this_sent

LOWER = False
DELIM = "￨"
UNK = 0
NA = 'N/A'
PAD_WORD = '<blank>'
UNK_WORD = '<unk>'
BOS_WORD = '<s>'
EOS_WORD = '</s>'
MIN_PLAN=10
MAX_PLAN=80
MIN_SUMM=50
MAX_SUMM=350

# -------------------------------------------------------------------------------------------------------------------- #
# ---------------------------------------------- very important patterns --------------------------------------------- #
# -------------------------------------------------------------------------------------------------------------------- #

# a long pattern with 2-6 numbers
pattern1 = re.compile("\( (?:\d+ - \d+ FG)?(?: (?:,|\.) \d+ - \d+ 3PT)?(?: (?:,|\.) \d+ - \d+ FT)? \)")

# patterns with 1 number
pattern2 = re.compile("assist(?:ed)? on \d+")
# the + field, three_point, free, charity, floor; behind/beyond the arc/three; deep/distance/long range;
pattern3 = re.compile("\d+ percent from the \S+")

# patterns with 2 numbers
pattern4 = re.compile("\d+ (?:- )?(?:of|for|-) (?:- )?(?:\S+ )?\d+ (?:shooting )?from (?:the )?\S+")
pattern5 = re.compile("\d+ (?:- )?(?:of|for) (?:- )?(?:\S+ )?\d+ \S+")
pattern6 = re.compile("\( \d+ - \d+ \)")
pattern7 = re.compile("\d+ - \d+")

count_missing = dict.fromkeys(list(range(1, 43)), 0)

word2record = {
    8: ('board', 'REB'),
    9: ('assist', 'AST'),
    10: ('dime', 'AST'),
    11: ('minute', 'MIN'),
    12: ('percent', 'PCT'),
    13: ('steal', 'STL'),
    14: ('block', 'BLK'),
    15: ('turnover', 'TOV'),
    16: ('three_pointer', 'FG3'),
    17: ('three_point', 'FG3'),
    18: ('three', 'FG3'),
    19: ('3PT', 'FG3'),
    20: ('attempt', 'ATMP'),  # not used
    21: ('free_throw', 'FT'),
    22: ('shot', 'FG'),
    23: ('offensive', 'OREB'),
    24: ('offensively', 'OREB'),
    25: ('made', 'FG'),
    26: ('point', ['PTS', 'DIFF']),
    27: ('rebound', 'REB'),
}
word2record = OrderedDict(word2record)

post_donts = {
    28: ('quarter', None),
    29: ('straight', None),
    30: ('starter', None),
    31: ('lead', None),
    32: ('team', None),
    33: ('content', None),
    34: ('run', None),
    35: ('tie', None),
    36: ('game', None),
    37: ('player', None),
}
post_donts = OrderedDict(post_donts)

pre_donts = {
    38: ('combined? for(?: \S+)? \d+', None),
    39: ('averag\S+(?: \S+)? \d+', None),
    40: ('\d{4} - \d{2,4}', None),
    41: ('(?:first|last) \d+ minutes?', None),
    42: ('\d+ minutes? (?:left|remaining)', None),
}

pre_donts = OrderedDict(pre_donts)

suffix2field = dict.fromkeys(['field', 'floor'])
suffix2three = dict.fromkeys(['three_point', 'beyond', 'behind', 'long', 'deep', 'downtown', '3', 'distance'])
suffix2foul = dict.fromkeys(['free_throw', 'charity', 'line', 'foul', 'stripe'])


# -------------------------------------------------------------------------------------------------------------------- #
# ---------------------------------------- identify patterns to be processed ----------------------------------------- #
# -------------------------------------------------------------------------------------------------------------------- #

def mark_records(sent):
    x = copy.deepcopy(sent)
    i = 1

    for idx, (k, v) in pre_donts.items():
        p = re.compile(k)
        delim = "#DELIM{}#".format(idx)
        for f in re.findall(p, x):
            rep = "{}{}{}".format(delim, delim.join(f.split()), delim)
            x = x.replace(f, rep)

    for p in [pattern1, pattern2, pattern3, pattern4, pattern5, pattern6, pattern7]:
        delim = "#DELIM{}#".format(i)
        i += 1
        for f in re.findall(p, x):
            rep = "{}{}{}".format(delim, delim.join(f.split()), delim)
            x = x.replace(f, rep)

    for idx, (k, v) in (list(word2record.items()) + list(post_donts.items())):
        p = re.compile("\d+ (?:- |team )*{}(?:s|ed)*".format(k))
        delim = "#DELIM{}#".format(idx)
        for f in re.findall(p, x):
            rep = "{}{}{}".format(delim, delim.join(f.split()), delim)
            x = x.replace(f, rep)

    return x


# -------------------------------------------------------------------------------------------------------------------- #
# ------------------------------------------ extract content plan from mwe ------------------------------------------- #
# -------------------------------------------------------------------------------------------------------------------- #

def _get_record(value, num2rcds, priority):
    candidates = num2rcds.get(value, None)
    if candidates is None:
        # print("num2rcds = {}".format(num2rcds))
        # print("*** WARNING *** value is not in num2rcds {}".format(value))
        if len(priority) > 1:
            return [], False
        else:
            return None, False

    candidates = sorted(candidates, key=lambda x: len(x.split(DELIM)[2]))
    assert len(priority) > 0
    if len(candidates) == 1:
        check = False
        for p in priority:
            if p in candidates[0].split(DELIM)[2]:
                check = True
                break
                # if not check:
                # print("priority: {}".format(priority))
                # print("num2rcds: {}".format(num2rcds))
                # print("*** WARNING *** candidates {} is not desired : {}".format(candidates, priority))

        if len(priority) > 1:
            return candidates, check
        else:
            return candidates[0], check
    else:
        results = []
        check = False
        for p in priority:
            for c in candidates:
                if p in c.split(DELIM)[2]:
                    results.append(c)
                    check = True
        if check:
            if len(priority) > 1:
                return results, True
            else:
                return results[0], True
        else:
            # print("*** WARNING *** candidates {} is not desired : {}".format(value, priority))
            if len(priority) > 1:
                return [], False
            else:
                return None, False


def retrieve_record(value, num2rcds, priority):
    candidate, check = _get_record(value, num2rcds, priority)

    # discard found candidates if it's not the desired rcd_type when priority list contains only 1 unambiguous rcd_type
    # NOTE: many numbers, like percentage are rounded, so the correct number may be +-1
        # others are mistakes incidentally captured and corrected
    if len(priority) == 1 and not check:
        for v in [value - 1, value + 1]:
            # print('searching {} for value = {}'.format(v, value))
            candidate, check = _get_record(v, num2rcds, priority)
            if candidate is not None and check:
                value = v
                break
    return candidate, value


def get_records(phrase, num2rcds, the_other_team_records):
    """
    :param phrase: marked mwe to of one type of pattern
    :param num2rcds: lookup
    :param the_other_team_records: sometimes a sentence compares to the other team without explicitly mentioning it
    :return: content plan, corrected phrase, locations of the numbers
    """

    # print(phrase)
    p = re.compile("#DELIM(\d+)#")
    temp = re.findall(p, phrase)
    pattern_num = int(temp[0])
    try:
        assert all([int(x) == pattern_num for x in temp])
    except:
        print("{} is misformatted".format(phrase))
        sys.exit(0)
    delim = "#DELIM{}#".format(pattern_num)
    tokens = [x for x in phrase.split(delim) if len(x) > 0]
    numbers_are_at = [i for x, i in zip(tokens, range(len(tokens))) if x.isdigit()]
    # original_phrase = ' '.join(tokens)
    numbers = [int(x) for x in tokens if x.isdigit()]
    # print("numbers = {}".format(numbers))
    # print("pattern_num = {}".format(pattern_num))

    result = []
    if pattern_num == 1:
        true_numbers_are_at = []
        tmp = re.compile("\( (?:\d+ - \d+ (FG))?(?: (?:,|\.) \d+ - \d+ (3PT))?(?: (?:,|\.) \d+ - \d+ (FT))? \)")
        suffix = [x for x in re.findall(tmp, ' '.join(phrase.split(delim)).strip())[0] if len(x) > 0]

        # fix typos
        if len(suffix) == 3:
            words_are_at = [i for x, i in zip(tokens, range(len(tokens))) if not x.isdigit()]
            suffix_temp = copy.deepcopy(suffix)
            if not suffix_temp[0] == 'FG':
                suffix[0] = 'FG'
                tokens[words_are_at[0]] = 'FG'
            if not suffix_temp[1] == '3PT':
                suffix[1] = '3PT'
                tokens[words_are_at[1]] = '3PT'
            if not suffix_temp[2] == 'FT':
                suffix[2] = 'FT'
                tokens[words_are_at[2]] = 'FT'

        i = 0
        for s in suffix:
            if s == 'FG':
                fgm, fga = numbers[i], numbers[i + 1]
                cp1, num1 = retrieve_record(fgm, num2rcds, priority=['FGM'])
                cp2, num2 = retrieve_record(fga, num2rcds, priority=['FGA'])
            elif s == '3PT':
                fg3m, fg3a = numbers[i], numbers[i + 1]
                cp1, num1 = retrieve_record(fg3m, num2rcds, priority=['FG3M'])
                cp2, num2 = retrieve_record(fg3a, num2rcds, priority=['FG3A'])
            elif s == 'FT':
                ftm, fta = numbers[i], numbers[i + 1]
                cp1, num1 = retrieve_record(ftm, num2rcds, priority=['FTM'])
                cp2, num2 = retrieve_record(fta, num2rcds, priority=['FTA'])
            else:
                print("*** WARNING *** other pattern found {}".format(phrase))
                print("phrase = {}".format(phrase))
                print("s = {}".format(s))
                print("suffix = {}".format(suffix))
                sys.exit(0)
            if cp1 is None or cp2 is None:
                pass
            # print("*** WARNING *** content not found for phrase {}".format(phrase))
            else:
                if cp1.split(DELIM)[-2][:2] == cp2.split(DELIM)[-2][:2]:
                    true_numbers_are_at.extend(numbers_are_at[i:i + 1 + 1])
                    tokens[numbers_are_at[i]] = str(num1)
                    tokens[numbers_are_at[i + 1]] = str(num2)
                    result.extend([cp1, cp2])
                else:
                    pass
                    # print("*** WARNING *** content not found for phrase {}".format(phrase))
            i += 2
        numbers_are_at = true_numbers_are_at

    elif pattern_num == 2:
        cp, num = retrieve_record(numbers[0], num2rcds, priority=['AST'])
        if cp is not None:
            tokens[-1] = str(num)
            result.append(cp)

    elif pattern_num == 3:
        # the + field, three_point, free, charity, floor; behind/beyond the arc/three; deep/distance/long range;
        tmp = re.compile('\d+ percent from (\S+) (\S+)')
        suf_1, suf_2 = re.findall(tmp, ' '.join(phrase.split(delim)).strip())[0]

        if suf_2 == '3':
            suf_2 = 'three_point'
            numbers_are_at.pop(-1)

        if suf_1 == 'the':
            if suf_2 in ['field', 'floor']:
                priority = ['FG_PCT']
            elif suf_2 == 'three_point':
                priority = ['FG3_PCT']
            elif suf_2 in ['free', 'charity']:
                priority = ['FT_PCT']
            else:
                priority = ['PCT']
        else:
            if suf_1 in ['behind', 'beyond', 'deep', 'distance', 'long']:
                priority = ['FG3_PCT']
            else:
                priority = ['PCT']
        cp, num = retrieve_record(numbers[0], num2rcds, priority=priority)
        if cp is not None:
            tokens[0] = str(num)
            result.append(cp)

    elif 4 <= pattern_num <= 7:
        if len(numbers) == 2:
            num1, num2 = numbers
        else:
            if numbers[-1] == 3:
                num1, num2, _ = numbers
                numbers_are_at.pop(-1)
            else:
                raise ValueError("*** WARNING *** phrase misformatted {}".format(phrase))

        if pattern_num == 4:
            tmp = re.compile("\d+ (?:- )?(?:of|for|-) (?:- )?(?:\S+ )?\d+ (?:shooting )?from (?:the )?(\S+)")
            suffix = re.findall(tmp, ' '.join(phrase.split(delim)).strip())[0]
            # print('suffix = {}'.format(suffix))
            if suffix in suffix2field or suffix in suffix2three or suffix in suffix2foul:
                if suffix in suffix2field:
                    p1 = ['FGM']
                    p2 = ['FGA']
                elif suffix in suffix2three:
                    p1 = ['FG3M']
                    p2 = ['FG3A']
                elif suffix in suffix2foul:
                    p1 = ['FTM']
                    p2 = ['FTA']
                cp1, num1 = retrieve_record(num1, num2rcds, priority=p1)
                cp2, num2 = retrieve_record(num2, num2rcds, priority=p2)
            else:
                p1 = ['FG3M', 'FGM', 'FTM']
                p2 = ['FG3A', 'FGA', 'FTA']
                temp1, num1 = retrieve_record(num1, num2rcds, priority=p1)
                temp2, num2 = retrieve_record(num2, num2rcds, priority=p2)
                # print("pattern 4 temp1 = {}".format(temp1))
                # print("pattern 4 temp2 = {}".format(temp2))
                cp1, cp2 = None, None
                for x in temp1:
                    for y in temp2:
                        if x.split(DELIM)[2][:-1] == y.split(DELIM)[2][:-1]:
                            cp1 = x
                            cp2 = y
                            break

        elif pattern_num == 5:
            tmp = re.compile("\d+ (?:- )?(?:of|for) (?:- )?(?:\S+ )?\d+ (\S+)")
            suffix = re.findall(tmp, ' '.join(phrase.split(delim)).strip())[0]
            if suffix.startswith('sho'):  # shot/shooting
                p1 = ['FGM']
                p2 = ['FGA']
                cp1, num1 = retrieve_record(num1, num2rcds, priority=p1)
                cp2, num2 = retrieve_record(num2, num2rcds, priority=p2)
            else:
                p1 = ['FG3M', 'FGM', 'FTM']
                p2 = ['FG3A', 'FGA', 'FTA']
                temp1, num1 = retrieve_record(num1, num2rcds, priority=p1)
                temp2, num2 = retrieve_record(num2, num2rcds, priority=p2)
                # print("pattern 6 temp1 = {}".format(temp1))
                # print("pattern 6 temp2 = {}".format(temp2))
                cp1, cp2 = None, None
                for x in temp1:
                    for y in temp2:
                        if x.split(DELIM)[2][:-1] == y.split(DELIM)[2][:-1]:
                            cp1 = x
                            cp2 = y
                            break

        elif pattern_num == 6:
            # print('num2rcds = {}'.format(num2rcds))
            # print('the_other_team_records = {}'.format(the_other_team_records))
            cp1, num1 = retrieve_record(num1, num2rcds, priority=['TEAM-WINS'])
            cp2, num2 = retrieve_record(num2, num2rcds, priority=['TEAM-LOSSES'])
            if cp1 is None or cp2 is None:
                cp1, num1 = retrieve_record(num1, num2rcds, priority=['TEAM-LOSSES'])
                cp2, num2 = retrieve_record(num2, num2rcds, priority=['TEAM-WINS'])
                if cp1 is None or cp2 is None:
                    # if len(priority) > 1, cp1 and cp2 are lists
                    temp1, num1 = retrieve_record(num1, num2rcds, priority=['FG3M', 'FGM', 'FTM', 'REB',
                                                                            'PTS_HALF-', 'PTS_QTR-'])
                    temp2, num2 = retrieve_record(num2, num2rcds, priority=['FG3A', 'FGA', 'FTA', 'REB',
                                                                            'PTS_HALF-', 'PTS_QTR-'])
                    # print("pattern 6 temp1 = {}".format(temp1))
                    # print("pattern 6 temp2 = {}".format(temp2))

                    cp1, cp2 = None, None
                    for x in temp1:
                        for y in temp2:
                            if x.split(DELIM)[2][:-1] == y.split(DELIM)[2][:-1]:
                                cp1 = x
                                cp2 = y
                                break

        elif pattern_num == 7:
            # print('num2rcds = {}'.format(num2rcds))
            # print('the_other_team_records = {}'.format(the_other_team_records))
            if the_other_team_records is not None:
                cp1, num1 = retrieve_record(num1, num2rcds, priority=['TEAM-PTS'])
                cp2, num2 = retrieve_record(num2, the_other_team_records, priority=['TEAM-PTS'])
                if cp1 is None or cp2 is None:
                    cp1, num1 = retrieve_record(num1, the_other_team_records, priority=['TEAM-PTS'])
                    cp2, num2 = retrieve_record(num2, num2rcds, priority=['TEAM-PTS'])

                if cp1 is None or cp2 is None:
                    # if not found separately, combine and continue searching
                    for k, v in the_other_team_records.items():
                        if not k in num2rcds:
                            num2rcds[k] = v
                        else:
                            num2rcds[k].extend(v)
                    temp1, num1 = retrieve_record(num1, num2rcds, priority=['TEAM-WINS', 'TEAM-PTS',
                                                                            'REB', 'AST', 'FTM', 'FGM', 'FG3M',
                                                                            'PTS_HALF-', 'PTS_QTR-'])
                    temp2, num2 = retrieve_record(num2, num2rcds, priority=['TEAM-LOSSES', 'TEAM-PTS',
                                                                            'REB', 'AST', 'FTA', 'FGA', 'FG3A',
                                                                            'PTS_HALF-', 'PTS_QTR-'])
                    cp1, cp2 = None, None
                    # print("pattern 7 xx temp1 = {}".format(temp1))
                    # print("pattern 7 xx temp2 = {}".format(temp2))
                    for x in temp1:
                        for y in temp2:
                            if x.split(DELIM)[2][:-1] == y.split(DELIM)[2][:-1] or (
                                    x.split(DELIM)[2] == 'TEAM-WINS' and y.split(DELIM)[2] == 'TEAM-LOSSES'):
                                cp1 = x
                                cp2 = y
                                break
            else:
                temp1, num1 = retrieve_record(num1, num2rcds, priority=['TEAM-WINS', 'TEAM-PTS',
                                                                        'REB', 'AST', 'FTM', 'FGM', 'FG3M',
                                                                        'PTS_HALF-', 'PTS_QTR-'])
                temp2, num2 = retrieve_record(num2, num2rcds, priority=['TEAM-LOSSES', 'TEAM-PTS',
                                                                        'REB', 'AST', 'FTA', 'FGA', 'FG3A',
                                                                        'PTS_HALF-', 'PTS_QTR-'])
                cp1, cp2 = None, None
                # print("pattern 7 temp1 = {}".format(temp1))
                # print("pattern 7 temp2 = {}".format(temp2))
                for x in temp1:
                    for y in temp2:
                        if x.split(DELIM)[2][:-1] == y.split(DELIM)[2][:-1] or (
                                x.split(DELIM)[2] == 'TEAM-WINS' and y.split(DELIM)[2] == 'TEAM-LOSSES'):
                            cp1 = x
                            cp2 = y
                            break

                            # print('cp1 = {}'.format(cp1))
                            # print('cp2 = {}'.format(cp2))
                            # print('num2rcds = {}'.format(num2rcds))

        if cp1 is None or cp2 is None:
            pass
        # print("*** WARNING *** content not found for phrase {}".format(phrase))
        # print("cp1 = {}, cp2 = {}".format(cp1, cp2))
        else:
            _, team_1, rcd_type_1, _ = cp1.split(DELIM)
            _, team_2, rcd_type_2, _ = cp2.split(DELIM)

            if rcd_type_1.startswith('TEAM'):
                if not rcd_type_2.startswith('TEAM'):
                    pass
                # print("*** WARNING *** cp1 and cp2 are not compatible for phrase {}".format(phrase))
                # print("cp1 = {}, cp2 = {}".format(cp1, cp2))
                else:
                    if rcd_type_1 == 'TEAM-WINS':
                        if not rcd_type_2 == 'TEAM-LOSSES':
                            pass
                        # print("*** WARNING *** cp1 and cp2 are not compatible for phrase {}".format(phrase))
                        # print("cp1 = {}, cp2 = {}".format(cp1, cp2))
                        else:
                            if team_1 == team_2:
                                tokens[numbers_are_at[0]] = str(num1)
                                tokens[numbers_are_at[1]] = str(num2)
                                result = [cp1, cp2]
                            else:
                                pass
                                # print("*** WARNING *** cp1 and cp2 are not compatible for phrase {}".format(phrase))
                                # print("cp1 = {}, cp2 = {}".format(cp1, cp2))

                    elif rcd_type_1 == 'TEAM-PTS':
                        if not rcd_type_2 == 'TEAM-PTS':
                            pass
                        # print("*** WARNING *** cp1 and cp2 are not compatible for phrase {}".format(phrase))
                        # print("cp1 = {}, cp2 = {}".format(cp1, cp2))
                        else:
                            if not (team_1 == team_2):
                                tokens[numbers_are_at[0]] = str(num1)
                                tokens[numbers_are_at[1]] = str(num2)
                                result = [cp1, cp2]
                            else:
                                pass
                                # print("*** WARNING *** cp1 and cp2 are not compatible for phrase {}".format(phrase))
                                # print("cp1 = {}, cp2 = {}".format(cp1, cp2))

                    else:
                        # enforcing a pair of digits having the same rcd_type
                        if rcd_type_1 == rcd_type_2 and team_1 != team_2:
                            tokens[numbers_are_at[0]] = str(num1)
                            tokens[numbers_are_at[1]] = str(num2)
                            result = [cp1, cp2]
                        else:
                            pass
                            # print("*** WARNING *** cp1 and cp2 are not compatible for phrase {}".format(phrase))
                            # print("cp1 = {}, cp2 = {}".format(cp1, cp2))

            else:
                if cp1.split(DELIM)[-2][:2] == cp2.split(DELIM)[-2][:2]:
                    tokens[numbers_are_at[0]] = str(num1)
                    tokens[numbers_are_at[1]] = str(num2)
                    result = [cp1, cp2]
                else:
                    pass
                    # print("*** WARNING *** cp1 and cp2 are not compatible for phrase {}".format(phrase))
                    # print("cp1 = {}, cp2 = {}".format(cp1, cp2))
                    # print(num2rcds)

    elif 8 <= pattern_num <= 27:
        k, v = word2record[pattern_num]
        if isinstance(v, list):
            priority = v
        else:
            priority = [v]
        cp, num = retrieve_record(numbers[0], num2rcds, priority=priority)
        if cp:
            if isinstance(cp, list):
                cp = cp[0]
            tokens[0] = str(num)
            result.append(cp)

    elif 28 <= pattern_num <= 42:
        pass

    else:
        print(phrase)
        print(num2rcds)
        raise ValueError("pattern_num {} is invalid".format(pattern_num))

    correct_phrase = ' '.join([x.strip() for x in tokens if len(x.strip()) > 0])
    # if correct_phrase != original_phrase:
    #     print("*** CORRECTON *** \n original_phrase = {}\ncorrect_phrase = {}".format(original_phrase, correct_phrase))

    if not len(result) > 0:
        count_missing[pattern_num] += 1

    return result, correct_phrase, numbers_are_at


# -------------------------------------------------------------------------------------------------------------------- #
# ------------------------------------------------------ main -------------------------------------------------------- #
# -------------------------------------------------------------------------------------------------------------------- #
RCD_PER_PLAYER = 21
NUM_PLAYERS = 26
RCD_PER_TEAM = len(knowledge_container.line_keys_ext) + len(knowledge_container.line_keys_more)
NUM_TEAMS = 2
print("RCD_PER_PLAYER = {}".format(RCD_PER_PLAYER))
print("NUM_PLAYERS = {}".format(NUM_PLAYERS))
print("RCD_PER_TEAM = {}".format(RCD_PER_TEAM))
print("NUM_TEAMS = {}".format(NUM_TEAMS))

alias2team = knowledge_container.alias2team
singular_prons = knowledge_container.singular_prons
plural_prons = knowledge_container.plural_prons
padding_token_lkt = dict.fromkeys(['<unk>', '<s>', '</s>', '<blank>'])
special_nodes_lkt = dict.fromkeys(['starters', 'bench', 'team_high'])


def _tokenize(word):
    return ' '.join(word.split('_'))


def _any_other_player(sent):
    """
        no idea why some games have missing players
    """
    tokens = sent.strip().split()
    # only checking 2-word names for simplicity
    two_grams = [' '.join(tokens[i:i+2]) for i in range(len(tokens))]
    for name in two_grams:
        if name in knowledge_container.player_lookup:
            return True
    return False


def _build_current_sent_players(sent, table):
    current_sent_players = OrderedDict()
    for word in sent.strip().split():
        if word in table['Players']:
            if word not in current_sent_players:
                current_sent_players[word] = True
    return current_sent_players


def _build_current_sent_teams(sent, table, city2team):
    current_sent_teams = OrderedDict()
    for word in sent.strip().split():
        # ------ resolve team name/city/alias ------ #
        if word in table['Teams']:
            team = word
        elif word in city2team:
            team = city2team[word]
        elif word in alias2team:
            team = alias2team[word]
        else:
            # continue until team word/city/alias is found
            continue
        if team not in current_sent_teams:
            current_sent_teams[team] = True
    return current_sent_teams

def _get_entity2ha(inp):
    entity2ha = {}
    records = inp.strip().split()
    for idx, rcd in enumerate(records):
        _, field, _, ha = rcd.split(DELIM)
        if not field in entity2ha:
            entity2ha[field] = ha
    return entity2ha

def main(args, DATASET):
    BASE_DIR = os.path.join(args.dir, "{}".format(DATASET))

    input_files = [
        "%s.ext.jsonl" % DATASET,         # from add feat
        "src_%s.norm.ext.txt" % DATASET,  # from add feat
        "src_%s.norm.ext.addsp.txt" % DATASET,  # from add feat
        "tgt_%s.norm.mwe.txt" % DATASET,  # from clean
    ]

    js, clean_src, clean_src_addsp, clean_tgt = [os.path.join(BASE_DIR, f) for f in input_files]

    for f in [js, clean_tgt]:
        if not os.path.exists(f):
            bname = os.path.basename(f)
            print("{} does not exist, copying from ../new_dataset/new_clean/{}/{}".format(f, DATASET, bname))
            shutil.copyfile("../new_dataset/new_clean/{}/{}".format(DATASET, bname), f)

    output_files = [
        "%s.trim.json" % DATASET,
        "%s.trim.fulltgt.json" % DATASET,
        "%s_content_plan_tks.txt" % DATASET,
        "%s_content_plan_ids.txt" % DATASET,
        "%s_ptrs.txt" % DATASET,
        "%s_content_plan_tks.addsp.txt" % DATASET,
        "%s_content_plan_ids.addsp.txt" % DATASET,
        "%s_ptrs.addsp.txt" % DATASET,
        "tgt_%s.norm.mwe.trim.txt" % DATASET,
        "tgt_%s.norm.mwe.trim.full.txt" % DATASET,
        "src_%s.norm.trim.txt" % DATASET,
        "src_%s.norm.trim.addsp.txt" % DATASET
    ]

    js_trim, js_trim_fulltgt, \
    cp_out_tks, cp_out_ids, ptrs_out, \
    cp_out_tks_addsp, cp_out_ids_addsp, ptrs_out_addsp, \
    clean_tgt_trim, clean_tgt_trim_full, clean_src_trim, \
    clean_src_trim_addsp = [os.path.join(BASE_DIR, f) for f in output_files]

    player_not_found = 0
    sent_count = 0
    empty_sent = 0
    empty_plan = 0
    output_count = 0
    dummy = 0
    too_long_or_short = 0
    filter_types = {}
    with jsonlines.open(js, 'r') as fin_js, \
            io.open(clean_src, 'r', encoding='utf-8') as fin_src, \
            io.open(clean_src_addsp, 'r', encoding='utf-8') as fin_src_addsp, \
            io.open(clean_tgt, 'r', encoding='utf-8') as fin_tgt, \
            io.open(js_trim, 'w+', encoding='utf-8') as fout_js_trim, \
            io.open(js_trim_fulltgt, 'w+', encoding='utf-8') as fout_js_full, \
            io.open(cp_out_tks, 'w+', encoding='utf-8') as fout_cp_tks, \
            io.open(cp_out_ids, 'w+', encoding='utf-8') as fout_cp_ids, \
            io.open(ptrs_out, 'w+', encoding='utf-8') as fout_ptr, \
            io.open(cp_out_tks_addsp, 'w+', encoding='utf-8') as fout_cp_tks_addsp, \
            io.open(cp_out_ids_addsp, 'w+', encoding='utf-8') as fout_cp_ids_addsp, \
            io.open(ptrs_out_addsp, 'w+', encoding='utf-8') as fout_ptr_addsp, \
            io.open(clean_tgt_trim, 'w+', encoding='utf-8') as fout_tgt, \
            io.open(clean_tgt_trim_full, 'w+', encoding='utf-8') as fout_tgt_full, \
            io.open(clean_src_trim, 'w+', encoding='utf-8') as fout_src, \
            io.open(clean_src_trim_addsp, 'w+', encoding='utf-8') as fout_src_addsp:

        output_table_trimtgt = []
        output_table_fulltgt = []

        original_summaries = fin_tgt.read().strip().split('\n')
        targets = original_summaries
        #! by default using inputs appended with special nodes to extract
        inputs = fin_src_addsp.read().strip().split('\n')
        inputs_nosp = fin_src.read().strip().split('\n')

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

        assert len(original_summaries) == len(targets) == len(inputs)

        if LOWER:
            inputs = [x.lower() for x in inputs]
            targets = [x.lower() for x in targets]

        #! processing each sample
        for idx, (inp, inp_nosp, summary, full_summary, table_original) in \
                tqdm(enumerate(zip(inputs, inputs_nosp, targets, original_summaries, fin_js.iter(type=dict, skip_invalid=True)))):
            city2team = {}
            current_sent_players = OrderedDict()
            current_sent_teams = OrderedDict()

            # ------ get record to index and str to record lookup ------ #
            rcd2idx = {}
            entity2ha = _get_entity2ha(inp)

            if not len(inp.strip().split()) == RCD_PER_PLAYER*NUM_PLAYERS + RCD_PER_TEAM*NUM_TEAMS:
                print(len(inp.strip().split()))
                print(RCD_PER_PLAYER*NUM_PLAYERS + RCD_PER_TEAM*NUM_TEAMS)
                pdb.set_trace()

            allstr2rcds = {}
            for i, rcd in enumerate(inp.strip().split()):
                value, field, rcd_type, ha = rcd.split(DELIM)
                if value == 'N/A' or field == 'N/A':
                    continue
                if rcd in rcd2idx:
                    print("*** WARNING *** duplicate record at line # {}".format(i))
                if not value.isdigit():
                    if value in padding_token_lkt:  #! seems unnecessary
                        continue
                    if not value in allstr2rcds:
                        allstr2rcds[value] = [rcd]
                    else:
                        allstr2rcds[value].append(rcd)
                rcd2idx[rcd] = str(i)

            # ------ get player and team record dictionary ------ #
            table = {"Players": {}, "Teams": {}}
            single_number2rcds = {}
            for rcd in inp.strip().split():
                value, field, rcd_type, ha = rcd.split(DELIM)
                if rcd_type.startswith("TEAM"):  # or rcd_type.startswith('GAME'):
                    if not field in table['Teams']:
                        table['Teams'].update({field: [rcd]})
                    else:
                        table['Teams'][field].append(rcd)
                    if rcd_type == 'TEAM-CITY':
                        city2team[value] = field
                    # this diff is incorporated the last, no apparent pattern found, so rely on single digit matching
                    if 'DIFF' in rcd_type:
                        if not value in single_number2rcds:
                            single_number2rcds[value] = [rcd]
                        else:
                            single_number2rcds[value].append(rcd)
                else:
                    if not field in table['Players']:
                        table['Players'].update({field: [rcd]})
                    else:
                        table['Players'][field].append(rcd)

            # ------ process each sentence ------ #
            paragraph_text = []
            word_pos = 0
            #! for ncpcc
            paragraph_plan = []
            rcd_pos = 0
            pointers = []

            #! for graph
            paragraph_plan_addsp = []
            rcd_pos_addsp = 0
            pointers_addsp = []

            buffer = {'plan': [], 'text': None, 'pointer': []}
            sentences = [x.strip() for x in summary.strip().split(' . ')]

            #! processing each sentence
            for cnt, sent in enumerate(sentences):
                sent_count += 1
                buffer, cat = dont_extract_this_sent(sentences, cnt, buffer, inp, allstr2rcds, table, city2team, alias2team, team_vocab, city_vocab)
                filter_types.setdefault(cat, 0)
                filter_types[cat] += 1

                if cat != 'go_check_content_plan':
                    # go to the next sentence if in the following categories --> buffer will be processed in next iteration
                    if cat == 'player-coref':
                        current_sent_players = _build_current_sent_players(sent, table)
                    elif cat == 'team-coref':
                        current_sent_teams = _build_current_sent_teams(sent, table, city2team)
                    continue

                # print("\n\n\n\n *** sent # {} *** is : \n{}".format(cnt, sent))
                pre_check_player = [x for x in sent.strip().split() if x in table['Players']]
                pre_check_team = [x for x in sent.strip().split() if x in table['Teams'] or x in city2team or x in alias2team]

                # ------ extract player/team this sentence is talking about ------ #
                if len(pre_check_player) > 0:
                    # only reset when new player is mentioned in this sent
                    current_sent_players = _build_current_sent_players(sent, table)
                else:
                    # print(" ** resolving player pronouns for {}**".format(sent))
                    player_found = False
                    for word in sent.strip().split():
                        if word in singular_prons:
                            player_found = True

                    if not player_found:
                        # neither a new player is found nor a pronoun is referring to a previous player
                        current_sent_players = OrderedDict()

                    elif _any_other_player(sent):
                        # print(" **{}** is describing a player not available in the table".format(sent))
                        current_sent_players = OrderedDict()
                        player_not_found += 1

                if len(pre_check_team) > 0:
                    # only reset when new team is mentioned in this sent
                    current_sent_teams = _build_current_sent_teams(sent, table, city2team)
                else:
                    # using team from previous sentence
                    team_found = False
                    for word in sent.strip().split():
                        if word in plural_prons:
                            team_found = True
                    if not team_found:
                        # neither a new team is found nor a pronoun is referring to a previous team
                        current_sent_teams = OrderedDict()

                this_sent_records = []
                for player in current_sent_players.keys():
                    player_records = table['Players'][player]
                    this_sent_records.extend(player_records)

                to_delete = []
                this_game_teams = list(table['Teams'].keys())
                for team in current_sent_teams.keys():
                    # keep track which team is mentioned, the other one might still be useful
                    if team in this_game_teams:
                        this_game_teams.remove(team)
                    else:
                        print("Team not found: {}".format(team))
                        to_delete.append(team)
                        continue
                    team_records = table['Teams'][team]
                    this_sent_records.extend(team_records)
                for i in to_delete:
                    del current_sent_teams[i]

                # only one team is mentioned, pass on the other team records in case needed
                the_other_team_records = None
                if len(this_game_teams) == 1:
                    the_other_team_records = OrderedDict()
                    for rcd in table['Teams'][this_game_teams[0]]:
                        value, field, rcd_type, ha = rcd.split(DELIM)
                        if value.isdigit():
                            value = int(value)
                            if not value in the_other_team_records:
                                the_other_team_records[value] = [rcd]
                            else:
                                the_other_team_records[value].append(rcd)

                # ------ separate player name/team/city/alias/arena from numbers ------ #
                num2rcds = OrderedDict()
                str2rcds = OrderedDict()
                for rcd in this_sent_records:
                    value, field, rcd_type, ha = rcd.split(DELIM)
                    if value.isdigit():
                        value = int(value)
                        if not value in num2rcds:
                            num2rcds[value] = [rcd]
                        else:
                            num2rcds[value].append(rcd)
                    else:
                        if not value in str2rcds:
                            str2rcds[value] = [rcd]
                        else:
                            str2rcds[value].append(rcd)

                this_sent_total_rcds = len(current_sent_players) * RCD_PER_PLAYER + \
                                       len(current_sent_teams) * RCD_PER_TEAM
                cnt = sum([len(v) for k, v in num2rcds.items()]) + sum([len(v) for k, v in str2rcds.items()])
                if not cnt == this_sent_total_rcds:
                    print('\n')
                    print(cnt)
                    print(this_sent_total_rcds)
                    pdb.set_trace()
                del this_sent_records
                '''
                this_game_teams: [team_names]
                num2rcds: {num: [records]}
                str2rcds: {player/team: [records]}
                '''

                # ------ labeling stats patterns ------ #
                unmarked_sent = sent
                sent = mark_records(unmarked_sent)

                phrases = []
                starting_word_pos = word_pos
                sentence_plan_numonly = []
                #! for ncpcc
                sentence_plan = []
                #! for graph
                sentence_plan_addsp = []

                #! processing tokens
                for mwe in sent.strip().split():
                    # print('-'*10 + 'new mwe : {} ({}) '.format(mwe, word_pos) + '-'*10)
                    # include the player/team/city name (alias not available before feature extension)
                    if mwe in str2rcds:
                        if len(str2rcds[mwe]) == 1:
                            this_rcd = str2rcds[mwe][0]

                            if mwe not in special_nodes_lkt and mwe != 'led':
                                #! only add to ncpcc if it's not special node
                                sentence_plan.append(this_rcd)
                                pointers.append(','.join(map(str, [word_pos, rcd_pos])))
                                rcd_pos += 1

                            #! add to addsp anyway
                            # starters, bench, team_high are included here, 'led' has >1
                            sentence_plan_addsp.append(this_rcd)
                            pointers_addsp.append(','.join(map(str, [word_pos, rcd_pos_addsp])))
                            rcd_pos_addsp += 1

                        else:
                            if mwe in special_nodes_lkt:
                                #! only add to special
                                #! assuming referring to the 1st mentioned team
                                this_rcd = str2rcds[mwe][0]
                                # however, if starters/bench were just mentioned, in the same sentence
                                # chances are it's comparing two teams, so use the second one
                                if this_rcd in sentence_plan:
                                    this_rcd = str2rcds[mwe][-1]

                                sentence_plan_addsp.append(this_rcd)
                                pointers_addsp.append(','.join(map(str, [word_pos, rcd_pos_addsp])))
                                rcd_pos_addsp += 1

                            elif mwe == 'led':
                                #! only add to special
                                this_team = [i for i in current_sent_teams.keys()][0]
                                if 'starters' in sent:
                                    key = 'STARTERS'
                                elif 'bench' in sent:
                                    key = 'BENCH'
                                else:
                                    key = 'ALL'
                                this_rcd = None
                                for r in str2rcds['led']:
                                    if key in r.split(DELIM)[2]:
                                        this_rcd = r
                                if this_rcd is None:
                                    this_rcd = str2rcds['led'][0]

                                sentence_plan_addsp.append(this_rcd)
                                pointers_addsp.append(','.join(map(str, [word_pos, rcd_pos_addsp])))
                                rcd_pos_addsp += 1

                            else:
                                #! same team name/city/day may be the next game team for playoffs
                                this_rcd = str2rcds[mwe][0]
                                for r in str2rcds[mwe]:
                                    if not 'NEXT' in r.split(DELIM)[2]:
                                        this_rcd = r

                                #! add to both
                                sentence_plan.append(this_rcd)
                                pointers.append(','.join(map(str, [word_pos, rcd_pos])))
                                rcd_pos += 1

                                sentence_plan_addsp.append(this_rcd)
                                pointers_addsp.append(','.join(map(str, [word_pos, rcd_pos_addsp])))
                                rcd_pos_addsp += 1

                            # print("\n{} --> {}".format(this_rcd, unmarked_sent))
                            # print("{}".format(sentence_plan))
                            # pprint(entity2ha)
                            # pdb.set_trace()

                        phrases.append(mwe)
                        word_pos += 1

                    elif mwe in special_nodes_lkt or mwe == 'led':
                        if len(current_sent_players) == 0:
                            #! no idea who's leading what
                            continue
                        else:
                            #! assuming referring to the 1st mentioned player
                            player = [i for i in current_sent_players.keys()][0]
                            ha = entity2ha[player]
                            if mwe != 'led':
                                for r in allstr2rcds[mwe]:
                                    if r.split(DELIM)[-1] == ha:
                                        this_rcd = r
                            else:
                                if 'starters' in sent:
                                    key = 'STARTERS'
                                elif 'bench' in sent:
                                    key = 'BENCH'
                                else:
                                    key = 'ALL'
                                this_rcd = None
                                for r in allstr2rcds['led']:
                                    if key in r.split(DELIM)[2]:
                                        this_rcd = r
                                if this_rcd is None:
                                    this_rcd = allstr2rcds['led'][0]

                        # print("\n{} --> {}".format(this_rcd, unmarked_sent))
                        # print("{}".format(sentence_plan))
                        # pprint(entity2ha)
                        # pdb.set_trace()
                        sentence_plan_addsp.append(this_rcd)
                        pointers_addsp.append(','.join(map(str, [word_pos, rcd_pos])))
                        rcd_pos_addsp += 1
                        phrases.append(mwe)
                        word_pos += 1

                    elif mwe.startswith("#DELIM"):
                        # print("just before calling get_records: \n num2rcds = {}\n str2rcds = {}".format(num2rcds, str2rcds))
                        records, phrase, numbers_are_at = get_records(mwe, num2rcds, the_other_team_records)
                        if len(records) > 0:
                            sentence_plan.extend(records)
                            sentence_plan_addsp.extend(records)  #! for graph
                            sentence_plan_numonly.extend(records)
                            if not len(numbers_are_at) == len(records):
                                print(numbers_are_at)
                                print(records)
                                pdb.set_trace()
                            for n in numbers_are_at:
                                pointers.append(','.join(map(str, [word_pos + n, rcd_pos])))
                                rcd_pos += 1
                                pointers_addsp.append(','.join(map(str, [word_pos + n, rcd_pos_addsp]))) #! for graph
                                rcd_pos_addsp += 1  #! for graph

                                # print("numbers_are_at = {}".format(numbers_are_at))
                                # print("pointers = {}".format(pointers))

                        phrases.append(phrase)
                        word_pos += len(phrase.split())

                    elif "#DELIM" in mwe:
                        # print("*** warning *** misformated mwe found: {}".format(mwe))
                        p = re.compile('#DELIM\d+#')
                        delim = list(set(re.findall(p, mwe)))
                        if len(delim) == 1:
                            # skip the 0th word
                            delim = delim[0]
                            pieces = mwe.split(delim)
                            phrases.append(pieces[0])
                            word_pos += 1

                            mwe = delim.join(pieces[1:])
                            records, phrase, numbers_are_at = get_records(mwe, num2rcds, the_other_team_records)
                            if len(records) > 0:
                                sentence_plan.extend(records)
                                sentence_plan_addsp.extend(records)  #! for graph
                                sentence_plan_numonly.extend(records)
                                if not len(numbers_are_at) == len(records):
                                    print(numbers_are_at)
                                    print(records)
                                    pdb.set_trace()
                                for n in numbers_are_at:
                                    pointers.append(','.join(map(str, [word_pos + n, rcd_pos])))
                                    rcd_pos += 1
                                    pointers_addsp.append(','.join(map(str, [word_pos + n, rcd_pos_addsp]))) #! for graph
                                    rcd_pos_addsp += 1  #! for graph
                                    # print("numbers_are_at = {}".format(numbers_are_at))
                                    # print("pointers = {}".format(pointers))

                            phrases.append(phrase)
                            word_pos += len(phrase.split())

                        else:
                            # ignore this error case
                            for d in delim:
                                mwe = mwe.replace(d, ' ').strip()
                            phrases.append(mwe)
                            word_pos += len(mwe.split())
                    else:
                        phrases.append(mwe)
                        word_pos += 1
                        # start guessing
                        guess = single_number2rcds.get(mwe, [])
                        best_guess = None
                        if len(guess) >= 1:
                            lkt = {i: True for i in sent.strip().split()}
                            ord2rcds = {v.split(DELIM)[-2].split('-')[-1].lower(): v for v in guess}
                            for k, v in ord2rcds.items():
                                if k in lkt:
                                    best_guess = v
                        if best_guess is not None:
                            dummy += 1
                            sentence_plan.append(best_guess)
                            sentence_plan_addsp.append(best_guess)  #! for graph
                            sentence_plan_numonly.append(best_guess)
                            pointers.append(','.join(map(str, [word_pos, rcd_pos])))
                            rcd_pos += 1
                            pointers_addsp.append(','.join(map(str, [word_pos, rcd_pos_addsp]))) #! for graph
                            rcd_pos_addsp += 1  #! for graph

                # filter out sentences with nothing found for the player/team
                if len(sentence_plan_numonly) > 0:
                    # include the previous buffer sentence
                    if len(buffer['plan'])>0 and buffer['text'] is not None:
                        # print('adding contents in buffer = {}'.format(buffer))
                        paragraph_text.append(buffer['text'])
                        paragraph_plan.extend(buffer['plan'])
                        paragraph_plan_addsp.extend(buffer['plan'])
                        for p in buffer['pointer']:
                            pointers.append(','.join(map(str, [word_pos + p, rcd_pos])))
                            rcd_pos += 1
                            pointers_addsp.append(','.join(map(str, [word_pos + p, rcd_pos_addsp]))) #! for graph
                            rcd_pos_addsp += 1  #! for graph

                        word_pos += len(buffer['text'].split())

                    paragraph_plan.extend(sentence_plan)
                    paragraph_plan_addsp.extend(sentence_plan_addsp)
                    correct_sent = ' '.join(phrases)
                    paragraph_text.append(correct_sent)
                    # increment by 1 for '.' at end of sentence
                    word_pos += 1
                else:
                    # reset both position counters
                    word_pos = starting_word_pos
                    empty_sent += 1
                    if len(buffer['plan'])>0:
                        empty_sent += 1
                    for _ in range(len(sentence_plan)):
                        # print("*** warning *** last pointer removed at word_pos = {}".format(word_pos))
                        pointers.pop(-1)
                        rcd_pos -= 1
                    for _ in range(len(sentence_plan_addsp)):
                        pointers_addsp.pop(-1)
                        rcd_pos_addsp -= 1  #! for graph

                        # print("After popping: {}".format(pointers))

                # NOTE: clear the buffer no matter what
                buffer = {'plan': [], 'text': None, 'pointer': []}

            # take care of non-empty buffer when last sent is finished
            if len(buffer['plan'])>0 and buffer['text'] is not None:
                # print('adding contents in buffer = {}'.format(buffer))
                paragraph_text.append(buffer['text'])
                paragraph_plan.extend(buffer['plan'])
                paragraph_plan_addsp.extend(buffer['plan'])
                for p in buffer['pointer']:
                    pointers.append(','.join(map(str, [word_pos + p, rcd_pos])))
                    rcd_pos += 1
                    pointers_addsp.append(','.join(map(str, [word_pos + p, rcd_pos_addsp]))) #! for graph
                    rcd_pos_addsp += 1  #! for graph

                word_pos += len(buffer['text'].split())

            paragraph_plan_ids = [rcd2idx[rcd] for rcd in paragraph_plan]
            if not len(paragraph_plan) == len(paragraph_plan_ids) == len(pointers):
                print("\nparagraph_text: \n{}".format(paragraph_text))
                print(len(paragraph_plan))
                print(len(paragraph_plan_ids))
                print("\nparagraph_plan: \n{}".format(paragraph_plan))
                print("\npointers: {}\n".format(pointers))
                print(len(pointers))
                pdb.set_trace()

            paragraph_plan_addsp_ids = [rcd2idx[rcd] for rcd in paragraph_plan_addsp]
            if not len(paragraph_plan_addsp) == len(paragraph_plan_addsp_ids) == len(pointers_addsp):
                print("\nparagraph_text: \n{}".format(paragraph_text))
                print(len(paragraph_plan_addsp))
                print(len(paragraph_plan_addsp_ids))
                print("\nparagraph_plan_addsp: \n{}".format(paragraph_plan_addsp))
                print("\npointers_addsp: {}\n".format(pointers_addsp))
                print(len(pointers_addsp))
                pdb.set_trace()

            paragraph_text = ' . '.join(paragraph_text).strip()
            if not paragraph_text.endswith('.'):
                paragraph_text = "{} .".format(paragraph_text)  # append the final '.' if missing somehow

            summ_len = len(paragraph_text.split())

            if len(paragraph_plan_ids) >= MIN_PLAN and summ_len >= MIN_SUMM:
                to_write = True
                paragraph_plan_ids = ' '.join(paragraph_plan_ids)
                paragraph_plan = ' '.join(paragraph_plan)

                paragraph_plan_addsp_ids = ' '.join(paragraph_plan_addsp_ids)
                paragraph_plan_addsp = ' '.join(paragraph_plan_addsp)

                pointers = ' '.join(map(str, pointers))
                pointers_addsp = ' '.join(map(str, pointers_addsp))

                fout_src.write("{}\n".format(inp_nosp.strip()))
                fout_src_addsp.write("{}\n".format(inp.strip()))

            else:
                to_write = False
                if len(paragraph_plan_ids) == 0:
                    empty_plan += 1
                    print("content_plan empty at {}".format(idx))
                    print(summary)
                else:
                    too_long_or_short += 1
                    # print("discarded since it's beyond required lengths \n{}\n".format(paragraph_plan, paragraph_text))

            if to_write:
                output_count += 1

                output_table_fulltgt.append(table_original)
                temp_table = copy.deepcopy(table_original)
                temp_table['summary'] = paragraph_text.split()  # substituting the trimmed summary
                output_table_trimtgt.append(temp_table)

                #! for ncpcc
                fout_cp_ids.write("{}\n".format(paragraph_plan_ids))
                fout_cp_tks.write("{}\n".format(paragraph_plan))
                fout_ptr.write("{}\n".format(pointers))

                #! for graph
                fout_cp_ids_addsp.write("{}\n".format(paragraph_plan_addsp_ids))
                fout_cp_tks_addsp.write("{}\n".format(paragraph_plan_addsp))
                fout_ptr_addsp.write("{}\n".format(pointers_addsp))

                fout_tgt.write("{}\n".format(paragraph_text))
                fout_tgt_full.write("{}\n".format(full_summary.strip()))

        json.dump(output_table_fulltgt, fout_js_full)
        json.dump(output_table_trimtgt, fout_js_trim)

    print("{} sentences out of {} are discarded due to empty content plan".format(empty_sent, sent_count))
    print("{} sentences out of {} contains players not available from the table".format(player_not_found, sent_count))
    print("{} samples are retained, {} empty content plans, {} are beyond length ranges".format(output_count, empty_plan, too_long_or_short))
    print("count_missing = {}".format(count_missing))
    print("dummy = {}".format(dummy))
    print("filter_types:")
    pprint(filter_types)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='clean')
    parser.add_argument('--dir', type=str, default='../new_dataset/new_extend/',
                        help='directory of src/tgt_train/valid/test.txt files')
    args = parser.parse_args()

    for DATASET in ['train', 'valid', 'test']:
        print("Extracting content plan from {}".format(DATASET))
        main(args, DATASET)