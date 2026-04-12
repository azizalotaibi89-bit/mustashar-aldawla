"""
PDF Text Processor for مستشار الدولة
Extracts and chunks legal text from the Kuwaiti legislation PDF
"""
import fitz  # PyMuPDF
import json
import re
import os

def extract_and_chunk(pdf_path, output_dir="data"):
    """Extract text from PDF and create searchable chunks."""
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)

    print(f"📄 Processing PDF: {doc.page_count} pages")

    # Extract all pages
    pages = []
    for i in range(doc.page_count):
        text = doc[i].get_text("text").strip()
        if text:
            pages.append({"page": i + 1, "text": text})

    # Create chunks - split by articles (مادة) and sections
    chunks = []
    current_chunk = ""
    current_meta = {"start_page": 1, "section": ""}

    for page_data in pages:
        text = page_data["text"]
        page_num = page_data["page"]

        # Detect section headers
        section_patterns = [
            r'(الباب\s+\w+[:\s].+)',
            r'(الفصل\s+\w+[:\s].+)',
            r'(الفرع\s+\w+[:\s].+)',
            r'(قانون\s+.+)',
        ]

        for pattern in section_patterns:
            match = re.search(pattern, text)
            if match:
                current_meta["section"] = match.group(1).strip()[:100]
                break

        # Split by articles
        parts = re.split(r'((?:مادة|المادة)\s*\d+)', text)

        for part in parts:
            if not part.strip():
                continue

            # If this is an article header, save current chunk and start new one
            if re.match(r'(?:مادة|المادة)\s*\d+', part.strip()):
                if current_chunk.strip() and len(current_chunk.strip()) > 50:
                    chunks.append({
                        "id": len(chunks),
                        "text": current_chunk.strip(),
                        "page": current_meta["start_page"],
                        "section": current_meta["section"]
                    })
                current_chunk = part
                current_meta["start_page"] = page_num
            else:
                current_chunk += " " + part

                # If chunk gets too large, split it
                if len(current_chunk) > 3000:
                    chunks.append({
                        "id": len(chunks),
                        "text": current_chunk.strip(),
                        "page": current_meta["start_page"],
                        "section": current_meta["section"]
                    })
                    current_chunk = ""
                    current_meta["start_page"] = page_num

    # Don't forget the last chunk
    if current_chunk.strip() and len(current_chunk.strip()) > 50:
        chunks.append({
            "id": len(chunks),
            "text": current_chunk.strip(),
            "page": current_meta["start_page"],
            "section": current_meta["section"]
        })

    # Save chunks
    output_path = os.path.join(output_dir, "chunks.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"✅ Created {len(chunks)} searchable chunks")
    print(f"💾 Saved to {output_path}")

    return chunks

if __name__ == "__main__":
    import sys
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "data/laws.pdf"
    extract_and_chunk(pdf_path)
