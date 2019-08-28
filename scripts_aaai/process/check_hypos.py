import re, io, copy, os, sys, pprint, jsonlines, pdb, argparse
from tqdm import tqdm
from collections import Counter, OrderedDict
from text2num import text2num
from pprint import pprint
from itertools import combinations
sys.path.insert(0, '.')
from table2graph import _get_lookups, _get_top_players, box_leadkeys

DELIM = "￨"
NA = 'N/A'
"""
python check_hypos.py --hypo /mnt/cephfs2/nlp/hongmin.wang/table2text/outputs/nbagraph2summary/inlg_outputs/graph_inlg_new_edgedir-small2big_edgeaware-add_edgeaggr-mean_graphfuse-highway_outlayer-add_trl_csl/roto_stage1_inter_graph_inlg_new_edgedir-small2big_edgeaware-add_edgeaggr-mean_graphfuse-highway_outlayer-add_trl_csl.e37.valid.txt
"""

def dedup_list(seq):
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]

#! NOTE: new_dataset means cleaned, with graph edge information added
BASE="/mnt/cephfs2/nlp/hongmin.wang/table2text/boxscore-data"
if __name__ == "__main__":

    goldsrc = "{}/scripts_inlg/new_dataset/new_ncpcc/valid/src_valid.norm.trim.ncp.full.txt".format(BASE)
    goldcp = "{}/scripts_inlg/new_dataset/new_ncpcc/valid/valid_content_plan_tks.txt".format(BASE)
    refname = "/mnt/cephfs2/nlp/hongmin.wang/table2text/outputs/data2text-plan-py/inlg_outputs/mean/best/mean_inlg_dim-256_batch-16_layer-2/roto_stage1_inter_mean_inlg_dim-256_batch-16_layer-2.e31.valid.txt"

    parser = argparse.ArgumentParser(description='clean')
    parser.add_argument('--hypo', type=str, default=None, help='the system output to check')
    args = parser.parse_args()

    # check all three
    counts = {}
    for f, key in zip([goldcp, refname, args.hypo], ['gold', 'ref', 'hypo']):
        print("\n *** processing {}".format(key))
        counts[key] = {
            'total': {
                'counts': 0,
                'repeat': 0
            },
            'number': {
                'counts': 0,
                'nondup': 0
            }
        }
        dup_vals = []
        dup_types = []

        with io.open(f, 'r', encoding='utf-8') as fin:
            outlines = fin.read().strip().split('\n')            # inputs = fin.read().strip().split('\n')

            for plan in tqdm(outlines):
                records = plan.strip().split()
                counts[key]['total']['counts'] += len(records)

                num_only = [x for x in records if x.split(DELIM)[0].isdigit()]
                counts[key]['number']['counts'] += len(num_only)

                counts[key]['number']['nondup'] += len(list(set(num_only)))

                dups = [x for x, c in Counter(records).most_common() if c > 1]
                counts[key]['total']['repeat'] += len(dups)

                for d in dups:
                    value, _, rcd_type, _ = d.split(DELIM)
                    dup_vals.append(value)
                    dup_types.append(rcd_type)

        total_cnt = counts[key]['total']['counts']
        dup_cnt = counts[key]['total']['repeat']
        num_cnt = counts[key]['number']['counts']
        nondup_num = counts[key]['number']['nondup']
        non_dup = total_cnt - dup_cnt

        print("{} out of {} ({:0.3f}%) are duplicates".format(dup_cnt, total_cnt, 100.0*dup_cnt/total_cnt))
        print("{} ({}) out of {} ({}), {:0.3f}% ({:0.3f}%) are numbers".format(
            nondup_num, num_cnt, non_dup, total_cnt, 100.0*nondup_num/non_dup, 100.0*num_cnt/total_cnt))

        print("Common dup types: \n")
        pprint(Counter(dup_types))
        # print("Common dup values: \n")
        # pprint(Counter(dup_vals))

    mentioned = dict.fromkeys(box_leadkeys, None)

    # TODO: check player rankings for identified records
    # compare ref and hypo, given gold
    with io.open(goldcp, 'r', encoding='utf-8') as fgold, \
        io.open(goldsrc, 'r', encoding='utf-8') as fsrc, \
        io.open(refname, 'r', encoding='utf-8') as fref, \
        io.open(args.hypo, 'r', encoding='utf-8') as fhypo:

        gold_otl = fgold.read().strip().split('\n')
        ref_otl = fref.read().strip().split('\n')
        hypo_otl = fhypo.read().strip().split('\n')
        inputs = fsrc.read().strip().split('\n')
        ref_more = 0
        hypo_more = 0
        gold_less = 0
        for gold, ref, hypo, sample in tqdm(zip(gold_otl, ref_otl, hypo_otl, inputs)):
            records = sample.strip().split()
            node2idx, meta2idx, entity2nodes, player_pairs, ha2player, ha2team = _get_lookups(records)
            player_rankings, _, _, _ = _get_top_players(ha2player, entity2nodes, gold, mentioned)
            player2rankings = {'HOME': {}, 'AWAY': {}}
            for ha in ['HOME', 'AWAY']:
                for key in ['ALL', 'BENCH', 'START']:
                    for p in player_rankings['PTS'][ha][key]:
                        if p[0] in player2rankings[ha]:
                            player2rankings[ha][p[0]].append(key)
                        else:
                            player2rankings[ha][p[0]] = [key]

            gold_lookup = dict.fromkeys(gold.strip().split())
            ref_lookup = dict.fromkeys(ref.strip().split())
            hypo_lookup = dict.fromkeys(hypo.strip().split())

            ref_correct = dict.fromkeys([x for x in ref.strip().split() if x in gold_lookup])
            hypo_correct = dict.fromkeys([x for x in hypo.strip().split() if x in gold_lookup])

            ref_better = [x for x in ref_correct if x not in hypo_lookup]
            hypo_better = [x for x in hypo_correct if x not in ref_lookup]
            if len(ref_better) > 0 or len(hypo_better) > 0:
                print("\n *** gold_lookup: ")
                pprint(gold_lookup)
                print("\n *** ref_lookup: ")
                pprint(ref_lookup)
                print("\n *** hypo_lookup: ")
                pprint(hypo_lookup)
                print("\n *** records better identified by ref: {}".format("\n".join(ref_better)))
                print("\n *** records better identified by hypo: {}".format("\n".join(hypo_better)))
                print("\n")

                ref_leads = [x for x in ref_better if x.split(DELIM)[-2] == 'PLAYER_NAME' and (x in player2rankings['HOME'] or x in player2rankings['AWAY'])]
                ref_more += len(ref_leads)
                hypo_leads = [x for x in hypo_better if x.split(DELIM)[-2] == 'PLAYER_NAME' and (x in player2rankings['HOME'] or x in player2rankings['AWAY'])]
                hypo_more += len(hypo_leads)
                gold_miss = [x for x in gold_lookup if x.split(DELIM)[-2] == 'PLAYER_NAME' and (x in player2rankings['HOME'] or x in player2rankings['AWAY']) and not (x in ref_lookup or x in hypo_lookup)]
                gold_less += len(gold_miss)
                # if len(ref_leads)>0 or len(hypo_leads)>0:
                #     import pdb
                #     pdb.set_trace()
        print("ref_more = {}".format(ref_more))
        print("hypo_more = {}".format(hypo_more))
        print("gold_less = {}".format(gold_less))
