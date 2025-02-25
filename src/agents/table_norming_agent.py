import json
import os
from typing import Literal

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from pydantic import BaseModel, Field

from agents.prompts.table_norming_prompts import (
    TABLE_NORMING_SYSTEM_PROMPT,
    TABLE_NORMING_USER_PROMPT,
)
from model import TableNormingState
from utils import llm


class NormalizedTableResult(BaseModel):
    """Represents the normalized table data."""

    familyNumber: int
    patentNumber: int
    title: str
    applicant: str
    examples: list


def _init(state: TableNormingState) -> Command[Literal["normalize_table"]]:
    """Initializes the state by loading table data from a JSON file."""
    path = state.doc_path
    output_dir = "output_data"

    file_name = os.path.basename(path).split(".")[0]
    json_file_path = os.path.join(output_dir, f"{file_name}.json")

    with open(json_file_path, "r") as json_file:
        json_content = json.load(json_file)

    return Command(update={"table_data": json_content["table_data"]}, goto="normalize_table")


def _normalize_table(state: TableNormingState) -> Command[Literal["verify_normalization"]]:
    """Normalizes the table data using an LLM."""
    parser = JsonOutputParser(pydantic_object=NormalizedTableResult)
    path = state.doc_path

    messages = [
        SystemMessagePromptTemplate.from_template(
            TABLE_NORMING_SYSTEM_PROMPT,
            partial_variables={"format_instructions": parser.get_format_instructions()},
        ),
        HumanMessagePromptTemplate.from_template(
            TABLE_NORMING_USER_PROMPT,
            partial_variables={"table_data": state.table_data},
            type="text",
        ),
    ]

    prompts = ChatPromptTemplate(messages=messages)
    chain = prompts | llm | parser
    resp = chain.invoke({})

    return Command(update={"normalized_table": resp}, goto="verify_normalization")


def _verify_normalization(state: TableNormingState) -> Command[Literal["save_normalized_table"]]:
    """Verifies the normalized table data."""
    # Implement verification logic here
    return Command(goto="save_normalized_table")


def save_normalized_table(state: TableNormingState) -> Command[Literal["__end__"]]:
    """Saves the normalized table data to a JSON file."""
    doc_path = state.doc_path
    output_dir = "output_data"
    os.makedirs(output_dir, exist_ok=True)

    file_name = os.path.basename(doc_path).split(".")[0]
    json_file_path = os.path.join(output_dir, f"{file_name}_normalized.json")

    data = state.normalized_table.model_dump()

    with open(json_file_path, "w") as json_file:
        json.dump(data, json_file)

    return Command(goto=END)


def construct_table_norming():
    """Constructs and returns the state graph for table normalization."""
    workflow = StateGraph(TableNormingState)
    workflow.add_node("init", _init)
    workflow.add_node("normalize_table", _normalize_table)
    workflow.add_node("verify_normalization", _verify_normalization)
    workflow.add_node("save_normalized_table", save_normalized_table)

    workflow.add_edge(START, "init")
    graph = workflow.compile()

    bytes = graph.get_graph().draw_mermaid_png()
    with open("table_norming.png", "wb") as f:
        f.write(bytes)

    return graph
