# Automated Code Review System

## Overview

This project provides an automated way to review code changes in a GitLab workflow. It integrates directly with merge requests, analyzes code diffs, and posts structured feedback as comments.

The goal is to catch real issues early — such as logical errors, potential runtime problems, and risky changes — without focusing on formatting or style.

---

## How It Works

1. A merge request is created in GitLab
2. The CI pipeline runs automatically
3. The pipeline:

   * Fetches the target branch
   * Generates a diff of changes
   * Sends the diff to the review service
4. The backend processes the code and generates a report
5. The report is posted back as a comment on the merge request

---

## Features

* Automatic review on every merge request
* Detects issues based on actual code behavior (not style)
* Filters out false positives
* Structured report with:

  * Summary
  * Critical issues
  * Warnings
  * Recommendations
* Language detection based on file changes

---

## Tech Stack

**Backend**

* Python
* FastAPI
* LangGraph workflow
* LLM integration via Groq

**CI/CD**

* GitLab CI
* Node.js (for pipeline scripting)

---

## API

### POST `/review`

#### Request

```json
{
  "code": "diff content"
}
```

#### Response

```json
{
  "analysis": "High-level analysis",
  "issues": ["- [CRITICAL] ...", "- [WARNING] ..."],
  "report": "Formatted review report"
}
```

---

## Pipeline Integration

The GitLab pipeline:

* Fetches the target branch
* Generates a diff file
* Sends it to the review service
* Posts the response as a merge request comment

Example flow:

```bash
git fetch origin target-branch
git diff origin/target-branch > changes.diff
```

---

## Project Structure

* `app.py` — FastAPI service and review logic 
* CI pipeline — handles integration with GitLab
* Review agent — multi-step workflow:

  1. Code analysis
  2. Issue detection
  3. Validation
  4. Report generation

---

## Design Notes

* The system avoids style-based suggestions intentionally
* Only issues that can be justified from the code are reported
* Validation step removes weak or incorrect findings
* Output is kept concise for readability in merge requests

---

## Limitations

* Depends on diff quality (large diffs may reduce accuracy)
* Language detection is heuristic-based
* Not a replacement for human review, but a supplement

---

## Future Improvements

* Support for more languages and frameworks
* Inline comments instead of a single report
* Improved diff parsing
* Custom rule configuration

---

## Usage

1. Deploy the backend service
2. Add the GitLab CI configuration
3. Set environment variables:

   * `GITLAB_TOKEN`
   * `GROQ_API_KEY`
4. Create a merge request

The review will be posted automatically.

---

## License

This project is intended for educational and internal use.
