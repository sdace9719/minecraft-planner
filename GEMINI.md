## General Guidelines

- If there are any existing frameworks or libraries, it's best to use them if they easily fit the use case, instead of re-inventing the wheel.
- Any test case files i ask to create should not be removed without permission
- Aim for functions that only perform one particular functions. It's better to have many functions rather than one function with everything. A good rule to follow is a function's task cannot be described in 100 characters its probably doing a lot of things which can be modularized into other functions.
- Aim for the code files to be small. This may lead to increased number of files but don't create files unecessary and when not asked. only create when necessary. if its not asked, do not create useless files like claude
- directory structures is important. it's better to organize code under relevant directory names. it helps keep root folder organized.

## Setup Environment

- use uv
- for dependencies use pyproject.toml and create env with uv sync
- Most commands then can use 'uv run' after sync is complete

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```