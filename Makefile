# ═══════════════════════════════════════════
# Invest Solo — Makefile
# ═══════════════════════════════════════════

.PHONY: install setup daily screen test clean backend frontend dev

# Install all dependencies
install:
	pip install -r requirements.txt

# First-time setup
setup:
	cp config/.env.example config/.env
	mkdir -p data/raw data/processed data/cache data/exports data/logs
	@echo "✅ Setup complete. Edit config/.env with your API keys."

# Run daily analysis pipeline
daily:
	python scripts/daily_run.py

# Screen PEA-eligible stocks
screen-pea:
	python scripts/daily_run.py --strategy pea

# Screen global stocks
screen-global:
	python scripts/daily_run.py --strategy global

# Update PEA universe
update-universe:
	python scripts/update_universe.py

# Run backtests
backtest:
	python scripts/backtest.py

# Run tests
test:
	pytest tests/ -v --cov=src

# Launch dashboard
dashboard:
	streamlit run src/reporting/dashboard.py

# ═══════════════════════════════════════════
# Full-Stack Development
# ═══════════════════════════════════════════

# Start FastAPI backend (port 8000)
backend:
	python -m uvicorn backend.app.main:app --reload --port 8000

# Start Next.js frontend (port 3000)
frontend:
	cd frontend && npm run dev

# Install frontend dependencies
frontend-install:
	cd frontend && npm install

# Build frontend for production
frontend-build:
	cd frontend && npm run build

# Clean cache and temporary files
clean:
	rm -rf data/cache/*
	rm -rf __pycache__ src/**/__pycache__
	find . -name "*.pyc" -delete

# Generate a company report
# Usage: make report TICKER=TTE.PA
report:
	python -c "from src.reporting.company_report import generate; generate('$(TICKER)')"
