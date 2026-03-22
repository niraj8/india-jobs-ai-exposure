"""
Compute pay and employment stats per NCO-2015 group from PLFS 2024 microdata.

Reads person-level CSV, aggregates by 3-digit NCO group code, and outputs
weighted employment counts and earnings statistics.

Usage:
    uv run python scripts/compute_plfs_stats.py
"""

import json

import numpy as np
import pandas as pd

PERSON_CSV = "data/plfs-2024/cperv1.csv"
NCO_FAMILIES_JSON = "nco_families.json"
OUTPUT_PATH = "plfs_stats.json"

# PLFS weight divisor: multiplier is in '00', pooled across 2 sub-samples and 4 quarters
# weight = Subsample_Multiplier / (100 * 2 * 4) = Subsample_Multiplier / 800
WEIGHT_DIVISOR = 800

# Principal status codes indicating employment (UPSS - Usual Principal Status)
# 11-51 = various forms of employment (self-employed, regular wage, casual labor)
EMPLOYED_STATUS_CODES = set(range(11, 52))

EMP_TYPE_FILTERS = {
    "all": set(range(11, 52)),
    "salaried": {31},
    "self_employed": {11, 12, 21},
    "casual": {41, 51},
}


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Compute weighted quantile."""
    sort_idx = np.argsort(values)
    sorted_values = values[sort_idx]
    sorted_weights = weights[sort_idx]
    cum_weights = np.cumsum(sorted_weights)
    total = cum_weights[-1]
    target = q * total
    idx = np.searchsorted(cum_weights, target)
    return float(sorted_values[min(idx, len(sorted_values) - 1)])


def compute_group_stats(df, group_titles, group_divisions):
    """Compute per-NCO-group stats for a filtered DataFrame. Returns a list of stat dicts."""
    results = []
    for group_code, group_df in df.groupby("nco_group"):
        sample_size = len(group_df)
        workers = int(round(group_df["weight"].sum()))

        # Earnings stats (only for those with positive earnings)
        earners = group_df[group_df["earnings"] > 0]
        if len(earners) >= 3:
            vals = earners["earnings"].values
            wts = earners["weight"].values
            median_pay = int(round(weighted_quantile(vals, wts, 0.5)))
            mean_pay = int(round(np.average(vals, weights=wts)))
            pay_25th = int(round(weighted_quantile(vals, wts, 0.25)))
            pay_75th = int(round(weighted_quantile(vals, wts, 0.75)))
        else:
            median_pay = mean_pay = pay_25th = pay_75th = None

        title = group_titles.get(group_code, "")
        hierarchy = group_divisions.get(group_code, {})

        results.append(
            {
                "nco_group": group_code,
                "title": title,
                "division": hierarchy.get("division", ""),
                "division_title": hierarchy.get("division_title", ""),
                "sub_division": hierarchy.get("sub_division", ""),
                "sub_division_title": hierarchy.get("sub_division_title", ""),
                "workers": workers,
                "median_monthly_pay": median_pay,
                "mean_monthly_pay": mean_pay,
                "pay_25th": pay_25th,
                "pay_75th": pay_75th,
                "sample_size": sample_size,
                "earners_in_sample": len(earners),
            }
        )

    results.sort(key=lambda x: x["nco_group"])
    return results


def main():
    # Load NCO families for group code → title mapping
    with open(NCO_FAMILIES_JSON) as f:
        families = json.load(f)

    group_titles = {}
    group_divisions = {}
    for fam in families:
        gc = fam["group"]
        if gc and gc not in group_titles:
            group_titles[gc] = fam["group_title"]
            group_divisions[gc] = {
                "division": fam["division"],
                "division_title": fam["division_title"],
                "sub_division": fam["sub_division"],
                "sub_division_title": fam["sub_division_title"],
            }

    # Load PLFS person-level data
    cols = [
        "Principal_Occupation_Code",
        "Principal_Status_Code",
        "CWS_Earnings_Salaried",
        "CWS_Earnings_SelfEmployed",
        "Subsample_Multiplier",
    ]
    print(f"Reading {PERSON_CSV}...")
    df = pd.read_csv(PERSON_CSV, usecols=cols)
    print(f"  Total persons: {len(df):,}")

    # Filter to employed persons with occupation codes
    df = df[
        df["Principal_Occupation_Code"].notna()
        & df["Principal_Status_Code"].isin(EMPLOYED_STATUS_CODES)
    ].copy()
    print(f"  Employed with occupation code: {len(df):,}")

    # Extract 3-digit NCO group code
    df["nco_group"] = df["Principal_Occupation_Code"].astype(int).astype(str)

    # Compute weight
    df["weight"] = df["Subsample_Multiplier"] / WEIGHT_DIVISOR

    # Combine earnings: salaried and self-employed are mutually exclusive
    df["earnings"] = df["CWS_Earnings_Salaried"].fillna(0) + df[
        "CWS_Earnings_SelfEmployed"
    ].fillna(0)

    # Aggregate by NCO group for each employment type
    all_results = {}
    for emp_type, status_codes in EMP_TYPE_FILTERS.items():
        filtered_df = df[df["Principal_Status_Code"].isin(status_codes)]
        all_results[emp_type] = compute_group_stats(filtered_df, group_titles, group_divisions)

    # Write output
    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\nResults:")
    for emp_type, results in all_results.items():
        total_workers = sum(r["workers"] for r in results)
        with_pay = [r for r in results if r["median_monthly_pay"] is not None]
        print(f"\n  [{emp_type}]")
        print(f"    NCO groups covered: {len(results)}")
        print(f"    Groups with pay data: {len(with_pay)}")
        print(f"    Total estimated workers: {total_workers:,}")

        # Show top 5 by employment for each type
        print(f"    Top 5 groups by employment:")
        by_workers = sorted(results, key=lambda x: x["workers"], reverse=True)
        for r in by_workers[:5]:
            pay_str = f"₹{r['median_monthly_pay']:,}" if r["median_monthly_pay"] else "N/A"
            print(
                f"      {r['nco_group']} {r['title'][:45]:45s}  "
                f"workers={r['workers']:>12,}  pay={pay_str}"
            )

    print(f"\nOutput written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
