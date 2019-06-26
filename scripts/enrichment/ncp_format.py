"""
(1) pre-pend 4 special tokens to src
(2) adjust content plan ids
(3) convert final tgt to tokenized version
"""

import re, io, copy, os, sys, argparse, json, pdb
from tqdm import tqdm
sys.path.insert(0, '../purification/')
from domain_knowledge import Domain_Knowledge
knowledge_container = Domain_Knowledge()

prefix = "<unk>￨<blank>￨<blank>￨<blank> <blank>￨<blank>￨<blank>￨<blank> <s>￨<blank>￨<blank>￨<blank> </s>￨<blank>￨<blank>￨<blank>"
assert len(prefix.split()) == 4

def main(args, DATASET):
    BASE_DIR = os.path.join(args.dir, "{}".format(DATASET))

    input_files = [
        "src_%s.norm.trim.txt" % DATASET,
        "%s_content_plan_ids.txt" % DATASET,
        "%s_ptrs.txt" % DATASET,
        "tgt_%s.norm.filter.mwe.trim.txt" % DATASET,
    ]

    trim_src, cp_in_ids, ptrs_in, clean_tgt_trim = [os.path.join(BASE_DIR, f) for f in input_files]

    output_files = [
        "src_%s.norm.trim.ncp.txt" % DATASET,
        "%s_content_plan_ids.ncp.txt" % DATASET,
        "tgt_%s.norm.filter.tk.trim.txt" % DATASET,
    ]

    src_out, cp_out_ids, clean_tgt_trim_tk = [os.path.join(BASE_DIR, f) for f in output_files]

    with io.open(trim_src, 'r', encoding='utf-8') as fin_src, \
            io.open(cp_in_ids, 'r', encoding='utf-8') as fin_cp, \
            io.open(ptrs_in, 'r', encoding='utf-8') as fin_ptr, \
            io.open(src_out, 'w+', encoding='utf-8') as fout_src, \
            io.open(cp_out_ids, 'w+', encoding='utf-8') as fout_cp:

        source = fin_src.read().strip().split('\n')
        content_plans = fin_cp.read().strip().split('\n')
        pointers = fin_ptr.read().strip().split('\n')
        print(len(source))
        print(len(content_plans))
        print(len(pointers))

        assert len(source) == len(content_plans) == len(pointers)

        for s, c, p in tqdm(zip(source, content_plans, pointers)):
            assert len(c.split()) == len(p.split())

            o = ' '.join([prefix, s])
            fout_src.write("{}\n".format(o))

            cp_plus = [str(int(x) + 4) for x in c.split()]
            fout_cp.write("{}\n".format(' '.join(cp_plus)))

    with io.open(clean_tgt_trim, 'r', encoding='utf-8') as fin, \
            io.open(clean_tgt_trim_tk, 'w+', encoding='utf-8') as fout:
        targets = fin.read().strip().split('\n')
        for summary in targets:
            output = summary.replace('_', ' ')
            fout.write("{}\n".format(output))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='clean')
    parser.add_argument('--dir', type=str, default='../new_dataset/new_extend/',
                        help='directory of src/tgt_train/valid/test.txt files')
    args = parser.parse_args()

    for DATASET in ['train', 'valid', 'test']:
        print("Converting to ONMT format: {}".format(DATASET))
        main(args, DATASET)