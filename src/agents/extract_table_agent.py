
from typing import Literal
import pymupdf
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from azure.ai.documentintelligence.models import AnalyzeResult, AnalyzeDocumentRequest
from model import BaseState
from pydantic import BaseModel, Field
from util_functions import pdf_to_base64_images
import os
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from util_functions import add_base64image_to_messages
from azure.core.credentials import AzureKeyCredential
from agents.prompts.extract_table_prompt import DETECT_CONTINUOUS_TABLES_SYSTEM_PROMPT, DETECT_CONTINUOUS_TABLES_USER_PROMPT, DETECT_IRRELEVANT_TABLES_SYSTEM_PROMPT, DETECT_IRRELEVANT_TABLES_USER_PROMPT
from azure.ai.documentintelligence import DocumentIntelligenceClient
from dotenv import load_dotenv
from utils import llm
from langchain_core.prompts.image import ImagePromptTemplate


load_dotenv()


class CheckContinuousTableResult(BaseModel):
    """Represents the result of a verification, including a status and reason."""

    result: str = Field(description="One of the following options: CONTINUOUS or DISTINCT. Do not write anything else than one of these options.")
    reason: str = Field(description="Outline your reasoning.")

class CheckRelevantTableResult(BaseModel):
    """Represents the result of a verification, including a status and reason."""

    result: str = Field(description="One of the following options: RELEVANT or IRRELEVANT. Do not write anything else than one of these options.")
    reason: str = Field(description="Outline your reasoning.")

def _init(
    state: BaseState,
) -> Command[Literal["pdf_to_base64_images", "__end__"]]:
    """Initializes the OCR process; checks for a document path."""
    
    if not state.doc_path:
        error_msg = "Document path is missing in the state."
        print(f"Error: {error_msg}")
        return Command(
            update={"error": error_msg},
            goto=END,
        )
        
    return Command(update={}, goto="pdf_to_base64_images")

def _pdf_to_base64_images(
    state: BaseState,
) -> Command[Literal["extract_tables_and_page_contents"]]:
    """Splits the document into page images"""
    pdf_bytes = pymupdf.open(state.doc_path).tobytes()
    pdf_page_images = pdf_to_base64_images(pdf_bytes)

    return Command(update={"pdf_page_images": pdf_page_images}, goto="extract_tables_and_page_contents")

