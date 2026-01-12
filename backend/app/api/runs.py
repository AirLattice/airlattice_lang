from typing import Any, Dict, Optional, Sequence, Union
from uuid import UUID, uuid4

import langsmith.client
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.exceptions import RequestValidationError
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langsmith.utils import tracing_is_enabled
from pydantic import BaseModel, Field, ValidationError
from sse_starlette import EventSourceResponse

from app.agent import agent, chat_retrieval, chatbot
from app.auth.handlers import AuthedUser
from app.memory import build_memory_context, store_memory_messages, store_user_message
from app.storage import get_assistant, get_thread
from app.stream import astream_state, to_sse

router = APIRouter()


class CreateRunPayload(BaseModel):
    """Payload for creating a run."""

    thread_id: str
    input: Optional[Union[Sequence[AnyMessage], Dict[str, Any]]] = Field(
        default_factory=dict
    )
    config: Optional[RunnableConfig] = None


def _extract_latest_human_message(
    input_: Optional[Union[Sequence[AnyMessage], Dict[str, Any]]],
) -> Optional[str]:
    if not input_:
        return None
    messages = input_ if isinstance(input_, list) else input_.get("messages")
    if not messages:
        return None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
        if isinstance(msg, dict) and msg.get("type") == "human":
            content = msg.get("content")
            if isinstance(content, str):
                return content
    return None


def _inject_system_message(
    input_: Optional[Union[Sequence[AnyMessage], Dict[str, Any]]],
    content: str,
) -> Optional[Union[Sequence[AnyMessage], Dict[str, Any]]]:
    if not input_:
        return input_
    system_message = {
        "content": content,
        "additional_kwargs": {},
        "type": "system",
        "example": False,
        "id": f"memory-{uuid4().hex}",
    }
    if isinstance(input_, list):
        if input_ and not isinstance(input_[0], dict):
            return [SystemMessage(content=content), *input_]
        return [system_message, *input_]
    messages = input_.get("messages") or []
    return {**input_, "messages": [system_message, *messages]}


def _extract_ai_messages(messages: Sequence[AnyMessage]) -> list[AIMessage]:
    return [message for message in messages if isinstance(message, AIMessage)]


async def _store_stream_ai_messages(
    messages: Sequence[AnyMessage],
    *,
    user_id: str,
    thread_id: str,
    assistant_id: Optional[str],
) -> None:
    ai_messages = _extract_ai_messages(messages)
    if ai_messages:
        store_memory_messages(
            messages=ai_messages,
            user_id=user_id,
            thread_id=thread_id,
            assistant_id=assistant_id,
        )


def _extract_output_messages(
    output: Optional[Union[Sequence[AnyMessage], Dict[str, Any]]],
) -> Sequence[AnyMessage]:
    if not output:
        return []
    if isinstance(output, dict):
        messages = output.get("messages")
        return messages if isinstance(messages, list) else []
    return output


async def _run_and_store_ai_messages(
    input_: Optional[Union[Sequence[AnyMessage], Dict[str, Any]]],
    config: RunnableConfig,
    *,
    user_id: str,
    thread_id: str,
    assistant_id: Optional[str],
) -> None:
    output = await agent.ainvoke(input_, config)
    messages = _extract_output_messages(output)
    ai_messages = _extract_ai_messages(messages)
    if ai_messages:
        store_memory_messages(
            messages=ai_messages,
            user_id=user_id,
            thread_id=thread_id,
            assistant_id=assistant_id,
        )


