# Contributing

This repository is a design pattern first and code second. The most valuable contributions are arguments and evidence, not features.

## What helps most

| Contribution | How |
|---|---|
| **Counter-example**: a boundary the pattern does not fit, or fits badly | Open an issue with the "Counter-example" template |
| **Known use**: a system that already works this way | Open an issue with the "Known use" template |
| **New variant or anti-pattern** | Open an issue first, then a pull request against `docs/` |
| **Correction** to the prior-art comparison | Pull request against `docs/comparison.md`, with a source |
| **Reference implementation** in another language or platform | Pull request adding a sibling folder under `reference/` |

Changes to the pattern's definition (`docs/pattern.md`) should start as an issue, so the reasoning is on record before the text changes.

## Checks

Run these before opening a pull request. CI runs the same commands.

```bash
python3 tools/test_check_docs.py      # the docs checker's own tests
python3 tools/check_docs.py .         # every relative link and anchor resolves
cd reference/python && pip install -e ".[dev]" && pytest -q
```

## Writing style

- Plain language. Define a term the first time it appears.
- State trade-offs and costs next to benefits.
- Keep the pattern free of any product, platform or protocol. Those belong under `reference/`.
- Cite prior art with a link.

## Backlog

Planned work is tracked in [`TODO.md`](TODO.md) and finished work in [`CHANGELOG.md`](CHANGELOG.md). The plan behind them is in [`docs/plans/PROJECT.md`](docs/plans/PROJECT.md).

## Licensing of contributions

By contributing you agree that documentation is licensed under [CC BY 4.0](LICENSE-DOCS.md) and code under [MIT](LICENSE).
