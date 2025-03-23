from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
import random

def setup_driver():
    # Set up Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--headless=chrome")  # Use older headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-accelerated-2d-canvas")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-accelerated-video-decode")  # Extra GPU suppression
    chrome_options.add_argument("--disable-accelerated-video-encode")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.90 Safari/537.36")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    # Specify ChromeDriver path if not in PATH (uncomment and update)
    # service = Service(executable_path="C:/Users/Manan/OneDrive/Desktop/Mesh_hackathon/chromedriver.exe")
    # driver = webdriver.Chrome(service=service, options=chrome_options)
    driver = webdriver.Chrome(options=chrome_options)  # Use if ChromeDriver is in PATH
    return driver

def scrape_alibaba(driver, search_query):
    url = f"https://www.alibaba.com/trade/search?keywords={search_query}"
    print(f"Loading URL: {url}")
    driver.get(url)
    
    try:
        WebDriverWait(driver, 40).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        print("Initial page load detected.")
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "search-card-item"))
        )
        print("Product listings loaded successfully.")
    except Exception as e:
        print(f"Error loading Alibaba page: {e}")
        with open("page_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("Page source saved to 'page_source.html'.")
        return []

    products = []
    items = driver.find_elements(By.CLASS_NAME, "search-card-item")
    print(f"Found {len(items)} items on the page.")
    
    if not items:
        print("No items found. Check 'page_source.html' for CAPTCHA or block.")
        return []

    for item in items[:10]:
        try:
            title = item.find_element(By.CSS_SELECTOR, ".elements-title-normal__content").text.strip() if item.find_elements(By.CSS_SELECTOR, ".elements-title-normal__content") else "N/A"
            price = item.find_element(By.CSS_SELECTOR, ".elements-offer-price-normal__price").text.strip() if item.find_elements(By.CSS_SELECTOR, ".elements-offer-price-normal__price") else "N/A"
            company = item.find_element(By.CSS_SELECTOR, ".search-card-e-company").text.strip() if item.find_elements(By.CSS_SELECTOR, ".search-card-e-company") else "N/A"
            
            products.append({
                'title': title,
                'price': price,
                'company': company,
                'source': 'Alibaba'
            })
            print(f"Scraped: {title[:50]}...")
        except Exception as e:
            print(f"Error parsing item: {e}")
            continue
    
    return products

def main():
    driver = None
    try:
        driver = setup_driver()
        print("WebDriver initialized successfully.")
        
        search_query = input("Enter product to search: ").strip()
        if not search_query:
            print("Error: No search query provided.")
            return
        
        alibaba_data = scrape_alibaba(driver, search_query)
        
        if alibaba_data:
            df = pd.DataFrame(alibaba_data)
            df.to_csv('alibaba_scraped_data.csv', index=False, encoding='utf-8')
            print("Data saved to 'alibaba_scraped_data.csv'")
            print(f"Total items scraped: {len(alibaba_data)}")
            print("\nSample data:")
            print(df.head())
        else:
            print("No data scraped from Alibaba.")
        
        time.sleep(random.uniform(2, 5))
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if driver:
            driver.quit()
            print("WebDriver closed.")

if __name__ == "__main__":
    main()