from flask import Flask, jsonify, request
import os
import requests
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
import time

app = Flask(__name__)

DELAY_SHORT = 2
DELAY_LONG = 3

# Load Webhook URL from environment variables
WEBHOOK_URL = "http://127.0.0.1:5678/webhook/automate"

class USCCourtScraper:
    def __init__(self, target_date):
        self.url = 'https://www.cafc.uscourts.gov/home/case-information/opinions-orders/'
        self.driver = self._initialize_driver()
        self.all_pdf_links = []
        self.target_date = target_date

    def _initialize_driver(self):
        """Initialize Selenium WebDriver with Chrome options (headless mode)."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  
        chrome_options.add_argument("--no-sandbox")  
        chrome_options.add_argument("--disable-dev-shm-usage")  
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    def open_website(self):
        """Open the court's website."""
        self.driver.get(self.url)
        time.sleep(DELAY_LONG)  # Allow page to load

    def filter_with_origin_and_current_date(self):
        """Filter the table by provided date and CFC origin."""
        try:
            date_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "table_1_range_from_0"))
            )
            date_field.clear()
            date_field.send_keys(self.target_date)  # Use provided date
            date_field.send_keys(Keys.RETURN)

            # Select "CFC" from the origin filter
            # origin_xpath = '//*[@id="table_1_2_filter"]/span/div/button'
            # select_origin_button = WebDriverWait(self.driver, 10).until(
            #     EC.element_to_be_clickable((By.XPATH, origin_xpath))
            # )
            # select_origin_button.click()

            # cfc_option = WebDriverWait(self.driver, 2).until(
            #     EC.element_to_be_clickable((By.XPATH, '//*[@id="table_1_2_filter"]/span/div/div/ul/li[7]/a'))
            # )
            # cfc_option.click()

            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(DELAY_LONG)

        except Exception as e:
            print(f"Error filtering data: {e}")

    def extract_pdf_links(self):
        """Extract PDF links from the current page."""
        try:
            table_body = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "tbody"))
            )
            rows = table_body.find_elements(By.TAG_NAME, "tr")
            
            origins = []
            case_names = []
            pdf_links = []
            statuses = []
            for row in rows:
                try:
                    origin = row.find_elements(By.TAG_NAME, "td")[-3].text
                    case_name = row.find_elements(By.TAG_NAME, "td")[-2].find_element(By.TAG_NAME, "a").text
                    pdf_link = row.find_elements(By.TAG_NAME, "td")[-2].find_element(By.TAG_NAME, "a").get_attribute("href")
                    status = row.find_elements(By.TAG_NAME, "td")[-1].text
                    origins.append(origin)
                    case_names.append(case_name)
                    pdf_links.append(pdf_link)
                    statuses.append(status)
                except Exception:
                    continue  # Skip rows without PDFs

            return {
                "origins": origins,
                "case_names": case_names,
                "pdf_links": pdf_links,
                "statuses": statuses
            }

        except Exception as e:
            print(f"Error extracting PDF links: {e}")
            return {}

    def paginate_and_scrape(self):
        all_data = {
            "origins": [],
            "case_names": [],
            "pdf_links": [],
            "statuses": []
        }
        """Iterate through all pages and collect PDF links."""
        while True:
            page_data = self.extract_pdf_links()["pdf_links"]
            if not page_data:
                break

            all_data["origins"].extend(page_data["origins"])
            all_data["case_names"].extend(page_data["case_names"])
            all_data["pdf_links"].extend(page_data["pdf_links"])
            all_data["statuses"].extend(page_data["statuses"])
            print(f"Collected {len(all_data['pdf_links'])} PDF links so far...")

            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                next_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//*[@id="table_1_next"]'))
                )
                next_button.click()
                time.sleep(DELAY_LONG)  # Allow next page to load
            except Exception:
                print("No more pages.")
                break

        return all_data

    def run(self):
        """Run the full scraping process."""
        self.open_website()
        self.filter_with_origin_and_current_date()
        time.sleep(DELAY_LONG)
        results = self.paginate_and_scrape()
        self.driver.quit()
        return results

def send_results(results):
    print(results)
    """Send extracted PDF links to the n8n webhook."""
    if not results["pdf_links"]:
        return {"message": "No new PDFs found."}

    success_count = 0
    failed_urls = []

    for id, file_url in enumerate(results["pdf_links"]):
        payload = {"file_url": file_url}
        try:
            #response = requests.post(WEBHOOK_URL, json=payload, verify=False)
            #if response.status_code == 200:
            if True:
                # print(f"Sent successfully: {file_url}")
                # print(f'{id}, {results["origins"][id]}, {results["case_names"][id]}, {results["pdf_links"][id]}, {results["statuses"][id]}')
                success_count += 1
            else:
                print(f"Failed: {file_url}, Status: {response.status_code}")
                failed_urls.append(file_url)
        except requests.exceptions.RequestException as e:
            print(f"Request error: {file_url}, Error: {e}")
            failed_urls.append(file_url)

    return {
        "message": f"Scraper completed! {success_count} PDFs sent successfully.",
        "failed_urls": failed_urls,
        "results":results
    }

@app.route("/run-scraper", methods=["POST"])
def run_scraper():
    """API endpoint to trigger the scraper from n8n."""
    data = request.get_json()
    target_date = data.get("date", datetime.now().strftime("%m/%d/%Y"))
    print(target_date)

    scraper = USCCourtScraper(target_date)
    results = scraper.run()
    
    response = send_results(results)

    return jsonify(response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
