from __future__ import annotations

import html
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
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
GAMERPOWER_URL = "https://www.gamerpower.com/api/giveaways"


@dataclass
class Offer:
    id: str
    title: str
    description: str
    platforms: list[str]
    offer_type: str
    url: str
    thumbnail: str
    end_at: datetime | None
    source: str
    raw: dict[str, Any]


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def safe_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.netloc) and parsed.username is None
    except (TypeError, ValueError):
        return False


def parse_date(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def normalize(item: dict[str, Any]) -> Offer | None:
    title = str(item.get("title", "")).strip()
    url = str(item.get("open_giveaway_url") or item.get("giveaway_url") or "").strip()
    desc = str(item.get("description", "")).strip()
    oid = str(item.get("id", "")).strip()
    if not (title and desc and len(desc) >= 50 and safe_http_url(url) and oid):
        return None
    platforms = [x.strip() for x in str(item.get("平台", item.get("platform", ""))).split(",") if x.strip()]
    end_at = parse_date(item.get("end_date"))
    thumb = str(item.get("thumbnail", "")).strip()
    if not safe_http_url(thumb):
        thumb = ""
    return Offer(
        id=oid,
        title=title,
        description=desc,
        platforms=platforms,
        offer_type=str(item.get("type", "game")).lower(),
        url=url,
        thumbnail=thumb,
        end_at=end_at,
        source="GamerPower",
        raw=item,
    )


def fetch_offers(config: dict[str, Any]) -> tuple[list[Offer], list[str]]:
    problems: list[str] = []
    found: dict[str, Offer] = {}
    platforms = config.get("platforms", [])
    types = config.get("include_types", ["game"])
    for platform in platforms:
        for offer_type in types:
            try:
                response = requests.get(
                    GAMERPOWER_URL,
                    params={"platform": platform, "type": offer_type, "sort-by": "date"},
                    timeout=25,
                    headers={"User-Agent": "TurkishFreeGameBlogger/1.0"},
                )
                if response.status_code == 201:
                    continue
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    payload = payload.get("data", [])
                if not isinstance(payload, list):
                    problems.append(f"{platform}/{offer_type}: beklenmeyen API yanıtı")
                    continue
                for row in payload:
                    if isinstance(row, dict):
                        offer = normalize(row)
                        if offer:
                            found[offer.id] = offer
            except (requests.RequestException, ValueError) as exc:
                problems.append(f"{platform}/{offer_type}: {type(exc).__name__}")
    return list(found.values()), problems


def platform_label(platforms: list[str]) -> str:
    raw = ",".join(platforms).lower()
    names = [
        ("epic", "Epic Games"), ("steam", "Steam"), ("gog", "GOG"),
        ("itch", "itch.io"), ("ubisoft", "Ubisoft Connect"),
        ("origin", "EA app"), ("ea", "EA app"), ("playstation", "PlayStation"),
        ("ps4", "PlayStation"), ("ps5", "PlayStation"), ("xbox", "Xbox"),
    ]
    for token, label in names:
        if token in raw:
            return label
    return "PC"


def access_requirement(offer: Offer) -> tuple[str | None, str | None]:
    """Return a requirement only when the source explicitly states it."""
    text = f"{offer.description} {offer.title} {offer.raw.get('instructions', '')}".lower()
    rules = [
        (r"prime\s*(gaming|üyeli|member|membership)|amazon\s*prime", "Prime Gaming", "Prime Gaming üyeliği gerekir."),
        (r"game\s*pass|pc\s*game\s*pass|xbox\s*game\s*pass", "Game Pass", "Game Pass aboneliği gerekir."),
        (r"playstation\s*plus|ps\s*plus|ps\+", "PlayStation Plus", "PlayStation Plus aboneliği gerekir."),
        (r"nintendo\s*switch\s*online", "Nintendo Switch Online", "Nintendo Switch Online üyeliği gerekir."),
    ]
    for pattern, label, notice in rules:
        if re.search(pattern, text):
            return label, notice
    return None, None


def safe_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()


def build_content(offer: Offer, config: dict[str, Any], timezone_name: str) -> tuple[str, list[str], str]:
    tz = ZoneInfo(timezone_name)
    requirement, notice = access_requirement(offer)
    end_txt = ""
    if offer.end_at:
        local_end = offer.end_at.astimezone(tz)
        end_txt = local_end.strftime("%d.%m.%Y %H:%M") + " (Türkiye saati)"
    description = html.escape(offer.description)
    store = platform_label(offer.platforms)
    parts: list[str] = []
    if notice:
        parts.append(f'<p><strong>⚠️ {html.escape(notice)}</strong></p>')
    elif requirement:
        parts.append(f'<p><strong>⚠️ {html.escape(requirement)} koşulunu kontrol edin.</strong></p>')
    parts.append(f'<p><strong>{html.escape(store)} teklifi:</strong> Bu fırsat kaynakta etkin ücretsiz oyun/ödül olarak listeleniyor. Teklif bölge, hesap ve platform koşullarına bağlı olabilir; almadan önce resmî mağaza sayfasındaki koşulları kontrol edin.</p>')
    parts.append('<h2>Oyun hakkında</h2>')
    parts.append(f'<p>{description}</p>')
    parts.append('<h2>Teklif süresi ve koşulları</h2>')
    if end_txt:
        parts.append(f'<p>Kampanya bitişi: <strong>{end_txt}</strong>. Mağazanın gösterdiği yerel saat ve bölge koşulları esas alınmalıdır.</p>')
    else:
        parts.append('<p>Kaynakta kesin bir bitiş zamanı belirtilmemiştir. Teklifin devam edip etmediğini resmî mağaza sayfasından kontrol edin.</p>')
    if offer.offer_type == "loot":
        parts.append('<p>Bu teklif oyun içi içerik veya ek içerik olabilir; temel oyunun ücretsiz olduğu anlamına gelmeyebilir.</p>')
    elif offer.offer_type == "beta":
        parts.append('<p>Bu kayıt beta/test erişimi olabilir; tam oyunun kalıcı olarak ücretsiz olduğu anlamına gelmez.</p>')
    parts.append('<h2>Nasıl alınır?</h2>')
    parts.append(f'<ol><li><a href="{html.escape(offer.url, quote=True)}" rel="nofollow noopener" target="_blank">Resmî teklif / mağaza sayfasını açın</a>.</li><li>Ülke, platform, abonelik ve son tarih koşullarını kontrol edin.</li><li>Mağazanın hesabınıza giriş adımlarını tamamlayıp teklifi süresi dolmadan alın.</li></ol>')
    parts.append('<h2>Sistem gereksinimleri</h2><p>Kaynak veride doğrulanmış sistem gereksinimleri bulunmuyor. Gereksinimleri mağazanın oyun sayfasından kontrol edin.</p>')
    if offer.thumbnail:
        parts.append(f'<p><img src="{html.escape(offer.thumbnail, quote=True)}" alt="{html.escape(offer.title, quote=True)} oyun görseli" loading="lazy"></p>')
    parts.append(f'<p>Veri kaynağı: <a href="{config["gamerpower_attribution_url"]}" rel="nofollow noopener">GamerPower</a>. Teklif bilgileri değişebilir.</p>')
    labels = [store, "Ücretsiz Oyun", "Süreli Kampanya" if offer.end_at else "Ücretsiz Teklif"]
    if requirement:
        labels.append(requirement)
    return "\n".join(parts), labels, notice or (f"{requirement} koşulu kaynak açıklamasında aranacak." if requirement else "Abonelik koşulu kaynakta doğrulanmamış; sayfadaki koşulları kontrol edin.")


def blogger_service() -> Any:
    client_id = os.environ["GOOGLE_CLIENT_ID"]
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    refresh_token = os.environ["GOOGLE_REFRESH_TOKEN"]
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret or None,
        scopes=[BLOGGER_SCOPE],
    )
    creds.refresh(Request())
    return build("blogger", "v3", credentials=creds, cache_discovery=False)


