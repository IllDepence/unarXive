""" From an arXiv metadata snapshot as provided by
        https://www.kaggle.com/Cornell-University/arxiv
    generate an SQLite database with indices for performant access.
"""

import json
import os
import re
import sqlite3
import sys
from tqdm import tqdm


def gen_meta_db(in_fp):
    # input prep
    in_path, in_fn = os.path.split(in_fp)
    in_fn_base, ext = os.path.splitext(in_fn)

    # output prep
    out_fp = os.path.join(in_path, '{}.sqlite'.format(in_fn_base))
    conn = sqlite3.connect(out_fp)
    db_cur = conn.cursor()
    db_cur.execute("""
        create table paper(
            'year' integer,
            'month' integer,
            'aid' text,
            'title' text,
            'json' text
        )
    """)

    aid_patt = re.compile(r'^(.*\/)?(\d\d)(\d\d).*$')

    num_lines = sum(1 for i in open(in_fp, 'rb'))
    print('filling table')
    with open(in_fp) as f:
        for line in tqdm(f, total=num_lines):
            ppr_meta = json.loads(line.strip())
            aid_m = aid_patt.match(ppr_meta['id'])
            assert aid_m is not None
            aid = aid_m.group(0)
            y = int(aid_m.group(2))
            m = int(aid_m.group(3))
            title = ppr_meta['title']
            db_cur.execute(
                (
                    "insert into paper "
                    "('year','month','aid','title','json')"
                    "values(?,?,?,?,?)"
                ),
                (y, m, aid, title, line.strip())
            )
    print('generating index')
    db_cur.execute(
          "create index ym  on paper('year', 'month')"
      )
    conn.commit()


if __name__ == '__main__':
    gen_meta_db(sys.argv[1])
