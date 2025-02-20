import os
from dotenv import load_dotenv
from azure.cosmos import cosmos_client, exceptions, ContainerProxy, CosmosDict
from typing import Tuple, Any, List
import logging
from data_models import Document

log = logging.getLogger("cosmosdb")


class CosmosDBManager:
    container: ContainerProxy

    """
    A class to manage interactions with Azure Cosmos DB.

    To use this class, you must have a .env file in the same directory
    containing the following environment variables:

    - HOST: Your Azure Cosmos DB account URI.
    - MASTER_KEY: Your Azure Cosmos DB account primary or secondary key.
    - DATABASE_ID: The ID of the Cosmos DB database to use.
    - CONTAINER_ID: The ID of the Cosmos DB container within the database to use.
    """

    def __init__(self):
        """
        Initializes the CosmosDBManager by loading environment variables from a .env file
        and initializing the Azure Cosmos DB client.

        The following environment variables must be set in the .env file:
        - HOST: Your Azure Cosmos DB account URI.
        - MASTER_KEY: Your Azure Cosmos DB account primary or secondary key.
        - DATABASE_ID: The ID of the Cosmos DB database to use.
        - CONTAINER_ID: The ID of the Cosmos DB container within the database to use.
        """
        load_dotenv()
        self.HOST = os.environ.get("HOST")
        self.MASTER_KEY = os.environ.get("MASTER_KEY")
        self.DATABASE_ID = os.environ.get("DATABASE_ID")
        self.CONTAINER_ID = os.environ.get("CONTAINER_ID")
        self.client, self.db, self.container = self._initialize_cosmosdb()

    def _initialize_cosmosdb(self) -> Tuple[cosmos_client.CosmosClient, Any, Any]:
        """
        Initializes the Cosmos DB client and returns the database and container clients.
        This is a private method called during class initialization.
        """
        log.debug("Initializing Cosmos DB client")

        client = cosmos_client.CosmosClient(
            self.HOST, {"masterKey": self.MASTER_KEY}, user_agent="LangGraphCosmosDB", user_agent_overwrite=True
        )
        try:
            db = client.get_database_client(self.DATABASE_ID)
            container = db.get_container_client(self.CONTAINER_ID)
            log.debug("Cosmos DB client initialized successfully")
            return client, db, container

        except exceptions.CosmosHttpResponseError as e:
            log.error(f"Error occurred while initializing Cosmos DB client: {e.message}")
            raise
        except Exception as e:
            log.error(f"An unexpected error occurred while initializing Cosmos DB client: {e}")
            raise

    def get_cosmos_item_by_id(self, item_id):
        """
        Retrieves an item from Cosmos DB by its ID.
        """
        return self._get_cosmos_item_by_id_internal(self.container, item_id)

    def _get_cosmos_item_by_id_internal(self, container: ContainerProxy, item_id) -> CosmosDict:
        """
        Internal method to retrieve an item from Cosmos DB by its ID.
        Separated for potential reuse or overriding without exposing container directly in public method signature.
        """
        log.debug(f"Getting item with Id: {item_id}")
        try:
            # Assuming the partition key is the same as the item_id
            response = container.read_item(item=item_id, partition_key=item_id)
            log.debug(f"Item Id: {response.get('id')}")
            return response
        except exceptions.CosmosHttpResponseError as e:
            log.error(f"Error occurred while getting item: {e.message}")
            return None

    def extract_nested_values_from_item(self, item_id: str, keys_path: List[str]) -> List[Any]:
        """
        Extracts values from a Cosmos DB item based on a provided path of keys.

        Args:
            item_id (str): The ID of the Cosmos DB item to retrieve.
            keys_path (List[str]): A list of keys representing the path to the desired values.
                                     For example, to get 'path' from 'documents' array, keys_path would be ['documents', 'path'].

        Returns:
            List[Any]: A list of extracted values, or an empty list if the item or path is not found, or if extraction fails.
        """
        item = self.get_cosmos_item_by_id(item_id)
        if not item:
            log.debug(f"Could not retrieve item with id '{item_id}'.")
            return []

        current_level = item
        for key in keys_path[:-1]:  # Iterate through keys except the last one to navigate the structure
            if key in current_level:
                current_level = current_level.get(key)
                if not isinstance(current_level, dict) and not isinstance(
                    current_level, list
                ):  # Ensure we can continue to navigate
                    log.debug(f"Path element '{key}' did not lead to a nested structure (dict or list) as expected.")
                    return []  # Stop if we can't navigate further
            else:
                log.error(f"Key '{key}' not found in the item for path '{keys_path}'.")
                return []  # Key not found, path is invalid

        target_key = keys_path[-1]  # The last key is the one from which we want to extract values
        extracted_values = []

        if isinstance(current_level, list):  # Handle case where the level before the last key is a list
            for element in current_level:
                if isinstance(element, dict) and target_key in element:
                    extracted_values.append(element.get(target_key))
        elif isinstance(current_level, dict) and target_key in current_level:  # Handle case where it's a dict
            # If the target key is found at this level, and it's a list, extend the results. If it's a single value, append it.
            target_value = current_level.get(target_key)
            if isinstance(target_value, list):
                extracted_values.extend(target_value)  # Extend if it's a list of values
            else:
                extracted_values.append(target_value)  # Append if it's a single value

        else:
            log.error(f"Target key '{target_key}' not found at the end of path '{keys_path}'.")
            return []  # Target key not found

        return extracted_values



    def create_item(self, item_body):
        """
        Creates an item in Cosmos DB.

        Args:
            item_id (str): The ID of the item to update.
            item_body (dict): A dictionary representing the complete updated item.
                                 It MUST include the 'id' of the item and any other fields you want to update.
        Returns:
            dict: The updated item as returned by Cosmos DB, or None if the update failed.
        """
        log.debug(f"Updating item with Id: {item_body['id']}")
        try:
            response = self.container.create_item(body=item_body)
            log.debug(f"Updated Item Id: {response.get('id')}")
            return response
        except exceptions.CosmosHttpResponseError as e:
            log.error(f"Error occurred while updating item: {e.message}")
            log.error(f"Status Code: {e.status_code}, Sub-status: {e.sub_status}")  # More detailed error info
            log.error(f"Error Message: {e.message}")
            return None
        except Exception as e:
            log.error(f"An unexpected error occurred while updating item: {e}")
            return None

    def update_cosmos_item(self, item_id, item_body):
        """
        Updates an item in Cosmos DB.

        Args:
            item_id (str): The ID of the item to update.
            item_body (dict): A dictionary representing the complete updated item.
                                 It MUST include the 'id' of the item and any other fields you want to update.
        Returns:
            dict: The updated item as returned by Cosmos DB, or None if the update failed.
        """
        log.debug(f"Updating item with Id: {item_id}")
        try:
            response = self.container.replace_item(item=item_id, body=item_body)
            log.debug(f"Updated Item Id: {response.get('id')}")
            return response
        except exceptions.CosmosHttpResponseError as e:
            log.error(f"Error occurred while updating item: {e.message}")
            log.error(f"Status Code: {e.status_code}, Sub-status: {e.sub_status}")  # More detailed error info
            log.error(f"Error Message: {e.message}")
            return None
        except Exception as e:
            log.error(f"An unexpected error occurred while updating item: {e}")
            return None

    def get_cosmos_items_iterable(self):
        """
        Retrieves items from Cosmos DB container efficiently using an iterator.
        """
        log.debug("Retrieving items from Cosmos DB container efficiently")
        try:
            items_iterable = self.container.read_all_items()
            log.debug("Cosmos DB items iterable obtained.")
            return items_iterable
        except exceptions.CosmosHttpResponseError as e:
            log.error(f"Error occurred while retrieving items from Cosmos DB: {e.message}")
            return None
        except Exception as e:
            log.error(f"An unexpected error occurred while retrieving items from Cosmos DB: {e}")
            return None



# Example usage:
if __name__ == "__main__":
    try:
        cosmos_manager = CosmosDBManager()

        item_id_to_get = "001"

        # --- Example: Get an item  ---
        item = cosmos_manager.get_cosmos_item_by_id(item_id_to_get)
        if item:
            log.debug(f"Item: {item}")

        # Example of getting a nested item 
        document_paths = cosmos_manager.extract_nested_values_from_item(item_id_to_get, ["documents", "path"])
        if document_paths:
            log.debug(f"Document paths: {document_paths}")

    except Exception as e:
        log.error(f"An error occurred: {e}")


