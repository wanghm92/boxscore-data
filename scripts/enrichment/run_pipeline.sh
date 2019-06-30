#!/usr/bin/env bash
#echo "add_feat"
#python add_feat.py
#echo "extract_outline_ext"
#python extract_outline_ext.py
#echo "finalize"
#python finalize.py

for DATA in train valid test
do
    echo "copying files to new_ws2017"
    cp ../new_dataset/new_extend/$DATA/$DATA.trim.ws.json ../new_dataset/new_ws2017_v2/$DATA.json

    echo "copying files to ncpcc"
    cp ../new_dataset/new_extend/$DATA/*.ncp* ../new_dataset/new_ncpcc/$DATA
    cp ../new_dataset/new_extend/$DATA/$DATA\_content_plan_tks.txt ../new_dataset/new_ncpcc/$DATA
    cp ../new_dataset/new_extend/$DATA/tgt_$DATA.norm.filter.mwe.trim.txt ../new_dataset/new_ncpcc/$DATA
    cp ../new_dataset/new_extend/$DATA/$DATA\_ptrs.txt ../new_dataset/new_ncpcc/$DATA
done

ls -l ../new_dataset/new_ws2017/
ls -l ../new_dataset/new_ncpcc/*