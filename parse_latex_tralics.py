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
from collections import OrderedDict, defaultdict
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


def _process_section_node(sec_node, curr_sec):
    """ Recursive function for getting text content of
        a section.
    """

    text_elemnts = []
    skip_tags = [
        'clearpage',
        'newpage',
        'tableofcontents',
        'vfill'
    ]
    for child_node in sec_node.getchildren():
        if child_node.tag in skip_tags:
            continue
        elif child_node.tag == 'head':
            # head
            curr_sec = _process_section_head(
                sec_node,
                child_node
            )
        elif child_node.tag[:3] == 'div':
            text_elemnts.extend(
                _process_section_node(child_node, curr_sec)
            )
        else:
            text_elem = _process_content_node(child_node, curr_sec)
            if len(text_elem['text'].strip()) > 0:
                text_elemnts.append(text_elem)
    return text_elemnts


def _process_section_head(sec_node, head_node):
    tag_name_to_type = defaultdict(str)
    tag_name_to_type['div0'] = 'section'
    tag_name_to_type['div1'] = 'subsection'
    tag_name_to_type['div2'] = 'subsubsection'
    curr_sec = {
        'head': head_node.text,
        'num': sec_node.attrib.get('id-text', '-1'),
        'type': tag_name_to_type[sec_node.tag]
    }
    return curr_sec


def _content_type_from_tag(tag):
    if tag == 'p':
        return 'paragraph'
    else:
        return tag


def _process_content_node(c_node, curr_sec):
    par_text = etree.tostring(
        c_node,
        encoding='unicode',
        method='text'
    )
    cite_spans, ref_spans = _get_local_refs(
        par_text
    )
    # par_text = re.sub('\s+', ' ', par_text).strip()
    par = OrderedDict({
        'section': curr_sec['head'],
        'sec_number': curr_sec['num'],
        'sec_type': curr_sec['type'],
        'content_type': _content_type_from_tag(c_node.tag),
        'text': par_text,
        'cite_spans': cite_spans,
        'ref_spans': ref_spans
    })
    return par


def _get_local_refs(par_text):
    marker_patt = re.compile(
        r'{{(cite|formula|figure|table|float):([0-9a-z-]+)}}'
    )
    cite_spans = []
    ref_spans = []
    for m in marker_patt.finditer(par_text):
        ref = {
            'start': m.start(),
            'end': m.end(),
            'text': m.group(0),
            'ref_id': m.group(2)
        }
        if m.group(1) == 'cite':
            cite_spans.append(ref)
        else:
            ref_spans.append(ref)
    return cite_spans, ref_spans


def parse(
    in_dir, out_dir, source_file_hashes, arxiv_meta, incremental,
    write_logs=True
):
    def log(msg):
        if write_logs:
            with open(os.path.join(out_dir, 'log.txt'), 'a') as f:
                f.write('{}\n'.format(msg))

    if not os.path.isdir(in_dir):
        print('input directory does not exist')
        return False

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    num_citations = 0
    num_citations_notfound = 0
    file_iterator = 0
    paper_dicts_list = []
    jsonl_chunk_counter = 1

    # iterate over each file in input directory
    for fn in os.listdir(in_dir):
        path = os.path.join(in_dir, fn)  # absolute path to current file
        # print('current file:', path)
        aid, ext = os.path.splitext(fn)  # get file extension
        # make txt file for each file
        out_json_path = os.path.join(
            out_dir,
            '{}.jsonl'.format(str('chunk_'+str(jsonl_chunk_counter)))
        )
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
                out = open(os.path.join(out_dir, 'log_tralics.txt'), 'a')
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
                'metadata': None,
                'abstract': [],
                'body_text': [],
                'bib_entries': {},
                'ref_entries': {}
            })

            paper_dict['_source_hash'] = source_file_hashes[aid]

            # aid_versionless = aid.split('v')[0]
            # metadata = arxiv_meta.get(aid_versionless, {})
            # paper_dict['metadata'] = metadata
            # abstract_text = metadata.get('abstract', '')
            abstract_text = ''  # TODO
            abstract = {
                'section': 'Abstract',
                'text': abstract_text,
                'cite_spans': [],
                'ref_spans': []
            }
            paper_dict['abstract'] = abstract

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

                        try:
                            location_offset_start = text.index(id_part)
                            location_offset_end = text.index(id_part) + len(id_part)
                            #print(f"### arxiv ID {id_part} in text gefunden ! ###")
                        except ValueError as e:
                            print(f"## value error: {e}\n{id_part} \n## not found in paper {aid} in \n{text}")
                            #print("## Setting offsets to None..")
                            #print("## Printing XML (item probably in tag but not in pretty text)")
                            #print(etree.tostring(containing_p, encoding='unicode', method='xml'))
                            location_offset_start = None
                            location_offset_end = None

                        arXiv_item_local_temp_dict = {'id':id_part,'start_offset':location_offset_start,'end_offset':location_offset_end}
                        contained_arXiv_ids_list.append(arXiv_item_local_temp_dict)

                    else:
                        try:
                            location_offset_start = text.index(link)
                            location_offset_end = text.index(link) + len(link)
                            #print(f"### link {link} ID in text gefunden! ###")
                        except ValueError as e:
                            print(f"## value error: {e}\n{link} \n## not found in paper {aid} in \n{text}")
                            #print("## Setting offsets to None..")
                            #print("## Printing XML (item probably in tag but not in pretty text)")
                            #print(etree.tostring(containing_p, encoding='unicode', method='xml'))
                            location_offset_start = None
                            location_offset_end = None

                        link_item_local_temp_dict = {'link':link,'start_offset':location_offset_start,'end_offset':location_offset_end}
                        contained_links_list.append(link_item_local_temp_dict)

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
                # if there are no div0 tags, we give up on sections and just
                # use paragraphs, lists, proofs, and listings and hope we
                # cover all content with those
                paragraphs = [
                    _process_content_node(p, curr_sec)
                    for p in tree.xpath((
                        '//*[self::p or self::list or self::proof or '
                        'self::listing]'
                    ))
                ]
            for sec in top_level_sections:
                paragraphs.extend(
                    _process_section_node(sec, curr_sec)
                )

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
    in_dir = sys.argv[1]
    out_dir = sys.argv[2]
    ret = parse(in_dir, out_dir, incremental=False)
    if not ret:
        sys.exit()
