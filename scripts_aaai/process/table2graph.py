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
    !+ [pending] Teams <-has-> START/BENCH <-has-> Players
    + [done] START/BENCH <-lead-> Best_Player (or Best_Player PTS)
    + [done] Teams <-lead-> Best_Player (or Best_Player PTS)
    + [done] START/BENCH SUM_PTS <-compare-> START/BENCH SUM_PTS across teams
    !+ [pending] verbalized edge for STARTERS/BENCH:
        (p|P)oint guard,
        (s|S)hooting guard,
        (s|S)mall forward,
        (P|p)ower forward,
        center(/Center)
        'the second unit' --> bench
        (1k+ tokens in train)
    !+ [pending] verbalized edge for led_by

2. others:
    + [done] team --> DIFFs
    + [optional] remove N/A players and nodes
    !+ [pending] WINNER
    !+ [pending] STAR/MVP
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
    for idx, rcd in enumerate(records):
        node2idx[rcd] = idx
        value, field, rcd_type, ha = rcd.split(DELIM)
        meta = DELIM.join([field, rcd_type, ha])
        meta2idx[meta] = idx  #! NOTE: meta may not be unique for N/A and <blank> players

        entity2nodes.setdefault(field, {rcd_type: (value, rcd)})
        entity2nodes[field][rcd_type] = (value, rcd)

        if rcd_type == 'TEAM-NAME':
            ha2team[ha] = rcd
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

    edges = {}
    for t in rcd_types:
        left_val, left_node = entity2nodes[left][t]
        left_idx = node2idx[left_node]
        right_val, right_node = entity2nodes[right][t]
        right_idx = node2idx[right_node]

        #! NOTE: (i, j) is an edge i --> j with label '>' if val(i) > val(j), else '='
        if left_val == 'N/A':
            if right_val.isdigit():
                # right > left
                edges[(right_idx, left_idx)] = '>'
                if direction == 'two':
                    edges[(left_idx, right_idx)] = '<'
            else:
                # right = left
                edges[(right_idx, left_idx)] = '='
                edges[(left_idx, right_idx)] = '='
        elif right_val == 'N/A':
            # left > right
            edges[(left_idx, right_idx)] = '>'
            if direction == 'two':
                edges[(right_idx, left_idx)] = '<'
        else:
            if int(left_val) > int(right_val):
                # left > right
                edges[(left_idx, right_idx)] = '>'
                if direction == 'two':
                    edges[(right_idx, left_idx)] = '<'

            elif int(left_val) < int(right_val):
                # right > left
                edges[(right_idx, left_idx)] = '>'
                if direction == 'two':
                    edges[(left_idx, right_idx)] = '<'
            else:
                # right = left
                edges[(right_idx, left_idx)] = '='
                edges[(left_idx, right_idx)] = '='

    return edges


def _get_team_player(ha2player, ha2team, node2idx):
    """
    :param ha2player: [dict] {'HOME/AWAY': [player_name_records]}
    :param ha2team  : [dict] {'HOME/AWAY': [team_name_records]}
    :param node2idx : [dict] {rcd: sample.index(rcd)}
    :return:
    """
    #! NOTE: undirected edges with the same label
    #? TODO: two different labels
    label = 'has'
    edges = {}
    for ha in ['HOME', 'AWAY']:
        team = ha2team[ha]
        team_id = node2idx[team]
        for p in ha2player[ha]:
            player_id = node2idx[p]
            edges[(team_id, player_id)] = label
            edges[(player_id, team_id)] = label
    return edges


def _get_other_edges(node2idx, meta2idx, entity2nodes, ha2player, ha2team):
    """
        node2idx     [dict]: {rcd: sample.index(rcd)}
        meta2idx     [dict]: {"field|rcd_type|ha": sample.index(rcd)}
        entity2nodes [dict]: {entity: {rcd_type: (value, rcd)}}
        ha2player    [dict]: {'HOME/AWAY': [player_name_records]}
        ha2team      [dict]: {'HOME/AWAY': [team_name_records]}
    """
    label = 'has'
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
                edges[(player_id, idx)] = label
                edges[(idx, player_id)] = label

        # -- TEAM_NAME to record edges -- #
        team = ha2team[ha]  # TEAM_NAME
        team_id = node2idx[team]
        team_records = entity2nodes[team.split(DELIM)[0]]
        # -1 is the TEAM_NAME rcd_type
        for key in line_numkeys + line_diffkeys + line_otherkeys[:-1]:
            node = team_records[key][1]
            idx = node2idx[node]
            edges[(idx, team_id)] = label
            edges[(team_id, idx)] = label

    return edges


