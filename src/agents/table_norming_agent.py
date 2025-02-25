import json  
import os  
from pathlib import Path  
from typing import Dict, List, Literal, Optional, Set, Any  
import pandas as pd 
from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser  
from langchain_core.prompts import (  
    ChatPromptTemplate,  
    HumanMessagePromptTemplate,  
    SystemMessagePromptTemplate,  
)  
from langgraph.graph import END, START, StateGraph  
from langgraph.types import Command  
from pydantic import BaseModel, Field  
from agents.prompts.table_norming_prompts import (  
    TABLE_NORMING_SYSTEM_PROMPT,  
    TABLE_NORMING_USER_PROMPT,  
)  
# Assuming the model module is in the correct path  
from models.table_norming import TableNormingState, NormalizedTableResult, Example, Molecule 
from utils import llm  
   

def _init(state: TableNormingState) -> Command[Literal["normalize_table"]]:  
    """Initializes the state by loading table data from a JSON file.  
      
    Args:  
        state: The current state containing document path  
          
    Returns:  
        Command to update state and proceed to normalize_table  
          
    Raises:  
        FileNotFoundError: If the JSON file doesn't exist  
        json.JSONDecodeError: If the JSON file is invalid  
    """  
    path = state.doc_path
    output_dir = Path("input_data")
    output_dir.mkdir(exist_ok=True)

    file_name = Path(path).stem
    json_file_path = output_dir / f"{file_name}.json"
    try:
        with open(json_file_path, "r", encoding="utf-8") as json_file:
            json_content = json.load(json_file)

        # If your table data is a 2D list, convert it to a list of dict
        if isinstance(json_content, list) and len(json_content) > 1 and isinstance(json_content[0], list):
            headers = json_content[0]  # The first row is assumed to be headers
            list_of_dicts = []
            for row in json_content[1:]:
                row_dict = {}
                for i, col in enumerate(row):
                    # Safely handle header/row length mismatches
                    col_name = headers[i] if i < len(headers) else f"col{i}"
                    row_dict[col_name] = col
                list_of_dicts.append(row_dict)
            json_content = list_of_dicts

        if not isinstance(json_content, list):
            raise ValueError(f"Expected a list in {json_file_path}, but got {type(json_content)}")
            
        return Command(update={"table_data": json_content}, goto="normalize_table")
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"Error loading table data: {e}")
        return Command(update={"table_data": [], "error": str(e)}, goto="normalize_table")
  
def _normalize_table(state: TableNormingState) -> Command[Literal["check_abnormal_material", "__end__"]]:  
    """Normalizes the table data using an LLM.  
      
    Args:  
        state: The current state containing table data  
          
    Returns:  
        Command to update state with normalized table and proceed  
    """  
    # If there was an error in the previous step, end the workflow  
    if hasattr(state, "error") and state.error:  
        print(f"Skipping normalization due to previous error: {state.error}")  
        return Command(goto=END)  
    if not state.table_data:  
        print("No table data to normalize")  
        return Command(update={"error": "No table data to normalize"}, goto=END)  
      
    parser = JsonOutputParser(pydantic_object=NormalizedTableResult)  
    try:  
        messages = [  
            SystemMessagePromptTemplate.from_template(  
                TABLE_NORMING_SYSTEM_PROMPT,  
                partial_variables={"format_instructions": parser.get_format_instructions()},  
            ),  
            HumanMessagePromptTemplate.from_template(  
                TABLE_NORMING_USER_PROMPT,  
                partial_variables={"table_data": state.table_data},  
                type="text",  
            ),  
        ]  
        prompts = ChatPromptTemplate(messages=messages)  
        chain = prompts | llm | parser  
        resp = chain.invoke({})  
          
        parsed_resp = NormalizedTableResult(**resp) if isinstance(resp, dict) else resp
        return Command(update={"normalized_table": parsed_resp}, goto="check_abnormal_material")  
    except Exception as e:  
        print(f"Error normalizing table: {e}")  
        return Command(update={"error": f"Normalization failed: {str(e)}"}, goto=END)  
  
