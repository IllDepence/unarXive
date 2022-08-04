## usage

### Prerequisites
* software
    * Tralics (Ubuntu: `# apt install tralics`)
    * latexpand (Ubuntu: `# apt install texlive-extra-utils`)
* data
    * arXiv source files (acquire sample [here](https://bwsyncandshare.kit.edu/s/Yp9tE6YgitpXfQ8), needs to be extracted before use)

### Usage
* setup virtual environment with packages in requirements.txt
* run `normalize_arxiv_dump.py` on raw source files
* run `prase_latex_tralics.py` on normalized LaTeX files

### Testruns
```
(venv) ys8950@aifb-ls3-icarus:/opt/unarXive/unarXive_update_2022/hiwi_task_220629_latexparse$ time python3 prepare.py /mnt/lsdf_clasics/data/arxiv-2022-wip/copied_src_files/ /opt/unarXive/unarXive_update_2022/unarXive_2022_wip_2018data_parsed/
1/392
[...]
392/392
140616 files
13430 PDFs

real    504m4,681s
user    373m41,079s
sys     59m28,106s
```


##### 2017 data
```
(venv) ys8950@aifb-ls3-icarus:/opt/unarXive/unarXive_update_2022/hiwi_task_220629_latexparse$ time python3 prepare.py /mnt/lsdf_clasics/data/arxiv-2022-wip/copied_src_files/ /opt/unarXive/unarXive_update_2022/unarXive_2022_wip_2017data_parsed/
1/305
[...]
305/305
123523 files
11202 PDFs

real    640m38,377s
user    519m0,535s
sys     74m5,791s
```

### TODOs
* investigate low rate of table and figure captions

### Misc
for a formula tag `t`, testing whether its string representation returned by
```
etree.tostring(
    etree.ETXPath(
        '{http://www.w3.org/1998/Math/MathML}math'
    )(t)[0],
    encoding='unicode',
    method='text',
    with_tail=False
)
```
contains a space (“ ”) apppears to be a usable heuristic to decide whether or not it can safely be printed as a unicode string w/o loosing any information (e.g. super/subscript)

### Troubleshooting
If the creation of the virtual enviroment fails try [this](https://stackoverflow.com/questions/5178416/libxml-install-error-using-pip)
or [this](https://stackoverflow.com/questions/22938679/error-trying-to-install-postgres-for-python-psycopg2)
