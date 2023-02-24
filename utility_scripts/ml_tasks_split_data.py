import json
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

    # get total distribution of stratification dimensions
    year_dist_abs = defaultdict(int)
    disc_dist_abs = defaultdict(int)
    cls_dist_abs = defaultdict(int)
    for ppr in smpl_packs:
        year_dist_abs[ppr['year']] += len(ppr[sample_key])
        disc_dist_abs[ppr['discipline']] += len(ppr[sample_key])
        for smpl in ppr[sample_key]:
            cls_dist_abs[smpl[label_key]] += 1
    smpls_total = sum(n for n in year_dist_abs.values())
    year_dist_rel = defaultdict(int)
    disc_dist_rel = defaultdict(int)
    cls_dist_rel = defaultdict(int)
    print(year_dist_abs)
    print(disc_dist_abs)
    print(cls_dist_abs)

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
