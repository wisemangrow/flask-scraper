from flask import Flask, jsonify, request
import os
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

app = Flask(__name__)

WEBHOOK_URL = os.getenv("https://n8n.patentlawprofessor.com/webhook/automate")

class USCCourtScraper:
    def __init__(self):
        self.url = 'https://www.cafc.uscourts.gov/home/case-information/opinions-orders/'
        self.driver = self._initialize_driver()
        self.all_pdf_links = []

    def _initialize_driver(self):
        """Initialize Selenium WebDriver with Chrome options (headless mode)."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  
        chrome_options.add_argument("--no-sandbox")  
        chrome_options.add_argument("--disable-dev-shm-usage")  
        chrome_options.add_argument("--disable-gpu")

        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    def run(self):
        """Run the scraping process."""
        try:
            self.driver.get(self.url)
            time.sleep(2)

            # Extract PDF links
            pdf_links = []
            table_body = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "tbody"))
            )
            rows = table_body.find_elements(By.TAG_NAME, "tr")

            for row in rows:
                try:
                    pdf_link = row.find_elements(By.TAG_NAME, "td")[-1].find_element(By.TAG_NAME, "a").get_attribute("href")
                    pdf_links.append(pdf_link)
                except:
                    continue

            self.all_pdf_links = pdf_links
            print(f"✅ Collected {len(self.all_pdf_links)} PDF links.")
            return pdf_links
        finally:
            self.driver.quit()

@app.route("/run-scraper", methods=["POST"])
def run_scraper():
    """Endpoint to trigger the scraper from n8n."""
    scraper = USCCourtScraper()
    pdf_links = scraper.run()
    
    # Send scraped links to n8n webhook
    for link in pdf_links:
        requests.post(WEBHOOK_URL, json={"file_url": link})
    
    return jsonify({"message": "Scraper completed!", "pdf_links": pdf_links})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
