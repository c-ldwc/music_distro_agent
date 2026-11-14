from src.email_utils import gmail


def test_html_to_text_strips_scripts_and_tags():
    html = "<html><style>p{}</style><script>x()</script><p>Artist</p><p>Album</p></html>"
    assert gmail._html_to_text(None, html) == "Artist\nAlbum"
