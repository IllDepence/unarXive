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


def prep_para(ppr, para, unicode_math=False):
    """ For a single paragraph.
    """

    # prepare math notation, figures, and tables
    replacement_dict = {}
    for ref_span in para['ref_spans']:
        rid = ref_span['ref_id']
        ref_entry = ppr['ref_entries'][rid]
        if ref_entry['type'] == 'formula':
            if unicode_math:
                # this is SLOW (b/c unicodeit is)
                math_unicode = unicodeit.replace(
                    ref_entry['latex']
                )
                # math font command replacement
                math_unicode = mathfont_patt.sub(
                    r'\2', math_unicode
                )
                replacement_dict[ref_span['text']] = math_unicode
            else:
                latex_intext = '\(' + ref_entry['latex'] + '\)'
                replacement_dict[ref_span['text']] = latex_intext
        else:
            repl_token = '<{}>'.format(ref_entry['type'].upper())
            replacement_dict[ref_span['text']] = repl_token
    # make replacements
    para_prepd = para['text']
    for repl_key, repl in replacement_dict.items():
        para_prepd = para_prepd.replace(repl_key, repl)

    # prepare citation markers
    cit_docs_seen = []
    cit_refid2mark = {}
    cit_mrk_links = {}
    for i, cite_span in enumerate(para['cite_spans']):
        # keep track of already assigned
        ref_id = cite_span['ref_id']
        if ref_id in cit_docs_seen:
            continue
        cit_docs_seen.append(ref_id)
        # only define replacements once per cited doc
        cit_marker = '[{}]'.format(i+1)
        cit_refid2mark[ref_id] = cit_marker
        ref = ppr['bib_entries'].get(ref_id, {})
        oa_id = ref.get('ids', {}).get('open_alex_id', '')
        if len(oa_id) > 0:
            ref = OrderedDict({
                'id': oa_id,
                'ref': ref.get('bib_entry_raw', ''),
                'offsets': []
            })
            cit_mrk_links[cit_marker] = ref
    # make replacements and keep track of offsets
    for i, cite_span in enumerate(para['cite_spans']):
        # find marker
        marker_text = cite_span['text']
        starts_at = para_prepd.index(marker_text)
        pre = para_prepd[:starts_at]
        post = para_prepd[starts_at+len(marker_text)-1:]
        # replace
        cit_marker = cit_refid2mark[cite_span['ref_id']]
        repl = cit_marker
        para_prepd = pre + repl + post
        # note offset for linked refs
        cit_marker = cit_refid2mark[cite_span['ref_id']]
        if cit_marker in cit_mrk_links:
            ends_at = starts_at+len(cit_marker)
            cit_mrk_links[cit_marker]['offsets'].append(
                (starts_at, ends_at)
            )
            assert para_prepd[starts_at:ends_at] == cit_marker

    return para_prepd, cit_mrk_links


def prep(root_dir):
    """ For all JSONLs in the given root directory.
    """

    counts = defaultdict(int)

    # collect JSONLs
    jsonl_fps = []
    for path_to_file, subdirs, files in os.walk(root_dir):
        for fn in files:
            fn_base, ext = os.path.splitext(fn)
            if ext == '.jsonl':
                fp = os.path.join(path_to_file, fn)
                if os.path.getsize(fp) > 0:
                    jsonl_fps.append(fp)
    imrad_paras = 0
    imrad_smpl_packets = []
    citrec_smpl_packets = []
    # go through JSONLs
    for i, fp in enumerate(jsonl_fps):
        print(f'{i}/{len(jsonl_fps)}')
        with open(fp) as f:
            lines = f.readlines()
            for line_num, line in enumerate(lines):
                # process paper
                imrad_smpls = []
                citrec_smpls = []
                ppr = json.loads(line)
                main_cat = ppr['metadata']['categories'].split(' ')[-1]
                for para_num, para in enumerate(ppr['body_text']):
                    # process paragraph
                    para_prepd, cit_mrk_links = prep_para(ppr, para)
                    # create IMRaD classification task data
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
                        if len(para_prepd) < 200:
                            counts['_tooshort'] += 1
                        else:
                            counts[label] += 1
                            imrad_smpl = OrderedDict({
                                    'orig_sec': sec_pre,
                                    'label': label,
                                    'text': para_prepd
                            })
                            imrad_smpls.append(imrad_smpl)
                    # create citation recommedation classification task data
                    sec_pre = para.get('section', '')
                    if len(cit_mrk_links) > 0:
                        citrec_smpl = OrderedDict({
                            'context': para_prepd,
                            'citations': cit_mrk_links
                        })
                        citrec_smpls.append(citrec_smpl)
                # pack all of samples from one paper
                if len(imrad_smpls) > 0:
                    imrad_smpl_packet = OrderedDict({
                            'year': get_paper_year(ppr),  # for stratified
                            'cat': main_cat,              # sampling
                            'imrad_smpls': imrad_smpls.copy(),
                        })
                    imrad_smpl_packets.append(imrad_smpl_packet)
                if len(citrec_smpls) > 0:
                    citrec_smpl_packet = OrderedDict({
                            'year': get_paper_year(ppr),  # for stratified
                            'cat': main_cat,              # sampling
                            'citrec_smpls': citrec_smpls.copy()
                        })
                    citrec_smpl_packets.append(citrec_smpl_packet)

    print(len(imrad_smpl_packets))
    print(len(citrec_smpl_packets))
    # TODO:
    # - make stratified tain/test/val splits
    # - persist

    pprint.pprint(counts)
    print(f'{imrad_paras} IMRaDR papras')


if __name__ == '__main__':
    if len(sys.argv) == 2:
        root_dir = sys.argv[1]
    else:
        root_dir = 'preview_sample'
    prep(root_dir)
