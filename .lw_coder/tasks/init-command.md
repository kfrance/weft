---
plan_id: init-command
status: done
evaluation_notes: []
git_sha: 2bb7e105ae28adf3184b522ce42bf8e4a5db4243
---

# Add Init Command for Project Bootstrapping

## Objectives

Create an `init` command for lw_coder that initializes new projects with frozen baseline prompts and judges. This provides a standardized starting point before project-specific prompt optimization begins.

**Key Goals:**
- Bootstrap new projects with minimal setup friction
- Distribute frozen "general-purpose baseline" templates that represent current best practices
- Support safe re-initialization when needed (with user confirmation)
- Detect git repositories and work from any subdirectory
- Provide version tracking for future template evolution
- Ensure atomic operations with rollback on failure
- Support both interactive and automated (CI/CD) workflows

## Requirements & Constraints

### Functional Requirements

1. **Command Interface**
   - Command: `lw_coder init [--force] [--yes]`
   - `--force`: Allow initialization when `.lw_coder/` already exists (with confirmation)
   - `--yes`: Skip interactive prompts (for CI/CD automation)
   - Exit codes: 0 for success, 1 for failure

2. **Git Repository Detection**
   - Must be run within a git repository
   - Detect git repository root from any subdirectory (reuse existing `find_repo_root()` from `repo_utils.py`)
   - Fail with clear, actionable error message if not in a git repository
   - Create `.lw_coder/` at the detected repository root, not in current working directory

3. **Frozen Template Assets**
   - Bundle current templates in package: `src/lw_coder/init_templates/`
   - Include complete directory structure:
     - `judges/` (code-reuse.md, plan-compliance.md)
     - `optimized_prompts/claude-code-cli/{sonnet,opus,haiku}/*.md`
   - Add `VERSION` file to track template version (format: semantic version + metadata)
   - Templates remain stable across lw_coder versions (not auto-updated)

4. **Initialization Logic**
   - **Case 1**: `.lw_coder/` doesn't exist
     - Create `.lw_coder/` directory at repo root
     - Copy all judges and optimized prompts
     - Display success message with next steps
   - **Case 2**: `.lw_coder/` exists, no `--force` flag
     - Fail with error: "Directory .lw_coder already exists. Use --force to reinitialize."
   - **Case 3**: `.lw_coder/` exists, `--force` without `--yes`
     - Load `.lw_coder/VERSION` file and check file hashes
     - Compare current file hashes against VERSION hashes to detect customizations
     - Display warnings for any customized files: "WARNING: N judges have been customized from baseline"
     - Prompt: "Overwrite existing judges? (y/n)"
     - Display warnings for any customized prompts: "WARNING: N prompts have been customized from baseline"
     - Prompt: "Overwrite existing optimized prompts? (y/n)"
     - Respect user choices, only overwrite confirmed sections
   - **Case 4**: `.lw_coder/` exists, `--force --yes`
     - Automatically overwrite both judges and prompts
     - No interactive prompts (for automation)

5. **Atomic Operations**
   - Use transactional approach with rollback on failure
   - If any step fails (permissions, disk space, etc.):
     - Rollback all changes made during this init invocation
     - Leave filesystem in original state
     - Report clear error message
   - Implementation approach: copy to temporary staging directory first, then atomic move

6. **Version Tracking with Customization Detection**
   - Create `src/lw_coder/init_templates/VERSION` file with format:
     ```json
     {
       "template_version": "1.0.0",
       "lw_coder_version": "0.6.0",
       "frozen_date": "2025-11-26",
       "description": "Initial frozen baseline templates",
       "files": {
         "judges/code-reuse.md": {"hash": "sha256:abc123..."},
         "judges/plan-compliance.md": {"hash": "sha256:def456..."},
         "optimized_prompts/claude-code-cli/sonnet/main.md": {"hash": "sha256:ghi789..."}
       }
     }
     ```
   - Include SHA256 hash for every template file
   - Copy VERSION to `.lw_coder/VERSION` during initialization
   - Before overwriting with `--force`, compare current file hashes to VERSION hashes
   - Warn user if files have been customized: "WARNING: judges/code-reuse.md has been modified from baseline. Overwriting will lose your customizations."
   - Users can check their template version

