"""T00_HELLO — the Phase 5 test agent: greets a name, exercising chain, limits, logging and schema."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from tubeforge_agents.base import AgentTask
from tubeforge_agents.prompting import render_user


class HelloInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class HelloAgent(AgentTask):
    code: ClassVar[str] = "T00_HELLO"
    task_type: ClassVar[str] = "hello"
    temperature: ClassVar[float] = 0.7
    max_output_tokens: ClassVar[int] = 120
    input_model: ClassVar[type[BaseModel]] = HelloInput

    def user_message(self, data: BaseModel) -> str:
        return render_user("Please greet: {{ name | untrusted('name') }}", data.model_dump())


HANDLERS: dict[str, AgentTask] = {HelloAgent.code: HelloAgent()}
