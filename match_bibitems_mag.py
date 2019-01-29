""" Match bibitem strings to MAG IDs
"""

import datetime
import json
import os
import re
import requests
import sys
import time
import unidecode
from operator import itemgetter
from multiprocessing import Pool
from sqlalchemy import (create_engine, Column, Integer, String, UnicodeText,
                        Table, func)
from sqlalchemy.sql import text as sqltext
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError
from sqlalchemy.ext.declarative import declarative_base
from db_model import (Base, Bibitem, BibitemArxivIDMap, BibitemMAGIDMap,
                      BibitemLinkMap)

DOI_PATT = re.compile(
    r'10.\d{4,9}/[-._;()/:A-Z0-9]+$', re.I)
ARXIV_URL_PATT = re.compile(
    r'arxiv\.org\/[a-z0-9-]{1,10}\/(([a-z0-9-]{1,15}\/)?[\d\.]{4,9}\d)', re.I)
ARXIV_ID_PATT = re.compile(
    r'arXiv:(([a-z0-9-]{1,15}\/)?[\d\.]{4,9}\d)', re.I)


def parscit_parse(text):
    """ Parse bibitem text using Neural-ParsCit docker container.
    """

    url = 'http://localhost:8000/parscit/parse'
    try:
        ret = requests.post(url, json={'string':text}, timeout=360)
    except requests.RequestException:
        return False, False, False
    if ret.status_code != 200:
        return False, False, False
    response = json.loads(ret.text)
    parsed_terms = response['data']
    title_terms = []
    journal_terms = []
    for parsed_term in parsed_terms:
        if parsed_term['entity'] == 'title':
            title_terms.append(parsed_term['term'])
        elif parsed_term['entity'] == 'journal':
            journal_terms.append(parsed_term['term'])
    if len(title_terms) == 0:
        title = False
    else:
        title = ' '.join(title_terms)
    if len(journal_terms) == 0:
        journal = False
    else:
        journal = ' '.join(journal_terms)
    return title, journal, parsed_terms


def clean(s):
    """ Generic string cleaning
    """

    s = re.sub('[^\w\s]+', '', s)
    s = re.sub('\s+', ' ', s)
    return s.strip().lower()


def mag_normalize(s):
    """ Normalize a string the same way paper titles are normalized in the MAG.

        - replace everything that is not a \w word character (letters, numbers
          and _, strangely) with a space
        - turn modified alphabet characters like Umlauts or accented characters
          into their "origin" (e.g. ä→a or ó→o)
        - replace multiple spaces with single ones
    """

    s = re.sub('[^\w]', ' ', s)
    s = re.sub('\s+', ' ', s)
    s = unidecode.unidecode(s)
    return s.strip().lower()


def title_by_doi(given_doi):
    """ Given a DOI, try to get a work's title using crossref.org
    """

    doi_base_url = 'https://data.crossref.org/'
    doi_headers = {'Accept': 'application/citeproc+json',
                   'User-Agent': ('DoiToTitleScript (working on XXXXXXXXXXXXXX'
                                  'X; mailto:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'
                                  'X)')}
    try:
        resp = requests.get(
                '{}{}'.format(doi_base_url, given_doi),
                headers=doi_headers,
                timeout=360
                )
        rate_lim_lim = resp.headers.get('X-Rate-Limit-Limit', '9001')
        rate_lim_int = resp.headers.get(
            'X-Rate-Limit-Interval', '1s'
            ).replace('s', '')
    except requests.RequestException:
        return False
    try:
        wait = float(rate_lim_int)/float(rate_lim_lim)
        if resp.elapsed.total_seconds() < wait:
            delta = wait - resp.elapsed.total_seconds()
            delta = max(delta, 3600)
            time.sleep(delta)
    except ValueError:
        pass
    try:
        doi_metadata = json.loads(resp.text)
        title = doi_metadata.get('title', False)
        if title and len(title) > 0:
            return title
    except json.decoder.JSONDecodeError:
        return False


