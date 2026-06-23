# Week 2 - Python Basics and Data Handling

## Overview

This is the Week 2 deliverable for the 3-Month AI Intern program. It covers two parts:

#### 1. practice exercises covering lists, tuples, dictionaries, sets, loops, conditionals, file handling, JSON, and NumPy
#### 2. the main deliverable, a small data processing script that reads student data from a CSV file and produces a summary plus a JSON output

## Files

- `week-2-practice.ipynb` - notebook with all practice exercises
- `week-2-deliverable.py` - the small data processing script (main deliverable)
- `students.csv` - sample input data used by the deliverable script
- `profile.json` - generated output file (created when the script runs)

## 1. Practice Exercises

All practice exercises are in `week-2-practice.ipynb`.

### Lists

Basic operations on a list of numbers: sum, largest value, and smallest value.

### Tuples

Stored a student's name, age, and role as a tuple and accessed each value by index.

### Dictionaries

Stored student details as a dictionary and looped through the key-value pairs.

### Sets

Created two sets of student names and demonstrated union and intersection.

### Conditionals

Took a number as input and checked whether it is even or odd.

### Reading a CSV File

Read rows from a CSV file using the `csv` module and printed each row.

### Converting CSV to JSON

Read student data from a CSV file using `csv.DictReader` and wrote it out as a JSON file using `json.dump`.

### NumPy Basics

Created a NumPy array and calculated the mean, max, and min.

### Lists vs NumPy Arrays

Compared multiplying a plain Python list by 2 against multiplying a NumPy array by 2, to show the difference between list repetition and element-wise array operations.

## 2. Deliverable: Data Processing Script

`week-2-deliverable.py` reads student records from `students.csv`, calculates a summary, and writes the cleaned data to `profile.json`.

### Features

- Reads `students.csv` using `csv.DictReader`
- Converts `age` and `marks` fields from text to integers
- Calculates the average marks across all students
- Finds the top student by marks
- Writes the cleaned student records to `profile.json`
- Uses `pathlib.Path` with `__file__` so the script finds `students.csv` and writes `profile.json` in the same folder, regardless of which directory it is run from
- Exits with a message if `students.csv` has no data

### How to Run

From inside the activated virtual environment, with `students.csv` in the same folder as the script:

```
cd Week-2
python week-2-deliverable.py
```

### Expected CSV Format

`students.csv` should have a header row with `name`, `age`, and `marks` columns, for example:

```
name,age,marks
Ridesha,22,88
Asha,21,92
Ram,20,75
Sita,19,85
```

### Example Output

```
Total Students: 4
Average Marks: 85.0
Top Student: Asha
JSON file created successfully
```

After running, `profile.json` will contain the same student records with `age` and `marks` stored as numbers instead of text.

## Notes

This week focused on moving from single scripts to working with structured data. The practice notebook covers the core Python data structures and a first look at NumPy, while the deliverable script combines file reading, data cleaning, basic calculations, and writing output to a new file. This builds directly on the functions and control flow practiced in Week 1, and sets up the file and data handling skills needed for the NLP work in Week 3.
