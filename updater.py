from google import genai
import re
import os
import config
from loguru import logger

os.makedirs("logs", exist_ok=True)
logger.add("logs/updater.log", rotation="10 MB", level="DEBUG")

def update_chapter(original_content, research_findings, api_key, instructions=None):
    """
    Rewrites a chapter using research findings and referencing the original document as [0].
    Also accepts optional user instructions for fine-tuning.
    """
    logger.info("Updating chapter content with research findings")
    client = genai.Client(api_key=api_key)
    
    instruction_fragment = f"\nUSER INSTRUCTIONS / FINE-TUNING:\n{instructions}\n" if instructions else ""
    
    prompt = f"""
    You are a professional report writer. Your task is to update a specific chapter of a report.
    
    SOURCES:
    [0] Original Report Content (Provided below)
    Research Findings (Provided below, contains various web sources)
    
    INSTRUCTIONS:
    1. Write a new, comprehensive version of this chapter that incorporates both the original context and the new research findings.
    2. You MUST cite the original report as [0] whenever you use information from it.
    3. You MUST cite the research findings using numerical indices (e.g., [1], [2], etc.) based on the sources provided in the research text.
    4. The updated chapter should logically transition from the old information to the new information.
    5. Ensure the tone is consistent and professional.
    6. Include a "Sources for this chapter" section at the end of the text.
    {instruction_fragment}
    
    ORIGINAL CONTENT [0]:
    {original_content}
    
    RESEARCH FINDINGS:
    {research_findings}
    
    Updated Chapter Content:
    """
    
    try:
        logger.debug(f"Sending writing prompt to {config.MODEL_WRITER}")
        response = client.models.generate_content(
            model=config.MODEL_WRITER,
            contents=prompt
        )
        logger.info("Chapter update successful")
        return response.text
    except Exception as e:
        logger.error(f"Failed to update chapter: {e}")
        logger.exception(e)
        return f"Error during chapter update: {e}"

def extract_sources_and_bibliography(text):
    """
    Extracts citations from the text and organizes them into a bibliography.
    """
    # This is a bit complex as the model might format sources differently.
    # We will look for anything that looks like a URL.
    urls = list(set(re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)))
    
    bibliography = ["[0] Original Document"]
    for i, url in enumerate(urls):
        bibliography.append(f"[{i+1}] {url}")
        
    return bibliography
