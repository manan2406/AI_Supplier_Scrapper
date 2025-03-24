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
import plotly.express as px
import plotly.graph_objects as go

# Load environment variables
load_dotenv()
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Set up OpenAI API
openai.api_key = OPENAI_API_KEY

# List of multi-supplier marketplaces
MULTI_SUPPLIER_SITES = [
    "alibaba.com",
    "thomasnet.com",
    "indiamart.com",
    "made-in-china.com",
    "globalsources.com"
]

# Function to extract text from a webpage with retries
def extract_webpage_text(url, retries=3):
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

# Chat with OpenAI to get insights from scraped data
def chat_with_openai(user_input, context=""):
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
        return "Sorry, I couldn't process that request due to an API error."

# Rank suppliers with weighted criteria
def rank_suppliers(text):
    criteria_weights = {
        "product_quality": 0.25,
        "certifications": 0.15,
        "customer_reviews": 0.20,
        "price_competitiveness": 0.15,
        "manufacturing_capabilities": 0.10,
        "reliability": 0.10,
        "innovation": 0.05
    }

    query = (
        "Based on the following supplier information, rank them numerically from best to worst considering "
        "the following criteria: product quality (consistency, durability), certifications (ISO, industry standards), "
        "customer reviews (sentiment and volume, if available), price competitiveness (relative to market), "
        "manufacturing capabilities (scale, technology), reliability (delivery consistency, uptime), and innovation "
        "(R&D, patents, technology adoption). Provide structured JSON output ONLY with supplier names as keys and "
        "their respective ranking scores out of 5 for each category. If a criterion cannot be evaluated due to missing "
        "data, assign a neutral score of 3. Ensure the response is strictly valid JSON with no additional text.\n\n"
        f"Supplier Info: {text[:5000]}"
    )
    response = chat_with_openai(query)
    
    try:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            ranking_data = json.loads(json_match.group(0))
            cleaned_data = {}
            for supplier, scores in ranking_data.items():
                if isinstance(scores, dict):
                    cleaned_scores = {}
                    for criterion in criteria_weights.keys():
                        if criterion in scores and isinstance(scores[criterion], (int, float)):
                            cleaned_scores[criterion] = min(5, max(0, float(scores[criterion])))
                        else:
                            cleaned_scores[criterion] = 3.0
                    weighted_total = sum(cleaned_scores[criterion] * weight for criterion, weight in criteria_weights.items())
                    cleaned_scores["total"] = round(weighted_total, 1)
                    cleaned_data[supplier] = cleaned_scores
            return cleaned_data
        else:
            st.error("No valid JSON found in ranking response.")
            return None
    except json.JSONDecodeError:
        st.error("Unable to parse JSON response from OpenAI for ranking.")
        return None

# Format deep scrape results with bold titles and no emojis
def format_deep_scrape_output(result):
    if "Error" in result:
        return result
    
    lines = result.split('\n')
    formatted_output = []
    sections = {
        "Phone Number": "Phone Numbers",
        "Email": "Emails",
        "Supplier Details": "Supplier Details",
        "Location": "Location",
        "Product Pricing": "Product Pricing",
        "ISO Certifications": "ISO Certifications",
        "Manufacturing Process Summary": "Manufacturing Process Summary"
    }
    
    supplier_lines = [line for line in lines if "supplier details" in line.lower()]
    multiple_suppliers = len(supplier_lines) > 1
    
    if multiple_suppliers:
        formatted_output.append("Multiple Suppliers Detected on this Website")
    
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
                content = line.split(':', 1)[1].strip() if ':' in line else line[len(key):].strip()
                if "Supplier Details" in display_name and multiple_suppliers:
                    supplier_index += 1
                    supplier_data[supplier_index] = [f"**Supplier {supplier_index} Details**: {content}"]
                else:
                    formatted_output.append(f"**{display_name}**: {content}")
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
                formatted_output.append(f"**{display_name}**: No ISO certifications mentioned.")
            elif display_name == "Manufacturing Process Summary":
                formatted_output.append(f"**{display_name}**: Please contact the supplier for details.")
            elif display_name == "Location":
                formatted_output.append(f"**{display_name}**: Not specified in the text.")
            else:
                formatted_output.append(f"**{display_name}**: Not found in the text.")
    
    return "\n".join(formatted_output) if formatted_output else "No structured data extracted."

