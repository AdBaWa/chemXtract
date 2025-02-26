import json
import os
import re
import urllib.parse
from typing import Literal

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from openai import BadRequestError
from pydantic import BaseModel, Field

from agents.prompts.extract_main_data_prompts import (
    EXTRACT_MAIN_INFO_SYSTEM_PROMPT,
    EXTRACT_MAIN_INFO_USER_PROMPT,
    RETRY_MAIN_INFO_SYSTEM_PROMPT,
    RETRY_MAIN_INFO_USER_PROMPT,
    VERIFY_MAIN_INFO_SYSTEM_PROMPT,
    VERIFY_MAIN_INFO_USER_PROMPT,
)
from model import ExtractMainDataState
from util_functions import add_file_content_to_messages
from utils import llm


"""
Workflow extracts key data (supplier, invoice number, date) from invoices using OCR and LLMs, with verification and retry mechanisms.
"""


class VerifyResult(BaseModel):
    """Represents the result of a verification, including a status and reason."""

    result: str = Field(description="One of the following options: VERIFIED, CERTAIN, UNSURE, FALSE. Do not write anything else than one of these options.")
    reason: str = Field(description="If Confidence is 'UNSURE' or 'FALSE', provide a reason. If Confidence is 'VERIFIED' or 'CERTAIN', write 'null'.")


class MainInfoResult(BaseModel):
    """Represents the main information extracted from an invoice."""

    supplier: str = Field(
        description="The supplier's name or null if you cannot find any supplier. Do not write anything else than the supplier company name or null."
    )
    invoice_number: str = Field(
        description="The invoice number or null if you cannot find any invoice number. Do not write anything else than the invoice number or null."
    )
    invoice_date: str = Field(
        description="The invoice date or null if you cannot find any invoice date. Do not write the due date. Do not write anything else than the invoice date or null."
    )
    error: str = Field(description="An explanation of why the extraction failed, e.g. 'No supplier found.' Be short and concise. ")


def _init(
    state: ExtractMainDataState,
) -> Command[Literal["get_main_info"]]:
    """Initializes the state by loading OCR text from a JSON file."""
    path = state.doc_path
    output_dir = "output_data"

    if path.startswith(("http://", "https://")):
        parsed_url = urllib.parse.urlparse(path)
        path_segments = parsed_url.path.split("/")
        filename_from_url = path_segments[-1] if path_segments[-1] else "url_doc"
        file_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename_from_url).split(".")[0]
        if not file_name:
            file_name = "url_document"
    else:
        file_name = path.split("/")[-1].split(".")[0]
        file_name = file_name.removeprefix('input_data\\')

    json_file_path = os.path.join(output_dir, f"{file_name}.json")

    with open(json_file_path, "r") as json_file:
        json_content = json.load(json_file)

    return Command(update={"ocr_text": json_content["ocr_text"]}, goto="get_main_info")


def _get_main_info(
    state: ExtractMainDataState,
) -> Command[Literal["verify_main_info"]]:
    """Extracts main information from the OCR text using an LLM."""
    parser = JsonOutputParser(pydantic_object=MainInfoResult)
    path = state.doc_path

    messages = [
        SystemMessagePromptTemplate.from_template(
            EXTRACT_MAIN_INFO_SYSTEM_PROMPT,
            partial_variables={"format_instructions": parser.get_format_instructions()},
        ),
        HumanMessagePromptTemplate.from_template(
            EXTRACT_MAIN_INFO_USER_PROMPT,
            partial_variables={"ocr_text": state.ocr_text},
            type="text",
        ),
    ]

    messages = add_file_content_to_messages(messages, path)
    prompts = ChatPromptTemplate(messages=messages)
    chain = prompts | llm | parser
    try:
        resp = chain.invoke({})
    except BadRequestError as e:
        if e.code == "content_filter":
            print(f"Content filter error during LLM processing for document '{path}'")
            resp = MainInfoResult(
                supplier="null",
                invoice_number="null",
                invoice_date="null",
                error="Content filter error",
            ).model_dump()
        else:
            raise e

    return Command(update={"main_info": resp}, goto="verify_main_info")


