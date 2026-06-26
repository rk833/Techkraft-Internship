# Week 3 - NLP Series (Customer Review Analysis)

## Project: Customer Review NLP Analysis

---

## Description

This project demonstrates a complete Natural Language Processing (NLP) workflow using customer review data. The goal is to process raw text, clean it, and extract meaningful insights such as sentiment and structure.

The project simulates a real-world use case where companies analyze customer feedback to understand user opinions and improve products or services.

This project marks the transition from basic Python data handling to real-world AI/NLP applications.

---

## Objectives

- Understand the fundamentals of Natural Language Processing (NLP)
- Learn how to clean and preprocess text data
- Apply tokenization, stop word removal, and lemmatization
- Perform sentiment analysis on real text data
- Convert unstructured text into structured insights

---

## Dataset

A simple dataset of customer reviews was used.

Each row contains a single review representing user feedback about a product or service.

---

## Project Structure

Week-3/
│
├── week-3-practice.ipynb
├── week-3-deliverables.ipynb
├── customer_reviews.csv
├── processed_reviews.csv
└── README.md

---

## Practice

In this section, I completed hands-on exercises to understand core NLP concepts step by step using Python and real text data.

---

### 1. Text Cleaning Practice

- Converted raw text to lowercase
- Removed punctuation and special characters
- Normalized messy text into clean format

---

### 2. Tokenization Practice

- Split sentences into individual words (tokens)
- Observed how text is broken into meaningful units
- Understood how punctuation affects token output

---

### 3. Stop Word Removal Practice

- Removed common words like "is", "the", "and"
- Focused only on meaningful words
- Improved quality of text for analysis

---

### 4. Stemming vs Lemmatization Practice

- Applied stemming to reduce words to root form
- Applied lemmatization to convert words into dictionary form
- Compared differences between both approaches

---

### 5. Part-of-Speech Tagging Practice

- Identified grammatical roles of words (noun, verb, adjective)
- Understood sentence structure from a linguistic perspective

---

### 6. Sentiment Analysis Practice

- Used TextBlob to analyze sentiment polarity
- Classified text as Positive or Negative
- Understood how machines interpret human opinions

---

### 7. Real Dataset Practice (Customer Reviews)

- Loaded customer review dataset from CSV
- Applied full NLP pipeline:
  - Text cleaning
  - Tokenization
  - Stop word removal
  - Lemmatization
  - Sentiment analysis

---

## Deliverables

- NLP notebook with complete preprocessing pipeline
- Processed dataset with sentiment scores
- Sentiment classification (Positive / Negative / Neutral)
- CSV output file with cleaned and processed data

---

## Workflow

The project follows a standard NLP pipeline:

### 1. Text Cleaning
- Convert text to lowercase
- Remove punctuation and special characters
- Normalize raw text

### 2. Tokenization
- Split text into words (tokens)
- Prepare text for further processing

### 3. Stop Word Removal
- Remove common words that do not add meaning
- Keep only important words

### 4. Lemmatization
- Convert words into their base dictionary form
- Reduce redundancy in text data

### 5. Sentiment Analysis
- Assign sentiment polarity score using TextBlob
- Classify reviews into Positive, Negative, or Neutral

---

## Output

The final output includes:

- Cleaned review text
- Tokenized words
- Filtered tokens
- Lemmatized words
- Sentiment scores
- Sentiment labels

---

## Tools and Libraries Used

- Python
- Pandas
- NLTK
- TextBlob
- Regular Expressions (re)

---

## Key Learnings

- How raw text is transformed into structured data
- Importance of preprocessing in NLP
- Difference between stemming and lemmatization
- How sentiment analysis works in real-world applications
- End-to-end NLP pipeline development

---

## Challenges Faced

- Handling noisy and unstructured text data
- Understanding differences between NLP techniques
- Interpreting sentiment polarity scores
- Working with multiple NLP libraries together

---

## Conclusion

This project provides a strong foundation in NLP workflows. It demonstrates how raw text can be cleaned, processed, and converted into meaningful insights.

This prepares the foundation for advanced topics like embeddings, vector search, and RAG systems in upcoming weeks.