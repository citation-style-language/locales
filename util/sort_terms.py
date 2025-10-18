# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lxml<7",
# ]
# ///

"""sort_terms.py

Utility for sorting and normalizing CSL locale XML files.

This script parses CSL locale files (XML) and sorts <term> elements
according to the canonical ordering derived from `locales-en-US.xml`, and
rewrites the files preserving comments and structure. It also provides
helpers to parse the terms into a dictionary (`get_terms_dict`) to ensure the
script is semantics-preserving: running the sorter and then reparsing the file
should produce the same terms dictionary.

Typical usage (from the repository root):
    python util/sort_terms.py [-a] [locales-xx-YY.xml ...]

"""

import argparse
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lxml import etree

CSL_NAMESPACE = {"cs": "http://purl.org/net/xbiblio/csl"}

GENDER_FORM_ORDER: dict[str, int] = {"": 0, "masculine": 1, "feminine": 2}


@dataclass
class Section:
    term_names: set[str]
    form: str


def is_section_title(node) -> bool:
    if not isinstance(node, etree._Comment):
        return False
    previous = node.getprevious()
    if previous is not None and "\n" not in (previous.tail or ""):
        return False
    text = node.text if isinstance(node.text, str) else ""
    return text.isupper()


def get_en_us_sections() -> dict[str, Section]:
    tree = etree.parse("locales-en-US.xml")
    terms = tree.getroot().find(".//cs:terms", namespaces=CSL_NAMESPACE)
    assert terms is not None

    sections: dict[str, Section] = {}

    category: str = ""

    section: str = ""
    term_names: set[str] = set()
    term_forms: set[str] = set()

    for node in terms:
        if is_section_title(node):
            title = str(node.text).strip()
            if section:
                assert term_names
                assert len(term_forms) == 1
                form = term_forms.pop()
                if form == "":  # section of long forms
                    sections[section] = Section(term_names=set(term_names), form=form)
                    term_names = set()
                    term_forms = set()
                    category = section
                else:
                    sections[section] = Section(
                        term_names=set(sections[category].term_names).union(term_names),
                        form=form,
                    )
            section = title
        elif isinstance(node.tag, str):
            name: str = node.attrib.get("name", "")
            assert name
            form: str = node.attrib.get("form", "")

            term_names.add(name)
            term_forms.add(form)

    if section:
        assert term_names
        assert len(term_forms) == 1
        form = term_forms.pop()
        if form == "":
            sections[section] = Section(term_names=set(term_names), form=form)
        else:
            sections[section] = Section(
                term_names=set(sections[category].term_names), form=form
            )
    return sections


def sort_locale_terms(path: Path, sections: dict[str, Section]) -> None:
    print(str(path))

    original_text = path.read_text(encoding="utf-8")

    tree = etree.parse(str(path))
    terms = tree.getroot().find(".//cs:terms", namespaces=CSL_NAMESPACE)
    assert terms is not None

    grouped_terms = group_by_section(sections, terms)
    new_terms = flatten(grouped_terms)

    terms[:] = new_terms

    text = etree.tostring(tree, encoding="utf-8", xml_declaration=True).decode("utf-8")
    text = re.sub(r"[ \t]+\n", "\n", text) + "\n"
    text = text.replace("'", '"', 4)
    text = text.replace(" ", "&#160;")
    text = text.replace("‑", "&#8209;")
    text = text.replace("—", "&#8212;")

    if text != original_text:
        now = datetime.now().astimezone(timezone.utc).isoformat(timespec="seconds")
        text = re.sub(r"<updated>.*?</updated>", f"<updated>{now}</updated>", text)
    path.write_text(text, encoding="utf-8")


@dataclass
class TermContent:
    name: str
    sort_key: tuple[int, str, str]
    elements: list[etree._Element]  # May include comments following the term


def group_by_section(
    sections: dict[str, Section], terms: etree._Element
) -> dict[str, list[TermContent]]:
    grouped_terms: dict[str, list[TermContent]] = {section: [] for section in sections}

    term_content: TermContent | None = None
    other_terms: list[TermContent] = []
    tmp_comments: list[etree._Comment] = []  # Comments before any term

    gender_form_order = GENDER_FORM_ORDER.copy()

    for term in terms.iterchildren(tag=etree.Element):
        gender_form = term.attrib.get("gender-form")
        if gender_form:
            if gender_form == "feminine":
                gender_form_order["masculine"] = 2
                gender_form_order["feminine"] = 1
            break

    for node in terms:
        if isinstance(node, etree._Comment):
            text = node.text.strip() if isinstance(node.text, str) else ""
            if text in sections or is_section_title(node):
                term_content = None
                continue

            tail = ""
            previous = node.getprevious()
            if previous is not None:
                tail = previous.tail or ""

            if "\n" not in tail and term_content:
                term_content.elements.append(deepcopy(node))
            else:
                tmp_comments.append(deepcopy(node))

        elif isinstance(node.tag, str):
            term = node
            name: str = term.attrib.get("name", "")
            assert name
            form = term.attrib.get("form", "")
            gender_form = term.attrib.get("gender-form", "")

            for section_name, section in sections.items():
                if (name in section.term_names and form == section.form) or (
                    (name == "ordinal" or name.startswith("ordinal-"))
                    and section_name == "ORDINALS"
                ):
                    new_term = deepcopy(term)
                    # new_term.tail = "\n    "
                    term_content = TermContent(
                        name=name,
                        sort_key=(
                            gender_form_order.get(gender_form, 0),
                            "editor-translator" if name == "editortranslator" else name,
                            name,
                        ),
                        elements=[*tmp_comments, new_term],
                    )
                    tmp_comments = []
                    grouped_terms[section_name].append(term_content)

                    break
            else:
                term_content = TermContent(
                    name=name, sort_key=(0, name, ""), elements=[deepcopy(term)]
                )
                other_terms.append(term_content)

        if other_terms:
            grouped_terms["REMAINDERS"] = other_terms

    return grouped_terms


