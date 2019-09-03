#!/usr/bin/env bash
# echo "clean: clean --> clean"
# python clean.py
# echo "add_feat (add special nodes): new_jsonl, new_clean --> new_extend"
# python add_feat.py
# for DATA in train valid test
# do
#     cp ../new_dataset/new_clean/$DATA/tgt_$DATA.norm.mwe.txt ../new_dataset/new_extend/$DATA/
# done

# echo "extract_outline_remove_unground"
# python extract_outline_remove_unground.py
# for DATA in train valid test
# do
#     mkdir -p ../new_dataset/new_extend_addsp/$DATA
#     mv ../new_dataset/new_extend/$DATA/*addsp* ../new_dataset/new_extend_addsp/$DATA/
#     cp ../new_dataset/new_extend/$DATA/tgt_$DATA.norm.mwe.trim.txt ../new_dataset/new_extend_addsp/$DATA/
#     cp ../new_dataset/new_extend_addsp/$DATA/src_$DATA.norm.ext.addsp.txt ../new_dataset/new_extend/$DATA/
# done
# ls -l ../new_dataset/new_extend_addsp/*

# echo "finalize"
# python finalize.py

# for DATA in train valid test
# do
#     echo "copying files to new_ws2017"
#     mkdir -p ../new_dataset/new_ws2017_v2
#     mv ../new_dataset/new_extend/$DATA/$DATA.trim.ws.json ../new_dataset/new_ws2017_v2/$DATA.json

#     echo "copying files to ncpcc"
#     mkdir -p ../new_dataset/new_ncpcc/$DATA
#     mv ../new_dataset/new_extend/$DATA/*.ncp* ../new_dataset/new_ncpcc/$DATA
#     mv ../new_dataset/new_extend/$DATA/*.nona* ../new_dataset/new_ncpcc/$DATA
#     cp ../new_dataset/new_extend/$DATA/$DATA\_content_plan_tks.txt ../new_dataset/new_ncpcc/$DATA
#     cp ../new_dataset/new_extend/$DATA/tgt_$DATA.norm.mwe.trim.txt ../new_dataset/new_ncpcc/$DATA
#     cp ../new_dataset/new_extend/$DATA/$DATA\_ptrs.txt ../new_dataset/new_ncpcc/$DATA
#     cp ../new_dataset/new_extend/$DATA/$DATA.trim.json ../new_dataset/new_ncpcc/$DATA

# done

# ls -l ../new_dataset/new_extend/*
# ls -l ../new_dataset/new_ws2017_v2/
# ls -l ../new_dataset/new_ncpcc/*

# echo "finalize_addsp"
# python finalize_addsp.py

# echo "constructing graph"
# for EDGE in big2small small2big
# do
# python table2graph.py --dataset aaai --direction $EDGE
# done

echo "template based"
python template.py --dataset aaai

echo " ****** Template Evaluation ****** "
BASE=/mnt/cephfs2/nlp/hongmin.wang/table2text/boxscore-data/scripts_aaai/new_dataset/new_extend_addsp
cd /mnt/cephfs2/nlp/hongmin.wang/table2text/boxscore-data/scripts_aaai/evaluate
for DATA in valid test
do
echo " ****** RS CS CO ****** "
python evaluate.py --path $BASE --dataset $DATA --hypo ../process/$DATA.rule.txt
echo " ****** BLEU ****** "
TGT=$BASE/$DATA/tgt_$DATA.norm.mwe.trim.txt
perl ~/table2text/multi-bleu.perl $TGT < ../process/$DATA.rule.txt
done
cd /mnt/cephfs2/nlp/hongmin.wang/table2text/boxscore-data/scripts_aaai/process
