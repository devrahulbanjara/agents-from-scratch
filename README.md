# AI Code Assistant Agent

An intelligent coding agent that can explore codebases, read files, execute code, and make changes using function calling and iterative loops.

## Setup

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Set up your API key:**
   Create a `.env` file in the project root:
   ```bash
   echo "GEMINI_API_KEY=your_api_key_here" > .env
   ```
   Or manually create `.env` and add:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

## Usage

### Basic Usage

Run the agent with a prompt:

```bash
uv run main.py "your prompt here"
```

### Examples

**Explore and understand code:**
```bash
uv run main.py "Explain how the calculator renders results to the console"
```

**List files:**
```bash
uv run main.py "List all files in the current directory"
```

**Read and analyze code:**
```bash
uv run main.py "Read main.py and explain what it does"
```

**Multi-step exploration:**
```bash
uv run main.py "Read the calculator code, run the tests, and tell me if they pass"
```

**Make changes:**
```bash
uv run main.py "Fix the bug in the calculator"
```

### Verbose Mode

Add `--verbose` to see detailed information about each iteration:

```bash
uv run main.py "your prompt" --verbose
```

This will show:
- Each iteration number
- Token usage (prompt and response tokens)
- Function calls being made
- Function responses

### Example with Verbose Output

```bash
uv run main.py "List files and read main.py" --verbose
```

Output will look like:
```
User prompt: List files and read main.py

--- Iteration 1 ---
Prompt tokens: 425
Response tokens: 12
 - Calling function: get_files_info
-> {'result': '...'}

--- Iteration 2 ---
Prompt tokens: 551
Response tokens: 51
 - Calling function: get_file_content
-> {'result': '...'}

--- Iteration 3 ---
Prompt tokens: 872
Response tokens: 82
Final response:
[Agent's explanation]
```

## How It Works

The agent uses an iterative loop that:

1. **Sends your prompt** to the Gemini API
2. **Receives a response** that may include function calls
3. **Executes function calls** (like reading files, running code, etc.)
4. **Adds results to conversation history** so the agent can learn from them
5. **Iterates** until the agent has enough information to provide a final answer
6. **Returns the final response** when no more function calls are needed

The agent can make up to **20 iterations** to complete a task, preventing infinite loops while allowing complex multi-step operations.

## Available Functions

The agent has access to these tools:

- **`get_files_info`**: List files and directories
- **`get_file_content`**: Read file contents
- **`run_python_file`**: Execute Python files with arguments
- **`write_file`**: Write or overwrite files

All paths are relative to the working directory (set in `config.py`, currently `./calculator`).

## Configuration

- **Working Directory**: Set in `config.py` (`WORKING_DIR`)
- **Model**: Currently using `gemini-2.5-flash-lite` (can be changed in `main.py`)
- **Max Iterations**: 20 (can be adjusted in `main.py`)

## Tips

- Be specific in your prompts - the agent works better with clear instructions
- Use verbose mode when debugging or understanding what the agent is doing
- The agent can chain multiple operations together automatically
- All file paths should be relative to the working directory
