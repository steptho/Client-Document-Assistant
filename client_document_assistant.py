# Client Document Assistant

import os
import tempfile
import base64
import json
import streamlit as st
import pandas as pd
from fpdf import FPDF
from pypdf import PdfReader
from docx import Document
from pptx import Presentation
from openai import OpenAI

# ---------------------------------------------------
# CONFIGURATION & PERSISTENCE
# ---------------------------------------------------
st.set_page_config(page_title="Document Data Assistant", layout="wide")
HISTORY_FILE = "analysis_history.json"

def load_history():
    """Loads history from a local JSON file."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_to_history(new_item):
    """Saves a new analysis record to the local JSON file."""
    history = load_history()
    history.append(new_item)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)

# ---------------------------------------------------
# SESSION STATE INITIALIZATION
# ---------------------------------------------------
if "state" not in st.session_state:
    st.session_state.state = {
        "logged_in": False,
        "analysis_result": "",
        "analysis_history": load_history(),
        "preview_text": ""
    }

# ---------------------------------------------------
# OPENAI CLIENT
# ---------------------------------------------------
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except:
    st.error("Please set your OPENAI_API_KEY in Streamlit Secrets.")

# ---------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------

def extract_text(uploaded_file):
    """Reads content from various file types including AI Vision for images."""
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    text = ""
    try:
        uploaded_file.seek(0)
        
        if ext == ".pdf":
            reader = PdfReader(uploaded_file)
            text = "\n".join([p.extract_text() or "" for p in reader.pages])
        elif ext == ".docx":
            doc = Document(uploaded_file)
            text = "\n".join([p.text for p in doc.paragraphs])
        elif ext == ".pptx":
            prs = Presentation(uploaded_file)
            text = "\n".join(shape.text for slide in prs.slides for shape in slide.shapes if hasattr(shape, "text"))
        elif ext in [".xlsx", ".xls"]:
            df = pd.read_excel(uploaded_file)
            text = f"Spreadsheet Data ({uploaded_file.name}):\n{df.to_string()}"
        elif ext in [".jpg", ".jpeg", ".png"]:
            file_bytes = uploaded_file.read()
            base64_image = base64.b64encode(file_bytes).decode("utf-8")
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a professional analyst. Describe the scene or extract text precisely."},
                    {"role": "user", "content": [
                                    {"type": "text", "text": "Describe this image in detail or transcribe its content."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"}}
                    ]}
                ]
            )
            text = response.choices[0].message.content
    except Exception as e:
        st.error(f"Error reading file: {e}")
    return text

def generate_pdf(text):
    """Generates a downloadable PDF with fixed width margins."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    
    clean_text = text.replace('’', "'").replace('“', '"').replace('”', '"').replace('—', '-')
    clean_text = clean_text.encode('latin-1', 'ignore').decode('latin-1')
    
    pdf.multi_cell(190, 10, clean_text, align='L')
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        return tmp.name

def handle_login():
    if st.session_state.get("temp_user_input", "").strip():
        st.session_state.state["logged_in"] = True

def clear_old_file_state():
    st.session_state.state["preview_text"] = ""
    st.session_state.state["analysis_result"] = ""

# ---------------------------------------------------
# MAIN UI LOGIC
# ---------------------------------------------------

if not st.session_state.state["logged_in"]:
    st.title("🔐 Secure Login")
    st.text_input("Enter Company Name", key="temp_user_input", on_change=handle_login)
    if st.button("Enter"):
        handle_login()
        st.rerun()

