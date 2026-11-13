# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **FEAT-012** (feat): Complete the documentation set: references, animated diagrams, a guide, the article and a publishing plan. Ref: docs/plans/PROJECT.md#scope. Validated: `python3 tools/check_docs.py docs --reachable-from docs/index.md --forbid inbox`. Docs: updated README.md, docs/index.md, docs/references.md, docs/pattern.md, docs/diagrams, launch/article.md, launch/posts.md, launch/publishing-plan.md. Includes: FEAT-012.1, FEAT-012.2, FEAT-012.3, FEAT-012.4.
- **FEAT-011** (feat): Apply the agreed definition: tasks, journalled actions, admission and compensation. Ref: docs/plans/PROJECT.md#decisions. Validated: `python3 tools/check_docs.py README.md docs reference --forbid inbox --require Admission`. Docs: updated README.md, docs/pattern.md, docs/protocol-mapping.md, docs/decision-guide.md, docs/example.md, docs/influences.md, reference/README.md, reference/abstraction.md. Includes: FEAT-011.1, FEAT-011.2.
- **FEAT-009** (feat): Document the inbox-driven ambassador, its influences and the System 1 preference. Ref: docs/plans/PROJECT.md#decisions. Validated: `python3 tools/check_docs.py docs/influences.md docs/pattern.md docs/decision-guide.md --require Inbox --require "System 1" --require Actor --require Accepted`. Docs: updated README.md, docs/comparison.md, docs/decision-guide.md, docs/influences.md, docs/pattern.md.

### Changed

- **TASK-014** (docs): Change the worked example to an invented online shop and courier. Ref: docs/example.md. Validated: `cd reference/python && pytest -q`. Docs: updated docs/example.md, launch/article.md, reference/README.md.
- **TASK-013** (docs): Merge the pattern documentation into one complete article. Ref: docs/plans/PROJECT.md#scope. Validated: `python3 tools/check_docs.py launch/article.md --require Admission --require Journal --require Compensation --require "Open questions" --require References`. Docs: updated launch/article.md.
- **TASK-010** (docs): Replace the novelty claims in influences.md with a statement of what the pattern emphasises. Ref: docs/influences.md. Validated: `python3 tools/check_docs.py docs/influences.md --require emphasises --forbid "pattern's own"`. Docs: updated docs/influences.md.
- **TASK-001** (chore): Clean up the repository so the docs can be checked and contributed to. Ref: docs/plans/PROJECT.md#lanes. Validated: `python3 tools/check_docs.py .`. Docs: updated README.md, CONTRIBUTING.md, launch/launch-kit.md, reference/README.md, reference/abstraction.md. Includes: TASK-001.1, TASK-001.2, TASK-001.3, TASK-001.4.
