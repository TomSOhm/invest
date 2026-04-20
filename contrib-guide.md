# Contributing to Invest Solo

Thank you for your interest in contributing! This guide will help you get started.

## Prerequisites

- Python 3.11+
- Node.js 18+
- bun
- Git

## Development Setup

```bash
# Fork and clone the repository
git clone https://github.com/<your-username>/invest.git
cd invest

# Set up API keys (optional — yfinance works without keys)
cp .env.example .env

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend && bun install && cd ..

# Start the backend (terminal 1)
make backend

# Start the frontend (terminal 2)
make frontend
```

## Development Workflow

1. **Fork** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
3. **Make your changes** following the code style guidelines below
4. **Test** your changes
5. **Commit** with a descriptive message:
   ```bash
   git commit -m "feat: add new valuation model for REITs"
   ```
6. **Push** your branch and open a Pull Request

## Branch Naming

| Prefix | Purpose |
|--------|---------|
| `feat/` | New features |
| `fix/` | Bug fixes |
| `docs/` | Documentation changes |
| `refactor/` | Code refactoring |
| `test/` | Adding or updating tests |

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short description>

[optional body]
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`

Examples:
- `feat: add Piotroski F-Score to scoring engine`
- `fix: correct DCF terminal value calculation`
- `docs: update API endpoints in DATA_SOURCES.md`

## Code Style

### Python
- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Use type hints for function signatures
- Use descriptive variable names (e.g., `free_cash_flow` not `fcf`)

### TypeScript / React
- Follow the existing ESLint configuration
- Use functional components with hooks
- Use TypeScript types (no `any`)

## What to Contribute

- **Bug reports** — Open an issue with steps to reproduce
- **New valuation models** — Add to `src/analysis/` or `backend/app/services/`
- **UI improvements** — Enhance components in `frontend/src/components/`
- **Documentation** — Improve docs, fix typos, add examples
- **Data sources** — Integrate new financial data providers
- **Tests** — Expand test coverage

## Pull Request Guidelines

- Keep PRs focused on a single change
- Update documentation if your change affects usage
- Ensure the backend and frontend both run without errors
- Describe what your PR does and why in the description

## Questions?

Open a [GitHub Discussion](https://github.com/TomSOhm/invest/discussions) or an issue — we are happy to help.
