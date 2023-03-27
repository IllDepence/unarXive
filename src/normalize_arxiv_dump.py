""" Normalize a arXiv dump

    - copy PDF files as is
    - unzip gzipped single files
        - copy if it's a LaTeX file
    - extract gzipped tar archives
        - try to flatten contents to a single LaTeX file
        - ignores non LaTeX contents (HTML, PS, TeX, ...)
"""

import chardet
import gzip
import magic
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from hashlib import sha1


MAIN_TEX_PATT = re.compile(r'(\\begin\s*\{\s*document\s*\})', re.I)
# ^ with capturing parentheses so that the pattern can be used for splitting
PDF_EXT_PATT = re.compile(r'^\.pdf$', re.I)
GZ_EXT_PATT = re.compile(r'^\.gz$', re.I)
TEX_EXT_PATT = re.compile(r'^\.tex$', re.I)
NON_TEXT_PATT = re.compile(r'^\.(pdf|eps|jpg|png|gif)$', re.I)
BBL_SIGN = '\\bibitem'
# natbib fix
PRE_FIX_NATBIB = True
NATBIB_PATT = re.compile(
    (r'\\cite(t|p|alt|alp|author|year|yearpar)\s*?\*?\s*?'
     r'(\[[^\]]*?\]\s*?)*?\s*?\*?\s*?\{([^\}]+?)\}'),
    re.I
)
# bibitem option fix
PRE_FIX_BIBOPT = True
BIBOPT_PATT = re.compile(r'\\bibitem\s*?\[[^]]*?\]', re.I | re.M)

# ↑ above two solve most tralics problems; except for mnras style bibitems
# (https://ctan.org/pkg/mnras)

# agressive math pre-removal
PRE_FILTER_MATH = False
FILTER_PATTS = []
for env in ['equation', 'displaymath', 'array', 'eqnarray', 'align', 'gather',
            'multline', 'flalign', 'alignat']:
    s = r'\\begin\{{{0}[*]?\}}.+?\\end\{{{0}\}}'.format(env)
    patt = re.compile(s, re.I | re.M | re.S)
    FILTER_PATTS.append(patt)
FILTER_PATTS.append(re.compile(r'\$\$.+?\$\$', re.S))
FILTER_PATTS.append(re.compile(r'\$.+?\$', re.S))
FILTER_PATTS.append(re.compile(r'\\\(.+?\\\)', re.S))
FILTER_PATTS.append(re.compile(r'\\\[.+?\\\]', re.S))


def read_file(path):
    try:
        with open(path) as f:
            cntnt = f.read()
    except UnicodeDecodeError:
        blob = open(path, 'rb').read()
        m = magic.Magic(mime_encoding=True)
        encoding = m.from_buffer(blob)
        try:
            cntnt = blob.decode(encoding)
        except (UnicodeDecodeError, LookupError) as e:
            encoding = chardet.detect(blob)['encoding']
            if encoding:
                try:
                    cntnt = blob.decode(encoding, errors='replace')
                except:
                    return ''
            else:
                return ''
    return cntnt


def read_gzipped_file(path):
    blob = gzip.open(path, 'rb').read()
    m = magic.Magic(mime_encoding=True)
    encoding = m.from_buffer(blob)
    try:
        cntnt = blob.decode(encoding)
    except (UnicodeDecodeError, LookupError) as e:
        encoding = chardet.detect(blob)['encoding']
        if not encoding:
            return False
        cntnt = blob.decode(encoding, errors='replace')
    return cntnt


def remove_math(latex_str):
    parts = re.split(MAIN_TEX_PATT, latex_str, maxsplit=1)
    for patt in FILTER_PATTS:
        parts[2] = re.sub(patt, '', parts[2])
    return ''.join(parts)


def _source_file_hash(fp):
    source_file_hasher = sha1()
    with open(fp, 'rb') as source_file:
        buf = source_file.read()
        source_file_hasher.update(buf)
        source_file_hash = str(source_file_hasher.hexdigest())
    return source_file_hash


