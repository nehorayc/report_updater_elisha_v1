import requests
import re

def validate_links(text):
    """
    Finds all URLs and checks if they return a 200 OK status.
    Returns (valid_count, broken_links)
    """
    urls = list(set(re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)))
    broken_links = []
    valid_count = 0
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for url in urls:
        try:
            # Using get instead of head since some servers block head, but with stream=True to avoid downloading body
            response = requests.get(url, headers=headers, timeout=5, stream=True)
            if response.status_code < 400:
                valid_count += 1
            else:
                broken_links.append((url, response.status_code))
        except Exception as e:
            broken_links.append((url, str(e)))
            
    return valid_count, broken_links

def validate_citations(text):
    """
    Checks if there are 'orphan' citations (cited in text but not in bibliography, or vice versa).
    Assumes a 'Sources' or 'Bibliography' section exists.
    """
    # Find all [x] patterns
    in_text_citations = set(re.findall(r'\[(\d+)\]', text))
    
    # Simple split to find the bibliography section
    parts = re.split(r'Sources|Bibliography|References', text, flags=re.IGNORECASE)
    if len(parts) < 2:
        return {"error": "No bibliography section found"}
        
    bib_text = parts[-1]
    in_bib_citations = set(re.findall(r'\[(\d+)\]', bib_text))
    
    orphans_in_text = in_text_citations - in_bib_citations
    orphans_in_bib = in_bib_citations - in_text_citations
    
    return {
        "text_citations": list(in_text_citations),
        "bib_citations": list(in_bib_citations),
        "orphans_in_text": list(orphans_in_text),
        "orphans_in_bib": list(orphans_in_bib),
        "has_original_ref": "0" in in_text_citations
    }
