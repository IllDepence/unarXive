""" Filter every JSONL to only contain permissively licensed papers.
"""

import json
import os
import sys
from collections import defaultdict


def is_permissive(license):
    cc_url = 'creativecommons.org'
    return cc_url in license.__repr__()


def filter_permissive(fp_full, out_dir):
    """ Filter a single JSONL
    """

    # filter and count
    license_counts = defaultdict(int)
    permissive_pprs = []
    full_ppr_count = 0
    with open(fp_full) as f:
        for line in f:
            ppr = json.loads(line.strip())
            full_ppr_count += 1
            # count
            license = ppr.get('metadata', {}).get('license')
            license_counts[license] += 1
            # filter
            if is_permissive(license):
                permissive_pprs.append(ppr)

    fn = os.path.split(fp_full)[-1]
    fp_filtered = os.path.join(out_dir, fn)
    if len(permissive_pprs) > 0:
        # persist
        with open(fp_filtered, 'w') as f:
            for ppr in permissive_pprs:
                f.write('{}\n'.format(json.dumps(ppr)))

    # report
    print(f'[ {fn} ]   {full_ppr_count} -> {len(permissive_pprs)}')

    return license_counts


def main(root_dir):
    # ensure output dir
    out_dir = os.path.join(
        root_dir,
        'permissive_subset'
    )
    if not os.path.exists(out_dir):
        os.mkdir(out_dir)

    # filter
    license_counts = defaultdict(int)
    for sub_dir, dirs, files in os.walk(root_dir):
        if out_dir in sub_dir:
            continue
        for fn in files:
            if os.path.splitext(fn)[-1] != '.jsonl':
                continue
            fp = os.path.join(sub_dir, fn)
            for license, count in filter_permissive(fp, out_dir).items():
                license_counts[license] += count
    permissive_total = 0
    restrictive_total = 0
    for license, count in license_counts.items():
        if is_permissive(license):
            permissive_total += count
        else:
            restrictive_total += count
        print(f'{license}: {count}')
    print(f'\noverall permissive: {permissive_total}')
    print(f'\noverall restrictive: {restrictive_total}')


if __name__ == '__main__':
    root_dir = sys.argv[1]
    main(root_dir)
