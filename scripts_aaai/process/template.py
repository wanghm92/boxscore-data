import re, io, copy, os, sys, pprint, jsonlines, pdb, argparse
from tqdm import tqdm
from collections import Counter, OrderedDict
from text2num import text2num
from pprint import pprint
from itertools import combinations
DELIM = "￨"
UNK = 0
NA = 'N/A'
PAD_WORD = '<blank>'
UNK_WORD = '<unk>'
BOS_WORD = '<s>'
EOS_WORD = '</s>'

"""
# [done] team - player: plays_for led_by
# [done] team <-> team and player <-> player: same rcd_type: >=<
# Edges:
1. START vs BENCH:
    + [optional] Teams <-has-> START/BENCH <-has-> Players
    + [done] START/BENCH SUMS <-led_by-> Top player PTS
    + [done] START/BENCH <-lead-> Best_Player (or Best_Player PTS)
    + [done] Teams <-lead-> Best_Player (or Best_Player PTS)
    + [done] START/BENCH SUM_PTS <-compare-> START/BENCH SUM_PTS across teams
    + [done] verbalized edge for STARTERS/BENCH:
        (p|P)oint guard,
        (s|S)hooting guard,
        (s|S)mall forward,
        (P|p)ower forward,
        center(/Center)
        [done] 'the second unit' --> bench
        (1k+ tokens in train)
    + [done] verbalized edge for led_by

2. others:
    + [done] team --> DIFFs
    + [optional] remove N/A players and nodes
    + [optional] WINNER
    + [optional] STAR/MVP
"""

line_numkeys = [
    'TEAM-PTS',
    'TEAM-PTS_HALF-FIRST', 'TEAM-PTS_HALF-SECOND',
    'TEAM-PTS_QTR1', 'TEAM-PTS_QTR2', 'TEAM-PTS_QTR3', 'TEAM-PTS_QTR4',
    'TEAM-PTS_QTR-1to3', 'TEAM-PTS_QTR-2to4',
    'TEAM-FG3A', 'TEAM-FG3M', 'TEAM-FG3_PCT',
    'TEAM-FGA', 'TEAM-FGM', 'TEAM-FG_PCT',
    'TEAM-FTA', 'TEAM-FTM', 'TEAM-FT_PCT',
    'TEAM-REB', 'TEAM-OREB', 'TEAM-DREB',
    'TEAM-AST', 'TEAM-BLK', 'TEAM-STL', 'TEAM-TOV',
    'TEAM-PTS_SUM-BENCH', 'TEAM-PTS_SUM-START',
]
print("line_numkeys: {}".format(len(line_numkeys)))

line_otherkeys = [
    'TEAM-STARTERS', 'TEAM-STARTERS_LEAD', 'TEAM-BENCH', 'TEAM-BENCH_LEAD', 'TEAM-ALL_LEAD', 'TEAM-ALL_HIGH',
    'TEAM-WINS', 'TEAM-LOSSES',
    'TEAM-ALIAS', 'TEAM-ARENA', 'TEAM-CITY',
    'TEAM-NAME'
]
print("line_otherkeys: {}".format(len(line_otherkeys)))

line_diffkeys = [
    'TEAM-PTS_TOTAL_DIFF',
    'TEAM-PTS_HALF_DIFF-FIRST', 'TEAM-PTS_HALF_DIFF-SECOND',
    'TEAM-PTS_QTR_DIFF-FIRST', 'TEAM-PTS_QTR_DIFF-SECOND', 'TEAM-PTS_QTR_DIFF-THIRD', 'TEAM-PTS_QTR_DIFF-FOURTH',
]
print("line_diffkeys: {}".format(len(line_diffkeys)))

box_numkeys = [
    'MIN', 'PTS',
    'FGM', 'FGA', 'FG_PCT',
    'FG3M', 'FG3A', 'FG3_PCT',
    'FTM', 'FTA', 'FT_PCT',
    'OREB', 'DREB', 'REB',
    'AST', 'TOV', 'STL', 'BLK', 'PF'
]
print("box_numkeys: {}".format(len(box_numkeys)))

box_otherkeys = [
    'START_POSITION', 'PLAYER_NAME'
]
print("box_otherkeys: {}".format(len(box_otherkeys)))

