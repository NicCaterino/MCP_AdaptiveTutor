import re
import fitz
from typing import List, Dict


def clean_text(text: str) -> str:
    """Clean extracted text by removing image references and noise."""
    lines = text.split('\n')
    cleaned_lines = []
    
    skip_patterns = [
        r'immagine\s*\d+',
        r'image\s*\d+',
        r'fig\.\s*\d+',
        r'figure\s*\d+',
        r'img\s*\d+',
        r'picture\s*\d+',
        r'photo\s*\d+',
        r'vedi\s+figura',
        r'see\s+figure',
        r'\[\s*\d+\s*\]',
        r'page\s*\d+\s+of\s*\d+',
    ]
    
    for line in lines:
        line = line.strip()
        
        skip = False
        for pattern in skip_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                skip = True
                break
        
        if skip:
            continue
        
        if len(line) > 2:
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


def extract_text_from_pdf(path: str) -> List[Dict[str, any]]:
    """
    Extract text from a PDF file.
    
    Args:
        path: Path to the PDF file
        
    Returns:
        List of dicts with 'page' and 'text' keys
    """
    try:
        doc = fitz.open(path)
        results = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            text = clean_text(text)
            text = text.strip()
            
            if text:
                results.append({
                    "page": page_num + 1,
                    "text": text
                })
        doc.close()
        return results
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF: {e}")


def chunk_text(text: str, chunk_size: int = 500) -> List[str]:
    """
    Split text into chunks of specified size.
    
    Args:
        text: Text to split
        chunk_size: Maximum size of each chunk (default 500)
        
    Returns:
        List of text chunks
    """
    if not text:
        return []
    
    words = text.split()
    chunks = []
    current_chunk = []
    current_length = 0
    
    for word in words:
        word_length = len(word) + 1
        if current_length + word_length > chunk_size and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]
            current_length = word_length
        else:
            current_chunk.append(word)
            current_length += word_length
    
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return chunks
