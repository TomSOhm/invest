# Contributing to Invest Solo

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to this project.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Git

### Development Setup

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/invest.git
   cd invest
   ```
3. **Set up the backend:**
   ```bash
   pip install -r requirements.txt
   cp .env.example .env
   # Edit .env with your API keys (yfinance works without a key)
   ```
4. **Set up the frontend:**
   ```bash
   cd frontend && bun install && cd ..
   ```
5. **Start development servers:**
   ```bash
   make backend    # FastAPI on port 8000
   make frontend   # Next.js on port 3000
   ```

## How to Contribute

### Reporting Bugs

- Use the [Bug Report](https://github.com/TomSOhm/invest/issues/new?template=bug_report.md) issue template
- Include steps to reproduce, expected behavior, and actual behavior
- Add your environment details (OS, Python version, Node.js version)

### Suggesting Features

- Use the [Feature Request](https://github.com/TomSOhm/invest/issues/new?template=feature_request.md) issue template
- Describe the problem your feature would solve
- Propose a solution and any alternatives you've considered

### Submitting Changes

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. **Make your changes** — keep commits focused and atomic
3. **Test your changes** — ensure existing functionality isn't broken
4. **Commit** with a clear message:
   ```bash
   git commit -m "feat: add support for new valuation model"
   ```
5. **Push** to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
6. **Open a Pull Request** against `main`

## Code Style

### Python

- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Use type hints for function signatures
- Keep functions focused and under 50 lines where possible

### TypeScript / React

- Follow the project's ESLint configuration
- Use functional components with hooks
- Keep components focused — split large components into smaller ones

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation changes
- `refactor:` — code restructuring without behavior change
- `test:` — adding or updating tests
- `chore:` — maintenance tasks (dependencies, config)

## Pull Request Guidelines

- Keep PRs focused on a single change
- Include a clear description of what changed and why
- Reference any related issues
- Ensure CI checks pass (when available)

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Questions?

Open a [GitHub issue](https://github.com/TomSOhm/invest/issues) for any questions about contributing.
