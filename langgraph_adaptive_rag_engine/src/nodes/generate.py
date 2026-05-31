from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from src.config.settings import get_settings
from src.state import AgentState


GENERATE_SYSTEM_PROMPT = """\
You are a helpful assistant that answers questions based on the provided context.
If the context does not contain enough information, say so honestly.
Do not fabricate information. Cite the source documents when possible."""


async def generate(state: AgentState) -> dict:
    """Generate an answer based on the retrieved documents and the user query."""
    settings = get_settings()

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_API_BASE,
        temperature=0,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", GENERATE_SYSTEM_PROMPT),
        ("human", "Context:\n{context}\n\nQuestion: {question}"),
    ])

    chain = prompt | llm | StrOutputParser()

    context = "\n\n---\n\n".join(
        doc.page_content for doc in state.retrieved_docs
    )

    answer = await chain.ainvoke({
        "context": context,
        "question": state.current_query,
    })

    return {"answer": answer}
