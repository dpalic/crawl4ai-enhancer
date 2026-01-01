from app.services.wordpress_media import WordPressMediaEnhancer
import json
import pathlib
import pytest


def test_match_media_item_by_slug_and_sizes():
    media_entries = [
        {
            "slug": "header-image",
            "source_url": "https://example.com/wp-content/uploads/2024/01/header-image.png",
            "alt_text": "Header alt",
            "title": {"rendered": "Header title"},
            "media_details": {
                "sizes": {
                    "thumbnail": {
                        "file": "header-image-150x150.png",
                        "width": 150,
                        "height": 150,
                        "mime_type": "image/png",
                        "source_url": "https://example.com/wp-content/uploads/2024/01/header-image-150x150.png",
                    },
                    "full": {
                        "file": "header-image.png",
                        "width": 1200,
                        "height": 400,
                        "mime_type": "image/png",
                        "source_url": "https://example.com/wp-content/uploads/2024/01/header-image.png",
                    },
                }
            },
        }
    ]

    result = WordPressMediaEnhancer.match_media_item(media_entries, "header-image.png")
    assert result is not None
    assert result["source_url"].endswith("header-image.png")
    assert result["alt_text"] == "Header alt"
    assert result["title"] == "Header title"
    size_names = {s["name"] for s in result["sizes"]}
    assert {"thumbnail", "full"} <= size_names


def test_match_against_sample_crawl_fixture():
    """
    Use a saved crawl result (pocs/crawl_result_immediate-winter-glacier-bernina-express-2026.json)
    and verify that the WordPress logo image slug resolves via a simulated media list.
    """
    crawl_path = pathlib.Path("pocs/crawl_result_immediate-winter-glacier-bernina-express-2026.json")
    if not crawl_path.exists():
        pytest.skip("fixture crawl result missing")
    crawl = json.loads(crawl_path.read_text())
    media_urls = []
    for res in crawl.get("results") or []:
        for item in res.get("enhanced_media") or []:
            if isinstance(item, dict):
                media_urls.append(item.get("src_url"))

    target_url = "https://bader-kulturreisen.de/wp-content/uploads/2021/07/bader-kulturreisen03.png"
    assert target_url in media_urls

    wp_media_entries = [
        {
            "slug": "bader-kulturreisen03",
            "source_url": target_url,
            "alt_text": "",
            "title": {"rendered": "bader-kulturreisen03"},
            "media_details": {
                "sizes": {
                    "full": {
                        "file": "bader-kulturreisen03.png",
                        "width": 580,
                        "height": 116,
                        "mime_type": "image/png",
                        "source_url": target_url,
                    }
                }
            },
        }
    ]

    result = WordPressMediaEnhancer.match_media_item(wp_media_entries, "bader-kulturreisen03.png")
    assert result is not None
    assert result["source_url"] == target_url
    assert any(s["name"] == "full" for s in result["sizes"])
