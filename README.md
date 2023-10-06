# unarXive

**Access**

* Data Set on Zenodo: [full](https://doi.org/10.5281/zenodo.7752754) / [permissively licensed subset](https://doi.org/10.5281/zenodo.7752615)
* [Data Sample](doc/unarXive_data_sample.tar.gz)
* ML Data on Hugging Face: [citation recommendation](https://huggingface.co/datasets/saier/unarXive_citrec) / [IMRaD classification](https://huggingface.co/datasets/saier/unarXive_imrad_clf)

**Documentation**

* Papers
    * [*Scientometrics*](http://link.springer.com/article/10.1007/s11192-020-03382-z) (2020)
    * [*JCDL 2023*](https://doi.org/10.1109/JCDL57899.2023.00020) (2023)
* [Data Format](#data)
* [Usage](#usage)
* [Development](#development)
* [Cite](#cite-as)

# Data

<p align="center">
  <img src="https://raw.githubusercontent.com/IllDepence/unarXive/master/doc/schema.svg" alt="unarXive schema" width="100%">
</p>

**unarXive contains**

* 1.9 M structured paper full-texts, containing
    * 63 M references (28 M linked to OpenAlex)
    * 134 M in-text citation markers (65 M linked)
    * 9 M figure captions
    * 2 M table captions
    * 742 M pieces of mathematical notation preserved as LaTeX

A comprehensive documentation of the **data format** can be found [here](doc/data_format.md).

You can find a **data sample** [here](doc/unarXive_data_sample.tar.gz).

# Usage

### Hugging Face Datasets

If you want to use unarXive for *citation recommendation* or *IMRaD classification*, you can simply use our Hugging Face datasets:

* [Citation Recommendation](https://huggingface.co/datasets/saier/unarxive_citrec)
* [IMRaD Classification](https://huggingface.co/datasets/saier/unarXive_imrad_clf)

For example, in the case of citation recommendation:

```
from datasets import load_dataset

citrec_data = load_dataset('saier/unarxive_citrec')
citrec_data = citrec_data.class_encode_column('label')  # assign target label column
citrec_data = citrec_data.remove_columns('_id')         # remove sample ID column
```

# Development

For instructions how to re-create or extend unarXive, see [src/](src/).

**Versions**

* Current release (1991–2022): see [*Access* section above](#unarxive)
* Previous releases ([old format](https://github.com/IllDepence/unarXive/tree/legacy_2020/)):
    * [1991–Jul 2020](https://zenodo.org/record/4313164)
    * [1991–2019](https://zenodo.org/record/3385851)

**Development Status**

See [issues](https://github.com/IllDepence/unarXive/issues).


## Cite as


**Current version**

```
@inproceedings{Saier2023unarXive,
  author        = {Saier, Tarek and Krause, Johan and F\"{a}rber, Michael},
  title         = {{unarXive 2022: All arXiv Publications Pre-Processed for NLP, Including Structured Full-Text and Citation Network}},
  booktitle     = {2023 ACM/IEEE Joint Conference on Digital Libraries (JCDL)},
  year          = {2023},
  pages         = {66--70},
  month         = jun,
  doi           = {10.1109/JCDL57899.2023.00020},
  publisher     = {IEEE Computer Society},
  address       = {Los Alamitos, CA, USA},
}
```

**Initial publication**

```
@article{Saier2020unarXive,
  author        = {Saier, Tarek and F{\"{a}}rber, Michael},
  title         = {{unarXive: A Large Scholarly Data Set with Publications’ Full-Text, Annotated In-Text Citations, and Links to Metadata}},
  journal       = {Scientometrics},
  year          = {2020},
  volume        = {125},
  number        = {3},
  pages         = {3085--3108},
  month         = dec,
  issn          = {1588-2861},
  doi           = {10.1007/s11192-020-03382-z}
}
```
