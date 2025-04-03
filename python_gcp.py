# Unified Flask app for scraping, PDF analysis, and tagging
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
import json
from openai import OpenAI
from dotenv import load_dotenv
import re
from io import BytesIO
from PyPDF2 import PdfReader
from requests.auth import HTTPBasicAuth

load_dotenv()

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

# WordPress credentials and API
site_url = "https://patentlawprofessor.com"
username = "admin_a683wnr3"
app_password = "SQ6E zz6O FbLX mGHA bBnT gHG1"
wp_endpoint = f"{site_url}/wp-json/wp/v2/tags"

DELAY_SHORT = 2
DELAY_LONG = 3

class USCCourtScraper:
    def __init__(self, target_date):
        self.url = 'https://www.cafc.uscourts.gov/home/case-information/opinions-orders/'
        self.driver = self._initialize_driver()
        self.target_date = target_date

    def _initialize_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    def open_website(self):
        self.driver.get(self.url)
        time.sleep(DELAY_LONG)

    def filter_with_origin_and_current_date(self):
        try:
            from_field = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "table_1_range_from_0")))
            from_field.clear()
            from_field.send_keys(self.target_date)
            from_field.send_keys(Keys.RETURN)

            to_field = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "table_1_range_to_0")))
            to_field.clear()
            to_field.send_keys(self.target_date)
            to_field.send_keys(Keys.RETURN)

            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="table_1_2_filter"]/span/div/button'))).click()
            for li in [9, 15, 21]:
                WebDriverWait(self.driver, 2).until(EC.element_to_be_clickable((By.XPATH, f'//*[@id="table_1_2_filter"]/span/div/div/ul/li[{li}]/a'))).click()

            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(DELAY_LONG)
        except Exception as e:
            print(f"Error filtering data: {e}")

    def extract_pdf_links(self):
        try:
            table_body = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "tbody")))
            rows = table_body.find_elements(By.TAG_NAME, "tr")
            data = {"pdf_links": [], "case_names": []}

            for row in rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    case_name = cells[-2].find_element(By.TAG_NAME, "a").text
                    pdf_link = cells[-2].find_element(By.TAG_NAME, "a").get_attribute("href")
                    data["case_names"].append(case_name)
                    data["pdf_links"].append(pdf_link)
                except:
                    continue
            return data
        except Exception as e:
            print(f"Error extracting PDF links: {e}")
            return {}

    def paginate_and_scrape(self):
        all_data = {"pdf_links": [], "case_names": []}
        while True:
            page_data = self.extract_pdf_links()
            if not page_data["pdf_links"]:
                break
            all_data["pdf_links"].extend(page_data["pdf_links"])
            all_data["case_names"].extend(page_data["case_names"])

            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="table_1_next"]'))).click()
                time.sleep(DELAY_LONG)
            except:
                break
        return all_data

    def run(self):
        self.open_website()
        self.filter_with_origin_and_current_date()
        time.sleep(DELAY_LONG)
        data = self.paginate_and_scrape()
        self.driver.quit()
        return data

def analyze_for_tags(pdf_url):
    try:
        response = requests.get(pdf_url)
        pdf = PdfReader(BytesIO(response.content))
        text = "".join([pdf.pages[i].extract_text() for i in range(min(3, len(pdf.pages))) if pdf.pages[i].extract_text()])
        prompt = (
            "Extract 5 concise topic tags from the following legal document. "
            "Tags should be relevant to patent law and formatted as a JSON list of strings.\n\n"
            f"{text}\n\n"
            "Output format: [\"tag1\", \"tag2\", \"tag3\"]"
        )
        chat_completion = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        reply = chat_completion.choices[0].message.content
        match = re.search(r'\[.*?\]', reply, re.DOTALL)
        return json.loads(match.group(0)) if match else []
    except Exception as e:
        print(f"Error extracting tags: {e}")
        return []

def create_wordpress_tag(tag):
    try:
        payload = {"name": tag}
        response = requests.post(wp_endpoint, json=payload, auth=HTTPBasicAuth(username, app_password))
        if response.status_code == 201:
            print(f"✅ Created tag: {tag}")
        elif response.status_code == 400 and 'term_exists' in response.text:
            print(f"⚠️ Tag already exists: {tag}")
        else:
            print(f"❌ Failed to create tag: {tag} — Status: {response.status_code}")
    except Exception as e:
        print(f"Request failed for tag '{tag}': {e}")

@app.route("/run-scraper", methods=["POST"])
def run_scraper():
    data = request.get_json()
    target_date = data.get("date", datetime.now().strftime("%m/%d/%Y"))
    scraper = USCCourtScraper(target_date)
    results = scraper.run()

    all_tags = set()
    for link in results["pdf_links"]:
        tags = analyze_for_tags(link)
        all_tags.update(tags)

    for tag in all_tags:
        continue
        create_wordpress_tag(tag)

    return jsonify({
        "message": f"Completed. Extracted and added {len(all_tags)} unique tags.",
        "tags": list(all_tags)
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
