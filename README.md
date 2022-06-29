## usage

### Prerequisites
* software
    * Tralics (Ubuntu: `# apt install tralics`)
    * latexpand (Ubuntu: `# apt install texlive-extra-utils`)
* data
    * arXiv source files (acquire sample [here](https://bwsyncandshare.kit.edu/s/Yp9tE6YgitpXfQ8))

### Usage
* setup virtual environment with packages in requirements.txt
* run `normalize_arxiv_dump.py` on raw source files
* run `prase_latex_tralics.py` on normalized LaTeX files

### TODOs
1. replace SQLite output with one CSV per DB table
2. replace JSONL output with CSV (write these CSVs into the output directory, not the CWD)
3. any code cleanup on the way is appreciated
