import os
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest


class DocumentIntelligenceAuth:
    def __init__(self):
        self.endpoint = os.getenv("ENDPOINT_DOCINT")
        self.key = os.getenv("API_KEY_DOCINT")

    def get_client(self):
        return DocumentIntelligenceClient(endpoint=self.endpoint, credential=AzureKeyCredential(self.key))


class OCRProcessor:
    def __init__(self, client):
        """Initializes the OCRProcessor with a DocumentIntelligenceClient."""
        self.client = client

    def extract_text_from_url(self, document_url):
        """Analyzes a document from a URL using the prebuilt-read model.

        Args:
            document_url: The URL of the document (e.g., SAS URL).

        Returns:
            The extracted text content as a string, or None if an error occurs.
        """
        try:
            analyze_request = AnalyzeDocumentRequest(url_source=document_url)
            poller = self.client.begin_analyze_document(
                "prebuilt-read",
                analyze_request,  # Pass AnalyzeDocumentRequest as body
            )
            result = poller.result()

            extracted_text = ""
            for page in result.pages:
                for line in page.lines:
                    extracted_text += line.content + "\n"
            return extracted_text
        except Exception as e:
            print(f"Error during OCR processing: {e}")
            return None
