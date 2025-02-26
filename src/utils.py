from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv
import os
from langchain_azure_ai.chat_models import AzureAIChatCompletionsModel


load_dotenv()
llm = AzureChatOpenAI(azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"), temperature=0.0)
phi4 = AzureAIChatCompletionsModel(
    endpoint=os.getenv("AZURE_AI_SERVICES_ENDPOINT"),
    credential=os.getenv("AZURE_AI_SERVICES_CREDENTIALS"),
    model_name=os.getenv("AZURE_AI_SERVICES_PHI4_MODEL_NAME"),
    model=os.getenv("AZURE_AI_SERVICES_PHI4_MODEL_NAME"),
)
