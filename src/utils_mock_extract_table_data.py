import base64
from model import ExtractTableDataState
import pickle
from typing import Any, Dict, List
from azure.ai.documentintelligence.models import AnalyzeResult


def convert_png_to_base64(png_file_path):
    with open(png_file_path, "rb") as image_file:
        base64_string = base64.b64encode(image_file.read()).decode("utf-8")
    return base64_string


def mock_extract_table_data_state() -> ExtractTableDataState:
    # Example usage
    png_file_path = "mock_tabledata/56388722_us2015274579_page-06.png"
    base64_string = convert_png_to_base64(png_file_path)

    ocr_file_path = "mock_tabledata/US7227700_2025-01-13T12-28-14Z.pkl"
    with open(ocr_file_path, "rb") as f:
        ocr_data = pickle.load(f)  # Load the object synchronously

    print("ready")
    return ExtractTableDataState(ocr_text=ocr_data, images=[base64_string], table_data_result=None, confidence=None, reason=None, retried=False)


def load_from_pickle(filename):
    with open(filename, "rb") as file:
        data = pickle.load(file)
    return data


# Load the `pages` object from the pickle file
# pages = load_from_pickle('mock_tabledata/56388722_us2015274579_pages1.pkl')
# page_6 = pages[5]

# Load the `tables` object from the pickle file
# tables = load_from_pickle('mock_tabledata/56388722_us2015274579_tables1.pkl')
# table_05 = tables[5]

# Example usage: print the loaded data
# print("Loaded pages:", pages)
# print("Loaded tables:", tables)

print("test")


# if __name__ == "__main__":
#    mock_extract_table_data_state()
