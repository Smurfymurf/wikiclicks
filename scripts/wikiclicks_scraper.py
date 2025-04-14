import requests, time, random, whois
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from supabase import create_client, Client
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

MAX_ARTICLES_PER_PAGE = 15
MAX_LINKS_PER_ARTICLE = 8
CATEGORY_PAGES_PER_RUN = 5

def get_article_urls(category_url):
    try:
        resp = requests.get(category_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.select("div.mw-category-group a")
        return ["https://en.wikipedia.org" + a['href'] for a in links[:MAX_ARTICLES_PER_PAGE]]
    except:
        return []

def extract_external_links(article_url):
    try:
        r = requests.get(article_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.select_one("#firstHeading").text.strip()
        links = []
        for a in soup.select("a.external"):
            href = a.get("href")
            if href and href.startswith("http"):
                links.append({
                    "article_title": title,
                    "article_url": article_url,
                    "link_url": href,
                    "link_text": a.text.strip()
                })
                if len(links) >= MAX_LINKS_PER_ARTICLE:
                    break
        return links
    except:
        return []

def check_status_and_availability(link):
    time.sleep(random.uniform(1.0, 2.5))  # polite delay
    try:
        status = requests.head(link["link_url"], timeout=5).status_code
    except:
        status = 0

    domain = urlparse(link["link_url"]).netloc

    try:
        who = whois.whois(domain)
        is_available = not who.domain_name
    except:
        is_available = True

    return {
        **link,
        "http_status": status,
        "domain": domain,
        "is_available": is_available,
        "discovered_at": datetime.utcnow().isoformat()
    }

def is_new_domain(domain):
    existing = supabase.table("wiki_leads").select("id").eq("domain", domain).execute()
    return len(existing.data) == 0

def main():
    print("Scraper started...")

    all_articles = []
    for page in random.sample(range(1, 100), CATEGORY_PAGES_PER_RUN):
        cat_url = f"https://en.wikipedia.org/w/index.php?title=Category:Articles_with_dead_external_links&pagefrom=A#{page}"
        article_urls = get_article_urls(cat_url)
        all_articles += article_urls
        time.sleep(random.uniform(1, 2))

    print(f"🔍 Pulled {len(all_articles)} articles from {CATEGORY_PAGES_PER_RUN} category pages")

    all_links = []
    for article in all_articles:
        links = extract_external_links(article)
        all_links += links
        time.sleep(random.uniform(0.5, 1.5))

    print(f"🔗 Found {len(all_links)} external links to scan")

    new_domain_count = 0

    with ThreadPoolExecutor(max_workers=6) as executor:
        enriched_links = list(executor.map(check_status_and_availability, all_links))

    for lead in enriched_links:
        if lead["http_status"] in [404, 410, 0] and lead["is_available"] and is_new_domain(lead["domain"]):
            print(f"🟢 New expired domain: {lead['domain']} ({lead['link_url']})")
            supabase.table("wiki_leads").insert({
                "article_title": lead["article_title"],
                "article_url": lead["article_url"],
                "link_url": lead["link_url"],
                "link_text": lead["link_text"],
                "domain": lead["domain"],
                "http_status": lead["http_status"],
                "is_available": lead["is_available"],
                "discovered_at": lead["discovered_at"]
            }).execute()
            new_domain_count += 1
            time.sleep(1)

    print(f"✅ Scraper finished: {new_domain_count} new domains added.")

if __name__ == "__main__":
    main()