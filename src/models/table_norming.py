from typing import Any, Dict, List, Optional
from model import BaseState
from pydantic import BaseModel, Field  # Make sure this line exists

class Molecule(BaseModel):  
    """Represents a molecule with its element and percentage."""  
    element: str  
    percentage: float  
  
class Example(BaseModel):  
    """Represents an example with its ID and molecules."""  
    id: int  
    molecules: List[Molecule] 

class NormalizedTableResult(BaseModel):  
    """Represents the normalized table data."""  
    familyNumber: int  
    patentNumber: int  
    title: str  
    applicant: str  
    examples: List[Example] = Field(description="List of examples extracted from the table")  
  
class TableNormingState(BaseModel):
    """State for table normalization processing."""
    doc_path: str
    table_data: Optional[List[Dict[str, Any]]] = None
    normalized_table: Optional[NormalizedTableResult] = None  # CHANGED: store the model
    abnormal_material: bool = False
    abnormal_details: Dict[int, List[str]] = {}
    error: Optional[str] = None