import psycopg2
from psycopg2.extras import Json, DictCursor
import json
import os
import glob
import gzip
import re
import unidecode
import unicodedata
import jsonlines
import sqlite3
import requests
from datetime import time
import subprocess
import lxml
from bs4 import BeautifulSoup

# handy comments
# scp openalex_linkage\extend_parsed_output_title_lookup.py udevz@aifb-ls3-icarus.aifb.kit.edu:/opt/unarXive_2022
# scp .\chunk_1.jsonl udevz@aifb-ls3-icarus.aifb.kit.edu:/opt/unarXive_2022/parsed_data


ARXIV_URL_PATT = re.compile(
    r'arxiv\.org\/[a-z0-9-]{1,10}\/(([a-z0-9-]{1,15}\/)?[\d\.]{4,9}\d)', re.I)
ARXIV_ID_PATT = re.compile(
    r'arXiv:(([a-z0-9-]{1,15}\/)?[\d\.]{4,9}\d)', re.I)
DOI_PATT = re.compile(
    r'10.\d{4,9}/[-._;()/:A-Z0-9]+$', re.I)


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


def title_lookup_in_arxive_metadata_db(arxive_id):
    connection = sqlite3.connect("unarXive_code_repo/arxiv-metadata-oai-snapshot_221115.sqlite")
    cursor = connection.cursor()

    # columns in table named paper:
    # year, month, aid, title, json

    query_aid_string = "SELECT title from paper WHERE aid= ?"

    metadata_title = cursor.execute(query_aid_string, (str(arxive_id),)).fetchall()
    connection.close()

    return metadata_title[0][0]


def find_title_in_crossref_by_doi(given_doi):
    """ Given a DOI, try to get a work's title using crossref.org
    """

    # doi_base_url = 'https://data.crossref.org/'
    doi_headers = {'Accept': 'json',
                   'User-Agent': ('DoiToTitleScript (working on title extraction)', 'mailto:udevz@student.kit.edu')}

    doi_base_url = "https://api.crossref.org/works/"
    req = '{}{}'.format(doi_base_url, given_doi) + '?mailto=udevz@student.kit.edu'
    try:
        resp = requests.get(
            req,
            # headers=doi_headers,
            timeout=360
        )

        rate_lim_lim = resp.headers.get('X-Rate-Limit-Limit', '9001')
        rate_lim_int = resp.headers.get('X-Rate-Limit-Interval', '1s').replace('s', '')
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


def find_title_with_grobid_in_string(bib_ref_string):
    grobid_call_string = f'curl -X POST -d "citations={bib_ref_string}" localhost:8070/api/processCitation'
    data = subprocess.Popen(grobid_call_string, stdout=subprocess.PIPE, shell=True) #
    (output, err) = data.communicate()
    return output, err


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
            print(openalex_item_author.split(" ")[-1])  # last name
            any_author_in_ref_string = True

    return any_author_in_ref_string


def vary_title_window(normalized_title_string):
    title_tokenized = normalized_title_string.split(" ")
    title_omit_first_token = title_tokenized[1:]
    title_omit_first_token = " ".join(title_omit_first_token)
    title_omit_last_token = title_tokenized[:-1]
    title_omit_last_token = " ".join(title_omit_last_token)
    return title_omit_first_token, title_omit_last_token


def match_title_in_openalexdb(query_string, bib_entry_title_norm, bib_entry_ref_string, connection,
                              try_title_windows_flag):
    cursor = connection.cursor()
    cursor.execute(query_string, (bib_entry_title_norm,))
    matching_openalex_pubs = cursor.fetchall()

    # if only one result is found, proceed to handover IDs from openalexdb
    if len(matching_openalex_pubs) == 1:
        print("Ein passender Eintrag in openalexdb gefunden - check if author in OpenAlex entry")

        # look for authors in bib_entry_ref_string
        openalex_item_authors_list = matching_openalex_pubs[0][2]
        if item_authors_in_ref_string(openalex_item_authors_list, bib_entry_ref_string):
            return matching_openalex_pubs[0]

        # author not found in refstring
        else:
            print('Authors maintained in OpenAlex for current item not present in ref string - no match - item skipped')
            return

    # more than one possible title match found in openalexdb
    elif len(matching_openalex_pubs) > 1:
        print(
            "Mehr als ein Eintrag mit passendem titel gefunden - select those with authors present in ref string - from these, start citation sort")

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
            print(matching_openalex_pubs)
            return matched_openalex_pub

        else:
            print(
                'Authors maintained in OpenAlex for title matched items all not present in ref string - no matches - items skipped')
            return

    # no match found -> try alternate title substrings and redo search
    elif len(matching_openalex_pubs) == 0:
        if try_title_windows_flag:
            print("NIX gefunden - no match of title in OpenAlex - check different window of title")
            bib_entry_title_norm_omit_first, bib_entry_title_norm_omit_last = vary_title_window(bib_entry_title_norm)

            matched_openalex_pub = match_title_in_openalexdb(query_string, bib_entry_title_norm_omit_first,
                                                             bib_entry_ref_string, False)
            if matched_openalex_pub is not None:
                return matched_openalex_pub
            else:
                matched_openalex_pub = match_title_in_openalexdb(query_string, bib_entry_title_norm_omit_last,
                                                                 bib_entry_ref_string, False)
                if len(matched_openalex_pub) is not None:
                    return matched_openalex_pub
                else:
                    # occurs when no match is found for original, and both window versions of the bib_entry_title
                    return
        else:
            # occurs when calling this matching function with flag for trying different title windows = False (usually in 1st recursive call of function to avoid infinite call loop)
            print("NIX gefunden - no match of title in OpenAlex - check for different title windows SKIPPED")
            return

    else:
        print("Unhandled matching scenario occurred.")
        return


