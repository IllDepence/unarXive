### Format

`<cited_paper_mag_id>␞<adjacent_citations_mag_ids>␞<citing_paper_mag_id>␞<cited_paper_arxiv_id>␞<adjacent_citations_arxiv_ids>␞<citing_paper_arxiv_id>␞<citation_context>`  
(separated by a record separator (U+241E))

##### Format `<adjacent_citations_*_ids>` if length == 0
`empty`

##### Format `<adjacent_citations_*_ids>` if length == 1
`<id>`

##### Format `<adjacent_citations_*_ids>` if length &gt; 1
`<id>␟<id>␟...`  
(separated by a unit separator (U+241F))

##### Format `<citation_context>`
`<sentence><citing_sentence><sentence>`

### Notes

* `adjacent_citations_mag_ids` and `adjacent_citations_arxiv_ids` are, per line, always in the same order
* missing values (e.g. when a citing paper (which all have an arXiv ID) that does not have a corresponding `citing_paper_mag_id`) are given as "None"
* to create context exports in different configurations (fewer/more sentences before/after the citing sentence etc.) use script `code/extract_contexts.py`
