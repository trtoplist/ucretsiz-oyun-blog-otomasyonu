from __future__ import annotations

import html
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
SEEN_PATH = ROOT / "data" / "seen.json"
BLOGGER_SCOPE = "https://www.googleapis.com/auth/blogger"
USER_AGENT = "Mozilla/5.0 (compatible; TurkishFreeGameBlogger/2.0)"
EPIC_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
STEAM_SEARCH_URL = "https://store.steampowered.com/search/"
STEAM_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
TRANSLATION_URL = "https://api.mymemory.translated.net/get"
TRANSLATION_DAILY_LIMIT = 5000  # anonymous free allowance, tracked in data/seen.json
EPIC_IMAGE_HOSTS = {"cdn1.epicgames.com", "cdn2.unrealengine.com", "media-cdn.epicgames.com"}
STEAM_IMAGE_HOSTS = {"shared.akamai.steamstatic.com", "cdn.akamai.steamstatic.com", "steamcdn-a.akamaihd.net"}
EXCLUDED_RE = re.compile(
    r"\b(dlc|add[- ]on|expansion|soundtrack|skin pack|starter pack|bundle|demo|beta|"
    r"trial|loot|key giveaway|giveaway|raffle|sweepstakes|contest|çekiliş|anahtar)\b",
    re.IGNORECASE,
)
TURKISH_HINTS = (
    " oyun ", " ve ", " için ", " bir ", " ile ", " ücretsiz ", " oyuncu ",
    " dünyasında ", " hikâye ", " hikaye ", " macera ", " hayatta ", " savaş ",
    " keşfet ", " strateji ", " aksiyon ", " bulmaca ", " yarış ", " takım ",
)


@dataclass
class Offer:
    id: str
    title: str
    description: str
    store: str
    url: str
    thumbnail: str
    genres: list[str]
    requirements: str
    offer_type: str
    end_at: datetime | None
    source_note: str
    translation_status: str = ""
    language_support: str = "Mağaza kaynağında doğrulanmadı."


