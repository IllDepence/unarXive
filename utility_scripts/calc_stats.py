import json
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
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


def get_license_fine_name(license_url):
    if license_url is None:
        return 'no license'
    if 'http://arxiv.org/licenses/nonexclusive-distrib/' in license_url:
        return 'arXiv non-exclusive'
    elif 'http://creativecommons.org/' in license_url:
        if 'publicdomain' in license_url:
            return 'Public Domain'
        url_parts = license_url.split('/')
        if url_parts[-4] == 'licenses':
            cc_type = url_parts[-3].upper()
            cc_version = url_parts[-2]
            cc_name = ' ' .join([
                'CC',
                cc_type,
                cc_version
            ])
            return cc_name
    return 'unknown license'


def get_license_coarse_name(license_url):
    fine_name = get_license_fine_name(license_url)
    if fine_name == 'arXiv non-exclusive':
        return fine_name
    elif fine_name == 'Public Domain':
        return fine_name
    elif fine_name[:2] == 'CC':
        return 'Creative Commons'
    else:
        return fine_name


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
    month = pid[2:4]
    stats['month'] = '{}-{}'.format(
        year,
        month
    )

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
    stats['license_url'] = ppr.get('metadata', {}).get('license', None)

    # full text based stats
    num_paras = 0
    num_para_types = defaultdict(int)  # nice for manual work
    num_para_type_paragraph = 0  # v easier to aggregate
    num_para_type_listing = 0
    num_para_type_label = 0
    num_para_type_item = 0
    num_para_type_proof = 0
    num_para_type_pic_put = 0  # ^ easier to aggregate
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
        if para['content_type'] == 'paragraph':
            num_para_type_paragraph += 1
        elif para['content_type'] == 'listing':
            num_para_type_listing += 1
        elif para['content_type'] == 'label':
            num_para_type_label += 1
        elif para['content_type'] == 'item':
            num_para_type_item += 1
        elif para['content_type'] == 'proof':
            num_para_type_proof += 1
        elif para['content_type'] == 'pic-put':
            num_para_type_pic_put += 1
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
    stats['num_para_type_paragraph'] = num_para_type_paragraph
    stats['num_para_type_listing'] = num_para_type_listing
    stats['num_para_type_label'] = num_para_type_label
    stats['num_para_type_item'] = num_para_type_item
    stats['num_para_type_proof'] = num_para_type_proof
    stats['num_para_type_pic_put'] = num_para_type_pic_put
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
    stats['num_fig_succs'] = num_non_text_success['figure'].get(
        'success', 0
    )
    stats['num_fig_fails'] = num_non_text_success['figure'].get(
        'fail', 0
    )
    stats['num_tbl_succs'] = num_non_text_success['table'].get(
        'success', 0
    )
    stats['num_tbl_fails'] = num_non_text_success['table'].get(
        'fail', 0
    )
    stats['num_formula_succs'] = num_non_text_success['formula'].get(
        'success', 0
    )
    stats['num_formula_fails'] = num_non_text_success['formula'].get(
        'fail', 0
    )

    return stats


def get_stats_matrix_indices(max_year=2022):
    """ Create inicies for a matrix of dimension
            num_categories × num_months
        s.t. all categies in a group and all months in a year
        have a continuous range of row/column indices.
    """

    # category axis
    cat_to_idx = {}
    grp_to_idx = defaultdict(list)
    idx = 0
    for gr_key, gr in GROUPS.items():
        for arch_key, arch in ARCHIVES.items():
            if arch['in_group'] != gr_key:
                continue
            for cat_key, cat in CATEGORIES.items():
                if cat['in_archive'] != arch_key:
                    continue
                grp_to_idx[gr_key].append(idx)
                cat_to_idx[cat_key] = idx
                idx += 1
    # month axis
    mon_to_idx = {}
    year_to_idx = defaultdict(list)
    jdx = 0
    for y in range(1991, max_year+1):
        y_key = str(y)
        for m in range(1, 13):
            m_key = '{}-{:02}'.format(y, m)
            year_to_idx[y_key].append(jdx)
            mon_to_idx[m_key] = jdx
            jdx += 1
    # create indices
    indices = {
        'cat_to_idx': cat_to_idx,
        'grp_to_idx': grp_to_idx,
        'mon_to_idx': mon_to_idx,
        'year_to_idx': year_to_idx
    }
    return indices


def get_empty_stats_matrix(indices):
    """ Create a zero filled matrix of dimension
            num_categories × num_months
        s.t. all categies in a group and all months in a year
        have a continuous range of row/column indices.
    """

    stats_matrx = np.zeros(
        (
            len(indices['cat_to_idx']),
            len(indices['mon_to_idx'])
        )
    )
    return stats_matrx


def print_stats_for_groups(mtrxs, idxs):
    """ Showcase
    """

    # for all the stats available
    for stat, mtrx in mtrxs.items():
        print('\n- - - {} - - -'.format(stat))
        # for each arXiv group
        for gk, gi in idxs['grp_to_idx'].items():
            gn = get_coarse_arxiv_group_name(gk)
            # sum up the respective rows over all years
            stat_val = np.sum(mtrx[gi[0]:gi[-1]+1, :])
            print('\t{}: {}'.format(gn, stat_val))


