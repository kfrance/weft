FROM node:20-slim

# Install essential development tools that droid needs for code analysis and editing.
# Droid uses these tools to search codebases (ripgrep, fd), process text (sed, awk, jq),
# analyze file structures (tree, find), and build/compile code (make, gcc, python).
# Note: Using Debian Slim instead of Alpine because droid binary requires glibc
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core utilities
    bash \
    curl \
    git \
    ca-certificates \
    # Text processing and search tools
    ripgrep \
    fd-find \
    grep \
    sed \
    gawk \
    jq \
    # File and directory tools
    tree \
    findutils \
    coreutils \
    diffutils \
    # Build tools
    make \
    build-essential \
    # Programming languages/runtimes
    python3 \
    python3-pip \
    # Text editors
    vim \
    nano \
    && rm -rf /var/lib/apt/lists/* \
    # Create symlink for fd (Debian calls it fd-find)
    && ln -s /usr/bin/fdfind /usr/bin/fd

# Create non-root user for running droid
RUN useradd -m -d /home/droiduser -s /bin/bash droiduser

# Set up workspace directory with appropriate permissions
WORKDIR /workspace
RUN chown droiduser:droiduser /workspace

# Switch to non-root user before installing droid
USER droiduser

# Install droid CLI as droiduser (note: in production, pin to specific version and verify checksum)
RUN curl -fsSL https://app.factory.ai/cli | sh

# Add droid to PATH
ENV PATH="/home/droiduser/.local/bin:${PATH}"

CMD ["/bin/bash"]
