import json
import os
import re
import urllib.parse
from typing import List, Literal

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import (ChatPromptTemplate,
                                    HumanMessagePromptTemplate,
                                    SystemMessagePromptTemplate)
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from openai import BadRequestError
from pydantic import BaseModel, Field

from utils import llm
from model import ExtractTableDataState
from utils_mock_extract_table_data import mock_extract_table_data_state
import pickle
from agents.prompts.step2_prompts import (
    EXTRACT_DATA,
    VERIFY_DATA
)
from util_functions import add_base64image_to_messages
import copy


class TableDataResult(BaseModel):
    """Represents the extracted table data and its metadata."""
    table_data: List[List[str]] = Field(description="The structured table data.")
    is_weight_percent: bool = Field(description="True if the table data is in weight%, False if in mol%. Or NaN if you are unsure.")

class VerifyExtractionResult(BaseModel):
    """Represents """
    feedback: str = Field(description="List of ALL errors that were made.")
    reextraction_necessary: bool = Field(description="True if too many values are incorrect in the current state of the table and thus the data are not reliable. False otherwise.")

def _init(state: ExtractTableDataState) -> Command[Literal["extract_table_data"]]:
    # nothing to do since everything is already in the state
    if os.getenv("SKIP_STEP_2") == "True":
        with open('data/step2.pkl', 'rb') as f:
            state = pickle.load(f)
        return Command(update=state, goto=END)
    return Command(update={}, goto="extract_table_data")


def _extract_table_data(state: ExtractTableDataState) -> Command[Literal["verify_table_data", "__end__"]]:
    """Extracts table data from OCR text and images using an LLM."""
    parser = JsonOutputParser(pydantic_object=TableDataResult)
    
    current_table = None
    current_idx = None

    if state.feedback is None:
        # take a new table and extract data
        for i,t in enumerate(state.tables):
            try:
                t["extracted_data"]
            except:
                t["extracted_data"] = None
                
            if not t["extracted_data"] is None:
                continue
            # if still data to extract
            current_table = t
            current_idx = i
            break
    else:
        # there is currently one table in ongoing work, i.e. refinement
        current_idx = state.curr_table_idx
        current_table = state.tables[current_idx]

    # data for all tables is extracted
    if current_table is None:
        if os.getenv("SKIP_STEP_2") == "False":
            with open('data/step2.pkl', 'wb') as f:  # open a text file
                pickle.dump(state, f) # serialize the list
        return Command(update={}, goto=END)
    
    # extract data for current table
    messages = [
        SystemMessagePromptTemplate.from_template(
            EXTRACT_DATA,
            partial_variables={"format_instructions": parser.get_format_instructions()},
        ),
        HumanMessagePromptTemplate.from_template(
            "OCR Text: {ocr_text}",
            partial_variables={"ocr_text": current_table["content"]},
            type="text",
        ),
    ]
    
    def get_page(pages, page_nr): # TODO THIS IS A DIRTY WORAROUND 
        for p in pages:
            if p["number"] - 1 == page_nr:
                return p
        return None
    
    # add all pages that cover parts of table t
    for p_nr in current_table["pages"]:
        img_base64 = get_page(state.pages, p_nr)["base64"]
        add_base64image_to_messages(messages, img_base64)

    prompts = ChatPromptTemplate(messages=messages)
    chain = prompts | llm | parser
    try:
        resp = chain.invoke({})
    except BadRequestError as e:
        if e.code == "content_filter":
            print(f"Content filter error during LLM processing for table '{current_idx}'")
            resp = TableDataResult(
                table_data=[],
                is_weight_percent=False,
            ).model_dump()
        else:
            raise e
    update_tables = copy.deepcopy(state.tables)
    update_tables[current_idx]["extracted_data"] = resp # is a dictionary
    return Command(update={"tables": update_tables, "curr_table_idx": current_idx}, goto="verify_table_data")


def _verify_table_data(state: ExtractTableDataState) -> Command[Literal["extract_table_data"]]:
    """Verifies the extracted table data using an LLM."""
    
    # limit of re-extraction trials
    max_n_retries = 3
    # initial value of the counter
    init_val_for_retry_counter = 1

    # too many re-extraction trials -> go back directly
    if state.retry_counter >= max_n_retries:
        # leave without doing anything (clear feedback, reset counter)
        return Command(update={"feedback":None, "retry_counter":init_val_for_retry_counter}, goto="extract_table_data")

    # start verification
    current_idx = state.curr_table_idx
    current_table = state.tables[current_idx]
    curr_retry_counter = state.retry_counter

    
    parser = JsonOutputParser(pydantic_object=VerifyExtractionResult)
    prompts = ChatPromptTemplate(
        [
            SystemMessagePromptTemplate.from_template(
                VERIFY_DATA,
                partial_variables={"format_instructions": parser.get_format_instructions()},
            ),
            HumanMessagePromptTemplate.from_template(
                "Table Data: {table_data}: ",
                partial_variables={"table_data": current_table},
                type="text",
            ),
        ]
    )

    chain = prompts | llm | parser
    resp = chain.invoke({})
    resp = VerifyExtractionResult.model_validate(resp)
    # decide whether a repeated extraction is required
    if resp.reextraction_necessary:
        # repeat extraction for this table (return verification feedback; increase counter)
        return Command(update={"feedback":resp.feedback, "retry_counter":curr_retry_counter+1}, goto="extract_table_data")
    else:
        # extract data for another table (reset feedback and counter)
        return Command(update={"feedback":None, "retry_counter":init_val_for_retry_counter}, goto="extract_table_data")
        


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
    workflow.add_node("save_table_data", save_table_data)

    workflow.add_edge(START, "init")
    graph = workflow.compile()

    #bytes = graph.get_graph().draw_mermaid_png()
    #with open("extract_table_data.png", "wb") as f:
    #    f.write(bytes)

    return graph


def my_mock() -> ExtractTableDataState:

    def load_from_pickle(filename): 
        with open(filename, 'rb') as file: 
            data = pickle.load(file)  
        return data  

    # Load the `tables` object from the pickle file  
    tables = load_from_pickle('mock_tabledata/56388722_us2015274579_tables1.pkl') 
    table_05 = tables[5]["content"]
    table_05_pages = tables[5]["pages"]

    # Load the `pages` object from the pickle file  
    pages = load_from_pickle('mock_tabledata/56388722_us2015274579_pages1.pkl')
    base64_pages_for_tab = [pages[p]["base64"] for p in table_05_pages]

    for t in tables:
        t["extracted_data"] = None

    mock_state = ExtractTableDataState(pages=pages, tables=tables)
    return mock_state


def main_url():
    graph = construct_extract_table_data()
    state = my_mock()
    _ = graph.invoke(state)


if __name__ == "__main__":
    main_url()
