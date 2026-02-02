import argparse
import asyncio

from logging_config import setup_logging, logger


async def main():
    parser = argparse.ArgumentParser(description="AI Code Assistant")
    parser.add_argument("user_prompt", type=str, help="Prompt to send to the agent")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--summary", action="store_true", help="Show session summary")
    parser.add_argument(
        "--workspace", default="./calculator", help="Workspace directory"
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    setup_logging(log_level=args.log_level)

    from agent import DeveloperAgent

    agent = DeveloperAgent(args.workspace)

    result = await agent.run(args.user_prompt, verbose=args.verbose)

    logger.info("Agent execution completed")
    print("\nFinal response:")
    print(result.response)

    if args.summary:
        logger.info(
            "Session summary",
            iterations=result.iterations,
            tokens_used=result.tokens_used,
            functions_called=result.functions_called,
            errors=len(result.errors),
        )
        print("\nSession Summary:")
        print(f"Iterations: {result.iterations}")
        print(f"Tokens used: {result.tokens_used}")
        print(f"Functions called: {result.functions_called}")
        if result.errors:
            print(f"Errors: {len(result.errors)}")
        print(agent.state.summary())


if __name__ == "__main__":
    asyncio.run(main())
