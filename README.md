# AI Code Assistant Agent

A production-ready AI coding agent built with Google's Gemini API. Provides file operations, code search, git integration, and code execution capabilities with comprehensive security controls and async I/O.

## Features

- **Async File Operations** - Read, write, list, and search files with `aiofiles` and `pathlib`
- **Code Execution** - Execute Python code using Gemini's native code execution sandbox
- **Git Integration** - Status checks, diffs, and commits with automatic secret detection
- **Pattern Search** - Regex-based search across codebases with binary file filtering
- **Security Controls** - Path traversal prevention, file size limits, dangerous extension blocking
- **Rate Limiting** - Configurable API and tool call rate limits to prevent quota exhaustion
- **Structured Errors** - AI-readable error messages with suggestions and context
- **Session Tracking** - Thread-safe operation tracking with async locks

## Installation

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Google Gemini API key

### Install uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# With pip
pip install uv
```

### Clone and Setup

```bash
# Clone the repository
git clone https://github.com/devrahulbanjara/agents-from-scratch.git
cd agents-from-scratch

# Install dependencies with uv
uv sync
```

### Configure API Key

Create a `.env` file in the project root:

```bash
echo "GEMINI_API_KEY=your_api_key_here" > .env
```

Or manually create `.env`:

```
GEMINI_API_KEY=your_api_key_here
```

> [!WARNING]
> Never commit your `.env` file to version control. It's already included in `.gitignore`.

> [!NOTE]
> Get your Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)

## Usage

### Basic Usage

```bash
uv run main.py "your prompt here"
```

### With Custom Workspace

```bash
uv run main.py "analyze the code" --workspace ./my-project
```

### With Verbose Logging

```bash
uv run main.py "list all files" --verbose --log-level DEBUG
```

### With Session Summary

```bash
uv run main.py "refactor main.py" --summary
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `prompt` | Task description for the agent | Required |
| `--workspace` | Working directory path | `./calculator` |
| `--verbose` | Enable detailed logging | `False` |
| `--summary` | Show session statistics after completion | `False` |
| `--log-level` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |

## Available Tools

The agent has access to the following operations:

### File Operations

```python
read_file(path: str, max_chars: int = 10000) -> str
```
Read file contents with automatic truncation.

**Limits:**
- Maximum file size: 100KB
- Returns truncated content if exceeds `max_chars`

**Errors:**
- `file_not_found` - File does not exist
- `file_too_large` - File exceeds size limit
- `permission_denied` - Path outside workspace

---

```python
write_file(path: str, content: str) -> str
```
Write or overwrite file contents.

**Limits:**
- Maximum content size: 1MB
- Blocked extensions: `.exe`, `.bat`, `.sh`, `.cmd`, `.scr`, `.com`

**Errors:**
- `file_too_large` - Content exceeds size limit
- `permission_denied` - Blocked file type or path violation

---

```python
list_files(directory: str = ".") -> str
```
List files and directories with sizes.

**Returns:** Formatted list with file sizes and type indicators

---

```python
create_directory(path: str, recursive: bool = True) -> str
```
Create directories with optional parent creation.

### Search Operations

```python
search_files(
    pattern: str,
    file_extensions: list[str] | None = None,
    case_sensitive: bool = False,
    max_results: int = 50
) -> str
```
Regex pattern search across files.

**Limits:**
- Maximum files scanned: 1000
- Maximum results returned: 100
- Skips binary files automatically
- Skips hidden files/directories (starting with `.`)

**Errors:**
- `invalid_regex` - Malformed regex pattern

**Example:**
```python
# Search for TODO comments in Python files
search_files(r"TODO:.*", file_extensions=[".py"])

# Case-sensitive search
search_files("ClassName", case_sensitive=True)
```

### Git Operations

```python
git_status() -> str
```
Get current branch, modified files, and recent commits.

---

```python
git_diff(file_path: str | None = None) -> str
```
Show staged and unstaged changes.

---

```python
git_commit(message: str, add_all: bool = False) -> str
```
Create git commit with security checks.

> [!IMPORTANT]
> When `add_all=True`, the agent scans for sensitive files before staging:
> - `.env` files and variants
> - Private keys (`id_rsa`, `.pem`, `.key`)
> - Credential files
> - Files containing API keys, tokens, or passwords

