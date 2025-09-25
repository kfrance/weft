### Overview of Your AI Coding Platform

Your AI coding platform is a sophisticated, self-optimizing system designed to assist with coding tasks on your codebase without fully reinventing existing tools. It leverages DSPy (a framework for prompt engineering and optimization) and GEPA (a genetic evolutionary prompt adaptation optimizer built on DSPy) to create a multi-agent architecture. At its core, it integrates with coding agents like Claude Code CLI (or alternatives such as Goose or other platforms that support subagents) as the primary executor. The focus is on generating optimized prompts that delegate subtasks to specialized subagents, with the "magic" in optimizing not just individual prompts but the overall scaffolding—such as the organization, order, and parallelism of agents—to improve efficiency and output quality over time. To ensure safe, isolated execution, all coding runs occur in Docker containers, and GEPA manages Git worktrees for each experiment to handle codebase states reproducibly.

#### Core Components
- **DSPy Signatures**: Every agent in the system is defined via DSPy signatures, which specify inputs (e.g., task description, codebase context) and outputs (e.g., generated code or reviews). This includes:
  - A core "coder" signature that outputs an optimized prompt for the chosen coding platform (e.g., Claude Code CLI).
  - Subagent signatures for specialized roles, such as code-reviewer (checks for bugs and style), test-writer (generates unit tests), plan-adherence-checker (ensures alignment with the original plan), and potentially others like dependency-resolver.
- **Coding Platform Integration**: The platform uses tools like Claude Code CLI, Goose, or similar subagent-capable systems as the execution engine. The core prompt is crafted to be passed directly (e.g., via `claude -p "<optimized_prompt>"`), including instructions for implementing code and delegating to subagents. Subagents are defined in platform-specific formats (e.g., Markdown files with YAML frontmatter for Claude).
- **GEPA Optimizer**: This evolutionary algorithm optimizes prompts and scaffolding using genetic mutations, evaluations, and selection. It ingests inputs from YAML or JSON files and has visibility into subagents via an "agent registry" (a context block listing agent names, descriptions, capabilities, and invocation syntax, e.g., "Delegate to code-reviewer with input: [code diff]"). Currently, GEPA does not propose or invent new subagents; it focuses on evolving the main prompt to better instruct the use of existing subagents, such as specifying optimal orders, sequences, or parallelism.
- **Subagents**: These are pre-defined but optimizable via DSPy. They can be called explicitly or proactively by the main agent. Subagent prompts are generated dynamically in the GEPA loop and configured for the platform before execution, enabling parallelism (e.g., "Run code-reviewer and plan-adherence-checker concurrently").
- **Isolation and Versioning**: All executions run in Docker containers to prevent system interference. Git worktrees are created based on specified SHAs for reproducible environments.

#### Workflow for a Coding Task
1. **Input Processing**: You provide a coding task, which is structured in YAML or JSON files containing:
   - `plan`: The high-level plan or task description (e.g., "Refactor API call to handle errors").
   - `git_sha`: The Git commit SHA to base the worktree on, ensuring a consistent starting codebase state.
   - `evaluation_notes`: Human-defined questions for post-run checks (e.g., "Did it use the correct API key? Passed/Failed with notes").
   Relevant codebase context is extracted or inferred from the Git worktree.
2. **Core Prompt Generation**: Using the optimized DSPy program (e.g., a `ChainOfThought` module), the system generates a tailored prompt. This includes:
   - Task implementation instructions derived from the plan.
   - Delegation logic, evolved by GEPA to suggest optimal agent calls, sequences, or parallelism based on the agent registry (e.g., specifying an order like "First delegate to plan-adherence-checker, then code-reviewer").
3. **Subagent Preparation**: Subagent configurations (e.g., prompts or files) are programmatically created or updated with their optimized content.
4. **Execution Environment Setup**: A new Git worktree is created from the specified `git_sha`. The coding platform (e.g., Claude Code CLI or Goose) is spun up in a Docker container, isolating the run to avoid impacting your main system.
5. **Execution**: The generated prompt is run through the platform in the container. The agent handles coding and delegates to subagents as instructed, producing code, reviews, tests, etc.
6. **Output and Iteration**: Results are captured from the container. If in a GEPA training loop, this output is evaluated; otherwise, it's delivered to you for use. The worktree and container are cleaned up post-run.

#### Optimization and Training Process
- **GEPA Training Loop**: This is where the system self-improves. GEPA processes a trainset derived from YAML/JSON files (built as `dspy.Example` objects), each representing an experiment (GEPA's term for optimization trials or iterations). Files include:
  - `plan`: Serves as the task input.
  - `git_sha`: Used to recreate the exact codebase state via worktrees.
  - `evaluation_notes`: Defines passed/failed checks as human questions, which feed into the metric (e.g., annotating failures like "Wrong API key used").
  For each GEPA experiment:
  - A dedicated Git worktree is created from the `git_sha`.
  - The coding platform runs in a Docker container on that worktree.
  - GEPA generates prompt variants, executes them, and evaluates outputs.
- **Evaluation Metrics**: A custom metric drives evolution, incorporating multiple factors for balanced optimization:
  - Automated: Check if generated code passes unit tests (e.g., via pytest in the container).
  - Semi-Automated/Human: Use `evaluation_notes` for questions like "Did it use the correct API key?" (evaluated via regex, a small LM, passed/failed flags, or your manual review). Failures from prior runs become negative examples.
  - Time-Based: Include coding execution time (measured during the container run) to prefer variants that accomplish the task faster, penalizing inefficient delegations or overly complex prompts.
- **Scaffolding Optimization**: GEPA evolves the core prompt to discover better uses of existing subagents (e.g., finding that a specific order like parallel reviews followed by serial checks speeds up workflows). It does not currently create new agents but can mutate subagent descriptions or refine invocation patterns based on patterns in evals. Each experiment's isolation (via worktrees and containers) ensures clean, reproducible results.
- **Bootstrap and Iteration**: Start with a small set of YAML/JSON files from manual runs. As you use the platform, log sessions to generate new files, expanding the trainset and retraining GEPA periodically. This creates a feedback loop where real usage refines the system, with `evaluation_notes` capturing evolving criteria.

#### Key Features and Enhancements
- **Multi-Agent Efficiency**: Avoids monolithic prompts by distributing work, with GEPA learning optimal delegation (e.g., serial for dependencies, parallel for independent checks) within the constraints of existing subagents.
- **Safety and Reproducibility**: Docker containers prevent destructive changes, while Git worktrees tied to SHAs allow exact recreation of past states for debugging or retraining.
- **Platform Flexibility**: Supports switching between Claude Code CLI, Goose, or other subagent-enabled tools, with GEPA adapting prompts accordingly.
- **Hybrid Flexibility**: Potential extensions include API calls for subagents (bypassing files for speed) or federating with other models (e.g., GPT for ideation).
- **Out-of-the-Box Elements**: The platform could evolve into a graph-based system (agents as nodes, optimized flows), self-invent new subagents from logs (as a future upgrade), or incorporate predictive failure modeling to prune bad variants early.
- **Practical Considerations**: Handles integration challenges by automating file management, worktree creation, container orchestration, and error fallbacks. It's user-centric, with evals tied to your process (via `evaluation_notes`) for ongoing refinement, now prioritizing time efficiency in metrics.

This platform transforms static tools into an adaptive ecosystem, optimizing both prompts and agent orchestration for your specific codebase needs, all while maintaining safety through isolated executions. If you'd like to expand on any part (e.g., code snippets for implementation), let me know!
