import re, io, copy, os, sys, pprint, jsonlines, pdb
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
# team - player: plays_for led_by
# team <-> team and player <-> player: same rcd_type: >=<
# Edges:
1. START vs BENCH:
    + Teams <-has-> START/BENCH <-has-> Players
    + START/BENCH <-lead-> Best_Player (or Best_Player PTS)
    + Teams <-lead-> Best_Player (or Best_Player PTS)
    + START/BENCH <-has-> SUM_PTS
    + START SUM_PTS <-compare-> BENCH SUM_PTS for each team
    + START/BENCH SUM_PTS <-compare-> START/BENCH SUM_PTS across teams
    !+ (Is this necessary?) START: (p|P)oint guard, (s|S)hooting guard, (s|S)mall forward, (P|p)ower forward, center(/Center)

2. TODOs:
    + DIFFs not decided
    + remove N/A players and nodes

# others:
1. HOME/AWAY
2. WINNER
3. STAR/MVP

"""

line_numkeys = [
    'TEAM-PTS',
    'TEAM-PTS_HALF-FIRST', 'TEAM-PTS_HALF-SECOND',
    'TEAM-PTS_QTR1', 'TEAM-PTS_QTR2', 'TEAM-PTS_QTR3', 'TEAM-PTS_QTR4',
    'TEAM-PTS_QTR-1to3', 'TEAM-PTS_QTR-2to4',
    'TEAM-PTS_SUM-BENCH', 'TEAM-PTS_SUM-START',
    'TEAM-FG3A', 'TEAM-FG3M', 'TEAM-FG3_PCT',
    'TEAM-FGA', 'TEAM-FGM', 'TEAM-FG_PCT',
    'TEAM-FTA', 'TEAM-FTM', 'TEAM-FT_PCT',
    'TEAM-REB', 'TEAM-OREB', 'TEAM-DREB',
    'TEAM-AST', 'TEAM-BLK', 'TEAM-STL', 'TEAM-TOV',
]
print("line_numkeys: {}".format(len(line_numkeys)))

line_otherkeys = [
    'TEAM-WINS', 'TEAM-LOSSES',
    'TEAM-ALIAS', 'TEAM-ARENA', 'TEAM-CITY', 'TEAM-NAME',
    'TEAM-NEXT_NAME', 'TEAM-NEXT_CITY', 'TEAM-NEXT_DAY', 'TEAM-NEXT_HA'
]
print("line_otherkeys: {}".format(len(line_otherkeys)))

temp = [
    'TEAM-PTS_TOTAL_DIFF',
    'TEAM-PTS_HALF_DIFF-FIRST', 'TEAM-PTS_HALF_DIFF-SECOND',
    'TEAM-PTS_QTR_DIFF-FIRST', 'TEAM-PTS_QTR_DIFF-SECOND', 'TEAM-PTS_QTR_DIFF-THIRD', 'TEAM-PTS_QTR_DIFF-FOURTH',
]
print("temp: {}".format(len(temp)))

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
        entity2nodes [dict]: {entity: {rcd_type:(value, rcd)}}
        player_pairs [dict]: {'HOME/AWAY': [(p_i, p_j)]}
        team_pairs   [dict]: {'HOME/AWAY': [(t_i, t_j)]}
    """
    node2idx = {}
    entity2nodes = {}
    ha2player = {'HOME':[], 'AWAY': []}
    ha2team = {'HOME': None, 'AWAY':None}
    for idx, rcd in enumerate(records):
        node2idx[rcd] = idx
        value, field, rcd_type, ha = rcd.split(DELIM)
        entity2nodes.setdefault(field, {rcd_type: (value, rcd)})
        entity2nodes[field][rcd_type] = (value, rcd)
        if rcd_type == 'TEAM-NAME':
            ha2team[ha] = rcd
        if rcd_type == 'PLAYER_NAME':
            ha2player[ha].append(rcd)

    player_pairs = {'HOME': [], 'AWAY':[]}
    for k, player in ha2player.items():
        player = [rcd.split(DELIM)[0] for rcd in player]
        player_pairs[k].extend(combinations(player, 2))
    return node2idx, entity2nodes, player_pairs, ha2player, ha2team

def _get_pairwise(left, right, rcd_types, entity2nodes, node2idx):
    edges = {}
    for t in rcd_types:
        left_val, left_node = entity2nodes[left][t]
        left_idx = node2idx[left_node]
        right_val, right_node = entity2nodes[right][t]
        right_idx = node2idx[right_node]

        if left_val == 'N/A':
            if right_val.isdigit():
                left2right = '<'
                right2left = '>'
            else:
                left2right = '='
                right2left = '='
        elif right_val == 'N/A':
            left2right = '>'
            right2left = '<'
        else:
            if int(left_val) > int(right_val):
                left2right = '>'
                right2left = '<'
            elif int(left_val) < int(right_val):
                left2right = '<'
                right2left = '>'
            else:
                left2right = '='
                right2left = '='

        edges[(left_idx, right_idx)] = left2right
        edges[(right_idx, left_idx)] = right2left
    return edges

def _get_team_player(ha2player, ha2team, node2idx):
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

BASE="/mnt/cephfs2/nlp/hongmin.wang/table2text/boxscore-data"
for DATA in ['train', 'valid', 'test']:

    fname = "{}/scripts_aaai/new_dataset/new_ncpcc/{}/src_{}.norm.trim.ncp.full.txt".format(BASE, DATA, DATA)
    fout = "{}/scripts_aaai/new_dataset/new_ncpcc/{}/edges_{}.ncp.jsonl".format(BASE, DATA, DATA)

    with io.open(fname, 'r', encoding='utf-8') as fin, jsonlines.open(fout, 'w') as writer:

        inputs = fin.read().strip().split('\n')
        for sample in tqdm(inputs):
            temp = {}
            records = sample.strip().split()
            node2idx, entity2nodes, player_pairs, ha2player, ha2team = _get_lookups(records)
            home = ha2team['HOME'].split(DELIM)[0]
            away = ha2team['AWAY'].split(DELIM)[0]
            team_pair = [(home, away)]
            for pair_list, key_list in zip([player_pairs['HOME'], player_pairs['AWAY'], team_pair], [box_numkeys, box_numkeys, line_numkeys]):
                for left, right in pair_list:
                    temp.update(_get_pairwise(left, right, key_list, entity2nodes, node2idx))

            tmp = _get_team_player(ha2player, ha2team, node2idx)
            temp.update(tmp)
            combo = {}
            for (left, right), lab in temp.items():
                key = '{},{}'.format(left, right)
                combo[key] = lab
            writer.write(combo)