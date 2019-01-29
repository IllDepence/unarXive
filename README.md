# unarXive

Code for generating a data set for citation based tasks using arXiv.org submissions.

### Prerequisites
* software
    * Tralics (Ubuntu: `# apt install tralics`)
    * latexpand (Ubuntu: `# apt install texlive-extra-utils`)
    * [Neural ParsCit](https://github.com/WING-NUS/Neural-ParsCit)
* data
    * arXiv source files: see [arXiv.org help - arXiv Bulk Data Access](https://arxiv.org/help/bulk_data)
    * MAG DB: **#TODO** add link/section describing MAG data base
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
3. (optional) Clean txt output with: `clean_txt_output.py`
4. (optional) Adjust parameters in `extract_contexts.py` at `def generate(...)`
5. (optional) Extract citation contexts with: `extract_contexts.py`

##### Example
* `$ source venv/bin/activate`
* `$ python3 prepare.py /tmp/arxiv-sources /tmp/arxiv-txt`
* `$ python3 match_bibitems_mag.py path /tmp/arxiv-txt 10`
* `$ python3 clean_txt_output.py /tmp/arxiv-txt`
* `$ python3 extract_contexts.py /tmp/arxiv-txt`

### Matching evaluation
For a manual evaluation of the reference resolution (`match_bibitems_mag.py`) we performed on a sample of 300 matchings, see `doc/matching_evaluation/`.