else:
    # --- Sidebar ---
    with st.sidebar:
        st.header("🏢 Session")
        if st.button("Logout"):
            st.session_state.state = {"logged_in": False, "analysis_result": "", "analysis_history": load_history(), "preview_text": ""}
            st.rerun()
        
        st.divider()
        st.subheader("📜 History Management")
        
        # Search Feature
        search_query = st.text_input("🔍 Search History", "").lower()
        
        history_list = st.session_state.state["analysis_history"]
        
        if history_list:
            # 1. Summarize All Button
            if st.button("🤖 Summarize All History"):
                with st.spinner("Analyzing your entire history..."):
                    all_text = "\n\n".join([f"Document: {h['title']}\nContent: {h['analysis']}" for h in history_list])
                    sum_res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{
                            "role": "user", 
                            "content": (
                                "Act as a personal executive assistant. Look through all these records and provide:"
                                "\n1. A categorized list (e.g., Financial, Events/Photos, Business)."
                                "\n2. A chronological timeline of when these events happened if dates are mentioned."
                                "\n3. A 'Bottom Line' summary of total spending or key highlights."
                                f"\n\nRecords:\n{all_text}"
        )
    }]
)
                    st.session_state.state["analysis_result"] = f"### 📊 GLOBAL HISTORY SUMMARY\n\n{sum_res.choices[0].message.content}"
                    st.rerun()

            st.divider()
            
            # 2. Filtered List
            filtered_history = [
                item for item in history_list 
                if search_query in item['title'].lower() or search_query in item['analysis'].lower()
            ]
            
            for idx, item in enumerate(filtered_history):
                if st.button(f"📄 {item['title']}", key=f"hist_{idx}"):
                    st.session_state.state["analysis_result"] = item["analysis"]
                    st.session_state.state["preview_text"] = ""
                    st.rerun()
            
            if not filtered_history:
                st.info("No matches found.")
            
            # 3. Clear History (Danger Zone)
            st.divider()
            st.warning("Danger Zone")
            confirm_clear = st.checkbox("Confirm Delete All")
            if st.button("🗑️ Clear All History", disabled=not confirm_clear):
                if os.path.exists(HISTORY_FILE):
                    os.remove(HISTORY_FILE)
                st.session_state.state["analysis_history"] = []
                st.session_state.state["analysis_result"] = ""
                st.success("History wiped!")
                st.rerun()
        else:
            st.info("No history yet.")

    # --- Main Panel ---
    st.title("📂 Document Data Assistant")

    uploaded_file = st.file_uploader(
        "Upload PDF, DOCX, PPTX, XLSX, or Images", 
        type=["pdf", "docx", "pptx", "xlsx", "jpg", "jpeg", "png"],
        on_change=clear_old_file_state
    )

    if uploaded_file:
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        is_image = file_ext in [".jpg", ".jpeg", ".png"]

        if not st.session_state.state["preview_text"]:
            with st.spinner("🔍 AI is reading the file..."):
                st.session_state.state["preview_text"] = extract_text(uploaded_file)

        st.subheader("📄 Document Preview")
        if is_image:
            st.image(uploaded_file, width=500)
            with st.expander("See AI-Extracted Raw Data"):
                st.write(st.session_state.state["preview_text"])
        else:
            st.text_area("Content", st.session_state.state["preview_text"], height=200)

        if st.button("🚀 Run Full Analysis"):
            raw_content = st.session_state.state["preview_text"]
            with st.spinner("📊 Finalizing report..."):
                t_res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": f"4-word title for: {raw_content[:500]}"}]
                )
                title = t_res.choices[0].message.content.strip().replace('"', '')

                if is_image:
                    analysis = raw_content
                else:
                    a_res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": f"Summarize key insights:\n{raw_content}"}]
                    )
                    analysis = a_res.choices[0].message.content

                save_to_history({"title": title, "analysis": analysis})
                st.session_state.state["analysis_history"] = load_history()
                st.session_state.state["analysis_result"] = analysis
                st.rerun()

    # Results Display
    if st.session_state.state["analysis_result"]:
        st.divider()
        st.subheader("💡 Analysis Findings")
        st.markdown(st.session_state.state["analysis_result"])

        pdf_path = generate_pdf(st.session_state.state["analysis_result"])
        with open(pdf_path, "rb") as f:
            st.download_button(label="📥 Download PDF", data=f, file_name="Analysis_Report.pdf", mime="application/pdf")


