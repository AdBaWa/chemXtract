from langgraph.graph import StateGraph, START, END
from agents.extract_table_agent import construct_extract_table_agent
from model import BaseState
import os


def _construct_graph():
    extract_tables_graph = construct_extract_table_agent()

    workflow = StateGraph(BaseState)
    workflow.add_node("extract_tables", extract_tables_graph)
    #workflow.add_node("extract_main_data", extract_main_data_graph)

    workflow.add_edge(START, "extract_tables")
    #workflow.add_edge("ocr", "extract_main_data")
    workflow.add_edge("extract_tables", END)

    graph = workflow.compile(debug=False)
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


def main():
    pdfs = ["data/56388722_us2015274579.pdf"
            #, "../data/78071_DE1771318A1.pdf"
            #, "../data/80946226_cn111646693.pdf"
            ]
    graph = _construct_graph()
    for pdf in pdfs:
        state = BaseState(doc_path=pdf)
        _ = graph.invoke(state)


if __name__ == "__main__":
    main()
