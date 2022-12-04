# this script reads data from OpenAlex dump files (works type) and it into a local DB
# imported are title, authors, citation counts and IDs


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

# check size of db
# psql openalex
# SELECT pg_size_pretty (pg_database_size ('openalex'));


#test the connection
conn = psycopg2.connect(database="openalex")
cursor = conn.cursor()
cursor.execute("select version()")

#Fetch a single row using fetchone() method.
data = cursor.fetchone()
print("Connection established to: ", data)


# remove previous instance of openalex table if existing

cursor = conn.cursor()
cursor.execute("DROP TABLE IF EXISTS openalex")
conn.commit()

#cursor.execute("DROP TABLE IF EXISTS openalex")

conn = psycopg2.connect(database="openalex")
cursor = conn.cursor()
cursor.execute('''
        CREATE TABLE openalex (
            number SERIAL PRIMARY KEY,
            normalized_title VARCHAR,
            authors VARCHAR[],
            citation_count INTEGER,
            ids VARCHAR[]
        )
''')
conn.commit()

print("Table created successfully.....")

# fill testwise
'''
json_raw = {'open_alex_id': 987, 'pmc_id': 123, 'pubmed_id': 555, 'doi': 'http://doiurl.com'}

s = ''
for v in json_raw.values():
    s += '"' + str(v) + '",'
s = "{" + str(s)[:-1] + "}"


a = '{"author1", "author2"}'
conn = psycopg2.connect(database="openalex")
cursor = conn.cursor()
print("inserting...")
cursor.execute("INSERT INTO openalex (number, normalized_title, authors, citation_count, ids) VALUES (%s,%s,%s,%s,%s)",
               (4, 'Titel', a, 75, s))

conn.commit()
conn.close()

conn = psycopg2.connect(database="openalex")
cursor = conn.cursor()
cursor.execute("SELECT * FROM openalex")
result = cursor.fetchone()
print(result)
conn.commit()
conn.close()
'''

i = 0
error_count = 0
file_count = 0
# recall openalexdb IDs column structure: list of IDs [oa_id, pubmedid, pmcid, doi]

# in db:
# (1, 'otello u shekspira na armianskoi stsene ai bem v monreale', ['anait bekarian'], 0, ['https://openalex.org/W4297237744', 'https://semopenalex.org/work/W4297237744', '', '', 'https://doi.org/10.54503/1829-4073-2022.2.118-129'])
# (3, 'premature primary tooth loss and oral health related quality of life in preschool children', ['monalisa cesarino gomes', 'matheus franca perazzo', 'ana flavia granville garcia'], 0, ['W4297237785', 'https://pubmed.ncbi.nlm.nih.gov/36231465', '', 'https://doi.org/10.3390/ijerph191912163'])

input_dir_openalex_works_files = r'/opt/unarXive_2022/openalex/openalex-works-2022-11-28/*'
print(f"Working in directory: {input_dir_openalex_works_files}")

for filename in glob.glob(os.path.join(input_dir_openalex_works_files, '*.gz')):
    print("Processing file..",filename)
    file_count += 1
    print(f"File {file_count} of",len(glob.glob(os.path.join(input_dir_openalex_works_files, '*.gz'))))

    with gzip.open(filename, 'r') as f:
        for line in f:
            try:
                i += 1
                json_data = json.loads(line.decode('utf-8'))

                # get data from current json line for current object

                work_title_orig = json_data['title']

                # normalize title
                if work_title_orig is not None:
                    # example orig title: Reversible Mechanochromic Luminescence of [(C6F5Au)2(μ-1,4-Diisocyanobenzene)]
                    # normalized title: reversible mechanochromic luminescence of c6f5au 2 m 1 4 diisocyanobenzene
                    work_title_norm = normalize_title(work_title_orig)

                else:
                    work_title_norm = ""

                work_authorships = json_data['authorships']
                work_author_list = []
                for author in work_authorships:
                    # normalize author name for every involved author
                    work_author_norm = normalize_author_name(author['author']['display_name']).replace("'","").replace('"','')
                    work_author_list.append(work_author_norm)

                # modify string so that it suits postgresql syntax to insert into table as a list of strings
                work_author_list_str = str(work_author_list).replace('[', '{').replace(']', '}').replace("'", '"')
                # example list str now:
                # {"engelbert knosp", "erich steiner", "klaus kitz", "christian matula"}

                work_cited_by_count = json_data['cited_by_count']

                ids = json_data.get('ids')
                # example ids list: {'openalex': 'https://openalex.org/W2169161843', 'doi': 'https://doi.org/10.1177/1362361312472989', 'pmid': 'https://pubmed.ncbi.nlm.nih.gov/23614935', 'mag': 2169161843}
                ids_list = []
                # wanted: openalex, semopenalex, pubmed, pmc, doi

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

                # adapt to postgresql syntax to insert into table as a list of strings
                ids_list = str(ids_list).replace('[', '{').replace(']', '}').replace("'", '"')

                # write data of current object to database table
                # write the values number, work_title_norm, work_author_list_str, work_cited_by_count, ids_list

                conn = psycopg2.connect(database="openalex")
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO openalex (number, normalized_title, authors, citation_count, ids) VALUES (%s,%s,%s,%s,%s)",
                    (i, work_title_norm, work_author_list_str, work_cited_by_count, ids_list))

                if i % 50000 == 0:
                    print(f"Inserting line {i} into table..")

                conn.commit()
                conn.close()

            except Exception as e:
                #print(f'{e} error in line {i} of file {filename}')
                #print('faulty data in:')
                #print(json_data['title'],json_data['authorships'] )
                # note: errors in most cases due to missing author name in OpenAlex data

                error_count += 1
                pass




print("------ DONE ------")
print(f"Processed {i} lines" )
print(f"Encountered {error_count} errors")
print("Success rate for reading and writing to postgresql db therefore: {:.2f}".format(100*((i-error_count)/i)))
print("#########")
