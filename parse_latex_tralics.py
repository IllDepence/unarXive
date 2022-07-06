""" Convert latex files to plain text with nice citation markers
"""

import json
import jsonlines
import os
import re
import subprocess
import sys
import tempfile
import uuid
from lxml import etree
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db_model import Base, Bibitem, BibitemLinkMap, BibitemArxivIDMap
from hashlib import sha1
import csv

PDF_EXT_PATT = re.compile(r'^\.pdf$', re.I)
ARXIV_URL_PATT = re.compile(
    (r'arxiv\.org\/[a-z0-9]{1,10}\/(([a-z0-9-]{1,15}\/'
     r')?[\d\.]{5,10}(v\d)?$)'),
    re.I
)


# if the hash is not unique, it gets updated with integers until it is unique
# # FIXME: are these two identical funcions calling each other?!
def update_hash_one(
        sha_hash, count, local_key, session, bibkey_map, aid, text
):
    session.rollback()
    sha_hash.update(str(count).encode('utf-8'))
    sha_hash_string = str(sha_hash.hexdigest())
    try:
        bibkey_map[local_key] = sha_hash_string
        bibitem_db = Bibitem(
            uuid=sha_hash_string, in_doc=aid, bibitem_string=text
        )
        session.add(bibitem_db)
        session.flush()
    except:
        update_hash_two(
            sha_hash=sha_hash, count=0, local_key=local_key,
            session=session, bibkey_map=bibkey_map, aid=aid, text=text
        )


def update_hash_two(
        sha_hash, count, local_key, session, bibkey_map, aid, text
):
    session.rollback()
    sha_hash.update(str(count).encode('utf-8'))
    sha_hash_string = str(sha_hash.hexdigest())
    try:
        bibkey_map[local_key] = sha_hash_string
        bibitem_db = Bibitem(
            uuid=sha_hash_string, in_doc=aid, bibitem_string=text
        )
        session.add(bibitem_db)
        session.flush()
    except:
        update_hash_one(
            sha_hash=sha_hash, count=count + 1, local_key=local_key,
            session=session, bibkey_map=bibkey_map, aid=aid, text=text
        )


def write_to_csv(output_dir, filename, header, lines):
    with open(output_dir + filename + '.csv', 'w', encoding='utf8') as f:
        # Setup CSV file
        csv_writer = csv.writer(f)
        csv_writer.writerow(header)
        csv_writer.writerows(lines)


