"""HTML aus RSS-Feeds darf nie im Feed landen."""
import httpx
import pytest

from app.collectors import NewsCollector, RedditCollector
from app.collectors.base import strip_html

# echter Reddit-RSS-Eintrag (gekürzt), so wie er im Dashboard falsch ankam
REDDIT_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
  <title>Is it enough that I've paused my D Ticket subscription with TicketPlus?</title>
  <author><name>/u/Asgerdobastapasta</name></author>
  <link href="https://www.reddit.com/r/deutschebahn/comments/1vi5fvw/is_it_enough/"/>
  <id>t3_1vi5fvw</id>
  <updated>2026-08-13T12:00:00+00:00</updated>
  <content type="html">&lt;!-- SC_OFF --&gt;&lt;div class="md"&gt;&lt;p&gt;Or should I take more steps in order to not get my money deducted for the ticket for September. I'm here only for August. &lt;/p&gt; &lt;p&gt;Dankesch&#246;n! &lt;/p&gt; &lt;/div&gt;&lt;!-- SC_ON --&gt; &amp;#32; submitted by &amp;#32; &lt;a href="https://www.reddit.com/user/Asgerdobastapasta"&gt; /u/Asgerdobastapasta &lt;/a&gt; &amp;#32; to &amp;#32; &lt;a href="https://www.reddit.com/r/deutschebahn/"&gt; r/deutschebahn &lt;/a&gt; &lt;br /&gt; &lt;span&gt;&lt;a href="https://i.redd.it/605huilgczhh1.jpeg"&gt;[link]&lt;/a&gt;&lt;/span&gt; &amp;#32; &lt;span&gt;&lt;a href="https://www.reddit.com/r/deutschebahn/comments/1vi5fvw/"&gt;[comments]&lt;/a&gt;&lt;/span&gt;</content>
</entry>
</feed>"""

NEWS_RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item>
  <title>heise: Kritische L&#252;cke</title>
  <description>&lt;p&gt;Ein &lt;strong&gt;Angreifer&lt;/strong&gt; kann Code ausf&#252;hren.&lt;/p&gt;&lt;script&gt;alert(1)&lt;/script&gt;</description>
  <link>https://example.org/1</link><guid>n1</guid>
</item>
</channel></rss>"""


def test_strip_html_removes_tags_comments_entities():
    raw = '<!-- SC_OFF --><div class="md"><p>Hallo &amp; willkommen</p></div><!-- SC_ON -->'
    out = strip_html(raw)
    assert "<" not in out and ">" not in out
    assert "SC_OFF" not in out and "SC_ON" not in out
    assert "&amp;" not in out
    assert "Hallo & willkommen" in out


def test_strip_html_removes_reddit_boilerplate():
    raw = "Echter Inhalt hier. submitted by /u/tester to r/linux [link] [comments]"
    out = strip_html(raw)
    assert out == "Echter Inhalt hier."


def test_strip_html_keeps_plain_text_untouched():
    assert strip_html("ganz normaler Satz") == "ganz normaler Satz"


def test_strip_html_handles_empty():
    assert strip_html("") == ""
    assert strip_html(None) == ""


@pytest.mark.asyncio
async def test_reddit_rss_fallback_delivers_clean_text():
    def handler(request: httpx.Request) -> httpx.Response:
        if "search.rss" in str(request.url):
            return httpx.Response(200, text=REDDIT_RSS)
        return httpx.Response(403, text="blocked")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        items = await RedditCollector(client).fetch(["deutschlandticket"])

    it = next(i for i in items if i.raw.get("mode") == "rss")
    for verboten in ("<div", "<p>", "SC_OFF", "SC_ON", "&#32;", "[link]", "[comments]", "submitted by"):
        assert verboten not in it.text, f"{verboten!r} steht noch im Text"
    assert "Or should I take more steps" in it.text
    assert "Dankeschön!" in it.text
    # Subreddit und Autor werden aus dem Link/Feed gezogen
    assert it.source == "r/deutschebahn"
    assert "Asgerdobastapasta" in it.author


@pytest.mark.asyncio
async def test_news_feed_delivers_clean_text():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=NEWS_RSS.encode()))
    ) as client:
        items = await NewsCollector(client).fetch([])

    it = items[0]
    assert "<strong>" not in it.text and "<p>" not in it.text
    assert "alert(1)" not in it.text, "script-Inhalt darf nicht durchrutschen"
    assert "Angreifer" in it.text
    assert "Kritische Lücke" in it.title
