import json
import os
import re
import urllib.parse
from typing import List, Literal

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

from model import ExtractTableDataState
from utils import llm
from utils_mock_extract_table_data import mock_extract_table_data_state


class TableDataResult(BaseModel):
    """Represents the extracted table data and its metadata."""
    table_data: List[List[str]] = Field(description="The structured table data.")
    is_weight_percent: bool = Field(description="True if the table data is in weight%, False if in mol%.")


def _init(state: ExtractTableDataState) -> Command[Literal["extract_table_data"]]:
    """Initializes the state by loading OCR text and images from JSON files."""
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

    json_file_path = os.path.join(output_dir, f"{file_name}.json")

    with open(json_file_path, "r") as json_file:
        json_content = json.load(json_file)

    return Command(update={"ocr_text": json_content["ocr_text"], "images": json_content["images"]}, goto="extract_table_data")


def _extract_table_data(state: ExtractTableDataState) -> Command[Literal["verify_table_data"]]:
    """Extracts table data from OCR text and images using an LLM."""
    parser = JsonOutputParser(pydantic_object=TableDataResult)
    path = state.doc_path

    messages = [
        SystemMessagePromptTemplate.from_template(
            "Extract table data and determine if it is in weight% or mol%.",
            partial_variables={"format_instructions": parser.get_format_instructions()},
        ),
        HumanMessagePromptTemplate.from_template(
            "OCR Text: {ocr_text}\nImages: {images}",
            partial_variables={"ocr_text": state.ocr_text, "images": state.images},
            type="text",
        ),
    ]

    prompts = ChatPromptTemplate(messages=messages)
    chain = prompts | llm | parser
    try:
        resp = chain.invoke({})
    except BadRequestError as e:
        if e.code == "content_filter":
            print(f"Content filter error during LLM processing for document '{path}'")
            resp = TableDataResult(
                table_data=[],
                is_weight_percent=False,
            ).model_dump()
        else:
            raise e

    return Command(update={"table_data_result": resp}, goto="verify_table_data")


def _verify_table_data(state: ExtractTableDataState) -> Command[Literal["save_table_data", "retry_extract_table_data"]]:
    """Verifies the extracted table data using an LLM."""
    info = state.table_data_result
    parser = JsonOutputParser(pydantic_object=TableDataResult)
    prompts = ChatPromptTemplate(
        [
            SystemMessagePromptTemplate.from_template(
                "Verify the extracted table data and its metadata.",
                partial_variables={"format_instructions": parser.get_format_instructions()},
            ),
            HumanMessagePromptTemplate.from_template(
                "Table Data: {table_data}\nIs Weight Percent: {is_weight_percent}",
                partial_variables={"table_data": info.table_data, "is_weight_percent": info.is_weight_percent},
                type="text",
            ),
        ]
    )
    chain = prompts | llm | parser
    resp = chain.invoke({})
    resp = TableDataResult.model_validate(resp)
    if resp.is_weight_percent is not None:
        return Command(update={"confidence": "VERIFIED"}, goto="save_table_data")
    else:
        if state.retried:
            print("Confidence not high enough and already retried, ending extraction")
            return Command(update={"confidence": "UNSURE"}, goto=END)

        print("Confidence not high enough, retrying extraction")
        return Command(update={"confidence": "UNSURE"}, goto="retry_extract_table_data")


def _retry_extract_table_data(state: ExtractTableDataState) -> Command[Literal["verify_table_data"]]:
    """Retries the table data extraction with a reason for failure."""
    parser = JsonOutputParser(pydantic_object=TableDataResult)
    path = state.doc_path
    messages = [
        SystemMessagePromptTemplate.from_template(
            "Retry extracting table data and determine if it is in weight% or mol%.",
            partial_variables={"format_instructions": parser.get_format_instructions()},
        ),
        HumanMessagePromptTemplate.from_template(
            "OCR Text: {ocr_text}\nImages: {images}\nReason: {reason}",
            partial_variables={"ocr_text": state.ocr_text, "images": state.images, "reason": state.reason},
            type="text",
        ),
    ]
    prompts = ChatPromptTemplate(messages=messages)
    chain = prompts | llm | parser
    resp = chain.invoke({})
    return Command(update={"table_data_result": resp, "retried": True}, goto="verify_table_data")


def save_table_data(state: ExtractTableDataState) -> Command[Literal["__end__"]]:
    """Saves the extracted table data to a JSON file, updating existing data."""
    doc_path = state.doc_path
    output_dir = "output_data"
    os.makedirs(output_dir, exist_ok=True)

    if doc_path.startswith(("http://", "https://")):
        parsed_url = urllib.parse.urlparse(doc_path)
        path_segments = parsed_url.path.split("/")
        filename_from_url = path_segments[-1] if path_segments[-1] else "url_doc"
        file_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename_from_url).split(".")[0]
        if not file_name:
            file_name = "url_document"
    else:
        file_name = doc_path.split("/")[-1].split(".")[0]

    json_file_path = os.path.join(output_dir, f"{file_name}.json")

    data = state.table_data_result.model_dump()
    data["confidence"] = state.confidence

    if os.path.exists(json_file_path):
        try:
            with open(json_file_path, "r") as json_file:
                existing_data = json.load(json_file)
                existing_data.update(data)
                data = existing_data
        except json.JSONDecodeError:
            pass

    with open(json_file_path, "w") as json_file:
        json.dump(data, json_file)

    return Command(goto=END)


def construct_extract_table_data():
    """Constructs and returns the state graph for extracting table data."""
    workflow = StateGraph(ExtractTableDataState)
    workflow.add_node("init", _init)
    workflow.add_node("extract_table_data", _extract_table_data)
    workflow.add_node("verify_table_data", _verify_table_data)
    workflow.add_node("retry_extract_table_data", _retry_extract_table_data)
    workflow.add_node("save_table_data", save_table_data)

    workflow.add_edge(START, "init")
    graph = workflow.compile()

    bytes = graph.get_graph().draw_mermaid_png()
    with open("extract_table_data.png", "wb") as f:
        f.write(bytes)

    return graph

def my_mock():
    def load_from_pickle(filename):  
        with open(filename, 'rb') as file:  
            data = pickle.load(file)  
        return data  

    # Load the `pages` object from the pickle file  
    pages = load_from_pickle('mock_tabledata/56388722_us2015274579_pages1.pkl')  
    page_6 = pages[5]

    # Load the `tables` object from the pickle file  
    tables = load_from_pickle('mock_tabledata/56388722_us2015274579_tables1.pkl') 
    table_05 = tables[5]

def main_url():
    graph = construct_extract_table_data()
    state = mock_extract_table_data_state()
    _ = graph.invoke(state)


if __name__ == "__main__":
    main_url()