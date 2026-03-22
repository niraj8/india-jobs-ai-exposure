"""
Build compact JSON for the website by merging PLFS stats, NCO families, and AI scores.

Reads plfs_stats.json, nco_families.json, and ai_scores.json.
Writes site/data.json.

Usage:
    uv run python build_site_data.py
"""

import json
import os


def main():
    with open("plfs_stats.json") as f:
        plfs = json.load(f)

    with open("nco_families.json") as f:
        families = json.load(f)

    with open("ai_scores.json") as f:
        ai_scores = json.load(f)

    # Extract skill_level per group from families (first non-null value per group)
    group_skill = {}
    for fam in families:
        g = fam["group"]
        if g not in group_skill and fam["skill_level"] is not None:
            group_skill[g] = fam["skill_level"]

    # Index AI scores by nco_group
    ai_by_group = {s["nco_group"]: s for s in ai_scores}

    def build_slice(stats_list):
        result = []
        for p in stats_list:
            g = p["nco_group"]
            score = ai_by_group.get(g, {})
            result.append({
                "title": p["title"],
                "group": g,
                "division": p["division_title"],
                "sub_division": p["sub_division_title"],
                "workers": p["workers"],
                "median_pay": p["median_monthly_pay"],
                "mean_pay": p["mean_monthly_pay"],
                "pay_25th": p["pay_25th"],
                "pay_75th": p["pay_75th"],
                "skill_level": group_skill.get(g),
                "exposure": score.get("exposure"),
                "exposure_rationale": score.get("rationale"),
            })
        return result

    # Build all 4 employment type slices
    output = {}
    for emp_type in ("all", "salaried", "self_employed", "casual"):
        output[emp_type] = build_slice(plfs[emp_type])

    os.makedirs("site", exist_ok=True)
    with open("site/data.json", "w") as f:
        json.dump(output, f)

    for emp_type, slice_data in output.items():
        total = sum(d["workers"] for d in slice_data)
        with_pay = sum(1 for d in slice_data if d["median_pay"] is not None)
        print(f"{emp_type}: {len(slice_data)} groups, {with_pay} with pay, {total:,} workers")


if __name__ == "__main__":
    main()
