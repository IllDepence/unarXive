""" Extend unarXive DB

    - add MAG IDs to citing docs
    - add arXiv IDs to cited docs
    - merge bibitemmagidmap data into bibitem table
"""

import csv
import datetime
import sys
from sqlalchemy import create_engine

if len(sys.argv) != 2:
    print('Usage: python3 id_extend.py path/to/refs.db')
    sys.exit()
db_path = sys.argv[1]

print('loading CSV data')
mid_aid_map = {}
aid_mid_map = {}

with open('mag_id_2_arxiv_id.csv') as f:
    csv_reader = csv.reader(f, delimiter=',')
    for row in csv_reader:
        mid = row[0]
        aid = row[3]
        mid_aid_map[mid] = aid
        aid_mid_map[aid] = mid

print('merging tables')
db_uri = 'sqlite:///{}'.format(db_path)
db_engine = create_engine(db_uri)

db_engine.execute('alter table bibitem rename to bibitemOld;')

db_engine.execute('''CREATE TABLE bibitem (
	uuid VARCHAR(36) NOT NULL,
	citing_mag_id VARCHAR(36),
	cited_mag_id VARCHAR(36),
	citing_arxiv_id VARCHAR(36),
	cited_arxiv_id VARCHAR(36),
	bibitem_string TEXT,
	PRIMARY KEY (uuid)
);''')

db_engine.execute('''INSERT INTO bibitem
    (uuid, cited_mag_id, citing_arxiv_id, bibitem_string)
    SELECT bibitemOld.uuid, mag_id, in_doc, bibitem_string
    FROM bibitemOld
    LEFT JOIN bibitemmagidmap
    ON bibitemOld.uuid = bibitemmagidmap.uuid;''')

print('builing indices')
db_engine.execute(
    'CREATE INDEX bibitem_citing_aid_idx ON bibitem (citing_arxiv_id);'
    );
print('index 1 built')
db_engine.execute(
    'CREATE INDEX bibitem_cited_mid_idx ON bibitem (cited_mag_id);'
    );
print('index 2 built')

print('extending IDs')
i = 0
count_all = len(mid_aid_map)
for mid, aid in mid_aid_map.items():
    if i%100000 == 0:
        print('{}: {}/{}  ({:.2f})'.format(
            datetime.datetime.now(), i, count_all, i/count_all
            ))
    db_engine.execute(('UPDATE bibitem SET citing_mag_id = "{}"'
        ' where citing_arxiv_id = "{}";').format(mid, aid))
    db_engine.execute(('UPDATE bibitem SET cited_arxiv_id = "{}"'
        ' where cited_mag_id = "{}";').format(aid, mid))
    i += 1

print('cleaning up')
db_engine.execute('DROP TABLE bibitemOld;')
db_engine.execute('DROP TABLE bibitemmagidmap;')
db_engine.execute('DROP INDEX bibitem_citing_aid_idx;')
db_engine.execute('DROP INDEX bibitem_cited_mid_idx;')
print('done')
