### (re)creating unarXive

The code in the `src/` directory can be used to re-create or update unarXive.

##### Prerequisites

* software
    * Tralics (Ubuntu: `# apt install tralics`)
    * latexpand (Ubuntu: `# apt install texlive-extra-utils`)
    * [GROBID](https://github.com/kermitt2/grobid)
* data
    * arXiv source files: see [arXiv.org help - arXiv Bulk Data Access](https://arxiv.org/help/bulk_data)
    * [OpenAlex](https://openalex.org/) (works records only)

##### Usage

1. Prepare arXiv metadata with: `utility_scripts/generate_metadata_db.py`
2. Prepare OpenAlex DB with: `utility_scripts/generate_openalex_db.py`
3. Parse arXiv sources with: `prepare.py` (or `normalize_arxiv_dump.py` + `prase_latex_tralics.py`)
4. Match reference items with: `match_references_openalex.py`
5. Extend matched data with: `extend_matched.py` (adds arXiv IDs to matched references and discipline information)
5. Verify and analyze result with: `utility_scripts/calc_stats.py`
