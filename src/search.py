from typing import Optional
from pydantic import BaseModel
from sqlalchemy import select
from src.database import get_db, ContentChunk, Material


class SearchResult(BaseModel):
    chunk_text: str
    page: int
    material_id: int
    material_name: str


def index_material(material_id: int) -> list[ContentChunk]:
    """Get all chunks for a material from the database."""
    db = next(get_db())
    try:
        chunks = db.query(ContentChunk).filter(
            ContentChunk.material_id == material_id
        ).all()
        return chunks
    finally:
        db.close()


def search(
    query: str,
    material_id: Optional[int] = None,
    page_start: Optional[int] = None,
    page_end: Optional[int] = None
) -> list[SearchResult]:
    """Search content chunks by query text with optional filters."""
    db = next(get_db())
    try:
        stmt = select(ContentChunk, Material).join(
            Material, ContentChunk.material_id == Material.id
        ).where(
            ContentChunk.chunk_text.like(f"%{query}%")
        )

        if material_id is not None:
            stmt = stmt.where(ContentChunk.material_id == material_id)

        if page_start is not None:
            stmt = stmt.where(ContentChunk.page >= page_start)

        if page_end is not None:
            stmt = stmt.where(ContentChunk.page <= page_end)

        results = db.execute(stmt).all()

        search_results = [
            SearchResult(
                chunk_text=chunk.chunk_text,
                page=chunk.page,
                material_id=chunk.material_id,
                material_name=material.filename
            )
            for chunk, material in results
        ]

        return search_results
    finally:
        db.close()