### Technical Constraints

- **Platform Support**: Linux only (matches lw_coder's current platform support)
- **Dependencies**:
  - Use standard library where possible (`hashlib`, `json`, `tempfile`, `shutil`)
  - Reuse existing utilities from codebase (see implementation notes below)
  - No new external dependencies required
- **Package Size**: Bundled templates will increase package size (acceptable tradeoff)
- **Path Handling**: Use `pathlib.Path` throughout (follow existing codebase pattern)
- **Git Requirements**: Requires git command-line tool (already a lw_coder dependency)
- **Code Patterns** - Follow existing codebase conventions:
  - Exception naming: `InitCommandError(Exception)` pattern
  - Logging: `logger = get_logger(__name__)` pattern
  - File I/O: `path.read_text(encoding="utf-8")` / `path.write_text(content, encoding="utf-8")`
  - JSON loading: Pattern from `droid_auth.py`
  - Temp directories: Pattern from `plan_command.py`

### Quality Requirements

- **Testing** (per `docs/BEST_PRACTICES.md`):
  - Unit tests for all core functions
  - Integration tests for full init workflow
  - Tests must use `pytest.fail()` for missing dependencies, not `pytest.skip()`
  - Test atomic rollback behavior
  - Test all initialization cases (new, existing, --force, --yes combinations)
  - Parametrized tests for different scenarios
  - No mocking of file operations (use temp directories)
- **Error Handling**:
  - Clear, actionable error messages
  - Suggest corrective actions (e.g., "Run 'git init' to create a repository")
  - Handle edge cases gracefully (permissions, read-only filesystems, etc.)
- **Documentation**:
  - Update CLAUDE.md with init command usage
  - Document template freezing process for maintainers
  - Add docstrings with examples
- **Code Quality**:
  - Follow existing codebase patterns
  - Reuse existing utilities (git detection, logging, etc.)
  - Type hints throughout

## Work Items

### 1. Freeze Current Templates

**Objective:** Capture current templates as frozen baseline in package.

**Tasks:**
- Create `src/lw_coder/init_templates/` directory structure
- Copy current `.lw_coder/judges/` contents:
  - `code-reuse.md`
  - `plan-compliance.md`
- Copy current `.lw_coder/optimized_prompts/` directory tree:
  - `claude-code-cli/sonnet/{main.md, plan-alignment-checker.md, code-review-auditor.md}`
  - `claude-code-cli/opus/{main.md, plan-alignment-checker.md, code-review-auditor.md}`
  - `claude-code-cli/haiku/{main.md, plan-alignment-checker.md, code-review-auditor.md}`
- Create `VERSION` file with metadata and per-file hashes:
  ```json
  {
    "template_version": "1.0.0",
    "lw_coder_version": "0.6.0",
    "frozen_date": "2025-11-26",
    "description": "Initial frozen baseline templates",
    "files": {
      "judges/code-reuse.md": {"hash": "sha256:abc123..."},
      "judges/plan-compliance.md": {"hash": "sha256:def456..."},
      "optimized_prompts/claude-code-cli/sonnet/main.md": {"hash": "sha256:ghi789..."}
    }
  }
  ```
- Calculate SHA256 hash for each template file
- Store relative path and hash in VERSION file
- Script to generate VERSION file: `scripts/generate_template_version.py`
- Verify templates are included in package distribution (check `pyproject.toml` package data)

**Acceptance Criteria:**
- All current templates captured in `src/lw_coder/init_templates/`
- Directory structure preserved exactly
- VERSION file present with valid JSON including SHA256 hash for every template file
- Script available to regenerate VERSION file if templates change (`scripts/generate_template_version.py`)
- Templates accessible after `uv tool install`
- No code duplication - reuses existing utilities where available

### 2. Reuse Existing Git Detection

**Objective:** Use existing git repository detection from codebase.

**Tasks:**
- Import and use `find_repo_root()` from `src/lw_coder/repo_utils.py`
  - Already handles finding git root from any path
  - Already raises `RepoUtilsError` with message "Must be run from within a Git repository."
  - No need to reimplement
- Add unit tests for init command's handling of git detection:
  - Test init from repository root
  - Test init from subdirectory (multiple levels deep)
  - Test init from non-git directory (verify error handling)
  - Tests will use existing `find_repo_root()` function

**Acceptance Criteria:**
- Init command uses existing `find_repo_root()` function
- Error messages are clear and actionable
- Tests cover all scenarios
- Follows existing codebase patterns for git operations

### 3. Implement Template Copying with Atomic Operations and Customization Detection

**Objective:** Copy templates safely with rollback on failure, detecting customizations before overwriting.

**Tasks:**
- Create `src/lw_coder/init_command.py` module
- Create `InitCommandError` exception (follow existing pattern: `class InitCommandError(Exception)`)
- Import reusable utilities:
  - `find_repo_root()` from `repo_utils.py`
  - `get_logger(__name__)` from `logging_config.py`
- Implement hash calculation utilities:
  - `calculate_file_hash(file_path: Path) -> str` - returns "sha256:..." string
    - Use `hashlib.sha256()` from Python standard library
    - Read file in binary mode: `file_path.read_bytes()`
    - Format as "sha256:hexdigest"
  - `load_version_file(path: Path) -> dict` - loads and parses VERSION JSON
    - Follow JSON loading pattern from `droid_auth.py`:
      ```python
      with open(path, "r", encoding="utf-8") as f:
          return json.load(f)
      ```
  - `detect_customizations(lw_coder_dir: Path, file_list: list[str]) -> list[str]` - returns list of customized files
- Implement customization detection logic:
  - Load `.lw_coder/VERSION` file
  - For each template file, calculate current hash
  - Compare to hash in VERSION["files"]
  - Return list of files that have been modified
- Implement `AtomicInitializer` context manager:
  - Creates temporary staging directory using `tempfile.mkdtemp()` (follow pattern from `plan_command.py`)
  - Copies templates to staging
  - On success: atomic move to target location using `shutil.move()`
  - On failure: cleanup staging directory with `shutil.rmtree()`, rollback changes
- Implement template copying functions:
  - `copy_judges(staging_dir: Path, bundle_path: Path) -> None`
  - `copy_optimized_prompts(staging_dir: Path, bundle_path: Path) -> None`
  - `copy_version_file(staging_dir: Path, bundle_path: Path) -> None`
  - Use `shutil.copytree()` for directory trees
  - Use `path.read_bytes()` / `path.write_bytes()` for individual files (follow pattern from `plan_file_copier.py`)
- Handle selective overwrite (based on user prompts):
  - Before prompting, detect and display customizations
  - Show count and list of customized files
  - Skip judges if user said "n"
  - Skip prompts if user said "n"
  - Always copy VERSION file
- Log all operations using `logger.info()` and `logger.debug()` (follow existing patterns)

**Acceptance Criteria:**
- Atomic operations: all-or-nothing behavior
- Rollback works correctly on failure (disk full, permissions, etc.)
- Preserves directory structure exactly
- Selective copying works based on user choices
- Customization detection works correctly (identifies modified files)
- Clear warnings displayed before overwriting customized files
- Comprehensive error handling
- Integration tests verify atomicity and customization detection

### 4. Implement Interactive Prompts and CLI Integration

**Objective:** Add user interaction and wire up CLI command.

**Tasks:**
- Implement prompt functions:
  - `prompt_yes_no(message: str) -> bool`
  - Returns True for 'y'/'yes', False for 'n'/'no'
  - Handles invalid input (reprompt)
  - Respects --yes flag (return True without prompting)
- Implement customization warning display:
  - `display_customization_warnings(customized_files: list[str], category: str) -> None`
  - Shows count and list of files that have been modified
  - Example: "WARNING: 2 judges have been customized from baseline:"
  - Lists each customized file with indentation
- Implement main init logic in `run_init_command()`:
  - Parse flags (--force, --yes)
  - Detect git repository root
  - Check if `.lw_coder/` exists
  - Handle all 4 initialization cases (see Functional Requirements)
  - For Case 3 & 4: detect customizations and warn user
  - Use AtomicInitializer for safe operations
  - Display appropriate success/error messages
- Add init subcommand to `src/lw_coder/cli.py`:
  - Add to argument parser: `subparsers.add_parser("init", help="Initialize lw_coder in git repository")`
  - Add `--force` flag: `action="store_true"`
  - Add `--yes` flag: `action="store_true"`
  - Wire to `run_init_command()`
- Update CLI help text and command list

**Acceptance Criteria:**
- Interactive prompts work correctly
- --yes flag skips prompts
- All 4 initialization cases handled correctly
- Clear success/error messages
- CLI integration follows existing patterns
- `lw_coder init --help` shows appropriate help text

### 5. Implement Comprehensive Test Suite

**Objective:** Ensure init command works correctly, reusing existing test infrastructure.

**Tasks:**

**A. Reuse Existing Fixtures** (from `tests/conftest.py`):
- ✅ `git_repo` fixture - Already creates temporary git repository
- ✅ `GitRepo` class - Helper for git operations
- ✅ `write_plan()` helper - For creating plan files if needed
- ✅ `monkeypatch` - Standard pytest fixture for mocking

**B. Add New Fixture** (in `tests/test_init_command.py`):
- `initialized_repo(git_repo)`: Repository with `.lw_coder/` already initialized
  - Calls init_command to create initial state
  - Returns git_repo with .lw_coder/ directory present

**C. Create Unit Tests** (`tests/test_init_command.py`):
- Test init-specific functionality (NOT git detection - already tested):
  ```python
  # Hash calculation utilities
  def test_calculate_file_hash(tmp_path)
  def test_load_version_file(tmp_path)
  def test_detect_customizations(tmp_path)

  # Init command logic (uses git_repo fixture)
  def test_init_creates_lw_coder_directory(git_repo)
  def test_init_copies_judges(git_repo)
  def test_init_copies_optimized_prompts(git_repo)
  def test_init_copies_version_file(git_repo)
  def test_init_version_file_includes_hashes(git_repo)
  def test_init_preserves_directory_structure(git_repo)
  def test_init_version_file_valid_json(git_repo)

  # Force flag behavior (uses initialized_repo fixture)
  def test_init_fails_when_exists_without_force(initialized_repo)
  def test_init_force_prompts_for_overwrite(initialized_repo, monkeypatch)
  def test_init_force_yes_overwrites_without_prompt(initialized_repo)
  def test_init_force_respects_no_to_judges(initialized_repo, monkeypatch)
  def test_init_force_respects_no_to_prompts(initialized_repo, monkeypatch)

  # Customization detection (uses initialized_repo fixture)
  def test_init_detects_customized_judges(initialized_repo)
  def test_init_detects_customized_prompts(initialized_repo)
  def test_init_warns_about_customizations(initialized_repo, capsys)

  # Atomic operations
  def test_init_rollback_on_disk_full(git_repo, monkeypatch)
  def test_init_rollback_on_permission_error(git_repo, monkeypatch)
  ```

**D. Augment Existing Tests** (`tests/test_cli.py`):
- ADD init command CLI tests alongside existing code/plan/finalize tests:
  ```python
  def test_init_command_success(monkeypatch, git_repo)
  def test_init_command_with_force(monkeypatch, git_repo)
  def test_init_command_with_yes(monkeypatch, git_repo)
  def test_init_command_help_text(capsys)
  ```
- Follow existing pattern: mock `run_init_command()` and verify arguments
- DON'T duplicate - add to existing file, follow existing test structure

**E. Skip Redundant Tests**:
- ❌ DON'T test `find_repo_root()` - already tested in `tests/test_repo_utils.py` (lines 17-61)
- ❌ DON'T test worktree creation - already tested extensively
- ❌ DON'T test git operations - already covered by existing tests

**F. Test Implementation Notes**:
- Use parametrized tests where appropriate (follow existing patterns)
- Test both success and failure paths
- Mock user input using `monkeypatch.setattr("sys.stdin", ...)` (see test_cli.py examples)
- Use `pytest.fail()` for missing dependencies, not `pytest.skip()` (per best practices)
- Use real file operations (no mocking of file I/O) with tmp_path

**Acceptance Criteria:**
- All test cases pass
- Code coverage >90% for init_command.py
- Tests follow `docs/BEST_PRACTICES.md` guidelines
- Tests reuse existing fixtures (git_repo, monkeypatch, etc.)
- Tests augment test_cli.py instead of duplicating patterns
- No redundant tests for already-covered functionality
- Atomic rollback verified through tests

### 6. Update Documentation

**Objective:** Document init command cohesively in existing docs.

**Tasks:**
- Update `CLAUDE.md`:
  - Add init command to CLI Usage section:
    - `lw_coder init` - Initialize lw_coder in current git repository
    - `lw_coder init --force` - Reinitialize with prompts
    - `lw_coder init --force --yes` - Reinitialize without prompts (CI/CD)
- Update `README.md` cohesively:
  - Add new "Quick Start" section after "Installation" with workflow:
    ```markdown
    ## Quick Start

    1. Install lw_coder (see Installation)
    2. Configure credentials in ~/.lw_coder/.env (see Configuration)
    3. Initialize your project: `cd your-project && lw_coder init`
    4. Create a plan: `lw_coder plan --text "your feature idea"`
    5. Implement it: `lw_coder code <plan_id>`
    ```
  - Add "Init Command" section after "Setup and Authentication":
    - Brief description of what init does
    - When to use it (first time in a new project)
    - What it creates (.lw_coder/judges/, .lw_coder/optimized_prompts/, VERSION)
    - Note about customization detection with --force
  - Integrate naturally with existing structure (not bolted on)
- Add docstrings to all functions:
  - Follow existing codebase pattern (NO examples - not used in codebase)
  - Clear descriptions of parameters, return values, exceptions
  - Brief, focused documentation

**Acceptance Criteria:**
- CLAUDE.md updated with init command examples
- README.md flows naturally with new Quick Start and Init Command sections
- No docs/TEMPLATES.md file created (not needed - obvious from code)
- All functions have clear docstrings following existing patterns
- Documentation reviewed for cohesiveness and clarity


## Deliverables

1. **Frozen Template Bundle** (`src/lw_coder/init_templates/`)
   - All current judges frozen at current state
   - All current optimized prompts frozen at current state
   - VERSION file with metadata
   - Included in package distribution

2. **Init Command Implementation** (`src/lw_coder/init_command.py`)
   - Git repository detection
   - Atomic initialization with rollback
   - Interactive prompts with --yes override
   - All 4 initialization cases handled
   - Comprehensive error handling

3. **CLI Integration** (updated `src/lw_coder/cli.py`)
   - `lw_coder init` subcommand
   - `--force` and `--yes` flags
   - Proper help text

4. **Comprehensive Test Suite** (`tests/test_init_command.py`)
   - Unit tests for all functions
   - Integration tests for full workflow
   - Parametrized tests for scenarios
   - Atomic rollback verification
   - >90% code coverage

5. **Documentation**
   - Updated CLAUDE.md with init command
   - Updated README.md with Quick Start and Init Command sections (cohesive flow)
   - Clear docstrings following existing patterns (no examples)

6. **Working Command**
   - `lw_coder init` bootstraps new projects
   - `lw_coder init --force` allows re-initialization with interactive prompts
   - `lw_coder init --force --yes` enables CI/CD automation
   - Clear error messages guide users
   - Customization detection warns before overwriting

## Out of Scope

The following features are explicitly NOT included in this initial implementation but may be added in future iterations:

1. **Template Upgrade Functionality**
   - No `lw_coder init --upgrade` command
   - No automatic template updates
   - No migration between template versions
   - Rationale: Focus on initial implementation; upgrade logic is complex and can be added later

2. **Template Drift Detection**
   - No `lw_coder init --check-drift` command
   - No comparison between local and package templates
   - Rationale: Not needed for initial adoption; can be added when upgrade functionality is implemented

3. **Profile System**
   - No `--profile` flag (minimal, standard, comprehensive, etc.)
   - No domain-specific templates (web, ML, devops, etc.)
   - Rationale: Current template set is small; profiles make sense as template library grows

4. **Custom Template Sources**
   - No fetching from GitHub releases
   - No custom template repositories
   - No URL-based template sources
   - Rationale: Package-bundled templates sufficient for initial implementation

5. **Template Inheritance**
   - No extending base templates
   - No partial overrides
   - Users must copy and modify entire files
   - Rationale: Advanced feature; initial implementation focuses on simple file copying

6. **Smart Merge Strategies**
   - No three-way merge
   - No interactive diff viewing
   - Simple overwrite-or-skip logic only
   - Rationale: Complex; can be added when upgrade functionality is implemented

7. **Backup Files**
   - No automatic backup creation before overwrite
   - No `.backup` files
   - Rationale: User explicitly confirms overwrite; git provides version control

8. **Template Validation in CI**
   - No automated template quality checks in CI/CD
   - No schema validation for judges/prompts
   - Rationale: Can be added as templates evolve; initial focus is on distribution

9. **Configuration-Based Templates**
   - No reference-based system (all files copied)
   - No symlink strategy
   - Rationale: Simpler to implement file copying; can migrate to config-based approach later if needed

10. **Cross-Platform Support**
    - Linux only (matches lw_coder's current support)
    - No macOS or Windows support
    - Rationale: Aligns with existing platform constraints

11. **Project-Level config.toml**
    - Not created by init (config.toml is being removed from codebase)
    - Rationale: Configuration system is changing

12. **Home-Level Setup**
    - No checking/creating `~/.lw_coder/.env`
    - No validation of API keys
    - Rationale: Separate concern from project initialization

13. **CLAUDE.md Template**
    - No default CLAUDE.md creation
    - Users create project documentation themselves
    - Rationale: Highly project-specific; no one-size-fits-all template

## Test Cases

```gherkin
Feature: Initialize lw_coder in git repository
  As a developer adopting lw_coder
  I want to initialize my project with baseline templates
  So that I can start using lw_coder quickly with best practices

  Scenario: Initialize new project
    Given I am in a git repository
    And the .lw_coder directory does not exist
    When I run "lw_coder init"
    Then the .lw_coder directory should be created at repository root
    And the .lw_coder/judges directory should contain frozen judges
    And the .lw_coder/optimized_prompts directory should contain frozen prompts
    And the .lw_coder/VERSION file should contain version metadata
    And I should see a success message with next steps

  Scenario: Fail when not in git repository
    Given I am not in a git repository
    When I run "lw_coder init"
    Then the command should fail with exit code 1
    And I should see an error message "Not in a git repository"
    And I should see a suggestion to run "git init"

  Scenario: Initialize from subdirectory
    Given I am in a subdirectory of a git repository
    And the .lw_coder directory does not exist at repository root
    When I run "lw_coder init"
    Then the .lw_coder directory should be created at repository root
    And not in the current subdirectory

  Scenario: Fail when already initialized without force
    Given I am in a git repository
    And the .lw_coder directory already exists
    When I run "lw_coder init"
    Then the command should fail with exit code 1
    And I should see an error message mentioning "--force"
    And the existing .lw_coder directory should not be modified

  Scenario: Reinitialize with force and selective overwrite
    Given I am in a git repository
    And the .lw_coder directory already exists
    And I have not customized any templates
    When I run "lw_coder init --force"
    And I answer "yes" to overwrite judges
    And I answer "no" to overwrite prompts
    Then the judges should be overwritten with frozen versions
    And the prompts should remain unchanged
    And I should see a success message

  Scenario: Warn about customized templates before overwriting
    Given I am in a git repository
    And the .lw_coder directory already exists
    And I have customized "judges/code-reuse.md"
    And I have customized "optimized_prompts/claude-code-cli/sonnet/main.md"
    When I run "lw_coder init --force"
    Then I should see "WARNING: 1 judges have been customized from baseline"
    And I should see "  - judges/code-reuse.md"
    When I answer "yes" to overwrite judges
    Then I should see "WARNING: 1 prompts have been customized from baseline"
    And I should see "  - optimized_prompts/claude-code-cli/sonnet/main.md"
    When I answer "no" to overwrite prompts
    Then the judges should be overwritten with frozen versions
    And the prompts should remain unchanged with my customizations
    And I should see a success message

  Scenario: Reinitialize with force and yes flag
    Given I am in a git repository
    And the .lw_coder directory already exists
    When I run "lw_coder init --force --yes"
    Then I should not be prompted for confirmation
    And the judges should be overwritten with frozen versions
    And the prompts should be overwritten with frozen versions
    And I should see a success message

  Scenario: Rollback on failure
    Given I am in a git repository
    And the .lw_coder directory does not exist
    And the filesystem will encounter an error during initialization
    When I run "lw_coder init"
    Then the command should fail with exit code 1
    And the .lw_coder directory should not exist
    And no partial files should be created
    And I should see a clear error message

Feature: Template version tracking
  As a lw_coder user
  I want to know which template version I have
  So that I can understand my starting point for customization

  Scenario: VERSION file created during initialization
    Given I am in a git repository
    And the .lw_coder directory does not exist
    When I run "lw_coder init"
    Then the .lw_coder/VERSION file should exist
    And it should contain valid JSON
    And it should include template_version field
    And it should include lw_coder_version field
    And it should include frozen_date field
    And it should include files field with hashes for all templates

  Scenario: Detect customized templates by hash comparison
    Given I am in a git repository
    And I have initialized lw_coder previously
    And the .lw_coder/VERSION file contains original hashes
    When I modify "judges/code-reuse.md"
    And I run "lw_coder init --force"
    Then the system should detect that "judges/code-reuse.md" has been customized
    And I should see a warning before being prompted to overwrite

Feature: CI/CD automation support
  As a DevOps engineer
  I want to initialize lw_coder non-interactively
  So that I can include it in automated workflows

  Scenario: Non-interactive initialization with yes flag
    Given I am in a git repository
    And the .lw_coder directory already exists
    When I run "lw_coder init --force --yes" in a non-interactive environment
    Then the command should complete without waiting for input
    And both judges and prompts should be overwritten
    And the command should exit with code 0

Feature: Directory structure preservation
  As a lw_coder user
  I want the template structure preserved exactly
  So that the system can find templates in expected locations

  Scenario: Template directory structure matches frozen bundle
    Given I am in a git repository
    When I run "lw_coder init"
    Then the .lw_coder/judges directory structure should match init_templates/judges
    And the .lw_coder/optimized_prompts directory structure should match init_templates/optimized_prompts
    And all subdirectories should be created
    And all files should be present with correct names
```
