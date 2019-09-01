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


def _get_pairwise(left, right, rcd_types, entity2nodes, node2idx, direction):
    """
    :param left/right  : [str]  player name
    :param rcd_types   : [list] list of rcd_types (digits) to compare with neighbours in the same(HOME/AWAY) teams
    :param entity2nodes: [dict] {entity: {rcd_type: (value, rcd)}}
    :param node2idx    : [dict] {rcd: sample.index(rcd)}
    :return edges      : [dict] {(left, right): label}
    """
    label = 'greater'
    edges = {}
    for t in rcd_types:
        left_val, left_node = entity2nodes[left][t]
        left_idx = node2idx[left_node]
        right_val, right_node = entity2nodes[right][t]
        right_idx = node2idx[right_node]

        #! NOTE: (i, j) is an edge i --> j with label '>' if val(i) > val(j), else '='
        # using the same 'greater' edge type in directed graph technically makes no difference
        if left_val == 'N/A':
            if right_val.isdigit():
                # right > left
                if direction == 'big2small':
                    edges[(right_idx, left_idx)] = label
                else:
                    edges[(left_idx, right_idx)] = label
            else:
                # right = left
                edges[(right_idx, left_idx)] = 'equal'
                edges[(left_idx, right_idx)] = 'equal'
        elif right_val == 'N/A':
            # left > right
            if direction == 'big2small':
                edges[(left_idx, right_idx)] = label
            else:
                edges[(right_idx, left_idx)] = label
        else:
            if int(left_val) > int(right_val):
                # left > right
                if direction == 'big2small':
                    edges[(left_idx, right_idx)] = label
                else:
                    edges[(right_idx, left_idx)] = label

            elif int(left_val) < int(right_val):
                # right > left
                if direction == 'big2small':
                    edges[(right_idx, left_idx)] = label
                else:
                    edges[(left_idx, right_idx)] = label
            else:
                # right = left
                edges[(right_idx, left_idx)] = 'equal'
                edges[(left_idx, right_idx)] = 'equal'

    return edges


def _get_team_player(ha2player, ha2team, node2idx):
    """
    :param ha2player: [dict] {'HOME/AWAY': [player_name_records]}
    :param ha2team  : [dict] {'HOME/AWAY': [team_name_records]}
    :param node2idx : [dict] {rcd: sample.index(rcd)}
    :return:
    """
    label = 'has_player'
    edges = {}
    for ha in ['HOME', 'AWAY']:
        team = ha2team[ha]
        team_id = node2idx[team]
        for p in ha2player[ha]:
            player_id = node2idx[p]
            # ! NOTE: directed edges from team to player
            edges[(team_id, player_id)] = label
            # edges[(player_id, team_id)] = label
    return edges


def _get_other_edges(node2idx, meta2idx, entity2nodes, ha2player, ha2team):
    """
        node2idx     [dict]: {rcd: sample.index(rcd)}
        meta2idx     [dict]: {"field|rcd_type|ha": sample.index(rcd)}
        entity2nodes [dict]: {entity: {rcd_type: (value, rcd)}}
        ha2player    [dict]: {'HOME/AWAY': [player_name_records]}
        ha2team      [dict]: {'HOME/AWAY': [team_name_records]}
    """
    label = 'has_record'
    edges = {}
    for ha in ['HOME', 'AWAY']:
        # -- PLAYER_NAME to record edges -- #
        for player in ha2player[ha]:
            player_id = node2idx[player]  # PLAYER_NAME
            player_records = entity2nodes[player.split(DELIM)[0]]
            # -1 is the PLAYER_NAME rcd_type
            for key in box_numkeys + box_otherkeys[:-1]:
                node = player_records[key][1]
                idx = node2idx[node]
                # ! NOTE: directed edges from player to records
                edges[(player_id, idx)] = label
                # edges[(idx, player_id)] = label

        # -- TEAM_NAME to record edges -- #
        team = ha2team[ha]  # TEAM_NAME
        team_id = node2idx[team]
        team_records = entity2nodes[team.split(DELIM)[0]]
        # -1 is the TEAM_NAME rcd_type
        for key in line_numkeys + line_diffkeys + line_otherkeys[:-1]:
            node = team_records[key][1]
            idx = node2idx[node]
            # edges[(idx, team_id)] = label
            # ! NOTE: directed edges from team to records
            edges[(team_id, idx)] = label

    return edges


