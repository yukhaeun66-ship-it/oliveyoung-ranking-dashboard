"""
올리브영 랭킹 스크래퍼
- 실행하면 ranking_data.json 생성/업데이트
- 대시보드(올리브영_랭킹_대시보드.html)에서 자동으로 읽어옴
- 실행 방법: python oliveyoung_scraper.py

필요 패키지 설치:
  pip install requests beautifulsoup4
"""

import json
import time
import os
from datetime import datetime, timedelta

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("패키지 설치 중...")
    os.system("pip install requests beautifulsoup4")
    import requests
    from bs4 import BeautifulSoup

# ── 설정 ──────────────────────────────────────────────────────────────────────
HISTORY_FILE = "ranking_history.json"   # 날짜별 누적 히스토리
OUTPUT_FILE  = "ranking_data.json"      # 대시보드가 읽는 파일
HISTORY_DAYS = 7                        # 최근 N일 유지

CATEGORIES = {
    "전체":    "https://www.oliveyoung.co.kr/store/main/getBestList.do?t_page=%ED%99%88&t_click=GNB&t_gnb_type=%EB%9E%AD%ED%82%B9",
    "스킨케어": "https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=100000100010014",
    "마스크팩": "https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=100000100010015",
    "선케어":  "https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=100000100010016",
    "클렌징":  "https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=100000100010017",
    "메이크업": "https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=100000100010013",
    "헤어":    "https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=100000100010022",
    "바디/헬스": "https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=100000100010019",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Referer": "https://www.oliveyoung.co.kr/",
    "Connection": "keep-alive",
}

# ── 파싱 함수 ─────────────────────────────────────────────────────────────────
def parse_price(text: str) -> int:
    """'18,900원' → 18900"""
    return int("".join(filter(str.isdigit, text))) if text else 0


def scrape_category(url: str, cat_name: str, session: requests.Session) -> list[dict]:
    """카테고리 URL에서 랭킹 상품 파싱"""
    try:
        resp = session.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except requests.RequestException as e:
        print(f"  [오류] {cat_name} 요청 실패: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    products = []

    # 올리브영 베스트 상품 리스트 선택자 (실제 구조에 맞게 조정 필요)
    # 구조가 변경될 경우 아래 선택자를 수정하세요
    item_selectors = [
        "ul.best_prd_list > li",       # 베스트 탭 구조
        "ul.prd_list > li",            # 일반 리스트 구조
        "li.li_best",                  # 대안 선택자
        ".cate_prd_list > li",
    ]

    items = []
    for sel in item_selectors:
        items = soup.select(sel)
        if items:
            break

    if not items:
        print(f"  [경고] {cat_name}: 상품 목록을 찾지 못했습니다. 선택자를 확인하세요.")
        return []

    for i, item in enumerate(items[:20], start=1):
        try:
            # 순위
            rank_el = item.select_one(".rank, .num, .prd_rank, .best_rank")
            rank = int(rank_el.text.strip()) if rank_el else i

            # 브랜드
            brand_el = item.select_one(".tx_brand, .brand, .prd_brand, .mft_nm")
            brand = brand_el.text.strip() if brand_el else ""

            # 상품명
            name_el = item.select_one(".tx_name, .prd_name, .name, .goods_name")
            name = name_el.text.strip() if name_el else ""
            if not name:
                continue

            # 가격
            price_el = item.select_one(".tx_price, .price, .prd_price, .price_pack")
            price = parse_price(price_el.text) if price_el else 0

            # 이미지
            img_el = item.select_one("img")
            image = img_el.get("src", "") or img_el.get("data-src", "") if img_el else ""
            if image.startswith("//"):
                image = "https:" + image

            # 상품 상세 URL
            link_el = item.select_one("a[href*='getGoodsDetail'], a[href*='goodsNo']")
            if not link_el:
                link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            if href and not href.startswith("http"):
                href = "https://www.oliveyoung.co.kr" + href
            product_url = href if "oliveyoung" in href else ""

            products.append({
                "rank": rank,
                "brand": brand,
                "name": name,
                "price": price,
                "category": cat_name,
                "image": image,
                "url": product_url,
            })
        except Exception as e:
            print(f"  [경고] 상품 파싱 중 오류 (index {i}): {e}")
            continue

        time.sleep(0.1)  # 서버 부하 방지

    print(f"  {cat_name}: {len(products)}개 상품 수집")
    return products


# ── 히스토리 관리 ──────────────────────────────────────────────────────────────
def load_history() -> dict:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}  # { "2026-03-25": { "브랜드_상품명": rank, ... } }


