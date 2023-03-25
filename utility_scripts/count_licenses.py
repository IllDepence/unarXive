import json
import os
import sys
from collections import defaultdict


def license_counts_from_json(fp):
    license_counts = defaultdict(int)
    with open(fp) as f:
        for line in f:
            ppr = json.loads(line.strip())
            license = ppr.get('metadata', {}).get('license')
            license_counts[license] += 1
    return license_counts


def main(root_dir):
    license_counts = defaultdict(int)

    for sub_dir, dirs, files in os.walk(root_dir):
        for fn in files:
            if os.path.splitext(fn)[-1] != '.jsonl':
                continue
            fp = os.path.join(sub_dir, fn)
            for license, count in license_counts_from_json(fp).items():
                license_counts[license] += count
    with open('license_counts.json', 'w') as f:
        json.dump(license_counts, f)
    for license, count in license_counts.items():
        print(f'{license}: {count}')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: count_licenses.py </path/to/data>')
        sys.exit()
    root_dir = sys.argv[1]
    main(root_dir)
