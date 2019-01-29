""" Normalize and parse.
"""

import os
import shutil
import sys
import tarfile
import tempfile
from normalize_arxiv_dump import normalize
from parse_latex_tralics import parse
# from match_bibitems import match
from match_bibitems_mag import match


def prepare(in_dir, out_dir, db_uri=None, write_logs=False):
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
        try:
            is_tar = tarfile.is_tarfile(tar_path)
        except IsADirectoryError:
            print(('unexpected directory "{}" in {}. skipping'
                   '').format(tar_fn, in_dir))
            continue
        if not is_tar:
            print(('"{}" is not a TAR archive. skipping'
                   '').format(tar_fn))
            continue
        with tempfile.TemporaryDirectory() as tmp_dir_path:
            # prepare folders for intermediate results
            tmp_dir_gz = os.path.join(tmp_dir_path, 'flattened')
            os.mkdir(tmp_dir_gz)
            tmp_dir_norm = os.path.join(tmp_dir_path, 'normalized')
            os.mkdir(tmp_dir_norm)
            # extraxt
            tar = tarfile.open(tar_path)
            tar.extractall(path=tmp_dir_gz)
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
            if db_uri:
                parse(tmp_dir_norm, out_dir, INCREMENTAL=True, db_uri=db_uri,
                      write_logs=write_logs)
                # match(db_uri=db_uri)
            else:
                parse(tmp_dir_norm, out_dir, INCREMENTAL=True,
                      write_logs=write_logs)
                # match(in_dir=out_dir)
        with open(done_log_path, 'a') as f:
            f.write('{}\n'.format(tar_fn))
    print('{} files'.format(num_files_total))
    print('{} PDFs'.format(num_pdf_total))


if __name__ == '__main__':
    if len(sys.argv) not in [3, 4]:
        print(('usage: python3 prepare.py </path/to/in/dir> </path/to/out/dir>'
               ' [<db_uri>]'))
        sys.exit()
    in_dir = sys.argv[1]
    out_dir_dir = sys.argv[2]
    if len(sys.argv) == 4:
        db_uri = sys.argv[3]
        ret = prepare(in_dir, out_dir_dir, db_uri=db_uri)
    else:
        ret = prepare(in_dir, out_dir_dir)
    if not ret:
        sys.exit()
