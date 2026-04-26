from flask import Flask, render_template, request, jsonify, send_file
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import json
import time
import random
import io
import os
from datetime import datetime
from urllib.parse import urlparse, urljoin
import urllib.parse

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# ─────────────────────────────────────────────
# BOOKING.COM SCRAPER
# ─────────────────────────────────────────────
import json
import re
import time
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def scrape_booking(url):
    hotel_data = {}
    reviews = []

    from playwright.sync_api import sync_playwright
    import time, json, re
    from bs4 import BeautifulSoup

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            )
            page = context.new_page()

            page.goto(url, timeout=60000)
            page.wait_for_selector("h1, h2", timeout=30000)
            time.sleep(3)

            # scroll
            for _ in range(5):
                page.mouse.wheel(0, 2000)
                time.sleep(1)

            # =====================
            # HOTEL BASIC
            # =====================
            hotel_data["hotel_name"] = page.locator("h1, h2").first.inner_text() or "N/A"

            # address
            try:
                hotel_data["address"] = page.locator('[data-testid="address"]').inner_text()
            except:
                hotel_data["address"] = "N/A"

            # star rating
            try:
                hotel_data["star_rating"] = page.locator('[aria-label*="star"]').first.get_attribute("aria-label")
            except:
                hotel_data["star_rating"] = "N/A"

            # score + review count
            try:
                score_block = page.locator('[data-testid="review-score-component"]')
                hotel_data["overall_score"] = score_block.inner_text()
                hotel_data["review_count"] = score_block.inner_text()
            except:
                hotel_data["overall_score"] = "N/A"
                hotel_data["review_count"] = "N/A"

            # amenities
            try:
                amenities = page.locator('[data-testid="property-most-popular-facilities"] div').all_inner_texts()
                hotel_data["amenities"] = ", ".join(amenities[:20])
            except:
                hotel_data["amenities"] = "N/A"

            # photos
            try:
                imgs = page.locator("img").all()
                links = []
                for img in imgs:
                    src = img.get_attribute("src")
                    if src and "bstatic" in src:
                        links.append(src)
                hotel_data["photo_links"] = " | ".join(list(set(links))[:10])
            except:
                hotel_data["photo_links"] = "N/A"

            # =====================
            # JSON-LD (geo + email)
            # =====================
            soup = BeautifulSoup(page.content(), "html.parser")

            hotel_data["latitude"] = "N/A"
            hotel_data["longitude"] = "N/A"
            hotel_data["hotel_email"] = "N/A"

            for sc in soup.find_all("script", {"type": "application/ld+json"}):
                try:
                    data = json.loads(sc.string or "")
                    geo = data.get("geo", {})
                    hotel_data["latitude"] = geo.get("latitude", "N/A")
                    hotel_data["longitude"] = geo.get("longitude", "N/A")
                    hotel_data["hotel_email"] = data.get("email", "N/A")
                except:
                    pass

            # map
            lat = hotel_data["latitude"]
            lon = hotel_data["longitude"]
            hotel_data["google_map_link"] = (
                f"https://maps.google.com/?q={lat},{lon}"
                if lat != "N/A" else "N/A"
            )

            # pet friendly
            page_text = page.content().lower()
            if "pet" in page_text:
                hotel_data["pet_friendly"] = "Yes"
            else:
                hotel_data["pet_friendly"] = "Unknown"

            hotel_data["source_website"] = "Booking.com"
            hotel_data["source_url"] = url

            # =====================
            # REVIEWS
            # =====================
            try:
                page.click("button:has-text('See all reviews')", timeout=5000)
                time.sleep(3)
            except:
                pass

            review_cards = page.locator('[data-testid="review-card"]')

            for i in range(min(review_cards.count(), 20)):
                card = review_cards.nth(i)

                try:
                    name = card.locator('[data-testid="reviewer-name"]').inner_text()
                except:
                    name = "Anonymous"

                try:
                    text = card.locator('[data-testid="review-text"]').inner_text()
                except:
                    text = "N/A"

                try:
                    score = card.locator('[data-testid="review-score"]').inner_text()
                except:
                    score = "N/A"

                try:
                    date = card.locator('[data-testid="review-date"]').inner_text()
                except:
                    date = "N/A"

                reviews.append({
                    "reviewer_name": name,
                    "review_text": text,
                    "review_score": score,
                    "review_date": date,
                    "source_website": "Booking.com"
                })
                
            browser.close()

    except Exception as e:
        hotel_data["error"] = str(e)

    return hotel_data, reviews
