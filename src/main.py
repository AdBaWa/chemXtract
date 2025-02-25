from langgraph.graph import StateGraph, START, END
from agents.extract_main_data_agent import construct_extract_main_data
from agents.ocr_agent import construct_ocr
from agents.extract_table_data_agent import construct_extract_table_data
from model import BaseState
import os


def _construct_graph():
    ocr_graph = construct_ocr()
    extract_main_data_graph = construct_extract_main_data()
    extract_table_data_graph = construct_extract_table_data()

    workflow = StateGraph(BaseState)
    workflow.add_node("ocr", ocr_graph)
    workflow.add_node("extract_main_data", extract_main_data_graph)
    workflow.add_node("extract_table_data", extract_table_data_graph)

    workflow.add_edge(START, "ocr")
    workflow.add_edge("ocr", "extract_main_data")
    workflow.add_edge("extract_main_data", "extract_table_data")
    workflow.add_edge("extract_table_data", END)

    graph = workflow.compile(debug=True)
    bytes_graph = graph.get_graph().draw_mermaid_png()
    with open("workflow.png", "wb") as f:
        f.write(bytes_graph)
    return graph


def main_local_files():
    graph = _construct_graph()

    input_folder = "input_data"
    for filename in os.listdir(input_folder):
        filepath = os.path.join(input_folder, filename)
        print(filepath)
        if os.path.isfile(filepath):
            state = BaseState(doc_path=filepath)
            _ = graph.invoke(state)


def main_url():
    urls = ["https://invoiceoffice.de/wp-content/uploads/2021/04/Eine-Beispielrechnung-fu%CC%88r-Freiberufler-und-Unternehmen.png"]
    graph = _construct_graph()
    for url in urls:
        state = BaseState(doc_path=url)
        _ = graph.invoke(state)


if __name__ == "__main__":
    main_url()
