import streamlit as st
import os
from dotenv import load_dotenv
import processor
import researcher
import updater
import validator
import time
import config
import logging

# Configure main app logger
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

st.set_page_config(page_title="Report Updater AI", layout="wide")

# Custom CSS for a premium look
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
        color: #ffffff;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #2e7d32;
        color: white;
    }
    .chapter-card {
        padding: 20px;
        border-radius: 10px;
        background-color: #1e2227;
        margin-bottom: 10px;
        border: 1px solid #3e444b;
    }
    .stTextInput>div>div>input {
        background-color: #262730;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Session State Initialization
if 'step' not in st.session_state:
    st.session_state.step = "UPLOAD"
if 'api_key' not in st.session_state:
    st.session_state.api_key = os.getenv("GEMINI_API_KEY", "")
if 'chapters' not in st.session_state:
    st.session_state.chapters = []
if 'processed_results' not in st.session_state:
    st.session_state.processed_results = {}
if 'source_metadata' not in st.session_state:
    st.session_state.source_metadata = {}

def next_step(step):
    st.session_state.step = step

# Sidebar for API Configuration
with st.sidebar:
    st.title("Settings")
    api_key = st.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
    if api_key:
        st.session_state.api_key = api_key
    
    st.divider()
    st.subheader("Research Configuration")
    research_sources = st.multiselect(
        "Enabled Sources",
        options=["Web Search", "Academic Papers"],
        default=["Web Search"],
        help="Select which sources to use for deep research. Academic papers come from OpenAlex."
    )
    
    st.divider()
    if st.button("Reset Application"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# --------------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------------
def run_full_update():
    """Processes all chapters sequentially."""
    next_step("PROCESSING")
    st.rerun()

def regenerate_chapter(idx, instructions=None, sources_override=None):
    """Regenerates a single chapter."""
    chapter = st.session_state.chapters[idx]
    
    # Use selected sources from sidebar unless overridden
    sources = sources_override if sources_override else research_sources
    
    with st.spinner(f"Updating '{chapter['title']}'..."):
        research_findings, sources_meta = researcher.perform_research(
            chapter['topic'], 
            chapter['timeframe'], 
            st.session_state.api_key,
            enabled_sources=sources
        )
        time.sleep(config.API_DELAY) # Delay to avoid rate limits
        updated_text = updater.update_chapter(chapter['content'], research_findings, st.session_state.api_key, instructions=instructions)
        st.session_state.processed_results[idx] = updated_text
        st.session_state.source_metadata[idx] = sources_meta
    st.success(f"Regenerated {chapter['title']}")

# --------------------------------------------------------------------------------
# STATE 1: UPLOAD
# --------------------------------------------------------------------------------
if st.session_state.step == "UPLOAD":
    st.title("📄 Report Updater AI")
    st.subheader("Step 1: Upload your existing report")
    
    uploaded_file = st.file_uploader("Choose a text file (.txt, .md)", type=['txt', 'md'])
    
    if uploaded_file and st.session_state.api_key:
        if st.button("Analyze Report Structure"):
            try:
                text = uploaded_file.read().decode("utf-8")
                raw_chapters = processor.parse_report_into_chapters(text)
                
                with st.status("Analyzing chapters...", expanded=True) as status:
                    st.write("Extracting content and identifying timeframes for all chapters...")
                    
                    # Perform bulk analysis
                    all_analysis = processor.analyze_all_chapters(raw_chapters, st.session_state.api_key)
                    
                    analyzed_chapters = []
                    for i, ch in enumerate(raw_chapters):
                        # Match analysis by index (safety check)
                        analysis = all_analysis[i] if i < len(all_analysis) else {
                            "summary": "Analysis unavailable", "topic": ch['title'], "timeframe": "Unknown"
                        }
                        
                        analyzed_chapters.append({
                            "id": i,
                            "title": ch['title'],
                            "content": ch['content'],
                            "summary": analysis.get('summary', 'No summary'),
                            "topic": analysis.get('summary', ch['title']), # Default topic to summary
                            "timeframe": analysis.get('timeframe', config.DEFAULT_TIMEFRAME)
                        })
                    st.session_state.chapters = analyzed_chapters
                    status.update(label="Analysis complete!", state="complete", expanded=False)
                    logger.info("Report structure analysis finalized")
                
                next_step("REVIEW")
                st.rerun()
            except Exception as e:
                logger.error(f"Critical error in UPLOAD stage: {e}")
                logger.exception(e)
                st.error(f"An error occurred during analysis: {e}. Check logs/app.log for details.")
    elif not st.session_state.api_key:
        st.warning("Please enter your Gemini API Key in the sidebar to continue.")

# --------------------------------------------------------------------------------
# STATE 2: REVIEW
# --------------------------------------------------------------------------------
elif st.session_state.step == "REVIEW":
    st.title("🔎 Step 2: Review & Edit Chapters")
    st.write("Adjust the research topics or remove chapters you don't want to update.")
    
    for i, chapter in enumerate(st.session_state.chapters):
        with st.container():
            st.markdown(f'<div class="chapter-card">', unsafe_allow_html=True)
            col1, col2 = st.columns([4, 1])
            
            with col1:
                title = st.text_input(f"Chapter Title", value=chapter['title'], key=f"title_{i}")
                st.session_state.chapters[i]['title'] = title
                
                topic = st.text_area(f"Research Topic / Summary", value=chapter['topic'], key=f"topic_{i}", height=100)
                st.session_state.chapters[i]['topic'] = topic
                
                tf = st.text_input(f"Cut-off Timeframe", value=chapter['timeframe'], key=f"tf_{i}")
                st.session_state.chapters[i]['timeframe'] = tf
                
                st.caption(f"Original Summary: {chapter['summary']}")
            
            with col2:
                if st.button("🗑️ Remove", key=f"del_{i}"):
                    st.session_state.chapters.pop(i)
                    st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)

    if st.button("➕ Add New Chapter"):
        st.session_state.chapters.append({
            "id": len(st.session_state.chapters),
            "title": "New Chapter",
            "content": "(Empty - will be generated from scratch using research)",
            "summary": "Manual addition",
            "topic": "Describe the subject for deep research here...",
            "timeframe": config.DEFAULT_TIMEFRAME
        })
        st.rerun()

    st.divider()
    if st.button("🚀 Start Deep Research & Update"):
        next_step("PROCESSING")
        st.rerun()

# --------------------------------------------------------------------------------
# STATE 3: PROCESSING
# --------------------------------------------------------------------------------
elif st.session_state.step == "PROCESSING":
    st.title("⏳ Step 3: Deep Research & Writing")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(st.session_state.chapters)
    for i, chapter in enumerate(st.session_state.chapters):
        status_text.write(f"Currently researching and writing: **{chapter['title']}** ({i+1}/{total})")
        
        try:
            # Research
            findings, sources_meta = researcher.perform_research(
                chapter['topic'], 
                chapter['timeframe'], 
                st.session_state.api_key,
                enabled_sources=research_sources
            )
            time.sleep(config.API_DELAY) # Delay between research and writing
            
            # Update
            updated_text = updater.update_chapter(chapter['content'], findings, st.session_state.api_key)
            
            st.session_state.processed_results[i] = updated_text
            st.session_state.source_metadata[i] = sources_meta
            progress_bar.progress((i + 1) / total)
            
            if i < total - 1:
                time.sleep(config.API_DELAY) # Delay before starting next chapter
        except Exception as e:
            logger.error(f"Error processing {chapter['title']}: {e}")
            logger.exception(e)
            st.session_state.processed_results[i] = f"Error: {e}. View logs for details."
            st.error(f"Failed to process {chapter['title']}. Logging error and continuing...")
            
    next_step("RESULT")
    st.rerun()

# --------------------------------------------------------------------------------
# STATE 4: RESULT
# --------------------------------------------------------------------------------
elif st.session_state.step == "RESULT":
    st.title("✅ Step 4: Final Report & Refinement")
    
    full_report = ""
    for i, chapter in enumerate(st.session_state.chapters):
        with st.expander(f"📖 Chapter {i+1}: {chapter['title']}", expanded=(i==0)):
            content = st.session_state.processed_results.get(i, "No content generated.")
            
            # Editable content area
            edited_content = st.text_area(
                f"Content Editor - Chapter {i+1}",
                value=content,
                height=400,
                key=f"editor_{i}",
                help="You can manually edit the content here. Edits are saved automatically to the final report."
            )
            st.session_state.processed_results[i] = edited_content
            
            full_report += f"# {chapter['title']}\n\n{edited_content}\n\n---\n\n"
            
            st.divider()
            
            # Fine-tuning section
            st.markdown("### 🛠️ Refine & Regenerate")
            instr_col, btn_col = st.columns([3, 1])
            
            with instr_col:
                instructions = st.text_input(
                    "Fine-tuning Instructions",
                    placeholder="e.g., 'Make it more technical', 'Focus more on the 2024 trends', 'Remove the summary section'",
                    key=f"instr_{i}"
                )
            
            with btn_col:
                if st.button("🔄 Regenerate", key=f"regen_{i}"):
                    regenerate_chapter(i, instructions=instructions)
                    st.rerun()
            
            # Validation check
            val = validator.validate_citations(edited_content)
            if val.get("has_original_ref"):
                st.success("Correctly references Original Report [0]")
            else:
                st.warning("Missing reference to Original Report [0]")
            
            if val.get("orphans_in_text"):
                st.error(f"Orphan citations found: {val['orphans_in_text']}")

    # Aggregate global bibliography
    academic_sources = []
    web_sources = []
    seen_urls = set()
    
    for sources in st.session_state.source_metadata.values():
        for s in sources:
            if s['url'] not in seen_urls:
                if s['title'].startswith("[Academic]"):
                    academic_sources.append(s)
                else:
                    web_sources.append(s)
                seen_urls.add(s['url'])
    
    bibliography_md = ""
    
    # Academic Section
    if academic_sources:
        bibliography_md += "\n## Academic Bibliography\n\n"
        for idx, source in enumerate(academic_sources):
            title = source['title'].replace("[Academic] ", "")
            bibliography_md += f"{idx + 1}. **{title}**  \n   Link: {source['url']}\n\n"
            
    # Web Section
    if web_sources:
        bibliography_md += "\n## Web References\n\n"
        for idx, source in enumerate(web_sources):
            bibliography_md += f"{idx + 1}. [{source['title']}]({source['url']})\n"
            
    if not academic_sources and not web_sources:
        bibliography_md = "\n## Bibliography\n\nNo external sources identified.\n"
    
    full_report += bibliography_md
    
    st.divider()
    st.subheader("Verification & Bibliography")
    
    with st.expander("📚 View Full Bibliography", expanded=True):
        if academic_sources:
            st.markdown("### 🎓 Academic Papers")
            for s in academic_sources:
                st.markdown(f"- **{s['title'].replace('[Academic] ', '')}** ([Link]({s['url']}))")
        
        if web_sources:
            st.markdown("### 🌐 Web Sources")
            for s in web_sources:
                st.markdown(f"- [{s['title']}]({s['url']})")
        
        if not academic_sources and not web_sources:
            st.write("No sources identified.")
        
    valid_count, broken = validator.validate_links(full_report)
    st.write(f"✅ {valid_count} Sources verified.")
    if broken:
        st.error(f"❌ {len(broken)} Broken links detected: {broken}")

    st.download_button(
        label="📥 Download Full Updated Report",
        data=full_report,
        file_name="updated_report.md",
        mime="text/markdown"
    )
    
    if st.button("Return to Review"):
        next_step("REVIEW")
        st.rerun()
