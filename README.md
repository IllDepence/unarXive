# unarXive

Code for generating a data set for citation based tasks using arXiv.org submissions. ([data set on Zenodo](https://doi.org/10.5281/zenodo.2609187))

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
    * Run `$ jupyter notebook` and follow instructions in `unarXive_DB_ID_extend.ipynb`
5. Extract citation contexts with: `extract_contexts.py` (see `$ extract_contexts.py -h` for usage details)

##### Example
```
$ source venv/bin/activate
$ python3 prepare.py /tmp/arxiv-sources /tmp/arxiv-txt
$ python3 match_bibitems_mag.py path /tmp/arxiv-txt 10
$ python3 clean_txt_output.py /tmp/arxiv-txt
$ psql MAG
MAG=> \copy (select * from paperurls where sourceurl like '%arxiv.org%') to 'mag_id_2_arxiv_url.csv' with csv
$ mag_id_2_arxiv_url_extend_arxiv_id.py
$ jupyter notebook
(go through steps in notebook)
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

### Cite as

```
@inproceedings{Saier2019BIR,
  author        = {Tarek Saier and
                   Michael F{\"{a}}rber},
  title         = {{Bibliometric-Enhanced arXiv: A Data Set for Paper-Based and
                   Citation-Based Tasks}},
  booktitle     = {Proceedings of the 8th International Workshop on
                   Bibliometric-enhanced Information Retrieval (BIR) co-located
                   with the 41st European Conference on Information Retrieval
                   (ECIR 2019)},
  pages         = {14--26},
  year          = {2019},
  month         = apr,
  location      = {Cologne, Germany},
  url           = {http://ceur-ws.org/Vol-2345/paper2.pdf}
}
```
