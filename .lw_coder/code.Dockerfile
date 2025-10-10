# Repo-specific Dockerfile for lw_coder code command
# This Dockerfile extends the base lw_coder_droid image with repo-specific
# dependencies and MCP server installations.

ARG BASE_IMAGE=lw_coder_droid:latest
FROM ${BASE_IMAGE}

# Switch to droiduser for installations
USER droiduser
WORKDIR /home/droiduser

# Install context7 MCP server
# This allows droid to access up-to-date library documentation
# If this fails, the build will fail - check network connectivity and MCP server availability
RUN droid mcp add --transport http context7 https://mcp.context7.com/mcp

# Add any repo-specific setup here
# Examples:
# - Install additional language runtimes
# - Add project-specific CLI tools
# - Configure environment variables

# Set working directory to workspace (will be mounted at runtime)
WORKDIR /workspace

# Default command (will be overridden by docker run)
CMD ["/bin/bash"]
