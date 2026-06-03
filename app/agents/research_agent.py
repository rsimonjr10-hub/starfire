"""
Research Agent — semantic knowledge retrieval and synthesis.

Given a query, searches the user's knowledge base (RAG), synthesizes
findings, and produces a research summary.
"""
import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.models.user import User
from app.services.rag import search, build_rag_context


class ResearchAgent(BaseAgent):
    name = "research"
    description = "Knowledge retrieval and synthesis from the user's knowledge base"

    async def run(self, db: AsyncSession, user: User, input_data: dict) -> dict:
        query = input_data.get("query", "")
        if not query:
            return {"report_text": "No query provided."}

        # Retrieve relevant knowledge
        items = await search(db, user.id, query, limit=8)
        rag_ctx = await build_rag_context(db, user.id, query, max_chars=6000)

        system = (
            "You are the Research Agent for STARFIRE OS. Your job is to synthesize the user's "
            "personal knowledge base to answer questions and produce research summaries. "
            "Always cite specific notes/documents by title. Be analytical and precise."
        )

        user_msg = f"""Research Query: {query}

{rag_ctx if rag_ctx else "No relevant knowledge items found in the knowledge base."}

Based on the above knowledge base content, produce a comprehensive research summary that:
1. Directly answers the query
2. Synthesizes key insights from relevant notes/documents
3. Identifies any gaps or contradictions
4. Suggests follow-up questions or actions

If no relevant knowledge was found, say so clearly and suggest what to add to the knowledge base."""

        report = await self._llm(system, user_msg, max_tokens=2000)

        return {
            "report_text": report,
            "sources": [
                {"id": item.id, "title": item.title, "type": item.item_type}
                for item in items
            ],
            "query": query,
        }