def _verfiy_main_info(
    state: ExtractMainDataState,
) -> Command[Literal["save_main_info", "retry_get_main_info"]]:
    """Verifies the extracted main information using an LLM."""
    info = state.main_info
    parser = JsonOutputParser(pydantic_object=VerifyResult)
    prompts = ChatPromptTemplate(
        [
            SystemMessagePromptTemplate.from_template(
                VERIFY_MAIN_INFO_SYSTEM_PROMPT,
                partial_variables={"format_instructions": parser.get_format_instructions()},
            ),
            HumanMessagePromptTemplate.from_template(
                VERIFY_MAIN_INFO_USER_PROMPT,
                partial_variables={"main_info": info},
                type="text",
            ),
        ]
    )
    chain = prompts | llm | parser
    resp = chain.invoke({})
    resp = VerifyResult.model_validate(resp)
    if resp.result in ["VERIFIED", "CERTAIN"]:
        return Command(update={"confidence": resp.result}, goto="save_main_info")
    else:
        if state.retried:
            print("Confidence not high enoguh and already retried, ending extraction")
            print(f"Reason: {resp.reason}")
            print(f"Confidence: {resp.result}")
            return Command(update={"confidence": resp.result, "reason": resp.reason}, goto=END)

        print("Confidence not high enough, retrying extraction with reason")
        return Command(
            update={"confidence": resp.result, "reason": resp.reason},
            goto="retry_get_main_info",
        )


def _retry_get_main_info(
    state: ExtractMainDataState,
) -> Command[Literal["verify_main_info"]]:
    """Retries the main information extraction with a reason for failure."""
    parser = JsonOutputParser(pydantic_object=MainInfoResult)
    path = state.doc_path
    messages = [
        SystemMessagePromptTemplate.from_template(
            RETRY_MAIN_INFO_SYSTEM_PROMPT,
            partial_variables={"format_instructions": parser.get_format_instructions()},
        ),
        HumanMessagePromptTemplate.from_template(
            RETRY_MAIN_INFO_USER_PROMPT,
            partial_variables={
                "main_info": state.main_info,
                "ocr_text": state.ocr_text,
                "reason": state.reason,
            },
            type="text",
        ),
    ]
    messages = add_file_content_to_messages(messages, path)
    prompts = ChatPromptTemplate(messages=messages)
    chain = prompts | llm | parser
    resp = chain.invoke({})
    return Command(update={"main_info": resp, "retried": True}, goto="verify_main_info")


def save_main_info(
    state: ExtractMainDataState,
) -> Command[Literal["__end__"]]:
    """Saves the extracted information to a JSON file, updating existing data."""
    doc_path = state.doc_path
    output_dir = "output_data"
    os.makedirs(output_dir, exist_ok=True)

    if doc_path.startswith(("http://", "https://")):
        # Handle URL
        parsed_url = urllib.parse.urlparse(doc_path)
        # Extract filename from the path part of the URL
        path_segments = parsed_url.path.split("/")
        filename_from_url = path_segments[-1] if path_segments[-1] else "url_doc"  # Use "url_doc" as fallback if no filename in path

        # Sanitize filename from URL
        file_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename_from_url)

        # Remove extension if it exists in the URL filename
        file_name = file_name.split(".")[0]

        if not file_name:
            file_name = "url_document"

    else:
        file_name = doc_path.split("/")[-1].split(".")[0]

    json_file_path = os.path.join(output_dir, f"{file_name}.json")

    data = state.main_info.model_dump()
    data["confidence"] = state.confidence
    data["reason"] = state.reason

    if os.path.exists(json_file_path):
        try:
            with open(json_file_path, "r") as json_file:
                existing_data = json.load(json_file)
                # Update existing data with new data
                existing_data.update(data)
                data = existing_data
        except json.JSONDecodeError:
            # If file is corrupted, use only new data
            pass

    # Write combined data back to file
    with open(json_file_path, "w") as json_file:
        json.dump(data, json_file)

    return Command(goto=END)


def construct_extract_main_data():
    """Constructs and returns the state graph for extracting main data."""
    workflow = StateGraph(ExtractMainDataState)
    workflow.add_node("init", _init)
    workflow.add_node("get_main_info", _get_main_info)
    workflow.add_node("verify_main_info", _verfiy_main_info)
    workflow.add_node("retry_get_main_info", _retry_get_main_info)
    workflow.add_node("save_main_info", save_main_info)

    workflow.add_edge(START, "init")
    graph = workflow.compile()

    bytes = graph.get_graph().draw_mermaid_png()
    with open("extract_main_data.png", "wb") as f:
        f.write(bytes)

    return graph
