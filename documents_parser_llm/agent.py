from typing import Annotated

from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from llm import Llm

from langchain_community.chat_models.ollama import ChatOllama
from langchain_community.embeddings import OllamaEmbeddings

from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser

from langchain_core.pydantic_v1 import BaseModel, Field

import chromadb
import uuid

from langchain_chroma import Chroma

from langchain_core.vectorstores import VectorStoreRetriever

class AskTNCD(BaseModel):
    """Cherche les informations dans le thésaurus national de cancérologie digestive."""

    query: str = Field(
        description="information à rechercher dans le document"
    )

import ollama

class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]

from langchain.tools.retriever import create_retriever_tool

# Create a ChromaDB client
client = chromadb.Client()

# Create a collection named "test"
collection = client.create_collection(name="TNCD")

embeddings = OllamaEmbeddings(model="all-minilm")



tool = create_retriever_tool(
    retriever,
    "search_state_of_union",
    "Searches and returns excerpts from the 2022 State of the Union.",
)
tools = [tool]

llm = ChatOllama(
                        
                        format="json",
                        model="phi3:latest",
                        temperature=0
                    )

graph_builder = StateGraph(State)

def chatbot(state: State):
    return {"messages": [llm.invoke(state["messages"])]}


# The first argument is the unique node name
# The second argument is the function or object that will be called whenever
# the node is used.
graph_builder.add_node("chatbot", chatbot)

graph_builder.add_edge(START, "chatbot")

graph_builder.add_edge("chatbot", END)

graph = graph_builder.compile()

while True:
    user_input = input("User: ")
    if user_input.lower() in ["quit", "exit", "q"]:
        print("Goodbye!")
        break
    for event in graph.stream({"messages": ("user", user_input)}):
        for value in event.values():
            print("Assistant:", value["messages"][-1].content)
