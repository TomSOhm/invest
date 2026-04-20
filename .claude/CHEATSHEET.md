# Claude Code Plugin & MCP Cheatsheet

Quick reference for all installed plugins, skills, agents, and MCP servers.

---

## 1. Development Workflow

| Tool | Command/Trigger | Use Case |
|------|----------------|----------|
| superpowers | `/superpowers:brainstorming` | Refine ideas before any creative/implementation work |
| superpowers | `/superpowers:writing-plans` | Break work into small executable tasks |
| superpowers | `/superpowers:executing-plans` | Execute plans with review checkpoints |
| superpowers | `/superpowers:test-driven-development` | RED-GREEN-REFACTOR cycle |
| superpowers | `/superpowers:systematic-debugging` | 4-phase root cause debugging |
| superpowers | `/superpowers:verification-before-completion` | Verify work before claiming done |
| superpowers | `/superpowers:requesting-code-review` | Pre-merge code review |
| superpowers | `/superpowers:receiving-code-review` | Handle review feedback properly |
| superpowers | `/superpowers:dispatching-parallel-agents` | Run 2+ independent tasks concurrently |
| superpowers | `/superpowers:subagent-driven-development` | Execute plans via subagents |
| superpowers | `/superpowers:using-git-worktrees` | Isolated feature branches |
| superpowers | `/superpowers:finishing-a-development-branch` | Merge/PR/cleanup decision |
| superpowers | `/superpowers:writing-skills` | Create new skills |
| superpowers | `/superpowers:using-superpowers` | Introduction to skills system |
| feature-dev | `/feature-dev:feature-dev` | Guided feature development with architecture focus |
| code-review | `/code-review:code-review` | Automated PR review with confidence scoring |
| ralph-wiggum | `/ralph-wiggum:ralph-loop` | Continuous iterative dev loop |
| ralph-wiggum | `/ralph-wiggum:cancel-ralph` | Stop the Ralph loop |
| ralph-wiggum | `/ralph-wiggum:help` | Explain Ralph Wiggum technique |
| frontend-design | `/frontend-design:frontend-design` | Create polished UI components/pages |

## 2. Plugin Development

| Tool | Command/Trigger | Use Case |
|------|----------------|----------|
| plugin-dev | `/plugin-dev:create-plugin` | 8-phase guided plugin creation |
| plugin-dev | `/plugin-dev:plugin-structure` | Directory layout & manifest guidance |
| plugin-dev | `/plugin-dev:command-development` | Create slash commands |
| plugin-dev | `/plugin-dev:agent-development` | Create autonomous agents |
| plugin-dev | `/plugin-dev:skill-development` | Create skills with progressive disclosure |
| plugin-dev | `/plugin-dev:hook-development` | Event-driven hooks (PreToolUse, PostToolUse, etc.) |
| plugin-dev | `/plugin-dev:mcp-integration` | Add MCP servers to plugins |
| plugin-dev | `/plugin-dev:plugin-settings` | Plugin configuration via .local.md |
| agent-sdk-dev | `/agent-sdk-dev:new-sdk-app` | Create new Claude Agent SDK app |
| skill-creator | (auto-trigger) | Guide for creating effective skills |

## 3. Document Creation

| Tool | Command/Trigger | Use Case |
|------|----------------|----------|
| document-skills-docx | (auto-trigger) | Word docs with tracked changes, comments, formatting |
| document-skills-pdf | (auto-trigger) | PDF manipulation: extract, merge, split, create, OCR |
| document-skills-pptx | (auto-trigger) | PowerPoint presentations via HTML-to-PPTX workflow |
| document-skills-xlsx | (auto-trigger) | Spreadsheets with formulas, formatting, data analysis |
| canvas-design | (auto-trigger) | Visual art in .png/.pdf with design philosophy |
| content-research-writer | (auto-trigger) | Research-backed content writing with citations |

## 4. Design & Automation