async def _run_input_and_config(payload: CreateRunPayload, user_id: str):
    thread = await get_thread(user_id, payload.thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    assistant = await get_assistant(user_id, str(thread.assistant_id))
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")

    config: RunnableConfig = {
        **assistant.config,
        "configurable": {
            **assistant.config["configurable"],
            **((payload.config or {}).get("configurable") or {}),
            "user_id": user_id,
            "thread_id": str(thread.thread_id),
            "assistant_id": str(assistant.assistant_id),
        },
    }

    bot_type = config["configurable"].get("type", "agent")

    try:
        if payload.input is not None:
            # Get the correct schema based on bot type
            if bot_type == "chat_retrieval":
                schema = chat_retrieval.get_input_schema()
            elif bot_type == "chatbot":
                schema = chatbot.get_input_schema()
            else:  # default to agent
                schema = agent.get_input_schema()
            # Validate against the correct schema
            schema.model_validate(payload.input)
    except ValidationError as e:
        raise RequestValidationError(e.errors(), body=payload)

    input_ = payload.input
    user_message = _extract_latest_human_message(input_)
    if (
        user_message
        and bot_type != "chat_retrieval"
        and config["configurable"].get("user_id")
    ):
        memory_context = await build_memory_context(
            user_id=config["configurable"]["user_id"],
            query=user_message,
        )
        if memory_context:
            input_ = _inject_system_message(input_, memory_context)

    return input_, config, user_message


@router.post("")
async def create_run(
    payload: CreateRunPayload,
    user: AuthedUser,
    background_tasks: BackgroundTasks,
):
    """Create a run."""
    input_, config, user_message = await _run_input_and_config(
        payload, user.user_id
    )
    if user_message:
        background_tasks.add_task(
            store_user_message,
            user_id=user.user_id,
            content=user_message,
            thread_id=payload.thread_id,
            assistant_id=config["configurable"].get("assistant_id"),
        )
    background_tasks.add_task(
        _run_and_store_ai_messages,
        input_,
        config,
        user_id=user.user_id,
        thread_id=payload.thread_id,
        assistant_id=config["configurable"].get("assistant_id"),
    )
    return {"status": "ok"}  # TODO add a run id


@router.post("/stream")
async def stream_run(
    payload: CreateRunPayload,
    user: AuthedUser,
    background_tasks: BackgroundTasks,
):
    """Create a run."""
    input_, config, user_message = await _run_input_and_config(
        payload, user.user_id
    )
    if user_message:
        background_tasks.add_task(
            store_user_message,
            user_id=user.user_id,
            content=user_message,
            thread_id=payload.thread_id,
            assistant_id=config["configurable"].get("assistant_id"),
        )

    async def on_complete(messages: Sequence[AnyMessage]) -> None:
        await _store_stream_ai_messages(
            messages,
            user_id=user.user_id,
            thread_id=payload.thread_id,
            assistant_id=config["configurable"].get("assistant_id"),
        )

    return EventSourceResponse(
        to_sse(astream_state(agent, input_, config, on_complete=on_complete))
    )


@router.get("/input_schema")
async def input_schema() -> dict:
    """Return the input schema of the runnable."""
    return agent.get_input_schema().model_json_schema()


@router.get("/output_schema")
async def output_schema() -> dict:
    """Return the output schema of the runnable."""
    return agent.get_output_schema().model_json_schema()


@router.get("/config_schema")
async def config_schema() -> dict:
    """Return the config schema of the runnable."""
    return agent.config_schema().model_json_schema()


if tracing_is_enabled():
    langsmith_client = langsmith.client.Client()

    class FeedbackCreateRequest(BaseModel):
        """
        Shared information between create requests of feedback and feedback objects
        """

        run_id: UUID
        """The associated run ID this feedback is logged for."""

        key: str
        """The metric name, tag, or aspect to provide feedback on."""

        score: Optional[Union[float, int, bool]] = None
        """Value or score to assign the run."""

        value: Optional[Union[float, int, bool, str, Dict]] = None
        """The display value for the feedback if not a metric."""

        comment: Optional[str] = None
        """Comment or explanation for the feedback."""

    @router.post("/feedback")
    def create_run_feedback(feedback_create_req: FeedbackCreateRequest) -> dict:
        """
        Send feedback on an individual run to langsmith

        Note that a successful response means that feedback was successfully
        submitted. It does not guarantee that the feedback is recorded by
        langsmith. Requests may be silently rejected if they are
        unauthenticated or invalid by the server.
        """

        langsmith_client.create_feedback(
            feedback_create_req.run_id,
            feedback_create_req.key,
            score=feedback_create_req.score,
            value=feedback_create_req.value,
            comment=feedback_create_req.comment,
            source_info={
                "from_langserve": True,
            },
        )

        return {"status": "ok"}
