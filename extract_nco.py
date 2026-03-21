"""
Extract NCO 2015 Family-level occupation data from the Concordance Table PDF.

Reads pages 34-238 (0-indexed: 45-249) of the NCO 2015 Vol I PDF and extracts
~590 Family-level records with their full hierarchy.

Usage:
    uv run python scripts/extract_nco.py
"""

import json
import re
import pdfplumber

PDF_PATH = "public/data/national classification of occupations _vol i- 2015.pdf"
OUTPUT_PATH = "public/data/nco_families.json"

# Pages 34-238 in PDF = 0-indexed 45-249 (12 front matter pages offset + 1 for TOC title page)
# Actually: page 33 in PDF footer = "VOLUME I 33" which is the concordance title page
# page 34 = first data page. Let's find the right 0-based index.
# From testing: pdf.pages[45] has Division 1 / Managers as first data row.
FIRST_PAGE = 45   # 0-indexed, PDF footer says "34"
LAST_PAGE = 249   # 0-indexed, PDF footer says "238"

# Skill level and education mapping by division number
SKILL_LEVEL_MAP = {
    "1": {"skill_level": None, "education": "Not Defined"},
    "2": {"skill_level": 4, "education": "More than 15 years of formal education"},
    "3": {"skill_level": 3, "education": "14-15 years of formal education"},
    "4": {"skill_level": 2, "education": "11-13 years of formal education"},
    "5": {"skill_level": 2, "education": "11-13 years of formal education"},
    "6": {"skill_level": 2, "education": "11-13 years of formal education"},
    "7": {"skill_level": 2, "education": "11-13 years of formal education"},
    "8": {"skill_level": 2, "education": "11-13 years of formal education"},
    "9": {"skill_level": 1, "education": "Up to 10 years of formal education"},
}


def slugify(title: str) -> str:
    """Convert a title to a URL-safe slug."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug


def clean_text(text: str | None) -> str:
    """Clean up extracted text (remove newlines, extra spaces)."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def parse_level(label: str) -> str | None:
    """Parse the level label from column 0."""
    label = clean_text(label)
    if not label:
        return None
    label_lower = label.lower().replace("-", "").replace(" ", "")
    if label_lower == "division":
        return "division"
    elif label_lower in ("subdivision", "sub"):
        return "sub_division"
    elif label_lower == "group":
        return "group"
    elif label_lower == "family":
        return "family"
    return None


def extract_families(pdf_path: str) -> list[dict]:
    """Extract all Family-level records from the NCO 2015 PDF."""
    pdf = pdfplumber.open(pdf_path)

    # First pass: collect all hierarchy titles (divisions, sub-divisions, groups)
    hierarchy = {
        "divisions": {},
        "sub_divisions": {},
        "groups": {},
    }

    # Current hierarchy context
    current_division = {"code": "", "title": ""}
    current_sub_division = {"code": "", "title": ""}
    current_group = {"code": "", "title": ""}
    current_family = None

    families = []
    occupation_count = 0

    for page_idx in range(FIRST_PAGE, min(LAST_PAGE + 1, len(pdf.pages))):
        page = pdf.pages[page_idx]
        tables = page.extract_tables()

        if not tables:
            continue

        for table in tables:
            for row in table:
                if not row or len(row) < 3:
                    continue

                col0 = clean_text(row[0])  # Level label
                col1 = clean_text(row[1]) if len(row) > 1 else ""  # Code
                col2 = clean_text(row[2]) if len(row) > 2 else ""  # Title

                # Skip header rows
                if col0 == "NCO 2015" or col1 == "NCO 2015":
                    continue

                level = parse_level(col0)

                if level == "division":
                    # Save previous family's occupation count
                    if current_family and occupation_count > 0:
                        current_family["occupation_count"] = occupation_count
                        occupation_count = 0

                    current_division = {"code": col1, "title": col2}
                    current_sub_division = {"code": "", "title": ""}
                    current_group = {"code": "", "title": ""}
                    hierarchy["divisions"][col1] = col2

                elif level == "sub_division":
                    if current_family and occupation_count > 0:
                        current_family["occupation_count"] = occupation_count
                        occupation_count = 0

                    current_sub_division = {"code": col1, "title": col2}
                    current_group = {"code": "", "title": ""}
                    hierarchy["sub_divisions"][col1] = col2

                elif level == "group":
                    if current_family and occupation_count > 0:
                        current_family["occupation_count"] = occupation_count
                        occupation_count = 0

                    current_group = {"code": col1, "title": col2}
                    hierarchy["groups"][col1] = col2

                elif level == "family":
                    # Save previous family's occupation count
                    if current_family and occupation_count > 0:
                        current_family["occupation_count"] = occupation_count

                    occupation_count = 0
                    div_code = current_division["code"]
                    skill_info = SKILL_LEVEL_MAP.get(div_code, {"skill_level": None, "education": ""})

                    current_family = {
                        "code": col1,
                        "title": col2,
                        "slug": slugify(col2),
                        "division": current_division["code"],
                        "division_title": current_division["title"],
                        "sub_division": current_sub_division["code"],
                        "sub_division_title": current_sub_division["title"],
                        "group": current_group["code"],
                        "group_title": current_group["title"],
                        "skill_level": skill_info["skill_level"],
                        "education": skill_info["education"],
                        "occupation_count": 0,
                    }
                    families.append(current_family)

                elif not level and col1 and "." in col1:
                    # This is an individual occupation row (code like 1111.0100)
                    occupation_count += 1

    # Save last family's occupation count
    if current_family and occupation_count > 0:
        current_family["occupation_count"] = occupation_count

    pdf.close()

    # Post-process: fill in missing hierarchy from codes
    for family in families:
        code = family["code"]
        if not code or len(code) < 4:
            continue

        div_code = code[0]
        sub_div_code = code[:2]
        group_code = code[:3]

        # Fill division if missing
        if not family["division"]:
            family["division"] = div_code
            family["division_title"] = hierarchy["divisions"].get(div_code, "")
            skill_info = SKILL_LEVEL_MAP.get(div_code, {"skill_level": None, "education": ""})
            family["skill_level"] = skill_info["skill_level"]
            family["education"] = skill_info["education"]

        # Fill sub-division if missing
        if not family["sub_division"]:
            family["sub_division"] = sub_div_code
            family["sub_division_title"] = hierarchy["sub_divisions"].get(sub_div_code, "")

        # Fill group if missing
        if not family["group"]:
            family["group"] = group_code
            family["group_title"] = hierarchy["groups"].get(group_code, "")

    return families


def main():
    print(f"Extracting families from: {PDF_PATH}")
    families = extract_families(PDF_PATH)

    print(f"\nExtracted {len(families)} families")

    # Summary by division
    div_counts = {}
    total_occupations = 0
    for f in families:
        div = f"{f['division']} - {f['division_title']}"
        div_counts[div] = div_counts.get(div, 0) + 1
        total_occupations += f["occupation_count"]

    print(f"Total occupations across all families: {total_occupations}")
    print("\nFamilies per division:")
    for div, count in sorted(div_counts.items()):
        print(f"  {div}: {count}")

    # Write output
    with open(OUTPUT_PATH, "w") as f:
        json.dump(families, f, indent=2, ensure_ascii=False)

    print(f"\nOutput written to: {OUTPUT_PATH}")

    # Show a few examples
    print("\nSample entries:")
    for entry in families[:3]:
        print(f"  {entry['code']}: {entry['title']} (occupations: {entry['occupation_count']})")


if __name__ == "__main__":
    main()
