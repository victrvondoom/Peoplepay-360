import re

def semantic_chunking(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """Semantic chunking that respects headings, clauses, and numbering.
    Chunk size: 700-900 tokens (approximated by character length or simple split).
    Overlap: 100-150 tokens.
    """
    if not text.strip():
        return []
        
    # Split text by major semantic boundaries (headings, clause numbers)
    # E.g., "1.", "1.1", "Article I", "Section 1", "\n\n#"
    pattern = r"(?:\n\n#+\s+|\n\n(?:Article|Section)\s+[A-Z0-9]+|\n\n\d+\.\d*\s+)"
    sections = re.split(f"({pattern})", text)
    
    # Recombine split sections with their delimiters
    semantic_blocks = []
    current_block = sections[0].strip()
    if current_block:
        semantic_blocks.append(current_block)
        
    for i in range(1, len(sections), 2):
        delimiter = sections[i]
        content = sections[i+1] if i + 1 < len(sections) else ""
        semantic_blocks.append((delimiter + content).strip())
        
    # Now chunk the semantic blocks to fit the chunk_size
    chunks = []
    current_chunk = ""
    
    # Using roughly 4 chars per token as an approximation
    char_chunk_size = chunk_size * 4
    char_overlap = overlap * 4
    
    for block in semantic_blocks:
        if not block:
            continue
            
        if len(current_chunk) + len(block) <= char_chunk_size:
            current_chunk = f"{current_chunk}\n\n{block}".strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
            
            # If a single block is larger than chunk size, we need to split it
            if len(block) > char_chunk_size:
                start = 0
                while start < len(block):
                    end = min(len(block), start + char_chunk_size)
                    # Try to find a sentence break to not cut in the middle of a word
                    if end < len(block):
                        # Look back for a period or newline
                        break_point = max(
                            block.rfind(". ", start, end),
                            block.rfind("\n", start, end)
                        )
                        if break_point != -1 and break_point > start + (char_chunk_size // 2):
                            end = break_point + 1
                    
                    chunks.append(block[start:end].strip())
                    if end >= len(block):
                        break
                    start = max(start + 1, end - char_overlap)
                current_chunk = ""
            else:
                current_chunk = block
                
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks
