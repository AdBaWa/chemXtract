from pydantic import BaseModel, Field
from typing import Annotated, List
import operator


class MainInfo(BaseModel):
    supplier: str = ""
    invoice_number: str = ""
    invoice_date: str = ""


class BaseState(BaseModel):
    doc_path: str = ""
    error: str = ""
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
    ocr_text: str = ""
    images: List[str] = []
    table_data_result: dict = {}
    confidence: str = ""
    reason: str = ""
    retried: bool = False