def normalize(in_dir, out_dir, write_logs=True):
    def log(msg):
        if write_logs:
            with open(os.path.join(out_dir, 'log.txt'), 'a') as f:
                f.write('{}\n'.format(msg))

    if not os.path.isdir(in_dir):
        print('dump directory does not exist')
        return False

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    source_file_info = dict()

    for fn in os.listdir(in_dir):
        path = os.path.join(in_dir, fn)
        aid_fn_safe, ext = os.path.splitext(fn)
        source_file_info[aid_fn_safe] = {
            'name': fn,
            'hash': _source_file_hash(path)
        }
        if PDF_EXT_PATT.match(ext):
            # copy over pdf file as is
            dest = os.path.join(out_dir, fn)
            shutil.copyfile(path, dest)
        elif GZ_EXT_PATT.match(ext):
            if tarfile.is_tarfile(path):
                with tempfile.TemporaryDirectory() as tmp_dir_path:
                    # extract archive contents
                    tar = tarfile.open(path)
                    fnames = tar.getnames()
                    tar.extractall(path=tmp_dir_path)
                    # identify main tex file
                    main_tex_path = None
                    ignored_names = []
                    # check .tex files first
                    for tfn in fnames:
                        if not TEX_EXT_PATT.match(os.path.splitext(tfn)[1]):
                            ignored_names.append(tfn)
                            continue
                        tmp_file_path = os.path.join(tmp_dir_path, tfn)
                        if os.path.isdir(tmp_file_path):
                            continue
                        try:
                            cntnt = read_file(tmp_file_path)
                        except:
                            continue
                        if re.search(MAIN_TEX_PATT, cntnt) is not None:
                            main_tex_path = tmp_file_path
                    # try other files
                    if main_tex_path is None:
                        for tfn in ignored_names:
                            tmp_file_path = os.path.join(tmp_dir_path, tfn)
                            if NON_TEXT_PATT.match(os.path.splitext(tfn)[1]):
                                continue
                            try:
                                cntnt = read_file(tmp_file_path)
                                if re.search(MAIN_TEX_PATT, cntnt) is not None:
                                    main_tex_path = tmp_file_path
                            except:
                                continue
                    # give up
                    if main_tex_path is None:
                        log(('couldn\'t find main tex file in dump archive {}'
                             '').format(fn))
                        continue
                    # "identify" bbl file
                    # https://arxiv.org/help/submit_tex#bibtex
                    main_tex_fn = os.path.normpath(
                        main_tex_path).split(os.sep)[-1]
                    fn_base = os.path.splitext(main_tex_path)[0]
                    bbl_fn = '{}.bbl'.format(fn_base)
                    if os.path.isfile(os.path.join(tmp_dir_path, bbl_fn)):
                        latexpand_args = ['latexpand',
                                          '--expand-bbl',
                                          bbl_fn,
                                          main_tex_fn]
                    else:
                        latexpand_args = ['latexpand',
                                          main_tex_fn]
                    # flatten to single tex file and save
                    new_tex_fn = '{}.tex'.format(aid_fn_safe)
                    tmp_dest = os.path.join(tmp_dir_path, new_tex_fn)
                    out = open(tmp_dest, mode='w')
                    if write_logs:
                        err = open(
                            os.path.join(out_dir, 'log_latexpand.txt'), 'a'
                            )
                    else:
                        err = open(os.devnull, 'w')
                    err.write('\n------------- {} -------------\n'.format(aid_fn_safe))
                    err.flush()
                    subprocess.run(latexpand_args, stdout=out, stderr=err,
                                   cwd=tmp_dir_path)
                    out.close()
                    err.close()
                    # re-read and write to ensure utf-8 b/c latexpand doesn't
                    # behave
                    cntnt = read_file(tmp_dest)
                    if PRE_FIX_NATBIB:
                        cntnt = NATBIB_PATT.sub(r'\\cite{\3}', cntnt)
                    if PRE_FIX_BIBOPT:
                        cntnt = BIBOPT_PATT.sub(r'\\bibitem', cntnt)
                    if PRE_FILTER_MATH:
                        cntnt = remove_math(cntnt)
                    dest = os.path.join(out_dir, new_tex_fn)
                    with open(dest, mode='w', encoding='utf-8') as f:
                        f.write(cntnt)
            else:
                # extraxt gzipped tex file
                cntnt = read_gzipped_file(path)
                if not cntnt:
                    continue
                if re.search(MAIN_TEX_PATT, cntnt) is None:
                    log('unexpected content in dump archive {}'.format(fn))
                    continue
                new_fn = '{}.tex'.format(aid_fn_safe)
                if PRE_FIX_NATBIB:
                    cntnt = NATBIB_PATT.sub(r'\\cite{\3}', cntnt)
                if PRE_FIX_BIBOPT:
                    cntnt = BIBOPT_PATT.sub('\\bibitem', cntnt)
                if PRE_FILTER_MATH:
                    cntnt = remove_math(cntnt)
                dest = os.path.join(out_dir, new_fn)
                with open(dest, mode='w', encoding='utf-8') as f:
                    f.write(cntnt)
        else:
            log('unexpected file {} in dump directory'.format(fn))

    return source_file_info


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(('usage: python3 nomalize_arxiv_dump.py </path/to/dump/dir> </pa'
               'th/to/out/dir>'))
        sys.exit()
    in_dir = sys.argv[1]
    out_dir = sys.argv[2]
    ret = normalize(in_dir, out_dir)
    if not ret:
        sys.exit()
