# unarXive

This repository contains
* [Helpful information for using the unarXive data set](#usage)
* [Instructions on how to (re)create the data set](#recreating-unarxive)
* [Citation information](cita-as)

Further links
* [Article in *Scientometrics*](http://link.springer.com/article/10.1007/s11192-020-03382-z)
* [Data Set on Zenodo](https://doi.org/10.5281/zenodo.2553522)

## Usage

The unarXive data set contains
* full text papers in plain text (`papers/`)
* a database with bibliographic interlinkings (`papers/refs.db`)
* pre-extracted citation-contexts (`contexts/extracted_contexts.csv`) (see [README_contexts.md](README_contexts.md))
* and a script for extracting citation-contexts (`code/extract_contexts.py`)

![](https://github.com/IllDepence/unarXive/raw/master/doc/structure.png)

### Data Sample
You can find a small sample of the data set in [doc/unarXive_sample.tar.bz2](https://github.com/IllDepence/unarXive/blob/master/doc/unarXive_sample.tar.bz2). (Generation procedure of the sample is documented in `unarXive_sample/paper_centered_sample/README` within the archive. Furthermore, the code used for sampling is provided.)

### Usage examples

##### Citation contexts

Load the pre-exported citation contexts into a pandas data frame.

```
import csv
import sys
import pandas as pd

# read in unarXive citation contexts
csv.field_size_limit(sys.maxsize)
df_contexts = pd.read_csv(
    'contexts/extracted_contexts.csv',
    names = [
        'cited_mag_id',
        'adjacent_citations_mag_ids',
        'citig_mid',
        'cited_arxiv_id',
        'adjacent_citations_arxiv_ids',
        'citig_arxiv_id',
        'citation_context'
        ],
    sep = '\u241E',
    engine = 'python',
    quoting = csv.QUOTE_NONE
)
# adjacent_*_ids values are seperated by \u241F

df_contexts
```

##### References database

Get the citation counts of the most cited computer science papers.

```
$ sqlite3 refs.db
sqlite> select
            bibitem.cited_arxiv_id,
            count(distinct bibitem.citing_mag_id)
        from
            bibitem
        join
            arxivmetadata
        on
            bibitem.cited_arxiv_id = arxivmetadata.arxiv_id
        where
            arxivmetadata.discipline = 'cs'
        group by
            bibitem.cited_arxiv_id
        order by
            count(distinct bibitem.citing_mag_id)
        desc;
```

##### Paper full texts

Extract citation contexts including identifiers of the citing and cited document.

See `code/extract_contexts.py` in the data set.

## (re)creating unarXive
Generating a data set for citation based tasks using arxiv.org submissions.

### Prerequisites
* software
    * Tralics (Ubuntu: `# apt install tralics`)
    * latexpand (Ubuntu: `# apt install texlive-extra-utils`)
    * [Neural ParsCit](https://github.com/WING-NUS/Neural-ParsCit)
* data
    * arXiv source files: see [arXiv.org help - arXiv Bulk Data Access](https://arxiv.org/help/bulk_data)
    * [MAG](https://www.microsoft.com/en-us/research/project/microsoft-academic-graph/) DB: see file `doc/MAG_DB_schema`
    * arXiv title lookup DB: see file `aid_title.db.placeholder`

### Setup
* create virtual environment: `$ python3 -m venv venv`
* activate virtual environment: `$ source venv/bin/activate`
* install requirements: `$ pip install -r requirements.txt`
* in `match_bibitems_mag.py`
    * adjust line `mag_db_uri = 'postgresql+psycopg2://XXX:YYY@localhost:5432/MAG'`
    * adjust line `doi_headers = { [...] working on XXX; mailto: XXX [...] }`
    * depending on your arXiv title lookup DB, adjust line `aid_db_uri = 'sqlite:///aid_title.db'`
* run Neural ParsCit web server ([instructions](https://github.com/WING-NUS/Neural-ParsCit#using-a-web-server))


### Usage
1. Extract plain texts and reference items with: `prepare.py` (or `normalize_arxiv_dump.py` + `prase_latex_tralics.py`)
2. Match reference items with: `match_bibitems_mag.py`
3. Clean txt output with: `clean_txt_output.py`
4. Extend ID mappings
    * Create mapping file with: `mag_id_2_arxiv_url_extend_arxiv_id.py` (see note in docstring)
    * Extend IDs with `id_extend.py`
5. Extract citation contexts with: `extract_contexts.py` (see `$ extract_contexts.py -h` for usage details)

##### Example
```
$ source venv/bin/activate
$ python3 prepare.py /tmp/arxiv-sources /tmp/arxiv-txt
$ python3 match_bibitems_mag.py path /tmp/arxiv-txt 10
$ python3 clean_txt_output.py /tmp/arxiv-txt
$ psql MAG
MAG=> \copy (select * from paperurls where sourceurl like '%arxiv.org%') to 'mag_id_2_arxiv_url.csv' with csv
$ python3 mag_id_2_arxiv_url_extend_arxiv_id.py
$ python3 id_extend.py /tmp/arxiv-txt/refs.db
$ python3 extract_contexts.py /tmp/arxiv-txt \
    --output_file context_sample.csv \
    --sample_size 100 \
    --context_margin_unit s \
    --context_margin_pre 2 \
    --context_margin_pre 0
```


### Evaluation of citation quality and coverage
* For a manual evaluation of the reference resolution (`match_bibitems_mag.py`) we performed on a sample of 300 matchings, see `doc/matching_evaluation/`.
* For a manual evaluation of citation coverage (compared to the MAG) we performed on a sample of 300 citations, see `doc/coverage_evaluation/`.

## Cite as
```
@article{Saier2020unarXive,
  author        = {Saier, Tarek and F{\"{a}}rber, Michael},
  title         = {{unarXive: A Large Scholarly Data Set with Publications’ Full-Text, Annotated In-Text Citations, and Links to Metadata}},
  journal       = {Scientometrics},
  year          = {2020},
  volume        = {125},
  number        = {3},
  pages         = {3085--3108},
  month         = dec,
  issn          = {1588-2861},
  doi           = {10.1007/s11192-020-03382-z}
}
```
