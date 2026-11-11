# 1. Experimental group (Ours: coverage + RE Pre-processed)
CODEACT_TESTGEN_PROMPT_WITH_RE = """
Your goal is to generate a comprehensive, **broad-coverage** test suite for the code below.

IMPORTANT REQUIREMENTS:
1. **No external help or resources**—use only the snippet below and the tools provided.
2. **Focus on breadth over depth**: cover all major functions, classes, and code paths early to minimize coverage iterations.
3. Each test function must start with `test_` and use `assert` to verify behavior.
4. Include only necessary imports (standard library or local).
5. **CRITICAL FOR COVERAGE**: Always import the specific target functions or classes being tested **locally inside each test function**. NOT at the top of the file. This prevents early ImportErrors and ensures proper coverage tracking.
6. Do **not** modify existing test files—create a brand new one. No `main()` or other non-test code.
7. Produce **at least 20 test functions**; if coverage is lacking, add more tests rather than removing or changing existing ones.

**YOUR WORKFLOW MUST BE EXACTLY AS FOLLOWS:**

**STEP 1: REVIEW THE ANALYSIS (MANDATORY FIRST ACTION)**
Read the **REQUIREMENTS ENGINEERING & STATIC ANALYSIS HINTS** provided at the top of this message.
It acts as your API contract/Specification. Pay special attention to the `RAISES EXCEPTIONS` lines—you MUST write tests that explicitly trigger these exceptions.
**NOTE**: The static extraction tool has already been run. You only need to run the coverage tool in STEP 3.

**STEP 2: WRITE THE TEST SUITE**
Based on the extracted specifications, write your tests and place them in `{test_file}`.
**IMPORTANT**: Do NOT try to write the entire file in one go if it is very large. Use file editing tools or `cat` to write/append incrementally to avoid JSON parsing errors.

**STEP 3: ITERATE ON COVERAGE & REPAIR**
Use the following command to run tests, check coverage, and get AST-guided hints for missed branches:
<execute_bash>
{analysis_command}
</execute_bash>
- **IF TESTS FAIL (E or F)**: You MUST read the traceback and REPAIR the broken tests immediately before trying to increase coverage.
- **IF COVERAGE IS LACKING**: Look at the hints and APPEND new test functions specifically targeting those missed lines/branches.

**STEP 4: FINAL SUBMISSION**
Once satisfied, verify all tests pass and finish the task by running:
<execute_bash> exit </execute_bash>

Below is the **complete code snippet** to test:
<START_OF_CODE>
{code_src}
<END_OF_CODE>

NOTE: If you are testing django, use `from django.test import SimpleTestCase` and class-based tests.
NOTE: Do NOT install new packages.
NOTE: NEVER output the full revised test suite in a single tool call. Always modify the file on disk incrementally.

**FINAL SUBMISSION**:
You DO NOT need to print or output the final test suite code in our conversation. 
Just ensure the final test code is fully and correctly written to `{test_file}` on the disk. 
Once you have verified the tests pass and the coverage is satisfactory, simply finish the task by running:
<execute_bash> exit </execute_bash>
"""

