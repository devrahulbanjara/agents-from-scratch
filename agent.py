import asyncio
import os
import random
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, cast

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from errors import AgentError
from logging_config import logger
from models import AgentResult
from prompts import SYSTEM_PROMPT
from rate_limiter import RateLimiter
from schema import SessionState
from tools import CodebaseTools


class DeveloperAgent:
    def __init__(self, working_dir: str):
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")

        self.client = genai.Client(api_key=api_key)
        self.state = SessionState()
        self.tools = CodebaseTools(Path(working_dir).resolve(), self.state)
        self.api_rate_limiter = RateLimiter(max_calls=10, period=60.0)
        self.tool_rate_limiter = RateLimiter(max_calls=30, period=60.0)

    async def run(
        self, prompt: str, verbose: bool = False, max_iterations: int = 20
    ) -> AgentResult:
        logger.info(
            "Starting agent run", prompt=prompt[:100], max_iterations=max_iterations
        )

        tool_config = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="read_file",
                    description="Read the contents of a file",
                    parameters=cast(
                        types.Schema,
                        {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path to the file to read",
                                },
                                "max_chars": {
                                    "type": "integer",
                                    "description": "Maximum characters to read",
                                    "default": 10000,
                                },
                            },
                            "required": ["path"],
                        },
                    ),
                ),
                types.FunctionDeclaration(
                    name="write_file",
                    description="Write content to a file",
                    parameters=cast(
                        types.Schema,
                        {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path to the file to write",
                                },
                                "content": {
                                    "type": "string",
                                    "description": "Content to write to the file",
                                },
                            },
                            "required": ["path", "content"],
                        },
                    ),
                ),
                types.FunctionDeclaration(
                    name="list_files",
                    description="List files and directories",
                    parameters=cast(
                        types.Schema,
                        {
                            "type": "object",
                            "properties": {
                                "directory": {
                                    "type": "string",
                                    "description": "Directory to list",
                                    "default": ".",
                                }
                            },
                        },
                    ),
                ),
                types.FunctionDeclaration(
                    name="create_directory",
                    description="Create a new directory",
                    parameters=cast(
                        types.Schema,
                        {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path of the directory to create",
                                },
                                "recursive": {
                                    "type": "boolean",
                                    "description": "Create parent directories if needed",
                                    "default": True,
                                },
                            },
                            "required": ["path"],
                        },
                    ),
                ),
                types.FunctionDeclaration(
                    name="search_files",
                    description="Search for text patterns in files",
                    parameters=cast(
                        types.Schema,
                        {
                            "type": "object",
                            "properties": {
                                "pattern": {
                                    "type": "string",
                                    "description": "Text pattern to search for",
                                },
                                "file_extensions": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "File extensions to search in",
                                },
                                "case_sensitive": {
                                    "type": "boolean",
                                    "description": "Whether search is case sensitive",
                                    "default": False,
                                },
                                "max_results": {
                                    "type": "integer",
                                    "description": "Maximum number of results",
                                    "default": 50,
                                },
                            },
                            "required": ["pattern"],
                        },
                    ),
                ),
                types.FunctionDeclaration(
                    name="git_status",
                    description="Get git repository status",
                    parameters=cast(types.Schema, {"type": "object", "properties": {}}),
                ),
                types.FunctionDeclaration(
                    name="git_diff",
                    description="Get git diff for changes",
                    parameters=cast(
                        types.Schema,
                        {
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "Specific file to diff (optional)",
                                }
                            },
                        },
                    ),
                ),
                types.FunctionDeclaration(
                    name="git_commit",
                    description="Create a git commit",
                    parameters=cast(
                        types.Schema,
                        {
                            "type": "object",
                            "properties": {
                                "message": {
                                    "type": "string",
                                    "description": "Commit message",
                                },
                                "add_all": {
                                    "type": "boolean",
                                    "description": "Stage all changes before committing",
                                    "default": False,
                                },
                            },
                            "required": ["message"],
                        },
                    ),
                ),
            ],
            code_execution=types.ToolCodeExecution(),
        )

        messages = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        total_tokens = 0
        functions_called = 0
        errors: list[str] = []

        for iteration in range(max_iterations):
            logger.info("Agent iteration", iteration=iteration + 1)

            try:
                await self.api_rate_limiter.acquire()
                loop = asyncio.get_event_loop()

                def _generate_content():
                    return self.client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=messages,
                        config=types.GenerateContentConfig(
                            tools=[tool_config],
                            system_instruction=SYSTEM_PROMPT,
                            temperature=0.2,
                            max_output_tokens=8192,
                        ),
                    )

                async def call_api():
                    return await loop.run_in_executor(None, _generate_content)

                response = await self._call_with_retry(call_api)

                if response.usage_metadata:
                    prompt_tokens = response.usage_metadata.prompt_token_count
                    response_tokens = response.usage_metadata.candidates_token_count
                    total_tokens += prompt_tokens + response_tokens
                    logger.info(
                        "Token usage",
                        iteration=iteration + 1,
                        prompt_tokens=prompt_tokens,
                        response_tokens=response_tokens,
                        total_tokens=total_tokens,
                    )

                if response.candidates:
                    messages.append(response.candidates[0].content)

                if not response.function_calls:
                    logger.success(
                        "Agent completed successfully",
                        iterations=iteration + 1,
                        total_tokens=total_tokens,
                        functions_called=functions_called,
                        has_errors=len(errors) > 0,
                    )

                    return AgentResult(
                        response=response.text,
                        iterations=iteration + 1,
                        tokens_used=total_tokens,
                        functions_called=functions_called,
                        errors=errors,
                    )

                logger.info(
                    "Executing function calls",
                    count=len(response.function_calls),
                    functions=[fc.name for fc in response.function_calls],
                )

                function_responses = []
                for function_call in response.function_calls:
                    functions_called += 1

                    try:
                        await self.tool_rate_limiter.acquire()
                        result = await self._execute_function_call(function_call)
                        function_responses.append(
                            types.Part.from_function_response(
                                name=function_call.name, response={"result": result}
                            )
                        )
                        logger.success(
                            "Function executed successfully",
                            function=function_call.name,
                            result_length=len(str(result)),
                        )

                    except AgentError as e:
                        error_msg = f"{function_call.name}: {e}"
                        errors.append(error_msg)
                        logger.error(
                            "Function error",
                            function=function_call.name,
                            error_code=e.code.value,
                            error_message=e.message,
                        )

                        function_responses.append(
                            types.Part.from_function_response(
                                name=function_call.name, response={"error": e.to_dict()}
                            )
                        )

                    except Exception as e:
                        exc_type, exc_value, exc_tb = sys.exc_info()
                        tb_str = "".join(
                            traceback.format_exception(exc_type, exc_value, exc_tb)
                        )

                        error_msg = f"{function_call.name}: {e}"
                        errors.append(error_msg)
                        logger.error(
                            "Unexpected function error",
                            function=function_call.name,
                            error=str(e),
                            traceback=tb_str,
                            exc_info=True,
                        )

                        function_responses.append(
                            types.Part.from_function_response(
                                name=function_call.name,
                                response={
                                    "error": {
                                        "message": str(e),
                                        "type": type(e).__name__,
                                        "traceback": tb_str[-500:],
                                    }
                                },
                            )
                        )

                messages.append(types.Content(role="user", parts=function_responses))

            except genai_errors.ClientError as e:
                if (
                    hasattr(e, "status_code")
                    and e.status_code >= 400
                    and e.status_code < 500
                ):
                    logger.error(
                        "Client error", error=str(e), status_code=e.status_code
                    )
                    return AgentResult(
                        response=f"Error: Invalid request - {e}",
                        iterations=iteration + 1,
                        tokens_used=total_tokens,
                        functions_called=functions_called,
                        errors=[str(e)],
                    )
                raise
            except Exception as e:
                error_details = str(e)
                error_type = type(e).__name__
                
                if isinstance(e, RuntimeError) and "Failed after" in error_details:
                    if ":" in error_details:
                        error_details = error_details.split(":", 1)[1].strip()
                
                if "429" in error_details or "quota" in error_details.lower() or "RESOURCE_EXHAUSTED" in error_details:
                    logger.error(
                        "API quota exceeded",
                        iteration=iteration + 1,
                        error=error_details,
                        error_type=error_type,
                        suggestion="Check quota at https://ai.dev/rate-limit or upgrade plan",
                        exc_info=True,
                    )
                    user_message = (
                        "API Quota Exceeded\n\n"
                        "Your Gemini API key has exceeded its quota. Please:\n"
                        "1. Check your API quota at https://ai.dev/rate-limit\n"
                        "2. Wait for quota to reset, or\n"
                        "3. Upgrade your API plan\n\n"
                        f"Technical details: {error_details}"
                    )
                elif "401" in error_details or "403" in error_details or "invalid" in error_details.lower():
                    logger.error(
                        "API authentication error",
                        iteration=iteration + 1,
                        error=error_details,
                        error_type=error_type,
                        suggestion="Verify API key in .env file or get new key from https://aistudio.google.com/app/apikey",
                        exc_info=True,
                    )
                    user_message = (
                        "API Authentication Error\n\n"
                        "There's an issue with your API key. Please:\n"
                        "1. Verify your API key in .env file\n"
                        "2. Get a new key from https://aistudio.google.com/app/apikey\n"
                        "3. Make sure GEMINI_API_KEY is set correctly\n\n"
                        f"Technical details: {error_details}"
                    )
                else:
                    logger.error(
                        "Unrecoverable error",
                        iteration=iteration + 1,
                        error=error_details,
                        error_type=error_type,
                        exc_info=True,
                    )
                    user_message = f"Error: {error_details}\n\nError type: {error_type}"
                
                return AgentResult(
                    response=user_message,
                    iterations=iteration + 1,
                    tokens_used=total_tokens,
                    functions_called=functions_called,
                    errors=[error_details],
                )

        logger.warning("Maximum iterations reached", max_iterations=max_iterations)
        return AgentResult(
            response="Maximum iterations reached without completion",
            iterations=max_iterations,
            tokens_used=total_tokens,
            functions_called=functions_called,
            errors=errors,
        )

    async def _execute_function_call(self, function_call) -> str:
        function_name = function_call.name
        args = dict(function_call.args) if function_call.args else {}

        function_map: dict[str, Callable[..., Any]] = {
            "read_file": self.tools.read_file,
            "write_file": self.tools.write_file,
            "list_files": self.tools.list_files,
            "create_directory": self.tools.create_directory,
            "search_files": self.tools.search_files,
            "git_status": self.tools.git_status,
            "git_diff": self.tools.git_diff,
            "git_commit": self.tools.git_commit,
        }

        if function_name not in function_map:
            from errors import ErrorCode

            raise AgentError(
                code=ErrorCode.FUNCTION_NOT_FOUND,
                message=f"Unknown function: {function_name}",
                suggestions=[f"Available functions: {', '.join(function_map.keys())}"],
                context={"requested_function": function_name},
            )

        func = function_map[function_name]
        return await func(**args)

    async def _call_with_retry(
        self,
        func: Callable[[], Any],
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> Any:
        last_exception: Exception | None = None
        for attempt in range(max_retries):
            try:
                return await func()

            except genai_errors.ClientError as e:
                last_exception = e
                if hasattr(e, "status_code"):
                    if e.status_code == 429:
                        logger.warning(
                            "Rate limited (429)",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            status_code=e.status_code,
                            error=str(e),
                        )
                        if attempt == max_retries - 1:
                            raise RuntimeError(
                                f"Rate limit exceeded after {max_retries} retries: {e}"
                            )
                        delay = base_delay * (2**attempt) + random.uniform(0, 1)
                        await asyncio.sleep(delay)
                        continue
                    elif e.status_code >= 400 and e.status_code < 500:
                        logger.error(
                            "Client error (4xx)",
                            attempt=attempt + 1,
                            status_code=e.status_code,
                            error=str(e),
                        )
                        raise RuntimeError(
                            f"API client error ({e.status_code}): {e}"
                        )
                else:
                    logger.error(
                        "Client error (no status code)",
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    raise RuntimeError(f"API client error: {e}")

            except genai_errors.ServerError as e:
                last_exception = e
                logger.warning(
                    "Server error (5xx)",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                )
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"Server error after {max_retries} retries: {e}"
                    )
                delay = base_delay * (2**attempt)
                await asyncio.sleep(delay)
            
            except Exception as e:
                last_exception = e
                logger.error(
                    "Unexpected error in API call",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True,
                )
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"Unexpected error after {max_retries} retries: {type(e).__name__}: {e}"
                    )
                delay = base_delay * (2**attempt)
                await asyncio.sleep(delay)

        error_msg = f"Failed after {max_retries} retries"
        if last_exception:
            error_msg += f": {type(last_exception).__name__}: {last_exception}"
        raise RuntimeError(error_msg)
