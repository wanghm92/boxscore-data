from __future__ import division
import re, io, copy, os, sys, argparse, json, pdb, jsonlines, shutil, jsonlines
from tqdm import tqdm
from pprint import pprint
from collections import Counter, OrderedDict
sys.path.insert(0, '../process/')
sys.path.insert(0, '.')
from evaluate import compute_rg_cs_co
from pyxdameraulevenshtein import normalized_damerau_levenshtein_distance

DELIM = "￨"

def main(args):

    input_files = [
        "src_%s.norm.trim.ncp.full.txt" % args.dataset,
        "%s_content_plan_tks.txt" % args.dataset,
    ]

    BASE_DIR = os.path.join(args.path, "{}".format(args.dataset))
    gold_src, gold_plan = [os.path.join(BASE_DIR, f) for f in input_files]

    with io.open(gold_src, 'r', encoding='utf-8') as fin_src, \
            io.open(gold_plan, 'r', encoding='utf-8') as fin_cp, \
            io.open(args.plan, 'r', encoding='utf-8') as fin:

        inputs = fin_src.read().strip().split('\n')
        gold_outlines = fin_cp.read().strip().split('\n')
        planner_output = fin.read().strip().split('\n')

        if not len(inputs) == len(gold_outlines) == len(planner_output):
            print("# Input tables = {}; # Gold Content Plans = {}; # Test Content Plans  = {}"
                    .format(len(inputs), len(gold_outlines), len(planner_output)))
            raise RuntimeError("Inputs must have the same number of samples (aligned 1 per line)")

        # ------ non-BLEU metrics ------ #
        print("\n *** Metrics ***\n")
        planner_output = [[i for i in x.strip().split() if i.split(DELIM)[0].isdigit()] for x in planner_output]
        print("\n *** Planned vs Gold ***\n")
        compute_rg_cs_co(gold_outlines, planner_output, inputs)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='clean')
    parser.add_argument('--path', type=str, required=True,
                        help='directory of src/tgt_train/valid/test.txt files')
    parser.add_argument('--dataset', type=str, default='valid', choices=['valid', 'test'])
    parser.add_argument('--plan', type=str, default=None,
                        help='content plan by ncpcc stage 1')
    args = parser.parse_args()

    print("Evaluating {} set".format(args.dataset))
    main(args)