from scripts.enrich_aozora_card_metadata import card_fields


def test_card_fields_maps_work_and_edition_rows() -> None:
    html = """
    <table><tr><td>作品名読み：</td><td>さくひん</td></tr>
    <tr><td>文字遣い種別：</td><td>新字新仮名</td></tr>
    <tr><td>底本：</td><td>「Sample Edition」</td></tr></table>
    """

    assert card_fields(html) == {
        "作品名読み": "さくひん",
        "文字遣い種別": "新字新仮名",
        "底本名1": "「Sample Edition」",
    }
