from app.collector.base import CollectedCompany

MOCK_COMPANIES: list[dict] = [
    {
        "source_id": "mock_001",
        "name": "Mebel Art",
        "category": "Мебель на заказ",
        "city": "Алматы",
        "address": "ул. Абая 52, Алматы",
        "phone": "+77001112233",
        "website": None,
        "instagram": "@mebel_art_alma",
        "rating": 4.8,
        "reviews_count": 124,
        "source_url": "https://2gis.kz/almaty/firm/mock_001",
        "latitude": 43.2380,
        "longitude": 76.9450,
    },
    {
        "source_id": "mock_002",
        "name": "Кухни Мастер",
        "category": "Мебель на заказ",
        "city": "Алматы",
        "address": "пр. Достык 45, Алматы",
        "phone": "+77003334455",
        "website": "https://kuhni-master.kz",
        "instagram": "@kuhni_master",
        "rating": 4.5,
        "reviews_count": 87,
        "source_url": "https://2gis.kz/almaty/firm/mock_002",
        "latitude": 43.2400,
        "longitude": 76.9500,
    },
    {
        "source_id": "mock_003",
        "name": "Гардеробная Мастерская",
        "category": "Мебель на заказ",
        "city": "Алматы",
        "address": "ул. Сатпаева 28, Алматы",
        "phone": "+77005556677",
        "website": None,
        "instagram": "@garderob_alma",
        "rating": 4.7,
        "reviews_count": 56,
        "source_url": "https://2gis.kz/almaty/firm/mock_003",
        "latitude": 43.2350,
        "longitude": 76.9400,
    },
    {
        "source_id": "mock_004",
        "name": "ОфисМебель Про",
        "category": "Офисная мебель",
        "city": "Алматы",
        "address": "ул. Кunaева 15, Алматы",
        "phone": "+77007778899",
        "website": "https://office-meble.kz",
        "instagram": None,
        "rating": 4.2,
        "reviews_count": 34,
        "source_url": "https://2gis.kz/almaty/firm/mock_004",
        "latitude": 43.2500,
        "longitude": 76.9550,
    },
    {
        "source_id": "mock_005",
        "name": "ДеревоДом",
        "category": "Мебель на заказ",
        "city": "Алматы",
        "address": "ул. Розыбакиева 110, Алматы",
        "phone": "+77009990011",
        "website": None,
        "instagram": "@derevodom_almaty",
        "rating": 4.9,
        "reviews_count": 201,
        "source_url": "https://2gis.kz/almaty/firm/mock_005",
        "latitude": 43.2320,
        "longitude": 76.9350,
    },
    {
        "source_id": "mock_006",
        "name": "Шкаф-Сервис",
        "category": "Мебель на заказ",
        "city": "Алматы",
        "address": "ул. Жандосова 8, Алматы",
        "phone": "+77001223344",
        "website": None,
        "instagram": "@shkaf_service",
        "rating": 4.3,
        "reviews_count": 42,
        "source_url": "https://2gis.kz/almaty/firm/mock_006",
        "latitude": 43.2280,
        "longitude": 76.9420,
    },
]


class MockCollectorAdapter:
    def search(
        self,
        city: str,
        category: str,
        limit: int,
    ) -> list[CollectedCompany]:
        results = []
        for item in MOCK_COMPANIES:
            if len(results) >= limit:
                break
            results.append(CollectedCompany(**item))
        return results