def guess_aps_journal_paper_doi(parscit_terms):
    """ American Physical Society Journals have predictable DOIs

        E.g.: Phys. Rev. B 84, 245128
           -> 10.1103/physrevb.84.245128

        Aggressive removal of dates in brackets b/c of cases like
            Phys. Rev. Lett. 73 (1994) 3070
        there preventing an incorrect guess 10.1103/physrevlett.73.1994
        instead of the correct 10.1103/physrevlett.73.3070
    """

    normalized_terms = []
    for term in parscit_terms:
        nodates = re.sub(r'\((19[0-9][0-9]|20[01][0-9])\)', ' ', term['term'])
        clean = re.sub(r'[^\w]', ' ', nodates)
        cleaner = re.sub('\s+', ' ', clean)
        parts = [p.lower() for p in cleaner.split() if len(p) > 0]
        normalized_terms.extend(parts)
    normalized_text_orig = ' '.join(normalized_terms)
    # heuristic to guess DOI of APS journal papers
    if ' phys rev ' in normalized_text_orig or \
       ' rev mod phys ' in normalized_text_orig:
        if ' phys rev ' in normalized_text_orig:
            doi_start_idx = normalized_terms.index('phys')
            journal_terms = normalized_terms[doi_start_idx:doi_start_idx+3]
            try:
                vol = normalized_terms[doi_start_idx+3]
                aps_id = normalized_terms[doi_start_idx+4]
            except IndexError:
                return False
        elif ' rev mod phys ' in normalized_text_orig:
            doi_start_idx = normalized_terms.index('rev')
            journal_terms = normalized_terms[doi_start_idx:doi_start_idx+4]
            try:
                vol = normalized_terms[doi_start_idx+4]
                aps_id = normalized_terms[doi_start_idx+5]
            except IndexError:
                return False
        if re.match(r'^\d+$', vol) and re.match(r'^\d+$', aps_id):
            doi_guess = '10.1103/{}.{}.{}'.format(
                ''.join(journal_terms),
                vol,
                aps_id
                )
            return doi_guess
    return False


def find_arxiv_id(text):
    """ Loor for an arXiv ID within the given text.
    """

    match = ARXIV_ID_PATT.search(text)
    if match:
        return match.group(1)
    else:
        match = ARXIV_URL_PATT.search(text)
        if match:
            return match.group(1)
    return False


def MAG_paper_authors(db_engine, mid):
    # q = sqltext(("select normalizedname from authors where authorid in (select"
    #              " authorid from paperauthoraffiliations where paperid = :mid)"
    #             ))
    # tuples = db_engine.execute(q, mid=mid).fetchall()
    tuples = db_engine.execute(
        ('select normalizedname from authors where authorid in (select'
         ' authorid from paperauthoraffiliations where paperid = {})'
         '').format(mid)
        ).fetchall()
    names = []
    for tupl in tuples:
        names.extend([n for n in tupl[0].split() if len(n) > 1])
    return names


def MAG_papers_by_title(db_engine, title):
    # q = sqltext(("select paperid, citationcount from papers where papertitle ="
    #              " :title"))
    # tuples = db_engine.execute(q, title=title).fetchall()
    if '\'' in title:
        # this is impossible
        title = mag_normalize(mag_normalize(mag_normalize(title)))
    tuples = db_engine.execute(
        ('select paperid, citationcount from papers where papertitle = \'{}\''
         '').format(title)
        ).fetchall()
    return tuples


def match(db_uri=None, in_dir=None, processes=1):
    """ Match bibitem strings to MAG IDs
    """

    if not (db_uri or in_dir):
        print('need either DB URI or input directory path')
        return False
    if in_dir:
        db_path = os.path.join(in_dir, 'refs.db')
        db_uri = 'sqlite:///{}'.format(os.path.abspath(db_path))
    print('Setting up preliminary bibitem DB connection')
    pre_engine = create_engine(db_uri)

    print('Querying bibitem DB')
    bibitem_tuples = pre_engine.execute(
        'select uuid, in_doc, bibitem_string from bibitem').fetchall()

    done_uuids = []
    if os.path.isfile('batch_prev_done.log'):
        print('sorting bibitem tuples')
        bibitem_tuples.sort(key=lambda tup: tup[0])
        print('reading bibitems done in previous run')
        with open('batch_prev_done.log') as f:
            lines = f.readlines()
        done_uuids = [l.strip() for l in lines]
        print('sorting bibitems done in previous run')
        done_uuids.sort()
        done_uuid_idx = 0
        bibitem_tuples_idx = 0
        bibitem_tuples_new = []
        print('filtering out bibitems done in previous run')
        skipped = 0
        filled = 0
        inbetween = 0
        found = 0
        while done_uuid_idx < len(done_uuids):
            done_uuid = done_uuids[done_uuid_idx]
            bibitem_uuid = bibitem_tuples[bibitem_tuples_idx][0]
            if done_uuid == bibitem_uuid:
                found += 1
                done_uuid_idx += 1
                bibitem_tuples_idx += 1
            else:
                bibitem_tuples_new.append(bibitem_tuples[bibitem_tuples_idx])
                bibitem_tuples_idx += 1
        bibitem_tuples_new.extend(bibitem_tuples[bibitem_tuples_idx:])
        bibitem_tuples = bibitem_tuples_new

    print('to process: {} bibitems'.format(len(bibitem_tuples)))
    print('number of processes: {}'.format(processes))
    batch_size = int(len(bibitem_tuples)/processes)
    batches = []
    for batch_id in range(processes):
        start = batch_size * batch_id
        end = batch_size * (batch_id + 1)
        if batch_id == processes - 1:
            batch = bibitem_tuples[start:len(bibitem_tuples) - 1]
        else:
            batch = bibitem_tuples[start:end]
        batches.append((batch, db_uri, batch_id))
    print('batch size: {}'.format(len(batches[0][0])))

    p = Pool(processes)
    print(p.map(match_batch, batches))


