from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
import config
from loguru import logger

os.makedirs("logs", exist_ok=True)
logger.add("logs/researcher.log", rotation="10 MB", level="DEBUG")

load_dotenv()

import requests

def search_openalex(topic, api_key, max_results=10):
    """
    Searches OpenAlex for academic papers and uses Gemini to filter for relevance.
    """
    logger.info(f"Searching OpenAlex for: {topic}")
    
    # OpenAlex API Endpoint
    url = f"https://api.openalex.org/works?search={topic}&per_page={max_results}"
    if config.OPENALEX_EMAIL:
        url += f"&mailto={config.OPENALEX_EMAIL}"
    
    findings = ""
    sources = []
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        results = data.get("results", [])
        
        if not results:
            return "No academic papers found.", []
            
        client = genai.Client(api_key=api_key)
        relevant_count = 0
        
        for res in results:
            if relevant_count >= config.OPENALEX_MAX_RESULTS:
                break
                
            title = res.get("display_name", "Untitled")
            abstract_dict = res.get("abstract_inverted_index")
            
            # OpenAlex returns abstract in an inverted index format
            abstract = ""
            if abstract_dict:
                # Reconstruct abstract
                word_index = {}
                for word, indices in abstract_dict.items():
                    for idx in indices:
                        word_index[idx] = word
                abstract = " ".join([word_index[i] for i in sorted(word_index.keys())])
            
            if not abstract:
                continue
                
            # AI Relevance Check
            prompt = f"""
            Is the following academic paper abstract relevant to the topic: '{topic}'?
            Answer ONLY with 'YES' or 'NO'.
            
            ABSTRACT:
            {abstract[:2000]}
            """
            
            check = client.models.generate_content(
                model=config.MODEL_RESEARCH,
                contents=prompt
            )
            
            if "YES" in check.text.upper():
                year = res.get("publication_year", "N/A")
                doi = res.get("doi") or f"https://openalex.org/{res.get('id').split('/')[-1]}"
                
                findings += f"ACADEMIC PAPER ({year}): {title}\nSUMMARY: {abstract[:1000]}...\n\n"
                sources.append({
                    "title": f"[Academic] {title}",
                    "url": doi
                })
                relevant_count += 1
                
    except Exception as e:
        logger.error(f"OpenAlex search failed: {e}")
        findings = f"Error during academic search: {e}"
        
    return findings, sources

def perform_research(topic, timeframe, api_key, enabled_sources=None):
    """
    Performs research on a topic across multiple sources.
    enabled_sources: list of strings like ["Web Search", "Academic Papers"]
    """
    if enabled_sources is None:
        enabled_sources = ["Web Search"]
        
    logger.info(f"Researching '{topic}' via sources: {enabled_sources}")
    client = genai.Client(api_key=api_key)
    
    all_findings = ""
    all_sources = []
    
    # 1. Web Search
    if "Web Search" in enabled_sources:
        prompt = f"""
        Research the following topic: {topic}
        Focus on events, data, and changes that occurred from {timeframe} until today (Late 2025).
        Crucially, you MUST include specific URLs as sources for your information.
        """
        try:
            response = client.models.generate_content(
                model=config.MODEL_RESEARCH,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    response_modalities=["TEXT"]
                )
            )
            all_findings += f"WEB RESEARCH FINDINGS:\n{response.text}\n\n"
            
            # Extract web sources
            if response and hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                    metadata = candidate.grounding_metadata
                    if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                        for chunk in metadata.grounding_chunks:
                            if hasattr(chunk, 'web') and chunk.web:
                                all_sources.append({
                                    "title": chunk.web.title,
                                    "url": chunk.web.uri
                                })
        except Exception as e:
            logger.error(f"Web research failed: {e}")
            all_findings += f"Error during web research: {e}\n\n"

    # 2. Academic Search
    if "Academic Papers" in enabled_sources:
        acad_findings, acad_sources = search_openalex(topic, api_key)
        all_findings += f"ACADEMIC RESEARCH FINDINGS:\n{acad_findings}\n\n"
        all_sources.extend(acad_sources)
    
    return all_findings, all_sources
