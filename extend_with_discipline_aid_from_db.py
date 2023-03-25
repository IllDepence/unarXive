"""
This script takes enhanced chunks of arXiv data and enriches the publications therein with discipline information
and further their included bibliography items with discipline information and arXiv IDs from an OpenAlex data dump,
provided the item matching against the OpenAlex data is successful
"""

from arxiv_taxonomy import GROUPS, ARCHIVES, CATEGORIES
from functools import lru_cache
import psycopg2
import os, json
from multiprocessing import Pool
from collections import OrderedDict
import sys
from datetime import datetime


@lru_cache(maxsize=1000)
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


@lru_cache(maxsize=1000)
def get_coarse_arxiv_group_name(grp_id):
    grp = GROUPS.get(grp_id, None)
    if grp is not None:
        return grp['name']
    return None


@lru_cache(maxsize=None)
def get_disc_and_arxiv_id_from_db(open_alex_id, cursor):
    """ Takes an openalex ID, look into the database table and returns discipline string as well as arxiv_id if present
    """

    openalex_db_id_query = 'SELECT * from papers WHERE openalex_id = %s'
    cursor.execute(openalex_db_id_query, (open_alex_id,))
    matching_openalex_pubs = cursor.fetchall()
    discipline = ""
    arxiv_id = ""
    if len(matching_openalex_pubs) == 1:
        discipline = matching_openalex_pubs[0][3]
        arxiv_id = matching_openalex_pubs[0][-1]
        return discipline, arxiv_id
    elif len(matching_openalex_pubs) > 1:
        # more than 1 match: shouldn't be the case, but check!
        print(f"Note: OpenAlex ID {open_alex_id} not unique in database table")
        return discipline, arxiv_id
    else:
        # no match in database
        return discipline, arxiv_id