# ─────────────────────────────────────────────
# TRIPADVISOR SCRAPER
# ─────────────────────────────────────────────
import time
import json
import re

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium_stealth import stealth


def scrape_tripadvisor(url):
    hotel_data = {}
    reviews = []
    driver = None

    try:
        options = Options()

        # ⚠️ Keep headless OFF initially (you can enable later)
        options.add_argument("--headless=new")

        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        # ✅ Real browser user-agent
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

        # ✅ Stealth mode (very important)
        stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL",
            fix_hairline=True,
        )

        driver.get(url)

        # ✅ Wait for real content (NOT sleep)
        WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )

        # ✅ Scroll to load dynamic content
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        print("Page loaded successfully:", url)

        # ── Hotel Name ──
        title_tag = soup.find("h1")
        hotel_data["hotel_name"] = title_tag.get_text(strip=True) if title_tag else "N/A"

        # ── JSON-LD extraction ──
        scripts = soup.find_all("script", {"type": "application/ld+json"})

        hotel_data["latitude"] = "N/A"
        hotel_data["longitude"] = "N/A"
        hotel_data["hotel_email"] = "N/A"

        for sc in scripts:
            try:
                data = json.loads(sc.string or "")
                if isinstance(data, dict) and data.get("@type") in ("Hotel", "LodgingBusiness"):

                    geo = data.get("geo", {})
                    hotel_data["latitude"] = geo.get("latitude", "N/A")
                    hotel_data["longitude"] = geo.get("longitude", "N/A")

                    addr = data.get("address", {})
                    if isinstance(addr, dict):
                        hotel_data["address"] = ", ".join(filter(None, [
                            addr.get("streetAddress", ""),
                            addr.get("addressLocality", ""),
                            addr.get("addressCountry", "")
                        ]))

                    agg = data.get("aggregateRating", {})
                    hotel_data["overall_score"] = str(agg.get("ratingValue", "N/A"))
                    hotel_data["review_count"] = str(agg.get("reviewCount", "N/A"))

            except Exception:
                continue

        # Defaults
        hotel_data.setdefault("address", "N/A")
        hotel_data.setdefault("overall_score", "N/A")
        hotel_data.setdefault("review_count", "N/A")

        lat = hotel_data.get("latitude")
        lon = hotel_data.get("longitude")

        hotel_data["google_map_link"] = (
            f"https://maps.google.com/?q={lat},{lon}"
            if lat != "N/A" and lon != "N/A" else "N/A"
        )

        # ── Reviews ──
        review_blocks = soup.find_all("div", {"data-reviewid": True})

        for blk in review_blocks[:20]:
            r = {}

            name = blk.find(class_=re.compile(r"info_text|username", re.I))
            r["reviewer_name"] = name.get_text(strip=True) if name else "Anonymous"

            text = blk.find(class_=re.compile(r"QewHA|review", re.I))
            r["review_text"] = text.get_text(strip=True) if text else "N/A"

            rating = blk.find(class_=re.compile(r"ui_bubble_rating", re.I))
            if rating:
                cls = " ".join(rating.get("class", []))
                match = re.search(r"bubble_(\d+)", cls)
                r["review_score"] = f"{int(match.group(1))//10}/10" if match else "N/A"
            else:
                r["review_score"] = "N/A"

            r["review_date"] = "N/A"
            r["source_website"] = "TripAdvisor"

            reviews.append(r)

        # Fallback if blocked / empty
        if not reviews:
            print("⚠️ No reviews found — likely blocked")
            reviews = [{
                "reviewer_name": "Demo User",
                "review_text": "Sample review (scraping likely blocked).",
                "review_score": "8/10",
                "review_date": "N/A",
                "source_website": "TripAdvisor"
            }]

        hotel_data["source_website"] = "TripAdvisor"
        hotel_data["source_url"] = url

    except Exception as e:
        hotel_data["error"] = str(e)

    finally:
        if driver:
            driver.quit()

    return hotel_data, reviews
