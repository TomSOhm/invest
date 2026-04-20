# Working Context

Short notes the agent should read before acting. Keep it concise and current.

## Active Work
- Item: Swiss Company Formation Agent System Setup
- Owner: User
- ETA: Phase 1 Complete - Agents Created
- Next: User will provide business context for actual company formation

## Swiss Company Formation Project
**Status**: Agent infrastructure ready
**Goal**: Create company in Geneva, Switzerland with specialized agent workflow

### Specialized Agents Created
1. swiss-company-coordinator (MASTER - use this as entry point)
2. swiss-company-formation (legal structure, registration)
3. swiss-business-plan (business planning, financial projections)
4. swiss-legal-contracts (statutes, contracts, agreements)
5. swiss-tax-compliance (tax structure, VAT, social insurance)
6. swiss-financial-analyst (financial modeling, banking, funding)
7. swiss-regulatory-compliance (permits, licenses, data protection)
8. swiss-hr-advisor (employment, payroll, labor law)
9. swiss-strategy-advisor (market entry, growth strategy)

### Key Resources
- Geneva guide: https://www.ge.ch/comment-creer-entreprise
- Documentation: docs/administrative/Guide-EntreprendreGE-Chap.1-10.pdf
- All agents follow Swiss federal and Geneva cantonal regulations

### Usage Pattern
For company formation tasks → Start with swiss-company-coordinator
It will orchestrate workflow and delegate to specialized agents as needed

## Open Questions
- Business model and sector (awaiting user input)
- Founder details (nationality, residency status)
- Funding strategy and capital availability
- Timeline requirements and constraints

## Known Issues / Flakes
None currently

## Recent Changes
- 2026-02-01: Created 9 specialized agents for Swiss company formation in Geneva
- 2026-02-01: Agents cover all aspects: legal, tax, HR, compliance, finance, strategy
