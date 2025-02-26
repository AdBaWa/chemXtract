import json  
from pathlib import Path  
from typing import Dict, List, Literal, Optional, Any  
from pydantic import BaseModel, Field  
from langchain_core.output_parsers import JsonOutputParser  
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate  
from langgraph.graph import END, START, StateGraph  
from langgraph.types import Command  
from agents.prompts.table_norming_prompts import TABLE_NORMING_SYSTEM_PROMPT, TABLE_NORMING_USER_PROMPT  
from utils import llm  
  
  
# Step 2 -> Step 3: Define models  
class TableDataResult(BaseModel):  
    """Represents the extracted table data and its metadata."""  
    table_data: List[List[str]] = Field(description="The structured table data.")  
    is_weight_percent: bool = Field(description="True if the table data is in weight%, False if in mol%. Or NaN if you are unsure.")  
  
  
class NormalizedTableResult(BaseModel):  
    familyNumber: int  
    patentNumber: int  
    title: str  
    applicant: str  
    tables: List[Dict[str, Any]] = Field(description="The normalized table data associated with pages and examples.")  
  
  
class TableNormingState(BaseModel):  
    doc_path: str  
    table_data: Optional[Dict[str, Any]] = None  # Adjusted to match input structure  
    normalized_table: Optional[NormalizedTableResult] = None  
    error: Optional[str] = None  
  
  
# State functions  
def _init(state: TableNormingState) -> Command[Literal["normalize_table"]]:  
    json_file_path = Path("input_data") / f"{Path(state.doc_path).stem}.json"  
  
    try:  
        with json_file_path.open("r", encoding="utf-8") as f:  
            json_content = json.load(f)  
  
        # Validate JSON structure  
        if "pages" not in json_content or "tables" not in json_content:  
            raise ValueError("JSON must contain 'pages' and 'tables' keys")  
  
        return Command(update={"table_data": json_content}, goto="normalize_table")  
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:  
        return Command(update={"table_data": {}, "error": str(e)}, goto="normalize_table")  
  
  
def _normalize_table(state: TableNormingState) -> Command[Literal["save_normalized_table", "__end__"]]:  
    if state.error or not state.table_data:  
        return Command(update={"error": "No valid table data to normalize"}, goto=END)  
  
    parser = JsonOutputParser(pydantic_object=NormalizedTableResult)  
    try:  
        # Prepare input data for normalization  
        table_data = state.table_data.get("tables", [])  
        pages = state.table_data.get("pages", [])  
  
        # Use TABLE_NORMING prompts to normalize tables  
        messages = [  
            SystemMessagePromptTemplate.from_template(  
                TABLE_NORMING_SYSTEM_PROMPT,  
                partial_variables={"format_instructions": parser.get_format_instructions()}  
            ),  
            HumanMessagePromptTemplate.from_template(  
                TABLE_NORMING_USER_PROMPT,  
                partial_variables={"table_data": table_data}  
            )  
        ]  
        chain = ChatPromptTemplate(messages=messages) | llm | parser  
        parsed_resp = chain.invoke({})  
  
        # Add normalized table response back to state  
        return Command(update={"normalized_table": parsed_resp}, goto="save_normalized_table")  
    except Exception as e:  
        return Command(update={"error": str(e)}, goto=END)  
  
  
def save_normalized_table(state: TableNormingState) -> Command[Literal["__end__"]]:  
    if not state.normalized_table:  
        return Command(goto=END)  
  
    try:  
        output_path = Path("output_data") / f"{Path(state.doc_path).stem}_normalized.json"  
        output_path.parent.mkdir(exist_ok=True)  
  
        # Save normalized table with abnormal material details  
        data = {  
            "normalized_table": state.normalized_table.model_dump(),  
            "abnormal_material": state.abnormal_material,  
            "abnormal_details": state.abnormal_details  
        }  
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")  
        return Command(goto=END)  
    except Exception as e:  
        return Command(update={"error": str(e)}, goto=END)  
  
  
# Build the state graph  
def construct_table_norming() -> StateGraph:  
    workflow = StateGraph(TableNormingState)  
    workflow.add_node("init", _init)  
    workflow.add_node("normalize_table", _normalize_table)  
    workflow.add_node("save_normalized_table", save_normalized_table)  
  
    workflow.add_edge(START, "init")  
    workflow.add_edge("normalize_table", "save_normalized_table")  
    workflow.add_edge("save_normalized_table", END)  

    graph = workflow.compile()

    bytes = graph.get_graph().draw_mermaid_png()
    with open("table_norming_agent.png", "wb") as f:
        f.write(bytes)
  
    return workflow.compile()  
  
# Main function to execute the workflow  
def main():  
    state_graph = construct_table_norming()  
    state = TableNormingState(doc_path="input_data/test_horizontal.json")  
  
    while True:  
        # Convert the state to a dictionary for update_state  
        state_dict = state.model_dump()  # Use .dict() for older Pydantic versions  
        command_dict = state_graph.invoke(state_dict)  
          
        if command_dict.get("goto") == END:  
            break  
          
        # Convert the updated state back to a Pydantic model  
        updated_state_dict = command_dict.get("update", {})  
        state = TableNormingState(**{**state_dict, **updated_state_dict})    
  
  
if __name__ == "__main__":  
    main()  