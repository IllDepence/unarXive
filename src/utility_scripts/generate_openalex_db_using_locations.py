""" this script reads data from OpenAlex dump files (works type) and imports it into a local DB
    extracted are title, authors, citation counts, discipline info, open access URLs and IDs
    this version is adapted to fit the new OpenAlex structure including "locations" entities
"""

import psycopg2
from psycopg2.extras import Json, DictCursor
import json
import os
import glob
import gzip
import re
import unidecode
import unicodedata


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


PATT_PS_CACHE_NEW_ID = re.compile('arxiv.org\/PS_cache\/arxiv\/pdf\/(.+?)(v\d+)?\.pdf', re.I)
PATT_PS_CACHE_OLD_ID = re.compile('arxiv.org\/PS_cache\/([a-z-]+)\/pdf\/(.+?)(v\d+)?\.pdf', re.I)
PATT_EXT = re.compile('arxiv.org\/[a-z]+\/(.+)((.pdf)|(\?.*$)|(v\d+))', re.I)
PATT_NORM = re.compile('arxiv.org\/[a-z]+\/(.+)$', re.I)
PATT_DOI = re.compile(r'10.\d{4,9}/[-._;()/:A-Z0-9]+$', re.I)


# method for extracting arxive IDs from url
def extract_arxiv_id_from_url(url):
    arxiv_id = ""
    success_flag = False
    aid_group = PATT_EXT.search(url)
    if not aid_group:
        aid_group = PATT_NORM.search(url)
    if not aid_group:
        aid_group = PATT_PS_CACHE_NEW_ID.search(url)
    if aid_group:
        arxiv_id = aid_group.group(1)
    else:
        aid_group2 = PATT_PS_CACHE_OLD_ID.search(url)
        if not aid_group2:
            print("Problem in: ", url)
        arxiv_id = '{}{}'.format(aid_group2.group(1), aid_group2.group(2))
    if len(arxiv_id) != 0:
        success_flag = True
    return success_flag, arxiv_id


conn = psycopg2.connect(database="openalex")
cursor = conn.cursor()
cursor.execute('''
        CREATE TABLE papers (
            number SERIAL PRIMARY KEY,
            openalex_id VARCHAR,
            normalized_title VARCHAR,
            authors VARCHAR[],
            discipline_name VARCHAR,
            discipline_url VARCHAR,
            citation_count INTEGER,
            ids VARCHAR[],
            doi VARCHAR,
            oa_url VARCHAR,
            arxiv_id VARCHAR
        )
''')
conn.commit()

print("Table created successfully.")

i = 0
error_count = 0
file_count = 0

input_dir_openalex_works_files = r'/opt/unarXive_2022/openalex/openalex-works-2022-11-28/*'
print(f"Working in directory: {input_dir_openalex_works_files}")

for filename in glob.glob(os.path.join(input_dir_openalex_works_files, '*.gz')):
    file_count += 1
    print(f"File {file_count} of", len(glob.glob(os.path.join(input_dir_openalex_works_files, '*.gz'))))

    with gzip.open(filename, 'r') as f:
        for line in f:

            try:
                i += 1
                json_data = json.loads(line.decode('utf-8'))

                work_title_orig = json_data['title']

                # normalize title
                if work_title_orig is not None:
                    work_title_norm = normalize_title(work_title_orig)

                else:
                    work_title_norm = ""

                work_authorships = json_data['authorships']
                work_author_list = []
                for author in work_authorships:
                    work_author_norm = normalize_author_name(author['author']['display_name']).replace("'",
                                                                                                       "").replace(
                        '"', '')
                    work_author_list.append(work_author_norm)

                work_author_list_str = str(work_author_list).replace('[', '{').replace(']', '}').replace("'", '"')

                work_cited_by_count = json_data['cited_by_count']

                ids = json_data.get('ids')
                ids_list = []

                if not ids['openalex'] is None:
                    ids_list.append(ids['openalex'].replace("https://openalex.org/", ""))
                else:
                    ids_list.append("")
                    ids_list.append("")

                pmid = json_data.get('ids').get('pmid')
                if not pmid is None:
                    ids_list.append(pmid)
                else:
                    ids_list.append("")

                pmc_id = json_data.get('ids').get('pmcid')
                if not pmc_id is None:
                    ids_list.append(pmc_id)
                else:
                    ids_list.append("")

                doi = json_data['doi']
                if not doi is None:
                    ids_list.append(doi)
                else:
                    ids_list.append("")

                ids_list = str(ids_list).replace('[', '{').replace(']', '}').replace("'", '"')

                openalex_id = ids['openalex'].replace("https://openalex.org/", "")

                # DOI value (not URL)
                if not doi is None:
                    doi_short = PATT_DOI.search(doi)
                    if doi_short is not None:
                        if len(doi_short[0]) != 0:
                            doi_short = doi_short[0]
                            # print(doi_short[0])
                    else:
                        doi_short = ""

                # Most weighted level-0 Concept: display name and wikidata URL
                concept_list = json_data['concepts']
                if concept_list is not None:
                    concept_name = None
                    for concept_item in concept_list:
                        if concept_name is None:
                            if concept_item['level'] == 0:
                                concept_name = concept_item['display_name']
                                concept_url = concept_item['wikidata']
                                # print(concept_name, concept_url)
                                # hardcore re-naming to capitalize concepts
                                if concept_name == "Political science":
                                    concept_name = "Political Science"
                                if concept_name == "Computer science":
                                    concept_name = "Computer Science"
                                if concept_name == "Materials science":
                                    concept_name = "Materials Science"
                                if concept_name == "Environmental science":
                                    concept_name = "Environmental Science"

                    if concept_name is None:
                        concept_name = ""
                        concept_url = ""

                oa_locations = json_data['locations']
                urls = []
                arxiv_url = ""

                if oa_locations is not None:
                    if len(oa_locations) != 0:
                        for location in oa_locations:
                            landing_page_url = location['landing_page_url']
                            if landing_page_url is not None:
                                if len(landing_page_url) != 0:
                                    urls.append(landing_page_url)
                                    if "/arxiv" in landing_page_url:  # optional check?!
                                        success, arxiv_id = extract_arxiv_id_from_url(landing_page_url)
                                        if success:
                                            arxiv_url = landing_page_url
                            pdf_url = location['pdf_url']
                            if pdf_url is not None:
                                if len(pdf_url) != 0:
                                    urls.append(pdf_url)
                                    if "/arxiv" in pdf_url:  # optional check?!
                                        success, arxiv_id = extract_arxiv_id_from_url(pdf_url)
                                        if success:
                                            arxiv_url = pdf_url

                        # remove duplicates from list
                        urls = list(set(urls))

                conn = psycopg2.connect(database="openalex")
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO papers (number, openalex_id, normalized_title, authors, discipline_name, discipline_url, citation_count, ids, doi, oa_url, arxiv_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (i, openalex_id, work_title_norm, work_author_list_str, concept_name, concept_url,
                     work_cited_by_count, ids_list, doi_short, arxiv_url, arxiv_id))

                conn.commit()
                conn.close()

            except Exception as e:
                print(f'{e} error in line {i} of file {filename}')
                error_count += 1
                pass

            if i % 1000000 == 0:
                print(f"Processed line #{i}")

print("------ DONE ------")
print(f"Processed {i} lines")
print(f"Encountered {error_count} errors")
print("Success rate for reading and writing to postgresql db therefore: {:.2f}".format(100 * ((i - error_count) / i)))
print("#########")
