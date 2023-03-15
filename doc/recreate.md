### (re)creating unarXive

The following hows how the code in `src/` can be used to re-create or update unarXive.

##### Prerequisites

* software
    * Tralics (Ubuntu: `# apt install tralics`)
    * latexpand (Ubuntu: `# apt install texlive-extra-utils`)
    * [GROBID](https://github.com/kermitt2/grobid)
* data
    * arXiv source files: see [arXiv.org help - arXiv Bulk Data Access](https://arxiv.org/help/bulk_data)
    * [OpenAlex](https://openalex.org/) (paper records only)

##### Usage

1. Prepare arXiv metadata with: `utility_scripts/generate_metadata_db.py`
2. Prepare OpenAlex DB with: `fill_openalex_postgresql_db.py`
3. Parse arXiv sources with: `prepare.py` (or `normalize_arxiv_dump.py` + `prase_latex_tralics.py`)
4. Match reference items with: `match_references.py`
5. Verify and analyze result with: `utility_scripts/calc_stats.py`
