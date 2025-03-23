import requests
from bs4 import BeautifulSoup

###Indiamart
def scrape_indiamart_bs4(search_query, num_results=5):
    """
    Scrapes supplier details from IndiaMart using requests & BeautifulSoup.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    indiamart_url = f"https://dir.indiamart.com/search.mp?ss={search_query.replace(' ', '+')}"
    response = requests.get(indiamart_url, headers=headers)

    if response.status_code != 200:
        print("Failed to fetch IndiaMart page.")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    suppliers = []
    for supplier in soup.select(".lg")[:num_results]:  # Adjust selector as needed
        name = supplier.find("h2")
        company_name = name.text.strip() if name else "Unknown Supplier"

        link = supplier.find("a", href=True)
        supplier_link = link["href"] if link else "N/A"

        contact_info = supplier.find("p", class_="c_info")
        phone_number = contact_info.text.strip() if contact_info else "N/A"

        suppliers.append({
            "name": company_name,
            "website": supplier_link,
            "phone": phone_number
        })

    return suppliers


# Example Usage
if __name__ == "__main__":
    results = scrape_indiamart_bs4("Automotive Parts", num_results=3)
    for supplier in results:
        print(supplier)


##ALIBABA

def scrape_alibaba_bs4(search_query, num_results=5):
    """
    Scrapes supplier details from Alibaba using requests & BeautifulSoup.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    alibaba_url = f"https://www.alibaba.com/trade/search?fsb=y&IndexArea=company_en&CatId=&SearchText={search_query.replace(' ', '+')}"
    response = requests.get(alibaba_url, headers=headers)

    if response.status_code != 200:
        print("Failed to fetch Alibaba page.")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    suppliers = []
    for supplier in soup.select(".m-gallery-product-item")[:num_results]:
        name = supplier.find("h2", class_="title")
        company_name = name.text.strip() if name else "Unknown Supplier"

        link = supplier.find("a", href=True)
        supplier_link = link["href"] if link else "N/A"

        location = supplier.find("div", class_="location")
        supplier_location = location.text.strip() if location else "N/A"

        suppliers.append({
            "name": company_name,
            "website": supplier_link,
            "location": supplier_location
        })

    return suppliers


# Example Usage
if __name__ == "__main__":
    results = scrape_alibaba_bs4("Automotive Parts", num_results=3)
    for supplier in results:
        print(supplier)
