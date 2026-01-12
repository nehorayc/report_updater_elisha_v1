from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
import config
import logging
import requests
from duckduckgo_search import DDGS
from urllib.parse import urlparse

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger(__name__)
if not logger.handlers:
    fh = logging.FileHandler("logs/researcher.log")
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

load_dotenv()

def search_web_ddg(topic, timeframe, max_results=8):
    """
    Searches DuckDuckGo for the latest news and information.
    """
    logger.info(f"Searching DuckDuckGo for: {topic} (since {timeframe})")
    findings = ""
    sources = []
    
    try:
        # DDG search query with timeframe context
        query = f"{topic} {timeframe}"
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            
            if not results:
                return "No web results found via DuckDuckGo.", []
            
            seen_domains = set()
            for i, r in enumerate(results):
                title = r.get('title', 'No Title')
                link = r.get('href', r.get('url', ''))
                snippet = r.get('body', r.get('snippet', ''))
                
                # Domain diversity check
                try:
                    domain = urlparse(link).netloc
                    if domain in seen_domains:
                        continue # Skip duplicate domains to ensure variety
                    seen_domains.add(domain)
                except:
                    pass
                
                if len(sources) >= 5: # Cap at 5 diverse sources
                    break

                findings += f"WEB SOURCE [{len(sources)+1}]: {title}\nURL: {link}\nCONTENT: {snippet}\n\n"
                sources.append({
                    "title": title,
                    "url": link
                })
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return f"Error during web search: {e}", []
        
    return findings, sources

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
                
            # AI Relevance Check (Low cost call)
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

def extract_keywords(topic, api_key):
    """
    Uses Gemini to extract 3-5 search-friendly keywords from a long topic description.
    """
    # If topic is already short, use it directly
    if len(topic.split()) < 10:
        return topic
        
    client = genai.Client(api_key=api_key)
    prompt = f"""
    Convert the following research topic into a concise search query (max 5-7 words) for a search engine. 
    Focus on the core subject matter and exclude filler words.
    
    Topic: "{topic}"
    
    Search Query:
    """
    
    try:
        response = client.models.generate_content(
            model=config.MODEL_RESEARCH,
            contents=prompt
        )
        query = response.text.replace('"', '').strip()
        logger.debug(f"Converted topic '{topic[:50]}...' to query '{query}'")
        return query
    except Exception as e:
        logger.warning(f"Keyword extraction failed: {e}")
        return topic[:100]


def perform_research(topic, timeframe, api_key, enabled_sources=None, search_query=None):
    """
    Performs research on a topic across multiple sources.
    Uses extracted keywords for better search results.
    """
    if enabled_sources is None:
        enabled_sources = ["Web Search"]
       
    # Optimizing query for search engines
    # Use provided query (from initial analysis) or fallback to extraction
    if not search_query:
        search_query = extract_keywords(topic, api_key)
        
    logger.info(f"Researching '{search_query}' (Original: {topic[:30]}...) via sources: {enabled_sources}")
    
    all_findings = ""
    all_sources = []
    
    # 1. Web Search (Direct, no AI call here)
    if "Web Search" in enabled_sources:
        web_findings, web_sources = search_web_ddg(search_query, timeframe)
        all_findings += f"WEB RESEARCH FINDINGS (Powered by DuckDuckGo):\n{web_findings}\n\n"
        all_sources.extend(web_sources)

    # 2. Academic Search (Independent API + 1 AI check per paper)
    if "Academic Papers" in enabled_sources:
        acad_findings, acad_sources = search_openalex(search_query, api_key)
        all_findings += f"ACADEMIC RESEARCH FINDINGS (Powered by OpenAlex):\n{acad_findings}\n\n"
        all_sources.extend(acad_sources)
    
    return all_findings, all_sources