box_leadkeys = [
    'PTS',
    'FGM', 'FGA',
    'FG3M', 'FG3A',
    'FTM', 'FTA',
    'OREB', 'DREB', 'REB',
    'AST', 'TOV', 'STL', 'BLK'
]
print("box_leadkeys: {}".format(len(box_leadkeys)))


def _get_lookups(records):
    """
    Input:
        sample [list]: [value|field|rcd_type|ha, ...]
    Return:
        node2idx     [dict]: {rcd: sample.index(rcd)}
        meta2idx     [dict]: {"field|rcd_type|ha": sample.index(rcd)}
        entity2nodes [dict]: {entity: {rcd_type: (value, rcd)}}
        player_pairs [dict]: {'HOME/AWAY': [(p_i, p_j)]}
        ha2player   [dict]: {'HOME/AWAY': [player_name_records]}
        ha2team   [dict]: {'HOME/AWAY': [team_name_records]}
    """
    node2idx = {}
    meta2idx = {}
    entity2nodes = {}
    ha2player = {'HOME':[], 'AWAY': []}
    ha2team = {'HOME': None, 'AWAY':None}

    #! get home/away team first
    for idx, rcd in enumerate(records):
        value, field, rcd_type, ha = rcd.split(DELIM)
        if rcd_type == 'TEAM-NAME':
            ha2team[ha] = rcd

    for idx, rcd in enumerate(records):
        value, field, rcd_type, ha = rcd.split(DELIM)
        meta = DELIM.join([field, rcd_type, ha])

        if not rcd in node2idx:
            node2idx[rcd] = idx
            meta2idx[meta] = idx  #! meta may not be unique for N/A and <blank> players
        else:
            assert meta in meta2idx

        entity2nodes.setdefault(field, {rcd_type: (value, rcd)})
        entity2nodes[field][rcd_type] = (value, rcd)

        if rcd_type == 'PLAYER_NAME':
            ha2player[ha].append(rcd)

    player_pairs = {'HOME': [], 'AWAY':[]}
    for ha, player in ha2player.items():
        player = [rcd.split(DELIM)[0] for rcd in player]
        player_pairs[ha].extend(combinations(player, 2))

    return node2idx, meta2idx, entity2nodes, player_pairs, ha2player, ha2team


def _get_top_players(ha2player, entity2nodes, plan, mentioned):

    plan_lkt = dict.fromkeys([x for x in plan.strip().split() if x.split(DELIM)[2] == 'PLAYER_NAME'], 1)

    cnt = 0
    # for rcd_type in box_leadkeys:
    rcd_type = 'PTS'
    if mentioned[rcd_type] is None:
        mentioned[rcd_type] = dict.fromkeys(['START', 'BENCH', 'ALL'], None)
    before = {
        'HOME': {
            'START': [],
            'BENCH': [],
            'ALL': []
        },
        'AWAY': {
            'START': [],
            'BENCH': [],
            'ALL': []
        }
    }

    for ha in ['HOME', 'AWAY']:
        for player in ha2player[ha]:
            name = player.split(DELIM)[0]
            records = entity2nodes[name]
            value, rcd = records[rcd_type]
            start_position = records['START_POSITION'][0]
            start_or_bench = 'BENCH' if start_position == 'N/A' else 'START'
            if value == 'N/A':
                continue
            else:
                value = int(value)
                before[ha][start_or_bench].append((player, value, rcd))
                before[ha]['ALL'].append((player, value, rcd))

    after = {
        'HOME': {
            'START': [],
            'BENCH': [],
            'ALL': []
        },
        'AWAY': {
            'START': [],
            'BENCH': [],
            'ALL': []
        }
    }
    correct = set()
    accum = set()
    for ha in ['HOME', 'AWAY']:
        for key, threshold in zip(['START', 'BENCH', 'ALL'], [3, 2, 3]):
            rankings = sorted(before[ha][key], key=lambda x:x[1], reverse=True)
            after[ha][key] = rankings[:3]  # get top 3 players/statistics
            for idx, (x, _, _) in enumerate(rankings):
                if idx <= threshold:
                    accum.add(x)
                if x in plan_lkt:
                    if rcd_type == 'PTS' and idx <= threshold:
                        plan_lkt[x] = 0
                        correct.add(x)
                    if mentioned[rcd_type][key] is None:
                        mentioned[rcd_type][key] = {idx: 1}
                    elif idx not in mentioned[rcd_type][key]:
                        mentioned[rcd_type][key][idx] = 1
                    else:
                        mentioned[rcd_type][key][idx] += 1

    remaining = sum(plan_lkt.values())
    return after, len(accum), len(correct), len(plan_lkt), remaining


