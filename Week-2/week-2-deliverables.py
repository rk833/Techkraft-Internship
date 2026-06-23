import csv
import json
from pathlib import Path

base_dir = Path(__file__).resolve().parent
csv_path = base_dir / "students.csv"
json_path = base_dir / "profile.json"

students = []

with csv_path.open("r") as file:
    reader = csv.DictReader(file)

    for row in reader:
        row["age"] = int(row["age"])
        row["marks"] = int(row["marks"])
        students.append(row)

if not students:
    print("No data found")
    exit()

average_marks = sum(s["marks"] for s in students) / len(students)
top_student = max(students, key=lambda s: s["marks"])

print("Total Students:", len(students))
print("Average Marks:", average_marks)
print("Top Student:", top_student["name"])

with json_path.open("w") as file:
    json.dump(students, file, indent=4)

print("JSON file created successfully")