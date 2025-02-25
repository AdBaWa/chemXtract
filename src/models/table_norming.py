from typing import Any, Dict, List, Optional
from model import BaseState

class TableNormingState(BaseState):
    """State for table normalization processing."""
    
    table_data: Optional[Dict[str, Any]] = None
    normalized_table: Optional[Dict[str, Any]] = None
    abnormal_material: bool = False
    abnormal_details: Dict[int, List[str]] = {}
    error: Optional[str] = None