class SteamResultParser(HTMLParser):
    """Extract app IDs from Steam's official Free-to-Play result rows."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        values = dict(attrs)
        if "search_result_row" not in (values.get("class") or ""):
            return
        raw = values.get("data-ds-appid") or ""
        for app_id in raw.split(","):
            if app_id.isdigit() and app_id not in self.ids:
                self.ids.append(app_id)


def get_json(url: str, *, params: dict[str, Any] | None = None) -> Any:
    response = requests.get(url, params=params, timeout=35, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.json()


def get_text(url: str, *, params: dict[str, Any] | None = None) -> str:
    response = requests.get(url, params=params, timeout=35, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text


def parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return date.astimezone(timezone.utc)
    except ValueError:
        return None


def is_https_url(value: str, allowed_hosts: set[str]) -> bool:
    try:
        parsed = urlparse(value)
    except (TypeError, ValueError):
        return False
    host = (parsed.hostname or "").lower().strip(".")
    return (
        parsed.scheme == "https"
        and bool(host)
        and parsed.username is None
        and any(host == domain or host.endswith("." + domain) for domain in allowed_hosts)
    )


def looks_turkish(text: str) -> bool:
    value = f" {text.lower()} "
    return sum(token in value for token in TURKISH_HINTS) >= 2 or sum(ch in text for ch in "çğıöşüÇĞİÖŞÜ") >= 3


def clean_html(value: Any) -> str:
    text = re.sub(r"<br\s*/?>", "\n", str(value or ""), flags=re.I)
    text = re.sub(r"</(?:p|li|div|h[1-6])\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def clean_store_description(value: Any) -> str:
    """Use one short store paragraph, never merge multiple copyrighted paragraphs."""
    raw = str(value or "")
    paragraphs = re.findall(r"<p\b[^>]*>(.*?)</p\s*>", raw, flags=re.I | re.S)
    candidate = paragraphs[0] if paragraphs else raw
    return clean_html(candidate)


def source_epic(seen: dict[str, Any], problems: list[str]) -> list[Offer]:
    now = datetime.now(timezone.utc)
    try:
        payload = get_json(EPIC_URL, params={"locale": "tr-TR", "country": "TR", "allowCountries": "TR"})
    except (requests.RequestException, ValueError) as exc:
        problems.append(f"Epic Games: {type(exc).__name__}")
        return []
    elements = (((payload or {}).get("data") or {}).get("Catalog") or {}).get("searchStore", {}).get("elements", [])
    found: list[Offer] = []
    for item in elements if isinstance(elements, list) else []:
        if not isinstance(item, dict) or item.get("offerType") != "BASE_GAME":
            continue
        title = str(item.get("title") or "").strip()
        desc = clean_store_description(item.get("description"))
        if not title or not desc or EXCLUDED_RE.search(title):
            continue
        price = ((item.get("price") or {}).get("totalPrice") or {})
        # Epic's active free promotions have discountPrice=0; require a real original price.
        if price.get("discountPrice") != 0 or not price.get("originalPrice"):
            continue
        promos = ((item.get("promotions") or {}).get("promotionalOffers") or [])
        active: list[dict[str, Any]] = []
        for group in promos:
            active.extend(group.get("promotionalOffers") or [])
        for promo in active:
            start, end = parse_date(promo.get("startDate")), parse_date(promo.get("endDate"))
            if not start or not end or not (start <= now < end):
                continue
            mapping = next((m for m in item.get("catalogNs", {}).get("mappings", []) if m.get("pageSlug")), None)
            if not mapping:
                continue
            url = f"https://store.epicgames.com/tr/p/{quote(mapping['pageSlug'], safe='-')}"
            image = next((str(img.get("url")) for img in item.get("keyImages", []) if img.get("url")), "")
            if not is_https_url(image, EPIC_IMAGE_HOSTS):
                image = ""
            oid = f"epic:{item.get('id') or item.get('namespace') or mapping['pageSlug']}"
            if oid in seen:
                continue
            requirements_obj = item.get("pcRequirements") or {}
            req = clean_html(requirements_obj.get("minimum") or "")
            found.append(Offer(oid, title, desc, "Epic Games", url, image, [], req, "Süreli ücretsiz kampanya", end,
                               "Epic Games Store Türkiye resmî kampanya verisi"))
            break
    return found


def steam_app_details(app_id: str) -> dict[str, Any] | None:
    payload = get_json(STEAM_DETAILS_URL, params={"appids": app_id, "cc": "tr", "l": "turkish"})
    result = (payload or {}).get(app_id) or {}
    if not result.get("success") or not isinstance(result.get("data"), dict):
        return None
    return result["data"]


def steam_release_day(value: Any) -> date | None:
    """Steam localizes release dates; accept English and Turkish month names."""
    text = str(value or "").strip().replace(",", "")
    for fmt in ("%d %b %Y", "%b %d %Y", "%d %B %Y", "%B %d %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    months = {
        "oca": "Jan", "şub": "Feb", "sub": "Feb", "mar": "Mar", "nis": "Apr", "may": "May",
        "haz": "Jun", "tem": "Jul", "ağu": "Aug", "agu": "Aug", "eyl": "Sep", "eki": "Oct",
        "kas": "Nov", "ara": "Dec",
    }
    parts = text.split()
    if len(parts) == 3:
        month = months.get(parts[1].lower().rstrip("."))
        if month:
            try:
                return datetime.strptime(f"{parts[0]} {month} {parts[2]}", "%d %b %Y").date()
            except ValueError:
                return None
    return None


def source_steam(seen: dict[str, Any], problems: list[str], days_new: int = 120) -> list[Offer]:
    try:
        page = get_text(STEAM_SEARCH_URL, params={"category1": "998", "sort_by": "Released_DESC", "cc": "tr", "l": "turkish"})
    except requests.RequestException as exc:
        problems.append(f"Steam: {type(exc).__name__}")
        return []
    parser = SteamResultParser()
    parser.feed(page)
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days_new)
    found: list[Offer] = []
    # Newest releases only: prevents an initial run from drafting the entire historic F2P catalog.
    for app_id in parser.ids[:60]:
        oid = f"steam:{app_id}"
        if oid in seen:
            continue
        try:
            data = steam_app_details(app_id)
        except (requests.RequestException, ValueError) as exc:
            problems.append(f"Steam app {app_id}: {type(exc).__name__}")
            continue
        if not data or data.get("type") != "game" or data.get("is_free") is not True:
            continue
        release = data.get("release_date") or {}
        release_text = str(release.get("date") or "").strip()
        release_day = steam_release_day(release_text)
        if not release_day:
            continue
        if release_day < cutoff:
            # The Steam page is sorted newest first; older games need not be queried.
            break
        genres = [str(g.get("description", "")).strip() for g in data.get("genres", []) if g.get("description")]
        if not any(g.lower() in {"oynaması ücretsiz", "free to play"} for g in genres):
            continue
        title = str(data.get("name") or "").strip()
        description = clean_store_description(data.get("short_description"))
        if not title or not description or EXCLUDED_RE.search(title):
            continue
        image = str(data.get("header_image") or "")
        if not is_https_url(image, STEAM_IMAGE_HOSTS):
            image = ""
        requirements_obj = data.get("pc_requirements") or {}
        requirements = clean_html(requirements_obj.get("minimum") or "")
        supported_languages = clean_html(data.get("supported_languages") or "")
        language_support = (
            "Steam mağaza verisinde Türkçe dil desteği listeleniyor. Ayrıntıları ürün sayfasında kontrol edin."
            if re.search(r"\bTurkish\b", supported_languages, re.IGNORECASE)
            else "Steam mağaza verisinde Türkçe dil desteği listelenmiyor."
        )
        found.append(Offer(oid, title, description, "Steam", f"https://store.steampowered.com/app/{app_id}/",
                           image, genres[:3], requirements, "Süresiz ücretsiz (oynaması ücretsiz)", None,
                           f"Steam Türkiye resmî mağaza kataloğu · çıkış: {release_text}",
                           language_support=language_support))
    return found


def fetch_offers(config: dict[str, Any], seen: dict[str, Any]) -> tuple[list[Offer], list[str]]:
    problems: list[str] = []
    offers: list[Offer] = []
    enabled = set(config.get("enabled_sources", ["epic", "steam"]))
    if "epic" in enabled:
        offers.extend(source_epic(seen, problems))
    if "steam" in enabled:
        offers.extend(source_steam(seen, problems, int(config.get("steam_recent_release_days", 120))))
    unsupported = sorted(set(config.get("requested_stores", [])) - {"Steam", "Epic Games"})
    if unsupported:
        problems.append("Resmî, doğrulanmış otomatik kaynağı henüz eklenmeyen mağazalar: " + ", ".join(unsupported))
    return offers, problems


def genre_label(offer: Offer) -> str:
    translations = {"action": "Aksiyon", "adventure": "Macera", "rpg": "Rol Yapma", "role-playing": "Rol Yapma",
                    "strategy": "Strateji", "simulation": "Simülasyon", "indie": "Bağımsız", "casual": "Gündelik",
                    "racing": "Yarış", "sports": "Spor", "massively multiplayer": "MMO", "devasa çok oyunculu": "MMO"}
    priority = {"aksiyon": 0, "action": 0, "nişancı": 1, "shooter": 1, "fps": 1,
                "rol yapma": 2, "rpg": 2, "strateji": 3, "strategy": 3,
                "yarış": 4, "racing": 4, "simülasyon": 5, "simulation": 5,
                "bulmaca": 6, "puzzle": 6, "macera": 7, "adventure": 7,
                "korku": 8, "horror": 8, "hayatta kalma": 9, "survival": 9}
    for value in sorted(offer.genres, key=lambda g: priority.get(g.lower(), 20)):
        if value.lower() in {"oynaması ücretsiz", "free to play"}:
            continue
        return translations.get(value.lower(), value[:40])
    guesses = [(r"\b(fps|shooter|nişancı|first.person)\b", "Nişancı"),
               (r"\b(rpg|rol yapma)\b", "Rol Yapma"), (r"\b(strateji|strategy)\b", "Strateji"),
               (r"\b(yarış|racing)\b", "Yarış"), (r"\b(simülasyon|simulation)\b", "Simülasyon"),
               (r"\b(bulmaca|puzzle)\b", "Bulmaca"), (r"\b(macera|adventure)\b", "Macera"),
               (r"\b(korku|horror)\b", "Korku"), (r"\b(hayatta kalma|survival)\b", "Hayatta Kalma"),
               (r"\b(aksiyon|action)\b", "Aksiyon")]
    text = f"{offer.title} {offer.description}".lower()
    return next((label for pattern, label in guesses if re.search(pattern, text)), "Türü Belirtilmemiş")


def translation_input(text: str, max_bytes: int = 500) -> str:
    """MyMemory accepts one paragraph up to 500 UTF-8 bytes per request."""
    value = re.sub(r"\s+", " ", text).strip()
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    shortened = encoded[:max_bytes].decode("utf-8", errors="ignore")
    cut = shortened.rfind(" ")
    if cut > 0:
        shortened = shortened[:cut]
    sentence_cut = max(shortened.rfind(". "), shortened.rfind("! "), shortened.rfind("? "))
    if sentence_cut > 120:
        shortened = shortened[:sentence_cut + 1]
    return shortened.strip()


def translate_description(text: str, used_today: int) -> tuple[str | None, int, str]:
    """Keep native Turkish; otherwise translate one short public store paragraph."""
    original = translation_input(text)
    if not original:
        return None, 0, "Açıklama boş"
    if looks_turkish(original):
        return original, 0, "Mağazanın Türkçe açıklaması"
    charge = len(original)
    if used_today + charge > TRANSLATION_DAILY_LIMIT:
        return None, 0, "Ücretsiz çeviri günlük sınırına ulaşıldı"
    try:
        response = requests.get(
            TRANSLATION_URL,
            params={"q": original, "langpair": "autodetect|tr", "mt": "1"},
            timeout=30,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        payload = response.json()
        translated = html.unescape(str((payload.get("responseData") or {}).get("translatedText") or "")).strip()
        if int(payload.get("responseStatus", 0)) != 200 or len(translated) < 20 or not looks_turkish(translated):
            return None, charge, "Çeviri Türkçe olarak doğrulanamadı"
        return translated, charge, "MyMemory ile otomatik Türkçe çeviri"
    except (requests.RequestException, ValueError, TypeError):
        return None, charge, "Ücretsiz çeviri servisine erişilemedi"


def build_content(offer: Offer, timezone_name: str) -> tuple[str, list[str], str]:
    tz = ZoneInfo(timezone_name)
    end_text = offer.end_at.astimezone(tz).strftime("%d.%m.%Y %H:%M (Türkiye saati)") if offer.end_at else "Bitiş tarihi yok; mağaza oyunu süresiz ücretsiz listeliyor."
    labels = [offer.store, genre_label(offer), "Ücretsiz Oyun", "Süresiz Ücretsiz" if offer.end_at is None else "Süreli Kampanya"]
    parts = [
        f"<p><strong>⚠️ {html.escape(offer.offer_type)}. Tanıtım: {html.escape(offer.translation_status or 'Türkçe mağaza metni')}. Bu çeviri, oyunun Türkçe dil desteği olduğu anlamına gelmez. {html.escape(offer.language_support)} Bölge ve hesap koşulları değişebilir.</strong></p>",
        f"<p><strong>Mağaza:</strong> {html.escape(offer.store)} · <strong>Tür:</strong> {html.escape(genre_label(offer))}</p>",
        "<h2>Oyun hakkında</h2>",
        f"<p>{html.escape(offer.description)}</p>",
        "<h2>Ücretsiz erişim ve son tarih</h2>",
        f"<p>{html.escape(end_text)}</p>",
        "<p>Ücretsiz oyun kataloğu veya kampanyalar ülke, hesap, platform ve mağaza koşullarına göre değişebilir. İşlemden önce resmî ürün sayfasında fiyatın ücretsiz olduğunu doğrulayın.</p>",
        "<h2>Nasıl alınır?</h2>",
        f'<ol><li><a href="{html.escape(offer.url, quote=True)}" rel="nofollow noopener" target="_blank">Resmî {html.escape(offer.store)} oyun sayfasını açın</a>.</li><li>Hesabınızda oturum açın; ülke ve cihaz koşullarını kontrol edin.</li><li>Mağazada ücretsiz fiyatı görünüyorsa oyunu hesabınıza ekleyin.</li></ol>',
        "<h2>Sistem gereksinimleri</h2>",
        f"<p>{html.escape(offer.requirements[:2500])}</p>" if offer.requirements else "<p>Resmî kaynakta doğrulanmış sistem gereksinimi bilgisi bulunmuyor.</p>",
    ]
    if offer.thumbnail:
        parts.append(f'<p><img src="{html.escape(offer.thumbnail, quote=True)}" alt="{html.escape(offer.title, quote=True)} oyun görseli" loading="lazy"></p>')
    parts.append(f'<p>Kaynak: <a href="{html.escape(offer.url, quote=True)}" rel="nofollow noopener">resmî {html.escape(offer.store)} mağaza sayfası</a>. {html.escape(offer.source_note)} Tanıtım metni kısa bir otomatik çeviridir; taslakta gözden geçirilmelidir.</p>')
    return "\n".join(parts), labels, "Taslak; kontrol ve onay bekliyor."


def blogger_service() -> Any:
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET") or None,
        scopes=[BLOGGER_SCOPE],
    )
    creds.refresh(Request())
    return build("blogger", "v3", credentials=creds, cache_discovery=False)


def create_draft(service: Any, blog_id: str, offer: Offer, content: str, labels: list[str]) -> str:
    title = f"{offer.title} ücretsiz: {offer.store} fırsatı"
    search_description = f"{offer.title} ücretsiz oyun fırsatı: {offer.store} kampanya koşulları, bitiş tarihi ve alma rehberi."
    payload = {
        "kind": "blogger#post", "title": title, "content": content, "labels": labels,
        "customMetaData": json.dumps({"description": search_description[:150]}, ensure_ascii=False),
    }
    result = service.posts().insert(blogId=blog_id, body=payload, isDraft=True).execute(num_retries=5)
    return str(result.get("url") or result.get("id") or "Taslak oluşturuldu")


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not config.get("publishing_enabled", False):
        print("Taslak üretimi kapalı. Önce test çalıştırmasını doğrulayıp config ayarını açın.")
        return 0
    if config.get("draft_only") is not True:
        print("Güvenlik nedeniyle bu uygulama yalnızca Blogger taslağı oluşturabilir.", file=sys.stderr)
        return 2
    blog_id = os.environ.get("BLOGGER_BLOG_ID", "").strip()
    if not blog_id:
        print("BLOGGER_BLOG_ID secret eksik.", file=sys.stderr)
        return 2
    state = json.loads(SEEN_PATH.read_text(encoding="utf-8")) if SEEN_PATH.exists() else {"seen": {}}
    seen: dict[str, Any] = state.get("seen", {})
    offers, problems = fetch_offers(config, seen)
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=int(config.get("campaign_safety_hours", 2)))
    safe: list[Offer] = []
    for offer in offers:
        if offer.end_at and offer.end_at <= cutoff:
            print(f"Atlandı; kampanya bitiyor/bitmiş: {offer.title}")
            continue
        # Never draft an offer without a first-party product URL and store-hosted image.
        hosts = EPIC_IMAGE_HOSTS if offer.store == "Epic Games" else STEAM_IMAGE_HOSTS
        if not is_https_url(offer.url, {"store.epicgames.com"} if offer.store == "Epic Games" else {"store.steampowered.com"}):
            print(f"Atlandı; mağaza bağlantısı doğrulanmadı: {offer.title}")
            continue
        if offer.thumbnail and not is_https_url(offer.thumbnail, hosts):
            offer.thumbnail = ""
        safe.append(offer)
    safe = safe[: int(config.get("max_posts_per_run", 3))]
    usage = state.get("translation_usage", {})
    usage_day = now.date().isoformat()
    used_today = int(usage.get(usage_day, 0))
    translated_safe: list[Offer] = []
    for offer in safe:
        translated, charged, status = translate_description(offer.description, used_today)
        used_today += charged
        if not translated:
            print(f"Atlandı ({offer.title}): {status}")
            continue
        offer.description = translated
        offer.translation_status = status
        translated_safe.append(offer)
    safe = translated_safe
    state["translation_usage"] = {usage_day: used_today}
    print(f"Resmî kaynaklardan Türkçe taslağa uygun yeni teklifler: {len(safe)}")
    for problem in problems:
        print(f"Kaynak notu: {problem}")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    created_titles: list[str] = []
    if safe:
        service = blogger_service()
        for offer in safe:
            content, labels, _ = build_content(offer, config.get("timezone", "Europe/Istanbul"))
            try:
                link = create_draft(service, blog_id, offer, content, labels)
                seen[offer.id] = {"title": offer.title, "created_at": now.isoformat(), "url": offer.url}
                created_titles.append(offer.title)
                print(f"Taslak oluşturuldu: {offer.title} — {link}")
            except HttpError as exc:
                print(f"Blogger hatası ({offer.title}): HTTP {exc.resp.status}")
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["seen"] = seen
    SEEN_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("\n## Ücretsiz oyun kontrolü\n")
            summary.write("\n".join(f"- Taslak: {title}" for title in created_titles) if created_titles else "- Yeni uygun oyun yok; taslak oluşturulmadı.")
            summary.write("\n\n- Yalnızca resmî Steam ve Epic Games kaynakları etkin.\n")
            if problems:
                summary.write("- Kaynak notları: " + "; ".join(problems) + "\n")
    print(f"Oluşturulan taslak: {len(created_titles)} (otomatik yayın yok)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