def _print_upper_bounds(cp_cnt, k, num_samples, players):
    pprint(Counter(cp_cnt))
    top = sum([x for _,x in Counter(cp_cnt).most_common()][:k])
    temp = num_samples*k*players
    total = sum([x for _,x in Counter(cp_cnt).most_common()])
    print("Upper bounds [{}][{}]: Recall({} / {}) = {:.2f}%, Precison({} / {}) = {:.2f}%".format(k, num_samples, top, total, 100.0*top/total, top, temp, 100.0*top/temp))


def _get_team_items(ha2team, entity2nodes):
    hometeam = ha2team['HOME'].split(DELIM)[0]
    homepts = int(entity2nodes[hometeam]['TEAM-PTS'][0])
    homewins = entity2nodes[hometeam]['TEAM-WINS'][0]
    homelosses = entity2nodes[hometeam]['TEAM-LOSSES'][0]
    arena = entity2nodes[hometeam]['TEAM-ARENA'][0]

    awayteam = ha2team['AWAY'].split(DELIM)[0]
    awaypts = int(entity2nodes[awayteam]['TEAM-PTS'][0])
    awaywins = entity2nodes[awayteam]['TEAM-WINS'][0]
    awaylosses = entity2nodes[awayteam]['TEAM-LOSSES'][0]

    if homepts > awaypts:
        first_items = (hometeam, homewins, homelosses, awayteam, awaywins, awaylosses, homepts, awaypts, arena)
    else:
        first_items = (awayteam, awaywins, awaylosses, hometeam, homewins, homelosses, awaypts, homepts, arena)

    home_next_name = entity2nodes[hometeam]['TEAM-NEXT_NAME'][0]
    home_next_city = entity2nodes[hometeam]['TEAM-NEXT_CITY'][0]
    home_next_day = entity2nodes[hometeam]['TEAM-NEXT_DAY'][0]
    home_next_ha = entity2nodes[hometeam]['TEAM-NEXT_HA'][0]
    home_next_items = (home_next_ha == 'home', hometeam, home_next_city, home_next_name, home_next_day)

    away_next_name = entity2nodes[awayteam]['TEAM-NEXT_NAME'][0]
    away_next_city = entity2nodes[awayteam]['TEAM-NEXT_CITY'][0]
    away_next_day = entity2nodes[awayteam]['TEAM-NEXT_DAY'][0]
    away_next_ha = entity2nodes[awayteam]['TEAM-NEXT_HA'][0]
    away_next_items = (away_next_ha == 'away', awayteam, away_next_city, away_next_name, away_next_day)

    return first_items, home_next_items, away_next_items


def _get_players(player_rankings):
    players = []

    for ha in ['HOME', 'AWAY']:
        seen = set()
        this = []
        for key in ['ALL', 'BENCH', 'START']:
            leaders = player_rankings[ha][key]
            for l in leaders:
                if not l in seen:
                    seen.add(l)
                    this.append(l)
            if len(this) >= 4:
                this = this[:4]
                break
        players.extend(this)

    return players


def _get_player_items(player, entity2nodes):
    name = player[0].split(DELIM)[0]
    fgm = entity2nodes[name]['FGM'][0]
    fga = entity2nodes[name]['FGA'][0]
    pts = player[1]
    rebounds = entity2nodes[name]['REB'][0]
    assists = entity2nodes[name]['AST'][0]
    steals = entity2nodes[name]['STL'][0]
    minutes = entity2nodes[name]['MIN'][0]

    return name, fgm, fga, pts, rebounds, assists, steals, minutes

