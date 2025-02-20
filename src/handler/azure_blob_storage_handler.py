import os
from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas, BlobClient
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv


class AzureBlobStorageManager:
    """
    Manages interactions with Azure Blob Storage, including container access and SAS URL generation.

    This class is initialized by reading configuration values from environment variables,
    specifically those defined in a `.env` file loaded using `python-dotenv`.

    **Environment Variables Required (in .env file):**

    - `AZURE_STORAGE_ACCOUNT_NAME`:  The name of your Azure Storage Account.
    - `AZURE_STORAGE_ACCOUNT_KEY`:  The access key for your Azure Storage Account.
    - `AZURE_STORAGE_CONTAINER_NAME`: The name of the Azure Blob Storage container you want to access.
    """

    def __init__(self):
        """
        Initializes AzureBlobStorageManager by loading storage account and container
        configuration from environment variables.

        **Environment Variables (expected to be set in .env file):**

        - `AZURE_STORAGE_ACCOUNT_NAME`:  (Required) The name of your Azure Storage Account.
        - `AZURE_STORAGE_ACCOUNT_KEY`:  (Required) The access key for your Azure Storage Account.
        - `AZURE_STORAGE_CONTAINER_NAME`: (Required) The name of the Azure Blob Storage container.

        Raises:
            ValueError: If any of the required environment variables are not set.
        """
        load_dotenv()
        self.account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
        self.account_key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
        self.container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME")

        if not self.account_name:
            raise ValueError("AZURE_STORAGE_ACCOUNT_NAME environment variable not set.")
        if not self.account_key:
            raise ValueError("AZURE_STORAGE_ACCOUNT_KEY environment variable not set.")
        if not self.container_name:
            raise ValueError("AZURE_STORAGE_CONTAINER_NAME environment variable not set.")

        self.blob_service_client = self._create_blob_service_client()
        self.container_client = self._get_container_client()

    def _create_blob_service_client(self):
        """
        Creates and returns a BlobServiceClient using the storage account connection string.

        Returns:
            BlobServiceClient: Initialized BlobServiceClient.
        """
        connect_str = f"DefaultEndpointsProtocol=https;AccountName={self.account_name};AccountKey={self.account_key};EndpointSuffix=core.windows.net"
        try:
            blob_service_client = BlobServiceClient.from_connection_string(connect_str)
            print("BlobServiceClient initialized successfully.")
            return blob_service_client
        except Exception as e:
            print(f"Error initializing BlobServiceClient: {e}")
            raise

    def _get_container_client(self):
        """
        Gets and returns a ContainerClient for the specified container name.

        Returns:
            ContainerClient: ContainerClient for the specified container.
        """
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            print(f"ContainerClient for '{self.container_name}' obtained successfully.")
            return container_client
        except Exception as e:
            print(f"Error getting ContainerClient for '{self.container_name}': {e}")
            raise

    def find_blob_by_filename(self, filename):
        """
        Searches for a blob in the container by its filename.

        Iterates through all blobs in the container and checks if the name of any blob
        ends with the provided filename. This allows finding blobs without knowing the full path.

        Args:
            filename (str): The filename to search for (e.g., "1524643529172026216015001.pdf").

        Returns:
            str or None: The full blob name (including path) if a blob with the given filename is found,
                         otherwise None.
        """
        try:
            blob_list = self.container_client.list_blobs()
            for blob in blob_list:
                if blob.name.endswith(filename):  # Check if blob name ends with the filename
                    print(f"Found blob with filename '{filename}': '{blob.name}'")
                    return blob.name  # Return the full blob name (path)
            print(f"Blob with filename '{filename}' not found in container '{self.container_name}'.")
            return None  # Blob not found
        except Exception as e:
            print(f"Error searching for blob by filename '{filename}': {e}")
            return None

    def generate_sas_url(self, blob_name, expiry_hours=2):
        """
        Generates a SAS URL for a specific blob in the container.

        Also accepts just the filename without path. It will first try to find the full blob path
        using `find_blob_by_filename` if the provided `blob_name` does not contain a path.

        Args:
            blob_name (str): Name of the blob (can be just filename or full path).
            expiry_hours (int): Number of hours until the SAS URL expires. Defaults to 2 hours.

        Returns:
            str: SAS URL for the blob, or None if an error occurs or blob is not found.
        """
        full_blob_name = blob_name

        # Check if blob_name looks like just a filename (no path separators)
        if "/" not in blob_name and "\\" not in blob_name:
            full_blob_name = self.find_blob_by_filename(blob_name)
            if not full_blob_name:
                print(f"Could not find blob with filename '{blob_name}' to generate SAS URL.")
                return None

        try:
            sas_token = generate_blob_sas(
                account_name=self.account_name,
                container_name=self.container_name,
                blob_name=full_blob_name,
                account_key=self.account_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
            )
            sas_url = (
                f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{full_blob_name}?{sas_token}"
            )
            print(f"SAS URL generated for blob '{full_blob_name}'.")
            return sas_url
        except Exception as e:
            print(f"Error generating SAS URL for blob '{full_blob_name}': {e}")
            return None

    def blob_exists(self, blob_name):
        """
        Checks if a blob exists in the container.

        Also accepts just the filename. It will first try to find the full blob path
        using `find_blob_by_filename` if the provided `blob_name` does not contain a path.

        Args:
            blob_name (str): Name of the blob to check (can be just filename or full path).

        Returns:
            bool: True if the blob exists, False otherwise.
        """
        full_blob_name = blob_name

        if "/" not in blob_name and "\\" not in blob_name:
            full_blob_name = self.find_blob_by_filename(blob_name)
            if not full_blob_name:
                print(f"Blob with filename '{blob_name}' does not exist (not found by filename search).")
                return False

        try:
            blob_client: BlobClient = self.container_client.get_blob_client(blob=full_blob_name)
            exists = blob_client.exists()
            if exists:
                print(f"Blob '{full_blob_name}' exists in container '{self.container_name}'.")
            else:
                print(f"Blob '{full_blob_name}' does not exist in container '{self.container_name}'.")
            return exists
        except Exception as e:
            print(f"Error checking if blob '{full_blob_name}' exists: {e}")
            return False

    def download_blob_content(self, blob_name):
        """
        Downloads the content of a blob as bytes.

        Also accepts just the filename. It will first try to find the full blob path
        using `find_blob_by_filename` if the provided `blob_name` does not contain a path.

        Args:
            blob_name (str): Name of the blob to download (can be just filename or full path).

        Returns:
            bytes or None: The content of the blob as bytes, or None if download fails or blob is not found.
        """
        full_blob_name = blob_name

        if "/" not in blob_name and "\\" not in blob_name:
            full_blob_name = self.find_blob_by_filename(blob_name)
            if not full_blob_name:
                print(f"Blob with filename '{blob_name}' not found, cannot download content.")
                return None

        try:
            blob_client: BlobClient = self.container_client.get_blob_client(blob=full_blob_name)
            download_stream = blob_client.download_blob()
            blob_content = download_stream.readall()
            print(f"Content of blob '{full_blob_name}' downloaded successfully.")
            return blob_content
        except Exception as e:
            print(f"Error downloading content of blob '{full_blob_name}': {e}")
            return None


