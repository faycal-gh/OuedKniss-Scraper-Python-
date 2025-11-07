import tkinter as tk
from tkinter import *
from tkinter import messagebox as mb
from tkinter import ttk
import sys
from bs4 import BeautifulSoup
import sqlite3
import time
import threading
import re
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
BASE_URL = "https://www.ouedkniss.com"
CATEGORY_PATH = "telephones-smartphones"
stop_event = threading.Event()
stop_button = None
total_phones_entry = None
scraping_thread = None
def ensure_schema(cursor):
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS data(
        name varchar(255),
        price varchar(255),
        phone varchar(255),
        normalized_phone varchar(255),
        username varchar(255)
    )''')
    existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(data)")}
    if "normalized_phone" not in existing_columns:
        cursor.execute("ALTER TABLE data ADD COLUMN normalized_phone varchar(255)")
    if "username" not in existing_columns:
        cursor.execute("ALTER TABLE data ADD COLUMN username varchar(255)")
    index_names = {row[1] for row in cursor.execute("PRAGMA index_list(data)")}
    if "idx_data_normalized_phone" in index_names:
        cursor.execute("DROP INDEX idx_data_normalized_phone")
    if "idx_data_phone_name_price" not in index_names:
        cursor.execute("CREATE UNIQUE INDEX idx_data_phone_name_price ON data(normalized_phone, name, price)")
def clear_database():
    try:
        with sqlite3.connect('ouedkniss.db') as local_conn:
            local_cursor = local_conn.cursor()
            ensure_schema(local_cursor)
            local_cursor.execute("DELETE FROM data")
            local_conn.commit()
    except sqlite3.Error as err:
        print(f"Error clearing database: {err}")
def create_TreeView(parent):
    global tv
    tv = ttk.Treeview(parent, columns=("name", "price", "phone", "username"), show="headings", height="20")
    vsb = ttk.Scrollbar(parent, orient="vertical", command=tv.yview)
    hsb = ttk.Scrollbar(parent, orient="horizontal", command=tv.xview)
    tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    vsb.pack(side='right', fill='y')
    hsb.pack(side='bottom', fill='x')
    tv.pack(side='left', fill='both', expand=True)
    tv.heading("name", text="Name")
    tv.heading("price", text="Price")
    tv.heading("phone", text="Phone")
    tv.heading("username", text="User")
    tv.column("name", width=220, anchor='w')
    tv.column("price", width=100, anchor='w')
    tv.column("phone", width=140, anchor='w')
    tv.column("username", width=140, anchor='w')
def clicked():
    global scraping_thread
    if scraping_thread and scraping_thread.is_alive():
        mb.showinfo(title='Info', message="Scraping is already running. Click Stop to end it first.")
        return
    if not total_phones_entry:
        mb.showerror(title='Error', message="Input field is not ready yet. Please retry.")
        return
    total_value = total_phones_entry.get().strip()
    if not total_value or not total_value.isdigit():
        mb.showinfo(title='Warning', message="Please enter a valid number of phones to scrape.")
        return
    total_needed = int(total_value)
    if total_needed < 1:
        mb.showinfo(title='Warning', message="Number of phones must be at least 1.")
        return
    tv.delete(*tv.get_children())
    stop_event.clear()
    scrap_button.config(state='disabled')
    stop_button.config(state='normal')
    scraping_thread = threading.Thread(target=get_phones, args=(total_needed,), daemon=True)
    scraping_thread.start()
def clearAll():
    if scraping_thread and scraping_thread.is_alive():
        stop_scraping()
    if total_phones_entry:
        total_phones_entry.delete(0, END)
    tv.delete(*tv.get_children())
    clear_database()
    if total_phones_entry:
        total_phones_entry.focus_set()
def number_only(text):
    if str.isdigit(text) or text == '':
        return True
    else:
        return False
def connect():    
    global conn, c
    conn = sqlite3.connect('ouedkniss.db', timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    c = conn.cursor()
    ensure_schema(c)
    conn.commit()
def createTable():
    ensure_schema(c)
    conn.commit()
def dropTable():
    delete_query = "DROP TABLE data"
    c.execute(delete_query)
def insertData(name, price, phone, normalized_phone, username):
    inserting_query = "INSERT OR IGNORE INTO data (name,price,phone,normalized_phone,username) VALUES (?, ?, ?, ?, ?)"
    c.execute(inserting_query, (name, price, phone, normalized_phone, username))
    return c.rowcount > 0
def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/chromium"
    service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)
    return driver
def load_page(driver, url, css_selector, timeout=12):
    if stop_event.is_set():
        return False
    try:
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
        )
        return True
    except TimeoutException:
        print(f"Timeout while loading {url}")
    except Exception as e:
        print(f"Error loading {url}: {e}")
    return False
def fetch_phone_number(driver, url, timeout=15, max_retries=2):
    if stop_event.is_set():
        return "Unavailable"
    def extract_tel_from_source():
        detail_soup = BeautifulSoup(driver.page_source, features="lxml")
        dialogs = detail_soup.find_all(['div'], class_=lambda c: c and ('dialog' in c.lower() or 'popup' in c.lower() or 'ok-dialog' in c))
        for dialog in dialogs:
            phone_link = dialog.find('a', href=lambda href: href and href.startswith('tel:'))
            if phone_link:
                phone_text = phone_link.get_text(strip=True)
                if phone_text:
                    return phone_text
                href_value = phone_link.get("href", "")
                return href_value.replace('tel:', '').strip()
        phone_link = detail_soup.find('a', href=lambda href: href and href.startswith('tel:'))
        if phone_link:
            phone_text = phone_link.get_text(strip=True)
            if phone_text:
                return phone_text
            href_value = phone_link.get("href", "")
            return href_value.replace('tel:', '').strip()
        return ""
    for attempt in range(max_retries + 1):
        if stop_event.is_set():
            break
        try:
            driver.get(url)
            try:
                WebDriverWait(driver, timeout).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except TimeoutException:
                pass
            appeler_clicked = False
            try:
                appeler_selectors = [
                    'button[aria-label="Appeler"]',
                    'div[aria-label="Appeler"] button',
                    'button.v-btn.ok-btn:has(.mdi-phone)',
                    'button:has(span:contains("Appeler"))',
                ]
                appeler_button = None
                for selector in appeler_selectors:
                    try:
                        appeler_button = WebDriverWait(driver, 3).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        break
                    except:
                        continue
                if not appeler_button:
                    buttons = driver.find_elements(By.TAG_NAME, 'button')
                    for btn in buttons:
                        try:
                            btn_html = btn.get_attribute('innerHTML') or ''
                            btn_text = btn.text.lower()
                            if ('appeler' in btn_text or 
                                'mdi-phone' in btn_html or 
                                'v-icon--phone' in btn_html or
                                btn.get_attribute('aria-label') == 'Appeler'):
                                appeler_button = btn
                                break
                        except:
                            continue
                if not appeler_button:
                    try:
                        appeler_button = driver.find_element(By.XPATH, 
                            "//button[contains(@class, 'ok-btn') and .//i[contains(@class, 'mdi-phone')]]")
                    except:
                        pass
                if appeler_button:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", appeler_button)
                    time.sleep(0.4)
                    try:
                        if appeler_button.is_displayed() and appeler_button.is_enabled():
                            appeler_button.click()
                        else:
                            driver.execute_script("arguments[0].click();", appeler_button)
                        appeler_clicked = True
                        print(f"Clicked 'Appeler' button on {url}")
                    except Exception as click_err:
                        driver.execute_script("arguments[0].click();", appeler_button)
                        appeler_clicked = True
                        print(f"Force-clicked 'Appeler' button on {url}")
                    time.sleep(1.5)
                else:
                    print(f"No 'Appeler' button found on {url}, trying fallback methods")
            except TimeoutException:
                print(f"No 'Appeler' button found on {url}, trying fallback methods")
            except Exception as e:
                print(f"Error clicking 'Appeler' button on {url}: {e}")
            if appeler_clicked:
                try:
                    WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href^="tel:"]'))
                    )
                except TimeoutException:
                    try:
                        WebDriverWait(driver, 3).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[class*="ok-dialog"], div[role="dialog"]'))
                        )
                    except:
                        pass
                revealed_phone = extract_tel_from_source()
                if revealed_phone:
                    return revealed_phone
            direct_phone = extract_tel_from_source()
            if direct_phone:
                return direct_phone
            reveal_keywords = ("afficher", "voir", "num", "tel", "télé", "show", "display", "appeler")
            clickable_elements = driver.find_elements(By.CSS_SELECTOR, 'button, a')
            clicked = False
            for element in clickable_elements:
                try:
                    text_value = element.text.strip().lower()
                except Exception:
                    text_value = ""
                if not text_value:
                    continue
                if any(keyword in text_value for keyword in reveal_keywords):
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    except Exception:
                        pass
                    try:
                        if element.is_displayed() and element.is_enabled():
                            element.click()
                        else:
                            driver.execute_script("arguments[0].click();", element)
                        clicked = True
                        time.sleep(0.8)
                        break
                    except Exception:
                        continue
            if clicked:
                try:
                    WebDriverWait(driver, 6).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href^="tel:"]'))
                    )
                except TimeoutException:
                    pass
                revealed_phone = extract_tel_from_source()
                if revealed_phone:
                    return revealed_phone
            try:
                soup = BeautifulSoup(driver.page_source, "lxml")
                for script in soup(["script", "style", "meta", "noscript"]):
                    script.decompose()
                visible_text = soup.get_text()
                phone_patterns = [
                    r'\b(0\d{3}[\s\-]?\d{2}[\s\-]?\d{2}[\s\-]?\d{2})\b',
                    r'\b(\+213[\s\-]?\d{1,3}[\s\-]?\d{2}[\s\-]?\d{2}[\s\-]?\d{2})\b',
                    r'\b(00213[\s\-]?\d{1,3}[\s\-]?\d{2}[\s\-]?\d{2}[\s\-]?\d{2})\b',
                ]
                for pattern in phone_patterns:
                    match = re.search(pattern, visible_text)
                    if match:
                        candidate = match.group(1).strip()
                        if '655958734553123' not in candidate and len(candidate.replace(' ', '').replace('-', '')) >= 9:
                            return candidate
            except Exception:
                pass
        except Exception as e:
            print(f"Error fetching phone number on {url} attempt {attempt}: {e}")
        time.sleep(1 + attempt * 1.5)
    print(f"Unable to extract phone number for {url}")
    return "Unavailable"
def normalize_phone(phone_value):
    if not phone_value or phone_value == "Unavailable" or phone_value == "0":
        return ""
    blacklist = ['655958734553123']
    if any(bad in phone_value for bad in blacklist):
        return ""
    digits = ''.join(ch for ch in phone_value if ch.isdigit() or ch == '+')
    if not digits:
        return ""
    if digits in blacklist or digits.replace('+', '') in blacklist:
        return ""
    if digits[0] == '+':
        candidate = digits
    elif digits.startswith('00') and len(digits) > 2:
        candidate = '+' + digits[2:]
    elif digits.startswith('213') and len(digits) >= 9:
        candidate = '+' + digits
    elif digits.startswith('0') and len(digits) >= 9:
        candidate = '+213' + digits[1:]
    else:
        candidate = digits
    digit_count = sum(ch.isdigit() for ch in candidate)
    if digit_count < 9 or digit_count > 13:
        return ""
    if candidate.startswith('+213'):
        local_part = candidate[4:]
        if local_part and local_part[0] not in ['5', '6', '7']:
            pass
    elif candidate.startswith('0'):
        if candidate[1] not in ['5', '6', '7']:
            pass
    return candidate
def get_phones(total_needed):
    connect()
    createTable()
    c.execute("DELETE FROM data")
    conn.commit()
    list_driver = create_driver()
    detail_driver = create_driver()
    total_scraped = 0
    seen_entries = set()
    seen_links = set()
    page_number = 1
    try:
        while not stop_event.is_set() and total_scraped < total_needed:
            page_url = f"{BASE_URL}/{CATEGORY_PATH}/{page_number}"
            print(f"======= page No: {page_number} =======")
            if not load_page(list_driver, page_url, 'div.v-row.v-row--dense div.o-announ-card'):
                break
            soup = BeautifulSoup(list_driver.page_source, features="lxml")
            annonces = soup.select('div.v-row.v-row--dense div.o-announ-card')
            print(f"Found {len(annonces)} announcements on this page")
            if not annonces:
                print(f"No announcements found on page {page_number}. Stopping.")
                break
            for annonce in annonces:
                if stop_event.is_set() or total_scraped >= total_needed:
                    break
                title_element = annonce.find('h3', class_='o-announ-card-title')
                price_element = annonce.find('span', class_='price')
                link_element = annonce.find('a', href=True)
                if not (title_element and price_element and link_element):
                    continue
                title_text = ' '.join(title_element.get_text(separator=' ', strip=True).split())
                price_div = price_element.find('div', dir='ltr')
                if price_div:
                    price_value = price_div.text.strip()
                    price_text = f"{price_value} DA"
                else:
                    price_text = price_element.get_text(separator=' ', strip=True)
                detail_href = link_element.get('href', '')
                detail_url = urljoin(BASE_URL, detail_href)
                if detail_url in seen_links:
                    print(f"Skipping duplicate listing URL: {detail_url}")
                    continue
                seen_links.add(detail_url)
                phone_number = fetch_phone_number(detail_driver, detail_url) if detail_url else "0"
                if phone_number == "Unavailable" or not phone_number:
                    phone_number = "0"
                    normalized_phone = "0"
                else:
                    normalized_phone = normalize_phone(phone_number)
                    if not normalized_phone:
                        phone_number = "0"
                        normalized_phone = "0"
                username_element = annonce.select_one('div.text-capitalize.font-weight-bold.ms-2')
                if username_element:
                    username_text = username_element.get_text(separator=' ', strip=True)
                else:
                    username_text = 'Unknown'
                entry_key = (normalized_phone, title_text, price_text)
                if entry_key in seen_entries:
                    print(f"Skipping duplicate entry: {title_text} | {price_text} | {phone_number}")
                    continue
                inserted = insertData(title_text, price_text, phone_number, normalized_phone, username_text)
                seen_entries.add(entry_key)
                if inserted:
                    conn.commit()
                    total_scraped += 1
                    print(f"Scraped: {title_text} | {price_text} | {phone_number}")
                    def append_row(name=title_text, price=price_text, phone=phone_number, user=username_text):
                        tv.insert('', 'end', values=(name, price, phone, user))
                    win.after(0, append_row)
                else:
                    print(f"Entry already stored: {title_text} | {price_text} | {phone_number}")
                if total_scraped >= total_needed:
                    break
            page_number += 1
    finally:
        stop_event.clear()
        try:
            list_driver.quit()
        except Exception:
            pass
        try:
            detail_driver.quit()
        except Exception:
            pass
        conn.commit()
        conn.close()
        print(f"Total unique phones scraped: {total_scraped}/{total_needed}")
        if total_scraped < total_needed:
            print(f"Could not reach requested total. Missing {total_needed - total_scraped} unique phones.")
        win.after(0, on_scrape_finished)
def stop_scraping():
    if not stop_event.is_set():
        stop_event.set()
    if 'stop_button' in globals() and stop_button:
        stop_button.config(state='disabled')
def on_scrape_finished():
    global scraping_thread
    if 'scrap_button' in globals() and scrap_button:
        scrap_button.config(state='normal')
    if 'stop_button' in globals() and stop_button:
        stop_button.config(state='disabled')
    scraping_thread = None
win = Tk()
win.title("OuedKniss Scraper")
win.geometry('800x500')
style = ttk.Style(win)
style.theme_use("clam")
main_frame = ttk.Frame(win, padding="10")
main_frame.pack(fill='both', expand=True)
tree_frame = ttk.Frame(main_frame)
tree_frame.pack(fill='both', expand=True, side='left', padx=(0, 10))
create_TreeView(tree_frame)
controls_frame = ttk.Frame(main_frame, padding="10")
controls_frame.pack(side='right', fill='y')
reg_fun = win.register(number_only)
ttk.Label(controls_frame, text="Number of Phones:").pack(pady=(0,5), anchor='w')
total_phones_entry = ttk.Entry(controls_frame, validate="key", validatecommand=(reg_fun, '%P'))
total_phones_entry.pack(pady=5, fill='x')
total_phones_entry.focus()
scrap_button = ttk.Button(controls_frame, text="Scrap Now", command=clicked)
scrap_button.pack(pady=10, fill='x')
stop_button = ttk.Button(controls_frame, text="Stop", command=stop_scraping, state='disabled')
stop_button.pack(pady=5, fill='x')
clear_button = ttk.Button(controls_frame, text="Clear All", command=clearAll)
clear_button.pack(pady=5, fill='x')
win.resizable(True, True)
win.mainloop()