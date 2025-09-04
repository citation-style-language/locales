# MIT license

# Copy new terms of `locales-en-US.xml` to other locals.

# Step 1: Add new terms in `locales-en-US.xml`. Make sure the "short", "verb", 
#         "verb-short" forms of each new term are also included.
# Step 2: Run `python3 add-locale-terms.py`


import glob
import os
import re

from lxml import etree


LOCALES_DIR = '.'
NSMAP = {'cs': 'http://purl.org/net/xbiblio/csl'}


def get_term_id(term) -> str:
    # e.g., `editor|short`
    term_id = term.attrib['name']
    if 'form' in term.attrib:
        term_id += '|' + term.attrib['form']
    # ignore "gender" and "gender-form"
    return term_id


def add_new_terms_to_locale(path, element_tree, new_terms, english_term_ids,
                            english_term_dict, locale_terms_el,
                            locale_term_ids, locale_term_list):
    for term_id in new_terms:
        common_terms = [
            tid for tid in english_term_ids if tid in locale_term_ids
        ]

        previous_terms = english_term_ids[:english_term_ids.index(term_id)]
        previous_common_term = [
            tid for tid in previous_terms if tid in common_terms
        ][-1]
        insert_index = locale_terms_el.index(
            locale_term_list[locale_term_ids.index(previous_common_term)])
        locale_terms_el.insert(insert_index, english_term_dict[term_id])

    et_str = etree.tostring(element_tree,
                            pretty_print=True,
                            xml_declaration=True,
                            encoding='utf-8').decode('utf-8')
                
    # https://github.com/citation-style-language/utilities/blob/master/csl-reindenting-and-info-reordering.py
    et_str = et_str.replace("'", '"', 4)  # replace quotes on XML declaration

    et_str = et_str.replace(' ', '&#160;')  # no-break space
    # et_str = et_str.replace('ᵉ', '&#7497;')
    et_str = et_str.replace(' ', '&#8195;')  # em space
    et_str = et_str.replace(' ', '&#8201;')  # thin space
    et_str = et_str.replace('‑', '&#8209;')  # non-breaking hyphen
    # # et_str = et_str.replace('–', "&#8211;")  # en dash
    # et_str = et_str.replace('—', '&#8212;')  # em dash
    et_str = et_str.replace(' ', '&#8239;')  # narrow no-break space

    et_str = re.sub(r'<term (.*?)/>', r'<term \1></term>', et_str)
    et_str = et_str.replace('<single/>', '<single></single>')
    et_str = et_str.replace('<multiple/>', '<multiple></multiple>')

    with open(path, 'w') as f:
        f.write(et_str.strip())
        f.write('\n')


def main():
    english_locale = 'locales-en-US.xml'
    english_path = os.path.join(LOCALES_DIR, english_locale)
    english_term_dict = dict()
    english_term_ids = []

    for term in etree.parse(english_path).findall('.//cs:term', NSMAP):
        term_id = get_term_id(term)
        english_term_ids.append(term_id)
        english_term_dict[term_id] = term

    for path in sorted(glob.glob(os.path.join(LOCALES_DIR, 'locales-*.xml'))):
        locale_file = os.path.split(path)[1]
        if locale_file == english_locale:
            continue

        element_tree = etree.parse(path)
        locale_terms_el = element_tree.find('.//cs:terms', NSMAP)

        locale_term_ids = []
        locale_term_list = []
        for term in locale_terms_el.findall('.//cs:term', NSMAP):
            term_id = get_term_id(term)
            locale_term_ids.append(term_id)
            locale_term_list.append(term)

        new_terms = [
            term_id for term_id in english_term_ids
            if term_id not in locale_term_ids and 'ordinal-' not in term_id
        ]
        new_terms = [
            term_id for term_id in new_terms
            if term_id.split('|')[0] in new_terms
        ]
        if new_terms:
            add_new_terms_to_locale(path, element_tree, new_terms,
                                    english_term_ids, english_term_dict,
                                    locale_terms_el, locale_term_ids,
                                    locale_term_list)


if __name__ == '__main__':
    main()
