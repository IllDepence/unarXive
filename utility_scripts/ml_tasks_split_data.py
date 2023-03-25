""" Split data pepared by script ml_task_prep_data.py into train,
    dev, and test.

    Stratified sampling is used wrt.
    - target clabel (class)
    - (citing) paper discipline
    - paper publication year
"""

import json
import math
import os
import random
import sys
import uuid
from collections import defaultdict, OrderedDict


def split(fn_to_split, fn_license_info, dev_test_size, single_disc):
    """ Create train/dev/test splits using stratified sampling accross
        - publications years
        - disciplines
        - target labels

        Possible single_disc values for filtering:
        grp_physics
        grp_math
        grp_cs
        grp_q-bio
        grp_q-fin
        grp_stat
    """

    print('reading paper data')
    with open(fn_to_split) as f:
        smpl_packs = json.load(f)
    print('reading license data')
    with open(fn_license_info) as f:
        paper_license_dict = json.load(f)
    license_dict_dist = {}

    if single_disc is not None:
        print(f'only using samples from discipline {single_disc}')
        smpl_packs = [
            sp for sp in smpl_packs if sp['discipline'] == single_disc
        ]

    dev_size_min_smpls = dev_test_size
    test_size_min_smpls = dev_test_size
    splits = ['test', 'dev', 'train']  # in fill order
    smpls_split = {}
    for split in splits:
        smpls_split[split] = []

    # determine sample and label key
    for key in ['imrad_smpls', 'citrec_smpls']:
        if key in smpl_packs[0]:
            sample_key = key

    # calculate sample allocation goals
    print('calculating sample allocation goals')
    dists_abs = {}
    dev_fill_min = {}
    test_fill_min = {}
    dev_fill_curr = {}
    test_fill_curr = {}
    strat_dimensions = ['year', 'discipline', 'label']
    num_packets_for_label = defaultdict(int)
    for strat in strat_dimensions:
        dists_abs[strat] = defaultdict(int)
        dev_fill_min[strat] = defaultdict(int)
        test_fill_min[strat] = defaultdict(int)
        dev_fill_curr[strat] = defaultdict(int)
        test_fill_curr[strat] = defaultdict(int)
    train_fill_curr_label = defaultdict(int)  # only used in pre-fill
    # # determine usable labels
    print('determining usable labels')
    for ppr in smpl_packs:
        # determine set of unique labels for which we have
        # samples for the current paper
        uniq_lbls = set()
        for smpl in ppr[sample_key]:
            uniq_lbls.add(smpl['label'])
        # for each unique label, increase count of papers
        # for label by 1
        for lbl in uniq_lbls:
            num_packets_for_label[lbl] += 1
    # usable labels are those for which we have samples
    # from at least <num_splits> (i.e. 3) papers
    usable_labels = [
        k for (k, v) in num_packets_for_label.items()
        if v >= len(splits)
    ]
    # # filter samples to only contain usable labels
    print('filtering out unusable labels')
    smpl_packs_usable = []
    # # shuffle b/c we’ll already pre-assign some sample to splits
    random.seed(42)
    random.shuffle(smpl_packs)
    for ppr in smpl_packs:
        # prepare usable subset of paper samples
        smpls_usable = []
        for smpl in ppr[sample_key]:
            lbl = smpl['label']
            if lbl in usable_labels:
                # pre-allocation to ensure each usable sample appears
                # at least once in each split
                for (split_key, fill_counter) in [
                    ('test', test_fill_curr['label']),
                    ('dev', dev_fill_curr['label']),
                    ('train', train_fill_curr_label),
                ]:
                    if fill_counter[lbl] == 0:
                        clean_smpls = clean_samples(
                            [smpl],  # function expects a list of samples
                            paper_license_dict,
                            license_dict_dist
                        )
                        smpls_split[split_key].extend(clean_smpls)
                        fill_counter[lbl] += 1
                        break  # don’t assign to other splits
                # rest is used for stratified samples
                smpls_usable.append(smpl)
        # if paper contains any usable samples
        if len(smpls_usable) > 0:
            # re-create paper with only usable samples
            ppr_usable = {}
            for k, v in ppr.items():
                if k != sample_key:
                    ppr_usable[k] = v
            ppr_usable[sample_key] = smpls_usable
            smpl_packs_usable.append(ppr_usable)
    # print('num usable labels:')
    # print(len(usable_labels))
    # print('num smpl packs:')
    # print(len(smpl_packs))
    # print('num usable smpl packs:')
    # print(len(smpl_packs_usable))
    # import pprint
    # for (split_key, fill_counter) in [
    #     ('test', test_fill_curr['label']),
    #     ('dev', dev_fill_curr['label']),
    #     ('train', train_fill_curr_label),
    # ]:
    #     print(f'{split_key}:')
    #     pprint.pprint(fill_counter)
    # for split_name, smpls in smpls_split.items():
    #     print(f'#{split_name} samples: {len(smpls)}')
    # sys.exit()
    smpl_packs = smpl_packs_usable
    # # determine total distribution of stratification dimensions
    for ppr in smpl_packs:
        dists_abs['year'][ppr['year']] += len(ppr[sample_key])
        dists_abs['discipline'][ppr['discipline']] += len(ppr[sample_key])
        for smpl in ppr[sample_key]:
            dists_abs['label'][smpl['label']] += 1
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
    split_mins = {
        'test': test_fill_min,
        'dev': dev_fill_min,
    }
    split_currs = {
        'test': test_fill_curr,
        'dev': dev_fill_curr,
    }
    for ppr in smpl_packs:
        added = False
        for i, split in enumerate(splits[:-1]):  # put in test or dev
            # check if labels to be allocated have enough remaining samples
            num_other_splits = len(splits) - i - 1
            cant_use = False
            for smpl in ppr[sample_key]:
                if num_packets_for_label[smpl['label']] <= num_other_splits:
                    cant_use = True
                    break
            if cant_use:
                continue
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
                clean_smpls = clean_samples(
                    ppr[sample_key],
                    paper_license_dict,
                    license_dict_dist
                )
                smpls_split[split].extend(clean_smpls)
                added = True
                # keep track of allocation numbers
                split_currs[split]['year'][ppr['year']] += len(
                    ppr[sample_key]
                )
                split_currs[split]['discipline'][ppr['discipline']] += len(
                    ppr[sample_key]
                )
                for smpl in ppr[sample_key]:
                    split_currs[split]['label'][smpl['label']] += 1
                # keep track of packets left per label
                for lbl in set([s['label'] for s in ppr[sample_key]]):
                    num_packets_for_label[lbl] -= 1
                # don’t add to other splits
                break
        # add to train if “not needed” in tran/dev
        if not added:
            clean_smpls = clean_samples(
                ppr[sample_key],
                paper_license_dict,
                license_dict_dist
            )
            smpls_split['train'].extend(clean_smpls)

    # for split in splits[:-1]:
    #     print(split)
    #     split_total = len(smpls_split[split])
    #     print(f'\tsamples total: {split_total}')
    #     for strat in strat_dimensions:
    #         for k in dists_abs[strat].keys():
    #             rel_of_total = dists_abs[strat][k] / smpls_total
    #             rel_of_split = split_currs[split][strat][k] / split_total
    #             print((
    #                 f'\t\t{strat}-{k}: {rel_of_total:.4f} '
    #                 f'-> {rel_of_split:.4f}'
    #                 f' ({split_currs[split][strat][k]})'
    #             ))

    # save samples
    fn_base, ext = os.path.splitext(os.path.split(fn_to_split)[-1])
    for split, smpls in smpls_split.items():
        fn = f'{fn_base}_{split}.jsonl'
        with open(fn, 'w') as f:
            for smpl in smpls:
                f.write(json.dumps(smpl) + '\n')
    # save license info
    fn_license = f'{fn_base}_license_info.jsonl'
    with open(fn_license, 'w') as f:
        for arxiv_id, license_info in license_dict_dist.items():
            line = json.dumps(license_info)
            f.write(f'{line}\n')


