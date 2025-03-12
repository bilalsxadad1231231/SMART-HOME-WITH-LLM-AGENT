from langchain_community.vectorstores import FAISS
from langchain.llms.base import LLM
from groq import Groq
from typing import Any, List, Optional, Dict
from pydantic import Field, BaseModel
import os
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain_community.llms import Ollama


class GroqLLM(LLM, BaseModel):
    groq_api_key: str = Field(..., description="Groq API Key")
    model_name: str = Field(default="llama-3.3-70b-versatile", description="Model name to use")
    client: Optional[Any] = None

    def __init__(self, **data):
        super().__init__(**data)
        self.client = Groq(api_key=self.groq_api_key)
    
    @property
    def _llm_type(self) -> str:
        return "groq"

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any) -> str:
        completion = self.client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=self.model_name,
            **kwargs
        )
        return completion.choices[0].message.content
    
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """Get the identifying parameters."""
        return {
            "model_name": self.model_name
        }
        
# llm = Ollama(
#     model="qwen2.5-coder:3b",  # Your local model name
#     base_url="http://localhost:11434"  # Default Ollama API endpoint
# )