def _check_abnormal_material(state: TableNormingState) -> Command[Literal["save_normalized_table", "__end__"]]:  
    """Checks for abnormal materials in the normalized table data.  
      
    Args:  
        state: The current state containing normalized table data  
          
    Returns:  
        Command to update state with abnormal material flag and proceed  
    """  
    if not hasattr(state, "normalized_table") or not state.normalized_table:  
        print("No normalized table data to check")  
        return Command(update={"error": "No normalized table data to check"}, goto=END)  
      
    try:  
        # Load the Excel file containing the usual components  
        excel_path = Path("background_info/übliche Komponenten.xlsx")  
        if not excel_path.exists():  
            print(f"Warning: Usual components file not found at {excel_path}")  
            usual_components = set()  
        else:  
            df = pd.read_excel(excel_path)  
            usual_components = set(df['oxide'].dropna().str.strip().tolist())  
          
        # Check for abnormal materials in the normalized table  
        abnormal_materials: Dict[int, List[str]] = {}  
          
        for example in state.normalized_table.examples:  
            unusual_elements = []  
            for molecule in example.molecules:  
                if molecule.element not in usual_components:  
                    unusual_elements.append(molecule.element)  
            if unusual_elements:  
                abnormal_materials[example.id] = unusual_elements  
          
        abnormal_flag = len(abnormal_materials) > 0  
        return Command(  
            update={  
                "abnormal_material": abnormal_flag,  
                "abnormal_details": abnormal_materials if abnormal_flag else {}  
            },   
            goto="save_normalized_table"  
        )  
    except Exception as e:  
        print(f"Error checking abnormal materials: {e}")  
        return Command(update={"error": f"Abnormal material check failed: {str(e)}"}, goto=END)  
  
def save_normalized_table(state: TableNormingState) -> Command[Literal["__end__"]]:  
    """Saves the normalized table data to a JSON file.  
      
    Args:  
        state: The current state containing normalized table data  
          
    Returns:  
        Command to end the workflow  
    """  
    if not hasattr(state, "normalized_table") or not state.normalized_table:  
        print("No normalized table data to save")  
        return Command(goto=END)  
      
    try:  
        doc_path = state.doc_path  
        output_dir = Path("output_data")  
        output_dir.mkdir(exist_ok=True)  
          
        file_name = Path(doc_path).stem  
        json_file_path = output_dir / f"{file_name}_normalized.json"  
        data = {  
            "normalized_table": state.normalized_table.model_dump(),  
            "abnormal_material": getattr(state, "abnormal_material", False),  
        }  
          
        if hasattr(state, "abnormal_details") and state.abnormal_details:  
            data["abnormal_details"] = state.abnormal_details  
          
        with open(json_file_path, "w", encoding="utf-8") as json_file:  
            json.dump(data, json_file, ensure_ascii=False, indent=2)  
          
        print(f"Normalized table saved to {json_file_path}")  
        return Command(goto=END)  
    except Exception as e:  
        print(f"Error saving normalized table: {e}")  
        return Command(update={"error": f"Failed to save normalized table: {str(e)}"}, goto=END)  
  
def construct_table_norming() -> StateGraph:  
    """Constructs and returns the state graph for table normalization.  
      
    Returns:  
        Compiled state graph for table normalization  
    """  
    workflow = StateGraph(TableNormingState)  
    workflow.add_node("init", _init)  
    workflow.add_node("normalize_table", _normalize_table)  
    workflow.add_node("check_abnormal_material", _check_abnormal_material)  
    workflow.add_node("save_normalized_table", save_normalized_table)  
      
    workflow.add_edge(START, "init")  
    workflow.add_edge("normalize_table", "check_abnormal_material")  
    workflow.add_edge("check_abnormal_material", "save_normalized_table")  
    workflow.add_edge("save_normalized_table", END)  
      
    graph = workflow.compile()  
    # Save visualization if possible  
    try:  
        bytes_data = graph.get_graph().draw_mermaid_png()  
        vis_path = Path("visualizations")  
        vis_path.mkdir(exist_ok=True)  
        with open(vis_path / "table_norming.png", "wb") as f:  
            f.write(bytes_data)  
    except Exception as e:  
        print(f"Could not generate graph visualization: {e}")  
      
    return graph  
  
def main():
    state_graph = construct_table_norming()
    current_state = TableNormingState(doc_path="input_data/test.json")

    while True:
        command_dict = state_graph.invoke(current_state)
        # Use dictionary lookups instead of attribute access
        if command_dict.get("goto") == END:
            break
        current_state = state_graph.update_state(current_state, command_dict.get("update", {})) 
  
if __name__ == "__main__":  
    main()