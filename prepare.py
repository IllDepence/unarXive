""" Normalize and parse.
"""

import os
import shutil
import sys
import tarfile
import tempfile
import time
from normalize_arxiv_dump import normalize
from parse_latex_tralics import parse


def prepare(in_dir, out_dir, write_logs=False):
    if not os.path.isdir(in_dir):
        print('input directory does not exist')
        return False

    ext_sample = [os.path.splitext(fn)[-1] for fn in os.listdir(in_dir)[:10]]
    if '.tar' not in ext_sample:
        print('input directory doesn\'t seem to contain TAR archives')
        return False

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    done_log_path = os.path.join(out_dir, 'done.log')
    done_tars = []
    if os.path.isfile(done_log_path):
        with open(done_log_path) as f:
            lines = f.readlines()
        done_tars = [l.strip() for l in lines]

    tar_fns = os.listdir(in_dir)
    tar_total = len(tar_fns)
    num_pdf_total = 0
    num_files_total = 0
    for tar_idx, tar_fn in enumerate(tar_fns):
        # for each tar archive
        print('{}/{}'.format(tar_idx+1, tar_total))
        if tar_fn in done_tars:
            print('done in a previous run. skipping')
            continue
        tar_path = os.path.join(in_dir, tar_fn)
        # check if file can be skipped
        skip_file = False
        # "gracefully" handle input file access (currently a network mount)
        num_tries = 1
        while True:
            # try file access
            try:
                # try tar
                try:
                    is_tar = tarfile.is_tarfile(tar_path)
                except IsADirectoryError:
                    print(('unexpected directory "{}" in {}. skipping'
                           '').format(tar_fn, in_dir))
                    skip_file = True
                if not is_tar:
                    print(('"{}" is not a TAR archive. skipping'
                           '').format(tar_fn))
                    skip_file = True
                break  # not remote access problems
            except IOError as err:
                print(('[{}] IO error when trying check tar file: {}'
                       '').format(num_tries, err))
                num_tries += 1
                time.sleep(60)
        if skip_file:
            continue
        with tempfile.TemporaryDirectory() as tmp_dir_path:
            # prepare folders for intermediate results
            tmp_dir_gz = os.path.join(tmp_dir_path, 'flattened')
            os.mkdir(tmp_dir_gz)
            tmp_dir_norm = os.path.join(tmp_dir_path, 'normalized')
            os.mkdir(tmp_dir_norm)
            # extraxt
            # "gracefully" handle input file access (currently a network mount)
            num_tries = 1
            while True:
                try:
                    tar = tarfile.open(tar_path)
                    tar.extractall(path=tmp_dir_gz)
                    break
                except IOError as err:
                    print(('[{}] IO error when trying exract tar file: {}'
                           '').format(num_tries, err))
                    num_tries += 1
                    time.sleep(60)
            containing_dir = os.listdir(tmp_dir_gz)[0]
            containing_path = os.path.join(tmp_dir_gz,
                                           containing_dir)
            for gz_fn in os.listdir(containing_path):
                num_files_total += 1
                gz_path_tmp = os.path.join(containing_path, gz_fn)
                if os.path.splitext(gz_fn)[-1] == '.pdf':
                    num_pdf_total += 1
                    os.remove(gz_path_tmp)
                    continue
                gz_path_new = os.path.join(tmp_dir_gz, gz_fn)
                shutil.move(gz_path_tmp, gz_path_new)
            os.rmdir(containing_path)
            # adjust in_dir
            normalize(tmp_dir_gz, tmp_dir_norm, write_logs=write_logs)
            parse(tmp_dir_norm, out_dir, INCREMENTAL=False,
                  write_logs=write_logs)
        with open(done_log_path, 'a') as f:
            f.write('{}\n'.format(tar_fn))
    print('{} files'.format(num_files_total))
    print('{} PDFs'.format(num_pdf_total))


if __name__ == '__main__':
    if len(sys.argv) not in [3, 4]:
        print('usage: python3 prepare.py </path/to/in/dir> </path/to/out/dir>')
        sys.exit()
    in_dir = sys.argv[1]
    out_dir_dir = sys.argv[2]
    ret = prepare(in_dir, out_dir_dir, write_logs=True)
