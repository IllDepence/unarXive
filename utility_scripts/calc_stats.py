import glob
import json
import os
import sys
from arxiv_taxonomy import GROUPS, ARCHIVES, CATEGORIES


def get_fine_arxiv_category_name(cat_id):
    fine_cat = CATEGORIES.get(cat_id, None)
    if fine_cat is not None:
        return fine_cat['name']
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
                return group['name'], group_id
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
    main_cat = None
    fine_cats = []
    coarse_cats = []
    fine_cat_ids = [
        c for c
        in ppr['metadata'].get('categories', '').split(' ')
        if len(c) > 0  # filter when categories is ''
    ]
    for fine_cat_id in fine_cat_ids:
        fine_cat_name = get_fine_arxiv_category_name(fine_cat_id)
        coarse_cat_name, coarse_cat_id = get_coarse_arxiv_category(fine_cat_id)
        if fine_cat_name is not None and coarse_cat_name is not None:
            fine_cats.append(
                (fine_cat_name, fine_cat_id)
            )
            coarse_cats.append(
                (coarse_cat_name, coarse_cat_id)
            )
            if main_cat is None:
                main_cat = (coarse_cat_name, coarse_cat_id)
    coarse_cats = list(set(coarse_cats))
    stats['man_cat'] = main_cat
    stats['coarse_cats'] = coarse_cats
    stats['fine_cats'] = fine_cats

    return stats


def calc_stats(root_dir):
    glob_patt = os.path.join(root_dir, '*', '*.jsonl')
    for fp in glob.glob(glob_patt):
        with open(fp) as f:
            for line in f:
                stats = paper_stats(json.loads(line))
                print(stats)
                x = input()
                if x == 'q':
                    sys.exit()


calc_stats('enriched_tmp')
