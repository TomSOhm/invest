# Decisions Log

Keep a running list of significant choices so agents can recover context quickly.

## Swiss Company Formation Project

- Date: 2026-02-01
- Owner: User + AI
- Context: Need comprehensive agent system for Geneva company formation covering administrative, legal, financial, tax, HR, and strategic aspects
- Decision: Created 9 specialized agents (coordinator + 8 domain experts) following Swiss/Geneva regulations
- Impact:
  - Complete coverage of company formation lifecycle
  - Clear delegation and coordination model (use coordinator as entry point)
  - Reference to official Geneva resources and Guide Entreprendre
  - Ready for actual company formation when user provides business context
  - Agents can be invoked individually or through coordinator orchestration

- Date: 2026-02-01
- Owner: User + AI
- Context: Agent architecture for company formation workflow
- Decision: Master-coordinator pattern with specialized domain agents
- Impact:
  - swiss-company-coordinator = master orchestrator (START HERE)
  - 8 specialized agents for specific domains (formation, legal, tax, finance, HR, compliance, strategy, business plan)
  - Coordinator manages workflow, dependencies, timeline, and delegation
  - Agents can work in parallel where no dependencies exist
  - Clear phase-based approach (8 phases from discovery to ongoing operations)