def match_batch(arg_tuple):
    bibitem_tuples = arg_tuple[0]
    db_uri = arg_tuple[1]
    batch_id = arg_tuple[2]
    done_log_fn = 'batch_{}_done.log'.format(batch_id)
    def prind(msg):
        print('[batch #{}]: {}'.format(batch_id, msg))
    def log_done(uuid):
        with open(done_log_fn, 'a') as f:
            f.write('{}\n'.format(uuid))

    prind('Setting up bibitem DB connection')
    engine = create_engine(db_uri, connect_args={'timeout': 600})
    Base.metadata.create_all(engine)
    Base.metadata.bind = engine
    DBSession = sessionmaker(bind=engine)
    session = DBSession()

    prind('Setting up arXiv ID DB connection')
    # set up arXiv ID DB
    AIDBase = declarative_base()

    class Paper(AIDBase):
        __tablename__ = 'paper'
        id = Column(Integer(), autoincrement=True, primary_key=True)
        aid = Column(String(36))
        title = Column(UnicodeText())

    aid_db_uri = 'sqlite:///aid_title.db'
    aid_engine = create_engine(aid_db_uri, connect_args={'timeout': 60})
    AIDBase.metadata.create_all(aid_engine)
    AIDBase.metadata.bind = aid_engine
    AIDDBSession = sessionmaker(bind=aid_engine)
    aid_session = AIDDBSession()
    # /set up arXiv ID DB

    prind('Setting up MAG DB connection')
    # set up MAG DB
    MAGBase = declarative_base()

    mag_db_uri = 'postgresql+psycopg2://XXX:YYY@localhost:5432/MAG'
    mag_engine = create_engine(mag_db_uri,
        connect_args={'options': '-c statement_timeout=60000'}
        )
    MAGBase.metadata.create_all(mag_engine)
    MAGBase.metadata.bind = mag_engine
    MAGDBSession = sessionmaker(bind=mag_engine)
    mag_session = MAGDBSession()

    MAGPaper = Table('papers', MAGBase.metadata,
                     autoload=True, autoload_with=mag_engine)
    # /set up MAG DB

    # set up bibitem_link_map
    bibitem_link_tuples = engine.execute(
        'select uuid, link from bibitemlinkmap').fetchall()
    bibitem_link_map = {}
    for bl_tup in bibitem_link_tuples:
        bibitem_link_map[bl_tup[0]] = bl_tup[1]
    # /set up bibitem_link_map

    num_matches = 0
    num_phys_rev = 0
    num_by_aid = 0
    num_by_aid_fail = 0
    num_by_doi = 0
    num_by_doi_fail = 0
    num_no_title = 0
    num_aps_doi_rebound = 0
    bi_total = len(bibitem_tuples)
    by_aid_total_time = 0
    by_aid_total_acc = 0
    by_doi_total_time = 0
    by_doi_total_acc = 0
    by_parscit_total_time = 0
    by_parscit_total_acc = 0
    magdb_total_time = 0
    magdb_total_acc = 0
    check_total_time = 0
    check_total_acc = 0
    db_total_time = 0
    db_total_acc = 0
    db_w_total_time = 0
    db_w_total_acc = 0
    prind('starting to match')
    for bi_idx, bibitem_tuple in enumerate(bibitem_tuples):
        bibitem_uuid = bibitem_tuple[0]
        bibitem_in_doc = bibitem_tuple[1]
        bibitem_string = bibitem_tuple[2]
        text = bibitem_string
        in_doc = bibitem_in_doc
        aid = find_arxiv_id(text)
        arxiv_id_success = False
        if aid:
            t1 = datetime.datetime.now()
            try:
                apaper_db = aid_session.query(Paper).filter_by(aid=aid).first()
            except SQLAlchemyTimeoutError:
                continue
            if not apaper_db:
                # catch cases like quant-ph/0802.3625 (acutally 0802.3625)
                guess = aid.split('/')[-1]
                try:
                    apaper_db = aid_session.query(Paper).\
                        filter_by(aid=guess).first()
                except SQLAlchemyTimeoutError:
                    continue
            if not apaper_db and re.match(r'^\d+$', aid):
                # catch cases like 14025167 (acutally 1402.5167)
                guess = '{}.{}'.format(aid[:4], aid[4:])
                try:
                    apaper_db = aid_session.query(Paper).\
                        filter_by(aid=guess).first()
                except SQLAlchemyTimeoutError:
                    continue
            # cases not handled:
            # - arXiv:9409089v2[hep-th] -> hep-th/9409089
            if apaper_db:
                text = apaper_db.title.replace('\n', ' ')
                text = re.sub('\s+', ' ', text)
                text_orig = text
                num_by_aid += 1
                arxiv_id_success = True
                t2 = datetime.datetime.now()
                d = t2 - t1
                by_aid_total_time += d.total_seconds()
                by_aid_total_acc += 1
        t1 = datetime.datetime.now()
        bibitemlink = bibitem_link_map.get(bibitem_uuid)
        t2 = datetime.datetime.now()
        d = t2 - t1
        db_total_time += d.total_seconds()
        db_total_acc += 1
        given_doi = False
        if bibitemlink:
            if 'doi' in bibitemlink:
                m = DOI_PATT.search(bibitemlink)
                if m:
                    given_doi = m.group(0)
        doi_success = False
        if not arxiv_id_success and given_doi:
            t1 = datetime.datetime.now()
            doi_resp = title_by_doi(given_doi)
            if doi_resp:
                text = doi_resp
                text_orig = text
                num_by_doi += 1
                doi_success = True
            t2 = datetime.datetime.now()
            d = t2 - t1
            by_doi_total_time += d.total_seconds()
            by_doi_total_acc += 1
        parscit_title = False
        if not (arxiv_id_success or doi_success):
            t1 = datetime.datetime.now()
            text_orig = text.replace('¦', '')
            if 'Phys. Rev.' in text_orig:
                num_phys_rev += 1
            text, journal, parscit_terms = parscit_parse(text_orig)
            t2 = datetime.datetime.now()
            d = t2 - t1
            by_parscit_total_time += d.total_seconds()
            by_parscit_total_acc += 1
            parscit_title = True
        if not text and parscit_terms:
            doi_guess = guess_aps_journal_paper_doi(parscit_terms)
            if doi_guess:
                doi_resp = title_by_doi(doi_guess)
                if doi_resp:
                    text = doi_resp
                    text_orig = text
                    num_aps_doi_rebound += 1
        if not (arxiv_id_success or doi_success):
            if not text:
                num_no_title += 1
                log_done(bibitem_uuid)
                continue

        # determine candidate MAG papers by title
        t1 = datetime.datetime.now()
        candidates = []
        if parscit_title:
            title_guesses = []
            normalized_title = mag_normalize(text)
            for lshift in range(3):
                for rshift in range(3):
                    words = normalized_title.split()
                    pick = words[lshift:(len(words)-rshift)]
                    if len(pick) >= 1:
                        title_guesses.append(' '.join(pick))
            title_guesses = list(set(title_guesses))
            for title_guess in title_guesses:
                try:
                    candidates = MAG_papers_by_title(mag_engine, title_guess)
                except SQLAlchemyTimeoutError:
                    continue
                if len(candidates) > 0:
                    break
        else:
            normalized_title = mag_normalize(text)
            try:
                candidates = MAG_papers_by_title(mag_engine, normalized_title)
            except SQLAlchemyTimeoutError:
                pass
        t2 = datetime.datetime.now()
        d = t2 - t1
        magdb_total_time += d.total_seconds()
        magdb_total_acc += 1

        if len(candidates) == 0:
            log_done(bibitem_uuid)
            continue

        # check author and citation count
        good_candidates = []
        choice = None
        bibitem_string_normalized = mag_normalize(bibitem_string)
        for c in candidates:
            author_names = MAG_paper_authors(mag_engine, c[0])
            for name in author_names:
                if name in bibitem_string_normalized:
                    good_candidates.append(c)
                    break
        if len(good_candidates) == 0:
            log_done(bibitem_uuid)
            continue
        elif len(good_candidates) == 1:
            choice = good_candidates[0]
        else:
            # pick the one with the highest citation count
            good_candidates = sorted(good_candidates,
                                     key=itemgetter(1),
                                     reverse=True)
            choice = good_candidates[0]

        if choice:
            mag_id = choice[0]
            num_matches += 1
            t1 = datetime.datetime.now()
            mag_id_db = BibitemMAGIDMap(
                uuid=bibitem_uuid,
                mag_id=mag_id
                )
            # add to DB
            try:
                try:
                    session.add(mag_id_db)
                    session.commit()
                    log_done(bibitem_uuid)
                except SQLAlchemyTimeoutError:
                    continue
            except SQLAlchemyOperationalError:
                prind(' - - - !!! - - -')
                prind('OperationalError at session.commit()')
                prind('for match to {}'.format(mag_id))
                prind(' - - - !!! - - -')
                continue
            t2 = datetime.datetime.now()
            d = t2 - t1
            db_w_total_time += d.total_seconds()
            db_w_total_acc += 1
        else:
            if arxiv_id_success:
                num_by_aid_fail += 1
            if doi_success:
                num_by_doi_fail += 1
            log_done(bibitem_uuid)
        if num_matches%100 == 0:
            prind('- - - - - - - - - - - - - - - - -')
            prind('{}/{}'.format(bi_idx+1, bi_total))
            prind('matches: {}'.format(num_matches))
            prind('Phys. Rev.: {}'.format(num_phys_rev))
            prind('no title: {}'.format(num_no_title))
            prind('by arXiv ID: {}'.format(num_by_aid))
            prind('by arXiv ID fail: {}'.format(num_by_aid_fail))
            prind('by doi: {}'.format(num_by_doi))
            prind('by doi fail: {}'.format(num_by_doi_fail))
            prind('APS doi rebound: {}'.format(num_aps_doi_rebound))
            prind('>>> avg time aID: {:.2f}'.format(
                by_aid_total_time/max(by_aid_total_acc, 1)
                ))
            prind('>>> avg time DOI: {:.2f}'.format(
                by_doi_total_time/max(by_doi_total_acc, 1)
                ))
            prind('>>> avg time ParsCit: {:.2f}'.format(
                by_parscit_total_time/max(by_parscit_total_acc, 1)
                ))
            prind('>>> avg time MAGDB: {:.2f}'.format(
                magdb_total_time/max(magdb_total_acc, 1)
                ))
            prind('>>> avg time DB r: {:.2f}'.format(
                db_total_time/max(db_total_acc, 1)
                ))
            prind('>>> avg time DB w: {:.2f}'.format(
                db_w_total_time/max(db_w_total_acc, 1)
                ))
    session.commit()
    final_stats = '------[ {} ]------\n'.format(batch_id)
    final_stats += '>>> time aID: {:.2f}\n'.format(by_aid_total_time)
    final_stats += '>>> time DOI: {:.2f}\n'.format(by_doi_total_time)
    final_stats += '>>> time ParsCit: {:.2f}\n'.format(by_parscit_total_time)
    final_stats += '>>> time MAGDB: {:.2f}\n'.format(magdb_total_time)
    final_stats += '>>> time DB r: {:.2f}\n'.format(db_total_time)
    final_stats += '>>> time DB w: {:.2f}'.format(db_w_total_time)
    prind(final_stats)
    return final_stats


if __name__ == '__main__':
    if len(sys.argv) not in [3, 4] or (sys.argv[1] not in ['path', 'uri']):
        print(('usage: python3 match_bibitems_mag.py path|uri </path/to/in/di'
               'r>|<db_uri> [num processes]'))
        sys.exit()
    path = sys.argv[1] == 'path'
    arg = sys.argv[2]
    if len(sys.argv) == 4:
        proc = int(sys.argv[3])
    else:
        proc = 1
    if path:
        ret = match(in_dir=arg, processes=proc)
    else:
        ret = match(db_uri=arg, processes=proc)
    if not ret:
        sys.exit()