def create_draft(service: Any, blog_id: str, offer: Offer, content: str, labels: list[str], timezone_name: str) -> str:
    title = f"{safe_title(offer.title)} ücretsiz! {platform_label(offer.platforms)} fırsatı"
    path = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:90] or offer.id
    payload = {
        "kind": "blogger#post",
        "title": title,
        "content": content,
        "labels": labels,
        "customMetaData": json.dumps({"description": f"{offer.title} için {platform_label(offer.platforms)} üzerindeki ücretsiz oyun/teklif. Kampanya koşullarını ve bitiş tarihini öğrenin."}, ensure_ascii=False),
    }
    result = service.posts().insert(blogId=blog_id, body=payload, isDraft=True).execute()
    return str(result.get("url") or result.get("id") or "Taslak oluşturuldu")


def main() -> int:
    config = load_json(CONFIG_PATH, None)
    if not config:
        print("config.json bulunamadı. config.example.json dosyasını config.json olarak kopyalayıp düzenleyin.", file=sys.stderr)
        return 2
    blog_id = os.environ.get("BLOGGER_BLOG_ID", "").strip()
    if not blog_id:
        print("BLOGGER_BLOG_ID secret eksik.", file=sys.stderr)
        return 2
    timezone_name = config.get("timezone", "Europe/Istanbul")
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=int(config.get("campaign_safety_hours", 2)))
    seen_doc = load_json(SEEN_PATH, {"seen": {}})
    seen: dict[str, Any] = seen_doc.get("seen", {})
    offers, problems = fetch_offers(config)
    print(f"Kaynakta bulunan uygun teklifler: {len(offers)}")
    if problems:
        print(f"Bazı kaynak sorguları başarısız: {len(problems)}")
    pending: list[tuple[Offer, str, list[str], str]] = []
    for offer in offers:
        if offer.id in seen:
            continue
        if offer.end_at and offer.end_at <= cutoff:
            print(f"Atlandı (bitmiş/yakın bitiyor): {offer.title}")
            continue
        requirement, _ = access_requirement(offer)
        # A subscription label is only safe when the source itself gives us that condition.
        raw_platforms = ",".join(offer.platforms).lower()
        if any(s in raw_platforms for s in ("prime", "game pass", "playstation plus", "subscription")) and not requirement:
            print(f"İnceleme gerekli (abonelik şartı doğrulanamadı): {offer.title}")
            continue
        body, labels, review_note = build_content(offer, config, timezone_name)
        pending.append((offer, body, labels, review_note))
    pending = pending[: int(config.get("max_posts_per_run", 12))]
    if not pending:
        print("Yeni ve güvenli koşulları sağlayan teklif yok; Blogger taslağı oluşturulmadı.")
        return 0
    service = blogger_service()
    created = 0
    for offer, body, labels, review_note in pending:
        try:
            link = create_draft(service, blog_id, offer, body, labels, timezone_name)
            seen[offer.id] = {"title": offer.title, "created_at": now.isoformat(), "url": offer.url}
            print(f"Taslak hazır: {offer.title} — {link}")
            print(f"İnceleme notu: {review_note}")
            created += 1
        except HttpError as exc:
            print(f"Blogger hatası ({offer.title}): HTTP {exc.resp.status}")
        except Exception as exc:
            print(f"İşleme hatası ({offer.title}): {type(exc).__name__}")
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(json.dumps({"seen": seen}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Oluşturulan taslak: {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