**Errors:**
- `git_error` - Sensitive files detected, empty message, or commit failure

### Code Execution

The agent can execute Python code using Gemini's built-in code execution tool. This is useful for:
- Calculations and data analysis
- Testing code snippets
- Quick prototypes

> [!NOTE]
> Code execution runs in Gemini's sandbox, not your local environment.

## Security Model

### Path Security

All file operations are restricted to the workspace directory:

```python
# Allowed
read_file("src/main.py")
read_file("../calculator/test.py")  # If within workspace

# Blocked - raises permission_denied
read_file("/etc/passwd")
read_file("../../outside/file.txt")
```

### File Size Limits

| Operation | Limit | Configurable |
|-----------|-------|--------------|
| Read | 100KB | Yes - via `max_chars` parameter |
| Write | 1MB | No |
| Search | 1MB per file | No |

### Rate Limiting

Default limits to prevent API quota exhaustion:

- **API calls:** 10 per 60 seconds
- **Tool calls:** 30 per 60 seconds

Limits are enforced with automatic backoff and logging.

### Blocked Extensions

The following file types cannot be written:
- `.exe`, `.bat`, `.sh`, `.cmd`, `.scr`, `.com`

### Git Commit Security

Sensitive file patterns blocked from commits:
- `\.env` and variants (`.env.local`, `.env.production`)
- Private keys: `id_rsa`, `id_dsa`, `id_ecdsa`, `.pem`, `.key`
- Credential files: `credentials`, `.aws/`, `.ssh/`
- Secrets files: `password.*`, `secrets.*`

Content scanning detects:
- API keys: `api_key = "..."`
- Tokens: `token = "..."`
- Stripe keys: `sk_live_...`
- GitHub tokens: `ghp_...`

## Error Handling

All errors follow a structured format:

```json
{
  "error_code": "file_not_found",
  "message": "File 'config.json' does not exist",
  "suggestions": [
    "Check the file path spelling",
    "Use list_files to see available files",
    "Create the file first with write_file"
  ],
  "context": {
    "requested_path": "config.json"
  }
}
```

### Common Error Codes

| Code | Description | Common Causes |
|------|-------------|---------------|
| `file_not_found` | File does not exist | Typo, wrong path, file not created |
| `permission_denied` | Access denied | Path outside workspace, blocked extension |
| `file_too_large` | File exceeds size limit | File > 100KB (read) or > 1MB (write) |
| `invalid_regex` | Malformed regex pattern | Unescaped special characters |
| `git_error` | Git operation failed | Sensitive files, empty message, no changes |

## Session Tracking

The agent tracks all operations during execution:

```bash
uv run main.py "refactor code" --summary
```

**Output:**
```
=== SESSION SUMMARY ===
Files read: 3
Files written: 2
Commands run: 0
Searches performed: 1

Files read: main.py, utils.py, config.py
Files written: main.py, utils.py
```

## Examples

### Explore Codebase

```bash
uv run main.py "List all Python files and show me the main entry point"
```

### Find and Fix Issues

```bash
uv run main.py "Search for TODO comments and create a summary"
```

### Code Analysis

```bash
uv run main.py "Read tests.py and tell me the test coverage"
```

### Refactoring

```bash
uv run main.py "Refactor calculator.py to use type hints"
```

### Git Workflow

```bash
uv run main.py "Show git status, review changes, and create a commit"
```

> [!WARNING]
> Always review changes before committing. Use `git_diff` to inspect modifications.

## Programmatic Usage

```python
import asyncio
from agent import DeveloperAgent

async def main():
    agent = DeveloperAgent(working_dir="./my-project")
    
    result = await agent.run(
        prompt="List all files and explain the project structure",
        verbose=True,
        max_iterations=20
    )
    
    print(f"Response: {result.response}")
    print(f"Iterations: {result.iterations}")
    print(f"Tokens used: {result.tokens_used}")
    print(f"Functions called: {result.functions_called}")
    
    if result.errors:
        print(f"Errors: {result.errors}")

asyncio.run(main())
```

## Architecture

