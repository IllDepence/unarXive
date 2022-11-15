""" Convert LaTeX files to S2ORC like JSONL output
"""

import jsonlines
import os
import re
import subprocess
import sys
import tempfile
import uuid
import IPython
from collections import OrderedDict
from hashlib import sha1
from lxml import etree

PDF_EXT_PATT = re.compile(r'^\.pdf$', re.I)
ARXIV_URL_PATT = re.compile(
    (r'arxiv\.org\/[a-z0-9]{1,10}\/(([a-z0-9-]{1,15}\/'
     r')?[\d\.]{5,10}(v\d)?$)'),
    re.I
)


def _write_debug_xml(tree):
    with open('/tmp/debugout.xml', 'wb') as f:
        f.write(etree.tostring(tree, pretty_print=True))


def _process_section_head(sec_node, head_node):
    tag_name_to_type = {
        'div0': 'section',
        'div1': 'subsection',
        'div2': 'subsubsection',
    }
    curr_sec = {
        'head': head_node.text,
        'num': sec_node.attrib.get('id-text', -1),
        'type': tag_name_to_type[sec_node.tag]
    }
    return curr_sec


def _process_paragraph(p_node, curr_sec):
    par_text = etree.tostring(
        p_node,
        encoding='unicode',
        method='text'
    )
    # par_text = re.sub('\s+', ' ', par_text).strip()
    par = OrderedDict({
        'section': curr_sec['head'],
        'sec_number': curr_sec['num'],
        'sec_type': curr_sec['type'],
        'text': par_text,
        'cite_spans': [],
        'ref_spans': []
    })
    return par


