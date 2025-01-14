import re
from io import BytesIO
from typing import Any, Dict, List

import docx2txt
import streamlit as st
from embeddings import OpenAIEmbeddings
from langchain.chains.question_answering import load_qa_chain
from langchain.chains.qa_with_sources import load_qa_with_sources_chain
from langchain.docstore.document import Document
from langchain.llms import AzureOpenAI
from langchain.chat_models import AzureChatOpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import VectorStore
from langchain.vectorstores.faiss import FAISS
from openai.error import AuthenticationError
from prompts import STUFF_PROMPT, REFINE_PROMPT, REFINE_QUESTION_PROMPT
from pypdf import PdfReader


# @st.cache_data
def parse_docx(file: BytesIO) -> str:
    text = docx2txt.process(file)
    # Remove multiple newlines
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text


# @st.cache_data
def parse_pdf(file: BytesIO) -> List[str]:
    pdf = PdfReader(file)
    output = []
    for page in pdf.pages:
        text = page.extract_text()
        # Merge hyphenated words
        text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)
        # Fix newlines in the middle of sentences
        text = re.sub(r"(?<!\n\s)\n(?!\s\n)", " ", text.strip())
        # Remove multiple newlines
        text = re.sub(r"\n\s*\n", "\n\n", text)

        output.append(text)

    return output


# @st.cache_data
def parse_txt(file: BytesIO) -> str:
    text = file.read().decode("utf-8")
    # Remove multiple newlines
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text


# @st.cache_data
def text_to_docs(text: str | List[str]) -> List[Document]:
    """Converts a string or list of strings to a list of Documents
    with metadata."""
    if isinstance(text, str):
        # Take a single string as one page
        text = [text]
    page_docs = [Document(page_content=page) for page in text]

    # Add page numbers as metadata
    for i, doc in enumerate(page_docs):
        doc.metadata["page"] = i + 1

    # Split pages into chunks
    doc_chunks = []

    for doc in page_docs:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""],
            chunk_overlap=0,
        )
        chunks = text_splitter.split_text(doc.page_content)
        for i, chunk in enumerate(chunks):
            doc = Document(
                page_content=chunk, metadata={"page": doc.metadata["page"], "chunk": i}
            )
            # Add sources a metadata
            doc.metadata["source"] = f"{doc.metadata['page']}-{doc.metadata['chunk']}"
            doc_chunks.append(doc)
    return doc_chunks


# @st.cache_data(show_spinner=False)
def embed_docs(docs: List[Document]) -> VectorStore:
    """Embeds a list of Documents and returns a FAISS index"""

    if not st.session_state.get("AZURE_OPENAI_API_KEY"):
        raise AuthenticationError(
            "You need to set the env variable AZURE_OPENAI_API_KEY"
        )
    else:
        # Embed the chunks
        embeddings = OpenAIEmbeddings() 
        index = FAISS.from_documents(docs, embeddings)

        return index


# @st.cache_data
def search_docs(index: VectorStore, query: str) -> List[Document]:
    """Searches a FAISS index for similar chunks to the query
    and returns a list of Documents."""

    # Search for similar chunks
    docs = index.similarity_search(query, k=2)
    return docs


# @st.cache_data
def get_answer(docs: List[Document], 
               query: str, 
               deployment: str, 
               chain_type: str, 
               temperature: float, 
               max_tokens: int
              ) -> Dict[str, Any]:
    
    """Gets an answer to a question from a list of Documents."""

    # Get the answer
    
    if deployment == "gpt-35-turbo":
        llm = AzureChatOpenAI(deployment_name=deployment, temperature=temperature, max_tokens=max_tokens)
    else:
        llm = AzureOpenAI(deployment_name=deployment, temperature=temperature, max_tokens=max_tokens)
    
    chain = load_qa_with_sources_chain(llm, chain_type=chain_type)
    
    answer = chain( {"input_documents": docs, "question": query}, return_only_outputs=True)
    #answer = chain( {"input_documents": docs, "question": query, "language": language}, return_only_outputs=True)

    return answer

# @st.cache_data
def get_answer_turbo(docs: List[Document], 
               query: str, 
               deployment: str, 
               language: str, 
               chain_type: str, 
               temperature: float, 
               max_tokens: int
              ) -> Dict[str, Any]:
    
    """Gets an answer to a question from a list of Documents."""
        # In Azure OpenAI create a deployment named "gpt-35-turbo" for the model "gpt-35-turbo (0301)"

    # Get the answer
    if deployment == "gpt-35-turbo":
        llm = AzureChatOpenAI(deployment_name=deployment, temperature=temperature, max_tokens=max_tokens)
    else:
        llm = AzureChatOpenAI(deployment_name="gpt-35-turbo", model_name="gpt-3.5-turbo-0301", temperature=temperature, max_tokens=max_tokens)
 
    if chain_type=="refine":
        chain = load_qa_chain(llm, chain_type=chain_type, question_prompt=REFINE_QUESTION_PROMPT, refine_prompt=REFINE_PROMPT)    
        answer = chain( {"input_documents": docs, "question": query, "language": language}, return_only_outputs=True)

        #passing answer again to openai to remove any additional leftover wording from chatgpt
        answer = chain({"input_documents": [Document(page_content=answer['output_text'])], "question": query, "language": "English"}, return_only_outputs=False)
    
    if chain_type=="stuff":
        chain = load_qa_chain(llm, chain_type=chain_type, prompt=STUFF_PROMPT)
    
    answer = chain( {"input_documents": docs, "question": query}, return_only_outputs=True)

    return answer

# @st.cache_data
def get_answer_turbo(docs: List[Document], 
               query: str, 
               language: str, 
               chain_type: str, 
               temperature: float, 
               max_tokens: int
              ) -> Dict[str, Any]:
    
    """Gets an answer to a question from a list of Documents."""

    # Get the answer
   
    # In Azure OpenAI create a deployment named "gpt-35-turbo" for the model "gpt-35-turbo (0301)"
    llm = AzureChatOpenAI(deployment_name="gpt-35-turbo", model_name="gpt-3.5-turbo-0301", temperature=temperature, max_tokens=max_tokens)
 
    if chain_type=="refine":
        chain = load_qa_chain(llm, chain_type=chain_type, question_prompt=REFINE_QUESTION_PROMPT, refine_prompt=REFINE_PROMPT)    
        answer = chain( {"input_documents": docs, "question": query, "language": language}, return_only_outputs=True)

        #passing answer again to openai to remove any additional leftover wording from chatgpt
        answer = chain({"input_documents": [Document(page_content=answer['output_text'])], "question": query, "language": "English"}, return_only_outputs=False)
    
    if chain_type=="stuff":
        chain = load_qa_chain(llm, chain_type=chain_type, prompt=STUFF_PROMPT)
        answer = chain( {"input_documents": docs, "question": query, "language": language}, return_only_outputs=False)       

    return answer


# @st.cache_data
def get_sources(answer: Dict[str, Any], docs: List[Document]) -> List[Document]:
    """Gets the source documents for an answer."""

    # Get sources for the answer
    source_keys = [s for s in answer["output_text"].split("SOURCES: ")[-1].split(", ")]

    source_docs = []
    for doc in docs:
        if doc.metadata["source"] in source_keys:
            source_docs.append(doc)

    return source_docs


def wrap_text_in_html(text: str | List[str]) -> str:
    """Wraps each text block separated by newlines in <p> tags"""
    if isinstance(text, list):
        # Add horizontal rules between pages
        text = "\n<hr/>\n".join(text)
    return "".join([f"<p>{line}</p>" for line in text.split("\n")])