def _extract_tables_and_page_contents(
    state: BaseState,
) -> Command[Literal["concatenate_tables"]]:
    """Extract tables and pages contents from images"""

    def get_page_content(analyze_result: AnalyzeResult, page_number: int):
        """Get the full textual content of the specified page from the document."""
        # Implementation to extract content from AnalyzeResult object
        # Assuming 'analyze_result' is the AnalyzeResult object.
        page = analyze_result.pages[page_number - 1]  # Pages are 1-indexed
        content = ""
        for span in page.spans:
            offset = span.offset
            length = span.length
            content += analyze_result.content[offset: offset + length]
        return content

    def get_table(analyze_result, table_index):
        """Get the table details including caption, headers, and rows."""
        table = analyze_result["tables"][table_index]

        # Get caption
        caption = ""
        if "caption" in table and table["caption"]:
            caption = table["caption"].get("content", "") or ""
        else:
            caption = ""

            # Build a mapping of (rowIndex, columnIndex) -> cell
        cell_map = {}
        for cell in table["cells"]:
            key = (cell["rowIndex"], cell["columnIndex"])
            cell_map[key] = cell

            # Get the number of columns and rows
        num_columns = table.get("columnCount", 0)
        num_rows = table.get("rowCount", 0)

        # Get headers from rowIndex == 0
        headers = []
        for col_index in range(num_columns):
            key = (0, col_index)
            if key in cell_map:
                cell = cell_map[key]
                content = cell.get("content", "") or ""
                headers.append(content)
            else:
                headers.append("")

                # Get data rows starting from rowIndex == 1
        rows = []
        for row_index in range(1, num_rows):
            row = []
            for col_index in range(num_columns):
                key = (row_index, col_index)
                if key in cell_map:
                    cell = cell_map[key]
                    content = cell.get("content", "") or ""
                    row.append(content)
                else:
                    row.append("")
            rows.append(row)

        return {"caption": caption, "headers": headers, "rows": rows}

    def get_table_content(table_dict):
        """Create a string representation of the table, separate the columns with ||"""
        table_content = ""
        table_content += table_dict["caption"] + "\n"
        table_content += "||".join(table_dict["headers"]) + "\n"
        for row in table_dict["rows"]:
            table_content += "||".join(row) + "\n"
        return table_content

    def get_page_tables(analyze_result: AnalyzeResult, page_number: int):
        """Get the tables detected on the specified page."""
        # Implementation to extract tables from AnalyzeResult object
        # Assuming 'analyze_result.tables' exists.
        tables = []
        for table_index, table in enumerate(analyze_result.tables):
            if page_number == get_table_page(analyze_result, table_index):
                tables.append(table_index)
        return tables

    def get_table_page(analyze_result: AnalyzeResult, table_index: int):
        """Get the page number of the table"""
        table = analyze_result.tables[table_index]
        table_page = table.bounding_regions[0].page_number
        return table_page


    with DocumentIntelligenceClient(
        endpoint=os.getenv("ENDPOINT_DOCINT"), credential=AzureKeyCredential(os.getenv("API_KEY_DOCINT"))
    ) as document_intelligence_client:
        file_path = state.doc_path
        with open(file_path, "rb") as fd:
            poller = document_intelligence_client.begin_analyze_document(
                "prebuilt-layout",
                AnalyzeDocumentRequest(bytes_source=fd.read()),
            )
            analyze_result = poller.result()

    # We need to have the result in a list of pages and a list of tables
    # pages: List[Dict[str, Any]] = [], where a dictionary is {"page_number": int, "content": str, "tables": List[int]}
    # tables: List[Dict[str, Any]] = [], where a dictionary is {"table_number": int, "content": str, "pages": List[int]}

    pages = []
    for page in analyze_result.pages:
        page_content = get_page_content(analyze_result, page.page_number)
        page_tables = get_page_tables(analyze_result, page.page_number)
        page_image = state.pdf_page_images[page.page_number - 1]
        pages.append({"number": page.page_number, "content": page_content, "tables": page_tables, "base64": page_image})

    tables = []
    for table_index, table in enumerate(analyze_result.tables):
        table_number = table_index
        table_content = get_table_content(get_table(analyze_result, table_index))
        tables.append({"number": table_number, "content": table_content, "pages": [get_table_page(analyze_result, table_index)-1]})

    return Command(update={"pages": pages, "tables": tables}, goto="concatenate_tables")

def add_merged_table(tables, tables_to_merge, pages):
    """Merge tables that belong together"""
    table_index = len(tables)
    table = {"number": table_index,
             "content": "\n".join(table["content"] for table in tables_to_merge),
             "pages": list(table["pages"][0] for table in tables_to_merge)
            }
    tables.append(table)
    
    for table in tables_to_merge:
        table_number = table['number']
        page_number = table["pages"][0] 
        pages[page_number]["tables"].remove(table_number)
        pages[page_number]["tables"].append(table_index)

def _concatenate_tables(
    state: BaseState,
) -> Command[Literal["filter_irrelevant_tables"]]:
    """Concatenates tables which belong together"""
    tables = []
    pages = state.pages
    table_index = 0
    
    while table_index < len(state.tables):
        tables_to_merge = [state.tables[table_index]]
        table_index += 1
        
        while table_index < len(state.tables):
            if tables_to_merge[-1]["pages"][0] + 1 == state.tables[table_index]["pages"][0]:
                last_page = tables_to_merge[-1]["pages"][0]
                tables_spills_to_next_page = check_if_table_spills(state.pdf_page_images[last_page], state.pdf_page_images[last_page + 1])
                
                if tables_spills_to_next_page:
                    #add_merged_table(tables, tables_to_merge)
                    tables_to_merge.append(state.tables[table_index])
                    table_index += 1
                else:
                    add_merged_table(tables, tables_to_merge, pages)
                    break
            else:
                add_merged_table(tables, tables_to_merge, pages)
                break
                
                
        if table_index == len(state.tables):
            add_merged_table(tables, tables_to_merge, pages)
    
    return Command(update={"pages": pages, "tables": tables}, goto="filter_irrelevant_tables")
    


