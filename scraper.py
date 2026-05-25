# scraper.py
from enum import Enum
import itertools
import logging
import re
import time
import traceback
from datetime import datetime
from typing import List, Optional, Dict, Any
from urllib.parse import unquote, urlparse, parse_qs
from numpy import place
import requests
from numpy import place

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, ElementHandle
import asyncio

class ScrapeMode(Enum):
    SUMMARY = "summary"
    REVIEWS = "reviews"
    CONVERT = "convert"
    REKAPV2 = "rekapv2"

class LanguageDetector:
    """Deteksi bahasa Google Maps (ID/EN)"""
    
    INDONESIAN_KEYWORDS = [
        "Saring ulasan", "Semua", "Ulasan", "Lokasi", "Buka", "Tutup",
        "Tentang", "Foto", "Peta", "Jam operasional"
    ]
    
    ENGLISH_KEYWORDS = [
        "Filter reviews", "All", "Reviews", "About", "Photos", "Map",
        "Hours", "Rating", "Open", "Closed"
    ]
    
    @staticmethod
    def detect_language(html_content: str) -> str:
        """Detect bahasa dari HTML content"""
        id_count = sum(1 for kw in LanguageDetector.INDONESIAN_KEYWORDS if kw in html_content)
        en_count = sum(1 for kw in LanguageDetector.ENGLISH_KEYWORDS if kw in html_content)
        
        return "id" if id_count >= en_count else "en"



GM_WEBPAGE = 'https://www.google.com/maps/'
MAX_WAIT = 10000  # milliseconds
MAX_RETRY = 5
MAX_SCROLLS = 400

