""" Filter every JSONL to only contain permissively licensed papers.

    Only use papers licensed
    - Public Domain
    - CC-Zero
    - CC-BY
    - CC-BY-SA
    such that the final data set can be shared as CC-BY-SA.
"""

import json
import os
import sys
from collections import defaultdict


def is_permissive(license_url):
    if license_url is None or license_url not in [
        # only use papers licensed such that result can be
        # shared as cc by-sa 4.0 — i.e. no nc and no nd
        # (could opt for using by-nc-sa and get ~15k more
        #  papers, but at ~200k it’s not a huge gain and
        #  requires restricting the use of the ML data)
        'http://creativecommons.org/licenses/by/4.0/',  # 130k
        'http://creativecommons.org/licenses/by/3.0/',  # 6k
        'http://creativecommons.org/licenses/by-sa/4.0/',  # 8k
        'http://creativecommons.org/publicdomain/zero/1.0/',  # 8k
        'http://creativecommons.org/licenses/publicdomain/',  # 2k
        # 'http://creativecommons.org/licenses/by-nc-sa/3.0/',  4k
        # 'http://creativecommons.org/licenses/by-nc-sa/4.0/',  18k
        # 'http://creativecommons.org/licenses/by-nc-nd/4.0/',  18k
    ]:
        return False
    return True


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
            license_url = ppr.get('metadata', {}).get('license')
            license_counts[license_url] += 1
            # filter
            if is_permissive(license_url):
                permissive_pprs.append(ppr)

    fn = os.path.split(fp_full)[-1]
    fp_filtered = os.path.join(out_dir, fn)
    if len(permissive_pprs) > 0:
        # save to disk
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
            for license_url, count in filter_permissive(fp, out_dir).items():
                license_counts[license_url] += count
    permissive_total = 0
    restrictive_total = 0
    for license_url, count in license_counts.items():
        if is_permissive(license_url):
            permissive_total += count
        else:
            restrictive_total += count
        print(f'{license_url}: {count}')
    print(f'\noverall permissive: {permissive_total}')
    print(f'\noverall restrictive: {restrictive_total}')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: filter_permissively_licensed.py </path/to/data>')
        sys.exit()
    root_dir = sys.argv[1]
    main(root_dir)