def extend_enhanced_arxiv_chunk(jsonl_file_path):
    pub_count = 0
    bib_item_count_processed = 0
    bib_item_count_total = 0
    openalex_match_count = 0
    arxiv_id_success_count = 0

    conn = psycopg2.connect(database=openalex_db_name)
    cursor = conn.cursor()

    # check if folder exists
    chunk_fn = os.path.basename(jsonl_file_path)
    year_dir = os.path.basename(os.path.dirname(jsonl_file_path))
    year_output_dir_path = os.path.join(output_dir_extended_enhanced_jsons, year_dir)
    extended_chunk_fp = os.path.join(year_output_dir_path, chunk_fn)
    if not os.path.exists(year_output_dir_path):
        os.makedirs(year_output_dir_path)

    start_time = datetime.now()

    with open(extended_chunk_fp, "w", encoding="utf-8") as output_chunk:
        with open(jsonl_file_path, 'r', encoding='utf-8') as chunk:
            print(f"New file will be: {extended_chunk_fp}")

            output_chunk_temp = ""

            for publication in chunk:
                try:
                    json_data = json.loads(publication)
                    pub_count += 1

                    primary_cat = json_data.get('metadata', {}).get('categories', '').split(' ')[-1]
                    coarse_cat = get_coarse_arxiv_category(primary_cat)
                    group_cat = get_coarse_arxiv_group_name(coarse_cat)

                    json_data['discipline'] = group_cat

                    # reorder keys and create orderedDict
                    kv_list_temp = [(k, v) for k, v in json_data.items()]
                    # keys ['paper_id', '_pdf_hash', '_source_hash', '_source_name', 'metadata', 'abstract',
                    # 'body_text', 'bib_entries', 'ref_entries', 'discipline']
                    ordering = [0, 1, 2, 3, 4, 9, 5, 6, 7, 8]
                    kv_list_temp[:] = [kv_list_temp[i] for i in ordering]
                    json_data = OrderedDict(kv_list_temp)

                    bib_entries = json_data.get('bib_entries')
                    bib_item_count_total += len(bib_entries)
                    for bib_entry in bib_entries:
                        try:
                            bib_item_count_processed += 1

                            bib_entry_ids = json_data['bib_entries'][bib_entry]['ids']
                            # might throw KeyError if processing of this bibitem was skipped in earlier matching steps

                            json_data['bib_entries'][bib_entry]['discipline'] = ""
                            json_data['bib_entries'][bib_entry]['ids']['arxiv_id'] = ""

                            if len(bib_entry_ids['open_alex_id']) != 0:
                                open_alex_id = bib_entry_ids['open_alex_id'].replace("https://openalex.org/", "")
                                bib_entry_disc, bib_entry_arxiv_id = get_disc_and_arxiv_id_from_db(open_alex_id, cursor)
                                json_data['bib_entries'][bib_entry]['discipline'] = bib_entry_disc
                                json_data['bib_entries'][bib_entry]['ids']['arxiv_id'] = bib_entry_arxiv_id

                                if len(bib_entry_disc) != 0:
                                    openalex_match_count += 1

                                if len(bib_entry_arxiv_id) != 0:
                                    arxiv_id_success_count += 1

                            # reorder content of bibitem dict
                            bib_entry_temp = json_data['bib_entries'][bib_entry]
                            kv_list_sorted = sorted([(k, v) for k, v in bib_entry_temp.items()])
                            bib_entry_temp_sorted = OrderedDict(kv_list_sorted)
                            json_data['bib_entries'][bib_entry] = bib_entry_temp_sorted

                        except KeyError as ke:
                            break


                except Exception as ge:
                    print(f"## General error: {ge} in {json_data['paper_id']} ##")
                    pass

                finally:
                    output_chunk_temp = output_chunk_temp + json.dumps(json_data) + "\n"

        output_chunk.write(output_chunk_temp)

        # write log
        if not os.path.exists(output_dir_extended_enhanced_jsons + "/logs"):
            os.makedirs(output_dir_extended_enhanced_jsons + "/logs")

        with open(
                output_dir_extended_enhanced_jsons + "/logs/" + chunk_fn + "-extension-log.json",
                "w") as log_file:
            end_time = datetime.now()

            if bib_item_count_processed != 0:
                bib_items_openalex_matching_rate = openalex_match_count / bib_item_count_processed
                bib_items_arxiv_id_found_rate = arxiv_id_success_count / bib_item_count_processed
            else:
                bib_items_openalex_matching_rate = 0
                bib_items_arxiv_id_found_rate = 0

            d = {'start_time': start_time.ctime(),
                 'end_time': end_time.ctime(),
                 'runtime_seconds': (end_time - start_time).total_seconds(),
                 'pubs_items_processed': pub_count,
                 'bib_items_total_in_pubs': bib_item_count_total,
                 'bib_items_processed': bib_item_count_processed,
                 'bib_items_matched_with_openalex': openalex_match_count,
                 'bib_items_openalex_matching_rate': bib_items_openalex_matching_rate,
                 'bib_items_arxiv_id_found': arxiv_id_success_count,
                 'bib_items_arxiv_id_found_rate': bib_items_arxiv_id_found_rate}

            json.dump(d, log_file)
            log_file.close()

        chunk.close()
        output_chunk.close()
    conn.close()


if __name__ == '__main__':
    if len(sys.argv) != 7:
        print('usage <in_dir> <out_dir> <openalex_db> <CPU workers>')
        sys.exit()

    input_dir_enhanced_output_jsons = sys.argv[1]  # r'/demo_in'
    output_dir_extended_enhanced_jsons = sys.argv[2]  # r'/demo_out/'
    openalex_db_name = sys.argv[3]  # openalex_db_name = "openalex"
    CPU_THREADS = int(sys.argv[4])

    jsonl_file_list = []
    for path_to_file, subdirs, files in os.walk(input_dir_enhanced_output_jsons):
        for filename in files:
            fn_base, ext = os.path.splitext(filename)
            if ext == '.jsonl':
                fp = os.path.join(path_to_file, filename)
                jsonl_file_list.append(fp)

    print("FILE COUNT to be processed:", len(jsonl_file_list))

    pool = Pool(CPU_THREADS, maxtasksperchild=5)
    pool.map(extend_enhanced_arxiv_chunk, jsonl_file_list)
    pool.close()

    print("### Done with all files ####")
