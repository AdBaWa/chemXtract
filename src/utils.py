from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv
import os


load_dotenv()
llm = AzureChatOpenAI(azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"), temperature=0.0)
