# AI Coding Platform

This project hosts a self-optimizing multi-agent coding assistant that orchestrates coding runs through containerized executors. Prompts are evolved with DSPy and the GEPA optimizer to coordinate specialized subagents—coders, reviewers, testers—for higher quality and faster delivery without reinventing the toolchain.

## Highlights
- Uses DSPy signatures to define the core coder and supporting review/test agents
- Integrates with CLI-based coding platforms and runs each experiment in isolated Docker worktrees
- Feeds GEPA with task/eval logs to iteratively improve prompt scaffolding, delegation order, and runtime efficiency
