""" Generate train/test data for two ML tasks
    - content based citation recommendation
    - IMRaD classification
    based on the full unarXive data set.

    Data generation in done for both tasks together because both take
    single paragraphs from papers an input. The script nicely prepares
    paragraphs (replacing in-text annotation for linked content such as
    references and mathematical notation with proper surface forms, e.g.
    citation markers and plain text rendition of mathematical notation.

    Note:
    - splitting into train/dev/test is done in a separate script [1]
    - filtering for disciplines and/or permissively licensed
      content is done in a separate script [1]

    [1] ml_tasks_split_data.py
"""

import json
import os
import pprint
import re
import sys
# import unicodeit
from collections import defaultdict, OrderedDict
from calc_stats import get_coarse_arxiv_category


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
    num_imrad_smpls = 0
    num_citrec_smpls = 0
    num_citrec_paras = 0
    imrad_smpl_packets = []
    citrec_smpl_packets = []
    paper_license_dict = {}
    num_pprs_per_cited_doc = defaultdict(int)
    num_smpls_per_cited_doc = defaultdict(int)
    # go through JSONLs
    for i, fp in enumerate(jsonl_fps):
        print(f'{i}/{len(jsonl_fps)}')
        with open(fp) as f:
            lines = f.readlines()
            for line_num, line in enumerate(lines):
                # process paper
                imrad_smpls = []
                citrec_smpls = []
                try:
                    ppr = json.loads(line)
                except json.decoder.JSONDecodeError:
                    print(f'failed to load {fp} line {line_num}\nskipping ...')
                # metadata
                metadata = ppr.get('metadata', {})
                license_url = metadata.get('license', None)
                if license_url is None or \
                        'http://creativecommons.org/' not in license_url:
                    # skip non premissively licensed
                    continue
                authors = metadata.get('authors', None)
                paper_license_dict[ppr['paper_id']] = {
                    'license': license_url,
                    'authors': authors
                }
                main_cat = metadata.get('categories', '').split(' ')[-1]
                grp_id = get_coarse_arxiv_category(main_cat)
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
                        if len(para_prepd) < 200:
                            counts['_tooshort'] += 1
                        else:
                            counts[label] += 1
                            num_imrad_smpls += 1
                            imrad_smpl = OrderedDict({
                                    '_paper_id': ppr['paper_id'],
                                    '_orig_sec': sec_pre,
                                    'label': label,
                                    'text': para_prepd
                            })
                            imrad_smpls.append(imrad_smpl)
                    # create citation recommedation classification task data
                    sec_pre = para.get('section', '')
                    if len(cit_mrk_links) > 0:
                        num_citrec_paras += 1
                        # create one sample per cited doc
                        for marker, cit_mrk_link in cit_mrk_links.items():
                            num_citrec_smpls += 1
                            num_smpls_per_cited_doc[cit_mrk_link['id']] += 1
                            citrec_smpl = OrderedDict({
                                '_paper_id': ppr['paper_id'],
                                '_raw_ref': cit_mrk_link['ref'],
                                'text': para_prepd,
                                'marker': marker,
                                'marker_offsets': cit_mrk_link['offsets'],
                                'label': cit_mrk_link['id']
                            })
                            citrec_smpls.append(citrec_smpl)
                # pack all of samples from one paper
                if len(imrad_smpls) > 0:
                    imrad_smpl_packet = OrderedDict({
                            'year': get_paper_year(ppr),  # for stratified
                            'discipline': grp_id,              # sampling
                            'category': main_cat,
                            'imrad_smpls': imrad_smpls.copy(),
                        })
                    imrad_smpl_packets.append(imrad_smpl_packet)
                if len(citrec_smpls) > 0:
                    uniq_lbls = set(
                        [s['label'] for s in citrec_smpls]
                    )
                    for lbl in uniq_lbls:
                        num_pprs_per_cited_doc[lbl] += 1
                    citrec_smpl_packet = OrderedDict({
                            'year': get_paper_year(ppr),  # for stratified
                            'discipline': grp_id,              # sampling
                            'category': main_cat,
                            'citrec_smpls': citrec_smpls.copy()
                        })
                    citrec_smpl_packets.append(citrec_smpl_packet)

    # get distribution numbers
    citrec_year_cat_dist = defaultdict(int)
    for ppr_smpls in citrec_smpl_packets:
        key = ppr_smpls['discipline'] + '-' + str(ppr_smpls['year'])
        citrec_year_cat_dist[key] += len(ppr_smpls['citrec_smpls'])
    imrad_year_cat_dist = defaultdict(int)
    for ppr_smpls in imrad_smpl_packets:
        key = ppr_smpls['discipline'] + '-' + str(ppr_smpls['year'])
        imrad_year_cat_dist[key] += len(ppr_smpls['imrad_smpls'])

    with open('license_information.json', 'w') as f:
        json.dump(paper_license_dict, f)
    with open('imrad_data.json', 'w') as f:
        json.dump(imrad_smpl_packets, f)
    with open('citrec_data.json', 'w') as f:
        json.dump(citrec_smpl_packets, f)

    print('citrec papers used:')
    print(len(citrec_smpl_packets))
    print(f'{num_citrec_paras} citrec paras')
    print(f'{num_citrec_smpls} citrec samples')
    pprint.pprint(citrec_year_cat_dist)
    cit_docs_smpls_ge3 = len(
        [v for v in num_smpls_per_cited_doc.values() if v >= 3]
    )
    cit_docs_smpls_lt3 = len(
        [v for v in num_smpls_per_cited_doc.values() if v < 3]
    )
    cit_docs_pprs_ge3 = len(
        [v for v in num_pprs_per_cited_doc.values() if v >= 3]
    )
    cit_docs_pprs_lt3 = len(
        [v for v in num_pprs_per_cited_doc.values() if v < 3]
    )
    print((
        f'{cit_docs_smpls_ge3} cited docs'
        f' w/ 3+ smpls, {cit_docs_smpls_lt3} w/ <3\n'
        f'{cit_docs_pprs_ge3} cited docs'
        f' w/ 3+ pprs, {cit_docs_pprs_lt3} w/ <3'
    ))
    print()
    print()
    print('IMRAD papers used:')
    print(len(imrad_smpl_packets))
    print(f'{num_imrad_smpls} IMRaD samples')
    pprint.pprint(counts)
    pprint.pprint(imrad_year_cat_dist)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(
            'Usage: python3 ml_task_prep_data.py </path/to/unarXive/root/dir>'
        )
        sys.exit()
    root_dir = sys.argv[1]
    prep(root_dir)