```
agents-from-scratch/
├── agent.py              # Main agent with iteration loop
├── tools.py              # File, search, and git operations
├── errors.py             # Structured error types
├── schema.py             # Session state tracking
├── rate_limiter.py       # API rate limiting
├── logging_config.py     # Structured logging setup
├── models.py             # Data models (AgentResult)
├── prompts.py            # System prompt configuration
├── main.py               # CLI entry point
├── test_agent.py         # Test suite
├── test_binary_detection.py  # Binary file tests
├── pyproject.toml        # Dependencies
└── calculator/           # Example workspace
    ├── main.py
    ├── tests.py
    └── pkg/
        ├── calculator.py
        └── render.py
```

### Key Design Decisions

- **Async I/O:** All file and subprocess operations use `aiofiles` and `asyncio.subprocess`
- **Thread Safety:** Session state uses `asyncio.Lock` for concurrent access
- **Manual Iteration:** Explicit control loop for transparency and debugging
- **Centralized Security:** Single `_secure_path` method validates all file paths
- **Structured Errors:** AI-readable error format with suggestions

## Configuration Defaults

Modify `CodebaseTools.__init__` in `tools.py`:

```python
self.max_read_size = 100 * 1024           # 100KB
self.max_write_size = 1 * 1024 * 1024     # 1MB
self.max_search_file_size = 1 * 1024 * 1024  # 1MB
self.max_files_per_search = 1000
self.max_search_results = 100
```

Modify rate limits in `DeveloperAgent.__init__` in `agent.py`:

```python
self.api_rate_limiter = RateLimiter(max_calls=10, period=60.0)
self.tool_rate_limiter = RateLimiter(max_calls=30, period=60.0)
```

## Testing

Run the test suite:

```bash
# All tests
uv run test_agent.py

# Binary file detection
uv run test_binary_detection.py
```

Tests cover:
- File operations (read, write, list, create)
- Security limits (file size, dangerous extensions)
- Path traversal protection
- Search functionality
- Session state tracking

## Troubleshooting

### Agent hits iteration limit

**Cause:** Task requires more than 20 iterations (default)

**Solution:** Increase `max_iterations`:
```python
result = await agent.run(prompt="...", max_iterations=50)
```

### Rate limit errors

**Cause:** Too many API calls in short time

**Solution:** Adjust rate limits or wait for cooldown period

### File not found errors

**Cause:** Incorrect path or file doesn't exist

**Solution:**
1. Use `list_files` to verify file location
2. Check path is relative to workspace
3. Verify file exists in workspace

### Permission denied

**Cause:** Path outside workspace or blocked file type

**Solution:**
1. Ensure path is within workspace directory
2. Check file extension is not blocked
3. Verify workspace path is correct

### Import errors after cloning

**Cause:** Dependencies not installed

**Solution:**
```bash
uv sync
```

## Limitations

- **No streaming responses** - All responses returned after completion
- **Single workspace** - One workspace per agent instance
- **Text files only** - Binary files skipped in search, cannot be read
- **Local git only** - No remote operations (push, pull, fetch)
- **Python 3.12+** - Uses modern type hints (`|` union syntax)

## Contributing

Contributions are welcome. Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/improvement`)
3. Make changes with tests
4. Run test suite (`uv run test_agent.py`)
5. Submit pull request

## License

MIT License - see LICENSE file for details

## Changelog

### v0.1.0 (In Development)

- Initial release
- Async file operations with aiofiles
- Git integration with secret detection
- Rate limiting and retry logic
- Structured error handling
- Session tracking with thread safety
- Binary file detection in search
- Comprehensive test suite

## Support

- **Issues:** https://github.com/devrahulbanjara/agents-from-scratch/issues
- **Discussions:** https://github.com/devrahulbanjara/agents-from-scratch/discussions

## Related Projects

- [Google Gemini API](https://ai.google.dev/gemini-api/docs)
- [aiofiles](https://github.com/Tinche/aiofiles)
- [loguru](https://github.com/Delgan/loguru)
- [uv](https://github.com/astral-sh/uv)

---

**Star History**

[![Star History Chart](https://api.star-history.com/svg?repos=devrahulbanjara/agents-from-scratch&type=Date)](https://star-history.com/#devrahulbanjara/agents-from-scratch&Date)