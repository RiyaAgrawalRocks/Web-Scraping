import csv
import uuid
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

# Define Costco category URLs
CATEGORIES = {
    "hair_care": "https://www.costco.com/hair-care.html",
    "skin_care": "https://www.costco.com/skin-care.html"
}

# Backup test site
TEST_CATEGORIES = {
    "books": "http://books.toscrape.com/catalogue/category/books_1/index.html"
}

CSV_FIELDS = [
    "product_id", "brand", "image", "price", "source", "currency",
    "description", "product_url", "product_title",
    "price_available", "additional_image", "additional_description"
]

MAX_PRODUCTS = 100

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Re-enable headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")  # Speed up loading
    options.add_argument("--disable-javascript")  # Try without JS first
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Add additional options to avoid detection
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # Execute script to remove webdriver property
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    # Set timeouts
    driver.implicitly_wait(10)
    driver.set_page_load_timeout(30)
    
    return driver

def scroll_to_load(driver, max_scrolls=5, pause=2):
    for _ in range(max_scrolls):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)

def extract_products(driver, category_url):
    driver.get(category_url)
    time.sleep(5)  # Longer wait for Costco
    scroll_to_load(driver, max_scrolls=10, pause=3)  # More scrolling
    
    # Costco-specific selectors first, then fallback to others
    selectors = [
        "div[data-automation-id='productTile']",  # Costco primary
        "div.product-tile",  # Costco alternative
        "div.product-item",  # Costco alternative
        ".product-tile-set .product-tile",  # Costco nested
        "article.product",  # Generic e-commerce
        "div.product",  # Generic
        ".product-list-item",  # Generic
        "article.product_pod",  # Books.toscrape fallback
        ".product_pod"  # Books.toscrape alternative
    ]
    
    products = []
    for selector in selectors:
        products = driver.find_elements(By.CSS_SELECTOR, selector)
        if products:
            print(f"  Found {len(products)} products using selector: {selector}")
            break
    
    if not products:
        # Debug: print page info and save HTML
        print(f"  Page title: {driver.title}")
        print(f"  Page URL: {driver.current_url}")
        print(f"  Page source length: {len(driver.page_source)} characters")
        
        # Check if we got an error page or empty page
        if "can't be reached" in driver.page_source.lower() or "error" in driver.title.lower():
            print("  ❌ Error page detected - website may be blocking requests")
        elif len(driver.page_source) < 1000:
            print("  ❌ Very short page content - possible blocking")
        else:
            print("  ⚠️  Page loaded but no products found - checking for alternative selectors")
            
        # Save page source for debugging
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("  Saved page source to debug_page.html for analysis")
    
    return products

def scrape_product_page(driver, url):
    try:
        driver.get(url)
        time.sleep(2)
        try:
            desc = driver.find_element(By.CSS_SELECTOR, "div.product-info-description").text.strip()
        except:
            desc = ""
        try:
            add_img = driver.find_element(By.CSS_SELECTOR, "div.product-image-carousel img").get_attribute("src")
        except:
            add_img = ""
        try:
            specs = driver.find_element(By.CSS_SELECTOR, "div.product-info-specs").text.strip()
        except:
            specs = ""
        return desc, add_img, specs
    except:
        return "", "", ""

