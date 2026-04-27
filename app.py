from typing import TypedDict, List, Dict
from langchain_groq import ChatGroq
import os
import re
import logging
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_CODE_LENGTH = 50_000  # characters

app = FastAPI()

allowed_origins = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


class CodeReviewRequest(BaseModel):
    code: str


class CodeReviewState(TypedDict):
    code: str
    language: str
    initial_analysis: str
    issues: List[str]
    final_report: str


def _detect_language(code: str) -> str:
    """Detect the programming language from diff file paths or code patterns."""

    diff_files = re.findall(r'\+\+\+ b/.*\.(\w+)', code)

    extension_map = {
        "py": "Python", "js": "JavaScript", "ts": "TypeScript",
        "jsx": "React JSX", "tsx": "React TSX", "java": "Java",
        "go": "Go", "rs": "Rust", "rb": "Ruby", "php": "PHP",
        "cs": "C#", "cpp": "C++", "c": "C", "swift": "Swift",
        "kt": "Kotlin", "yml": "YAML", "yaml": "YAML",
        "sql": "SQL", "sh": "Shell", "html": "HTML", "css": "CSS",
    }

    for ext in diff_files:
        if ext.lower() in extension_map:
            return extension_map[ext.lower()]

    # Fallback: detect from code patterns
    if "def " in code and "import " in code:
        return "Python"
    if "function " in code or ("const " in code and "=>" in code):
        return "JavaScript"
    if "func " in code and "package " in code:
        return "Go"
    if "public class " in code or "private void " in code:
        return "Java"

    return "Unknown"


def _compute_issue_count(code: str) -> str:
    """Return a proportional issue count range based on diff size."""
    line_count = code.count("\n")
    if line_count < 20:
        return "1-2"
    elif line_count < 100:
        return "2-4"
    elif line_count < 300:
        return "3-5"
    else:
        return "5-8"


class SimpleCodeReviewAgent:
    def __init__(self):
        self.llm = ChatGroq(
            api_key=os.getenv("GROQ_API_KEY"),
            model="llama-3.3-70b-versatile",
            temperature=0
        )
        self.graph = self._build_graph()

    def _analysis_agent(self, state: CodeReviewState) -> Dict:
        """Step 1: High-level analysis of the code."""
        language = state.get("language", "Unknown")

        prompt = f"""Analyse the following {language} code diff briefly:
{state['code']}

Focus on:
- Purpose of the change
- Code structure
- Potential risks
"""
        try:
            response = self.llm.invoke(prompt)
            return {"initial_analysis": response.content}
        except Exception as e:
            logger.error(f"Analysis agent failed: {e}")
            raise RuntimeError(f"LLM analysis failed: {e}")

    def _find_issues(self, state: CodeReviewState) -> Dict:
        """Step 2: Find real issues — no style nits."""
        language = state.get("language", "Unknown")
        issue_count = _compute_issue_count(state["code"])

        prompt = f"""You are a senior {language} code reviewer.

Code:
{state['code']}

Prior analysis:
{state['initial_analysis']}

RULES:
- Only report REAL issues: runtime errors, security flaws, logical bugs, data flow problems, type mismatches.
- DO NOT report: style suggestions, naming improvements, formatting, or missing comments.
- Be specific — reference the exact line or pattern causing the issue.

Return {issue_count} issues in this format:
- [CRITICAL] description
- [WARNING] description
"""
        try:
            response = self.llm.invoke(prompt)
            issues = [line.strip() for line in response.content.split(
                '\n') if line.strip().startswith('-')]
            return {"issues": issues}
        except Exception as e:
            logger.error(f"Issue finder failed: {e}")
            raise RuntimeError(f"LLM issue detection failed: {e}")

    def _validate_issues(self, state: CodeReviewState) -> Dict:
        """Step 3: Filter out false positives and generic advice."""
        prompt = f"""You are validating code review findings.

Code:
{state['code']}

Reported issues:
{chr(10).join(state['issues'])}

TASK:
- Remove any issue that is generic advice, not provable from the code.
- Remove any issue that is factually incorrect.
- Correct severity labels if wrong.
- Keep only issues backed by evidence in the code.

Return the cleaned list in the same format:
- [CRITICAL] description
- [WARNING] description
"""
        try:
            response = self.llm.invoke(prompt)
            issues = [line.strip() for line in response.content.split(
                '\n') if line.strip().startswith('-')]
            return {"issues": issues if issues else state["issues"]}
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return {"issues": state["issues"]}

    def _generate_report(self, state: CodeReviewState) -> Dict:
        """Step 4: Generate the final review report."""
        language = state.get("language", "Unknown")
        issues_text = '\n'.join(state['issues'])

        prompt = f"""Generate a concise {language} code review report.

Validated issues:
{issues_text}

FORMAT:
## Summary
(max 3 lines — what the code does and overall quality)

## Critical Issues
(list only [CRITICAL] items, or "None" if empty)

## Warnings
(list only [WARNING] items, or "None" if empty)

## Recommendations
(1-2 actionable next steps based on the issues above)

DO NOT include generic advice. Only reference findings from the issues list.
"""
        try:
            response = self.llm.invoke(prompt)
            return {"final_report": response.content}
        except Exception as e:
            logger.error(f"Report generator failed: {e}")
            raise RuntimeError(f"LLM report generation failed: {e}")

    def _build_graph(self) -> StateGraph:
        """Build the 4-step langgraph workflow."""
        workflow = StateGraph(CodeReviewState)

        workflow.add_node("analyzer", self._analysis_agent)
        workflow.add_node("issue_finder", self._find_issues)
        workflow.add_node("validator", self._validate_issues)
        workflow.add_node("report_generator", self._generate_report)

        workflow.set_entry_point("analyzer")
        workflow.add_edge("analyzer", "issue_finder")
        workflow.add_edge("issue_finder", "validator")
        workflow.add_edge("validator", "report_generator")
        workflow.add_edge("report_generator", END)

        return workflow.compile()


agent = SimpleCodeReviewAgent()


@app.post("/review")
def review_code(request: CodeReviewRequest):
    if not request.code or not request.code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty.")

    if len(request.code) > MAX_CODE_LENGTH:
        raise HTTPException(
            status_code=413,
            detail=f"Code too large. Maximum {MAX_CODE_LENGTH} characters allowed."
        )

    language = _detect_language(request.code)
    logger.info(
        f"Detected language: {language}, diff size: {len(request.code)} chars")

    initial_state = {
        "code": request.code,
        "language": language,
        "initial_analysis": "",
        "issues": [],
        "final_report": ""
    }

    try:
        result = agent.graph.invoke(initial_state)
    except Exception as e:
        logger.error(f"Review pipeline failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Review failed: {str(e)}")

    return {
        "analysis": result["initial_analysis"],
        "issues": result["issues"],
        "report": result["final_report"]
    }
