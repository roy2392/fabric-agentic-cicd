# Fabric agentic CI/CD handbook

This handbook is the shared project context for operators, the Claude developer and the independent Codex reviewer. It describes the implemented synthetic loyalty demo, its limits and the evidence needed to change it safely.

## Start here

| Goal | Read |
|---|---|
| Understand the system and trust boundaries | [Architecture](/Architecture) |
| Understand ingestion and history | [Ingestion Framework Guide](/Ingestion-Framework-Guide) |
| Author a valid source configuration | [Metadata Schema Reference](/Metadata-Schema-Reference) |
| Find source and column definitions | [Table Inventory](/Table-Inventory) |
| Execute an authorized load | [How to Run a Load](/How-to-Run-a-Load) |
| Add a source | [Onboarding a New Source System](/Onboarding-a-New-Source-System) |
| Watch the two agents work | [Agent Workflow and Context](/Agent-Workflow-and-Context) |
| Recover from an error | [Troubleshooting and Recovery](/Troubleshooting-and-Recovery) |
| Assess what has actually passed | [Verified Execution Evidence](/Verified-Execution-Evidence) |

## What this demo proves

A scoped developer can implement an assigned feature, run bounded checks and open a PR. A separate reviewer reads the exact source and target revisions and records approval or actionable findings. A human decides whether to merge. The original source-onboarding demonstration also has historical Fabric pipeline and notebook evidence; a utility or documentation PR does not constitute a new Fabric execution.

The current automatic board lane supports small local Python utilities and Markdown documentation. It does not automatically onboard arbitrary sources, deploy infrastructure or run Fabric. The earlier onboarding lane has a different execution contract.

## Source of truth

Solution Git defines implementation. The project wiki defines operational context. The board defines the assigned acceptance criteria. The pinned official Microsoft Fabric skills supply product guidance. None of these grants additional permissions. Deployment uses an explicitly selected environment; private credentials and deployment manifests stay outside public Git.

The handbook is versioned in the wiki's `wikiMaster` branch. New agent sessions pin its commit and return complete required pages through tools. Publication and review evidence records that commit and page hashes. Historical reviews created before this integration have no such receipt and must not be described as wiki-gated.