# ─────────────────────────────────────────────
# DEMO DATA GENERATOR (fallback)
# ─────────────────────────────────────────────
def generate_demo_reviews(hotel_name, count=10):
    names = ["Emma W.", "Raj P.", "Sarah L.", "Ahmed K.", "Yuki T.", "Carlos M.", "Priya S.", "John D.", "Li Wei", "Fatima H."]
    titles = ["Excellent stay!", "Great value", "Would recommend", "Amazing service", "Good location", "Perfect for business", "Lovely hotel", "Clean and comfortable", "Fantastic experience", "Nice place"]
    bodies = [
        "The staff were incredibly friendly and helpful. Room was spotless.",
        "Breakfast was amazing, great variety. Location perfect for sightseeing.",
        "WiFi was fast, bed very comfortable. Will definitely return.",
        "Check-in was smooth. Pool area well-maintained and clean.",
        "Exceeded expectations. Room service was prompt and delicious.",
    ]
    reviews = []
    for i in range(count):
        reviews.append({
            "reviewer_name": names[i % len(names)],
            "review_date": f"2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "review_score": f"{random.randint(7,10)}/10",
            "review_text": f"{titles[i%len(titles)]} | {bodies[i%len(bodies)]}",
            "source_website": "Demo Data"
        })
    return reviews


# ─────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────
def detect_and_scrape(url):
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    if "booking.com" in domain:
        return scrape_booking(url)
    elif "tripadvisor" in domain:
        return scrape_tripadvisor(url)
    else:
        # Generic fallback
        hotel_data = {
            "hotel_name": "Hotel (Generic Scrape)",
            "star_rating": "N/A", "address": "N/A",
            "amenities": "N/A", "photo_links": "N/A",
            "overall_score": "N/A", "review_count": "N/A",
            "pet_friendly": "Unknown", "hotel_email": "N/A",
            "latitude": "N/A", "longitude": "N/A",
            "google_map_link": "N/A",
            "source_website": domain,
            "source_url": url,
            "note": "Generic scrape — limited data. Try a Booking.com or TripAdvisor URL."
        }
        reviews = generate_demo_reviews("Hotel", 8)
        return hotel_data, reviews


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/extract", methods=["POST"])
def extract():
    data = request.get_json()
    url = data.get("url","").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    hotel_data, reviews = detect_and_scrape(url)
    return jsonify({"hotel": hotel_data, "reviews": reviews})


@app.route("/export", methods=["POST"])
def export():
    import pandas as pd
    import io
    from flask import request, send_file

    data = request.get_json()
    hotel = data.get("hotel", {})
    reviews = data.get("reviews", [])
    fmt = data.get("format", "csv")

    output = io.BytesIO()

    # =====================
    # 🔥 FLATTEN DATA
    # =====================
    if reviews:
        rows = []
        for r in reviews:
            row = {}

            # Hotel fields
            for k, v in hotel.items():
                row[f"hotel_{k}"] = v

            # Review fields
            for k, v in r.items():
                row[k] = v

            rows.append(row)

        df = pd.DataFrame(rows)

    else:
        df = pd.DataFrame([hotel])

    # =====================
    # EXPORT
    # =====================
    if fmt == "excel":
        with pd.ExcelWriter(output, engine="openpyxl") as writer:

            # Sheet 1: Hotel summary
            pd.DataFrame([hotel]).to_excel(
                writer,
                sheet_name="Hotel Details",
                index=False
            )

            # Sheet 2: Reviews (flattened)
            if reviews:
                df.to_excel(
                    writer,
                    sheet_name="Reviews",
                    index=False
                )

        output.seek(0)
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="hotel_data.xlsx"
        )

    else:
        df.to_csv(output, index=False)
        output.seek(0)
        return send_file(
            output,
            mimetype="text/csv",
            as_attachment=True,
            download_name="hotel_data.csv"
        )
        
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)