def check_if_table_spills(page1, page2):
    parser = JsonOutputParser(pydantic_object=CheckContinuousTableResult)
    messages = ChatPromptTemplate(
        [
            SystemMessagePromptTemplate.from_template(
                DETECT_CONTINUOUS_TABLES_SYSTEM_PROMPT,
                partial_variables={"format_instructions": parser.get_format_instructions()},
            ),
            HumanMessagePromptTemplate.from_template(
                DETECT_CONTINUOUS_TABLES_USER_PROMPT,
                #partial_variables={"pages": page1},
                type="text",
            ),
        ]
    )
    
    add_base64image_to_messages(messages, page1)
    add_base64image_to_messages(messages, page2)
    
    chain = messages | llm | parser
    resp = chain.invoke({})
    resp = CheckContinuousTableResult.model_validate(resp)
    
    return resp.result == "CONTINUOUS"

def _filter_irrelevant_tables(
    state: BaseState,
) -> Command[Literal["__end__"]]:
    """Filter out irrelevant tables"""
    relevant_tables = []
    relevant_pages_numbers = set()

    for table in state.tables:
        # Check whether the table is relevant
        if check_if_table_relevant(state.pages, table):
            relevant_tables.append(table)
            relevant_pages_numbers.update(table["pages"])

    # Filter pages to only include those related to relevant tables
    relevant_pages = [state.pages[page_number] for page_number in sorted(relevant_pages_numbers)]

    # Update the state with the filtered tables and pages
    return Command(update={"tables": relevant_tables, "pages": relevant_pages}, goto=END)


def check_if_table_relevant(pages, table):
    parser = JsonOutputParser(pydantic_object=CheckRelevantTableResult)
    messages = ChatPromptTemplate(
        [
            SystemMessagePromptTemplate.from_template(
                DETECT_IRRELEVANT_TABLES_SYSTEM_PROMPT,
                partial_variables={"format_instructions": parser.get_format_instructions()},
            ),
            HumanMessagePromptTemplate.from_template(
                DETECT_IRRELEVANT_TABLES_USER_PROMPT,
                type="text",
            ),
        ]
    )

    # Get the pages associated with the table
    table_pages = [pages[page_number] for page_number in table["pages"]]

    # Add the table content
    table_content = table["content"]
    messages.append(
        HumanMessagePromptTemplate.from_template(table_content, type="text")
    )

    # Add the page contents
    # Gather page contents
    pages_content = "\n".join(page["content"] for page in table_pages)
    messages.append(
        HumanMessagePromptTemplate.from_template(pages_content, type="text")
        )

    # Add the page images
    # Get page images
    page_images = [page["base64"] for page in table_pages]
    for page_image in page_images:
        add_base64image_to_messages(messages, page_image)


    chain = messages | llm | parser
    resp = chain.invoke({})
    resp = CheckRelevantTableResult.model_validate(resp)

    return resp.result == "RELEVANT"


def construct_extract_table_agent():
    """Constructs and returns the state graph for extracting tables."""
    workflow = StateGraph(BaseState)
    workflow.add_node("init", _init)
    workflow.add_node("pdf_to_base64_images", _pdf_to_base64_images)
    workflow.add_node("extract_tables_and_page_contents", _extract_tables_and_page_contents)
    workflow.add_node("concatenate_tables", _concatenate_tables)
    workflow.add_node("filter_irrelevant_tables",_filter_irrelevant_tables)

    workflow.add_edge(START, "init")
    graph = workflow.compile()

    bytes = graph.get_graph().draw_mermaid_png()
    with open("extract_tables.png", "wb") as f:
        f.write(bytes)

    return graph
