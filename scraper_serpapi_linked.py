import requests
from bs4 import BeautifulSoup
import time
import html

SERPAPI_KEY = "ea021dba5d23a5f08e6daca4c9ddc0e14025a16ae2ac3e55b6cee1793a38458d" 


def scrape_linkedin_suppliers(industry, location, num_results=5):
    """
    Uses Google Search via SerpAPI to find LinkedIn supplier profiles,
    then extracts publicly available details.
    """
    search_query = f"site:linkedin.com/company {industry} suppliers in {location}"
    
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

    # **Only extract company pages (LinkedIn /company/ pages)**
    linkedin_links = [result["link"] for result in data["organic_results"] if "/company/" in result["link"]]

    # Step 2: Scrape each LinkedIn company page for public details
    supplier_data = []
    
    for link in linkedin_links[:num_results]:
        try:
            response = requests.get(link, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(response.text, "html.parser")

            # Extract company name (From Title, Meta, or H1)
            title = soup.title.text.strip() if soup.title else None
            h1 = soup.find("h1").text.strip() if soup.find("h1") else None
            supplier_name = title.replace(" | LinkedIn", "").strip() if title else (h1 if h1 else "Unknown Company")

            # Extract company description
            description_meta = soup.find("meta", {"name": "description"})
            description = description_meta["content"] if description_meta else "No description available"

            # Decode HTML Entities (Fixes &amp;)
            description = html.unescape(description)

            supplier_data.append({
                "name": supplier_name,
                "linkedin": link,
                "description": description
            })

            time.sleep(2)  # Avoid rate limits

        except Exception as e:
            print(f"Error scraping {link}: {e}")

    return supplier_data


# Example Usage
if __name__ == "__main__":
    results = scrape_linkedin_suppliers("Automotive Parts", "India", num_results=3)
    for supplier in results:
        print(supplier)