def rule_gen(player_rankings, ha2team, node2idx, entity2nodes):

    # --- first sentence --- #
    first_items, home_next_items, away_next_items = _get_team_items(ha2team, entity2nodes)
    first_line = "The {} ( {} - {} ) defeated the {} ( {} - {} ) {} - {} at {} .".format(*first_items)

    # --- player sentence --- #
    ret = [first_line]
    for player in _get_players(player_rankings):
        player_items = _get_player_items(player, entity2nodes)
        player_line = "{} went {} - for - {} from the field , scored {} points , {} rebounds , {} assists , {} steals in {} minutes .".format(*player_items)
        ret.append(player_line)

    # --- last sentence --- #
    at_home = "{} ' next game will be at home against the {} on {}"
    on_the_way = "{} will be on_the_way to {} to face the {} on {}"

    if home_next_items[0]:
        home_next_line = at_home.format(home_next_items[1], home_next_items[3], home_next_items[4])
    else:
        home_next_line = on_the_way.format(home_next_items[1], home_next_items[2], home_next_items[3], home_next_items[4])

    if away_next_items[0]:
        away_next_line = at_home.format(away_next_items[1], away_next_items[3], away_next_items[4])
    else:
        away_next_line = on_the_way.format(away_next_items[1], away_next_items[2], away_next_items[3], away_next_items[4])

    next_line = "{} , while {} .".format(home_next_line, away_next_line)
    ret.append(next_line)
    ret = " ".join(ret)
    return ret


#! NOTE: new_dataset means cleaned, with graph edge information added
BASE="/mnt/cephfs2/nlp/hongmin.wang/table2text/boxscore-data"
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='clean')
    parser.add_argument('--dataset', required=True, choices=['inlg', 'aaai'],
                        help='which dataset to take in')
    args = parser.parse_args()

    if args.dataset == 'aaai':
        line_otherkeys.extend(['TEAM-NEXT_NAME', 'TEAM-NEXT_CITY', 'TEAM-NEXT_DAY', 'TEAM-NEXT_HA'])

    for DATA in ['train', 'valid', 'test']:
        print("Processing {} set".format(DATA))
        total = 0
        remaining = 0
        accum = 0
        correct = 0
        mentioned = dict.fromkeys(box_leadkeys, None)

        srcname = "{}/scripts_{}/new_dataset/new_extend_addsp/{}/src_{}.norm.trim.addsp.ncp.full.txt"\
            .format(BASE, args.dataset, DATA, DATA)
        cpname = "{}/scripts_{}/new_dataset/new_extend_addsp/{}/{}_content_plan_tks.addsp.txt"\
            .format(BASE, args.dataset, DATA, DATA)  # only for counting
        outname = "{}.rule.txt".format(DATA)

        cp_cnt = []
        num_cnt = []
        with io.open(srcname, 'r', encoding='utf-8') as fin, \
                io.open(cpname, 'r', encoding='utf-8') as cpfin, \
                io.open(outname, 'w', encoding='utf-8') as fout:

            outlines = cpfin.read().strip().split('\n')
            inputs = fin.read().strip().split('\n')
            print("Sample size = {}".format(len(outlines)))
            for sample, plan in tqdm(zip(inputs, outlines)):
                records = plan.strip().split()
                records = list(set(records))
                player_rcd_types = [x.split(DELIM)[2] for x in records if not 'TEAM' in x]
                num_cnt.append(player_rcd_types.count('PLAYER_NAME'))
                cp_cnt.extend(player_rcd_types)

                # --- get lookup tables --- #
                records = sample.strip().split()
                node2idx, meta2idx, entity2nodes, player_pairs, ha2player, ha2team = _get_lookups(records)

                player_rankings, _accum, _correct, temp, tmp = _get_top_players(ha2player, entity2nodes, plan, mentioned)

                total += temp
                remaining += tmp
                accum += _accum
                correct += _correct

                summary = rule_gen(player_rankings, ha2team, node2idx, entity2nodes)
                fout.write("{}\n".format(summary))

        print("{} out of {} are not top3 players {:0.2f} %".format(remaining, total, 100-100.0*remaining/total))
        print("{} out of {} top3 players {:0.2f} % are mentioned".format(correct, accum, 100.0*correct/accum))

        _print_upper_bounds(cp_cnt, 9, len(outlines), 8)
