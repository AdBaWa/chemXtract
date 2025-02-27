from pydantic import BaseModel, Field
from typing import Annotated, List
import operator
from typing import Dict, Any

class MainInfo(BaseModel):
    supplier: str = ""
    invoice_number: str = ""
    invoice_date: str = ""


class BaseState(BaseModel):
    doc_path: str = ""
    error: str = ""
    pdf_page_images: list[str] = []
    pages: list[Dict[str, Any]] = []
    tables: list[Dict[str, Any]] = []
    input_tokens: Annotated[int, operator.add] = 0
    output_tokens: Annotated[int, operator.add] = 0


class PerformOCRState(BaseState):
    ocr_text: str = ""


class ExtractMainDataState(BaseState):
    ocr_text: str = ""
    main_info: MainInfo = None
    confidence: str = Field(default="")
    reason: str = Field(default="")
    retried: bool = False

class ExtractTableDataState(BaseState):
    #ocr_text: str = "" # tables
    #images: List[str] = [] # pages
    #table_data_result: dict = {} # --> subfield of tables ("extracted_data"), type: TableDataResult
    feedback: str|None = None
    retry_counter: int = 1
    curr_table_idx: int = None
    #confidence: str = ""
    #reason: str = ""
    #retried: bool = False


class TableNormingState(BaseState):
    table_data: dict = None
    normalized_table: dict = None