def parse(IN_DIR, OUT_DIR, INCREMENTAL, db_uri=None, write_logs=True):
    # Start setup of parse
    def log(msg):
        if write_logs:
            with open(os.path.join(OUT_DIR, 'log.txt'), 'a') as f:
                f.write('{}\n'.format(msg))

    if not os.path.isdir(IN_DIR):
        print('input directory does not exist')
        return False

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    # Setup sqlite database
    if not db_uri:
        db_path = os.path.join(OUT_DIR, 'refs.db')
        db_uri = 'sqlite:///{}'.format(os.path.abspath(db_path))
    engine = create_engine(db_uri)
    Base.metadata.create_all(engine)
    Base.metadata.bind = engine
    DBSession = sessionmaker(bind=engine)
    session = DBSession()

    num_citations = 0
    num_citations_notfound = 0

    # Setup lists to put in csv instead of json
    lines_figures = []
    lines_formulas = []
    lines_tables = []
    # Setup list to put in csv instead of db
    lines_bibitem = []
    lines_bibitemarxividmap = []
    lines_bibitemlinkmap = []

    # Iterate over each file in input directory
    for fn in os.listdir(IN_DIR):
        path = os.path.join(IN_DIR, fn)  # absolute path to current file
        aid, ext = os.path.splitext(fn)  # get file extension
        out_txt_path = os.path.join(OUT_DIR, '{}.txt'.format(aid))  # make txt file for each file
        if INCREMENTAL and os.path.isfile(out_txt_path):  # Skip already existing files
            # print('{} already in output directory, skipping'.format(aid))
            continue
        # print(aid)
        if PDF_EXT_PATT.match(ext):  # Skip pdf files
            log('skipping file {} (PDF)'.format(fn))
            continue
        # Write latex contents in a temporary xml file
        with tempfile.TemporaryDirectory() as tmp_dir_path:
            tmp_xml_path = os.path.join(tmp_dir_path, '{}.xml'.format(aid))
            # run latexml
            tralics_args = ['tralics',
                            '-silent',
                            '-noxmlerror',
                            '-utf8',
                            '-oe8',
                            '-entnames=false',
                            '-nomathml',
                            '-output_dir={}'.format(tmp_dir_path),
                            path]

            if write_logs:
                out = open(os.path.join(OUT_DIR, 'log_tralics.txt'), 'a')
            else:
                out = open(os.devnull, 'w')
            err = open(os.path.join(tmp_dir_path, 'tralics_out.txt'), mode='w')
            out.write('\n------------- {} -------------\n'.format(aid))
            out.flush()
            try:
                subprocess.run(tralics_args, stdout=out, stderr=err, timeout=5)
            except subprocess.TimeoutExpired as e:
                # print('FAILED {}. skipping'.format(aid))
                log('\n--- {} ---\n{}\n----------\n'.format(aid, e))
                continue
            out.close()
            err.close()

            # get mathless plain text from latexml output
            parser = etree.XMLParser()
            if not os.path.isfile(tmp_xml_path):  # Check if smth went wrong with parsing latex to temporary xml file
                # print('FAILED {}. skipping'.format(aid))
                log(('\n--- {} ---\n{}\n----------\n'
                     '').format(aid, 'no tralics output'))
                continue
            with open(tmp_xml_path) as f:
                try:
                    tree = etree.parse(f, parser)  # Get tree of XML hierarchy
                except (etree.XMLSyntaxError, UnicodeDecodeError) as e:  # Catch exception to faulty XML file
                    # print('FAILED {}. skipping'.format(aid))
                    log('\n--- {} ---\n{}\n----------\n'.format(aid, e))
                    continue
            # tags things that could be treated specially
            # - <Metadata>
            #     - <title>
            #     - <authors><author>
            # - <head>
            # - <proof>
            # - <abstract>
            # - <maketitle>
            # - <list> (might be used for larger chunks of text like
            #           related work)
            #
            # tags *NOT* to touch
            # - <unknown>: can surround whole content

            # Combined with csv output
            with jsonlines.open('figure_json.jsonl',
                                mode='a') as writer:  # Put all figures with ids and captions in json file
                for stag in tree.xpath('//{}'.format('figure')):
                    figure_uuid = uuid.uuid4()  # Create uuid for each figure
                    caption_text = ''
                    for element in stag.iter():
                        if element.tag == 'caption':
                            if element.text is not None:
                                caption_text += element.text + ' '
                    if len(caption_text) >= 1:
                        stag.tail = '{{{{figure:{}}}}} {}'.format(
                            1, caption_text
                        )
                        # generate json line
                        line = {
                            'id': str(figure_uuid),
                            'caption': caption_text
                        }
                        # Generate csv line
                        line_csv = [
                            str(figure_uuid),
                            caption_text
                        ]
                        lines_figures.append(line_csv)
                        line = json.dumps(line)
                        writer.write(line)
                    else:
                        stag.tail = '{{{{figure:{}}}}}'.format(figure_uuid)
                        # generate json line
                        line = {
                            'id': str(figure_uuid),
                            'caption': 'no-caption'
                        }
                        # Generate csv line
                        line_csv = [
                            str(figure_uuid),
                            'no-caption'
                        ]
                        lines_figures.append(line_csv)
                        line = json.dumps(line)
                        writer.write(line)
            # Add all generated csv lines to file
            write_to_csv(OUT_DIR, 'figure_csv', ['id', 'caption'], lines_figures)
            etree.strip_elements(tree, 'figure', with_tail=False)  # Delete all figure tags from xml file

            # Combined with csv output
            with jsonlines.open('table_json.jsonl', mode='a') as writer:
                for stag in tree.xpath('//{}'.format('table')):
                    # uuid
                    table_uuid = uuid.uuid4()
                    caption_text = ''
                    for element in stag.iter():
                        if element.tag == 'caption':
                            if element.text is not None:
                                caption_text += element.text + ' '
                    if len(caption_text) >= 1:
                        stag.tail = '{{{{table:{}}}}} {}'.format(
                            1, caption_text
                        )
                        # generate json line
                        line = {
                            'id': str(table_uuid),
                            'caption': caption_text
                        }
                        # Generate csv line
                        line_csv = [
                            str(table_uuid),
                            caption_text
                        ]
                        lines_tables.append(line_csv)
                        line = json.dumps(line)
                        writer.write(line)
                    else:
                        stag.tail = '{{{{table:{}}}}}'.format(figure_uuid)
                        # generate json line
                        line = {
                            'id': str(table_uuid),
                            'caption': 'no-caption'
                        }
                        # Generate csv line
                        line_csv = [
                            str(table_uuid),
                            'no-caption'
                        ]
                        lines_tables.append(line_csv)
                        line = json.dumps(line)
                        writer.write(line)
            # Add all generated csv lines to file
            write_to_csv(OUT_DIR, 'table_csv', ['id', 'caption'], lines_tables)

            etree.strip_elements(tree, 'table', with_tail=False)  # Delete all table files from XML file

            # Combined with csv output
            with jsonlines.open('formula_json.jsonl', mode='a') as writer:
                for stag in tree.xpath('//{}'.format('formula')):
                    content = stag.tail
                    doc_name = fn
                    try:
                        items = [
                            stag[1].text.encode('utf-8'),
                            doc_name.encode('utf-8')
                        ]
                    except:
                        items = ['none-type'.encode('utf-8')]
                    # uuid
                    formula_uuid = uuid.uuid4()
                    if stag.tail:
                        stag.tail = '{{{{formula:{}}}}} {}'.format(
                            formula_uuid,
                            content
                        )
                        # generate json line
                        line = {
                            'id': str(formula_uuid),
                            'content': stag[1].text
                        }
                        # Generate csv line
                        line_csv = [
                            str(formula_uuid),
                            stag[1].text
                        ]
                        lines_formulas.append(line_csv)
                        line = json.dumps(line)
                        writer.write(line)
                    else:
                        stag.tail = '{{{{formula:{}}}}}'.format(formula_uuid)
                        # generate json line
                        line = {
                            'id': str(formula_uuid),
                            'content': 'no-content'
                        }
                        # Generate csv line
                        line_csv = [
                            str(formula_uuid),
                            'no-content'
                        ]
                        lines_formulas.append(line_csv)
                        line = json.dumps(line)
                        writer.write(line)
            # Add all generated csv lines to file
            write_to_csv(OUT_DIR, 'formula_csv', ['id', 'caption'], lines_formulas)

            etree.strip_elements(tree, 'formula', with_tail=False)  # Remove all formula tag from XML file

            # remove title and authors (works only in a few papers)
            attributes = ['title', 'author', 'date', 'thanks']  # keywords
            for attribute in attributes:
                etree.strip_elements(tree, attribute, with_tail=False)
            # mark sections (works in most papers)
            for stag in tree.xpath('//{}'.format('div0')):
                stag[0].text = '<section>{}</section>'.format(stag[0].text)
            # mark subsections (works in most papers)
            for stag in tree.xpath('//{}'.format('div1')):
                stag[0].text = '<subsection>{}</subsection>'.format(
                    stag[0].text
                )
            # mark subsubsections (works in most papers)
            for stag in tree.xpath('//{}'.format('div2')):
                stag[0].text = '<subsubsection>{}</subsubsection>'.format(
                    stag[0].text
                )
            # remove what is most likely noise
            mby_noise = tree.xpath('//unexpected')
            for mn in mby_noise:
                if len(mn.getchildren()) == 0:
                    mn.getparent().remove(mn)
            # replace non citation references with REF
            for rtag in tree.xpath('//ref[starts-with(@target, "uid")]'):
                if rtag.tail:
                    rtag.tail = '{} {}'.format('REF', rtag.tail)
                else:
                    rtag.tail = ' {}'.format('REF')

            # processing of citation markers
            bibitems = tree.xpath('//bibitem')
            bibkey_map = {}

            for bi in bibitems:
                containing_p = bi.getparent()
                try:
                    while containing_p.tag != 'p':
                        # sometimes the bibitem element
                        # is not the direct child of
                        # the containing p item we want
                        containing_p = containing_p.getparent()
                except AttributeError:
                    # getparent() might return None
                    continue
                for child in containing_p.getchildren():
                    if child.text:
                        child.text = '{}'.format(child.text)
                text = etree.tostring(containing_p,
                                      encoding='unicode',
                                      method='text')
                text = re.sub('\s+', ' ', text).strip()
                # replace the uuid of formulas in reference string
                text = re.sub(r'(^{{formula:)(.*)', '', text)
                sha_hash = str(uuid.uuid4())  # That does nothing
                sha_hash = sha1()
                items = [text.encode('utf-8'), str(aid).encode('utf-8')]
                for item in items:
                    sha_hash.update(item)
                sha_hash_string = str(sha_hash.hexdigest())
                local_key = bi.get('id')

                # Contents of bibitem table
                try:
                    bibkey_map[local_key] = sha_hash_string
                    bibitem_db = Bibitem(
                        uuid=sha_hash_string,
                        in_doc=aid,
                        bibitem_string=text
                    )
                    line_csv = [
                        sha_hash_string,
                        aid,
                        text
                    ]
                    lines_bibitem.append(line_csv)
                    session.add(bibitem_db)
                    session.flush()
                except:  # idk what this does
                    update_hash_one(
                        sha_hash=sha_hash, count=0, local_key=local_key,
                        session=session, bibkey_map=bibkey_map, aid=aid,
                        text=text
                    )

                # nach arxiv Kategorie Filtern können
                # --> wissenschaftliche Disziplin mit abspeichern
                # Contents of bibitemarxividmap and bibitemlink db
                for xref in containing_p.findall('xref'):
                    link = xref.get('url')
                    match = ARXIV_URL_PATT.search(link)
                    # Part of ugly solution, see below
                    line_arxiv = []
                    line_link = []
                    if match:
                        id_part = match.group(1)
                        map_db = BibitemArxivIDMap(
                            uuid=sha_hash_string,
                            arxiv_id=id_part
                        )
                        line_arxiv = [
                            sha_hash_string,
                            id_part
                        ]
                    else:
                        map_db = BibitemLinkMap(
                            uuid=sha_hash_string,
                            link=link
                        )
                        line_link = [
                            sha_hash_string,
                            link
                        ]

                    session.add(map_db)
                    session.flush()

                    # ugly solution but no other way to get the primary key of the other dbs
                    local_id = map_db.id
                    if len(line_arxiv) > 0:
                        line_arxiv.insert(0, local_id)
                        lines_bibitemarxividmap.append(line_arxiv)
                    else:
                        line_link.insert(0, local_id)
                        lines_bibitemlinkmap.append(line_link)



                # make refs db a json (how to check unique constraint?)
                """
                with jsonlines.open('refs.jsonl', mode='a') as writer:

                line = {{'uuid':sha_hash_string,
                        'citing_arxiv_id':aid,
                        'citing_arxiv_categories':[],
                        'citing_paper_file':fn,
                        'cited_arxiv_id':None,
                        'cited_openalex_id':None,
                        'cited_doi':None,
                        'reference_text':text,
                        'reference_links':[link],
                        'reference_arxiv_ids':[id_part]}}
                """

            citations = tree.xpath('//cit')
            for cit in citations:
                num_citations += 1
                elem = cit.find('ref')
                if elem is None:
                    log(('WARNING: cite element in {} contains no ref element'
                         '').format(aid))
                    continue
                ref = elem.get('target')
                replace_text = ''
                if ref in bibkey_map:
                    marker = '{{{{cite:{}}}}}'.format(bibkey_map[ref])
                    replace_text += marker
                else:
                    log(('WARNING: unmatched bibliography key {} for doc {}'
                         '').format(ref, aid))
                    num_citations_notfound += 1
                if cit.tail:
                    cit.tail = replace_text + cit.tail
                else:
                    cit.tail = replace_text
            # /processing of citation markers
            etree.strip_elements(tree, 'Bibliography', with_tail=False)
            etree.strip_elements(tree, 'bibitem', with_tail=False)
            etree.strip_elements(tree, 'cit', with_tail=False)
            etree.strip_tags(tree, '*')
            tree_str = etree.tostring(tree, encoding='unicode', method='text')
            # tree_str = re.sub('\s+', ' ', tree_str).strip()

            with open(out_txt_path, 'w') as f:
                f.write(tree_str)
            session.commit()
        # Write db file contents in csv
        write_to_csv(OUT_DIR, 'bibitem_csv', ['uuid', 'in_doc', 'bibitem_string'], lines_bibitem)
        write_to_csv(OUT_DIR, 'bibitemarividmap_csv', ['id', 'uuid', 'arxiv_id'], lines_bibitemarxividmap)
        write_to_csv(OUT_DIR, 'bibitemlinkmap_csv', ['id', 'uuid', 'link'], lines_bibitemlinkmap)

    log(('Citations: {} (not unique)\nUnmatched citations: {}'
         '').format(num_citations, num_citations_notfound))
    return True


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(('usage: python3 parse_latex_tralics.py </path/to/in/dir> </path'
               '/to/out/dir>'))
        sys.exit()
    IN_DIR = sys.argv[1]
    OUT_DIR = sys.argv[2]
    ret = parse(IN_DIR, OUT_DIR, INCREMENTAL=True)
    if not ret:
        sys.exit()