# 2. Control group (Baseline: only coverage)
CODEACT_TESTGEN_PROMPT_BASELINE = """
Your goal is to generate a comprehensive, **broad-coverage** test suite for the code below, ensuring you test as many lines and branches as possible on the first attempt.

Place your test suite in a new file named {test_file}.

IMPORTANT REQUIREMENTS:
1. **No external help or resources**—use only the snippet below.
2. **Focus on breadth over depth**: cover all major functions, classes, and code paths early to minimize coverage iterations.
3. Each test function must start with `test_` and use `assert` to verify behavior.
4. Include only necessary imports (standard library or local).
5. **CRITICAL FOR COVERAGE**: Always import the specific target functions or classes being tested **locally inside each test function**. NOT at the top of the file. This prevents early ImportErrors and ensures proper coverage tracking.
6. Do **not** modify existing test files—create a brand new one. No `main()` or other non-test code.
7. Produce **at least 20 test functions**; if coverage is lacking, add more tests rather than removing or changing existing ones.
8. Use the following command to check coverage (it includes a specialized analysis tool):
   <execute_bash>
   {analysis_command}
   </execute_bash>
   - The tool will output **[MISSING LOGIC]** blocks with hints.
   - **Action**: Read the hints, and add new test functions to cover those lines.
9. When you're satisfied with coverage, finalize by running:
   <execute_bash> exit </execute_bash>

Below is the **complete code snippet** to test:

<START_OF_CODE>
{code_src}
<END_OF_CODE>

NOTE: if you are testing django, you must use from django.test import SimpleTestCase and class based tests (i.e. class TestSomething(SimpleTestCase)).
NOTE: if there is an error executing tests you MUST fix it before exiting. DO NOT install new packages.
NOTE: if outputting a revised test suite REPLACE {test_file} with the revised suite.

**FINAL SUBMISSION**:
You DO NOT need to print or output the final test suite code in our conversation. 
Just ensure the final test code is fully and correctly written to `{test_file}` on the disk. 
Once you have verified the tests pass and the coverage is satisfactory, simply finish the task by running:
<execute_bash> exit </execute_bash>
"""


# 3. Full system (Full Matrix: RE + Semantic Memory)
CODEACT_TESTGEN_PROMPT_FULL_MATRIX = """
Your goal is to generate a comprehensive, **broad-coverage** test suite for the code below.

IMPORTANT REQUIREMENTS:
1. **No external help or resources**—use only the snippet below and the tools provided.
2. **Focus on breadth over depth**: cover all major functions, classes, and code paths early to minimize coverage iterations.
3. Each test function must start with `test_` and use `assert` to verify behavior.
4. Include only necessary imports (standard library or local).
5. **CRITICAL FOR COVERAGE**: Always import the specific target functions or classes being tested **locally inside each test function**. NOT at the top of the file. This prevents early ImportErrors and ensures proper coverage tracking.
6. Do **not** modify existing test files—create a brand new one. No `main()` or other non-test code.
7. Produce **at least 20 test functions**; if coverage is lacking, add more tests rather than removing or changing existing ones.

**YOUR WORKFLOW MUST BE EXACTLY AS FOLLOWS:**

**STEP 1: REVIEW THE ANALYSIS (MANDATORY FIRST ACTION)**
Read the **REQUIREMENTS ENGINEERING & STATIC ANALYSIS HINTS** provided at the top of this message.
It acts as your API contract/Specification. Pay special attention to the `RAISES EXCEPTIONS` lines—you MUST write tests that explicitly trigger these exceptions.

**STEP 2: WRITE THE TEST SUITE**
Based on the extracted specifications AND your historical memory rules, write your tests and place them in `{test_file}`.
**IMPORTANT**: Do NOT try to write the entire file in one go if it is very large. Use file editing tools or `cat` to write/append incrementally to avoid JSON parsing errors.

**STEP 3: ITERATE ON COVERAGE & REPAIR**
Use the following command to run tests, check coverage, and get AST-guided hints for missed branches:
<execute_bash>
{analysis_command}
</execute_bash>
- **IF TESTS FAIL (E or F)**: You MUST read the traceback and REPAIR the broken tests immediately before trying to increase coverage.
- **IF COVERAGE IS LACKING**: Look at the hints and APPEND new test functions specifically targeting those missed lines/branches.

**STEP 4: FINAL SUBMISSION**
Once satisfied, verify all tests pass and finish the task by running:
<execute_bash> exit </execute_bash>

Below is the **complete code snippet** to test:
<START_OF_CODE>
{code_src}
<END_OF_CODE>

CRITICAL: The following insights are extracted from your own successful experiences in this repository. PRIORITIZE these rules over any general assumptions.
{memory_hints}

NOTE: If you are testing django, use `from django.test import SimpleTestCase` and class-based tests.
NOTE: Do NOT install new packages.
NOTE: NEVER output the full revised test suite in a single tool call. Always modify the file on disk incrementally.

**FINAL SUBMISSION**:
You DO NOT need to print or output the final test suite code in our conversation.
Just ensure the final test code is fully and correctly written to `{test_file}` on the disk.
Once you have verified the tests pass and the coverage is satisfactory, simply finish the task by running:
<execute_bash> exit </execute_bash>
"""

