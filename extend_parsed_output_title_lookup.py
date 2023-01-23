import psycopg2
import json
import os
import glob
import re
import unidecode
import unicodedata
import sqlite3
import requests
import subprocess
import lxml
import sys
import traceback
from bs4 import BeautifulSoup
from datetime import datetime, time
from multiprocessing import Pool
from psycopg2.extras import Json, DictCursor


ARXIV_URL_PATT = re.compile(
    r'arxiv\.org\/[a-z0-9-]{1,10}\/(([a-z0-9-]{1,15}\/)?[\d\.]{4,9}\d)', re.I)
ARXIV_ID_PATT = re.compile(
    r'arXiv:(([a-z0-9-]{1,15}\/)?[\d\.]{4,9}\d)', re.I)
ARXIV_ID_PATT_DATE = re.compile(
    r'^([a-zA-Z-\.]+)?\/?(\d\d)(\d\d)(.*)$')
DOI_PATT = re.compile(
    r'10.\d{4,9}/[-._;()/:A-Z0-9]+$', re.I)
FORMULA_PATT = re.compile(
    '\{\{formula:.{36}\}\}', re.I)


def find_arxiv_id(text):
    """ Loor for an arXiv ID within the given text.
    """

    match = ARXIV_ID_PATT.search(text)
    if match:
        return match.group(1)
    else:
        match = ARXIV_URL_PATT.search(text)
        if match:
            return match.group(1)
    return False


def title_lookup_in_arxiv_metadata_db(arxiv_id, cursor_arxiv, ppr_year, ppr_month):
    # columns in table named paper:
    # year, month, aid, title, json

    query_aid_string = "SELECT  json from paper where year=? and month=? and aid=?"
    #query_aid_string = "SELECT title from paper WHERE aid= ?"
    metadata_tup  = cursor_arxiv.execute(query_aid_string, (ppr_year, ppr_month, str(arxiv_id),)).fetchone()
    try:
        metadata = json.loads(metadata_tup[0])
    except (TypeError, IndexError) as e:
        return {}
    return metadata.get('title', '')


def find_title_in_crossref_by_doi(given_doi):
    """ Given a DOI, try to get a work's title using crossref.org
    """

    doi_base_url = "https://api.crossref.org/works/"
    mail = 'tarek,saier@kit.edu'
    req = '{}{}?mailto={}'.format(
        doi_base_url,
        given_doi,
        mail
    )
    try:
        resp = requests.get(
            req,
            timeout=360
        )

        rate_lim_lim = resp.headers.get('X-Rate-Limit-Limit', '9001')
        rate_lim_int = resp.headers.get(
            'X-Rate-Limit-Interval',
            '1s'
        ).replace('s', '')
    except requests.RequestException:
        print("Request Exception")
        return False
    try:
        wait = float(rate_lim_int) / float(rate_lim_lim)
        if resp.elapsed.total_seconds() < wait:
            delta = wait - resp.elapsed.total_seconds()
            delta = max(delta, 3600)
            time.sleep(delta)
    except ValueError:
        pass
    try:
        title = resp.json()['message']['title'][0]
        # print(doi_metadata)
        if title and len(title) > 0:
            return title
    except json.decoder.JSONDecodeError:
        print("JSON decode error")
        return False


def find_title_with_grobid_in_string(grobid_url, bib_ref_string):
    response = requests.post(grobid_url, data={'citations': bib_ref_string})

    if response.status_code == 200:
        return response.text
    else:
        return False


def normalize_title(title_string):
    title_string_norm = re.sub('[^\w]', ' ', title_string)
    title_string_norm = re.sub('\s+', ' ', title_string_norm)
    title_string_norm = unicodedata.normalize('NFD', title_string_norm)
    title_string_norm = unidecode.unidecode(title_string_norm)
    return title_string_norm.strip().lower()


def normalize_author_name(author_string):
    author_string_norm = re.sub('[^\w]', ' ', author_string)
    author_string_norm = re.sub('\s+', ' ', author_string_norm)
    author_string_norm = unicodedata.normalize('NFD', author_string_norm)
    author_string_norm = unidecode.unidecode(author_string_norm)
    return author_string_norm.strip().lower()


