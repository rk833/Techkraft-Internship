"""
Generate the three PDFs Module 09 searches across.

Three separate documents, each owned by a different department, so that
retrieval has to choose between sources rather than just between chunks. Some
questions are answerable from one document, some need two, and some are
answerable only if the right department is selected.

Usage:
    python make_samples.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.sample_pdf import write_pdf

HERE = Path(__file__).resolve().parent

DOCUMENTS = {
    "people-handbook.pdf": {
        "department": "people",
        "year": 2025,
        "pages": [
            [
                "Northbridge Analytics - People Handbook (2025)",
                "Section 1: Annual Leave",
                "",
                "Full time staff receive 25 days of annual leave per year, plus public",
                "holidays. Up to 5 unused days may be carried into the following year.",
                "Anything beyond 5 days is forfeited on 31 December.",
                "",
                "Requests of 3 days or fewer need 1 week of notice. Longer requests need",
                "4 weeks of notice and line manager approval before booking travel.",
            ],
            [
                "Section 2: Equipment and Expenses",
                "",
                "Laptops are refreshed every 3 years. Staff may claim up to 300 pounds",
                "towards home office equipment, resetting every 2 years.",
                "",
                "Lost or stolen equipment must be reported to the security team within",
                "24 hours. A police reference number is required for the insurance claim,",
                "and the people team will arrange a replacement device once security has",
                "confirmed the report.",
                "",
                "Expenses must be submitted within 60 days of the receipt date. Meals",
                "while travelling are capped at 40 pounds per day.",
            ],
        ],
    },
    "security-policy.pdf": {
        "department": "security",
        "year": 2026,
        "pages": [
            [
                "Northbridge Analytics - Security Policy (2026)",
                "Section 1: Passwords and Access",
                "",
                "Passwords must be at least 14 characters. Reuse across systems is",
                "forbidden. All staff must use the company password manager.",
                "",
                "Multi factor authentication is mandatory for email, the cloud console",
                "and the production database. Hardware keys are issued on request and",
                "are required for anyone with production database access.",
                "",
                "Access is reviewed quarterly. Accounts unused for 90 days are disabled",
                "automatically.",
            ],
            [
                "Section 2: Incidents and Lost Devices",
                "",
                "A lost or stolen laptop is treated as a security incident, not only an",
                "equipment problem. Report it to the security team immediately, and in",
                "all cases within 24 hours.",
                "",
                "Security will remotely wipe the device and revoke its certificates",
                "before any replacement is issued. Do not contact the people team for a",
                "replacement until the wipe has been confirmed.",
                "",
                "Suspected phishing should be forwarded to the security mailbox and then",
                "deleted. Never forward it to colleagues as a warning.",
            ],
        ],
    },
    "engineering-guide.pdf": {
        "department": "engineering",
        "year": 2026,
        "pages": [
            [
                "Northbridge Analytics - Engineering Guide (2026)",
                "Section 1: Deployment",
                "",
                "Deployments to production run Monday to Thursday only. Friday deploys",
                "need written approval from the on call engineer and a director.",
                "",
                "The rollback script takes the previous image tag as an argument. It does",
                "not look the tag up, so record it before deploying.",
                "",
                "Every deployment must pass the full test suite and a staging soak of at",
                "least 30 minutes.",
            ],
            [
                "Section 2: On Call and Code Review",
                "",
                "On call rotates weekly. The on call engineer acknowledges pages within",
                "15 minutes during working hours and 30 minutes overnight.",
                "",
                "Pull requests need one approval, or two if they touch billing or",
                "authentication. Review error handling before style. Check that failures",
                "are logged with enough context to debug, and that nothing swallows an",
                "exception silently.",
                "",
                "Production database access requires a hardware key, as set out in the",
                "security policy.",
            ],
        ],
    },
}


def main() -> int:
    for name, spec in DOCUMENTS.items():
        path = HERE / name
        write_pdf(path, spec["pages"])
        print(
            f"wrote {name} ({path.stat().st_size} bytes, "
            f"{len(spec['pages'])} pages, department={spec['department']})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
