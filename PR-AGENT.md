## PR Agent Guidance

You are reviewing **only the changes in this pull request**. Focus on correctness, safety, and maintainability.

This file is **project-level guidance** intended to stay stable across PRs.

### Pre-Review Steps

Follow these steps **before reviewing any code**:

1. **Read the full PR description** to establish context for the changes.
2. **Check for an "Agent Notes" section** in the description.
   - If present: these instructions take priority for this review (unless they conflict with repo guardrails or security/correctness). Begin your review output with a concise summary of the Agent Notes.
   - If absent: proceed with standard review focus.
3. **Check for other PR-specific sections** ("Review Focus", "Out of scope", "Rollout plan") and respect their scope.

---

### Critical Review Rules

- **Security**: No hardcoded secrets, credentials, or tokens. No SQL injection, XSS, or command injection vectors.
- **Backwards compatibility**: Don't break existing consumers, APIs, or interfaces without explicit migration plans.
- **Error handling**: Errors must be handled, not swallowed. Wrap with context where possible.
- **Testing**: New features and bug fixes should include test coverage.

### What NOT to Flag

- Code formatting or style — linters handle this.
- Existing code outside the PR diff.
- Minor documentation wording.

### Review Output Procedure

**CRITICAL — Single Comment Rule**: There must be **exactly one** Claude review comment on a PR at any time. Never post a second comment. Follow these steps in order:

1. **Before writing any review output**, list all existing comments on the PR.
2. **Search for a prior Claude review comment**. A comment is "yours" if the author is `claude[bot]` AND the body contains the heading `## 🔍 PR Review Summary` (defined in the [shared workflow](https://github.com/justworkshr/.github/blob/main/.github/workflows/claude-code-review.yml)).
3. **If a prior comment exists**:
   - You **MUST** edit/update that comment with your new review.
   - Remove findings that no longer apply to the current diff.
   - Add new findings for changes since the last review.
   - Do **NOT** create a new comment. This is non-negotiable.
4. **If no prior comment exists**: Create a new comment with your review.

### Review Content Expectations

- **Actionable feedback**: Include **file:line** for code issues and provide a concrete fix suggestion.
- **Avoid nitpicking**: Focus on correctness, safety, and maintainability. Skip trivial style or formatting issues.
- **Prioritization**: Only mark **Critical** for issues that can cause production outages, data loss, security vulnerabilities, or breaking changes.