def _get_top_players(ha2player, entity2nodes, plan, mentioned):

    plan_lkt = dict.fromkeys([x for x in plan.strip().split() if x.split(DELIM)[2] == 'PLAYER_NAME'], 1)
    player_rankings = {}
    for rcd_type in box_leadkeys:
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

        for ha in ['HOME', 'AWAY']:
            for key in ['START', 'BENCH', 'ALL']:
                rankings = sorted(before[ha][key], key=lambda x:x[1], reverse=True)
                after[ha][key] = rankings[:3]  # get top 3 players/statistics
                for idx, (x, _, _) in enumerate(rankings):
                    if x in plan_lkt:
                        if rcd_type == 'PTS' and idx <= 2:
                            plan_lkt[x] = 0
                        if mentioned[rcd_type][key] is None:
                            mentioned[rcd_type][key] = {idx: 1}
                        elif idx not in mentioned[rcd_type][key]:
                            mentioned[rcd_type][key][idx] = 1
                        else:
                            mentioned[rcd_type][key][idx] += 1
        player_rankings[rcd_type] = after

    remaining = sum(plan_lkt.values())
    return player_rankings, mentioned, len(plan_lkt), remaining


def _get_lead_edges(node2idx, meta2idx, entity2nodes, ha2player, ha2team, plan, mentioned):

    edges = {}
    player_rankings, mentioned, cnt, remaining = _get_top_players(ha2player, entity2nodes, plan, mentioned)
    labels = {i:"top_{}".format(i+1) for i in range(3)}

    for rcd_type in box_leadkeys:
        team_rcd_type = "TEAM-{}".format(rcd_type)
        for ha in ['HOME', 'AWAY']:
            team = ha2team[ha]  # the TEAM_NAME node

            #! add TEAM-TYPE --> PLAYER-TYPE
            lead_players = player_rankings[rcd_type][ha]['ALL']
            _, teamentity, _, _ = team.split(DELIM)
            team_rcd_meta = DELIM.join([teamentity, team_rcd_type, ha])
            team_rcd_id = meta2idx[team_rcd_meta]
            for idx, (_, _, rcd) in enumerate(lead_players):
                rcd_id = node2idx[rcd]
                edges[(team_rcd_id, rcd_id)] = labels[idx]

            #! add TEAM-NAME --> PLAYER NAME for ALL, START, BENCH lead players
            team_id = node2idx[team]  # the TEAM_NAME node
            if rcd_type == 'PTS':
                #! TEAM_NAME --> 2nd & 3rd PLAYER_NAME
                lead_players = player_rankings[rcd_type][ha]['ALL']
                for idx, (p, _, _) in enumerate(lead_players):
                    player_id = node2idx[p]
                    edges[(team_id, player_id)] = labels[idx]
                #! TEAM_NAME --> 1st PLAYER_NAME (two possible verbalizations)
                first_player_id = node2idx[lead_players[0][0]]  # PLAYER_NAME
                team_led = DELIM.join(['led', teamentity, 'TEAM-ALL_LEAD', ha])
                team_led_id = node2idx[team_led]
                edges[(team_led_id, first_player_id)] = 'led_by'
                team_high = DELIM.join(['team_high', teamentity, 'TEAM-ALL_HIGH', ha])
                team_high_id = node2idx[team_high]
                edges[(team_high_id, first_player_id)] = 'led_by'

                #! SUM-START --> 1/2/3 PLAYER PTS
                start_pts_meta = DELIM.join([teamentity, 'TEAM-PTS_SUM-START', ha])
                start_pts_id = meta2idx[start_pts_meta]
                lead_starters = player_rankings[rcd_type][ha]['START']
                for idx, (_, _, rcd) in enumerate(lead_starters):
                    rcd_id = node2idx[rcd]
                    edges[(start_pts_id, rcd_id)] = labels[idx]
                #! TEAM-STARTERS-LEAD --> 1st PLAYER_NAME
                first_starter_id = node2idx[lead_starters[0][0]]  # PLAYER_NAME
                starter_led = DELIM.join(['led', teamentity, 'TEAM-STARTERS_LEAD', ha])
                starter_led_id = node2idx[starter_led]
                edges[(starter_led_id, first_starter_id)] = 'led_by'

                #! SUM-BENCH --> 1/2/3 PLAYER PTS
                bench_pts_meta = DELIM.join([teamentity, 'TEAM-PTS_SUM-BENCH', ha])
                bench_pts_id = meta2idx[bench_pts_meta]
                lead_benchers = player_rankings[rcd_type][ha]['BENCH']
                for idx, (_, _, rcd) in enumerate(lead_benchers):
                    rcd_id = node2idx[rcd]
                    edges[(bench_pts_id, rcd_id)] = labels[idx]
                #! TEAM-BENCH-LEAD --> 1st PLAYER_NAME
                first_bench_id = node2idx[lead_benchers[0][0]]  # PLAYER_NAME
                bench_led = DELIM.join(['led', teamentity, 'TEAM-BENCH_LEAD', ha])
                bench_led_id = node2idx[bench_led]
                edges[(bench_led_id, first_bench_id)] = 'led_by'

    return edges, mentioned, cnt, remaining


