from dataclasses import dataclass


@dataclass
class AgentResult:
    response: str
    iterations: int
    tokens_used: int
    functions_called: int
    errors: list[str]

    def __str__(self) -> str:
        return self.response

    def estimated_cost(self) -> float:
        input_cost_per_1k = 0.0
        output_cost_per_1k = 0.0

        input_tokens = self.tokens_used * 0.7
        output_tokens = self.tokens_used * 0.3

        return (input_tokens / 1000 * input_cost_per_1k) + (
            output_tokens / 1000 * output_cost_per_1k
        )
