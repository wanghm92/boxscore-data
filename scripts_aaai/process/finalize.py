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

prefix = "<unk>￨<blank>￨<blank>￨<blank> <blank>￨<blank>￨<blank>￨<blank> <s>￨<blank>￨<blank>￨<blank> </s>￨<blank>￨<blank>￨<blank>"
assert len(prefix.split()) == 4

def _to_reserve(rcd):
    return rcd.split(DELIM)[2] == 'START_POSITION' or (rcd.split(DELIM)[0] != 'N/A' and rcd.split(DELIM)[1] != 'N/A')

def main(args, DATASET):
    BASE_DIR = os.path.join(args.dir, "{}".format(DATASET))

    input_files = [
        "src_%s.norm.trim.txt" % DATASET,
        "%s_content_plan_ids.txt" % DATASET,
        "%s_content_plan_tks.txt" % DATASET,
        "%s_ptrs.txt" % DATASET,
        "tgt_%s.norm.mwe.trim.txt" % DATASET,
        "%s.trim.json" % DATASET
    ]

    trim_src, cp_in_ids, cp_in_tks, ptrs_in, clean_tgt_trim, js_trim = [os.path.join(BASE_DIR, f) for f in input_files]

    output_files = [
        "src_%s.norm.trim.nona.txt" % DATASET,
        "src_%s.norm.trim.ncp.full.txt" % DATASET,
        "src_%s.norm.trim.ncp.nona.txt" % DATASET,
        "%s_content_plan_ids.nona.txt" % DATASET,
        "%s_content_plan_ids.ncp.full.txt" % DATASET,
        "%s_content_plan_ids.ncp.nona.txt" % DATASET,
        "tgt_%s.norm.tk.trim.txt" % DATASET,
        "%s.trim.ws.json" % DATASET
    ]

    src_out_nona, src_out_ncp_full, src_out_ncp_nona, \
    cp_out_ids_nona, cp_out_ids_ncp_full, cp_out_ids_ncp_nona,\
    clean_tgt_trim_tk, js_trim_tk = \
        [os.path.join(BASE_DIR, f) for f in output_files]  #! NOTE: last two are for ws17

    with io.open(trim_src, 'r', encoding='utf-8') as fin_src, \
            io.open(cp_in_ids, 'r', encoding='utf-8') as fin_cp_ids, \
            io.open(cp_in_tks, 'r', encoding='utf-8') as fin_cp_tks, \
            io.open(ptrs_in, 'r', encoding='utf-8') as fin_ptr, \
            io.open(js_trim, 'r', encoding='utf-8') as fin_js, \
            io.open(src_out_nona, 'w+', encoding='utf-8') as fout_src_nona, \
            io.open(src_out_ncp_full, 'w+', encoding='utf-8') as fout_src_ncp_full, \
            io.open(src_out_ncp_nona, 'w+', encoding='utf-8') as fout_src_ncp_nona, \
            io.open(cp_out_ids_nona, 'w+', encoding='utf-8') as fout_cp_nona, \
            io.open(cp_out_ids_ncp_full, 'w+', encoding='utf-8') as fout_cp_ncp_full, \
            io.open(cp_out_ids_ncp_nona, 'w+', encoding='utf-8') as fout_cp_ncp_nona, \
            io.open(js_trim_tk, 'w+', encoding='utf-8') as fout_js:

        source = fin_src.read().strip().split('\n')
        content_plan_ids = fin_cp_ids.read().strip().split('\n')
        content_plan_tks = fin_cp_tks.read().strip().split('\n')
        pointers = fin_ptr.read().strip().split('\n')
        tables = json.load(fin_js)

        print(len(source))
        print(len(content_plan_ids))
        print(len(content_plan_tks))
        print(len(pointers))
        print(len(tables))

        assert len(source) == len(content_plan_ids) == len(pointers) == len(tables)

        tokenized_tables = []
        for src_full, cp_ids, cp_tks, ptr, tbl in \
                tqdm(zip(source, content_plan_ids, content_plan_tks, pointers, tables)):
            assert len(cp_ids.split()) == len(cp_tks.split()) == len(ptr.split())

            # --- processing input records --- #
            # add 4 special tokens in front for NCP (as they designed)
            ncp_src_full = ' '.join([prefix, src_full])
            fout_src_ncp_full.write("{}\n".format(ncp_src_full))

            # remove N/A records from src
            #! NOTE: START_POSITION is N/A for bench players
            src_nona = [rcd for rcd in src_full.split() if _to_reserve(rcd)]
            fout_src_nona.write("{}\n".format(' '.join(src_nona)))

            # add 4 special tokens in front of non-N/A records for NCP
            ncp_src_nana = ' '.join([prefix, ' '.join(src_nona)])
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

            # --- processing json tables --- #
            tmp = copy.deepcopy(tbl)
            tokens = []
            for mwe in tbl['summary']:
                tokens.extend(mwe.split('_'))
            tmp['summary'] = tokens

            first_names = copy.deepcopy(tbl['box_score']['FIRST_NAME'])
            for idx, n in tbl['box_score']['FIRST_NAME'].items():
                n.replace('.', '')
                first_names[idx] = n

            tmp['box_score']['<blank>'] = {str(k): '<blank>' for k in range(len(tmp['box_score']['FIRST_NAME']))}

            tmp['box_score']['FIRST_NAME'] = first_names

            tokenized_tables.append(tmp)

        print("dumping tokenized table ...")
        json.dump(tokenized_tables, fout_js)

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