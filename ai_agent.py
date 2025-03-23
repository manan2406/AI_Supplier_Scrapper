import scrapy
from scrapy.crawler import CrawlerProcess
import pandas as pd
from openai import OpenAI
from flask import Flask, request, jsonify
import json
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Open AI API Key (replace with your actual key)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Step 1: Define the Scrapy Spider
class IndiaMartSpider(scrapy.Spider):
    name = "indiamart"
    allowed_domains = ["indiamart.com"]
    start_urls = ["https://dir.indiamart.com/indianexporters/m_automobile.html"]  # Automotive suppliers

    def parse(self, response):
        for supplier in response.css("div.listing-container"):
            yield {
                "name": supplier.css("a.prd-name::text").get(default="N/A").strip(),
                "website": supplier.css("a.prd-name::attr(href)").get(default="N/A"),
                "description": supplier.css("p.sdesc::text").get(default="N/A").strip(),
                "contact": supplier.css("span.contact::text").get(default="N/A")
            }
        next_page = response.css("a.next::attr(href)").get()
        if next_page:
            yield response.follow(next_page, self.parse)

# Step 2: Clean Data Function
def clean_data(input_file, output_file):
    data = pd.read_json(input_file)
    data.drop_duplicates(subset=["name", "website"], inplace=True)
    data["description"] = data["description"].str.lower().str.strip()
    data.fillna("N/A", inplace=True)
    data.to_csv(output_file, index=False)
    print(f"Data cleaned and saved to {output_file}")

# Step 3: Classify Suppliers with Open AI
def classify_supplier(description):
    prompt = f"""
    Given the supplier description: '{description}',
    extract the following:
    - Industries served (e.g., Automotive, Electronics)
    - Manufacturing processes (e.g., CNC Machining, Die-Casting)
    - Commodities (e.g., Aluminum, Steel)
    - Assign a relevance score (0-100) based on data completeness and credibility
    Return the result as a JSON object.
    """
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that extracts structured data from text."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=150
    )
    return json.loads(response.choices[0].message.content)

def process_suppliers(input_file, output_file):
    data = pd.read_csv(input_file)
    classified_data = []

    for index, row in data.iterrows():
        result = classify_supplier(row["description"])
        classified_data.append({
            "name": row["name"],
            "website": row["website"],
            "contact": row["contact"],
            "industries": result.get("industries", []),
            "processes": result.get("processes", []),
            "commodities": result.get("commodities", []),
            "relevance_score": result.get("relevance_score", 0)
        })

    pd.DataFrame(classified_data).to_csv(output_file, index=False)
    print(f"Classified data saved to {output_file}")

# Step 4: Flask API
app = Flask(__name__)

def load_suppliers():
    return pd.read_csv("classified_suppliers.csv")

@app.route("/search", methods=["GET"])
def search_suppliers():
    suppliers = load_suppliers()
    query = request.args.get("q", "").lower()
    results = suppliers[
        suppliers["industries"].str.lower().str.contains(query, na=False) |
        suppliers["processes"].str.lower().str.contains(query, na=False) |
        suppliers["commodities"].str.lower().str.contains(query, na=False)
    ].sort_values(by="relevance_score", ascending=False).to_dict(orient="records")
    return jsonify(results)

# Main Execution
if __name__ == "__main__":
    # Step 1: Run the Scrapy Spider
    process = CrawlerProcess(settings={
        "FEEDS": {"suppliers.json": {"format": "json"}},
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    process.crawl(IndiaMartSpider)
    process.start()

    # Step 2: Clean the Data
    clean_data("suppliers.json", "cleaned_suppliers.csv")

    # Step 3: Classify with Open AI
    process_suppliers("cleaned_suppliers.csv", "classified_suppliers.csv")

    # Step 4: Start Flask API
    print("Starting Flask API at http://localhost:5000/search")
    app.run(debug=True)