# 4. Iterative loop (Iterate Prompt)
CODEACT_TESTGEN_PROMPT_ITERATE = """
Goal: Improve coverage for `{test_file}`.
**CURRENT STATUS**
- You have existing tests.
- Some logic might still be missing, or some tests might be failing.

**YOUR TASK**
1.  Run the analysis command:
    <execute_bash>
    {analysis_command}
    </execute_bash>
2.  **MANDATORY REPAIR**: If the analysis command output shows that tests are failing (Errors or Failures), you MUST read the traceback and FIX the broken tests. Do NOT comment them out. Broken tests destroy coverage tracking.
3.  **IMPROVE COVERAGE**: Read the [MISSING LOGIC] report (if tests passed).
4.  **APPEND** new test functions to `{test_file}` to cover the missing lines.
    - Use `cat <<'EOF' >> {test_file}` via `execute_bash` for large updates.
    - You MAY use `str_replace_editor` for small edits (<=50 lines).
    - **DO NOT REWRITE** the existing file entirely to prevent JSON parsing errors.

<START_OF_CODE>
{code_src}
<END_OF_CODE>
"""

# 5. Ablation study prompt templates

# Variant 1: Ours (Full System) - includes all features
CODEACT_TESTGEN_PROMPT_OURS_FULL = CODEACT_TESTGEN_PROMPT_FULL_MATRIX

# Variant 2: Ours w/o Memory - no memory system
CODEACT_TESTGEN_PROMPT_WO_BOTH_MEMORIES = CODEACT_TESTGEN_PROMPT_WITH_RE

# Variant 3: Ours w/o Dynamic Feedback - no dynamic coverage feedback
CODEACT_TESTGEN_PROMPT_WO_COVERAGE_GUIDED_FEEDBACK = """
Your goal is to generate a comprehensive, **broad-coverage** test suite for the code below.

IMPORTANT REQUIREMENTS:
1. **No external help or resources**—use only the snippet below and the tools provided.
2. **Focus on breadth over depth**: cover all major functions, classes, and code paths early to minimize coverage iterations.
3. Each test function must start with `test_` and use `assert` to verify behavior.
4. Include only necessary imports (standard library or local).
5. **CRITICAL FOR COVERAGE**: Always import the specific target functions or classes being tested **locally inside each test function**. NOT at the top of the file. This prevents early ImportErrors and ensures proper coverage tracking.
6. Do **not** modify existing test files—create a brand new one. No `main()` or other non-test code.
7. Produce **at least 20 test functions**; if coverage is lacking, add more tests rather than removing or changing existing ones.

**YOUR WORKFLOW MUST BE EXACTLY AS FOLLOWS:**

**STEP 1: REVIEW THE ANALYSIS (MANDATORY FIRST ACTION)**
Read the **REQUIREMENTS ENGINEERING & STATIC ANALYSIS HINTS** provided at the top of this message.
It acts as your API contract/Specification. Pay special attention to the `RAISES EXCEPTIONS` lines—you MUST write tests that explicitly trigger these exceptions.

**STEP 2: WRITE THE TEST SUITE**
Based on the extracted specifications AND your historical memory rules, write your tests and place them in `{test_file}`.
Use file editing tools or `cat` to write/append incrementally to avoid JSON parsing errors.

**STEP 3: CHECK COVERAGE & REPAIR**
Use the following commands to check coverage:
   <execute_bash> {coverage_command} </execute_bash>
   <execute_bash> coverage report -m --include {code_file} </execute_bash>
- **IF TESTS FAIL (E or F)**: You MUST read the traceback and REPAIR the broken tests immediately before trying to increase coverage.
- **IF COVERAGE IS LACKING**: If lines remain uncovered, add new tests targeting them specifically.

**STEP 4: FINAL SUBMISSION**
Once satisfied, verify all tests pass and finish the task by running:
<execute_bash> exit </execute_bash>

Below is the **complete code snippet** to test:
<START_OF_CODE>
{code_src}
<END_OF_CODE>

CRITICAL: The following insights are extracted from your own successful experiences in this repository. PRIORITIZE these rules over any general assumptions.
{memory_hints}

NOTE: If you are testing django, use `from django.test import SimpleTestCase` and class-based tests.
NOTE: Do NOT install new packages.
NOTE: NEVER output the full revised test suite in a single tool call. Always modify the file on disk incrementally.

**FINAL SUBMISSION**:
You DO NOT need to print or output the final test suite code in our conversation. 
Just ensure the final test code is fully and correctly written to `{test_file}` on the disk. 
Once you have verified the tests pass and the coverage is satisfactory, simply finish the task by running:
<execute_bash> exit </execute_bash>
"""

