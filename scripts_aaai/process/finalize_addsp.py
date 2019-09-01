"""
(1) pre-pend 4 special tokens to src
(2) adjust content plan ids
(3) convert final tgt to tokenized version
!(4) [NEW] remove N/A records
"""

import re, io, copy, os, sys, argparse, json, pdb
from tqdm import tqdm
sys.path.insert(0, '../purification/')
from domain_knowledge import Domain_Knowledge
knowledge_container = Domain_Knowledge()
DELIM = "￨"

ncp_prefix = "<unk>￨<blank>￨<blank>￨<blank> <blank>￨<blank>￨<blank>￨<blank> <s>￨<blank>￨<blank>￨<blank> </s>￨<blank>￨<blank>￨<blank>"
assert len(ncp_prefix.split()) == 4

def _to_reserve(rcd):
    return rcd.split(DELIM)[2] == 'START_POSITION' or (rcd.split(DELIM)[0] != 'N/A' and rcd.split(DELIM)[1] != 'N/A')

def main(args, DATASET):
    BASE_DIR = os.path.join(args.dir, "{}".format(DATASET))

    input_files = [
        "src_%s.norm.trim.addsp.txt" % DATASET,
        "%s_content_plan_ids.addsp.txt" % DATASET,
        "%s_content_plan_tks.addsp.txt" % DATASET,
        "%s_ptrs.addsp.txt" % DATASET,  # for checking only
    ]

    trim_src, cp_in_ids, cp_in_tks, ptrs_in = [os.path.join(BASE_DIR, f) for f in input_files]

    output_files = [
        "src_%s.norm.trim.addsp.nona.txt" % DATASET,
        "src_%s.norm.trim.addsp.ncp.full.txt" % DATASET,
        "src_%s.norm.trim.addsp.ncp.nona.txt" % DATASET,
        "%s_content_plan_ids.addsp.nona.txt" % DATASET,
        "%s_content_plan_ids.addsp.ncp.full.txt" % DATASET,
        "%s_content_plan_ids.addsp.ncp.nona.txt" % DATASET,
    ]

    src_out_nona, src_out_ncp_full, src_out_ncp_nona, \
    cp_out_ids_nona, cp_out_ids_ncp_full, cp_out_ids_ncp_nona = \
        [os.path.join(BASE_DIR, f) for f in output_files]  #! NOTE: last two are for ws17

    with io.open(trim_src, 'r', encoding='utf-8') as fin_src, \
            io.open(cp_in_ids, 'r', encoding='utf-8') as fin_cp_ids, \
            io.open(cp_in_tks, 'r', encoding='utf-8') as fin_cp_tks, \
            io.open(ptrs_in, 'r', encoding='utf-8') as fin_ptr, \
            io.open(src_out_nona, 'w+', encoding='utf-8') as fout_src_nona, \
            io.open(src_out_ncp_full, 'w+', encoding='utf-8') as fout_src_ncp_full, \
            io.open(src_out_ncp_nona, 'w+', encoding='utf-8') as fout_src_ncp_nona, \
            io.open(cp_out_ids_nona, 'w+', encoding='utf-8') as fout_cp_nona, \
            io.open(cp_out_ids_ncp_full, 'w+', encoding='utf-8') as fout_cp_ncp_full, \
            io.open(cp_out_ids_ncp_nona, 'w+', encoding='utf-8') as fout_cp_ncp_nona:

        source = fin_src.read().strip().split('\n')
        content_plan_ids = fin_cp_ids.read().strip().split('\n')
        content_plan_tks = fin_cp_tks.read().strip().split('\n')
        pointers = fin_ptr.read().strip().split('\n')

        print(len(source))
        print(len(content_plan_ids))
        print(len(content_plan_tks))
        print(len(pointers))

        assert len(source) == len(content_plan_ids) == len(pointers)

        tokenized_tables = []
        for src_full, cp_ids, cp_tks, ptr in \
                tqdm(zip(source, content_plan_ids, content_plan_tks, pointers)):
            assert len(cp_ids.split()) == len(cp_tks.split()) == len(ptr.split())

            # --- processing input records --- #
            # add 4 special tokens in front for NCP (as they designed)
            ncp_src_full = ' '.join([ncp_prefix, src_full])
            fout_src_ncp_full.write("{}\n".format(ncp_src_full))

            # remove N/A records from src
            #! NOTE: START_POSITION is N/A for bench players
            src_nona = [rcd for rcd in src_full.split() if _to_reserve(rcd)]
            fout_src_nona.write("{}\n".format(' '.join(src_nona)))

            # add 4 special tokens in front of non-N/A records for NCP
            ncp_src_nana = ' '.join([ncp_prefix, ' '.join(src_nona)])
            fout_src_ncp_nona.write("{}\n".format(ncp_src_nana))

            # --- processing content plans --- #
            ncp_cp_ids = [str(int(x) + 4) for x in cp_ids.split()]
            fout_cp_ncp_full.write("{}\n".format(' '.join(ncp_cp_ids)))

            # get record ids out of non-N/A records
            cp_ids_nona = [str(src_nona.index(rcd)) for rcd in cp_tks.split()]
            assert len(cp_ids_nona) == len(ncp_cp_ids)
            fout_cp_nona.write("{}\n".format(' '.join(cp_ids_nona)))

            ncp_cp_ids_nona = [str(int(x) + 4) for x in cp_ids_nona]
            fout_cp_ncp_nona.write("{}\n".format(' '.join(ncp_cp_ids_nona)))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='clean')
    parser.add_argument('--dir', type=str, default='../new_dataset/new_extend_addsp/',
                        help='directory of src/tgt_train/valid/test.txt files')
    args = parser.parse_args()

    for DATASET in ['train', 'valid', 'test']:
        print("Converting to ONMT format: {}".format(DATASET))
        main(args, DATASET)