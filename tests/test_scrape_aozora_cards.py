from scripts.scrape_aozora_cards import destination_for, xhtml_urls


def test_extracts_xhtml_file_link_from_table_row() -> None:
    page = (
        '<table><tr><td><a href="files/57105_59659.html">XHTMLファイル</a></td></tr></table>'
        '<a href="wrong.html">XHTMLファイル</a>'
    ).encode("cp932")

    assert xhtml_urls("https://www.aozora.gr.jp/cards/001779/card57105.html", page) == [
        "https://www.aozora.gr.jp/cards/001779/files/57105_59659.html"
    ]


def test_destination_includes_author_id(tmp_path) -> None:
    assert destination_for(
        "https://www.aozora.gr.jp/cards/001779/files/57105_59659.html", tmp_path
    ) == tmp_path / "001779_57105_59659.html"
