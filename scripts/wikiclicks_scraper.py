import requests, time, random, whois
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from supabase import create_client, Client

# === CONFIG ===
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-anon-or-service-role-key"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

MAX_ARTICLES_PER_RUN = 6
MAX_LINKS_PER_ARTICLE = 5

def get_random_category_page():
    page_number = random.randint(1, 100)  # You can increase this over time
    return f"https://en.wikipedia.org/w/index.php?title=Category:Articles_with_dead_external_links&pagefrom=A#{page_number}"

def get_article_urls(category_url):
    resp = requests.get(category_url, timeout=10)
    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.select("div.mw-category-group a")
    return ["https://en.wikipedia.org" + a['href'] for a in links[:MAX_ARTICLES_PER_RUN]]

def extract_external_links(article_url):
    try:
        r = requests.get(article_url, timeout=10)
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
    cat_url = get_random_category_page()
    articles = get_article_urls(cat_url)

    all_links = []
    for article in articles:
        all_links += extract_external_links(article)

    # Multithread checkers
    with ThreadPoolExecutor(max_workers=6) as executor:
        enriched_links = list(executor.map(check_status_and_availability, all_links))

    for lead in enriched_links:
        if lead["http_status"] in [404, 410, 0] and lead["is_available"] and is_new_domain(lead["domain"]):
            print(f"New expired domain: {lead['domain']} ({lead['link_url']})")
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
            time.sleep(1)

    print("Scraper finished.")

if __name__ == "__main__":
    main()
