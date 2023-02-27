import json
import math
import random
import sys
from collections import defaultdict


def split(fn):
    with open(fn) as f:
        smpl_packs = json.load(f)

    dev_size_min_smpls = 1000
    test_size_min_smpls = 1000

    # determine sample and label key
    for key in ['imrad_smpls', 'citrec_smpls']:
        if key in smpl_packs[0]:
            sample_key = key
    for key in ['label', 'cited_doc']:
        if key in smpl_packs[0][sample_key][0]:
            label_key = key

    # calculate sample allocation goals
    dists_abs = {}
    dev_fill_min = {}
    test_fill_min = {}
    dev_fill_curr = {}
    test_fill_curr = {}
    strat_dimensions = ['year', 'discipline', label_key]
    for strat in strat_dimensions:
        dists_abs[strat] = defaultdict(int)
        dev_fill_min[strat] = defaultdict(int)
        test_fill_min[strat] = defaultdict(int)
        dev_fill_curr[strat] = defaultdict(int)
        test_fill_curr[strat] = defaultdict(int)
    # # determine total distribution of stratification dimensions
    for ppr in smpl_packs:
        dists_abs['year'][ppr['year']] += len(ppr[sample_key])
        dists_abs['discipline'][ppr['discipline']] += len(ppr[sample_key])
        for smpl in ppr[sample_key]:
            dists_abs[label_key][smpl[label_key]] += 1
    # # determine relative distribution of stratification dimensions
    # # and calculate allocation minima
    smpls_total = sum(n for n in dists_abs['year'].values())
    for strat in strat_dimensions:
        for k, v in dists_abs[strat].items():
            rel_size = v / smpls_total
            dev_fill_min[strat][k] = math.ceil(
                dev_size_min_smpls * rel_size
            )
            test_fill_min[strat][k] = math.ceil(
                test_size_min_smpls * rel_size
            )
    # allocate samples
    splits = ['test', 'dev', 'train']  # in fill order
    smpls_split = {}
    for split in splits:
        smpls_split[split] = []
    split_mins = {
        'test': test_fill_min,
        'dev': dev_fill_min,
    }
    split_currs = {
        'test': test_fill_curr,
        'dev': dev_fill_curr,
    }
    random.seed(42)
    random.shuffle(smpl_packs)
    for ppr in smpl_packs:
        added = False
        for split in splits[:-1]:  # put in test or dev
            # check if current paper samples are useful to add to split
            num_strat_dims_needed = 0
            for strat in strat_dimensions:  # for all dims
                needed = False
                for k in dists_abs[strat].keys():  # for all vals
                    n_curr = split_currs[split][strat][k]
                    n_min = split_mins[split][strat][k]
                    if n_curr < n_min:
                        needed = True
                        break
                if needed:
                    num_strat_dims_needed += 1
            # add if useful
            if num_strat_dims_needed == len(strat_dimensions):
                smpls_split[split].extend(ppr[sample_key])
                added = True
                # keep track of allocation numbers
                split_currs[split]['year'][ppr['year']] += len(
                    ppr[sample_key]
                )
                split_currs[split]['discipline'][ppr['discipline']] += len(
                    ppr[sample_key]
                )
                for smpl in ppr[sample_key]:
                    split_currs[split][label_key][smpl[label_key]] += 1
                # don’t add to other splits
                break
        # add to train if “not needed” in tran/dev
        if not added:
            smpls_split['train'].extend(ppr[sample_key])

    # for split in splits[:-1]:
    #     print(split)
    #     split_smpls_total = len(smpls_split[split])
    #     print(f'\tsamples total: {split_smpls_total}')
    #     for strat in strat_dimensions:
    #         for k in dists_abs[strat].keys():
    #             rel_of_total = dists_abs[strat][k] / smpls_total
    #             rel_of_split = split_currs[split][strat][k] / split_smpls_total
    #             print((
    #                 f'\t\t{strat}-{k}: {rel_of_total:.4f} '
    #                 f'-> {rel_of_split:.4f}'
    #                 f' ({split_currs[split][strat][k]})'
    #             ))
    #             input()

    # TODO
    # - persist


if __name__ == '__main__':
    split(sys.argv[1])