# Cache the deep scrape to avoid repeated calls
@lru_cache(maxsize=128)
def deep_scrape_website(url):
    data_values = extract_webpage_text(url)
    if data_values:
        truncated_text = data_values[:5000]
        user_input = (
            f"Extract and analyze details from this text: {truncated_text}. "
            f"If multiple suppliers are mentioned, list each separately with their details. "
            f"Provide the output in a structured format with the following sections:\n"
            f"- Phone Number: List any phone numbers found.\n"
            f"- Email: List any email addresses found.\n"
            f"- Supplier Details: Include company name, address, or contact person if mentioned; if multiple suppliers, list each separately.\n"
            f"- Location: Specify the specific location of the supplier if available; if not, state 'Not specified in the text.'\n"
            f"- Product Pricing: List prices of products mentioned.\n"
            f"- ISO Certifications: Specify any ISO certifications if present; if none, state 'No ISO certifications mentioned.'\n"
            f"- Manufacturing Process Summary: Summarize specific manufacturing process details if available; if not, state 'PLEASE CONTACT THE SUPPLIER FOR DETAILS'."
        )
        result = chat_with_openai(user_input, context=truncated_text)
        formatted_result = format_deep_scrape_output(result)
        summary_prompt = f"Summarize the following text in 200 words or less: {truncated_text}"
        summary = chat_with_openai(summary_prompt, context=truncated_text)
        return formatted_result, summary
    return "No data extracted. The website might be blocking requests.", None

# Extract a company name from the URL
def get_company_name_from_url(url):
    url = re.sub(r'^https?://', '', url)
    url = re.sub(r'^www\.', '', url)
    domain = re.split(r'[./]', url)[0]
    for site in MULTI_SUPPLIER_SITES:
        if site in url.lower():
            return f"{domain} (Multiple Suppliers Found)"
    return domain

# Scrape suppliers using SerpAPI
def search_for_suppliers(industry, category, location, num_results=5, output_file="suppliers.csv"):
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
    
    progress_bar = st.progress(0)
    total_links = len(supplier_links)
    
    for idx, link in enumerate(supplier_links):
        try:
            supplier_name = get_company_name_from_url(link)
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
        
        progress_bar.progress((idx + 1) / total_links)

    try:
        with open(output_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=["category", "name", "website", "email", "phone", "ranking"])
            if file.tell() == 0:
                writer.writeheader()
            writer.writerows(supplier_data)
    except Exception as e:
        st.error(f"Error saving to CSV: {e}")

    return supplier_data

# Streamlit UI setup
st.set_page_config(page_title="AI Supplier Scraper", layout="wide", initial_sidebar_state="expanded")

# Professional CSS styling with light mode friendly colors
st.markdown("""
    <style>
    body {
        font-family: 'Roboto', sans-serif;
        background-color: #F7FAFC;
        color: #2D3748;
    }
    .main-header {
        color: #2B6CB0;
        font-size: 2.2em;
        font-weight: 600;
        text-align: center;
        margin-bottom: 10px;
    }
    .sub-header {
        color: #4A5568;
        font-size: 1.1em;
        text-align: center;
        margin-bottom: 30px;
    }
    .supplier-table {
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 15px;
        background-color: #FFFFFF;
    }
    .supplier-row {
        border-bottom: 1px solid #E2E8F0;
        padding: 12px 0;
        transition: background-color 0.3s;
    }
    .supplier-row:hover {
        background-color: #EDF2F7;
    }
    .deep-result {
        background-color: #F7FAFC;
        padding: 15px;
        border-radius: 6px;
        margin-bottom: 15px;
        border-left: 4px solid #2B6CB0;
    }
    .chat-container {
        background-color: #F7FAFC;
        padding: 15px;
        border-radius: 6px;
        margin-top: 15px;
        border: 1px solid #E2E8F0;
    }
    .chat-message {
        padding: 8px;
        margin: 5px 0;
        border-radius: 5px;
    }
    .user-message {
        background-color: #EBF8FF;
        text-align: right;
    }
    .bot-message {
        background-color: #E2E8F0;
        text-align: left;
    }
    .ranking-display {
        color: #2B6CB0;
        font-weight: 500;
        font-size: 1em;
    }
    .link-button {
        display: inline-block;
        padding: 8px 12px;
        border: 1px solid #2B6CB0;
        border-radius: 5px;
        text-decoration: none;
        color: #2D3748;
        font-size: 14px;
        cursor: pointer;
        transition: border-color 0.3s;
    }
    .link-button:hover {
        border-color: #2C5282;
    }
    .action-button {
        background-color: #2B6CB0;
        color: #FFFFFF;
        border: none;
        border-radius: 5px;
        padding: 8px 12px;
        cursor: pointer;
        font-size: 14px;
        transition: background-color 0.3s;
    }
    .action-button:hover {
        background-color: #2C5282;
    }
    .favorite-button {
        background-color: #4A5568;
        color: #FFFFFF;
        border: none;
        border-radius: 5px;
        padding: 8px 12px;
        cursor: pointer;
        font-size: 14px;
    }
    .favorite-button:hover {
        background-color: #2D3748;
    }
    .sidebar .sidebar-content {
        background-color: #F7FAFC;
    }
    </style>
""", unsafe_allow_html=True)