class GoogleMapsScraper:

    def __init__(self, debug=False):
        self.debug = debug
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.logger = self.__get_logger()
        self.__setup_browser()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is not None:
            traceback.print_exception(exc_type, exc_value, tb)

        self.close()
        return True

    def close(self):
        """Close browser and playwright instances"""
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def __setup_browser(self):
        """Setup Playwright browser instance"""
        self.playwright = sync_playwright().start()
        
        if self.debug:
            self.browser = self.playwright.chromium.launch(headless=False, args=["--window-size=1366,768"])
        else:
            self.browser = self.playwright.chromium.launch(headless=True)
        
        self.context = self.browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        self.page = self.context.new_page()
        #reload page to set user agent
        

    def sort_by(self, url: str, ind: int) -> int:
        """Sort reviews by criteria"""
        self.page.goto(url)
        self.__click_on_cookie_agreement()

        # Open dropdown menu
        clicked = False
        tries = 0
        while not clicked and tries < MAX_RETRY:
            try:
                menu_bt = self.page.wait_for_selector('button[data-value="Sort"]', timeout=MAX_WAIT)
                menu_bt.click()
                clicked = True
                time.sleep(3)
            except Exception as e:
                tries += 1
                self.logger.warn(f'Failed to click sorting button: {e}')

        if tries == MAX_RETRY:
            return -1

        # Select sorting option
        menu_items = self.page.query_selector_all('div[role="menuitemradio"]')
        if ind < len(menu_items):
            menu_items[ind].click()

        time.sleep(5)
        return 0

    def get_places(self, keyword_list: Optional[List[str]] = None) -> None:
        """Get places based on keywords"""
        df_places = pd.DataFrame()
        search_point_url_list = self._gen_search_points_from_square(keyword_list=keyword_list)

        for i, search_point_url in enumerate(search_point_url_list):

            if (i + 1) % 10 == 0:
                print(f"{i}/{len(search_point_url_list)}")
                df_places = df_places[['search_point_url', 'href', 'name', 'rating', 'num_reviews', 'close_time', 'other']]
                df_places.to_csv('output/places_wax.csv', index=False)

            try:
                self.page.goto(search_point_url)
            except Exception:
                self.close()
                self.__setup_browser()
                self.page.goto(search_point_url)

            # Scroll to load all places
            scrollable_div = self.page.wait_for_selector('div.m6QErb.DxyBCb.kA9KIf.dS8AEf.ecceSd > div[aria-label*="Results for"]')
            for _ in range(10):
                self.page.evaluate('(element) => { element.scrollTop = element.scrollHeight }', scrollable_div)

            # Get places names and href
            time.sleep(2)
            response = BeautifulSoup(self.page.content(), 'html.parser')
            div_places = response.select('div[jsaction] > a[href]')

            for div_place in div_places:
                place_info = {
                    'search_point_url': search_point_url.replace('https://www.google.com/maps/search/', ''),
                    'href': div_place['href'],
                    'name': div_place['aria-label']
                }
                df_places = pd.concat([df_places, pd.DataFrame([place_info])], ignore_index=True)

        df_places = df_places[['search_point_url', 'href', 'name']]
        df_places.to_csv('output/places_wax.csv', index=False)

    def get_reviews(self, offset: int, cab: str) -> List[Dict[str, Any]]:
        """Get reviews from current page"""
        self.page.reload()
        self.__click_on_cookie_agreement()
        # Scroll to load reviews
        self.__scroll()

        # Wait for other reviews to load
        time.sleep(4)

        # Expand review text
        self.__expand_reviews()

        # Parse reviews
        response = BeautifulSoup(self.page.content(), 'html.parser')
        rblock = response.find_all('div', class_='jftiEf fontBodyMedium')
        parsed_reviews = []
        
        for index, review in enumerate(rblock):
            if index >= offset:
                r = self.__parse(review, cab)
                parsed_reviews.append(r)
                #print(r)

        return parsed_reviews

    def get_account(self, url: str, cab: str) -> Dict[str, Any]:
        """Get account/place information"""
        self.page.goto(url)
        self.page.reload()
        self.__click_on_cookie_agreement()
        time.sleep(2)

        resp = BeautifulSoup(self.page.content(), 'html.parser')
        place_data = self.__parse_place(resp, url, cab)
        return place_data
    
    

    def __parse(self, review, cab) -> Dict[str, Any]:
        """Parse individual review"""
        item = {}

        try:
            kodecab = cab
        except:
            kodecab = None

        try:
            id_review = review['data-review-id']
        except:
            id_review = None

        try:
            username = review['aria-label']
        except:
            username = None

        try:
            review_text = self.__filter_string(review.find('span', class_='wiI7pd').text)
        except:
            review_text = None

        try:
            rating = float(review.find('span', class_='kvMYJc')['aria-label'].split(' ')[0])
        except:
            rating = None

        try:
            relative_date = review.find('span', class_='rsqaWe').text
        except:
            relative_date = None

        try:
            n_reviews = review.find('div', class_='RfnDt').text.split(' ')[3]
        except:
            n_reviews = 0

        try:
            user_url = review.find('button', class_='WEBjve')['data-href']
        except:
            user_url = None

        try:
            resp = BeautifulSoup(self.page.content(), 'html.parser')
            raw_title = resp.find("title").text.strip()

            # Hilangkan "- Google Maps"
            name = re.sub(r"\s*-\s*Google Maps\s*$", "", raw_title, flags=re.IGNORECASE)

            # Ganti spasi dengan underscore
            name = name.replace(" ", "_")

            # Bersihkan karakter aneh (kecuali _ dan alfanumerik)
            name = re.sub(r"[^a-zA-Z0-9_]", "", name)

            item["name"] = name
        except:
            item["name"] = None

        item['kode_cabang'] = kodecab
        item['id_review'] = id_review
        item['caption'] = review_text
        item['relative_date'] = relative_date
        item['retrieval_date'] = datetime.now()
        item['rating'] = rating
        item['username'] = username
        item['n_review_user'] = n_reviews
        item['url_user'] = user_url
        item['url_place'] = self.page.url

        return item
    
    def get_review_categories_summary(self) -> dict:
        """
        Ambil jumlah review per kategori dari Google Maps (support ID & EN)
        """
        TARGET_CATEGORIES = {
            "pelayanan", "angsuran", "pengiriman", "proses", "stnk", "bpkb", "kasir",
        }
        
        time.sleep(2)
        soup = BeautifulSoup(self.page.content(), "html.parser")
        
        # Try detect language
        page_text = soup.get_text()
        is_indonesian = "Saring ulasan" in page_text or "pelayanan" in page_text
        
        # Try both ID and EN selectors
        filter_label_id = 'div[aria-label="Saring ulasan"]'
        filter_label_en = 'div[aria-label="Filter reviews"]'
        
        buttons = soup.select(f'{filter_label_id} button[role="radio"]')
        
        if not buttons:
            buttons = soup.select(f'{filter_label_en} button[role="radio"]')

        result = {k: 0 for k in TARGET_CATEGORIES}
        result["lain_lain"] = 0

        for btn in buttons:
            name_el = btn.select_one("span.uEubGf")
            count_el = btn.select_one("span.bC3Nkc")

            if not name_el or not count_el:
                continue

            name = name_el.text.strip().lower()
            try:
                count = int(count_el.text.strip().replace(".", "").replace(",", ""))
            except ValueError:
                count = 0

            if name in TARGET_CATEGORIES:
                result[name] += count
            else:
                result["lain_lain"] += count

        return result


    def __parse_place(self, response, url: str, cab: str) -> Dict[str, Any]:
        """Parse place information"""
        place = {}

        try:
            raw_title = response.find("title").text.strip()

            # Hilangkan "- Google Maps"
            name = re.sub(r"\s*-\s*Google Maps\s*$", "", raw_title, flags=re.IGNORECASE)

            # Ganti spasi dengan underscore
            name = name.replace(" ", "_")

            # Bersihkan karakter aneh (kecuali _ dan alfanumerik)
            name = re.sub(r"[^a-zA-Z0-9_]", "", name)

            place["name"] = name
        except:
            place["name"] = None

        try:
            place["kode_cabang"] = cab
            print(f"Cabang 1: {cab}")
        except:
            place["kode_cabang"] = None

        try:
            rating_text = response.select_one("div.jANrlb div.fontDisplayLarge")
            place['overall_rating'] = float(
                rating_text.text.replace(",", ".")
            ) if rating_text else None
        except:
            place['overall_rating'] = None

        try:
            review_text = response.select_one("div.jANrlb div.HHrUdb span").text
            place['n_reviews'] = int(
                review_text
                .replace(" ulasan", "")
                .replace(".", "")
            ) if review_text else None
        except:
            place['n_reviews'] = None

        try:
            pelayanan_text = response.select_one("div.jANrlb div.fontBodySmall").text
            place['service_rating'] = float(pelayanan_text)
        except:
            place['service_rating'] = None



        try:
            n_photos_text = response.find('div', class_='YkuOqf').text
            place['n_photos'] = int(re.sub(r'[^\d]', '', n_photos_text.split(' ')[0]))
        except:
            place['n_photos'] = 0

        try:
            place['category'] = response.find('button', jsaction='pane.rating.category').text.strip()
        except:
            place['category'] = None

        try:
            place['description'] = response.find('div', class_='PYvSYb').text.strip()
        except:
            place['description'] = None

        b_list = response.find_all('div', class_='Io6YTe fontBodyMedium')
        try:
            place['address'] = b_list[0].text
        except:
            place['address'] = None

        try:
            place['website'] = b_list[1].text
        except:
            place['website'] = None

        try:
            place['phone_number'] = b_list[2].text
        except:
            place['phone_number'] = None
    
        try:
            place['plus_code'] = b_list[3].text
        except:
            place['plus_code'] = None

        try:
            opening_hours_element = response.find('div', class_='t39EBf GUrTXd')
            if opening_hours_element and 'aria-label' in opening_hours_element.attrs:
                place['opening_hours'] = opening_hours_element['aria-label'].replace('\u202f', ' ')
            else:
                place['opening_hours'] = None
        except:
            place['opening_hours'] = None


        category_summary = self.get_review_categories_summary()
        place['pelayanan_count'] = category_summary.get('pelayanan', 0)
        place['angsuran_count'] = category_summary.get('angsuran', 0)
        place['pengiriman_count'] = category_summary.get('pengiriman', 0)
        place['proses_count'] = category_summary.get('proses', 0)
        place['stnk_count'] = category_summary.get('stnk', 0)
        place['bpkb_count'] = category_summary.get('bpkb', 0)
        place['kasir_count'] = category_summary.get('kasir', 0)
        place['lain_lain_count'] = category_summary.get('lain_lain', 0)

        place['url'] = url

        try:
            url_parts = url.split('/')
            if len(url_parts) > 6:
                coords = url_parts[6].split(',')
                place['lat'] = coords[0][1:] if coords[0].startswith('@') else coords[0]
                place['long'] = coords[1]
            else:
                place['lat'] = None
                place['long'] = None
        except:
            place['lat'] = None
            place['long'] = None

        return place
    
    def get_rekap_info(self, url: str, cab: str) -> Dict[str, Any]:
        """ AMBIL INFORMASI PLACE SEPERTI LINK GAMBAR, LINK MAP, LINK WEBSITE, DLL (REKAP V2) """
        self.page.goto(url)
        self.page.reload()
        self.__click_on_cookie_agreement()
        time.sleep(2)

        resp = BeautifulSoup(self.page.content(), 'html.parser')
        place_data = self.__get_info_rekap(resp, url, cab)
        return place_data
    
    def __get_info_rekap(self, response, url: str, cab: str) -> Dict[str, Any]:
        """Parse place information untuk rekap v2 (gabungan summary + reviews)"""
        place = {}
        try:
            place["kode_cabang"] = cab
        except:
            place["kode_cabang"] = None

        try:
            raw_title = response.find("title").text.strip()

            name = re.sub(r"\s*-\s*Google Maps\s*$", "", raw_title, flags=re.IGNORECASE)

            name = re.sub(r"[^a-zA-Z0-9\s]", "", name)

            place["name"] = name.strip()

        except:
            place["name"] = None

        try:
            """ AMBIL EMAIL TEMPAT (JIKA ADA) """
            place["email"] = response.find('a', jsaction='pane.rating.email').text.strip()
        except:
            place["email"] = None

        try:
            place["link_tree"] = parse_qs(urlparse(response.find('a', attrs={'data-item-id': 'services'})['href']).query).get('q', [None])[0]
        except:
            place["link_tree"] = None

        """ AMBIL JAM OPRASIONAL (FORMAT LEBIH RAPIH) """
        try:
            row = response.find_all('tr', class_='y0skZc')[datetime.now().weekday()]
            jam = row.find('td', class_='mxowUb')['aria-label'].split(',')[0]

            start, end = jam.split(' hingga ')

            place['jamopr'] = f"{datetime.strptime(start,'%H.%M').strftime('%-I.%M %p').lower()}-{datetime.strptime(end,'%H.%M').strftime('%-I.%M %p').lower()}"

        except:
            place['jamopr'] = None

        """ AMBIL TITIK LOKASI LINK GMAPS dan  """
        try:
            gen_cid = re.search(r'0x[a-f0-9]+:0x([a-f0-9]+)', url)
            if gen_cid:
                place['titiklokasi'] = "https://www.google.com/maps?cid=" + str(int(gen_cid.group(1), 16))
            else:
                place['titiklokasi'] = url
            
            
            
        except:
            place['titiklokasi'] = None

        """ AMBIL NO TELEPON TEMPAT """
        try:
            place['notelp'] = response.find('button', attrs={'data-item-id': lambda x: x and x.startswith('phone:tel:')})['data-item-id'].replace('phone:tel:', '')
        except:
            place['notelp'] = None

        """ AMBIL LINK WEBSITE TEMPAT """
        try:
            place['situsweb'] = parse_qs(urlparse(response.find('a', attrs={'data-item-id': 'authority'})['href']).query).get('q', [None])[0]
        except:
            place['situsweb'] = None

        try:

            place["link"] = None
        except:
            place["link"] = None

        """ AMBIL TOTAL ULASAN TEMPAT """
        try:
            place["totulasan"] = int(re.search(r'[\d\.]+', response.find('button', attrs={'jsaction':'pane.wfvdle14.reviewChart.moreReviews'}).text).group().replace('.', ''))
        except:
            place["totulasan"] = None

        try:
            place["totbalasan"] = response.find('span', jsaction='pane.wfvdle14.reviewChart.moreReviews').text.strip()
        except:
            place["totbalasan"] = None

        """ AMBIL RATING TEMPAT """
        try:
            place["rating"] = float(response.find('div', class_='fontDisplayLarge').text.strip().replace(',', '.'))
        except:
            place["rating"] = None

        """ AMBIL LINK GAMBAR TEMPAT """
        try:
            place["image_link"] = response.select_one('button[jsaction*="heroHeaderImage"] img')['src']
        except:
            place["image_link"] = None

        """ BUAT FIELD tglUpd tgl sekarang format dd-mm-yyyy"""
        place["tglUpd"] = datetime.now().strftime("%d-%m-%Y")
    
        """ BUAT FIELD jamUpd tgl sekarang """
        place["jamUpd"] = datetime.now().strftime("%H:%M:%S")
        return place
    
    def scrape(
        self,
        url: str,
        cab: str,
        mode: ScrapeMode,
        fields: Optional[List[str]] = None,
        review_offset: int = 0
    ):
        """
        Scrape with auto URL detection and conversion if needed.
        
        For REVIEWS mode: Automatically converts short/normal URLs to reviews section
        For SUMMARY mode: Uses URL as-is
        """
        # Auto-process URL (convert if needed for reviews mode)
        processed_url = self._auto_process_url(url, mode)
        
        if mode == ScrapeMode.SUMMARY:
            data = self.get_account(processed_url, cab)
            print(f"Cabang: {cab}")
            self.__click_reviews_tab()
            return self._filter_fields(data, fields)

        elif mode == ScrapeMode.REVIEWS:
            self.page.goto(processed_url)
            self.page.reload()
            self.__click_on_cookie_agreement()
            # Click review button jika belum di reviews section
            self.__click_reviews_tab()
            reviews = self.get_reviews(review_offset, cab)
            return self._filter_review_fields(reviews, fields)

        elif mode == ScrapeMode.REKAPV2:
            data = self.get_rekap_info(processed_url, cab)
            print(f"Cabang: {cab}")
            return self._filter_fields(data, fields)

        else:
            raise ValueError(f"Mode tidak valid: {mode}")
    
    def _auto_process_url(self, url: str, mode: ScrapeMode) -> str:
        """
        Auto-detect dan convert URL jika diperlukan.
        
        Untuk REVIEWS mode:
        - Jika URL sudah pointing ke /reviews → gunakan as-is
        - Jika URL adalah short URL atau normal place URL → convert ke reviews
        
        Untuk SUMMARY mode:
        - Gunakan URL as-is (summary bisa dari URL apapun)
        """
        
        return url

    def _filter_fields(self, data: Dict[str, Any], fields: Optional[List[str]]):
        if not fields:
            return data
        return {f: data.get(f) for f in fields}

    def _filter_review_fields(self, reviews: List[Dict[str, Any]], fields: Optional[List[str]]):
        if not fields:
            return reviews
        return [{f: r.get(f) for f in fields} for r in reviews]

    def _gen_search_points_from_square(self, keyword_list: Optional[List[str]] = None) -> List[str]:
        """Generate search points from square coordinates"""
        keyword_list = [] if keyword_list is None else keyword_list

        # This would normally read from a CSV file
        # square_points = pd.read_csv('input/square_points.csv')
        # For demonstration, returning empty list
        return []

    def __expand_reviews(self) -> None:
        """Expand review descriptions"""
        buttons = self.page.query_selector_all('button.w8nwRe.kyuRq')
        for button in buttons:
            button.click()

    def __scroll(self, max_scrolls: int = 40, delay: float = 2.0) -> None:
        """Scroll to load more reviews until max_scrolls or no more new content"""
        try:
            scrollable_div = self.page.wait_for_selector(
                'div.m6QErb.DxyBCb.kA9KIf.dS8AEf',
                timeout=MAX_WAIT
            )
            last_height = 0

            for i in range(max_scrolls):
                self.page.evaluate('(element) => { element.scrollTop = element.scrollHeight }', scrollable_div)
                time.sleep(delay)

                # cek apakah masih ada review baru
                new_height = self.page.evaluate('(element) => element.scrollTop', scrollable_div)
                if new_height == last_height:
                    print(f"Scroll berhenti di {i+1} kali, sudah tidak ada review baru.")
                    break
                last_height = new_height
        except Exception as e:
            self.logger.error(f"Gagal scroll: {e}")

    def __get_logger(self) -> logging.Logger:
        """Setup logger"""
        logger = logging.getLogger('googlemaps-scraper')
        logger.setLevel(logging.DEBUG)

        fh = logging.FileHandler('gm-scraper.log')
        fh.setLevel(logging.DEBUG)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)

        logger.addHandler(fh)
        return logger

    def __click_reviews_tab(self) -> bool:
        """
        Click on reviews/ulasan tab jika belum di reviews section
        Handles both Indonesian dan English interface
        """
        try:
            # Wait for page to load
            time.sleep(2)
            
            # Check if we're already in reviews section
            soup = BeautifulSoup(self.page.content(), "html.parser")
            page_text = soup.get_text()
            
            # Cek kalau sudah di reviews section
            if "Ulasan" in page_text or "Reviews" in page_text:
                # Try to find dan klik reviews tab
                # Method 1: Click by aria-label "Ulasan" (Indonesian)
                try:
                    reviews_button = self.page.query_selector('[role="tablist"][aria-label*="Ulasan"]')
                    if reviews_button:
                        print("[CLICK] Clicking 'Ulasan' tab...")
                        reviews_button.click()
                        time.sleep(3)
                        return True
                except:
                    pass
                
                # Method 2: Click by aria-label "Reviews" (English)
                try:
                    reviews_button = self.page.query_selector('[role="tab"][aria-label*="Review"]')
                    if reviews_button:
                        print("[CLICK] Clicking 'Reviews' tab...")
                        reviews_button.click()
                        time.sleep(3)
                        return True
                except:
                    pass
                
                # Method 3: Find tab button containing review-related text
                try:
                    tabs = self.page.query_selector_all('[role="tab"]')
                    for tab in tabs:
                        aria_label = tab.get_attribute('aria-label') or ''
                        if 'ulasan' in aria_label.lower() or 'review' in aria_label.lower():
                            print(f"[CLICK] Clicking tab: {aria_label}")
                            tab.click()
                            time.sleep(3)
                            return True
                except:
                    pass
                
                # Method 4: Try clicking by button text content
                try:
                    buttons = self.page.query_selector_all('button')
                    for btn in buttons:
                        text_content = btn.text_content() or ''
                        if 'ulasan' in text_content.lower() or 'review' in text_content.lower():
                            if 'saring' not in text_content.lower():  # Jangan klik filter button
                                print(f"[CLICK] Clicking button with text: {text_content[:20]}")
                                btn.click()
                                time.sleep(3)
                                return True
                except:
                    pass
        
        except Exception as e:
            print(f"[WARN] Failed to click reviews tab: {e}")
            return False
        
        print("[INFO] Reviews section might already be loaded")
        return True
    
    def __click_on_cookie_agreement(self) -> bool:
        """Handle cookie agreement popup (Support ID & EN)"""
        try:
            # Try English: "Reject all"
            reject_button = self.page.wait_for_selector('//span[contains(text(), "Reject all")]', timeout=5000)
            if reject_button:
                reject_button.click()
                return True
        except:
            pass
        
        try:
            # Try Indonesian: "Tolak semua"
            reject_button = self.page.wait_for_selector('//span[contains(text(), "Tolak semua")]', timeout=5000)
            if reject_button:
                reject_button.click()
                return True
        except:
            pass
        
        try:
            # Try generic button with data-testid
            reject_button = self.page.wait_for_selector('button[aria-label*="egect"]', timeout=3000)
            if reject_button:
                reject_button.click()
                return True
        except:
            pass
        
        return False

    def __filter_string(self, text: str) -> str:
        """Clean special characters from string"""
        return text.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')

    

def extract_name_from_url(url: str) -> str:
    """Extract place name from Google Maps URL"""
    match = re.search(r'/place/([^/]+)', url)
    if match:
        raw_name = match.group(1)
    else:
        raw_name = "unknown_place"
    
    decoded = unquote(raw_name)
    safe_name = re.sub(r'[^a-zA-Z0-9_\- ]', '_', decoded)
    safe_name = safe_name[:50]
    
    return safe_name.strip("_")





def scrape_google_maps_reviews(url: str):
    """Main function to scrape Google Maps reviews"""
    with GoogleMapsScraper(debug=True) as scraper:
        place_data = scraper.get_account(url)
        reviews = scraper.get_reviews(0)

        print(f"Found {len(reviews)} reviews")

        if reviews:
            df = pd.DataFrame(reviews)
            place_name_from_url = extract_name_from_url(url)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            filename = f"{place_name_from_url}_reviews_{timestamp}.csv"

            df.to_csv(
                filename,
                index=False,
                sep="|",
                encoding="utf-8-sig"
            )

            print(f"Data berhasil disimpan dalam file: {filename}")
        else:
            print("Tidak ada review yang ditemukan.")   

    return reviews