def _get_norms(edges):
    edges_with_norms = copy.deepcopy(edges)

    label2metanorm = {
        'greater': 1.0/8,
        'equal': 1.0/8,
        'has_player': 1.0/4,
        'has_record': 1.0/4,
        'top_1': 1.0/4,
        'top_2': 1.0/4,
        'top_3': 1.0/4,
        'led_by': 1.0/4,
    }

    sink2norms = {}
    for (src, sink), label in edges.items():
        if not sink in sink2norms:
            sink2norms[sink] = {
                'greater': [],
                'equal': [],
                'has_player':[],
                'has_record': [],
                'top_1': [],
                'top_2': [],
                'top_3': [],
                'led_by': []
            }
        sink2norms[sink][label].append(src)

    tmp = copy.deepcopy(sink2norms)
    for sink, temp in sink2norms.items():
        meta_count = len([x for _, x in temp.items() if len(x)>0])
        if meta_count > 0:
            # meta_norm = 1.0/meta_count
            pass
        else:
            raise ValueError("sink = {} has no neighbour ???".format(sink))
            import pdb
            pdb.set_trace()

        for key, neighbours in temp.items():
            cnt = len(neighbours)
            if cnt == 0:
                continue
            meta_norm = label2metanorm[key]
            norm = meta_norm/cnt
            tmp[sink][key] = list(zip([norm]*cnt, neighbours))
            for n in neighbours:
                label = edges_with_norms[(n, sink)]
                assert label == key
                edges_with_norms[(n, sink)] = (label, norm)

    return edges_with_norms


def _sanity_check(edges, records, has_norm=False):
    import pandas as pd
    temp = {'left':[], 'label':[], 'right':[]}
    if has_norm:
        temp['norm'] = []
    for (left, right), value in edges.items():
        temp['left'].append(records[left])
        temp['right'].append(records[right])
        if has_norm:
            label, norm = value
            temp['norm'].append(norm)
        else:
            label = value
        temp['label'].append(label)

    print("\n")
    print(pd.DataFrame(temp).to_string())
    import pdb
    pdb.set_trace()


