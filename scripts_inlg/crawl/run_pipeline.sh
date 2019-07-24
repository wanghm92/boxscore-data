#!/usr/bin/env bash
#echo "parsing htmls and grabbing game stats"
#python get_rotowire.py

echo "preprocessing"
python preproc.py

echo "json2txt"
python new_json2txt.py