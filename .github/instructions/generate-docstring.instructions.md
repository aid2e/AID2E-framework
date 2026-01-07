---
applyTo: "*.py"
---
You are GPT-5. I will provide a Python file. Your task is to EDIT the file by adding or improving docstrings for all public functions, methods, classes, and modules.

## Hard rules
- Do NOT change runtime behavior.
- Do NOT change function signatures (names, args, defaults), unless required to fix a syntax error already present.
- Do NOT remove existing comments unless they are wrong; keep existing docstrings but improve them if needed.
- Keep formatting consistent and PEP8-friendly.
- If you add type hints, only do so when you are confident they’re correct and won’t break compatibility.
- If something is unclear from the code, state assumptions inside the docstring under “Notes”.

## Docstring format
Use Google-style docstrings consistently:

- One-line summary in imperative mood.
- Blank line.
- Longer description (optional).
- Args: (for each parameter)
- Returns: (if non-None)
- Raises: (only if the code clearly raises)
- Examples: (1 short example when helpful)
- Notes: (assumptions, edge cases)

## Coverage requirements
- Add a module docstring at the top if missing (purpose, key concepts, main entrypoints).
- Add docstrings to:
  - all top-level functions
  - all classes
  - all class methods (including `__init__`)
  - important internal/private helpers if they are non-trivial
- For tiny trivial helpers, add a short docstring only (1–2 lines).

## Output format
- Return the FULL UPDATED FILE CONTENTS as a single Python code block.
- Do not include explanations outside the code block unless there are important assumptions.
