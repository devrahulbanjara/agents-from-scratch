import asyncio
import mimetypes
import re
from pathlib import Path

import aiofiles

from errors import ErrorCode, FileError, GitError, SearchError


class CodebaseTools:
    def __init__(self, root: Path, state):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.state = state

        self.max_read_size = 100 * 1024
        self.max_write_size = 1 * 1024 * 1024
        self.max_search_file_size = 1 * 1024 * 1024
        self.max_files_per_search = 1000
        self.max_search_results = 100

    def _secure_path(self, path: str) -> Path:
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root):
            raise FileError(
                code=ErrorCode.PERMISSION_DENIED,
                message=f"Path '{path}' is outside workspace",
                suggestions=["Use relative paths within the workspace"],
                context={"requested_path": path, "workspace_root": str(self.root)},
            )
        return target

    def _is_text_file(self, file_path: Path) -> bool:
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type and not mime_type.startswith("text"):
            return False

        binary_extensions = {
            ".pyc",
            ".pyo",
            ".so",
            ".dylib",
            ".dll",
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".pdf",
            ".zip",
            ".tar",
            ".gz",
            ".exe",
            ".bin",
            ".ico",
            ".svg",
            ".woff",
            ".woff2",
            ".ttf",
            ".eot",
            ".otf",
            ".mp3",
            ".mp4",
            ".avi",
            ".mov",
            ".webm",
            ".webp",
            ".bmp",
            ".tiff",
            ".psd",
            ".ai",
            ".eps",
        }
        if file_path.suffix.lower() in binary_extensions:
            return False

        try:
            with open(file_path, "rb") as f:
                sample = f.read(1024)
                if b"\x00" in sample:
                    return False
        except Exception:
            return False

        return True

    def _is_sensitive_file(self, file_path: str) -> bool:
        sensitive_patterns = [
            r"\.env(\.|$)",
            r"\.pem$",
            r"id_rsa|id_dsa|id_ecdsa",
            r"credentials?$",
            r"\.aws/",
            r"\.ssh/",
            r"password\.(txt|yml|yaml|json)$",
            r"secrets?\.(txt|yml|yaml|json)$",
            r"\.key$",
        ]

        path_lower = file_path.lower()
        return any(re.search(pattern, path_lower) for pattern in sensitive_patterns)

    async def _contains_secrets(self, file_path: str) -> bool:
        secret_patterns = [
            r'api[_-]?key\s*=\s*["\'][^"\']+["\']',
            r'password\s*=\s*["\'][^"\']+["\']',
            r'token\s*=\s*["\'][^"\']+["\']',
            r"sk_live_[a-zA-Z0-9]+",
            r"ghp_[a-zA-Z0-9]+",
        ]

        try:
            target = self._secure_path(file_path)
            loop = asyncio.get_event_loop()
            exists = await loop.run_in_executor(None, target.exists)
            if not exists or not await loop.run_in_executor(None, target.is_file):
                return False

            stat_result = await loop.run_in_executor(None, target.stat)
            if stat_result.st_size > 100 * 1024:
                return False

            async with aiofiles.open(
                target, "r", encoding="utf-8", errors="ignore"
            ) as f:
                content = await f.read()
                return any(
                    re.search(pattern, content, re.IGNORECASE)
                    for pattern in secret_patterns
                )
        except Exception:
            return False

    async def read_file(self, path: str, max_chars: int = 10000) -> str:
        target = self._secure_path(path)

        loop = asyncio.get_event_loop()
        exists = await loop.run_in_executor(None, target.exists)
        if not exists:
            raise FileError(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"File '{path}' does not exist",
                suggestions=[
                    "Check the file path spelling",
                    "Use list_files to see available files",
                    "Create the file first with write_file",
                ],
                context={"requested_path": path},
            )

        is_file = await loop.run_in_executor(None, target.is_file)
        if not is_file:
            is_dir = await loop.run_in_executor(None, target.is_dir)
            raise FileError(
                code=ErrorCode.INVALID_PATH,
                message=f"'{path}' is not a file",
                suggestions=["Use list_files to see file types"],
                context={"path_type": "directory" if is_dir else "unknown"},
            )

        stat_result = await loop.run_in_executor(None, target.stat)
        file_size = stat_result.st_size
        if file_size > self.max_read_size:
            raise FileError(
                code=ErrorCode.FILE_TOO_LARGE,
                message=f"File '{path}' is too large to read ({file_size} bytes)",
                suggestions=[
                    f"File exceeds {self.max_read_size} byte limit",
                    "Use search_files to find specific content",
                    "Read file in application code with streaming",
                ],
                context={"file_size": file_size, "limit": self.max_read_size},
            )

        try:
            async with aiofiles.open(target, "r", encoding="utf-8") as f:
                content = await f.read()
        except UnicodeDecodeError:
            raise FileError(
                code=ErrorCode.INVALID_PATH,
                message=f"File '{path}' is not a text file",
                suggestions=["Only text files can be read"],
                context={"file_path": path},
            )

        if max_chars and len(content) > max_chars:
            content = content[:max_chars] + f"\n[... truncated to {max_chars} chars]"

        await self.state.add_file_read(path)
        return content

    async def write_file(self, path: str, content: str) -> str:
        target = self._secure_path(path)

        if len(content) > self.max_write_size:
            raise FileError(
                code=ErrorCode.FILE_TOO_LARGE,
                message=f"Content too large ({len(content)} chars)",
                suggestions=[
                    "Write smaller files",
                    "Split content into multiple files",
                ],
                context={"content_size": len(content), "limit": self.max_write_size},
            )

        dangerous_extensions = {".exe", ".bat", ".sh", ".cmd", ".scr", ".com"}
        if target.suffix.lower() in dangerous_extensions:
            raise FileError(
                code=ErrorCode.PERMISSION_DENIED,
                message=f"Cannot write executable file '{path}'",
                suggestions=["Write text files only"],
                context={"file_extension": target.suffix},
            )

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None, lambda: target.parent.mkdir(parents=True, exist_ok=True)
            )
            async with aiofiles.open(target, "w", encoding="utf-8") as f:
                await f.write(content)
        except PermissionError:
            raise FileError(
                code=ErrorCode.PERMISSION_DENIED,
                message=f"Permission denied writing to '{path}'",
                suggestions=["Check file permissions", "Try a different location"],
                context={"target_path": str(target)},
            )

        await self.state.add_file_written(path)
        return f"Successfully wrote {len(content)} characters to {path}"

    async def list_files(self, directory: str = ".") -> str:
        target = self._secure_path(directory)
        loop = asyncio.get_event_loop()

        exists = await loop.run_in_executor(None, target.exists)
        if not exists:
            raise FileNotFoundError(f"Directory '{directory}' does not exist")

        is_dir = await loop.run_in_executor(None, target.is_dir)
        if not is_dir:
            raise ValueError(f"'{directory}' is not a directory")

        items = []
        dir_items = await loop.run_in_executor(None, lambda: sorted(target.iterdir()))
        for item in dir_items:
            stat_result = await loop.run_in_executor(None, item.stat)
            size = stat_result.st_size
            item_is_dir = await loop.run_in_executor(None, item.is_dir)
            items.append(f"- {item.name}: file_size={size} bytes, is_dir={item_is_dir}")

        return "\n".join(items) if items else "Directory is empty"

    async def create_directory(self, path: str, recursive: bool = True) -> str:
        target = self._secure_path(path)
        loop = asyncio.get_event_loop()

        exists = await loop.run_in_executor(None, target.exists)
        if exists:
            is_dir = await loop.run_in_executor(None, target.is_dir)
            if is_dir:
                return f"Directory '{path}' already exists"
            else:
                raise ValueError(f"'{path}' exists but is not a directory")

        if recursive:
            await loop.run_in_executor(
                None, lambda: target.mkdir(parents=True, exist_ok=True)
            )
        else:
            await loop.run_in_executor(None, lambda: target.mkdir())

        return f"Successfully created directory '{path}'"

    async def search_files(
        self,
        pattern: str,
        file_extensions: list[str] | None = None,
        case_sensitive: bool = False,
        max_results: int = 50,
    ) -> str:
        if not pattern.strip():
            raise SearchError(
                code=ErrorCode.INVALID_REGEX,
                message="Search pattern cannot be empty",
                suggestions=["Provide a non-empty search pattern"],
                context={},
            )

        if max_results > self.max_search_results:
            max_results = self.max_search_results

        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            regex_pattern = re.compile(pattern, flags)
        except re.error as e:
            raise SearchError(
                code=ErrorCode.INVALID_REGEX,
                message=f"Invalid regex pattern '{pattern}': {e}",
                suggestions=[
                    "Use simpler text search instead of regex",
                    "Escape special characters like . * + ? ^ $ { } [ ] \\ | ( )",
                    "Test regex pattern in a regex validator",
                ],
                context={"pattern": pattern, "regex_error": str(e)},
            )

        results = []
        matches_found = 0
        files_scanned = 0
        loop = asyncio.get_event_loop()

        file_paths = await loop.run_in_executor(
            None, lambda: list(self.root.rglob("*"))
        )

        for file_path in file_paths:
            files_scanned += 1
            if files_scanned > self.max_files_per_search:
                results.append(
                    f"... (stopped after scanning {self.max_files_per_search} files)"
                )
                break

            if any(part.startswith(".") for part in file_path.parts):
                continue

            is_file = await loop.run_in_executor(None, file_path.is_file)
            if not is_file:
                continue

            if file_extensions and not any(
                file_path.suffix == ext for ext in file_extensions
            ):
                continue

            try:
                stat_result = await loop.run_in_executor(None, file_path.stat)
                if stat_result.st_size > self.max_search_file_size:
                    continue
            except (OSError, PermissionError):
                continue

            is_text = await loop.run_in_executor(None, self._is_text_file, file_path)
            if not is_text:
                continue

            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    line_num = 0
                    async for line in f:
                        line_num += 1
                        if regex_pattern.search(line):
                            matches_found += 1
                            rel_path = file_path.relative_to(self.root)
                            results.append(f"{rel_path}:{line_num}: {line.strip()}")

                            if matches_found >= max_results:
                                results.append(
                                    f"... (truncated at {max_results} matches)"
                                )
                                break

                    if matches_found >= max_results:
                        break

            except (UnicodeDecodeError, PermissionError):
                continue

        await self.state.add_search_performed(
            {
                "pattern": pattern,
                "extensions": file_extensions,
                "results": min(matches_found, max_results),
                "files_scanned": files_scanned,
            }
        )

        if not results:
            return f'No matches found for pattern "{pattern}" (scanned {files_scanned} files)'

        header = f'Found {min(matches_found, max_results)} matches for pattern "{pattern}" (scanned {files_scanned} files):'
        return header + "\n" + "\n".join(results)

    async def git_status(self) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "rev-parse",
                "--git-dir",
                cwd=self.root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=30.0)
            if proc.returncode != 0:
                return "Error: Not a git repository"
        except asyncio.TimeoutError:
            return "Error: Not a git repository"

        results = []

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "branch",
                "--show-current",
                cwd=self.root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode == 0:
                branch_output = stdout.decode().strip()
                if branch_output:
                    results.append(f"Current branch: {branch_output}")
        except asyncio.TimeoutError:
            pass

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "status",
                "--porcelain",
                cwd=self.root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode == 0:
                status_output = stdout.decode().strip()
                if status_output:
                    results.append("Modified files:")
                    for line in status_output.split("\n"):
                        results.append(f"  {line}")
                else:
                    results.append("Working directory is clean")
        except asyncio.TimeoutError:
            pass

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "log",
                "--oneline",
                "-5",
                cwd=self.root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode == 0:
                log_output = stdout.decode().strip()
                if log_output:
                    results.append("Recent commits:")
                    for line in log_output.split("\n"):
                        if line:
                            results.append(f"  {line}")
        except asyncio.TimeoutError:
            pass

        return "\n".join(results) if results else "No git information available"

    async def git_diff(self, file_path: str | None = None) -> str:
        args = ["diff"]
        if file_path:
            args.append(file_path)

        results = []

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                "--cached",
                cwd=self.root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode == 0:
                staged_output = stdout.decode().strip()
                if staged_output:
                    results.append("=== STAGED CHANGES ===")
                    results.append(staged_output)
        except asyncio.TimeoutError:
            pass

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=self.root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode == 0:
                unstaged_output = stdout.decode().strip()
                if unstaged_output:
                    results.append("=== UNSTAGED CHANGES ===")
                    results.append(unstaged_output)
        except asyncio.TimeoutError:
            pass

        return "\n".join(results) if results else "No changes found"

    async def git_commit(self, message: str, add_all: bool = False) -> str:
        if not message.strip():
            raise GitError(
                code=ErrorCode.GIT_ERROR,
                message="Commit message cannot be empty",
                suggestions=["Provide a descriptive commit message"],
                context={},
            )

        if len(message) > 500:
            raise GitError(
                code=ErrorCode.GIT_ERROR,
                message="Commit message too long",
                suggestions=["Keep commit messages under 500 characters"],
                context={"message_length": len(message)},
            )

        results = []

        if add_all:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "status",
                    "--porcelain",
                    cwd=self.root,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
                if proc.returncode != 0:
                    raise GitError(
                        code=ErrorCode.GIT_ERROR,
                        message="Error checking git status",
                        suggestions=["Check git repository status"],
                        context={},
                    )

                status_output = stdout.decode().strip()

                dangerous_files = []

                for line in status_output.split("\n"):
                    if line:
                        file_path = line[3:].strip()
                        if self._is_sensitive_file(file_path):
                            dangerous_files.append(file_path)
                        elif await self._contains_secrets(file_path):
                            dangerous_files.append(
                                f"{file_path} (contains potential secrets)"
                            )

                if dangerous_files:
                    raise GitError(
                        code=ErrorCode.GIT_ERROR,
                        message="Refusing to commit potentially sensitive files",
                        suggestions=[
                            "Review files before committing",
                            "Add files individually instead of using add_all",
                            "Add sensitive files to .gitignore",
                        ],
                        context={"dangerous_files": dangerous_files},
                    )

                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "add",
                    ".",
                    cwd=self.root,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.wait(), timeout=30.0)
                if proc.returncode != 0:
                    raise GitError(
                        code=ErrorCode.GIT_ERROR,
                        message="Error staging files",
                        suggestions=[
                            "Check git repository status",
                            "Ensure files exist",
                        ],
                        context={},
                    )
                results.append("Staged all changes (after security check)")

            except asyncio.TimeoutError:
                raise GitError(
                    code=ErrorCode.GIT_ERROR,
                    message="Timeout staging files",
                    suggestions=["Check git repository status"],
                    context={},
                )

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "commit",
                "-m",
                message,
                cwd=self.root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode != 0:
                stderr_text = stderr.decode() if stderr else ""
                raise GitError(
                    code=ErrorCode.GIT_ERROR,
                    message=f"Error creating commit: {stderr_text}",
                    suggestions=[
                        "Ensure there are changes to commit",
                        "Check if git repository is properly initialized",
                        "Verify git user configuration",
                    ],
                    context={"git_error": stderr_text},
                )
            commit_output = stdout.decode().strip()
            results.append(f"Commit created: {commit_output}")
        except asyncio.TimeoutError:
            raise GitError(
                code=ErrorCode.GIT_ERROR,
                message="Timeout creating commit",
                suggestions=["Check git repository status"],
                context={},
            )

        return "\n".join(results)
