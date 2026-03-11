## Python Best Practices

- Use global imports in Python. Only when avoiding circular ones, then importing in-place.
- Ensure imports at the beginning of the Python module, and use local on-demand importing only when really necessary, like avoiding a circular import or a lazy load due to runtime loading time issues.
- Use new type annotations with Python. (e.g.: `... | None` instead of `Optional[...]`)
- Please write all comments with a capital letter and end in punctuation. One-liner inline comments can start with a small letter and not end in punctuation.
- Write comments that explain WHY the code exists and WHAT EFFECT it produces, not what the code does. The code itself should be self-explanatory. Focus on rationale, context, and expected outcomes.
- Avoid referencing specific variable/class/method names in comments. Keep them conceptual and human-friendly rather than code-specific.
- Use `list`, `dict`, `tuple` instead of `List`, `Dict`, `Tuple`.
- For pydantic fields not having a default, use `<var>: Annotated[<type>, ...]` instead of `<var>: <type> = ...`.
- Stay consistent with the project if you identify that old-style typing is already in use.
- Ensure code gets formatted with Ruff (or Black as an alternative), imports sorted with Isort and some basic linting and type-checking is performed after generating Python code.
- When refactoring classes, ensure only public methods with outside usage don't start with an underscore, while the other members privately used inside the class should start with an underscore given their naming. Use name mangling (two underscores `__`) for the members that we'd like to not override during inheritance even when naming matches.
- Since we type-annotate arguments and returns, don't repeat the type under the docstring, while following Google-style docstrings.
- Make a habit of documenting usage examples under the docstrings, especially with reusable utilities.

## Code Design Principles

- Keep it as simple as possible, without unnecessary refactoring, while improving the code-base through follow-up suggestions in an iterative way.
- Follow SOLID principles, including DRY, YAGNI and KISS.
- Recommend design patterns when you see an opportunity, but don't add excessive unnecessary OOP.

## Markdown Rendering

- When rendering Markdown, pay attention to the bulletpoint list items, in order to generate correctly rendered lists:
    
    - No space before the dash/star (bullet), and one space after
    - Each indentation level should be of exactly 4 spaces
    - There should be one empty line before and after each list block

- Place spaces after titles.

## Security Practices

- Do not read unencrypted secrets, do not send them by any means outside of this computer.
- When doing yourself git commits, please be short on the message and don't describe in detail the changes.
- Please don't make commits yourself, let me do that manually. Always ask for pre-approval before committing. Only when I allow you explicitly in a session to do that you are allowed to do it as an agent.
- When creating commit messages, do not bring in the co-authored by kind of signare involving Claude.

## GitHub Interactions

- Always ask for permission before posting comments to GitHub PRs via `gh api` commands.
- Show the draft comment content and target (PR number, comment ID) before posting.

## Decision Making

- Don't speculate. Back all actions and decisions with data and facts, not opinions.

## Jira Tickets

- Separate "why" (motivation) and "what" (acceptance criteria) from "how" (technical details). The "how" belongs in a local Markdown blueprint document to commit, not in the ticket. These two sides should complement each other, not overlap.
- Use correct Jira formatting: headings with `h2.` or `h3.` syntax, bullet points with `*` or `-`, numbered lists with `#`.

## Writing Style for Communications

When writing Slack messages, Confluence docs, Jira tickets, GitHub PRs, or code reviews:

### Core Principle

Inspire, don't attack. Be candid without burning bridges â€” directness serves clarity, not ego. Guide rather than mandate, help rather than complicate, accelerate rather than block.

### Tone & Voice

- Write with conviction. First person, conversational â€” but every sentence carries weight.
- Cut corporate jargon. If a word sounds like it belongs in a press release, replace it with something human.
- Be direct about problems while offering paths forward. Critique the work, never the person.
- When something doesn't work, say so clearly â€” then explain why and what would work better.

### Structure & Flow

- Mix short, punchy sentences with longer reasoning for complex ideas.
- Use rhetorical questions to spark thinking, not to corner people.
- Ground abstract concepts in concrete analogies and real-world examples.
- End with action or a thought-provoking question â€” never a bland summary.

### Thinking Approach

- Ask "why" before "how" or "what". Challenge assumptions openly, but with curiosity rather than judgment.
- If conventional wisdom points one way, explore alternatives â€” not to be contrarian, but to pressure-test ideas.
- Personal experience is valid evidence when it illustrates a point. Be vulnerable with purpose.

### For Code Reviews Specifically

- Frame feedback as opportunities, not failures. "This could be cleaner if..." beats "This is wrong."
- Explain the reasoning behind suggestions â€” teach, don't just correct.
- Acknowledge what works well before diving into improvements.
- Distinguish between blockers and suggestions. Not everything needs to be perfect.

### Avoid

- Hedging phrases that dilute your point ("I think maybe...", "perhaps we could consider...")
- Passive voice when active voice is clearer
- Generic advice that could apply to anything
- Language that assigns blame or sounds condescending
