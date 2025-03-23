import requests
from bs4 import BeautifulSoup
import re
import time
import csv
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

def scrape_suppliers(industry, location, num_results=5, output_file="data.csv"):
    """
    Searches Google via SerpAPI for suppliers in a given industry and location,
    extracts supplier details from the top search results, and saves the data to a CSV file.
    """
    search_query = f"{industry} suppliers in {location}"
    
    # Step 1: Get search results from Google using SerpAPI
    params = {
        "engine": "google",
        "q": search_query,
        "num": num_results,
        "api_key": SERPAPI_KEY
    }

    response = requests.get("https://serpapi.com/search", params=params)
    data = response.json()
    
    if "organic_results" not in data:
        print("No results found")
        return []

    supplier_links = [result["link"] for result in data["organic_results"][:num_results]]

    # Step 2: Scrape supplier websites for details
    supplier_data = []
    
    for link in supplier_links:
        try:
            supplier_response = requests.get(link, timeout=10)
            soup = BeautifulSoup(supplier_response.text, "html.parser")

            # Extract supplier name (H1 or Title)
            supplier_name = soup.find("h1")
            supplier_name = supplier_name.text.strip() if supplier_name else soup.title.text.strip()

            # Extract contact details (email, phone)
            text_content = soup.get_text()
            emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text_content)
            phones = re.findall(r"\+?\d[\d -]{8,}\d", text_content)

            supplier_data.append({
                "name": supplier_name,
                "website": link,
                "email": emails[0] if emails else "N/A",
                "phone": phones[0] if phones else "N/A"
            })

            time.sleep(2)  # Avoid rate limits

        except Exception as e:
            print(f"Error scraping {link}: {e}")

    # Step 3: Save data to CSV
    with open(output_file, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=["name", "website", "email", "phone"])
        writer.writeheader()
        writer.writerows(supplier_data)
    
    print(f"Data saved to {output_file}")
    return supplier_data


# Example Usage
if __name__ == "__main__":
    results = scrape_suppliers("gravity casting", "india", num_results=50)
    for supplier in results:
        print(supplier)
