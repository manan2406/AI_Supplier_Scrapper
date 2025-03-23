

import requests
from bs4 import BeautifulSoup
import re
import time

SERPAPI_KEY = "ea021dba5d23a5f08e6daca4c9ddc0e14025a16ae2ac3e55b6cee1793a38458d" 

def scrape_suppliers(industry, location, num_results=5):
    """
    Searches Google via SerpAPI for suppliers in a given industry and location,
    extracts supplier details from the top search results.
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

    return supplier_data


# Example Usage
if __name__ == "__main__":
    results = scrape_suppliers("Automotive Parts", "India", num_results=3)
    for supplier in results:
        print(supplier)
