#!/usr/bin/env bash
echo "clean"
python clean.py
echo "filter train, valid, test"
python pre_filter.py --dataset train
python pre_filter.py --dataset valid
python pre_filter.py --dataset test
echo "content plan and trim"
python extract_outline.py
echo "finalize"
python ncp_format.py
