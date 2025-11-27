---
plan_id: sdk-network-no-proxy
status: done
evaluation_notes: []
git_sha: 93dfd62d77872f52458428189edcc7bcad050119
---

# SDK Network Access via NO_PROXY Environment Variable

## Objectives

Enable network access in SDK-spawned Claude Code sessions by setting `NO_PROXY="*"` environment variable, allowing tools like WebFetch to function correctly during SDK execution.

## Requirements & Constraints

### Functional Requirements
- SDK sessions must be able to make network requests (e.g., WebFetch tool)
- Environment variable changes must be scoped to the SDK session only
- Original `NO_PROXY` value must be restored after session completes
- Cleanup must occur even if SDK session raises exceptions

### Technical Constraints
- **Uses documented Claude Code feature**: `NO_PROXY` environment variable is officially documented at https://code.claude.com/docs/en/settings
  - `NO_PROXY="*"` bypasses proxy for all network requests
  - Setting applies at process startup (inherited by SDK-spawned subprocess)
- **Security Trade-off**: SDK sessions get unrestricted network access with no audit trail
- **Environment Inheritance**: Relies on SDK subprocess inheriting parent process environment

### Implementation Requirements
- Use try/finally pattern to guarantee environment restoration
- Add code comments explaining the NO_PROXY usage and why it's scoped
- Implement comprehensive test coverage to verify behavior
- Add debug logging for troubleshooting

## Work Items

### 1. Modify `src/lw_coder/sdk_runner.py`

**Objective**: Enable network access for SDK sessions using documented `NO_PROXY` environment variable.

**Changes to `run_sdk_session()` function**:
- Add `import os` at top of file
- Save current `NO_PROXY` value before creating SDK client: `original_no_proxy = os.environ.get("NO_PROXY")`
- Set `NO_PROXY="*"` to bypass proxy for all requests
- Use try/finally block to guarantee restoration
- In finally block: restore original value if it existed, or remove `NO_PROXY` if it didn't exist originally
- Add comments explaining why NO_PROXY is set (enables WebFetch in SDK sessions)
- Add debug logging: "Set NO_PROXY='*' for SDK session network access" and "Restored NO_PROXY to original value"

**Reference**: NO_PROXY documented at https://code.claude.com/docs/en/settings

### 2. Update Security Documentation

**Objective**: Document the security trade-off of enabling unrestricted network access.

**Add section to `docs/THREAT_MODEL.md`** under "Security Design Decisions":

**Section title**: "SDK Network Access"

**Content to document**:
- **Decision**: Enable unrestricted network access for SDK sessions via `NO_PROXY="*"`
- **Rationale**: SDK sessions need network access for WebFetch and similar tools to function
- **Risk Accepted**: SDK sessions can make requests to any domain without audit trail or allowlist
  - Potential for injection attacks if malicious code is executed
  - No visibility into what external resources are accessed
- **Justification**: Local developer CLI tool with trusted codebase; external attack surface is low
  - Repository code is under developer control (same trust boundary as rest of system)
  - Not a multi-tenant or production system
  - Developer controls what code is executed
- **Mitigation**: Environment variable is scoped to SDK session only (restored after completion)

### 3. Create Integration Tests

**Objective**: Verify NO_PROXY enables network access and environment is properly restored.

**Create `tests/test_sdk_network.py`** with 4 integration tests:

1. **`test_sdk_network_fails_without_no_proxy`**
   - Create SDK session WITHOUT setting NO_PROXY
   - Use prompt that requires WebFetch tool
   - Assert: Session fails with network/sandbox error
   - Purpose: Demonstrates the problem

2. **`test_sdk_network_succeeds_with_no_proxy`**
   - Create SDK session WITH NO_PROXY="*"
   - Use same WebFetch prompt
   - Assert: Session succeeds and returns data
   - Purpose: Validates the solution

3. **`test_no_proxy_restored_after_successful_session`**
   - Set NO_PROXY="custom_value" before test
   - Run successful SDK session
   - Assert: NO_PROXY reverted to "custom_value" after session
   - Purpose: Verifies environment cleanup on success path

4. **`test_no_proxy_restored_on_sdk_error`**
   - Set NO_PROXY="custom_value" before test
   - Run SDK session that raises exception
   - Assert: Exception propagates AND NO_PROXY still reverted to "custom_value"
   - Purpose: Verifies finally block guarantees cleanup

## Deliverables

1. **Modified `src/lw_coder/sdk_runner.py`**
   - `run_sdk_session()` function with NO_PROXY save/restore logic
   - Import `os` module
   - Code comments explaining NO_PROXY usage for SDK network access
   - Debug logging for NO_PROXY changes

2. **Updated `docs/THREAT_MODEL.md`**
   - New "SDK Network Access" section documenting security trade-off
   - Explains risk acceptance for unrestricted network access
   - Justifies decision based on local developer tool threat model

3. **New test file `tests/test_sdk_network.py`**
   - Test 1: `test_sdk_network_fails_without_no_proxy` - Demonstrates problem
   - Test 2: `test_sdk_network_succeeds_with_no_proxy` - Validates solution
   - Test 3: `test_no_proxy_restored_after_successful_session` - Cleanup verification
   - Test 4: `test_no_proxy_restored_on_sdk_error` - Exception safety verification

4. **All tests passing**
   - Run `uv run pytest -m integration` to verify integration tests
   - Run `uv run pytest` to ensure no regressions

## Out of Scope

The following are explicitly out of scope for this plan:

### Not Included
- **Security hardening**: Adding network access allowlists or audit logging (blanket "*" access accepted for now)
- **Concurrent session tests**: Testing NO_PROXY isolation across parallel sessions
- **Platform-specific tests**: Explicit testing on Windows/macOS (Linux only initially)
- **Documentation updates**: README/SECURITY.md updates about network access (can be done separately)

### Future Enhancements
- Add opt-in flag `--enable-sdk-network` for explicit user control
- Implement audit logging for network access tracking
- Add allowlist-based network restrictions instead of blanket "*" access (e.g., `NO_PROXY="trusted.internal,api.example.com"`)

### Known Limitations
- No visibility into what network resources SDK sessions access
- Assumes subprocess environment inheritance
- Blanket network access (all domains) rather than allowlist
