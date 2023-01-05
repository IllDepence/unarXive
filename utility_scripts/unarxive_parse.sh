#!/bin/bash
#SBATCH --job-name=unarXive_parsing_PARSE_FILTER
#SBATCH --mail-type=END,FAIL          # (NONE, BEGIN, END, FAIL, ALL)
#SBATCH --mail-user=tarek.saier@kit.edu
#SBATCH --ntasks=1                    # num CPUs
#SBATCH --time=72:00:00               # hrs:min:sec
#SBATCH --mem=64gb
#SBATCH --output=unarxive_parse_PARSE_FILTER_%j.log   # Std out&err log
#SBATCH --partition=single
pwd; hostname; date

echo "Running unarXive parsing"

echo "creating output dir: PARSE_FILTER"
mkdir "/pfs/work7/workspace/scratch/ys8950-unarXive2022/arxiv-parsed/PARSE_FILTER"
echo "parse filter: 'arXiv_src_PARSE_FILTER'"
echo "starting parse script"
enroot start -m /pfs/work7/workspace/scratch/ys8950-unarXive2022/arxiv-src:/arxiv-src -m /pfs/work7/workspace/scratch/ys8950-unarXive2022/arxiv-parsed:/arxiv-parsed -m /home/kit/aifb/ys8950/unarXive_code_repo:/unarXive_code_repo --rw debian_10 bash -c "source /venv/bin/activate;python3 unarXive_code_repo/prepare.py /arxiv-src /arxiv-parsed/PARSE_FILTER /unarXive_code_repo/arxiv-metadata-oai-snapshot_230101.sqlite arXiv_src_PARSE_FILTER"
echo "finished"

date