if __name__ == "__main__":
    # Example usage of AzureBlobStorageManager
    print("#" * 80)
    print("#  AzureBlobStorageManager Example Usage")
    print("#  Before running, ensure you have:")
    print("#  1. Created a .env file in the same directory as this script.")
    print("#  2. Set the following environment variables in your .env file:")
    print("#     - AZURE_STORAGE_ACCOUNT_NAME=your_account_name")
    print("#     - AZURE_STORAGE_ACCOUNT_KEY=your_account_key")
    print("#     - AZURE_STORAGE_CONTAINER_NAME=your_container_name")
    print("#  3. Replace the example blob paths/filenames below with actual values")
    print("#     from your Azure Blob Storage container.")
    print("#" * 80)

    try:
        blob_storage_manager = AzureBlobStorageManager()

        document_paths_example = [
            {"path": "path/to/your/document1.pdf"},  # Replace with a real blob path
            {"path": "images/photo.jpg"},             # Replace with another real blob path
            {"path": "report.docx"},                  # Example filename (will use find_blob_by_filename)
        ]

        print("\nStarting example usage of AzureBlobStorageManager...")

        for doc_info in document_paths_example:
            blob_name = doc_info["path"]

            if blob_storage_manager.blob_exists(blob_name):
                sas_url = blob_storage_manager.generate_sas_url(blob_name=blob_name)
                if sas_url:
                    print(f"\nSAS URL for blob '{blob_name}':")
                    print(sas_url)
                else:
                    print(f"Failed to generate SAS URL for blob '{blob_name}'.")
            else:
                print(f"Blob '{blob_name}' does not exist in the container.")

        print("\nExample usage complete.")

        print("\nStarting example usage of AzureBlobStorageManager to download blob content...")
        example_blob_name_download = "example_blob.txt" # Replace with a real blob name or filename
        
        blob_content = blob_storage_manager.download_blob_content(example_blob_name_download)
        if blob_content:
            print(f"\nContent of blob '{example_blob_name_download}' (first 100 bytes shown, total length: {len(blob_content)} bytes):")
            print(blob_content[:100])
        else:
            print(f"Failed to download content of blob '{example_blob_name_download}'.")

    except ValueError as ve:
        print(f"Configuration Error: {ve}")
        print("Please ensure you have set the required Azure Storage environment variables in your .env file.")
    except Exception as e:
        print(f"An error occurred: {e}")
