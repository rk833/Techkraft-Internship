"""
Generate handbook.pdf, the document Module 08 answers questions about.

Written as a policy handbook because that is a realistic RAG target: specific,
checkable facts spread across pages, where getting the number wrong matters.

Some obvious questions are deliberately NOT answerable from this document, so
the "say you do not know" behaviour can be tested. There is nothing here about
parental leave, salary, notice periods or pensions.

Usage:
    python make_sample.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.sample_pdf import write_pdf

HERE = Path(__file__).resolve().parent

PAGES = [
    [
        "Northbridge Analytics - Staff Handbook",
        "Section 1: Annual Leave",
        "",
        "Full time staff receive 25 days of annual leave per year, in addition to",
        "public holidays. Leave accrues monthly from the start date.",
        "",
        "Up to 5 unused days may be carried into the following year. Anything",
        "beyond 5 days is forfeited on 31 December and cannot be paid out.",
        "",
        "Requests of 3 days or fewer need 1 week of notice. Requests longer than",
        "3 days need 4 weeks of notice. All requests go through the leave system",
        "and must be approved by a line manager before travel is booked.",
        "",
        "During the annual audit period, which runs through March, no more than",
        "two members of the finance team may be on leave at the same time.",
    ],
    [
        "Section 2: Expenses",
        "",
        "Work related expenses are reimbursed if submitted within 60 days of the",
        "date on the receipt. Claims submitted after 60 days are rejected.",
        "",
        "Meals while travelling are capped at 40 pounds per day. Hotel stays are",
        "capped at 150 pounds per night outside London and 220 pounds inside",
        "London. Anything above these caps needs written approval from a director",
        "before the booking is made, not afterwards.",
        "",
        "Standard class rail travel is reimbursed in full. First class is only",
        "reimbursed when it was cheaper than standard at the time of booking, and",
        "the claim must include a screenshot showing both prices.",
        "",
        "Taxi fares are reimbursed only between 22:00 and 06:00, or when carrying",
        "equipment heavier than 10 kilograms.",
    ],
    [
        "Section 3: Remote Work",
        "",
        "Staff may work remotely up to 3 days per week. Tuesday is a fixed office",
        "day for all teams and cannot be taken remotely.",
        "",
        "Core hours are 10:00 to 16:00. Staff are expected to be reachable during",
        "core hours regardless of location. Hours outside that window are",
        "flexible provided the weekly total is met.",
        "",
        "Working from outside the United Kingdom requires approval from both the",
        "line manager and the people team, and is limited to 20 working days per",
        "calendar year for tax reasons.",
    ],
    [
        "Section 4: Equipment",
        "",
        "Laptops are refreshed every 3 years. A replacement can be requested",
        "earlier if the device fails and repair would take longer than 5 working",
        "days.",
        "",
        "Staff may claim up to 300 pounds towards home office equipment such as a",
        "chair, desk or monitor. This allowance resets every 2 years. The company",
        "retains ownership of anything above 100 pounds in value.",
        "",
        "Lost or stolen equipment must be reported to the security team within 24",
        "hours, and a police reference number is required for insurance.",
        "",
        "Personal use of company laptops is permitted but they must not be shared",
        "with family members or used to store personal financial records.",
    ],
]


def main() -> int:
    path = HERE / "handbook.pdf"
    write_pdf(path, PAGES)
    print(f"wrote {path.name} ({path.stat().st_size} bytes, {len(PAGES)} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
