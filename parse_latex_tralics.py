""" Convert latex files to plain text with nice citation markers
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from lxml import etree
from hashlib import sha1
import csv

PDF_EXT_PATT = re.compile(r'^\.pdf$', re.I)
ARXIV_URL_PATT = re.compile(
    (r'arxiv\.org\/[a-z0-9]{1,10}\/(([a-z0-9-]{1,15}\/'
     r')?[\d\.]{5,10}(v\d)?$)'),
    re.I
)


def write_to_csv(output_dir, filename, header, lines):
    fn = f'{filename}.csv'
    fp = os.path.join(output_dir, fn)
    skip_header = os.path.isfile(fp)
    with open(fp, 'a', encoding='utf8') as f:
        # Setup CSV file
        csv_writer = csv.writer(f, dialect='unix')
        if not skip_header:
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

    num_citations = 0
    num_citations_notfound = 0

    # setup lists to put in csv instead of json
    lines_figures = []
    lines_tables = []
    lines_formulas = []
    # setup list to put in csv instead of db
    lines_bibitem = []
    lines_bibitemarxividmap = []
    lines_bibitemlinkmap = []
    # primary key replacements
    i = 1
    j = 1

    # iterate over each file in input directory
    for fn in os.listdir(IN_DIR):
        path = os.path.join(IN_DIR, fn)  # absolute path to current file
        aid, ext = os.path.splitext(fn)  # get file extension
        # make txt file for each file
        out_txt_path = os.path.join(OUT_DIR, '{}.txt'.format(aid))
        # skip already existing files
        if INCREMENTAL and os.path.isfile(out_txt_path):
            # print('{} already in output directory, skipping'.format(aid))
            continue
        # print(aid)
        if PDF_EXT_PATT.match(ext):  # Skip pdf files
            log('skipping file {} (PDF)'.format(fn))
            continue
        # write latex contents in a temporary xml file
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
            # check if smth went wrong with parsing latex to temporary xml file
            if not os.path.isfile(tmp_xml_path):
                # print('FAILED {}. skipping'.format(aid))
                log(('\n--- {} ---\n{}\n----------\n'
                     '').format(aid, 'no tralics output'))
                continue
            with open(tmp_xml_path) as f:
                try:
                    tree = etree.parse(f, parser)  # get tree of XML hierarchy
                # catch exception to faulty XML file
                except (etree.XMLSyntaxError, UnicodeDecodeError) as e:
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

            # figures and tables
            # # come in the follwoingforms:
            # # - <figure/table><head>caption text ...
            # # - <figure/table><caption>caption text ...
            # # - <float type="figure/table"><caption>caption text ...
            ftags = tree.xpath('//{}'.format('figure'))
            ttags = tree.xpath('//{}'.format('table'))
            fltags = tree.xpath('//{}'.format('float'))
            for xtag in ftags + ttags + fltags:
                if xtag.tag in ['figure', 'table']:
                    treat_as_type = xtag.tag
                else:
                    assert xtag.tag == 'float'
                    if xtag.get('type') in ['figure', 'table']:
                        treat_as_type = xtag.get('type')
                    else:
                        continue
                elem_uuid = uuid.uuid4()  # create uuid for each figure
                caption_text = ''
                for element in xtag.iter():
                    if element.tag in ['head', 'caption']:
                        elem_text = etree.tostring(
                            element,
                            encoding='unicode',
                            method='text',
                            with_tail=False
                        )
                        if len(elem_text) > 0:
                            caption_text += elem_text
                            caption_text += ' '
                if len(caption_text) < 1:
                    caption_text = 'NO_CAPTION'

                xtag.tail = '{{{{{}:{}}}}}'.format(treat_as_type, elem_uuid)
                # generate csv line
                line_csv = [
                    str(elem_uuid),
                    ''.join(caption_text.splitlines())
                ]
                if treat_as_type == 'figure':
                    lines_figures.append(line_csv)
                elif treat_as_type == 'table':
                    lines_tables.append(line_csv)
            # add all generated csv lines to file
            write_to_csv(
                OUT_DIR,
                'figures',
                ['id', 'caption'],
                lines_figures
            )
            write_to_csv(
                OUT_DIR,
                'tables',
                ['id', 'caption'],
                lines_tables
            )
            # delete all figure/table/float tags from xml file
            etree.strip_elements(tree, 'figure', with_tail=False)
            etree.strip_elements(tree, 'table', with_tail=False)
            etree.strip_elements(tree, 'float', with_tail=False)

            for ftag in tree.xpath('//{}'.format('formula')):
                # uuid
                formula_uuid = uuid.uuid4()
                latex_content = etree.tostring(
                    ftag.find('texmath'),
                    encoding='unicode',
                    method='text',
                    with_tail=False
                )
                mathml_content = etree.tostring(
                    etree.ETXPath(
                        '{http://www.w3.org/1998/Math/MathML}math'
                    )(ftag)[0],
                    encoding='unicode',
                    method='xml',
                    with_tail=False
                )
                if ftag.tail:
                    new_tail = ' {}'.format(ftag.tail)
                else:
                    new_tail = ''
                ftag.tail = '{{{{formula:{}}}}}{}'.format(
                     formula_uuid,
                     new_tail
                )
                # Generate csv line
                line_csv = [
                    str(formula_uuid),
                    ''.join(latex_content.splitlines()),
                    ''.join(mathml_content.splitlines())
                ]
                lines_formulas.append(line_csv)
            # add all generated csv lines to file
            write_to_csv(
                OUT_DIR,
                'formulas',
                ['id', 'latex', 'mathml'],
                lines_formulas
            )
            # remove all formula tags from XML file
            etree.strip_elements(tree, 'formula', with_tail=False)

            # remove title and authors (works only in a few papers)
            attributes = ['title', 'author', 'date', 'thanks']  # keywords
            for attribute in attributes:
                etree.strip_elements(tree, attribute, with_tail=False)
            # mark sections (works in most papers)
            for dtag in tree.xpath('//{}'.format('div0')):
                dtag[0].text = '<section>{}</section>'.format(dtag[0].text)
            # mark subsections (works in most papers)
            for dtag in tree.xpath('//{}'.format('div1')):
                dtag[0].text = '<subsection>{}</subsection>'.format(
                    dtag[0].text
                )
            # mark subsubsections (works in most papers)
            for dtag in tree.xpath('//{}'.format('div2')):
                dtag[0].text = '<subsubsection>{}</subsubsection>'.format(
                    dtag[0].text
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
                text = etree.tostring(
                    containing_p,
                    encoding='unicode',
                    method='text'
                )
                text = re.sub(r'\s+', ' ', text).strip()
                # replace the uuid of formulas in reference string
                # NOTE: commented out line below b/c it removes information
                # text = re.sub(r'(^{{formula:)(.*)', '', text)
                sha_hash = sha1()
                items = [text.encode('utf-8'), str(aid).encode('utf-8')]
                for item in items:
                    sha_hash.update(item)
                sha_hash_string = str(sha_hash.hexdigest())
                local_key = bi.get('id')
                bibkey_map[local_key] = sha_hash_string

                # contents of bibitem table
                line_csv = [
                    sha_hash_string,
                    aid,
                    text
                ]
                lines_bibitem.append(line_csv)

                # TODO: check if code below makes sense and/or
                #       needs refactoring

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
                        line_arxiv = [
                            sha_hash_string,
                            id_part
                        ]
                    else:
                        line_link = [
                            sha_hash_string,
                            link
                        ]

                    # ugly solution but no other way to get the primary key
                    # of the other dbs
                    if len(line_arxiv) > 0:
                        # line_arxiv.insert(0, local_id)
                        line_arxiv.insert(0, i)
                        lines_bibitemarxividmap.append(line_arxiv)
                        i += 1
                    else:
                        # line_link.insert(0, local_id)
                        line_link.insert(0, j)
                        lines_bibitemlinkmap.append(line_link)
                        j += 1

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

        # write contents in csv
        write_to_csv(
            OUT_DIR,
            'bibitem',
            ['uuid', 'in_doc', 'bibitem_string'],
            lines_bibitem
        )
        write_to_csv(
            OUT_DIR,
            'bibitemarividmap',
            ['id', 'uuid', 'arxiv_id'],
            lines_bibitemarxividmap
        )
        write_to_csv(
            OUT_DIR,
            'bibitemlinkmap',
            ['id', 'uuid', 'link'],
            lines_bibitemlinkmap
        )

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
    ret = parse(IN_DIR, OUT_DIR, INCREMENTAL=False)
    if not ret:
        sys.exit()