id_keys_in_output = ['open_alex_id', 'sem_open_alex_id', 'pubmed_id', 'pmc_id', 'doi']


def map_ids_from_openalexdb_match_to_dict(matched_pub_from_db):
    openalexdb_match_ids = matched_pub_from_db[4]
    bib_entry_ids_dict = {}

    # go through all four ID types in openalexdb and add to temporary bib_entry_ids_dict
    # recall openalexdb IDs column structure: list of IDs [oa_id, pubmedid, pmcid, doi]
    # recall wanted dict structure: id_keys_in_output = ['open_alex_id', 'sem_open_alex_id', 'pubmed_id', 'pmc_id', 'doi']

    bib_entry_ids_dict[id_keys_in_output[0]] = 'https://openalex.org/' + openalexdb_match_ids[0]
    bib_entry_ids_dict[id_keys_in_output[1]] = 'https://semopenalex.org/' + openalexdb_match_ids[0]
    bib_entry_ids_dict[id_keys_in_output[2]] = openalexdb_match_ids[1]
    bib_entry_ids_dict[id_keys_in_output[3]] = openalexdb_match_ids[2]
    bib_entry_ids_dict[id_keys_in_output[4]] = openalexdb_match_ids[3]

    return bib_entry_ids_dict


input_dir_parsed_output_jsons = r'/opt/unarXive_2022/parsed_data/'
output_dir_enriched_parsed_output = r'/opt/unarXive_2022/parsed_data_enriched/'
test_file = 'chunk_1.jsonl'

i = 0
bib_item_counter = 0
bib_item_no_title_error_counter = 0
crossref_title_tempstore = {}
saved_requests_counter = 0