def _get_lead_player(ha2player, entity2nodes):
    lead_players = {
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
        lead = [(None, 0)]
        start_lead = [(None, 0)]
        bench_lead = [(None, 0)]
        for player in ha2player[ha]:
            name = player.split(DELIM)[0]
            records = entity2nodes[name]
            points = records['PTS'][0]
            start_position = records['START_POSITION'][0]
            start_or_bench = 'BENCH' if start_position == 'N/A' else 'START'
            if points == 'N/A':
                continue
            else:
                points = int(points)

                if points > lead[0][1]:
                    lead = [(player, points)]
                elif points == lead[0][1]:
                    lead.append((player, points))

                if start_or_bench == 'START':
                    if points > start_lead[0][1]:
                        start_lead = [(player, points)]
                    elif points == start_lead[0][1]:
                        start_lead.append((player, points))
                else:
                    if points > bench_lead[0][1]:
                        bench_lead = [(player, points)]
                    elif points == bench_lead[0][1]:
                        bench_lead.append((player, points))

        lead_players[ha]['START'] = [x for x in start_lead if x[0] is not None]
        lead_players[ha]['BENCH'] = [x for x in bench_lead if x[0] is not None]
        lead_players[ha]['ALL'] = [x for x in lead if x[0] is not None]

    return lead_players


def _get_lead_edges(node2idx, meta2idx, entity2nodes, ha2player, ha2team):
    # TODO: current version has TEAM-PTS_SUM-START led_by PLAYER_NAME, change it

    lead_players = _get_lead_player(ha2player, entity2nodes)
    edges = {}
    label = 'led_by'

    for ha in ['HOME', 'AWAY']:
        team = ha2team[ha]  # TEAM_NAME
        teamname, teamentity, _, _ = team.split(DELIM)
        # print("teamname = {}, teamentity = {}".format(teamname, teamentity))

        team_id = node2idx[team]
        start_meta = DELIM.join([teamentity, 'TEAM-PTS_SUM-START', ha])
        start_id = meta2idx[start_meta]
        bench_meta = DELIM.join([teamentity, 'TEAM-PTS_SUM-BENCH', ha])
        bench_id = meta2idx[bench_meta]

        # print("start_meta = {}, bench_meta = {}".format(start_meta, bench_meta))

        triple = lead_players[ha]
        all_leaders = triple['ALL']
        start_leaders = triple['START']
        bench_leaders = triple['BENCH']

        # print("all_leaders = {}\n start_leaders = {}\n bench_leaders = {}\n"
        #       .format(all_leaders, start_leaders, bench_leaders))

        for player, _ in all_leaders:
            # print("all leader = {}".format(player))
            player_id = node2idx[player]
            edges[(team_id, player_id)] = label
            # edges[(player_id, team_id)] = label

        for player, _ in start_leaders:
            # print("start leader = {}".format(player))
            player_id = node2idx[player]
            edges[(start_id, player_id)] = label
            # edges[(player_id, start_id)] = label

        for player, _ in bench_leaders:
            # print("bench leader = {}".format(player))
            # try:
            player_id = node2idx[player]
            # except:
            #     import pdb
            #     pdb.set_trace()
            edges[(bench_id, player_id)] = label
            # edges[(player_id, bench_id)] = label

    return edges


def _sanity_check(edges, records):
    import pandas as pd
    temp = {'left':[], 'label':[], 'right':[]}
    for (left, right), label in edges.items():
        temp['left'].append(records[left])
        temp['right'].append(records[right])
        temp['label'].append(label)

    # with pd.option_context('display.max_rows', None, 'display.max_columns', None):
    print(pd.DataFrame(temp).to_string())
    import pdb
    pdb.set_trace()


#! NOTE: new_dataset means cleaned, with graph edge information added
BASE="/mnt/cephfs2/nlp/hongmin.wang/table2text/boxscore-data"
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='clean')
    parser.add_argument('--direction', required=True, choices=['one', 'two'],
                        help='if use undirected edges between pair of statistics, e.g. PTS vs PTS. Default: False')
    parser.add_argument('--dataset', required=True, choices=['inlg', 'aaai'],
                        help='which dataset to take in')
    args = parser.parse_args()

    if args.dataset == 'aaai':
        line_otherkeys.extend(['TEAM-NEXT_NAME', 'TEAM-NEXT_CITY', 'TEAM-NEXT_DAY', 'TEAM-NEXT_HA'])

    for DATA in ['train', 'valid', 'test']:
        fname = "{}/scripts_{}/new_dataset/new_ncpcc/{}/src_{}.norm.trim.ncp.full.txt"\
            .format(BASE, args.dataset, DATA, DATA)
        fout = "{}/scripts_{}/new_dataset/new_ncpcc/{}/edges_{}.ncp.new.direction-{}.jsonl"\
            .format(BASE, args.dataset, DATA, DATA, args.direction)

        with io.open(fname, 'r', encoding='utf-8') as fin, jsonlines.open(fout, 'w') as writer:

            inputs = fin.read().strip().split('\n')
            for sample in tqdm(inputs):
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

                # _sanity_check(edges, records)

                team_player_edges = _get_team_player(ha2player, ha2team, node2idx)
                edges.update(team_player_edges)

                other_edges = _get_other_edges(node2idx, meta2idx, entity2nodes, ha2player, ha2team)
                edges.update(other_edges)

                lead_edge = _get_lead_edges(node2idx, meta2idx, entity2nodes, ha2player, ha2team)
                edges.update(lead_edge)

                # _sanity_check(edges, records)

                combo = {}
                for (left, right), lab in edges.items():
                    key = '{},{}'.format(left, right)
                    combo[key] = lab
                writer.write(combo)