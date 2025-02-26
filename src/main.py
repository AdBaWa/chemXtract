from langgraph.graph import StateGraph, START, END
from agents.extract_table_agent import construct_extract_table_agent
from agents.table_norming_agent import construct_table_norming
from agents.extract_table_data_agent import construct_extract_table_data
from model import BaseState
import os
import requests
from openinference.instrumentation.langchain import LangChainInstrumentor
from phoenix.otel import register

# test for Phoenix by sending an http request to the Phoenix Dashboard
url = "http://localhost:6006/v1/traces"
success = True
try:
    response = requests.get(url)
    success = response.status_code == 200
except Exception:
    success = False

if success:
    tracer_provider = register(
        project_name="default",  # Default is 'default'
        endpoint="http://localhost:6006/v1/traces",
    )
    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
else:
    print("Failed to register Phoenix tracer.")


def _construct_graph():
    extract_tables_graph = construct_extract_table_agent()
    extract_table_data_graph = construct_extract_table_data()
    table_norming_graph = construct_table_norming()

    workflow = StateGraph(BaseState)
    workflow.add_node("extract_tables", extract_tables_graph)
    workflow.add_node("extract_table_data", extract_table_data_graph)
    workflow.add_node("table_norming", table_norming_graph)

    workflow.add_edge(START, "extract_tables")
    workflow.add_edge("extract_tables", "extract_table_data")
    workflow.add_edge("extract_table_data", "table_norming")
    workflow.add_edge("table_norming", END)

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
    pdfs = [  # "data/56388722_us2015274579.pdf"
        # "data/78071_DE1771318A1.pdf"
        "data/80946226_cn111646693.pdf"
    ]
    graph = _construct_graph()
    for pdf in pdfs:
        state = BaseState(doc_path=pdf)
        _ = graph.invoke(state)


if __name__ == "__main__":
    main()
