import asyncio
import pandas as pd
import os
import mimetypes
from playwright.async_api import async_playwright
import aiohttp

# Updated CSV file name and Supabase bucket URL
CSV_FILE = 'costco - sheet updated.csv'
OUTPUT_DIR = 'images'
BASE_URL = "https://rpmzykoxqnbozgdoqbpc.supabase.co/storage/v1/object/public/costco-beverages-and-water"
os.makedirs(OUTPUT_DIR, exist_ok=True)

new_image_urls = {}

async def download_image(url, product_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                content = await resp.read()
                content_type = resp.headers.get('Content-Type')
                ext = mimetypes.guess_extension(content_type) or '.jpg'
                filename = f"{product_id}{ext}"
                file_path = os.path.join(OUTPUT_DIR, filename)
                with open(file_path, 'wb') as f:
                    f.write(content)
                print(f"Downloaded: {file_path}")

                image_url = f"{BASE_URL}/{filename}"
                new_image_urls[product_id] = image_url
            else:
                print(f"Failed to download {url} (Status: {resp.status})")

async def handle_url(playwright, product_id, product_url):
    browser = await playwright.chromium.launch(headless=False, args=["--no-sandbox"])
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        java_script_enabled=True,
        viewport={"width": 1280, "height": 720},
    )
    page = await context.new_page()

    image_captured = asyncio.Event()

    async def handle_request(route, request):
        if "bfasset" in request.url and request.resource_type == "image":
            if not image_captured.is_set():
                image_captured.set()
                await download_image(request.url, product_id)
        await route.continue_()

    await context.route("**/*", handle_request)

    try:
        await page.goto(product_url, timeout=30000)
        try:
            await asyncio.wait_for(image_captured.wait(), timeout=10)
        except asyncio.TimeoutError:
            print(f"No bfasset image found for {product_id}")
    except Exception as e:
        print(f"Error loading {product_url}: {e}")
    await browser.close()

async def main():
    df = pd.read_csv(CSV_FILE)

    async with async_playwright() as playwright:
        for index, row in df.iterrows():
            product_id = str(row['product_id'])
            product_url = row['product_url']
            await handle_url(playwright, product_id, product_url)

    df['image_url'] = df['product_id'].map(new_image_urls)
    df.to_csv(CSV_FILE, index=False)
    print(f"Updated CSV with image URLs saved to: {CSV_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