def flatten(grouped_terms: dict[str, list[TermContent]]) -> list[etree._Element]:
    new_terms: list[etree._Element] = []
    for section_name, section_terms in grouped_terms.items():
        # print(section_name)
        if new_terms:
            new_terms[-1].tail = "\n\n    "
        section_title = etree.Comment(f" {section_name} ")
        section_title.tail = "\n    "
        new_terms.append(section_title)

        if section_name not in {"PUNCTUATION", "REMAINDERS"}:
            section_terms = sorted(section_terms, key=lambda x: x.sort_key)
        for term_content in section_terms:
            new_terms.extend(term_content.elements)
            new_terms[-1].tail = "\n    "
    if new_terms:
        new_terms[-1].tail = "\n  "
    return new_terms


# The parsed form is based on `src/util_locale.js` of `Juris-M/citeproc-js`.
# <https://github.com/Juris-M/citeproc-js/blob/f88a47e6d143ace8a79569388534ff8ad9205da0/src/util_locale.js#L86>
def get_terms_dict(path: Path) -> dict[str, Any]:
    tree = etree.parse(str(path))
    terms = tree.getroot().find(".//cs:terms", namespaces=CSL_NAMESPACE)
    assert terms is not None

    term_dict = {
        "terms": {},
        "ord": {},
        "noun-genders": {},
    }
    term_dict["ord"]["1.0.1"] = None
    term_dict["ord"]["keys"] = {}
    ordinals_101 = {"last-digit": {}, "last-two-digits": {}, "whole-number": {}}
    ordinals101_toggle = False
    genderized_terms: dict[str, bool] = {}

    for term in terms.iterchildren(tag=etree.Element):
        name = term.attrib.get("name", "")
        if name == "issue":
            pass
        assert name
        if name == "sub verbo":
            name = "sub-verbo"

        if name == "ordinal" or name.startswith("ordinal-"):
            if name == "ordinal":
                ordinals101_toggle = True
            else:
                match = term.attrib.get("match", "")
                term_stub = name[8:]
                gender_form = term.attrib.get("gender-form", "neuter")
                if not match:
                    match = "last-two-digits"
                    if term_stub[:1] == "0":
                        match = "last-digit"
                if term_stub[:1] == "0":
                    term_stub = term_stub[1:]
                if term_stub not in ordinals_101[match]:
                    ordinals_101[match][term_stub] = {}
                ordinals_101[match][term_stub][gender_form] = name
            term_dict["ord"]["keys"][name] = True

        if name not in term_dict["terms"]:
            term_dict["terms"][name] = {}

        form = term.attrib.get("form", "long")
        gender_form = term.attrib.get("gender-form", "")
        gender = term.attrib.get("gender", "")

        if gender:
            term_dict["noun-genders"][name] = gender

        if gender_form:
            term_dict["terms"][name][gender_form] = {}
            term_dict["terms"][name][gender_form][form] = []
            target = term_dict["terms"][name][gender_form]
            genderized_terms[name] = True
        else:
            term_dict["terms"][name][form] = []
            target = term_dict["terms"][name]

        multiple = term.find("cs:multiple", namespaces=CSL_NAMESPACE)
        if multiple is not None:
            single = term.find("cs:single", namespaces=CSL_NAMESPACE)
            assert single is not None
            target[form].append(single.text or "")
            target[form].append(multiple.text or "")
        else:
            target[form] = term.text or ""

    if ordinals101_toggle:
        for ikey in genderized_terms:
            gender_segments = {}
            form_segments = 0
            for jkey in term_dict["terms"][ikey]:
                if jkey in {"masculine", "feminine"}:
                    gender_segments[jkey] = term_dict["terms"][ikey][jkey]
                else:
                    form_segments += 1
            if not form_segments:
                if "feminine" in gender_segments:
                    for jkey in gender_segments["feminine"]:
                        term_dict["terms"][ikey][jkey] = gender_segments["feminine"][
                            jkey
                        ]
                elif "masculine" in gender_segments:
                    for jkey in gender_segments["masculine"]:
                        term_dict["terms"][ikey][jkey] = gender_segments["masculine"][
                            jkey
                        ]

        term_dict["ord"]["1.0.1"] = ordinals_101

    return term_dict


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--all", action="store_true")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    paths = [Path(path) for path in args.files]
    if args.all or not paths:
        paths = sorted(Path().glob("locales-*.xml"))

    sections = get_en_us_sections()

    for path in paths:
        original_terms_dict = get_terms_dict(path)
        # pprint(original_terms_dict)
        sort_locale_terms(path, sections)
        terms_dict = get_terms_dict(path)
        # Path("original-terms-dict.json").write_text(
        #     json.dumps(
        #         original_terms_dict, ensure_ascii=False, indent="\t", sort_keys=True
        #     )
        # )
        # Path("terms-dict.json").write_text(
        #     json.dumps(terms_dict, ensure_ascii=False, indent="\t", sort_keys=True)
        # )
        assert terms_dict == original_terms_dict


if __name__ == "__main__":
    main()
