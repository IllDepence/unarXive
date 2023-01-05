#!/bin/bash
for yy in `ls /pfs/work7/workspace/scratch/ys8950-unarXive2022/arxiv-src/ | grep -Po 'src_\d\d' | grep -Po '\d\d' | sort | uniq`
do
	cp unarxive_parse.sh unarxive_parse_${yy}.sh
	sed -i -E "s/PARSE_FILTER/${yy}/g" unarxive_parse_${yy}.sh
	sbatch unarxive_parse_${yy}.sh
	sleep 0.2
	rm unarxive_parse_${yy}.sh
done
