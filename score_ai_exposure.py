"""
Score each NCO-2015 occupation group's AI exposure using an LLM via OpenRouter.

Sends occupation context (title, hierarchy, skill level, pay, employment) to
an LLM and collects structured AI exposure scores (0-10 with rationale).
Results are cached incrementally to resume on interruption.

Usage:
    uv run python scripts/score_ai_exposure.py
    uv run python scripts/score_ai_exposure.py --model google/gemini-3-flash-preview
    uv run python scripts/score_ai_exposure.py --start 0 --end 5  # test on first 5
"""

import argparse
import json
import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "google/gemini-3-flash-preview"
OUTPUT_FILE = "public/data/ai_scores.json"
PLFS_STATS = "public/data/plfs_stats.json"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """\
You are an expert analyst evaluating how exposed different occupations are to \
AI and automation. You will be given information about an occupation from \
India's National Classification of Occupations (NCO 2015), including its \
title, hierarchy, skill level, employment size, and median pay.

Rate the occupation's overall **AI Exposure** on a scale from 0 to 10.

AI Exposure measures: how much will AI reshape this occupation? Consider both \
direct effects (AI automating tasks currently done by humans) and indirect \
effects (AI making each worker so productive that fewer are needed).

A key signal is whether the job's work product is fundamentally digital. If \
the job can be done entirely from a home office on a computer — writing, \
coding, analyzing, communicating — then AI exposure is inherently high (7+), \
because AI capabilities in digital domains are advancing rapidly. Conversely, \
jobs requiring physical presence, manual skill, or real-time human interaction \
in the physical world have a natural barrier to AI exposure.

Consider India-specific context: the mix of formal/informal sector, \
technology adoption levels, and the nature of work in the Indian economy.

Use these anchors to calibrate your score:

- **0–1: Minimal exposure.** The work is almost entirely physical, hands-on, \
or requires real-time human presence in unpredictable environments. AI has \
essentially no impact on daily work. \
Examples: agricultural labourers, construction labourers, domestic helpers.

- **2–3: Low exposure.** Mostly physical or interpersonal work. AI might help \
with minor peripheral tasks (scheduling, paperwork) but doesn't touch the \
core job. \
Examples: electricians, plumbers, motor vehicle mechanics, tailors.

- **4–5: Moderate exposure.** A mix of physical/interpersonal work and \
knowledge work. AI can meaningfully assist with the information-processing \
parts but a substantial share of the job still requires human presence. \
Examples: nursing professionals, police officers, veterinarians, teachers.

- **6–7: High exposure.** Predominantly knowledge work with some need for \
human judgment, relationships, or physical presence. AI tools are already \
useful and workers using AI may be substantially more productive. \
Examples: secondary school teachers, managers, accountants, legal professionals.

- **8–9: Very high exposure.** The job is almost entirely done on a computer. \
All core tasks — writing, coding, analyzing, designing, communicating — are \
in domains where AI is rapidly improving. The occupation faces major \
restructuring. \
Examples: software developers, graphic designers, translators, data analysts.

- **10: Maximum exposure.** Routine information processing, fully digital, \
with no physical component. AI can already do most of it today. \
Examples: data entry clerks, telemarketers.

Respond with ONLY a JSON object in this exact format, no other text:
{
  "exposure": <0-10>,
  "rationale": "<2-3 sentences explaining the key factors>"
}\
"""


def build_occupation_prompt(group: dict) -> str:
    """Build the user prompt with occupation context."""
    pay_str = (
        f"₹{group['median_monthly_pay']:,}/month"
        if group.get("median_monthly_pay")
        else "N/A"
    )
    workers_str = f"{group['workers']:,}" if group.get("workers") else "N/A"

    return f"""\
Occupation: {group['title']}
NCO Group Code: {group['nco_group']}
Division: {group['division']} - {group['division_title']}
Sub-Division: {group['sub_division']} - {group['sub_division_title']}
Estimated Workers in India: {workers_str}
Median Monthly Pay: {pay_str}
"""


def score_occupation(client: httpx.Client, text: str, model: str) -> dict:
    """Send one occupation to the LLM and parse the structured response."""
    response = client.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
        },
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]

    # Strip markdown code fences if present
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    return json.loads(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument(
        "--force", action="store_true", help="Re-score even if already cached"
    )
    args = parser.parse_args()

    # Load PLFS stats (occupation groups with pay/employment data)
    with open(PLFS_STATS) as f:
        groups = json.load(f)

    subset = groups[args.start : args.end]

    # Load existing scores
    scores = {}
    if os.path.exists(OUTPUT_FILE) and not args.force:
        with open(OUTPUT_FILE) as f:
            for entry in json.load(f):
                scores[entry["nco_group"]] = entry

    print(f"Scoring {len(subset)} occupations with {args.model}")
    print(f"Already cached: {len(scores)}")

    errors = []
    client = httpx.Client()

    for i, group in enumerate(subset):
        code = group["nco_group"]

        if code in scores:
            continue

        prompt = build_occupation_prompt(group)
        print(f"  [{i+1}/{len(subset)}] {group['title']}...", end=" ", flush=True)

        try:
            result = score_occupation(client, prompt, args.model)
            scores[code] = {
                "nco_group": code,
                "title": group["title"],
                **result,
            }
            print(f"exposure={result['exposure']}")
        except Exception as e:
            print(f"ERROR: {e}")
            errors.append(code)

        # Save after each one (incremental checkpoint)
        with open(OUTPUT_FILE, "w") as f:
            json.dump(list(scores.values()), f, indent=2)

        if i < len(subset) - 1:
            time.sleep(args.delay)

    client.close()

    print(f"\nDone. Scored {len(scores)} occupations, {len(errors)} errors.")
    if errors:
        print(f"Errors: {errors}")

    # Summary stats
    vals = [s for s in scores.values() if "exposure" in s]
    if vals:
        avg = sum(s["exposure"] for s in vals) / len(vals)
        by_score = {}
        for s in vals:
            bucket = s["exposure"]
            by_score[bucket] = by_score.get(bucket, 0) + 1
        print(f"\nAverage exposure across {len(vals)} occupations: {avg:.1f}")
        print("Distribution:")
        for k in sorted(by_score):
            print(f"  {k}: {'█' * by_score[k]} ({by_score[k]})")


if __name__ == "__main__":
    main()