def item_authors_in_ref_string(openalex_item_authors_list, ref_string):
    any_author_in_ref_string = False
    ref_string_normalized = normalize_author_name(ref_string)
    for openalex_item_author in openalex_item_authors_list:
        if openalex_item_author.split(" ")[-1] in ref_string_normalized.split(
                " "):  # check occurence of author in token-wise ref string
            # print(openalex_item_author.split(" ")[-1])  # last name
            any_author_in_ref_string = True

    return any_author_in_ref_string


def vary_title_window(normalized_title_string):
    title_tokenized = normalized_title_string.split(" ")
    title_omit_first_token = title_tokenized[1:]
    title_omit_first_token = " ".join(title_omit_first_token)
    title_omit_last_token = title_tokenized[:-1]
    title_omit_last_token = " ".join(title_omit_last_token)
    return title_omit_first_token, title_omit_last_token


def match_title_in_openalexdb(query_string, bib_entry_title_norm, bib_entry_ref_string, cursor,
                              try_title_windows_flag):
    cursor.execute(query_string, (bib_entry_title_norm,))
    matching_openalex_pubs = cursor.fetchall()

    # if only one result is found, proceed to handover IDs from openalexdb
    if len(matching_openalex_pubs) == 1:
        # print("Ein passender Eintrag in openalexdb gefunden - check if author in OpenAlex entry")

        # look for authors in bib_entry_ref_string
        openalex_item_authors_list = matching_openalex_pubs[0][2]
        if item_authors_in_ref_string(openalex_item_authors_list, bib_entry_ref_string):
            return matching_openalex_pubs[0]

        # author not found in refstring
        else:
            # print('Authors maintained in OpenAlex for current item not present in ref string - no match - item skipped')
            return

    # more than one possible title match found in openalexdb
    elif len(matching_openalex_pubs) > 1:
        # print(
        # "Mehr als ein Eintrag mit passendem titel gefunden - select those with authors present in ref string - from these, start citation sort")

        matching_openalex_pubs_with_author_present = []
        for match in matching_openalex_pubs:
            openalex_item_authors_list = match[2]

            # consider only the title matched pubs that have an author match with the ref string for citation count comparison in the next step
            if item_authors_in_ref_string(openalex_item_authors_list, bib_entry_ref_string):
                matching_openalex_pubs_with_author_present.append(match)

        # iterate through returned matches to identify and select the most cited
        if len(matching_openalex_pubs_with_author_present) != 0:
            citation_counts_of_matches = []
            for match in matching_openalex_pubs_with_author_present:
                citation_counts_of_matches.append(match[3])

            index_of_most_cited_in_match_list = citation_counts_of_matches.index(max(citation_counts_of_matches))
            matched_openalex_pub = matching_openalex_pubs_with_author_present[index_of_most_cited_in_match_list]
            # print(matching_openalex_pubs)
            return matched_openalex_pub

        else:
            # print(
            # 'Authors maintained in OpenAlex for title matched items all not present in ref string - no matches - items skipped')
            return

    # no match found -> try alternate title substrings and redo search
    elif len(matching_openalex_pubs) == 0:
        if try_title_windows_flag:
            # print("NIX gefunden - no match of title in OpenAlex - check different window of title")
            bib_entry_title_norm_omit_first, bib_entry_title_norm_omit_last = vary_title_window(bib_entry_title_norm)

            matched_openalex_pub = match_title_in_openalexdb(query_string, bib_entry_title_norm_omit_first,
                                                             bib_entry_ref_string, cursor, False)
            if matched_openalex_pub is not None:
                return matched_openalex_pub
            else:
                matched_openalex_pub = match_title_in_openalexdb(query_string, bib_entry_title_norm_omit_last,
                                                                 bib_entry_ref_string, cursor, False)
                if matched_openalex_pub is not None:
                    return matched_openalex_pub
                else:
                    # occurs when no match is found for original, and both window versions of the bib_entry_title
                    return
        else:
            # occurs when calling this matching function with flag for trying different title windows = False (usually in 1st recursive call of function to avoid infinite call loop)
            # print("NIX gefunden - no match of title in OpenAlex - check for different title windows SKIPPED")
            # print(f"[OA lookup] unsucessful for title {bib_entry_title_norm}")
            return

    else:
        print(f"Unhandled matching scenario occurred. Bib ref string: {bib_entry_ref_string}")
        return