def save_history(history: dict):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def product_key(p: dict) -> str:
    return f"{p['brand']}_{p['name']}"


def get_history_for_product(key: str, history: dict, today: str) -> list:
    """최근 7일간 해당 상품의 순위 배열 반환 (없으면 null)"""
    result = []
    for i in range(HISTORY_DAYS - 1, -1, -1):
        d = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=i)).strftime("%Y-%m-%d")
        day_data = history.get(d, {})
        result.append(day_data.get(key, None))
    return result


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*50}")
    print(f"  올리브영 랭킹 스크래퍼 시작  ({now_str})")
    print(f"{'='*50}\n")

    history = load_history()
    session = requests.Session()

    # 전체 랭킹 수집 (기본)
    print("[1/2] 전체 랭킹 수집 중...")
    all_products = scrape_category(CATEGORIES["전체"], "전체", session)

    # 전체 수집이 실패하면 카테고리별 수집
    if not all_products:
        print("\n[1/2] 전체 수집 실패 → 카테고리별 수집 시도...")
        cat_names = ["스킨케어", "마스크팩", "선케어", "클렌징", "메이크업", "헤어", "바디/헬스"]
        for cat in cat_names:
            prods = scrape_category(CATEGORIES[cat], cat, session)
            all_products.extend(prods)
            time.sleep(1.0)

        # 중복 제거 후 재정렬
        seen = set()
        deduped = []
        for p in all_products:
            key = product_key(p)
            if key not in seen:
                seen.add(key)
                deduped.append(p)
        all_products = deduped

    if not all_products:
        print("\n[오류] 상품을 수집하지 못했습니다.")
        print("  → 원인: User-Agent 차단, 동적 렌더링, 선택자 변경 등")
        print("  → 해결: Selenium/Playwright 사용 권장")
        return

    # 오늘 히스토리 업데이트
    print(f"\n[2/2] 히스토리 업데이트 중... ({today})")
    today_data = {product_key(p): p["rank"] for p in all_products}
    history[today] = today_data

    # 오래된 데이터 정리
    cutoff = (datetime.now() - timedelta(days=HISTORY_DAYS + 1)).strftime("%Y-%m-%d")
    history = {d: v for d, v in history.items() if d >= cutoff}
    save_history(history)

    # 이전 날짜 데이터로 prevRank 계산
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_day = history.get(yesterday, {})

    output_products = []
    for p in all_products:
        key = product_key(p)
        prev_rank = prev_day.get(key, None)
        history_arr = get_history_for_product(key, history, today)
        output_products.append({
            "rank":     p["rank"],
            "prevRank": prev_rank,
            "brand":    p["brand"],
            "name":     p["name"],
            "price":    p["price"],
            "category": p["category"],
            "image":    p.get("image", ""),
            "url":      p.get("url", ""),
            "isNew":    prev_rank is None and all(h is None for h in history_arr[:-1]),
            "history":  history_arr,
        })

    # 순위 정렬
    output_products.sort(key=lambda x: x["rank"])

    # 최종 JSON 저장
    output = {
        "updatedAt": now_str,
        "products":  output_products,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n완료! {len(output_products)}개 상품 → {OUTPUT_FILE} 저장")
    print("브라우저에서 대시보드를 열고 [새로고침] 버튼을 클릭하세요.\n")


if __name__ == "__main__":
    main()