#! NOTE: new_dataset means cleaned, with graph edge information added
BASE="/mnt/cephfs2/nlp/hongmin.wang/table2text/boxscore-data"
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='clean')
    parser.add_argument('--direction', required=True, choices=['big2small', 'small2big'],
                        help='if use undirected edges between pair of statistics, e.g. PTS vs PTS. Default: False')
    parser.add_argument('--dataset', required=True, choices=['inlg', 'aaai'],
                        help='which dataset to take in')
    args = parser.parse_args()

    if args.dataset == 'aaai':
        line_otherkeys.extend(['TEAM-NEXT_NAME', 'TEAM-NEXT_CITY', 'TEAM-NEXT_DAY', 'TEAM-NEXT_HA'])

    for DATA in ['train', 'valid', 'test']:
        print("Processing {} set".format(DATA))
        total = 0
        remaining = 0
        mentioned = dict.fromkeys(box_leadkeys, None)

        fname = "{}/scripts_{}/new_dataset/new_extend_addsp/{}/src_{}.norm.trim.addsp.ncp.full.txt"\
            .format(BASE, args.dataset, DATA, DATA)
        cpname = "{}/scripts_{}/new_dataset/new_extend_addsp/{}/{}_content_plan_tks.addsp.txt"\
            .format(BASE, args.dataset, DATA, DATA)  # only for counting
        fout = "{}/scripts_{}/new_dataset/new_extend_addsp/{}/edges_{}.ncp.new.direction-{}.newnorms.addsp.jsonl"\
            .format(BASE, args.dataset, DATA, DATA, args.direction)

        with io.open(fname, 'r', encoding='utf-8') as fin, io.open(cpname, 'r', encoding='utf-8') as cpfin, \
                jsonlines.open(fout, 'w') as writer:

            outlines = cpfin.read().strip().split('\n')
            inputs = fin.read().strip().split('\n')
            for sample, plan in tqdm(zip(inputs, outlines)):
                edges = {}

                # --- get lookup tables --- #
                records = sample.strip().split()
                node2idx, meta2idx, entity2nodes, player_pairs, ha2player, ha2team = _get_lookups(records)
                home = ha2team['HOME'].split(DELIM)[0]
                away = ha2team['AWAY'].split(DELIM)[0]
                team_pair = [(home, away)]

                # --- get lookup tables --- #
                for pair_list, rcd_types in \
                        zip([player_pairs['HOME'], player_pairs['AWAY'], team_pair],
                            [box_numkeys, box_numkeys, line_numkeys]):
                    for left, right in pair_list:
                        edges.update(_get_pairwise(left, right, rcd_types, entity2nodes, node2idx, args.direction))

                team_player_edges = _get_team_player(ha2player, ha2team, node2idx)
                edges.update(team_player_edges)
                # _sanity_check(team_player_edges, records)

                other_edges = _get_other_edges(node2idx, meta2idx, entity2nodes, ha2player, ha2team)
                # _sanity_check(other_edges, records)
                edges.update(other_edges)
                # import pdb
                # pdb.set_trace()
                lead_edge, mentioned, temp, tmp = _get_lead_edges(node2idx, meta2idx, entity2nodes, ha2player, ha2team, plan, mentioned)
                # _sanity_check(lead_edge, records)
                edges.update(lead_edge)

                edges = _get_norms(edges)
                # _sanity_check(edges, records)

                total += temp
                remaining += tmp
                combo = {}
                for (left, right), (lab, norm) in edges.items():
                    key = '{},{}'.format(left, right)
                    combo[key] = (lab, norm)
                writer.write(combo)

        print("{} out of {} are not top3 players {:0.2f} %".format(remaining, total, 100-100.0*remaining/total))
        for rcd_type in box_leadkeys:
            print("\n *** {}".format(rcd_type))
            pprint(mentioned[rcd_type])
            for key in ['START', 'BENCH', 'ALL']:
                this_sum = 0
                for rank in [0, 1, 2]:
                    count = mentioned[rcd_type][key][rank]
                    this_sum += count
                    print("[{}] Player ranked #{} has been mentioned {}/{} ({:0.2f}%) times".format(
                        key,
                        rank + 1,
                        count,
                        total,
                        count*100.0/total
                    ))

                print(" ** [{}] Player ranked top-3 has been mentioned {}/{} ({:0.2f}%) times".format(key, this_sum, total, this_sum*100.0/total))