def map_ids_from_openalexdb_match_to_dict(matched_pub_from_db):
    id_keys_in_output = ['open_alex_id', 'sem_open_alex_id', 'pubmed_id', 'pmc_id', 'doi']
    openalexdb_match_ids = matched_pub_from_db[4]  # ids are in column [4] of the returned data from OpenAlex table
    bib_entry_ids_dict = {}

    # go through all four ID types in openalexdb and add to temporary bib_entry_ids_dict
    # recall openalexdb IDs column structure: list of IDs [oa_id, pubmedid, pmcid, doi]
    # recall desired dict structure: id_keys_in_output = ['open_alex_id', 'sem_open_alex_id', 'pubmed_id', 'pmc_id', 'doi', 'arXiv_id]
    #                                                             not in openalex data -> needs to be determined later somehow ^

    bib_entry_ids_dict[id_keys_in_output[0]] = ""
    if len(openalexdb_match_ids[0]) != 0:
        bib_entry_ids_dict[id_keys_in_output[0]] = 'https://openalex.org/' + openalexdb_match_ids[0]

    bib_entry_ids_dict[id_keys_in_output[1]] = ""
    if len(openalexdb_match_ids[0]) != 0:
        bib_entry_ids_dict[id_keys_in_output[1]] = 'https://semopenalex.org/work/' + openalexdb_match_ids[0]

    #    ↓ field in `ids` dict ↓                ↓ [oa_id, pubmedid, pmcid, doi]
    bib_entry_ids_dict[id_keys_in_output[2]] = openalexdb_match_ids[1]
    bib_entry_ids_dict[id_keys_in_output[3]] = openalexdb_match_ids[2]
    bib_entry_ids_dict[id_keys_in_output[4]] = openalexdb_match_ids[3]

    return bib_entry_ids_dict