| Tool | Command/Trigger | Use Case |
|------|----------------|----------|
| canva-automation | (auto-trigger) | Automate Canva: create, export, autofill designs |
| figma-automation | (auto-trigger) | Figma: get files, render nodes, extract design tokens |

## 5. Business & Research

| Tool | Command/Trigger | Use Case |
|------|----------------|----------|
| domain-name-brainstormer | (auto-trigger) | Generate domain names + check availability |
| lead-research-assistant | (auto-trigger) | Identify leads, score fit, build prospect lists |

## 6. Testing

| Tool | Command/Trigger | Use Case |
|------|----------------|----------|
| webapp-testing | (auto-trigger) | Test web apps with Playwright (screenshots, logs, automation) |

## 7. Documentation Lookup

| Tool | Command/Trigger | Use Case |
|------|----------------|----------|
| context7-plugin | `/context7-plugin:docs` | Look up any library documentation |
| context7-plugin | `/context7-plugin:documentation-lookup` | Auto-triggers for framework/library questions |

## 8. MCP Servers (Built-in Tools)

| Server | What It Does |
|--------|-------------|
| Context7 | Version-specific library docs lookup via `resolve-library-id` + `query-docs` |
| GitHub | Repo management, PRs, issues, code review via `gh` CLI |
| Figma | Design file access, component inspection |
| Chrome DevTools | Browser debugging and web inspection |
| Hugging Face | Model/dataset/paper search, space discovery, doc search |
| 21st.dev Magic | Crafted UI components (requires `21STDEV_API_KEY`) |

## 9. Specialized Subagents

| Agent | Trigger | Use Case |
|-------|---------|----------|
| `code-architect` | `feature-dev:code-architect` | Design feature architectures from existing patterns |
| `code-explorer` | `feature-dev:code-explorer` | Trace execution paths, map architecture layers |
| `code-reviewer` | `feature-dev:code-reviewer` | Bug/security/quality review with confidence filtering |
| `code-reviewer` | `superpowers:code-reviewer` | Review completed steps against plan and standards |
| `architect-reviewer` | (Task tool) | SOLID principles, layering, maintainability review |
| `backend-architect` | (Task tool) | REST APIs, microservices, DB schemas, scalability |
| `database-architect` | (Task tool) | Data modeling, DB tech selection, scalability |
| `frontend-developer` | (Task tool) | React components, state management, accessibility |
| `fullstack-developer` | (Task tool) | End-to-end app dev, API integration |
| `security-auditor` | (Task tool) | Vulnerability review, auth flows, OWASP compliance |
| `error-detective` | (Task tool) | Log analysis, error pattern detection, debugging |
| `typescript-pro` | (Task tool) | Advanced TS types, strict typing, migration |
| `ui-ux-designer` | (Task tool) | User research, wireframes, design systems |
| `mcp-expert` | (Task tool) | MCP server configs, protocol specs |
| `python_ml_expert` | (Task tool) | ML, data analysis, visualization in Python |
| `research_explorer` | (Task tool) | Research papers, algorithms, experimental approaches |

## 10. Swiss Business Suite

| Agent | Use Case |
|-------|----------|
| `swiss-company-coordinator` | Master coordinator for Swiss company formation |
| `swiss-company-formation` | Geneva canton legal entity setup |
| `swiss-business-plan` | Business plans for Swiss investors |
| `swiss-financial-analyst` | Swiss accounting, banking, financial modeling |
| `swiss-tax-compliance` | Geneva/federal taxes, VAT, social insurance |
| `swiss-legal-contracts` | Swiss Code of Obligations contracts |
| `swiss-hr-advisor` | Swiss employment law, payroll, benefits |
| `swiss-regulatory-compliance` | Permits, licenses, GDPR/Swiss DPA |
| `swiss-strategy-advisor` | Market entry, competitive positioning in CH |

---

*Last updated: 2026-02-15*