# Variant 4: Ours w/o Static Requirement - no static requirements constraint
CODEACT_TESTGEN_PROMPT_WO_STRUCTURAL_ANALYSIS = """
Your goal is to generate a comprehensive, **broad-coverage** test suite for the code below.

IMPORTANT REQUIREMENTS:
1. **No external help or resources**—use only the snippet below and the tools provided.
2. **Focus on breadth over depth**: cover all major functions, classes, and code paths early to minimize coverage iterations.
3. Each test function must start with `test_` and use `assert` to verify behavior.
4. Include only necessary imports (standard library or local).
5. **CRITICAL FOR COVERAGE**: Always import the specific target functions or classes being tested **locally inside each test function**. NOT at the top of the file. This prevents early ImportErrors and ensures proper coverage tracking.
6. Do **not** modify existing test files—create a brand new one. No `main()` or other non-test code.
7. Produce **at least 20 test functions**; if coverage is lacking, add more tests rather than removing or changing existing ones.

**YOUR WORKFLOW MUST BE EXACTLY AS FOLLOWS:**

**STEP 1: WRITE THE TEST SUITE**
Based on the provided source code AND your historical memory rules, write your tests and place them in `{test_file}`.
**IMPORTANT**: Do NOT try to write the entire file in one go if it is very large. Use file editing tools or `cat` to write/append incrementally to avoid JSON parsing errors.

**STEP 2: ITERATE ON COVERAGE & REPAIR**
Use the following command to run tests, check coverage, and get AST-guided hints for missed branches:
<execute_bash>
{analysis_command}
</execute_bash>
- **IF TESTS FAIL (E or F)**: You MUST read the traceback and REPAIR the broken tests immediately before trying to increase coverage.
- **IF COVERAGE IS LACKING**: Look at the hints and APPEND new test functions specifically targeting those missed lines/branches.

**STEP 3: FINAL SUBMISSION**
Once satisfied, verify all tests pass and finish the task by running:
<execute_bash> exit </execute_bash>

Below is the **complete code snippet** to test:
<START_OF_CODE>
{code_src}
<END_OF_CODE>

CRITICAL: The following insights are extracted from your own successful experiences in this repository. PRIORITIZE these rules over any general assumptions.
{memory_hints}

NOTE: If you are testing django, use `from django.test import SimpleTestCase` and class-based tests.
NOTE: Do NOT install new packages.
NOTE: NEVER output the full revised test suite in a single tool call. Always modify the file on disk incrementally.

**FINAL SUBMISSION**:
You DO NOT need to print or output the final test suite code in our conversation. 
Just ensure the final test code is fully and correctly written to `{test_file}` on the disk. 
Once you have verified the tests pass and the coverage is satisfactory, simply finish the task by running:
<execute_bash> exit </execute_bash>
"""



