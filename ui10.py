import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import csv
import openai
from functools import lru_cache
import json
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# API Keys
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Configure OpenAI API
openai.api_key = OPENAI_API_KEY

# List of known multi-supplier marketplaces
MULTI_SUPPLIER_SITES = [
    "alibaba.com",
    "thomasnet.com",
    "indiamart.com",
    "made-in-china.com",
    "globalsources.com"
]

def extract_info(url, retries=3):
    """Extract text from a webpage with retries and error handling."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                return soup.get_text()
            elif response.status_code in [403, 429]:
                st.warning(f"Access denied for {url}. Retrying... ({attempt+1}/{retries})")
                time.sleep(5)
            else:
                st.error(f"Failed with status code {response.status_code} for {url}")
                return None
        except requests.exceptions.RequestException as e:
            st.warning(f"Error: {e}. Retrying in 3 seconds...")
            time.sleep(3)
    st.error(f"Failed to retrieve {url} after {retries} attempts.")
    return None

def chat_with_openai(user_input, context=""):
    """Send a message to OpenAI API with context and get a response."""
    try:
        messages = [
            {"role": "system", "content": "You are a helpful assistant analyzing supplier website content."},
            {"role": "user", "content": f"Context: {context}\n\nQuestion: {user_input}"}
        ]
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        st.error(f"OpenAI API error: {e}")
        return f"Error processing with OpenAI API: {str(e)}"

def rank_suppliers(text):
    """Query OpenAI to rank suppliers based on features and return structured numerical data out of 5."""
    query = (
        "Based on the following supplier information, rank them numerically from best to worst considering "
        "product quality, certifications, customer reviews (if available), price competitiveness, and manufacturing "
        "capabilities. Provide structured JSON output ONLY with supplier names and their respective ranking scores "
        "out of 5 for each category. Ensure that there are no null values—remove any missing values completely "
        "from the JSON output. Ensure that the response is strictly valid JSON with no additional text.\n\n"
        + text[:5000]
    )
    response = chat_with_openai(query)
    
    try:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            ranking_data = json.loads(json_match.group(0))
            cleaned_data = {}
            for supplier, scores in ranking_data.items():
                if isinstance(scores, dict):
                    cleaned_scores = {k: v for k, v in scores.items() if isinstance(v, (int, float))}
                    cleaned_scores = {k: min(5, v / 2) if v > 5 else v for k, v in cleaned_scores.items()}
                    cleaned_scores["total"] = sum(cleaned_scores.values()) / len(cleaned_scores)
                    cleaned_data[supplier] = cleaned_scores
            return cleaned_data
        else:
            st.error("No valid JSON found in ranking response.")
            return None
    except json.JSONDecodeError:
        st.error("Unable to parse JSON response from OpenAI for ranking.")
        return None

def format_deep_scrape_result(result):
    """Format the OpenAI response into a structured, detailed output."""
    if "Error" in result:
        return result
    
    lines = result.split('\n')
    formatted_output = []
    sections = {
        "Phone Number": "Phone Numbers",
        "Email": "Emails",
        "Supplier Details": "Supplier Details",
        "Location": "Location",  # Added new section for location
        "Product Pricing": "Product Pricing",
        "ISO Certifications": "ISO Certifications",
        "Manufacturing Process Summary": "Manufacturing Process Summary"
    }
    
    supplier_lines = [line for line in lines if "supplier details" in line.lower()]
    multiple_suppliers = len(supplier_lines) > 1
    
    if multiple_suppliers:
        formatted_output.append("*⚠️ Multiple Suppliers Detected on this Website*")
    
    current_section = None
    supplier_index = 0
    supplier_data = {}
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        for key, display_name in sections.items():
            if key.lower() in line.lower():
                current_section = display_name
                if "Supplier Details" in display_name and multiple_suppliers:
                    supplier_index += 1
                    supplier_data[supplier_index] = [f"*Supplier {supplier_index} Details*: {line.split(':', 1)[1].strip() if ':' in line else line[len(key):].strip()}"]
                else:
                    formatted_output.append(f"- *{display_name}*: {line.split(':', 1)[1].strip() if ':' in line else line[len(key):].strip()}")
                break
        else:
            if current_section and line:
                if multiple_suppliers and current_section == "Supplier Details":
                    supplier_data[supplier_index].append(f"  - {line}")
                else:
                    formatted_output[-1] += f" {line}"
    
    if multiple_suppliers:
        for idx, details in supplier_data.items():
            formatted_output.extend(details)
    
    for display_name in sections.values():
        if not any(display_name in item for item in formatted_output):
            if display_name == "ISO Certifications":
                formatted_output.append(f"- *{display_name}*: No ISO certifications mentioned.")
            elif display_name == "Manufacturing Process Summary":
                formatted_output.append(f"- *{display_name}*: PLEASE CONTACT THE SUPPLIER FOR DETAILS")
            elif display_name == "Location":
                formatted_output.append(f"- *{display_name}*: Not specified in the text.")
            else:
                formatted_output.append(f"- *{display_name}*: Not found in the text.")
    
    return "\n".join(formatted_output) if formatted_output else "No structured data extracted."

@lru_cache(maxsize=128)
def scrape_deeper(url):
    """Scrape deeper details using OpenAI API and return both formatted result and summarized text."""
    data_values = extract_info(url)
    if data_values:
        truncated_text = data_values[:5000]
        user_input = (
            f"Extract and analyze details from this text: {truncated_text}. "
            f"If multiple suppliers are mentioned, list each supplier separately with their details. "
            f"Provide the output in a structured format with the following sections:\n"
            f"- *Phone Number*: List any phone numbers found.\n"
            f"- *Email*: List any email addresses found.\n"
            f"- *Supplier Details*: Include company name, address, or contact person if mentioned; if multiple suppliers, list each separately.\n"
            f"- *Location*: Specify the specific location of the supplier if available; if not, state 'Not specified in the text.'\n"
            f"- *Product Pricing*: List prices of products mentioned.\n"
            f"- *ISO Certifications*: Specify any ISO certifications if present; if none, state 'No ISO certifications mentioned.'\n"
            f"- *Manufacturing Process Summary*: Summarize specific manufacturing process details if available; if not, state 'PLEASE CONTACT THE SUPPLIER FOR DETAILS'."
        )
        result = chat_with_openai(user_input, context=truncated_text)
        formatted_result = format_deep_scrape_result(result)
        summary_prompt = f"Summarize the following text in 200 words or less: {truncated_text}"
        summary = chat_with_openai(summary_prompt, context=truncated_text)
        return formatted_result, summary
    return "No data extracted. The website may be blocking requests.", None

def extract_company_name_from_url(url):
    """Extract company name from URL and append '(Multiple Suppliers Found)' if applicable."""
    url = re.sub(r'^https?://', '', url)
    url = re.sub(r'^www\.', '', url)
    domain = re.split(r'[./]', url)[0]
    for site in MULTI_SUPPLIER_SITES:
        if site in url.lower():
            return f"{domain} (Multiple Suppliers Found)"
    return domain

def scrape_suppliers(industry, category, location, num_results=5, output_file="suppliers.csv"):
    """Search Google via SerpAPI for suppliers and extract basic details."""
    search_query = f"{industry} {category} suppliers in {location}"
    params = {
        "engine": "google",
        "q": search_query,
        "num": num_results,
        "api_key": SERPAPI_KEY
    }

    try:
        response = requests.get("https://serpapi.com/search", params=params)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        st.error(f"Error fetching search results: {e}")
        return []

    if "organic_results" not in data:
        st.warning(f"No results found for {category} in {location}")
        return []

    supplier_links = [result["link"] for result in data["organic_results"][:num_results]]
    supplier_data = []
    
    for link in supplier_links:
        try:
            supplier_name = extract_company_name_from_url(link)
            supplier_response = requests.get(link, timeout=10)
            soup = BeautifulSoup(supplier_response.text, "html.parser")
            text_content = soup.get_text()
            emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text_content)
            phones = re.findall(r"\+?\d[\d -]{8,}\d", text_content)

            supplier_data.append({
                "category": category,
                "name": supplier_name,
                "website": link,
                "email": emails[0] if emails else "[content protected]",
                "phone": phones[0] if phones else "[content protected]",
                "ranking": "Not Ranked"
            })
            time.sleep(2)
        except Exception as e:
            st.warning(f"Error scraping {link}: {e}")

    try:
        with open(output_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=["category", "name", "website", "email", "phone", "ranking"])
            if file.tell() == 0:
                writer.writeheader()
            writer.writerows(supplier_data)
    except Exception as e:
        st.error(f"Error saving to CSV: {e}")

    return supplier_data

# Streamlit UI
st.set_page_config(page_title="AI Supplier Scraper", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS for better styling and font consistency
st.markdown("""
    <style>
    .supplier-table {
        border: 1px solid #e6e6e6;
        border-radius: 5px;
        padding: 10px;
        background-color: #f9f9f9;
        font-family: Arial, sans-serif;
    }
    .supplier-row {
        border-bottom: 1px solid #e6e6e6;
        padding: 10px 0;
    }
    .deep-result {
        background-color: #f0f8ff;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 10px;
        font-family: Arial, sans-serif;
    }
    .chat-container {
        background-color: #f9f9f9;
        padding: 10px;
        border-radius: 5px;
        margin-top: 10px;
        font-family: Arial, sans-serif;
    }
    .chat-message {
        padding: 5px;
        margin: 5px 0;
        border-radius: 3px;
    }
    .user-message {
        background-color: #d1e7dd;
        text-align: right;
    }
    .bot-message {
        background-color: #e2e3e5;
        text-align: left;
    }
    .ranking-display {
        color: #ff9500;
        font-weight: bold;
    }
    .link-button {
        display: inline-block;
        padding: 5px 10px;
        background-color: #f0f0f0;
        border: 1px solid #ccc;
        border-radius: 4px;
        text-decoration: none;  /* Removes underline */
        color: #333;
        font-size: 20px;
        cursor: pointer;
        text-align: center;
    }
    .link-button:hover {
        background-color: #e0e0e0;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if "industry" not in st.session_state:
    st.session_state["industry"] = ""
if "category" not in st.session_state:
    st.session_state["category"] = ""
if "location" not in st.session_state:
    st.session_state["location"] = ""
if "num_results" not in st.session_state:
    st.session_state["num_results"] = 5
if "suppliers" not in st.session_state:
    st.session_state["suppliers"] = []
if "deep_scrape_results" not in st.session_state:
    st.session_state["deep_scrape_results"] = {}
if "deep_scrape_raw_text" not in st.session_state:
    st.session_state["deep_scrape_raw_text"] = {}
if "chat_histories" not in st.session_state:
    st.session_state["chat_histories"] = {}
if "chat_active" not in st.session_state:
    st.session_state["chat_active"] = {}
if "ranking_results" not in st.session_state:
    st.session_state["ranking_results"] = {}

# Title and description
st.title("🔍AI Supplier Scraper")
st.markdown("Search for suppliers by industry, category, and location using SerpAPI.")

# Input fields
with st.form(key="search_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        industry = st.text_input("Industry", value=st.session_state["industry"], placeholder="e.g., Automotive")
    with col2:
        category = st.text_input("Category", value=st.session_state["category"], placeholder="e.g., Hot Forgings")
    with col3:
        location = st.text_input("Location", value=st.session_state["location"], placeholder="e.g., China")
    
    num_results = st.slider("Number of Results", min_value=1, max_value=20, value=st.session_state["num_results"])
    
    col4, col5 = st.columns([1, 1])
    with col4:
        search_clicked = st.form_submit_button("🔎 Search", use_container_width=True)
    with col5:
        clear_clicked = st.form_submit_button("🗑️ Clear", use_container_width=True)

# Search logic
if search_clicked:
    if not industry or not category or not location:
        st.warning("Please fill in all fields before searching.")
    else:
        st.session_state["industry"] = industry
        st.session_state["category"] = category
        st.session_state["location"] = location
        st.session_state["num_results"] = num_results
        with st.spinner("Scraping supplier data..."):
            st.session_state["suppliers"] = scrape_suppliers(
                industry, category, location, num_results, "suppliers.csv"
            )

# Clear logic
if clear_clicked:
    st.session_state["industry"] = ""
    st.session_state["category"] = ""
    st.session_state["location"] = ""
    st.session_state["num_results"] = 5
    st.session_state["suppliers"] = []
    st.session_state["deep_scrape_results"] = {}
    st.session_state["deep_scrape_raw_text"] = {}
    st.session_state["chat_histories"] = {}
    st.session_state["chat_active"] = {}
    st.session_state["ranking_results"] = {}
    st.rerun()

# Display results
if st.session_state["suppliers"]:
    st.markdown(f"### Supplier Results for '{st.session_state['industry']} {st.session_state['category']}' in {st.session_state['location']}")
    st.markdown(f"*Found {len(st.session_state['suppliers'])} suppliers*")
    
    df = pd.DataFrame(st.session_state["suppliers"])
    
    # Display deep scrape and ranking results above the table
    for index, row in df.iterrows():
        if row["website"] in st.session_state["deep_scrape_results"]:
            with st.expander(f"Deep Scrape Results for {row['name']} ({row['website']})", expanded=False):
                st.markdown('<div class="deep-result">', unsafe_allow_html=True)
                deep_result = st.session_state["deep_scrape_results"][row["website"]]
                lines = deep_result.split('\n')
                for line in lines:
                    if "Multiple Suppliers Detected" in line:
                        st.markdown(f"<span style='color:red; font-weight:bold'>{line}</span>", unsafe_allow_html=True)
                    else:
                        st.markdown(line, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Display ranking if available
                if row["website"] in st.session_state["ranking_results"]:
                    st.markdown("#### Supplier Ranking")
                    ranking = st.session_state["ranking_results"][row["website"]]
                    supplier_name = list(ranking.keys())[0]
                    total_score = ranking[supplier_name]["total"]
                    st.markdown(f"*{supplier_name}*: {total_score:.1f}/5 ")
                    st.markdown(f"Details: {json.dumps(ranking[supplier_name], indent=2)}")

                # Chatbot toggle button
                col1, col2 = st.columns([10, 1])
                with col2:
                    if st.button("💬", key=f"chat_{index}", help="Chat about this supplier"):
                        st.session_state["chat_active"][row["website"]] = not st.session_state["chat_active"].get(row["website"], False)
                
                # Chatbot interface
                if st.session_state["chat_active"].get(row["website"], False):
                    with st.container():
                        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
                        st.markdown("#### Chat with Supplier Bot")
                        
                        if row["website"] not in st.session_state["chat_histories"]:
                            st.session_state["chat_histories"][row["website"]] = []
                        
                        for message in st.session_state["chat_histories"][row["website"]]:
                            if message["role"] == "user":
                                st.markdown(f'<div class="chat-message user-message">{message["content"]}</div>', unsafe_allow_html=True)
                            else:
                                st.markdown(f'<div class="chat-message bot-message">{message["content"]}</div>', unsafe_allow_html=True)
                        
                        with st.form(key=f"chat_form_{row['website']}", clear_on_submit=True):
                            user_query = st.text_input("Ask a question about this supplier:", key=f"input_{row['website']}")
                            submit_button = st.form_submit_button(label="Send")
                            
                            if submit_button and user_query:
                                st.session_state["chat_histories"][row["website"]].append({"role": "user", "content": user_query})
                                summary = st.session_state["deep_scrape_raw_text"].get(row["website"], "")
                                if summary:
                                    with st.spinner("Generating response..."):
                                        bot_response = chat_with_openai(user_query, context=summary)
                                else:
                                    bot_response = "No website content available to answer your question."
                                st.session_state["chat_histories"][row["website"]].append({"role": "bot", "content": bot_response})
                                st.rerun()
                        
                        st.markdown('</div>', unsafe_allow_html=True)
    
    # Custom styled table with tappable icon and ranking display
    with st.container():
        st.markdown('<div class="supplier-table">', unsafe_allow_html=True)
        for index, row in df.iterrows():
            st.markdown('<div class="supplier-row">', unsafe_allow_html=True)
            col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 2, 2, 2, 1, 1, 1])
            with col1:
                # Tappable icon in a button-like box without underline
                st.markdown(
                    f'<a href="{row["website"]}" target="_blank" class="link-button">🧷</a>',
                    unsafe_allow_html=True
                )
            with col2:
                st.markdown(f"*{row['name']}*")
            with col3:
                st.markdown(row["email"])
            with col4:
                st.markdown(row["phone"])
            with col5:
                if st.button("🔍", key=f"deep_{index}", help="Scrape deeper details"):
                    with st.spinner(f"Scraping deeper details for {row['website']}..."):
                        formatted_result, summary = scrape_deeper(row["website"])
                        st.session_state["deep_scrape_results"][row["website"]] = formatted_result
                        st.session_state["deep_scrape_raw_text"][row["website"]] = summary
            with col6:
                if st.button("⭐", key=f"rank_{index}", help="Rank this supplier"):
                    with st.spinner(f"Ranking {row['name']}..."):
                        raw_text = extract_info(row["website"])
                        if raw_text:
                            ranking = rank_suppliers(raw_text)
                            if ranking:
                                st.session_state["ranking_results"][row["website"]] = ranking
                                for i, supplier in enumerate(st.session_state["suppliers"]):
                                    if supplier["website"] == row["website"]:
                                        supplier_name = list(ranking.keys())[0]
                                        total_score = ranking[supplier_name]["total"]
                                        st.session_state["suppliers"][i]["ranking"] = f"{total_score:.1f}/5"
                                        break
                            else:
                                st.error(f"Failed to rank {row['name']}.")
                        else:
                            st.error(f"No data extracted for {row['website']} to rank.")
            with col7:
                ranking_display = row["ranking"]
                if row["website"] in st.session_state["ranking_results"]:
                    supplier_name = list(st.session_state["ranking_results"][row["website"]].keys())[0]
                    total_score = st.session_state["ranking_results"][row["website"]][supplier_name]["total"]
                    ranking_display = f"{total_score:.1f}/5 ★"
                st.markdown(f'<span class="ranking-display">{ranking_display}</span>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Download button
    csv_data = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download CSV",
        data=csv_data,
        file_name=f"{industry}{category}{location}_suppliers.csv",
        mime="text/csv",
        key="download-csv",
        use_container_width=True
    )
elif search_clicked and not st.session_state["suppliers"]:
    st.info("No suppliers found for the given criteria.")

# Footer
st.markdown("---")
st.markdown("Powered by SerpAPI, BeautifulSoup, and OpenAI")