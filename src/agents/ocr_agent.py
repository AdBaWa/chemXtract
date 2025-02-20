from typing import List, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
import json
from src.model import PerformOCRState
import os
from src.handler.ocr_processor_client import OCRProcessor, DocumentIntelligenceAuth

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
    return Command(goto="perform_ocr")

def _perform_ocr(
    state: PerformOCRState,
) -> Command[Literal["extract_main_data", "__end__"]]:
    """
    Perform OCR on the document.
    """
    doc_path = state.doc_path
    print("Performing OCR on the document...")
    extracted_text = ocr_processor.extract_text_from_base64_image(doc_path)

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
    """
    doc_path = state.doc_path
    extracted_text = state.ocr_text
    print("Saving the extracted OCR text to a local JSON file...")
    file_name = doc_path.split("/")[-1].split(".")[0]
    output_dir = "output_data"
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    json_file_path = os.path.join(output_dir, f"{file_name}.json")
    with open(json_file_path, "w") as json_file:
        json.dump({"ocr_text": extracted_text}, json_file)

    return Command(goto=END)

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