def extend_parsed_arxiv_chunk(params):
    jsonl_file_path, output_root_dir, match_db_host, meta_db_uri, grobid_url = params
    i = 0
    bib_item_counter = 0
    bib_item_no_title_error_counter = 0
    bib_item_title_not_in_openalex_error_counter = 0
    saved_requests_counter = 0
    start_time = datetime.now()

    # create connection to local openalex database (with openalex and crossref tables)
    conn = psycopg2.connect(
        host=match_db_host,
        database='openalex',
        user='unarxive_matching',
        password='over9000bibitems'
    )
    cursor = conn.cursor()

    # connection to local arxiv db for lookup using arxiv ID
    connection_arxiv_db = sqlite3.connect(meta_db_uri)
    cursor_arxiv = connection_arxiv_db.cursor()

    # check if folder exists
    chunk_fn = jsonl_file_path.split("/")[-1]  # FIXME: use os.path instead of
    year_dir = jsonl_file_path.split("/")[-2]  # fiddling with strings manuall
    year_dir_path = os.path.join(output_root_dir, year_dir)
    enriched_chunk_fp = os.path.join(year_dir_path, chunk_fn)
    if not os.path.exists(year_dir_path):
        os.makedirs(year_dir_path)

    with open(enriched_chunk_fp, "w", encoding="utf-8") as output_chunk:
        with open(jsonl_file_path, 'r', encoding='utf-8') as chunk:
            print("Worker reading file ", jsonl_file_path, "..")
            output_chunk_temp = ""
            for publication in chunk:
                try:
                    json_data = json.loads(publication)
                    # print(json_data['paper_id'], json_data['bib_entries'])

                    # iterate through all bib_entries of current paper
                    # entries have form:
                    # {'bib_entry_raw': 'N. Doroud, J. Gomis, B. Le Floch, and S. Lee, “Exact Results in D=2 Supersymmetric Gauge Theories,” JHEP 05 (2013) 093, arXiv:1206.2606 [hep-th].', 'contained_arXiv_ids': ['1206.2606'], 'contained_links': ['http://dx.doi.org/10.1007/JHEP05(2013)093']}

                    for bib_entry in json_data['bib_entries']:

                        bib_item_counter += 1
                        bib_entry_aid = None
                        title = None
                        grobid_flag = False

                        # look for arxiv ID in parsed bib entry data
                        if len(json_data['bib_entries'][bib_entry]['contained_arXiv_ids']) != 0:

                            # print (json_data['bib_entries'][bib_entry])
                            bib_entry_aid = json_data['bib_entries'][bib_entry]['contained_arXiv_ids']
                            # print(bib_entry_aid, "ID in Parsed data")

                        # look for arxiv ID in full ref string of bib item
                        else:
                            bib_entry_regex_test = find_arxiv_id(json_data['bib_entries'][bib_entry]['bib_entry_raw'])
                            if bib_entry_regex_test is not False:
                                bib_entry_aid = bib_entry_regex_test
                                # print(bib_entry_aid, "REGEX")

                        # if arxiv ID is determined either way, check metadata arxiv db to get clean title
                        if bib_entry_aid is not None:

                            try:
                                # if multiple arxiv ids or dict in parsed data, choose first one of that list for the current bib item
                                if type(bib_entry_aid) is list:
                                    if len(bib_entry_aid) != 0:
                                        # example entry [{'id': '1101.2663', 'text': 'arXiv:1101.2663 [hep-ex] .', 'start': 50, 'end': 76}]

                                        #def title_lookup_in_arxiv_metadata_db(arxiv_id, cursor_arxiv, ppr_year,ppr_month):
                                        aid = str(bib_entry_aid[0]['id'])
                                        aid_m = ARXIV_ID_PATT_DATE.match(aid)
                                        aid_year = aid_m.group(2)
                                        aid_month = aid_m.group(3)

                                        title_from_arxive_meta_db = title_lookup_in_arxiv_metadata_db(
                                            aid, cursor_arxiv, aid_year, aid_month)
                                else:
                                    aid_m = ARXIV_ID_PATT_DATE.match(str(bib_entry_aid))
                                    aid_year = aid_m.group(2)
                                    aid_month = aid_m.group(3)
                                    title_from_arxive_meta_db = title_lookup_in_arxiv_metadata_db(str(bib_entry_aid),
                                                                                                  cursor_arxiv, aid_year, aid_month)

                                if title_from_arxive_meta_db is not None:
                                    if len(title_from_arxive_meta_db) != 0:
                                        title = title_from_arxive_meta_db
                                        # print("[arxive db] success - title found")

                            except IndexError as indexerror:
                                # print("indexerror encountered.")
                                # print(bib_entry_aid)
                                # print(traceback.format_exc())
                                pass

                            except Exception as e:
                                print(e)
                                pass

                        # retrieve title from crossref (look for DOI in contained links)
                        if title is None:
                            if len(json_data['bib_entries'][bib_entry]['contained_links']) != 0:
                                # multiple urls possible in list
                                for bib_item_url in json_data['bib_entries'][bib_entry]['contained_links']:

                                    # print('Doi patt search using URL link')
                                    bib_item_url = json_data['bib_entries'][bib_entry]['contained_links']
                                    for url in bib_item_url:
                                        try:
                                            bib_item_doi = DOI_PATT.search(url)
                                            # print(bib_item_doi)
                                            if bib_item_doi is not None:
                                                if len(bib_item_doi[0]) != 0:

                                                    # check whether there's already a title for this DOI in local crossref table
                                                    crossrefdb_title_query = "SELECT * from crossref WHERE doi=%s"
                                                    cursor.execute(crossrefdb_title_query, (bib_item_doi[0],))
                                                    crossref_matching_pub = cursor.fetchall()

                                                    if len(crossref_matching_pub) == 1:
                                                        print(
                                                            "[crossref db] Ein passender Eintrag in local crossrefdb gefunden")
                                                        print(crossref_matching_pub[0][1])
                                                        title = crossref_matching_pub[0][1]
                                                        saved_requests_counter += 1

                                                    elif len(crossref_matching_pub) > 1:
                                                        print(
                                                            "[crossref db] more than one crossref entry for the current doi?! :",
                                                            bib_item_doi[0])
                                                        title = crossref_matching_pub[0][1]
                                                        saved_requests_counter += 1

                                                    elif len(crossref_matching_pub) == 0:
                                                        print(
                                                            "[crossref db] not in crossref db yet - call API and write to db ")

                                                        crossref_api_result = find_title_in_crossref_by_doi(
                                                            bib_item_doi[0])
                                                        if crossref_api_result is not False:
                                                            print(
                                                                '[crossref API] title found in crossref API - writing to db')
                                                            title = crossref_api_result

                                                            # write title to db
                                                            cursor.execute(
                                                                "INSERT INTO crossref (doi, title) VALUES (%s,%s)",
                                                                (bib_item_doi[0], title))
                                                            conn.commit()


                                        except TypeError as te:
                                            pass

                                        # for the unprobable case that two threads look up the title for same DOI
                                        # at the same time and try to write to table (DOI is primary key)
                                        except psycopg2.IntegrityError as ie:
                                            pass

                        # find title with GROBID in ref string
                        if title is None:
                            bib_item_ref_string = json_data['bib_entries'][bib_entry]['bib_entry_raw']

                            # remove quote characters from bib ref string (they disturb curl API call)
                            bib_item_ref_string_clean = bib_item_ref_string.replace('"', '').replace("'", "").replace(
                                '„', '').replace('“', '').replace('‟', '').replace('”', '').replace('`', '')

                            # check for formula entries and replace with actual (latex) content
                            match = FORMULA_PATT.search(bib_item_ref_string_clean)

                            if match is not None:
                                # at least one formula in title
                                match = FORMULA_PATT.finditer(bib_item_ref_string_clean)
                                for m in match:
                                    formula_ref_string = m.group(0)
                                    formula_ref_key = formula_ref_string.replace("{{formula:", "").replace("}}", "")
                                    # print("[regex formula] replacing formula in title:", bib_item_ref_string_clean)
                                    bib_item_ref_string_clean = bib_item_ref_string_clean.replace(formula_ref_string,
                                                                                                  json_data['ref_entries'][
                                                                                                      formula_ref_key][
                                                                                                      'latex'])
                                    # print("[regex formula] replaced formula in title:", bib_item_ref_string_clean)

                            # get title from GROBID API
                            grobid_bibstruct_xml = find_title_with_grobid_in_string(grobid_url, bib_item_ref_string_clean)

                            if grobid_bibstruct_xml:
                                grobid_returned_data_xml = BeautifulSoup(grobid_bibstruct_xml, 'lxml')
                                grobid_title_results = grobid_returned_data_xml.findAll('title')

                                for t in grobid_title_results:

                                    if title is None:
                                        # grobid output marked as title:
                                        # [<title level="a" type="main">The spectral radius of the Coxeter transformations for a generalized Cartan matrix</title>, <title level="j">Math. Ann</title>]
                                        # key "type" not always present

                                        try:
                                            if t['type'] == "main":
                                                title = t.get_text(strip=True)
                                                grobid_flag = True
                                                # print(t['type'], title)
                                        except KeyError as ke:
                                            if t.get_text(strip=True) is not None:
                                                if len(t.get_text(strip=True)) is not 0:
                                                    title = t.get_text(strip=True)
                                                    grobid_flag = True
                                            pass

                        # no title identifiable for this ref string (is skipped)
                        if title is None:
                            # print("[title extraction] No title identifiable in: ", bib_item_ref_string)
                            bib_item_no_title_error_counter += 1

                            # append empty ids dict.
                            json_data['bib_entries'][bib_entry]['ids'] = {}
                            json_data['bib_entries'][bib_entry]['ids']['open_alex_id'] = ""
                            json_data['bib_entries'][bib_entry]['ids']['sem_open_alex_id'] = ""
                            json_data['bib_entries'][bib_entry]['ids']['pubmed_id'] = ""
                            json_data['bib_entries'][bib_entry]['ids']['pmc_id'] = ""
                            json_data['bib_entries'][bib_entry]['ids']['doi'] = ""

                        # title is found and now used to check (local) OpenAlex database
                        if title is not None:
                            bib_item_title_norm = normalize_title(title)
                            bib_item_ref_string = json_data['bib_entries'][bib_entry]['bib_entry_raw']

                            # look at "left" 1000 characters in normalized title for lookup using index
                            openalexdb_title_query = 'SELECT * from openalex WHERE ("left"(normalized_title::text, 1000)) = %s'
                            # openalexdb_title_query = "SELECT * from openalex WHERE normalized_title=%s"

                            # look into openalex table, look for normalized item(s) with same title, do citation and author lookup
                            # use returned pub for additional info on work IDs

                            # SELECT * FROM openalex where normalized_title='probability threshold indexing' LIMIT 10;
                            # SELECT * FROM openalex WHERE("left"(normalized_title::text, 1000)) = 'probability threshold indexing' LIMIT 10;

                            # print('[OA lookup] start lookup for title:', bib_item_title_norm)
                            matching_openalex_pub = match_title_in_openalexdb(openalexdb_title_query,
                                                                              bib_item_title_norm,
                                                                              bib_item_ref_string, cursor, grobid_flag)

                            if matching_openalex_pub is None:
                                # print('[OA lookup] no match was returned for:', bib_item_title_norm)
                                bib_item_title_not_in_openalex_error_counter += 1

                                # append empty ids dict.
                                json_data['bib_entries'][bib_entry]['ids'] = {}
                                json_data['bib_entries'][bib_entry]['ids']['open_alex_id'] = ""
                                json_data['bib_entries'][bib_entry]['ids']['sem_open_alex_id'] = ""
                                json_data['bib_entries'][bib_entry]['ids']['pubmed_id'] = ""
                                json_data['bib_entries'][bib_entry]['ids']['pmc_id'] = ""
                                json_data['bib_entries'][bib_entry]['ids']['doi'] = ""

                            elif matching_openalex_pub is not None:
                                # print('[OA lookup] MATCH was returned - adding IDs from OpenAlex DB to current publication json')
                                bib_entry_ids_dict = map_ids_from_openalexdb_match_to_dict(matching_openalex_pub)

                                # add data from OpenAlex to JSON object of current publication
                                json_data['bib_entries'][bib_entry]['ids'] = {}   # TODO: maybe use a OrderedDict
                                json_data['bib_entries'][bib_entry]['ids']['open_alex_id'] = bib_entry_ids_dict[
                                    'open_alex_id']
                                json_data['bib_entries'][bib_entry]['ids']['sem_open_alex_id'] = bib_entry_ids_dict[
                                    'sem_open_alex_id']
                                json_data['bib_entries'][bib_entry]['ids']['pubmed_id'] = bib_entry_ids_dict[
                                    'pubmed_id']
                                json_data['bib_entries'][bib_entry]['ids']['pmc_id'] = bib_entry_ids_dict['pmc_id']
                                json_data['bib_entries'][bib_entry]['ids']['doi'] = bib_entry_ids_dict['doi'].replace(
                                    "https://doi.org/", "").replace("http://doi.org/", "")

                                # if len(json_data['bib_entries'][bib_entry]['contained_arXiv_ids']) != 0:
                                #    json_data['bib_entries'][bib_entry]['ids']['arXiv_id'] = \
                                #        json_data['bib_entries'][bib_entry]['contained_arXiv_ids'][0]
                                # else:
                                #    json_data['bib_entries'][bib_entry]['ids']['arXiv_id'] = ""

                        # print("bib item count ",bib_item_counter, "i:",i)
                        # print(json_data['bib_entries'][bib_entry])

                        # print update log to screen
                        if bib_item_counter % 5000 == 0:
                            print(f"Update for chunk " + {jsonl_file_path})
                            print(f"Error rate for title determination in bibitems:",
                                  bib_item_no_title_error_counter, "/", bib_item_counter,
                                  "\t | Success = {:.2f}".format(
                                      100 * ((bib_item_counter - bib_item_no_title_error_counter) / bib_item_counter)))
                            print("Error rate for title matching with OpenAlex for bibitems:",
                                  bib_item_title_not_in_openalex_error_counter, "/", bib_item_counter,
                                  "\t | Success = {:.2f}".format(
                                      100 * ((
                                                     bib_item_counter - bib_item_title_not_in_openalex_error_counter) / bib_item_counter)))

                except Exception as ge:
                    #print("## General error: "+str(ge)+" ##")
                    pass

                finally:
                    # print(f"Done with publication, writing json to chunk of {jsonl_file_path}..")
                    output_chunk_temp = output_chunk_temp + json.dumps(json_data) + "\n"
                    # output_chunk.write(output_chunk_temp)
                    # output_chunk.write("\n")

                i += 1
                if i % 100 == 0:
                    print("### publication no.", i, "in current file ###")

            output_chunk.write(output_chunk_temp)

            print(f"Worker done with chunk file {jsonl_file_path}. \nErrors in title determination in bibitems:",
                  bib_item_no_title_error_counter, "/",
                  bib_item_counter)
            print("Success quota (fraction of titles successfully determined) = {:.2f}".format(
                100 * ((bib_item_counter - bib_item_no_title_error_counter) / bib_item_counter)))

            print("Error rate for title matching with OpenAlex for bibitems with determined title:",
                  bib_item_title_not_in_openalex_error_counter, "/",
                  (bib_item_counter - bib_item_no_title_error_counter),
                  "\t | Success = {:.2f}".format(
                      100 * ((
                                     bib_item_counter - bib_item_title_not_in_openalex_error_counter - bib_item_no_title_error_counter) / (
                                         bib_item_counter - bib_item_no_title_error_counter))))
            print("Overall bib_item_matching_success_quota = {:.2f}".format((
                                                                                        bib_item_counter - bib_item_no_title_error_counter - bib_item_title_not_in_openalex_error_counter) / bib_item_counter))

            if not os.path.exists(output_root_dir + "logs"):
                os.makedirs(output_root_dir + "logs")

            # write log
            with open(
                    output_root_dir + "logs/" + jsonl_file_path.split("/")[-1] + "-matching-log.json",
                    "w") as log_file:
                end_time = datetime.now()

                d = {'start_time': start_time.ctime(),
                     'end_time': end_time.ctime(),
                     'runtime_seconds': (end_time - start_time).total_seconds(),
                     'bib_items_processed': bib_item_counter,
                     'bib_items_error_no_title': bib_item_no_title_error_counter,
                     'bib_items_error_no_match_in_openalex': bib_item_title_not_in_openalex_error_counter,
                     'bib_item_matching_success_quota': ((
                                                                 bib_item_counter - bib_item_no_title_error_counter - bib_item_title_not_in_openalex_error_counter) / bib_item_counter),
                     'crossref_requests_saved': saved_requests_counter}

                json.dump(d, log_file)
                log_file.close()

            bib_item_counter = 0
            bib_item_no_title_error_counter = 0
            saved_requests_counter = 0
            chunk.close()
        output_chunk.close()
    conn.close()
    connection_arxiv_db.close()


