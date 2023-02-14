import json
import os
import pprint
import re
import sys
import unicodeit
from collections import defaultdict, OrderedDict


mathfont_patt = re.compile(
    r'\\math(cal|frak|bb|normal|rm|it|bf|sf|tt)\s*{([^}]+)}'
)
alloc_map = {
    'introduction':
        [
            'introduction',
            'introduction and preliminaries',
            'preliminaries',
            'preliminary',
            'background',
            'motivation',
        ],
    'methods':
        [
            'method',
            'methods',
            'methodology',
            'model',
            'the model',
            'system model',
            'experiments',
            'experimental setup',
            'numerical experiments',
            'evaluation',
            'analysis',
            'simulations',
            'implementation',
        ],
    'results':
        [
            'result',
            'results',
            'main result',
            'main results',
            'the main result',
            'numerical results',
            'experimental results',
            'simulation results',
            'auxiliary results',
            'observations',
        ],
    'discussion':
        [
            'discussion',
            'discussions',
            'discussion and conclusion',
            'discussion and conclusions',
            'conclusions and discussion',
            'conclusions',
            'conclusion',
            'concluding remarks',
            'conclusions and outlook',
            'conclusion and future work',
            'conclusions and future work',
            'summary and discussion',
            'summary and conclusion',
            'summary and conclusions',
            'summary and outlook',
        ],
    'related work':
        [
            'related work',
            'related works',
        ]
}


def get_paper_year(ppr):
    pid = ppr.get('paper_id')
    if '/' in pid:
        # old format ID
        pref, pid = pid.split('/')
    if pid[0] == '9':
        # years 1991–1999
        year = int('19' + pid[:2])
    else:
        # years 2000–2099
        year = int('20' + pid[:2])
    # month = pid[2:4]
    return year


def prep_para(ppr, para):
    """ For a single paragraph.
    """

    replacement_dict = defaultdict(tuple)

    # citation markers
    for i, cite_span in enumerate(para['cite_spans']):
        cit_marker = '[{}]'.format(i+1)
        replacement_dict[cite_span['text']] = cit_marker

    # math notation, figures and tables
    for ref_span in para['ref_spans']:
        rid = ref_span['ref_id']
        ref_entry = ppr['ref_entries'][rid]
        if ref_entry['type'] == 'formula':
            # unicodeit based replacement
            math_unicode = unicodeit.replace(
                ref_entry['latex']
            )
            # math font command replacement
            math_unicode = mathfont_patt.sub(
                r'\2', math_unicode
            )
            replacement_dict[ref_span['text']] = math_unicode
        else:
            repl_token = '<{}>'.format(ref_entry['type'].upper())
            replacement_dict[ref_span['text']] = repl_token

    # make replacements
    para_prepd = para['text']
    for repl_key, repl in replacement_dict.items():
        para_prepd = para_prepd.replace(repl_key, repl)

    return para_prepd


def prep(root_dir):
    """ For all JSONLs in the given root directory.
    """

    counts = defaultdict(int)

    # go through JSONLs
    jsonl_fps = []
    for path_to_file, subdirs, files in os.walk(root_dir):
        for fn in files:
            fn_base, ext = os.path.splitext(fn)
            if ext == '.jsonl':
                fp = os.path.join(path_to_file, fn)
                if os.path.getsize(fp) > 0:
                    jsonl_fps.append(fp)
    cs = 0
    nocs = 0
    imrad_paras = 0
    ml_smpl_packets = []
    for fp in jsonl_fps:
        with open(fp) as f:
            for line in f:
                ml_smpls = []
                ppr = json.loads(line)
                main_cat = ppr['metadata']['categories'].split(' ')[-1]
                if not main_cat.startswith('cs.'):
                    nocs += 1
                else:
                    cs += 1
                    for para in ppr['body_text']:
                        sec_pre = para.get('section', '')
                        if sec_pre is None:
                            sec_pre = ''
                        sec_clean = sec_pre.strip().lower().replace(
                            '.', ''
                        )
                        label = None
                        if sec_clean in alloc_map['introduction']:
                            label = 'i'
                        elif sec_clean in alloc_map['methods']:
                            label = 'm'
                        elif sec_clean in alloc_map['results']:
                            label = 'r'
                        elif sec_clean in alloc_map['discussion']:
                            label = 'd'
                        elif sec_clean in alloc_map['related work']:
                            label = 'w'
                        else:
                            counts['_noclass'] += 1
                        if label is not None:
                            imrad_paras += 1
                            para_prepd = prep_para(ppr, para)
                            if len(para_prepd) < 200:
                                counts['_tooshort'] += 1
                            else:
                                counts[label] += 1
                                ml_smpl = OrderedDict({
                                        'orig_sec': sec_pre,
                                        'label': label,
                                        'text': para_prepd
                                })
                                ml_smpls.append(ml_smpl)
                    ml_smpl_packet = OrderedDict({
                            'year': get_paper_year(ppr),  # for stratified
                            'cat': main_cat,              # sampling
                            'smpls': ml_smpls.copy()
                        })
                    ml_smpl_packets.append(ml_smpl_packet)

    # TODO:
    # - make stratified tain/test/val splits
    # - persist

    print(f'{cs} CS papers\n{nocs} non CS papers')
    pprint.pprint(counts)
    print(f'{imrad_paras} IMRaDR papras')


if __name__ == '__main__':
    if len(sys.argv) == 2:
        root_dir = sys.argv[1]
    else:
        root_dir = 'preview_sample'
    prep(root_dir)
