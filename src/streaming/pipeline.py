import json

from bs4 import BeautifulSoup
import polars as pl

from config import MatchConfig
from events.adapter import prepare_article, json_text
from events.service import MatchingService
from events.similarity import TextModel
from extractors.accident import extract_frame
from extractors.vnexpress import fetch_vnexpress_locations
from filters.accident import classify_accident
from preprocessors.rss_generic import parse_rss_date


def clean_text(text):
    soup = BeautifulSoup(text, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    # RSS image anchors must not leak into the lead used by the classifier.
    return " ".join(soup.get_text(" ", strip=True).split())


def clean_article(row):
    row = dict(row)
    row["title"] = clean_text(row["title"])
    description = row["description"]
    if row["source"] == "vietnamplus":
        # Match Silver preprocessing: the paragraph is the lead; surrounding
        # anchors are image/related stories and can introduce unrelated places.
        paragraph = BeautifulSoup(description, "html.parser").find("p")
        if paragraph is not None:
            description = str(paragraph)
    row["description"] = clean_text(description)
    if not row["title"]:
        raise ValueError("empty title after cleaning")
    date = parse_rss_date(row["pub_date"])
    if date is None:
        raise ValueError("invalid RSS publication date")
    row["pub_date"] = date
    return row


class ArticleProcessor:
    def __init__(self, repo, config=None):
        self.repo = repo
        self.config = config or MatchConfig(radius_hours=24)
        self.matching = MatchingService(self.config, past_only=True)
        self.config_id = self.matching.config_id

    def process(self, row):
        repo, key = self.repo, row["article_key"]
        prior = repo.connection.execute(
            "SELECT status,event_id FROM stream_receipts WHERE article_key=?", [key]).fetchone()
        if prior:
            return {"status": "already_processed", "event_id": prior[1]}
        raw = json_text(row)
        cleaned = clean_article(row)
        label = classify_accident(cleaned["title"], cleaned["description"])
        article = None
        if label.label == "accident":
            # Keep Bronze metadata in the receipt; extraction needs only scalar fields.
            frame = pl.DataFrame([{k: cleaned[k] for k in (
                "source", "article_key", "normalized_url", "link", "title", "description", "pub_date")}])
            locations = fetch_vnexpress_locations(frame) if row["source"] == "vnexpress" else None
            article = prepare_article(extract_frame(frame, locations).row(0, named=True), reference="redis")
        repo.connection.execute("BEGIN TRANSACTION")
        try:
            event_id = None
            status = label.label
            if article:
                stored = repo.read_articles()
                repo.insert_article(article)
                stored[key] = article
                model = TextModel([a["text"] for a in stored.values()])
                decision = self.matching.decide(article, repo, stored, model)
                status = decision["decision"]
                if status == "needs_review":
                    repo.save_review(article, decision)
                else:
                    event_id = repo.save_assignment(article, decision, self.config_id, model.fingerprint)
                    repo.refresh_event(event_id, stored)
            repo.connection.execute(
                "INSERT INTO stream_receipts (article_key,status,raw_payload,event_id) VALUES (?,?,?,?)",
                [key, status, raw, event_id])
            repo.connection.execute("COMMIT")
        except BaseException:
            repo.connection.execute("ROLLBACK")
            raise
        return {"status": status, "event_id": event_id}
