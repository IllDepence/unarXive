import json
import math
import sys
from collections import defaultdict


def split(fn):
    with open(fn) as f:
        smpl_packs = json.load(f)

    dev_size_min_smpls = 1000
    test_size_min_smpls = 1000

    for key in ['imrad_smpls', 'citrec_smpls']:
        if key in smpl_packs[0]:
            sample_key = key
    for key in ['label', 'cited_doc']:
        if key in smpl_packs[0][sample_key][0]:
            label_key = key

    # calculate sample allocation goals
    dists_abs = {}
    fill_min_dev = {}
    fill_min_test = {}
    for strat in ['year', 'discipline', label_key]:
        dists_abs[strat] = defaultdict(int)
        fill_min_dev[strat] = defaultdict(int)
        fill_min_test[strat] = defaultdict(int)
    # # determine total distribution of stratification dimensions
    for ppr in smpl_packs:
        dists_abs['year'][ppr['year']] += len(ppr[sample_key])
        dists_abs['discipline'][ppr['discipline']] += len(ppr[sample_key])
        for smpl in ppr[sample_key]:
            dists_abs[label_key][smpl[label_key]] += 1
    # # determine relative distribution of stratification dimensions
    # # and calculate allocation minima
    smpls_total = sum(n for n in dists_abs['year'].values())
    for strat in ['year', 'discipline', label_key]:
        for k, v in dists_abs[strat].items():
            rel_size = v / smpls_total
            fill_min_dev[strat][k] = math.ceil(
                dev_size_min_smpls * rel_size
            )
            fill_min_test[strat][k] = math.ceil(
                test_size_min_smpls * rel_size
            )
    import pprint
    pprint.pprint(fill_min_dev)

    # TODO
    # - parameters for abs/rel size of val & test set (train is rest)
    # - determine min number of samples per
    #     - year
    #     - discipline
    #     - target label
    #   that should be included in val & test respectively
    # - shuffle data
    # - fill val & test
    #    - insert sample if across all stratification goals, min is not reached
    #    - if above isn’t enough to fill val & test: re-run w/ less strict rule
    # - rest goes into train


if __name__ == '__main__':
    split(sys.argv[1])
