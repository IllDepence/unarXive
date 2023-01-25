import glob
import json
import os
import sys
from collections import defaultdict
from arxiv_taxonomy import GROUPS, ARCHIVES, CATEGORIES


def get_fine_arxiv_category_name(cat_id):
    fine_cat = CATEGORIES.get(cat_id, None)
    if fine_cat is not None:
        return fine_cat['name']
    return None


def get_coarse_arxiv_group_name(grp_id):
    grp = GROUPS.get(grp_id, None)
    if grp is not None:
        return grp['name']
    return None


def get_coarse_arxiv_category(cat_id):
    """ In arXiv taxonomy, go
            category -> archive -> group.
        e.g.
            hep-th -> hep-th -> grp_physics
            cs.CL -> cs -> grp_cs
    """

    cat = CATEGORIES.get(cat_id, None)
    if cat is not None:
        archive_id = cat['in_archive']
        archive = ARCHIVES.get(archive_id, None)
        if archive is not None:
            group_id = archive['in_group']
            group = GROUPS.get(group_id, None)
            if group is not None:
                return group_id
    return None


def get_open_alex_id_from_ref(ref):
    """ Get OpenAlex ID from a reference dict in bib_entries.

        Return none if the reference was not matched to an OpenAlex work.
    """

    open_alex_id = ref.get('ids', {}).get('open_alex_id', None)
    if open_alex_id is not None and len(open_alex_id) > 0:
        return open_alex_id
    return None


def paper_stats(ppr):
    """ Get various stats of a paper
    """

    stats = {}

    # determine year
    pid = ppr.get('paper_id', None)
    if pid is None:
        year = -1
    elif pid[0] == '9':
        # years 1991–1999
        year = int('19' + pid[:2])
    else:
        # years 2000–2099
        year = int('20' + pid[:2])
    stats['year'] = year

    # determine categories
    main_fine_cat = None
    main_coarse_cat = None
    fine_cats = []
    coarse_cats = []
    fine_cat_ids = [
        c for c
        in ppr.get('metadata', {}).get('categories', '').split(' ')
        if len(c) > 0  # filter when categories is ''
    ]
    for fine_cat_id in fine_cat_ids:
        fine_cats.append(fine_cat_id)
        if main_fine_cat is None:
            main_fine_cat = fine_cat_id
        coarse_cat_id = get_coarse_arxiv_category(fine_cat_id)
        if coarse_cat_id is not None:
            coarse_cats.append(coarse_cat_id)
            if main_coarse_cat is None:
                main_coarse_cat = coarse_cat_id
    coarse_cats = list(set(coarse_cats))
    stats['main_fine_cat'] = main_fine_cat
    stats['main_coarse_cat'] = main_coarse_cat
    stats['coarse_cats'] = coarse_cats
    stats['fine_cats'] = fine_cats

    # determine license
    stats['license'] = ppr.get('metadata', {}).get('license', None)

    # full text based stats
    num_paras = 0
    num_para_types = defaultdict(int)
    num_cit_markers = 0
    num_cit_markers_linked = 0
    num_refs = 0
    num_refs_linked = 0
    num_non_text_types = defaultdict(int)
    num_non_text_success = defaultdict(dict)
    # reference section entries
    for ref in ppr['bib_entries'].values():
        # count reference section entries separately, because a single
        # entry can appear in multiple paragraphs
        num_refs += 1
        open_alex_id = get_open_alex_id_from_ref(ref)
        if open_alex_id is not None:
            num_refs_linked += 1
    stats['num_refs'] = num_refs
    stats['num_refs_linked'] = num_refs_linked
    # paragraphs and in-text citations
    for para in ppr.get('body_text', []):
        num_paras += 1
        num_para_types[para['content_type']] += 1
        for cit in para['cite_spans']:
            # for each reference
            ref_id = cit['ref_id']
            num_mrkrs = para['text'].count(ref_id)
            num_cit_markers += num_mrkrs
            ref = ppr['bib_entries'].get(
                ref_id, {}
            )
            open_alex_id = get_open_alex_id_from_ref(ref)
            if open_alex_id is not None:
                num_cit_markers_linked += num_mrkrs
    stats['num_paras'] = num_paras
    stats['num_para_types'] = num_para_types
    stats['num_cit_markers'] = num_cit_markers
    stats['num_cit_markers_linked'] = num_cit_markers_linked
    # formulae, tables, figures
    for non_text in ppr['ref_entries'].values():
        nt_type = non_text['type']
        if nt_type == 'formula':
            content = non_text['latex']
        else:
            content = non_text['caption']
        for succ in ['fail', 'success']:
            if succ not in num_non_text_success[nt_type]:
                num_non_text_success[nt_type][succ] = 0
        if content[:3] == 'NO_':
            # NO_CAPTION / NO_LATEX_CONTENT
            num_non_text_success[nt_type]['fail'] += 1
        else:
            num_non_text_types[nt_type] += 1
            num_non_text_success[nt_type]['success'] += 1
    stats['num_non_text_types'] = num_non_text_types
    stats['num_non_text_success'] = num_non_text_success

    return stats


def add_to_overall_stats(stats_overall, stats_single):
    """ Aggregate stats for
            - all papers
            - papers per coarse category
            - papers per fine category
            - each year (?)
                -> two dimensional indexing
                -> mby rely on Pandas for this
    """

    pass


def calc_stats(root_dir):
    # set up stats data structure

    # go through JSONLs
    glob_patt = os.path.join(root_dir, '*', '*.jsonl')
    for fp in glob.glob(glob_patt):
        with open(fp) as f:
            for i, line in enumerate(f):
                stats = paper_stats(json.loads(line))
                print(fp)
                print(i)
                from pprint import pprint
                pprint(stats)
                x = input()
                if x == 'q':
                    sys.exit()


"""
{'coarse_cats': ['grp_physics'],
 'fine_cats': ['astro-ph'],
 'license': None,
 'main_coarse_cat': 'grp_physics',
 'main_fine_cat': 'astro-ph',
 'num_cit_markers': 32,
 'num_cit_markers_linked': 3,
 'num_non_text_success': defaultdict(<class 'dict'>,
                                     {'figure': {'fail': 5, 'success': 2},
                                      'formula': {'fail': 0, 'success': 115},
                                      'table': {'fail': 0, 'success': 6}}),
 'num_non_text_types': defaultdict(<class 'int'>,
                                   {'figure': 2,
                                    'formula': 115,
                                    'table': 6}),
 'num_para_types': defaultdict(<class 'int'>, {'paragraph': 34}),
 'num_paras': 34,
 'num_refs': 30,
 'num_refs_linked': 3,
 'year': 2008}
 """

calc_stats('enriched_tmp')