def parse_product(elem, driver):
    pid = str(uuid.uuid4())

    # Costco-specific selectors first, then fallback to others
    title, link = "", ""
    title_selectors = [
        "a[data-automation-id='productName']",  # Costco primary
        "div.description > a",  # Costco alternative
        ".product-title a",  # Generic e-commerce
        "h3 a",  # Generic/Books
        ".description a",
        "a.product-link",
        "article h3 a"
    ]
    
    for selector in title_selectors:
        try:
            title_elem = elem.find_element(By.CSS_SELECTOR, selector)
            title = title_elem.text.strip()
            link = title_elem.get_attribute("href")
            if title:  # Only break if we actually got a title
                break
        except:
            continue

    # Get full title from title attribute if text is truncated
    if title and "..." in title:
        try:
            title_elem = elem.find_element(By.CSS_SELECTOR, "h3 a, a[data-automation-id='productName']")
            full_title = title_elem.get_attribute("title")
            if full_title:
                title = full_title
        except:
            pass

    # Brand selectors (Costco-specific first)
    brand = ""
    brand_selectors = [
        "[data-automation-id='brandName']",  # Costco
        "div.product-brand-name",  # Costco alternative
        ".brand-name",
        ".product-brand"
    ]
    
    for selector in brand_selectors:
        try:
            brand = elem.find_element(By.CSS_SELECTOR, selector).text.strip()
            break
        except:
            continue

    # Image selectors (Costco-specific first)
    img = ""
    img_selectors = [
        "[data-automation-id='productImage'] img",  # Costco
        ".product-image img",  # Costco alternative
        ".image_container img",  # Books fallback
        "img"  # Generic
    ]
    
    for selector in img_selectors:
        try:
            img_elem = elem.find_element(By.CSS_SELECTOR, selector)
            img = img_elem.get_attribute("src")
            # Make relative URLs absolute
            if img and not img.startswith("http"):
                if "costco.com" in driver.current_url:
                    img = "https://www.costco.com" + img.lstrip("/")
                elif "books.toscrape.com" in driver.current_url:
                    img = "https://books.toscrape.com/" + img.lstrip("/")
            break
        except:
            continue

    # Price selectors (Costco-specific first)
    price, price_available = None, False
    price_selectors = [
        "[data-automation-id='productPrice']",  # Costco
        ".price-current",  # Costco alternative
        ".price",  # Generic
        ".product-price",
        "p.price_color",  # Books fallback
        ".sr-only"
    ]
    
    for selector in price_selectors:
        try:
            price_text = elem.find_element(By.CSS_SELECTOR, selector).text.replace(",", "")
            # Extract numeric value from price text
            import re
            price_match = re.search(r'[\d.]+', price_text)
            if price_match:
                price = float(price_match.group())
                price_available = True
                break
        except:
            continue

    # Determine source and currency based on current URL
    if "costco.com" in driver.current_url:
        source = "costco.com"
        currency = "USD"
        # Try to get product rating or other Costco-specific info
        description = ""
        try:
            rating_elem = elem.find_element(By.CSS_SELECTOR, "[data-automation-id='productRating']")
            description = f"Rating: {rating_elem.get_attribute('aria-label')}"
        except:
            pass
    elif "books.toscrape.com" in driver.current_url:
        source = "books.toscrape.com"
        currency = "GBP"
        # Get star rating for books site
        description = ""
        try:
            rating_elem = elem.find_element(By.CSS_SELECTOR, "p.star-rating")
            description = rating_elem.get_attribute("class").replace("star-rating ", "")
        except:
            pass
    else:
        source = "unknown"
        currency = "USD"
        description = ""

    # Skip deep scraping for now to avoid additional blocking
    additional_image, additional_description = "", ""

    return {
        "product_id": pid,
        "brand": brand,
        "image": img,
        "price": price,
        "source": source,
        "currency": currency,
        "description": description,
        "product_url": link,
        "product_title": title,
        "price_available": price_available,
        "additional_image": additional_image,
        "additional_description": additional_description
    }

def main():
    driver = setup_driver()
    rows = []
    total = 0

    # First test with a simple page to ensure the driver works
    print("Testing web driver connectivity...")
    try:
        driver.get("https://httpbin.org/headers")
        print("✅ Web driver is working correctly")
    except Exception as e:
        print(f"❌ Web driver test failed: {e}")
        driver.quit()
        return

    # Try Costco categories
    print("\n🛒 Attempting to scrape Costco...")
    for cat, url in CATEGORIES.items():
        print(f"\nScraping category: {cat}")
        try:
            products = extract_products(driver, url)
            print(f" Found {len(products)} products")

            for elem in products:
                if total >= MAX_PRODUCTS:
                    break
                try:
                    row = parse_product(elem, driver)
                    if row['product_title']:  # Only add if we got a title
                        rows.append(row)
                        total += 1
                        print(f"  → Scraped: {row['product_title'][:60]}...")
                    else:
                        print(f"  × Skipped product with no title")
                except Exception as e:
                    print(f"  × Skipped product due to error: {e}")
                    continue
            
            if total >= MAX_PRODUCTS:
                break
                
        except Exception as e:
            print(f"❌ Failed to scrape category {cat}: {e}")
            continue

    # If Costco failed and we have no products, try the test site
    if total == 0:
        print(f"\n📚 Costco scraping failed, testing with backup site...")
        for cat, url in TEST_CATEGORIES.items():
            print(f"\nScraping test category: {cat}")
            try:
                products = extract_products(driver, url)
                print(f" Found {len(products)} products")

                for elem in products[:10]:  # Just get a few test products
                    try:
                        row = parse_product(elem, driver)
                        if row['product_title']:
                            rows.append(row)
                            total += 1
                            print(f"  → Test scraped: {row['product_title'][:60]}...")
                    except Exception as e:
                        print(f"  × Skipped test product due to error: {e}")
                        continue
                break
            except Exception as e:
                print(f"❌ Failed to scrape test category {cat}: {e}")
                continue

    driver.quit()

    # Save results
    with open("costco_products.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    if total > 0:
        print(f"\n✅ Done! Saved {len(rows)} products to costco_products.csv")
        if any("costco.com" in row.get('source', '') for row in rows):
            print("🎉 Successfully scraped from Costco!")
        else:
            print("⚠️  Used backup site as Costco was not accessible")
    else:
        print(f"\n❌ No products were scraped. Check debug_page.html for troubleshooting.")

if __name__ == "__main__":
    main()