# REB (Repo Exploration Benchmark)
CODEACT_TESTGEN_PROMPT_FULL_MATRIX_REB = """
Your goal is to generate a comprehensive, **broad-coverage** test suite for the code below.

IMPORTANT REQUIREMENTS:
1. **No external help or resources**—use only the snippet below and the tools provided.
2. **Focus on breadth over depth**: cover all major functions, classes, and code paths early to minimize coverage iterations.
3. Each test function must start with `test_` and use `assert` to verify behavior.
4. Include only necessary imports (standard library or local).
5. **CRITICAL FOR COVERAGE**: Always import the specific target functions or classes being tested **locally inside each test function**. NOT at the top of the file. This prevents early ImportErrors and ensures proper coverage tracking.
6. Do **not** modify existing test files—create a brand new one. No `main()` or other non-test code.
7. Produce **at least 20 test functions**; if coverage is lacking, add more tests rather than removing or changing existing ones.

**YOUR WORKFLOW MUST BE EXACTLY AS FOLLOWS:**

**STEP 1: REVIEW THE ANALYSIS (MANDATORY FIRST ACTION)**
Read the **REQUIREMENTS ENGINEERING & STATIC ANALYSIS HINTS** provided at the top of this message.
It acts as your API contract/Specification. Pay special attention to the `RAISES EXCEPTIONS` lines—you MUST write tests that explicitly trigger these exceptions.

**STEP 2: WRITE THE TEST SUITE**
Based on the extracted specifications AND your historical memory rules, write your tests and place them in `{test_file}`.
**IMPORTANT**: Do NOT try to write the entire file in one go if it is very large. Use file editing tools or `cat` to write/append incrementally to avoid JSON parsing errors.

**STEP 3: ITERATE ON COVERAGE & REPAIR**
Use the following command to run tests, check coverage, and get AST-guided hints for missed branches:
<execute_bash>
{analysis_command}
</execute_bash>
- **IF TESTS FAIL (E or F)**: You MUST read the traceback and REPAIR the broken tests immediately before trying to increase coverage.
- **IF COVERAGE IS LACKING**: Look at the hints and APPEND new test functions specifically targeting those missed lines/branches.

**STEP 4: FINAL SUBMISSION**
Once satisfied, verify all tests pass and finish the task by running:
<execute_bash> exit </execute_bash>

Below is the **complete code snippet** to test:
<START_OF_CODE>
{code_src}
<END_OF_CODE>

CRITICAL: The following insights are extracted from your own successful experiences in this repository. PRIORITIZE these rules over any general assumptions.
{memory_hints}

NOTE: If you are testing django, use `from django.test import SimpleTestCase` and class-based tests.
NOTE: Do NOT install new packages.
NOTE: NEVER output the full revised test suite in a single tool call. Always modify the file on disk incrementally.

**FINAL SUBMISSION & CRITICAL REQUIREMENT**:
You DO NOT need to print or output the final test suite code in our conversation.
Just ensure the final test code is fully and correctly written to `{test_file}` on the disk. Do not use any other filename. The evaluation framework will specifically look for this file to score your performance.
Once you have verified the tests pass and the coverage is satisfactory, simply finish the task by running:
<execute_bash> exit </execute_bash>
"""

EXPEREPAIR_HINT_TEMPLATE = """
==============================================================
!!! CRITICAL MEMORY INJECTION: REPOSITORY SURVIVAL RULES !!!
==============================================================
[WARNING]: The following rules are extracted from FATAL FAILURES in previous attempts.
Ignoring them guarantees exactly 0% coverage and task failure.

{}

==============================================================
"""

