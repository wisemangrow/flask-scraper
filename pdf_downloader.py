import os
import requests
from selenium import webdriver
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from datetime import datetime
# import schedule
import time

# Security Risk: This is not safe for production since it disables SSL verification
# Suppress the warning
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

WEBHOOK_URL = "https://n8n.patentlawprofessor.com/webhook/automate"
FILE_PATH = "pdf_links.txt"
class USCCourtScraper:
    def __init__(self):
        self.url = 'https://www.cafc.uscourts.gov/home/case-information/opinions-orders/'
        self.driver = self._initialize_driver()
        self.all_pdf_links = []

    def _initialize_driver(self):
        """Initialize Selenium WebDriver with Chrome options."""
        chrome_options = Options()
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--auto-open-devtools-for-tabs")    

        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    def open_website(self):
        """Open the website and refresh to ensure elements load properly."""
        self.driver.get(self.url)
        time.sleep(2)
        self.driver.refresh()

    def filter_with_origin_and_current_date(self):
        """Filter the table by current date and CFC origin."""
        current_date = datetime.now().strftime("%m/%d/%Y")
        # current_date = '02/10/2025' # For testing purpose
        date_field = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "table_1_range_from_0"))
        )
        date_field.clear()
        date_field.send_keys(current_date)
        date_field.send_keys(Keys.RETURN)

        origin_xpath = '//*[@id="table_1_2_filter"]/span/div/button'
        select_origin_button = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, origin_xpath))
        )
        select_origin_button.click()

        cfc_option = WebDriverWait(self.driver, 2).until(
            EC.element_to_be_clickable((By.XPATH, '//*[@id="table_1_2_filter"]/span/div/div/ul/li[7]/a'))
        )
        cfc_option.click()

        ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

    def extract_pdf_links(self):
        """Extract PDF links from the current page."""
        try:
            table_body = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "tbody"))
            )
            rows = table_body.find_elements(By.TAG_NAME, "tr")
            
            pdf_links = []
            for row in rows:
                try:
                    pdf_link = row.find_elements(By.TAG_NAME, "td")[-1].find_element(By.TAG_NAME, "a").get_attribute("href")
                    pdf_links.append(pdf_link)
                except Exception as e:
                    print("No more pdfs are found")
                    self.driver.quit()
            
            return pdf_links
        except Exception as e:
            print(f"Error extracting PDF links: {e}")
            return []

    def paginate_and_scrape(self):
        """Iterate through all pages and collect PDF links."""
        while True:
            self.all_pdf_links.extend(self.extract_pdf_links())
            print(f"Collected {len(self.all_pdf_links)} PDF links so far...")

            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                next_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//*[@id="table_1_next"]'))
                )
                next_button.click()
                time.sleep(5)  # Allow time for next page to load
            except Exception as e:
                print("No more pages")
                self.driver.quit()
                break

    def save_links_to_file(self, filename="pdf_links.txt"):
        """Save all collected PDF links to a text file."""
        with open(filename, 'w') as file:
            for link in self.all_pdf_links:
                file.write(link + '\n')
        print(f"✅ Saved {len(self.all_pdf_links)} PDF links to '{filename}'")

    def run(self):
        """Run the entire scraping process."""
        self.open_website()
        self.filter_with_origin_and_current_date()
        time.sleep(2)
        self.paginate_and_scrape()
        self.save_links_to_file()
        self.driver.quit()

def send_file_urls():
    if not os.path.exists(FILE_PATH):
        print("No file found. Exiting.")
        return

    with open(FILE_PATH, "r") as file:
        file_urls = [line.strip() for line in file.readlines() if line.strip()]

    if not file_urls:
        print("No file URLs found. Exiting.")
        return

    success_count = 0
    for file_url in set(file_urls): 
        payload = {"file_url": file_url}
        try:
            response = requests.post(WEBHOOK_URL, json=payload, verify=False)
            if response.status_code == 200:
                print(f"✅ Sent successfully: {file_url}")
                print(response.content)
                success_count += 1
                file_urls.remove(file_url)
            else:
                print(f"❌ Failed: {file_url}, Status: {response.status_code}, Response: {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"❌ Request error: {file_url}, Error: {e}")

    with open(FILE_PATH, "w") as file:
        for url in file_urls:
            file.write(url + "\n")

    if success_count == len(file_urls):
        print("✅ All URLs sent successfully. File updated and emptied.")
    else:
        print(f"⚠️ {success_count} out of {len(file_urls)} URLs were successfully sent. File updated.")



def run_scraper():
    scraper = USCCourtScraper()
    scraper.run()
    send_file_urls()

# schedule.every().day.at("06:00").do(run_scraper)
run_scraper()
# <---------------->
# For test purpose comment the above line of code and uncomment the below lines of code.
# run_at_time = (datetime.now() + timedelta(minutes=1)).strftime("%H:%M")
# schedule.every().day.at(run_at_time).do(run_scraper)
# run_scraper()

# <----------------->
# while True:
#     schedule.run_pending()
#     time.sleep(60) 