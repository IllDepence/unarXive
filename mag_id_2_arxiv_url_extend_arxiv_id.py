""" Take paperurls data from MAG exported as
    \copy (select * from paperurls where sourceurl like '%arxiv.org%') to '/tmp/mag_id_2_arxiv_url.csv' with csv
    and add a column containing clean arXiv IDs

    ID notes:
        arXiv               MAG url
        cs0110036           https://arxiv.org/abs/cs/0110036
        hep-lat0110155      https://arxiv.org/abs/hep-lat/0110155
        quant-ph0108117     https://arxiv.org/pdf/quant-ph/0108117v2
        1412.0979           https://arxiv.org/pdf/1412.0979
                            https://www.arxiv.org/abs/1310.4075
                            http://export.arxiv.org/pdf/hep-lat/0310020
                            https://arxiv.org/abs/1405.4421?context=q-fin
                            http://arxiv.org/pdf/cond-mat/0303112.pdf
                            https://aps.arxiv.org/abs/1901.06826
                            https://za.arxiv.org/abs/1407.5025
                            https://au.arxiv.org/abs/1609.01107
                            https://xxx.arxiv.org/abs/1312.1581
        nucl-ex0512021      http://arxiv.org/PS_cache/nucl-ex/pdf/0512/0512021v1.pdf
        0908.2534           http://arxiv.org/PS_cache/arxiv/pdf/0908/0908.2534v2.pdf
                            ...

"""

import re
import sys

patt_ps_cache_new_id = re.compile('arxiv.org\/PS_cache\/arxiv\/pdf\/(.+?)(v\d+)?\.pdf', re.I)
patt_ps_cache_old_id = re.compile('arxiv.org\/PS_cache\/([a-z-]+)\/pdf\/(.+?)(v\d+)?\.pdf', re.I)
patt_ext = re.compile('arxiv.org\/[a-z]+\/(.+)((.pdf)|(\?.*$)|(v\d+))', re.I)
patt_norm = re.compile('arxiv.org\/[a-z]+\/(.+)$', re.I)

with open('mag_id_2_arxiv_url.csv') as fi:
    with open('mag_id_2_arxiv_id.csv', 'w') as fo:
        for line in fi:
            if '0909.5384v1' in line:
                # https://infoscience.epfl.ch/record/184000/files/arxiv.org-pdf-0909.5384v1.pdf
                line = '1483108286,3,https://arxiv.org/abs/0909.5384v1'
            if 'crm.sns.it/media/publication/225/arxiv.org_abs_1112.0531' in line:
                # http://www.crm.sns.it/media/publication/225/arxiv.org_abs_1112.0531.pdf
                continue
            if 'carroll s. lectures on general relativity' in line:
                # http://inis.jinr.ru/sl/p_physics/pgr_gravitation/carroll%20s.%20lectures%20on%20
                # general%20relativity%20(arxiv.org,%201997)(238s).pdf
                continue
            if 'duke.edu/~lcarin' in line:
                # http://people.ee.duke.edu/~lcarin/arxiv.org.pdf_1112.pdf
                continue
            if 'crm.sns.it/media/publication/227/arxiv.org_pdf_1210.1353' in line:
                # http://crm.sns.it/media/publication/227/arxiv.org_pdf_1210.1353.pdf
                continue
            if 'crm.sns.it/media/publication/226/arxiv.org_pdf_1208.0147' in line:
                # http://www.crm.sns.it/media/publication/226/arxiv.org_pdf_1208.0147.pdf
                continue
            if 'r.p.stevenson/papers/arxiv.org_pdf_1503.03996v1' in line:
                # https://staff.fnwi.uva.nl/r.p.stevenson/papers/arxiv.org_pdf_1503.03996v1.pdf
                continue
            if '~wmg/arxiv.org_pdf_1204.5308v2.pdf' in line:
                # http://www.math.umd.edu/~wmg/arxiv.org_pdf_1204.5308v2.pdf
                continue
            if '~wmg//arxiv.org_pdf_1204.5308v2.pdf' in line:
                # http://www2.math.umd.edu/~wmg//arxiv.org_pdf_1204.5308v2.pdf
                continue
            if 'ecommons.cornell.edu/bitstream/1813/3478/1/ArXiv.org.ppt' in line:
                # http://ecommons.cornell.edu/bitstream/1813/3478/1/ArXiv.org.ppt
                continue
            if 'eprints.usq.edu.au/24507/1/bcool-iaus302-arxiv.org-1310.6507v1.pdf' in line:
                # http://eprints.usq.edu.au/24507/1/bcool-iaus302-arxiv.org-1310.6507v1.pdf
                continue
            if 'eartharxiv.org/' in line:
                # http://eartharxiv.org/e4gt7/
                # https://eartharxiv.org/8a93m/
                continue
            if 'marxiv.org/' in line:
                # https://marxiv.org/dx2hy/
                continue
            if '2766616821,0,arxiv.org' in line:
                continue
            m = patt_ext.search(line.strip())
            if not m:
                m = patt_norm.search(line.strip())
            if not m:
                m = patt_ps_cache_new_id.search(line.strip())
            if m:
                arxiv_id = m.group(1)
                arxiv_id = arxiv_id.replace('/', '')
                fo.write('{},{}\n'.format(line.strip(), arxiv_id))
            else:
                m2 = patt_ps_cache_old_id.search(line.strip())
                if not m2:
                    print('Problem with line: "{}"'.format(line))
                    sys.exit()
                arxiv_id = '{}{}'.format(m2.group(1), m2.group(2))
                arxiv_id = arxiv_id.replace('/', '')
                fo.write('{},{}\n'.format(line.strip(), arxiv_id))