def match(in_dir, out_dir, match_db_host, meta_db_uri, grobid_url, num_workers):
    # in_dir = '/opt/unarXive_2022/arxiv_parsed'
    # out_dir = '/opt/unarXive_2022/parsed_data_enriched/'
    # match_db_host = '129.13.152.175'
    # meta_db_uri = '/opt/unarXive_2022/unarXive_code_repo/arxiv-metadata-oai-snapshot_230101.sqlite'
    # grobid_url = 'http://localhost:8070/api/processCitation'
    input_fns_glob_patt = os.path.join(
        in_dir,     # root dir path
        '*',        # year dir
        '*.jsonl'   # JSONl files
    )

    # collect all .jsonl chunks to iterate over with multiple workers
    # (see no. of CPU THREADS above)
    worker_params = []
    for input_file_path in glob.glob(input_fns_glob_patt):
        worker_params.append(
            (
                input_file_path,
                out_dir,
                match_db_host,
                meta_db_uri,
                grobid_url
            )
        )

    pool = Pool(num_workers, maxtasksperchild=5)
    pool.map(extend_parsed_arxiv_chunk, worker_params)
    pool.close()


if __name__ == '__main__':
    if len(sys.argv) != 7:
        print('usage ...')
        sys.exit()

    in_dir = sys.argv[1]
    out_dir = sys.argv[2]
    match_db_host = sys.argv[3]
    meta_db_uri = sys.argv[4]
    grobid_url = sys.argv[5]
    num_workers = int(sys.argv[6])
    match(in_dir, out_dir, match_db_host, meta_db_uri, grobid_url, num_workers)