# Sidebar with "Designed by Code Intellect"
with st.sidebar:
    st.markdown(
        """
        <div style='text-align: center; padding: 10px;'>
            <h2 style='color: #2B6CB0; font-size: 1.5em; font-weight: 600; margin-bottom: 20px;'>
                Designed by Code Intellect
            </h2>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("### About")
    st.markdown("This application facilitates supplier discovery and analysis using SerpAPI and OpenAI. Developed by Code Intellect.")

# Initialize session state for storing data
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
if "favorites" not in st.session_state:
    st.session_state["favorites"] = []

# Main UI
st.markdown('<h1 class="main-header">AI Supplier Scraper</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Discover and analyze suppliers efficiently</p>', unsafe_allow_html=True)

# Input form for searching suppliers
with st.form(key="search_form"):
    st.markdown("### Search for Suppliers")
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
        search_clicked = st.form_submit_button("Search Suppliers", use_container_width=True)
    with col5:
        clear_clicked = st.form_submit_button("Clear Search", use_container_width=True)

# Handle search and clear actions
if search_clicked:
    if not industry or not category or not location:
        st.warning("Please fill in all fields to start searching.")
    else:
        st.session_state["industry"] = industry
        st.session_state["category"] = category
        st.session_state["location"] = location
        st.session_state["num_results"] = num_results
        with st.spinner("Scraping supplier data..."):
            st.session_state["suppliers"] = search_for_suppliers(
                industry, category, location, num_results, "suppliers.csv"
            )

if clear_clicked:
    # Preserve favorites while clearing other session state
    preserved_favorites = st.session_state["favorites"]
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
    st.session_state["favorites"] = preserved_favorites  # Restore favorites
    st.rerun()

# Display search results
if st.session_state["suppliers"]:
    st.markdown(f"### Supplier Results for '{st.session_state['industry']} {st.session_state['category']}' in {st.session_state['location']}")
    st.markdown(f"Found {len(st.session_state['suppliers'])} suppliers")
    
    df = pd.DataFrame(st.session_state["suppliers"])
    
    for index, row in df.iterrows():
        if row["website"] in st.session_state["deep_scrape_results"]:
            with st.expander(f"Deep Scrape Results for {row['name']} ({row['website']})", expanded=False):
                st.markdown('<div class="deep-result">', unsafe_allow_html=True)
                deep_result = st.session_state["deep_scrape_results"][row["website"]]
                lines = deep_result.split('\n')
                for line in lines:
                    if "Multiple Suppliers Detected" in line:
                        st.markdown(f"<span style='color:#4A5568; font-weight:bold'>{line}</span>", unsafe_allow_html=True)
                    else:
                        st.markdown(line, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
                if row["website"] in st.session_state["ranking_results"]:
                    st.markdown("#### Supplier Ranking")
                    ranking = st.session_state["ranking_results"][row["website"]]
                    supplier_name = list(ranking.keys())[0]
                    total_score = ranking[supplier_name]["total"]
                    st.markdown(f"{supplier_name}: {total_score:.1f}/5")

                    scores = ranking[supplier_name]
                    criteria = [key.replace("_", " ").title() for key in scores.keys() if key != "total"]
                    values = [scores[key] for key in scores.keys() if key != "total"]

                    fig = go.Figure()
                    fig.add_trace(go.Scatterpolar(
                        r=values + [values[0]],
                        theta=criteria + [criteria[0]],
                        fill='toself',
                        name=supplier_name,
                        line=dict(color='#2B6CB0'),
                        fillcolor='rgba(43, 108, 176, 0.3)'
                    ))
                    fig.update_layout(
                        polar=dict(
                            radialaxis=dict(
                                visible=True,
                                range=[0, 5]
                            )
                        ),
                        showlegend=False,
                        height=300,
                        width=300,
                        margin=dict(l=20, r=20, t=30, b=20),
                        title=dict(text="Ranking Breakdown", x=0.5, font=dict(size=14))
                    )
                    st.plotly_chart(fig)

                col1, col2 = st.columns([10, 1])
                with col2:
                    if st.button(f"💬 Chat", key=f"chat_{index}", help="Chat about this supplier"):
                        st.session_state["chat_active"][row["website"]] = not st.session_state["chat_active"].get(row["website"], False)
                
                if st.session_state["chat_active"].get(row["website"], False):
                    with st.container():
                        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
                        st.markdown("#### Chat with Supplier Assistant")
                        
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
                                    bot_response = "Sorry, no website content available to answer your question."
                                st.session_state["chat_histories"][row["website"]].append({"role": "bot", "content": bot_response})
                                st.rerun()
                        
                        st.markdown('</div>', unsafe_allow_html=True)
    
    with st.container():
        st.markdown('<div class="supplier-table">', unsafe_allow_html=True)
        for index, row in df.iterrows():
            st.markdown('<div class="supplier-row">', unsafe_allow_html=True)
            col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([2, 2, 2, 2, 1, 1, 1, 1])
            with col1:
                st.markdown(
                    f'<a href="{row["website"]}" target="_blank" class="link-button">🌐 Visit Website</a>',
                    unsafe_allow_html=True
                )
            with col2:
                st.markdown(f"**{row['name']}**")
            with col3:
                st.markdown(row["email"])
            with col4:
                st.markdown(row["phone"])
            with col5:
                if st.button(f"🔍 Details", key=f"deep_{index}", help="Scrape deeper details"):
                    with st.spinner(f"Scraping deeper details for {row['website']}..."):
                        formatted_result, summary = deep_scrape_website(row["website"])
                        st.session_state["deep_scrape_results"][row["website"]] = formatted_result
                        st.session_state["deep_scrape_raw_text"][row["website"]] = summary
            with col6:
                if st.button(f"⭐ Rank", key=f"rank_{index}", help="Rank this supplier"):
                    with st.spinner(f"Ranking {row['name']}..."):
                        raw_text = extract_webpage_text(row["website"])
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
                    ranking_display = f"{total_score:.1f}/5"
                st.markdown(f'<span class="ranking-display">{ranking_display}</span>', unsafe_allow_html=True)
            with col8:
                if row["website"] in st.session_state["favorites"]:
                    if st.button(f"💔 Remove Favorite", key=f"fav_remove_{index}"):
                        st.session_state["favorites"].remove(row["website"])
                        st.rerun()
                else:
                    if st.button(f"❤️ Add to Favorites", key=f"fav_add_{index}", help="Add to favorites"):
                        st.session_state["favorites"].append(row["website"])
                        st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    csv_data = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Results as CSV",
        data=csv_data,
        file_name=f"{industry}_{category}_{location}_suppliers.csv",
        mime="text/csv",
        key="download-csv",
        use_container_width=True
    )

    # Display Favorite Suppliers section below Download CSV
    if st.session_state["favorites"]:
        st.markdown("### Favorite Suppliers")
        fav_df = df[df["website"].isin(st.session_state["favorites"])]
        st.dataframe(fav_df)

elif search_clicked and not st.session_state["suppliers"]:
    st.info("No suppliers found for the given criteria. Try adjusting your search terms.")

    # Display Favorite Suppliers even if no suppliers are found
    if st.session_state["favorites"]:
        st.markdown("### Favorite Suppliers")
        # Since no suppliers are found, we need to reconstruct the DataFrame from favorites
        fav_suppliers = [s for s in st.session_state["favorites"]]
        # Create a DataFrame for favorites (we'll need to fetch or store supplier details differently if needed)
        # For simplicity, we'll show only the website URLs if no current supplier data is available
        fav_data = [{"website": website} for website in fav_suppliers]
        fav_df = pd.DataFrame(fav_data)
        st.dataframe(fav_df)

# Footer
st.markdown("---")
st.markdown("Powered by SerpAPI, BeautifulSoup, and OpenAI | Developed by Code Intellect")