def clean_samples(smpls, paper_license_dict, license_dict_dist):
    """ Prepare samples and their license info for distribution

        - remove debug information from samples
          (=dict fields starting with an underscore)
        - generate per sample lincense info
    """

    clean_smpls = []
    for smpl in smpls:
        smpl_id = str(uuid.uuid4())
        # generate clean sample
        clean_smpl = OrderedDict()
        clean_smpl['_id'] = smpl_id
        clean_smpl['text'] = smpl['text']
        for k, v in smpl.items():
            if k[0] != '_' and k not in ['text', 'label']:
                clean_smpl[k] = v
        clean_smpl['label'] = smpl['label']
        # note sample IDs for license info
        ppr_id = smpl['_paper_id']
        license_info = paper_license_dict[ppr_id]
        if ppr_id not in license_dict_dist:
            ld = OrderedDict()
            ld['paper_arxiv_id'] = ppr_id
            ld['authors'] = license_info['authors']
            ld['license'] = license_info['license']
            ld['sample_ids'] = []
            license_dict_dist[ppr_id] = ld
        license_dict_dist[ppr_id]['sample_ids'].append(smpl_id)

        clean_smpls.append(clean_smpl)
    return clean_smpls


if __name__ == '__main__':
    if len(sys.argv) not in [4, 5]:
        print((
            'Usage: python3 ml_tasks_split_data.py '
            '<ml_data_file> <license_info_file> <dev/test set size> '
            '[discipline filter]'
        ))
    else:
        to_split = sys.argv[1]
        license_info = sys.argv[2]
        dev_test_size = int(sys.argv[3])
        single_disc = None
        if len(sys.argv) == 5:
            single_disc = sys.argv[4]
        split(to_split, license_info, dev_test_size, single_disc=single_disc)