for filename in glob.glob(os.path.join(input_dir_parsed_output_jsons, '*.jsonl')):
    with open((output_dir_enriched_parsed_output + filename.split("/")[-1]), "w", encoding="utf-8") as output_chunk:
        with open(filename, 'r', encoding='utf-8') as chunk:
            print("Reading file ", filename, "..")
            for publication in chunk:

                # this conditition makes the process stop after one hundred publications (for testing!)
                if i < 100:

                    print("####### ", i, " ###### ")
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
                                # print("starting metadata db request.. ")

                                title_from_arxive_meta_db = title_lookup_in_arxive_metadata_db(str(bib_entry_aid[0]))

                                if title_from_arxive_meta_db is not None:
                                    if len(title_from_arxive_meta_db) != 0:
                                        title = title_from_arxive_meta_db
                                        # print("title in arxive table db :", title)

                            except Exception as e:
                                print(e)
                                pass

                        # retrieve title from crossref (look for DOI in contained links)
                        if title is None:
                            if len(json_data['bib_entries'][bib_entry]['contained_links']) != 0:
                                # multiple urls possible in list
                                for bib_item_url in json_data['bib_entries'][bib_entry]['contained_links']:

                                    # print('Doi patt serach using URL link')
                                    bib_item_url = json_data['bib_entries'][bib_entry]['contained_links']
                                    for url in bib_item_url:
                                        bib_item_doi = DOI_PATT.search(url)
                                        # print(bib_item_doi)
                                        if bib_item_doi is not None:
                                            if len(bib_item_doi[0]) != 0:

                                                # check whether title string for this DOI is already in tempstore dict
                                                if bib_item_doi[0] in crossref_title_tempstore.keys():
                                                    title = crossref_title_tempstore[bib_item_doi[0]]
                                                    saved_requests_counter += 1
                                                    # print("crossref title found in tempstore:", title)

                                                # if title not retrieved yet, carry out crossref API call
                                                else:
                                                    crossref_api_result = find_title_in_crossref_by_doi(bib_item_doi[0])
                                                    if crossref_api_result is not False:
                                                        title = crossref_api_result
                                                        # print("crossref title found via web request :", title)
                                                        crossref_title_tempstore[bib_item_doi[0]] = title

                        # find title with GROBID in ref string
                        if title is None:
                            bib_item_ref_string = json_data['bib_entries'][bib_entry]['bib_entry_raw']

                            # curl grobid
                            output, err = find_title_with_grobid_in_string(bib_item_ref_string)

                            if output is not None:
                                grobid_returned_data_xml = BeautifulSoup(output, 'lxml')
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
                                # print("####")
                                ## to-do !!
                                # returns: [<title level="a" type="main">The axial vector current in beta decay</title>, <title level="j">Il Nuovo Cimento, Italian Physical Society</title>]

                        if title is None:
                            print("##############")
                            print("##### still no title for item! ", bib_item_ref_string, " ####### ")
                            print("#############")
                            bib_item_no_title_error_counter += 1

                        # title is found and now used to check (local) OpenAlex database
                        if title is not None:
                            bib_item_title_norm = normalize_title(title)
                            bib_item_ref_string = json_data['bib_entries'][bib_entry]['bib_entry_raw']
                            openalexdb_title_query = "SELECT * from openalex WHERE normalized_title=%s"

                            # look into openalex table, look for normalized item(s) with same title, do citation and author lookup
                            # use returned pub for additional info on work IDs

                            conn = psycopg2.connect(database="openalex")
                            matching_openalex_pub = match_title_in_openalexdb(openalexdb_title_query,
                                                                              bib_item_title_norm,
                                                                              bib_item_ref_string, conn, grobid_flag)

                            if matching_openalex_pub is None:
                                print('no match was returned')


                            elif matching_openalex_pub is not None:
                                print('MATCH was returned - writing IDs from OpenAlex DB to chunk')
                                bib_entry_ids_dict = map_ids_from_openalexdb_match_to_dict(matching_openalex_pub)


                                # add data from OpenAlex to JSON object of current publication
                                json_data['bib_entries'][bib_entry]['ids'] = {}
                                json_data['bib_entries'][bib_entry]['ids']['open_alex_id'] = bib_entry_ids_dict[
                                    'open_alex_id']
                                json_data['bib_entries'][bib_entry]['ids']['sem_open_alex_id'] = bib_entry_ids_dict[
                                    'sem_open_alex_id']
                                json_data['bib_entries'][bib_entry]['ids']['pubmed_id'] = bib_entry_ids_dict[
                                    'pubmed_id']
                                json_data['bib_entries'][bib_entry]['ids']['pmc_id'] = bib_entry_ids_dict['pmc_id']
                                json_data['bib_entries'][bib_entry]['ids']['doi'] = bib_entry_ids_dict['doi']  ###?

                                if len(json_data['bib_entries'][bib_entry]['contained_arXiv_ids']) != 0:
                                    json_data['bib_entries'][bib_entry]['ids']['arXiv_id'] = \
                                        json_data['bib_entries'][bib_entry]['contained_arXiv_ids'][0]

                        # recall wanted dict structure: id_keys_in_output = ['open_alex_id', 'sem_open_alex_id', 'pubmed_id', 'pmc_id', 'doi']

                        if bib_item_counter % 100 == 0:
                            print("Current success quota for title determination in bibitems:",
                                  bib_item_no_title_error_counter, "/", bib_item_counter, " | Success = {:.2f}".format(
                                    100 * ((bib_item_counter - bib_item_no_title_error_counter) / bib_item_counter)))

                    output_chunk.write(json.dumps(json_data))

                i += 1
                if i % 10 == 0:
                    print("###", i, "###")

            print("Chunk done. \nErrors in title determination in bibitems:", bib_item_no_title_error_counter, "/",
                  bib_item_counter)
            print("Success quota is = {:.2f}".format(
                100 * ((bib_item_counter - bib_item_no_title_error_counter) / bib_item_counter)))
            print(f"btw.. we saved {saved_requests_counter} due to the temporary Crossref title storage")
            chunk.close()
        output_chunk.close()

### next clean title
### use title for lookup in openalex db
### get ids from openalex
### integrate ids into existing dict and extend the data from the chunks (write new chunks though)
### re-use existing DOI or arxiv ids if already there.
### in addition pmc, pubmed id, OA id and SOA id

# command dump
# PS C:\Users\Johan\Documents\_Uni\Hiwi Tasks\LatexParse> scp openalex_linkage\extend_parsed_output_title_lookup.py udevz@aifb-ls3-icarus.aifb.kit.edu:/opt/unarXive_2022
