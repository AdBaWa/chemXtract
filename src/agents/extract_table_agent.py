
from typing import Literal

from utils import azure_blob_storage_manager, log
from langchain_core.prompts.image import ImagePromptTemplate
from langchain_core.prompts import HumanMessagePromptTemplate
from model import Document
import pymupdf
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from handler.ocr_processor_client import DocumentIntelligenceAuth, OCRProcessor
from model import BaseState
from util_functions import pdf_to_base64_images

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
    pdf_bytes = pymupdf.open(state.doc_path)
    pdf_page_images = pdf_to_base64_images(pdf_bytes)

    return Command(update={}, goto="extract_tables_and_page_contents")

def _extract_tables_and_page_contents(
    state: BaseState,
) -> Command[Literal["concatenate_tables"]]:
    """Extract tables and pages contents from images"""
    pass

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
    #workflow.add_node("extract_tables_and_page_contents", _extract_tables_and_page_contents)
    #workflow.add_node("concatenate_tables", _concatenate_tables)
    #workflow.add_node("filter_irrelevant_tables",_filter_irrelevant_tables)

    workflow.add_edge(START, "init")
    graph = workflow.compile()

    bytes = graph.get_graph().draw_mermaid_png()
    with open("extract_tables.png", "wb") as f:
        f.write(bytes)

    return graph