def parse(IN_DIR, OUT_DIR, INCREMENTAL, write_logs=True):
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
    file_iterator = 0
    paper_dicts_list = []
    jsonl_chunk_counter = 1

    # iterate over each file in input directory
    for fn in os.listdir(IN_DIR):
        path = os.path.join(IN_DIR, fn)  # absolute path to current file
        print("current file:", path)
        aid, ext = os.path.splitext(fn)  # get file extension
        # make txt file for each file
        aid_chunk = aid + "_" + str(jsonl_chunk_counter)  # FIXME: not used
        out_txt_path = os.path.join(OUT_DIR, '{}.txt'.format(aid))  # was aid
        out_json_path = os.path.join(
            OUT_DIR,
            '{}.jsonl'.format(str('chunk_'+str(jsonl_chunk_counter)))
        )

        # skip already existing files
        if INCREMENTAL and os.path.isfile(out_txt_path):  # is usually false
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

            # test-wise: print content of xml
            # with open(tmp_xml_path,'r') as testxml:
            #     print("#################################################################################################################################")
            #     print(testxml.read())

            # check if smth went wrong with parsing latex to temporary xml file
            if not os.path.isfile(tmp_xml_path):
                # print('FAILED {}. skipping'.format(aid))
                log(('\n--- {} ---\n{}\n----------\n'
                     '').format(aid, 'no tralics output'))
                continue
            with open(tmp_xml_path) as f:
                try:
                    tree = etree.parse(f, parser)  # get tree of XML hierarchy
                    print("tree worked")
                    file_iterator += 1
                # catch exception to faulty XML file
                except (etree.XMLSyntaxError, UnicodeDecodeError) as e:
                    # print('FAILED {}. skipping'.format(aid))
                    log('\n--- {} ---\n{}\n----------\n'.format(aid, e))
                    continue

            # start bulding paper dict
            paper_dict = OrderedDict({
                'paper_id': aid,
                '_pdf_hash': None,
                '_source_hash': None,
                'abstract': [],
                'body_text': [],
                'bib_entries': {},
                'ref_entries': {}
            })

            source_file_hasher = sha1()
            with open(path, 'rb') as source_file:
                buf = source_file.read()
                source_file_hasher.update(buf)
                # FIXME: determine and persist hash of input source file during
                #        normalization of LaTeX (normalize_arxiv_dump.py)
                #        and simply read and store it here afterwards
                source_file_hash = str(source_file_hasher.hexdigest())

            paper_dict['_source_hash'] = source_file_hash

            paper_dict['abstract'] = [{
                    'section': 'Abstract''',
                    'text': '',  # Abstract text goes here
                    'cite_spans': [],
                    'ref_spans': []
                }]  # not included in parse results

            # parse XML

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
            # # come in the follwoing forms:
            # # - <figure/table><head>caption text ...
            # # - <figure/table><caption>caption text ...
            # # - <float type="figure/table"><caption>caption text ...

            ftags = tree.xpath('//{}'.format('figure'))
            ttags = tree.xpath('//{}'.format('table'))
            fltags = tree.xpath('//{}'.format('float'))

            paper_dict['ref_entries'] = {}

            for xtag in ftags + ttags + fltags:
                if xtag.tag in ['figure', 'table']:
                    treat_as_type = xtag.tag
                else:
                    assert xtag.tag == 'float'
                    if xtag.get('type') in ['figure', 'table']:
                        treat_as_type = xtag.get('type')
                    else:
                        continue
                elem_uuid = uuid.uuid4()  # create uuid for each fig/tbl

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
                            caption_text = elem_text
                if len(caption_text) < 1:
                    caption_text = 'NO_CAPTION'

                xtag.tail = '{{{{{}:{}}}}}'.format(treat_as_type, elem_uuid)

                if treat_as_type == 'figure':
                    paper_dict['ref_entries'][str(elem_uuid)] = {
                        'caption': ''.join(caption_text.splitlines()),
                        'type': 'figure'}

                elif treat_as_type == 'table':
                    paper_dict['ref_entries'][str(elem_uuid)] = {
                        'caption': ''.join(caption_text.splitlines()),
                        'type': 'table'}

            # remove all figure/table/float tags from xml file
            etree.strip_elements(tree, 'figure', with_tail=False)
            etree.strip_elements(tree, 'table', with_tail=False)
            etree.strip_elements(tree, 'float', with_tail=False)

            # math notation
            for ftag in tree.xpath('//{}'.format('formula')):
                # uuid
                formula_uuid = uuid.uuid4()
                latex_content = etree.tostring(
                    ftag.find('texmath'),
                    encoding='unicode',
                    method='text',
                    with_tail=False
                )
                # mathml_content = etree.tostring(
                #     etree.ETXPath(
                #         '{http://www.w3.org/1998/Math/MathML}math'
                #     )(ftag)[0],
                #     encoding='unicode',
                #     method='xml',
                #     with_tail=False
                # )
                if ftag.tail:
                    new_tail = ' {}'.format(ftag.tail)
                else:
                    new_tail = ''
                ftag.tail = '{{{{formula:{}}}}}{}'.format(
                     formula_uuid,
                     new_tail
                )

                paper_dict['ref_entries'][str(formula_uuid)] = {
                    'latex': ''.join(latex_content.splitlines()),
                    'type': 'formula'}

            # remove all formula tags from XML file
            etree.strip_elements(tree, 'formula', with_tail=False)

            # remove title and authors (works only in a few papers)
            attributes = ['title', 'author', 'date', 'thanks']  # keywords
            for attribute in attributes:
                etree.strip_elements(tree, attribute, with_tail=False)
            # remove what is most likely noise
            mby_noise = tree.xpath('//unexpected')
            for mn in mby_noise:
                if len(mn.getchildren()) == 0:
                    mn.getparent().remove(mn)
            # replace non citation references with REF
            for rtag in tree.xpath('//ref[starts-with(@target, "uid")]'):
                # FIXME: should resolve section refs here
                if rtag.tail:
                    rtag.tail = '{} {}'.format('REF', rtag.tail)
                else:
                    rtag.tail = ' {}'.format('REF')

            # processing of citation markers
            bibitems = tree.xpath('//bibitem')
            bibkey_map = {}

            paper_dict['bib_entries'] = {}
            bib_item_counter = 0

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
                # NOTE: commented out lines below b/c it removes information
                # # replace the uuid of formulas in reference string
                # text = re.sub(r'(^{{formula:)(.*)', '', text)
                sha_hash = sha1()
                items = [text.encode('utf-8'), str(aid).encode('utf-8')]
                for item in items:
                    sha_hash.update(item)
                sha_hash_string = str(sha_hash.hexdigest())
                local_key = bi.get('id')
                bibkey_map[local_key] = sha_hash_string

                paper_dict['bib_entries'][sha_hash_string] = {
                    'bib_entry_raw': text
                }

                contained_arXiv_ids_list = []
                contained_links_list = []

                for xref in containing_p.findall('xref'):
                    link = xref.get('url')
                    match = ARXIV_URL_PATT.search(link)
                    if match:
                        id_part = match.group(1)
                        contained_arXiv_ids_list.append(id_part)

                    else:
                        contained_links_list.append(link)

                paper_dict['bib_entries'][sha_hash_string][
                    'contained_arXiv_ids'
                ] = contained_arXiv_ids_list
                paper_dict['bib_entries'][sha_hash_string][
                    'contained_links'
                ] = contained_links_list

                bib_item_counter += 1

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

            # _write_debug_xml(tree)
            # IPython.embed()
            # sys.exit()

            # process document structure
            paragraphs = []
            curr_sec = {
                'head': '',
                'num': '-1',
                'type': ''
            }
            # div0 tag can appear on different levels of the XML hierarchy,
            # such as /std/div0 or /unknown/frontmatter/div0
            # we therefore take div0s from anywhere and assume they always
            # are the lowest level containers of the main textual contents
            top_level_sections = tree.xpath('//div0')
            if len(top_level_sections) == 0:
                # give up on sections and just use paragraphs
                paragraphs = [
                    _process_paragraph(p, curr_sec)
                    for p in tree.xpath('//p')
                ]
            for sec in top_level_sections:
                for sec_child in sec.getchildren():
                    # contents of section
                    if sec_child.tag == 'head':
                        # head
                        curr_sec = _process_section_head(
                            sec,
                            sec_child
                        )
                    elif sec_child.tag == 'p':
                        # text
                        par = _process_paragraph(
                            sec_child,
                            curr_sec
                        )
                        paragraphs.append(par)
                    elif sec_child.tag == 'div1':
                        # subsections
                        for suse_child in sec_child.getchildren():
                            # contents of subsection
                            if suse_child.tag == 'head':
                                # head
                                curr_sec = _process_section_head(
                                    sec_child,
                                    suse_child
                                )
                            elif suse_child.tag == 'p':
                                # text
                                par = _process_paragraph(
                                    suse_child,
                                    curr_sec
                                )
                                paragraphs.append(par)
                            elif suse_child.tag == 'div2':
                                # subsubsections
                                for sususe_child in suse_child.getchildren():
                                    # contents of subsection
                                    if sususe_child.tag == 'head':
                                        # head
                                        curr_sec = _process_section_head(
                                            suse_child,
                                            sususe_child
                                        )
                                    elif sususe_child.tag == 'p':
                                        # text
                                        par = _process_paragraph(
                                            sususe_child,
                                            curr_sec
                                        )
                                        paragraphs.append(par)

            paper_dict['body_text'] = paragraphs

        # bundle paper dicts for presisting as JSONL (one JSONL per 100k pprs)
        paper_dicts_list.append(paper_dict)

        # persist 100k papers as JSONL, one paper per line
        if file_iterator % 1000000 == 0:
            with jsonlines.open(out_json_path, 'w') as writer:
                print("Writing JSONL for", out_json_path)
                writer.write_all(paper_dicts_list)
            paper_dicts_list = []
            jsonl_chunk_counter += 1

    # persist last remaining papers
    if not file_iterator % 1000000 == 0:
        with jsonlines.open(out_json_path, 'w') as writer:
            print("Writing JSONL finally for", out_json_path)
            writer.write_all(paper_dicts_list)
        paper_dicts_list = []
        jsonl_chunk_counter += 1

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
