---
plan_id: docker-removal-host-exec-plan
git_sha: 6e10b8e96bc0eb6738d174b8d81a21325ad9c4d2
status: done
evaluation_notes: []
---

## Objectives
- Eliminate Docker dependencies from all `lw_coder` workflows.
- Run `plan` and `code` commands directly on Linux host environments.
- Prepare the codebase for future Claude Code CLI sandbox integration without implementing it yet.

## Requirements & Constraints
1. Remove Docker usage across source code, tests, scripts, configuration, and documentation.
2. Support Linux hosts and emit explicit warnings when execution occurs on unsupported operating systems.
3. Document manual prerequisites instead of introducing an automated installer.
4. Accept elevated host permissions temporarily while documenting associated security considerations.
5. Preserve DSPy/GEPA workflows and ensure the existing test suite succeeds without Docker involvement.

## Work Items
1. **Code Refactor**
   - Replace `droid_session` Docker orchestration with host-native execution.
   - Update `code_command` and `plan_command` to invoke the new host runner and drop Docker command construction.
   - Remove Docker-specific helpers, temporary passwd/group file handling, and mount logic.
   - Implement host-based environment and path resolution for `.factory`, `.lw_coder`, and related assets.
2. **Unsupported OS Handling**
   - Detect host operating system at runtime.
   - Display clear warnings (or prevent execution, if appropriate) on macOS and Windows, including guidance on current limitations.
3. **Testing Updates**
   - Rewrite integration tests that currently rely on Docker to exercise the host execution path.
   - Remove Docker build/run tests and introduce coverage for the new workflow.
   - Adjust CI scripts and configurations to operate without Docker dependencies.
4. **Configuration & Scripts**
   - Delete Dockerfiles, Docker build scripts, and any automation invoking Docker commands.
   - Update auxiliary scripts or tooling that reference containerized execution.
5. **Documentation**
   - Revise README, overview, and related documents to describe the host-based workflow and remove Docker references.
   - Document Linux support expectations, manual dependency setup, and unsupported OS behavior.
   - Highlight security implications while Claude sandbox integration remains pending.
6. **Validation**
   - Confirm `uv run pytest` passes on a clean Linux environment without Docker.
   - Verify `lw_coder plan` and `lw_coder code` execute successfully end-to-end on the host.

## Deliverables
- Updated Python modules implementing host execution with OS warnings.
- Removal of Docker assets alongside updated scripts and tests.
- Revised documentation detailing host workflow and platform limitations.
- Passing automated tests demonstrating successful host-based operation.

## Out of Scope
- Implementing Claude Code CLI sandbox integration.
- Creating automated installers or dependency bootstrapping tooling.
- Providing macOS or Windows support beyond issuing warnings and documenting limitations.

## Test Cases
```gherkin
Feature: Host-based lw_coder execution
  Scenario: Running plan command on Linux without Docker
    Given a Linux developer environment with required dependencies installed
    And ~/.factory/auth.json and lw_coder configs exist
    When the user runs "lw_coder plan idea.md"
    Then the command executes using the host environment without invoking Docker
    And the output plan file is generated successfully

  Scenario: Running code command with repository tests
    Given a Linux developer environment configured to run repository tests
    When the user runs "lw_coder code plan.md"
    Then the command validates the plan and executes coding steps on the host
    And repository tests execute using the developer's host environment

  Scenario: Detecting unsupported host OS
    Given the developer is on macOS
    When they attempt to run "lw_coder plan idea.md"
    Then lw_coder detects the unsupported OS
    And it displays a warning explaining Linux-only support and current limitations
```
