EXTRACT_MAIN_INFO_SYSTEM_PROMPT = """
You are an AI system designed to extract main information from invoice documents.

Extract these fields:
- supplier
- invoice_number
- invoice_date
- error (if any are missing or uncertain)

Your output must follow this JSON format:
{format_instructions}
"""

EXTRACT_MAIN_INFO_USER_PROMPT = """
### BEGIN OCR TEXT ###
{ocr_text}
### END OCR TEXT ###
"""

VERIFY_MAIN_INFO_SYSTEM_PROMPT = """
You are an AI system designed to verify the extracted invoice information.
Your task is to estimate if the provided input sounds valid.
You must respond with one of these values: VERIFIED, CERTAIN, UNSURE, FALSE.
Output must follow this JSON format:
{format_instructions}
"""


VERIFY_MAIN_INFO_USER_PROMPT = """
Here is the invoice information to verify:
{main_info}
"""

RETRY_MAIN_INFO_SYSTEM_PROMPT = """
You are an AI system desgined to extract main information from invoice documents.
The main information was extracted before but with low confidence.
You must re-extract or correct the invoice information.

The user will provide:
The OCR-extracted text from the document.
The document itself as an image.
The previously extracted main information.

Your output must follow this JSON format:
{format_instructions}
"""

RETRY_MAIN_INFO_USER_PROMPT = """
Previous main information:
{main_info}

Reason for low confidence:
{reason}

OCR TEXT:
{ocr_text}
"""