# Memory distillation and reflection prompts
SUMMARIZER_PROMPT = """
You are an expert Python QA Engineer and System Architect.
We have just successfully generated a passing test suite for the repository: **{repo_name}**.

Here is the target source code we were testing:
```python
{code_src}
```

Here is the final, successful test code that achieved high coverage (>= 80%) and passed all assertions:
```python
{test_code}
```

YOUR TASK:
Analyze the successful test code and infer the "Root Cause" of why naive attempts might fail, and the "Critical Fix" that made this succeed.
Reflect on the contrast between a standard/naive approach and what was actually required here.

Critical Analysis Rule for 0% Coverage:
If the test coverage is exactly 0%, or if Pytest reports "collected 0 items", DO NOT look for logical bugs. You MUST look for Framework Structural Failures. Check if the agent wrapped the tests in a class instead of using standalone def test_...() functions, or if it missed the test_ prefix. Extract these structural mistakes as top-priority Pitfalls.

Classify your insights into these categories:

Convention: Mandatory coding styles or patterns.

Pitfall: Specific traps or errors to avoid (Root Cause).

Setup: Critical mocking or initialization steps (Critical Fix).

OUTPUT FORMAT:
You MUST output a valid JSON array of strings. Each string must start with "Convention:", "Pitfall:", or "Setup:".
If your insight is about code structure or test formatting (e.g., prohibiting classes), you MUST format your string using this template (replace the bracketed parts with your analysis):
'Convention: STRICTLY FORBIDDEN to use <Bad Pattern>. [FATAL PATTERN]: <Example> [REQUIRED PATTERN]: <Example>'

DO NOT output any markdown formatting (like ```json), just the raw JSON array.

CRITICAL JSON ESCAPING RULE:
Because your insights will contain LaTeX and regex (e.g., \\sin, \\begin), you MUST double-escape ALL backslashes to output valid JSON.
Example: You must output "\\\\sin" instead of "\\sin".
Example: You must output "\\\\begin{{equation}}" instead of "\\begin{{equation}}".
Failure to double-escape will crash the JSON parser.
"""

DUAL_TRACK_SUMMARIZER_PROMPT = """
You are an expert AI Agent Behavior Analyst and Test Framework Architect.
We have just completed a test generation task for the repository: **{repo_name}**.

Target source code:
```python
{code_src}
```

Final test code:
```python
{test_code}
```

Agent Trajectory (Errors & Fixes):
<AGENT_TRAJECTORY>
{trajectory}
</AGENT_TRAJECTORY>

YOUR TASK:
Extract TWO strictly separated types of knowledge into a JSON object:

"static_conventions": Strict structural framework rules specific to this repository.

ONLY include: testing framework (pytest/unittest), class vs bare def requirements, mandatory decorators, or base class inheritance.

MUST start with "Convention: ".

DO NOT include any mocking strategies, business logic, or general python tips here.

"dynamic_insights": Cross-repo debugging experiences and root-cause solutions derived from the trajectory.

Explain the pitfall and the actionable fix.

DO NOT use prefixes like "Pitfall:" or "Setup:" or "Convention:". Write pure, actionable debug steps.

DO NOT include any Case IDs or IDs inside the string. Write pure, actionable debug steps.

OUTPUT FORMAT (JSON ONLY, double-escape backslashes):
{{
  "static_conventions": [
    "Convention: Tests must use bare functions (def), not classes."
  ],
  "dynamic_insights": [
    "When patching os.environ, always use mock.patch.dict instead of mutating directly."
  ]
}}
"""

BASE_DYNAMIC_MEMORY_EXTRACTION_PROMPT = """
You are an expert AI Agent Behavior Analyst and Test Framework Architect.
We have just analyzed a test generation trajectory for the repository: **{repo_name}**.

TEST EXECUTION RESULT:
- Pass/Fail Status: {test_status}
- Final Coverage: {coverage}

Target source code:
```python
{code_src}
```

Final test code:
```python
{test_code}
```

Agent Trajectory (Specific Aha-Moments & Fixes):
<AGENT_TRAJECTORY>
{trajectory}
</AGENT_TRAJECTORY>

YOUR TASK:
Extract dynamic debugging knowledge into a JSON object based on the trajectory provided.

"dynamic_insights": Cross-repo debugging experiences derived STRICTLY from the specific errors and fixes in the <AGENT_TRAJECTORY>.

*** CRITICAL GUARDRAILS ***

CRITICAL: You must ABSTRACT task-specific details. DO NOT include specific file paths (e.g., sympy/physics/.../test_foo.py ), specific variable names, or hardcoded line numbers.

Instead, use general architectural terms like <module_test_directory> , <relevant_class> , or <target_function> .

Focus strictly on the underlying engineering principle, framework convention, or structural rule.

ZERO HALLUCINATION RULE: If the <AGENT_TRAJECTORY> does NOT contain explicit "[Encountered Error]" and "[Agent Fix Actions]" blocks (e.g., it only says "Global Result: Agent successfully generated..."), YOU MUST RETURN AN EMPTY ARRAY [] for "dynamic_insights". DO NOT guess, infer, or reverse-engineer pitfalls from the source code.

NO PREFIXES RULE: When writing dynamic insights, combine the problem and solution into a single fluid, actionable sentence. ABSOLUTELY DO NOT use prefixes like "Pitfall:", "Fix:", "Problem:", or "Solution:".

OUTPUT FORMAT (JSON ONLY):
{{
 "static_conventions": [],
 "dynamic_insights": [ ... ]
}}
"""

