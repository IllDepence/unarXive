""" Clean arXiv dump txt ouput
"""

import os
import re
import shutil
import sys

CITE_PATT = re.compile((r'\{\{cite:([0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}'
                         '-[89AB][0-9A-F]{3}-[0-9A-F]{12})\}\}'), re.I)


def clean(in_dir):
    """ Separate output files with no citations in them.
    """

    no_cit_dir = os.path.join(in_dir, 'no_cit')
    if not os.path.isdir(no_cit_dir):
        os.makedirs(no_cit_dir)

    file_names = os.listdir(in_dir)
    for file_idx, fn in enumerate(file_names):
        if file_idx%100 == 0:
            print('{}/{}'.format(file_idx, len(file_names)))
        path = os.path.join(in_dir, fn)
        aid, ext = os.path.splitext(fn)
        if ext != '.txt':
            continue
        with open(path) as f:
            text = f.read()
        if not re.search(CITE_PATT, text):
            new_path = os.path.join(no_cit_dir, fn)
            shutil.move(path, new_path)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: python3 clean_txt_output.py </path/to/input/dir>')
        sys.exit()
    in_dir = sys.argv[1]
    ret = clean(in_dir)
    if not ret:
        sys.exit()
