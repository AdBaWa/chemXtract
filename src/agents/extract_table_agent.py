
from typing import Literal
import pymupdf
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from azure.ai.documentintelligence.models import AnalyzeResult, AnalyzeDocumentRequest
from handler.ocr_processor_client import DocumentIntelligenceAuth, OCRProcessor
from model import BaseState
from util_functions import pdf_to_base64_images
import os
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from dotenv import load_dotenv
load_dotenv()

doc_int_auth = DocumentIntelligenceAuth()
doc_int_client = doc_int_auth.get_client()
ocr_processor = OCRProcessor(doc_int_client)


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
        tables.append({"number": table_number, "content": table_content, "pages": [get_table_page(analyze_result, table_index)]})

    return Command(update={"pages": pages, "tables": tables}, goto="concatenate_tables")

def _concatenate_tables(
    state: BaseState,
) -> Command[Literal["filter_irrelevant_tables"]]:
    """Concatenates tables which belong together"""
    pass

def _filter_irrelevant_tables(
    state: BaseState,
) -> Command[Literal["__end__"]]:
    """Filter out irrelevant tables"""
    pass


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