EXTRA_STATIC_MEMORY_EXTRACTION_PROMPT = """
Additionally extract static repository conventions into "static_conventions".

"static_conventions": Strict structural framework rules specific to this repository (e.g., pytest vs unittest, mock usage). MUST start with "Convention: ".

*** CRITICAL NEGATIVE CONSTRAINTS RULE ***
When extracting structural rules (like test formats or framework usage), you MUST generate strict NEGATIVE CONSTRAINTS to override default LLM biases. Identify the repository's paradigm and explicitly forbid the opposing paradigm:
- If the repo uses bare functions (pytest style), explicitly write: "DO NOT wrap tests in classes. DO NOT use unittest."
- If the repo uses OOP class-based tests, explicitly write: "DO NOT write bare functions. MUST use classes."
Your rules must be aggressive and prohibitive.

QUALITY GATE FOR CONVENTIONS: If the "Final Coverage" is "0%" or the "Pass/Fail Status" indicates "0 passed", it means the agent FAILED to generate a valid testing structure. In this case, YOU MUST RETURN AN EMPTY ARRAY [] FOR "static_conventions". DO NOT extract the agent's actions as a "static_conventions" (because it is wrong!).

When static conventions are requested, output format remains:
{{
 "static_conventions": [ ... ],
 "dynamic_insights": [ ... ]
}}
"""

CAUSAL_MEMORY_EXTRACTION_PROMPT = (
    BASE_DYNAMIC_MEMORY_EXTRACTION_PROMPT + "\n" + EXTRA_STATIC_MEMORY_EXTRACTION_PROMPT
)

CRITIC_PROMPT = """
You are a strict test-quality critic focused on identifying why a generated test suite failed to satisfy execution or coverage requirements for repository: {repo_name}.

Here is the target source code:
```python
{code_src}
```

Here is the generated test code:
```python
{test_code}
```

Here is the failure context (execution traces, failing assertions, or coverage diagnostics):
{failure_context}

YOUR TASK:
Extract compact, reusable failure reflections that can prevent the same failure pattern in future attempts.
Focus on:

Convention: Mandatory structure and formatting constraints.

Pitfall: Root causes behind failures and anti-patterns that must be avoided.

Setup: Missing setup or mocking steps that are required.

OUTPUT FORMAT:
You MUST output a valid JSON array of strings. Each string must start with "Convention:", "Pitfall:", or "Setup:".
If your insight is about code structure or test formatting (e.g., prohibiting classes), you MUST format your string using this template (replace the bracketed parts with your analysis):
'Convention: STRICTLY FORBIDDEN to use <Bad Pattern>. [FATAL PATTERN]: <Example> [REQUIRED PATTERN]: <Example>'

DO NOT output any markdown formatting (like ```json), just the raw JSON array.

CRITICAL JSON ESCAPING RULE:
Because your insights will contain LaTeX and regex (e.g., \\sin, \\begin), you MUST double-escape ALL backslashes to output valid JSON.
Example: You must output "\\\\sin" instead of "\\sin".
Example: You must output "\\\\begin{{equation}}" instead of "\\begin{{equation}}".
Failure to double-escape will crash the JSON parser.
"""