def print_stats_for_years(mtrxs, idxs):
    """ Showcase
    """

    # for all the stats available
    for stat, mtrx in mtrxs.items():
        print('\n- - - {} - - -'.format(stat))
        # for each year
        for yk, yi in idxs['year_to_idx'].items():
            # sum up the respective rows over all categories
            stat_val = np.sum(mtrx[:, yi[0]:yi[-1]+1])
            print('\t{}: {}'.format(yk, stat_val))


def get_cats_over_years_plot_data_quota(mtrxs, idxs, part_key, total_key):
    """ Showcase of data generation for plots that show one stat
        divided by another for each coarse discipline across the years.

        With e.g.
        part_key='num_refs_linked'
        total_key='num_refs'
    """

    ref_succ_rates = {}
    years = list(idxs['year_to_idx'].keys())  # x labels for plot
    for disc, d_idx in idxs['grp_to_idx'].items():
        # for each discipline, create a list of ref matching success
        # rates with one value per year (NOTE: change to month?)
        ref_succ_rates[disc] = []
        for year, y_idx in idxs['year_to_idx'].items():
            val_total = np.sum(mtrxs[total_key][
                d_idx[0]:  # \discipline
                d_idx[-1],  # |slice
                y_idx[0]:  # year
                y_idx[-1]  # slice
            ])
            val_part = np.sum(mtrxs[part_key][
                d_idx[0]:
                d_idx[-1],
                y_idx[0]:
                y_idx[-1]
            ])
            if val_total == 0:
                quota = 0
            else:
                quota = val_part / val_total
            ref_succ_rates[disc].append(quota)
    return ref_succ_rates, years


def demoplot():
    matrices, indices = calc_stats('enriched_tmp')
    succs, yrs = get_cats_over_years_plot_data_quota(
        matrices,
        indices,
        'num_refs_linked',
        'num_refs'
    )
    for gk, vals in succs.items():
        gn = get_coarse_arxiv_group_name(gk)
        plt.plot(yrs, vals, label=gn)

    plt.legend()
    plt.show()


def calc_stats(root_dir):
    """ Calculates a range of stats, each stored in a matrix of dimensions
            num_categories × num_months
        where consecutive sections of rows/columns are category groups/years.

        Toy example:
                            2017                           2018
                        ----- ^ --------------. .------------^-------- - -
                        2017-10 2017-11 2017-12 2018-01 2018-02 2018-03 ...
             /  cs.CL         0       1       2       3       4       5
         cs -|  cs.LG         6       7       8       9       0       1
             \  cs.IT         2       3       4       5       6       7
             /  hep-ph        6       7       0       1       2       1
             |  hep-th        9       0       1       3       4       5
        phys-|  gr-qc         2       3       4       5       6       7
             |  ...


        For each statistical value (num papers, num references, etc.) one
        such matrix is created.
    """

    # set up stats data structure
    ppr_stats_keys = [
        'num_cit_markers',
        'num_cit_markers_linked',
        'num_refs',
        'num_refs_linked',
        'num_paras',
        'num_para_type_paragraph',
        'num_para_type_listing',
        'num_para_type_label',
        'num_para_type_item',
        'num_para_type_proof',
        'num_para_type_pic_put',
        'num_fig_succs',
        'num_fig_fails',
        'num_tbl_succs',
        'num_tbl_fails',
        'num_formula_succs',
        'num_formula_fails'
    ]
    stats_matrix_indices = get_stats_matrix_indices()
    stats_matrix_dict = {}
    aggregrate_only_keys = [
        'num_pprs',
        'num_license_arxiv_non-exclusive',
        'num_license_public_domain',
        'num_license_creative_commons',
        'num_license_no_license',
        'num_license_unknown_license'
    ]
    for k in ppr_stats_keys + aggregrate_only_keys:
        stats_matrix_dict[k] = get_empty_stats_matrix(stats_matrix_indices)

    # go through JSONLs
    jsonl_fps = []
    for path_to_file, subdirs, files in os.walk(root_dir):
        for fn in files:
            fn_base, ext = os.path.splitext(fn)
            if ext == '.jsonl':
                fp = os.path.join(path_to_file, fn)
                if os.path.getsize(fp) > 0:
                    jsonl_fps.append(fp)
    print('found {} JSONLs to parse'.format(len(jsonl_fps)))
    for fp in jsonl_fps:
        with open(fp) as f:
            for i, line in enumerate(f):
                ppr_stats = paper_stats(json.loads(line))
                # get stats matrix indices
                cat = ppr_stats['main_fine_cat']
                mon = ppr_stats['month']
                cat_m_idx = stats_matrix_indices['cat_to_idx'][cat]
                mon_m_idx = stats_matrix_indices['mon_to_idx'][mon]
                # add to ppr count
                stats_matrix_dict['num_pprs'][cat_m_idx][mon_m_idx] += 1
                # add license counts
                license_stats_key = 'num_license_{}'.format(
                    get_license_coarse_name(
                        ppr_stats['license_url']
                    ).replace(' ', '_').lower()
                )
                stats_matrix_dict[license_stats_key][cat_m_idx][mon_m_idx] += 1
                # add to other keys
                for stats_key in ppr_stats_keys:
                    stats_matrix_dict[
                        stats_key
                    ][cat_m_idx][mon_m_idx] += ppr_stats[stats_key]
    return stats_matrix_dict, stats_matrix_indices


if __name__ == '__main__':
    pass
