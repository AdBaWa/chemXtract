from typing import List, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
import json
from src.model import PerformOCRState
import os
from src.handler.ocr_processor_client import OCRProcessor, DocumentIntelligenceAuth
from src.util_functions import convert_image_to_base64_from_disk
import urllib.parse
import re

doc_int_auth = DocumentIntelligenceAuth()
doc_int_client = doc_int_auth.get_client()
ocr_processor = OCRProcessor(doc_int_client)

def _init(
    state: PerformOCRState,
) -> Command[Literal["perform_ocr", "__end__"]]:
    """
    Initialization node to check if document path is provided.
    """
    if not state.doc_path:
        error_msg = "Document path is missing in the state."
        print(f"Error: {error_msg}")
        return Command(
            update={"error": error_msg},
            goto=END,
        )
    return Command(update={},goto="perform_ocr")

def _perform_ocr(
    state: PerformOCRState,
) -> Command[Literal["save_ocr_text"]]:
    """
    Perform OCR on the document.
    """
    doc_path = state.doc_path
    print("Performing OCR on the document...")
    if doc_path.lower().startswith(("http://", "https://")):
        extracted_text = ocr_processor.extract_text_from_url(doc_path)
    else:
        #TODO: Currently failes due to Invalid Request Error; Code: Invalid Content; Message: File is corrupted or format unsupported...
        base64_image = convert_image_to_base64_from_disk(doc_path)
        extracted_text = ocr_processor.extract_text_from_base64_image(base64_image)
    
    return Command(
        update={
            "ocr_text": extracted_text,
        },
        goto="save_ocr_text",

    )

def _save_ocr_text(
    state: PerformOCRState,
) -> Command[Literal["__end__"]]:
    """
    Save the extracted OCR text to a local JSON file.
    Handles both local file paths and URLs for doc_path.
    """
    doc_path = state.doc_path
    extracted_text = state.ocr_text
    print("Saving the extracted OCR text to a local JSON file...")
    output_dir = "output_data"
    os.makedirs(output_dir, exist_ok=True)

    if doc_path.startswith(("http://", "https://")):
        # Handle URL
        parsed_url = urllib.parse.urlparse(doc_path)
        # Extract filename from the path part of the URL
        path_segments = parsed_url.path.split("/")
        filename_from_url = path_segments[-1] if path_segments[-1] else "url_doc" # Use "url_doc" as fallback if no filename in path

        # Sanitize filename from URL to be safe for file system
        file_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename_from_url)

        # Remove extension if it exists in the URL filename 
        file_name = file_name.split(".")[0]

        # If after sanitization and removing extension, filename is empty, use a generic name
        if not file_name:
            file_name = "url_document"

    else:
        file_name = doc_path.split("/")[-1].split(".")[0]

    json_file_path = os.path.join(output_dir, f"{file_name}.json")
    with open(json_file_path, "w") as json_file:
        json.dump({"ocr_text": extracted_text}, json_file)

    return Command(update={}, goto=END)

def construct_ocr():
    workflow = StateGraph(PerformOCRState)
    workflow.add_node("init", _init)
    workflow.add_node("perform_ocr", _perform_ocr)
    workflow.add_node("save_ocr_text", _save_ocr_text)

    workflow.add_edge(START, "init")
    graph = workflow.compile()

    bytes = graph.get_graph().draw_mermaid_png()
    with open("perform_ocr.png", "wb") as f:
        f.write(bytes)

    return graph