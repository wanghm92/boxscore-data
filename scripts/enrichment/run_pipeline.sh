#!/usr/bin/env bash
#echo "add_feat"
#python add_feat.py
#echo "extract_outline_ext"
#python extract_outline_ext.py
#echo "ncp_format"
#python ncp_format.py

#echo "copying files to new_ws2017"
#cp ../new_dataset/new_extend/train/train.trim.json ../new_dataset/new_ws2017/train.json
#cp ../new_dataset/new_extend/test/test.trim.json ../new_dataset/new_ws2017/test.json
#cp ../new_dataset/new_extend/valid/valid.trim.json ../new_dataset/new_ws2017/valid.json
#cp ../new_dataset/new_extend/train/train_ptrs.txt ../new_dataset/new_ws2017/train_ptrs.txt
#ls -l ../new_dataset/new_ws2017/

echo "copying files to ncpcc"
cp ../new_dataset/new_extend/train/*.ncp* ../new_dataset/new_ncpcc/train
cp ../new_dataset/new_extend/test/*.ncp* ../new_dataset/new_ncpcc/test
cp ../new_dataset/new_extend/valid/*.ncp* ../new_dataset/new_ncpcc/valid

cp ../new_dataset/new_extend/train/train_content_plan_tks.txt ../new_dataset/new_ncpcc/train
cp ../new_dataset/new_extend/test/test_content_plan_tks.txt ../new_dataset/new_ncpcc/test
cp ../new_dataset/new_extend/valid/valid_content_plan_tks.txt ../new_dataset/new_ncpcc/valid

cp ../new_dataset/new_extend/train/tgt_train.norm.filter.mwe.trim.txt ../new_dataset/new_ncpcc/train
cp ../new_dataset/new_extend/test/tgt_test.norm.filter.mwe.trim.txt ../new_dataset/new_ncpcc/test
cp ../new_dataset/new_extend/valid/tgt_valid.norm.filter.mwe.trim.txt ../new_dataset/new_ncpcc/valid

cp ../new_dataset/new_extend/train/train_ptrs.txt ../new_dataset/new_ncpcc/train
cp ../new_dataset/new_extend/test/test_ptrs.txt ../new_dataset/new_ncpcc/test
cp ../new_dataset/new_extend/valid/valid_ptrs.txt ../new_dataset/new_ncpcc/valid

ls -l ../new_dataset/new_ncpcc/*