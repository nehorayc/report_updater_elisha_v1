from google import genai
import os
import re
from dotenv import load_dotenv
import logging

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger(__name__)
if not logger.handlers:
    fh = logging.FileHandler("logs/processor.log")
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

load_dotenv()

def parse_report_into_chapters(text):
    """
    Splits the report into chapters based on headers or double newlines.
    Returns a list of dictionaries: [{'title': str, 'content': str}]
    """
    # Try a simple regex first for headers
    chapters = []
    
    # Common header patterns: # Header, Chapter 1, Section 1
    lines = text.split('\n')
    current_chapter = {"title": "Introduction", "content": ""}
    
    header_pattern = re.compile(r'^(#+\s+|Chapter\s+\d+|Section\s+\d+|[A-Z][^a-z]+$)', re.IGNORECASE)
    
    for line in lines:
        if header_pattern.match(line.strip()) and len(line.strip()) < 100:
            if current_chapter["content"].strip():
                chapters.append(current_chapter)
            current_chapter = {"title": line.strip().lstrip('#').strip(), "content": ""}
        else:
            current_chapter["content"] += line + "\n"
            
    if current_chapter["content"].strip() or current_chapter["title"] != "Introduction":
        chapters.append(current_chapter)
        
    # If we only got one chapter and it's huge, maybe it failed to parse.
    # In a real app we might use an LLM to identify boundaries better.
    return chapters

import json
import config

def analyze_all_chapters(chapters, api_key):
    """
    Uses Gemini to analyze all chapters in a single prompt with strict schema.
    """
    logger.info(f"Starting batch analysis for {len(chapters)} chapters")
    client = genai.Client(api_key=api_key)
    
    # Prepare the input for the model
    chapters_preview = []
    for i, ch in enumerate(chapters):
        chapters_preview.append({
            "index": i,
            "title": ch['title'],
            "content_preview": ch['content'][:config.MAX_PREVIEW_LENGTH] 
        })
    
    # Define the schema for a single chapter analysis
    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "summary": {"type": "STRING", "description": "3-4 sentence summary of the chapter"},
                "topic": {"type": "STRING", "description": "Main subject for deep research"},
                "timeframe": {"type": "STRING", "description": "Latest timeframe or date mentioned"},
                "search_query": {"type": "STRING", "description": "Concise search keywords (max 5-7 words) for DuckDuckGo/OpenAlex"},
                "writing_style": {"type": "STRING", "description": "The writing style/tone (e.g., Formal, Academic, Casual)"},
                "language": {"type": "STRING", "description": "The language of the chapter (e.g., English, Hebrew, Spanish)"}
            },
            "required": ["summary", "topic", "timeframe", "search_query", "writing_style", "language"]
        }
    }
    
    prompt = f"""
    Analyze the following report chapters. For each chapter:
    1. Provide a short summary.
    2. Identify the main subject for deep research.
    3. Identify the latest date or timeframe mentioned.
    4. Generate concise search keywords (max 5-7 words) that would best find external information on this topic.
    5. Identify the writing style/tone.
    6. Identify the language.
    
    Chapters Data:
    {json.dumps(chapters_preview)}
    """
    
    try:
        logger.debug(f"Sending batch analysis prompt to {config.MODEL_ANALYSIS}")
        response = client.models.generate_content(
            model=config.MODEL_ANALYSIS,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema
            }
        )
        results = json.loads(response.text)
        logger.info("Batch analysis successful")
        return results
    except Exception as e:
        logger.error(f"Error in batch analysis: {e}")
        logger.exception(e)
        return [{"summary": "Analysis failed.", "topic": ch['title'], "timeframe": config.DEFAULT_TIMEFRAME} for ch in chapters]

def get_chapter_summary(chapter_content, api_key):
    """
    Uses Gemini to summarize the chapter with a strict schema.
    """
    client = genai.Client(api_key=api_key)
    
    schema = {
        "type": "OBJECT",
        "properties": {
            "summary": {"type": "STRING"},
            "topic": {"type": "STRING"},
            "timeframe": {"type": "STRING"}
        },
        "required": ["summary", "topic", "timeframe"]
    }
    
    prompt = f"""
    Analyze the following report chapter. 
    1. Provide a short summary.
    2. Identify the main topic.
    3. Identify the latest date or timeframe.
    
    Chapter Content:
    {chapter_content[:4000]} 
    """
    
    try:
        response = client.models.generate_content(
            model=config.MODEL_ANALYSIS,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema
            }
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Manual summary failed: {e}")
        return {
            "summary": "No summary available.",
            "topic": "Unknown topic",
            "timeframe": config.DEFAULT_TIMEFRAME
        }
