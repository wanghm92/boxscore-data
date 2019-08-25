import re, io, copy, os, sys, pprint, jsonlines, pdb, argparse
from tqdm import tqdm
from collections import Counter, OrderedDict
from text2num import text2num
from pprint import pprint
from itertools import combinations
DELIM = "￨"
NA = 'N/A'

#! NOTE: new_dataset means cleaned, with graph edge information added
BASE="/mnt/cephfs2/nlp/hongmin.wang/table2text/boxscore-data"
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='clean')
    parser.add_argument('--plan', type=str, default=None,
                        help='content plan by ncpcc stage 1')
    args = parser.parse_args()

    # for DATA in ['train', 'valid', 'test']:
        # dataset = 'inlg'
        # print("Checking {} set".format(DATA))

    dup_cnt = 0
    total_cnt = 0
    num_cnt = 0
    nondup_num = 0
    # cpname = "{}/scripts_{}/new_dataset/new_ncpcc/{}/{}_content_plan_tks.txt".format(BASE, dataset, DATA, DATA)
    dup_vals = []
    dup_types = []
    cpname = args.plan
    with io.open(cpname, 'r', encoding='utf-8') as cpfin:

        outlines = cpfin.read().strip().split('\n')            # inputs = fin.read().strip().split('\n')
        for plan in tqdm(outlines):
            records = plan.strip().split()
            total_cnt += len(records)
            num_only = [x for x in records if x.split(DELIM)[0].isdigit()]
            num_cnt += len(num_only)
            nondup_num += len(list(set(num_only)))
            dups = [x for x, c in Counter(records).most_common() if c > 1]
            dup_cnt += len(dups)
            for d in dups:
                value, _, rcd_type, _ = d.split(DELIM)
                dup_vals.append(value)
                dup_types.append(rcd_type)

    non_dup = total_cnt - dup_cnt
    print("{} out of {} ({:0.3f}) are duplicates".format(dup_cnt, total_cnt, 100.0*dup_cnt/total_cnt))
    print("{} ({}) out of {} ({}), {:0.3f} ({:0.3f}) are numbers".format(
        nondup_num, num_cnt, non_dup, total_cnt, 100.0*nondup_num/non_dup, 100.0*num_cnt/total_cnt))

        # print("Common dup types: \n")
        # pprint(Counter(dup_types))
        # print("Common dup values: \n")
        # pprint(Counter(dup_vals))
