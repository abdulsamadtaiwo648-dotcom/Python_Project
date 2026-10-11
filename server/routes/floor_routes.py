"""Community endpoints for SoloBiz's anonymous vendor hub, The Floor."""

from datetime import date, datetime, timedelta
import hashlib
import hmac
import re
import secrets
import unicodedata
from zoneinfo import ZoneInfo

from flask import jsonify, redirect, render_template, request, session
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ..app import app, get_current_user_id
from ..extensions import community_db
from ..models import CommunityVote, MarketMood, SabiPlugRecommendation, SabiPlugRequest, StreetTip


FLOOR_CITIES = (
    "Lagos", "Ilorin", "Ibadan", "Abuja", "Port Harcourt", "Kano",
    "Benin City", "Enugu", "Abeokuta", "Other",
)
FLOOR_CATEGORIES = (
    "General", "Fashion", "Food & Groceries", "Tech/Gadgets",
    "Beauty & Personal Care", "Home & Lifestyle", "Creative Services",
)
MOODS = ("fire", "normal", "cold")
URL_PATTERN = re.compile(
    r"(?i)(?:\b(?:https?://|ftp://|www\.)\S+|\b[a-z0-9][a-z0-9.-]*\.(?:com|net|org|ng|co|io|app|shop|site|link|info|biz|xyz|me|ly|gg)(?:/[^\s]*)?)"
)
HTML_TAG_PATTERN = re.compile(r"</?[a-z][^>]*>", re.IGNORECASE)


def _json_error(message, status=400):
    return jsonify({"status": "error", "message": message}), status


def _payload():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _normalise_text(value, limit, label):
    if not isinstance(value, str):
        return None, f"Enter {label}."
    value = unicodedata.normalize("NFKC", value)
    value = " ".join("".join(char for char in value if char.isprintable() or char.isspace()).split())
    if not value:
        return None, f"Enter {label}."
    if len(value) > limit:
        return None, f"Keep {label} to {limit} characters or fewer."
    if HTML_TAG_PATTERN.search(value):
        return None, "Please remove formatting and enter plain text."
    return value, None


def _validate_scope(data):
    city = str(data.get("city", "")).strip()
    category = str(data.get("category", "")).strip()
    if city not in FLOOR_CITIES:
        return None, None, "Choose a city from the list."
    if category not in FLOOR_CATEGORIES:
        return None, None, "Choose a business category from the list."
    return city, category, None


def _user_hash():
    """Create a stable, non-reversible identifier for this account/session."""
    user_id = get_current_user_id()
    if user_id:
        identity = f"account:{user_id}"
    else:
        identity = session.get("floor_visitor_id")
        if not identity:
            identity = secrets.token_urlsafe(32)
            session["floor_visitor_id"] = identity
        identity = f"visitor:{identity}"
    key = str(app.secret_key).encode("utf-8")
    return hmac.new(key, identity.encode("utf-8"), hashlib.sha256).hexdigest()


def _week_start():
    today = datetime.now(ZoneInfo("Africa/Lagos")).date()
    return today - timedelta(days=today.weekday())


def _mood_summary(city, category):
    start = _week_start()
    records = MarketMood.query.filter_by(week_start=start, city=city, category=category).all()
    counts = {mood: 0 for mood in MOODS}
    for record in records:
        if record.mood in counts:
            counts[record.mood] += 1
    total = sum(counts.values())
    percentages = {
        mood: round(count / total * 100) if total else 0
        for mood, count in counts.items()
    }
    leading_mood = max(counts, key=counts.get) if total else None
    return {
        "counts": counts,
        "percentages": percentages,
        "total": total,
        "leading_mood": leading_mood,
        "week_start": start.isoformat(),
    }


def _filtered_scope():
    city_value = request.args.get("city") or request.cookies.get("floor_city") or "Lagos"
    category_value = request.args.get("category") or request.cookies.get("floor_category") or "General"
    city = city_value if city_value in FLOOR_CITIES else "Lagos"
    category = category_value if category_value in FLOOR_CATEGORIES else "General"
    return city, category


def _iso(value):
    return value.isoformat() if value else None


def _tip_json(tip):
    return {
        "id": tip.id,
        "city": tip.city,
        "category": tip.category,
        "content": tip.content,
        "upvotes": tip.upvotes,
        "created_at": _iso(tip.created_at),
    }


def _recommendation_json(recommendation):
    return {
        "id": recommendation.id,
        "plug_detail": recommendation.plug_detail,
        "upvotes": recommendation.upvotes,
        "created_at": _iso(recommendation.created_at),
    }


@app.route("/floor")
def floor_home():
    if not get_current_user_id():
        return redirect("/login?next=/floor")

    city, category = _filtered_scope()
    cutoff = datetime.utcnow() - timedelta(days=30)
    mood = _mood_summary(city, category)
    active_requests = (
        SabiPlugRequest.query.options(selectinload(SabiPlugRequest.recommendations))
        .filter_by(city=city, category=category)
        .filter(SabiPlugRequest.created_at >= cutoff)
        .order_by(SabiPlugRequest.created_at.desc())
        .limit(40)
        .all()
    )
    tips = (
        StreetTip.query.filter_by(city=city, category=category)
        .order_by(StreetTip.upvotes.desc(), StreetTip.created_at.desc())
        .limit(40)
        .all()
    )
    user_hash = _user_hash()
    tip_ids = [tip.id for tip in tips]
    recommendation_ids = [
        recommendation.id
        for plug_request in active_requests
        for recommendation in plug_request.recommendations
    ]
    voted_tips = {
        vote.target_id for vote in CommunityVote.query.filter_by(
            user_hash=user_hash, target_type="tip"
        ).filter(CommunityVote.target_id.in_(tip_ids)).all()
    } if tip_ids else set()
    voted_recommendations = {
        vote.target_id for vote in CommunityVote.query.filter_by(
            user_hash=user_hash, target_type="recommendation"
        ).filter(CommunityVote.target_id.in_(recommendation_ids)).all()
    } if recommendation_ids else set()
    checked_in = MarketMood.query.filter_by(user_hash=user_hash, week_start=_week_start()).first()

    return render_template(
        "floor.html",
        city=city,
        category=category,
        cities=FLOOR_CITIES,
        categories=FLOOR_CATEGORIES,
        mood=mood,
        checked_in=checked_in,
        active_requests=active_requests,
        tips=tips,
        voted_tips=voted_tips,
        voted_recommendations=voted_recommendations,
        csrf_token=session.get("csrf_token", ""),
    )


@app.route("/floor/mood", methods=["POST"])
def floor_mood():
    if not get_current_user_id():
        return _json_error("Please sign in to check in to the Market Pulse.", 401)
    data = _payload()
    city, category, error = _validate_scope(data)
    if error:
        return _json_error(error)
    mood = str(data.get("mood", "")).strip().lower()
    if mood not in MOODS:
        return _json_error("Choose fire, managing, or cold for your market check-in.")

    user_hash = _user_hash()
    week_start = _week_start()
    record = MarketMood.query.filter_by(user_hash=user_hash, week_start=week_start).first()
    if record:
        record.city = city
        record.category = category
        record.mood = mood
        record.created_at = datetime.utcnow()
    else:
        record = MarketMood(
            user_hash=user_hash,
            city=city,
            category=category,
            mood=mood,
            week_start=week_start,
        )
        community_db.session.add(record)

    try:
        community_db.session.commit()
    except IntegrityError:
        community_db.session.rollback()
        record = MarketMood.query.filter_by(user_hash=user_hash, week_start=week_start).first()
        if not record:
            return _json_error("Your check-in could not be saved. Please try again.", 409)
        record.city = city
        record.category = category
        record.mood = mood
        record.created_at = datetime.utcnow()
        community_db.session.commit()

    return jsonify({
        "status": "success",
        "message": "Your anonymous check-in has been saved for this week.",
        "mood": _mood_summary(city, category),
        "checked_in": mood,
    })


@app.route("/floor/tip", methods=["POST"])
def floor_tip():
    if not get_current_user_id():
        return _json_error("Please sign in to share a Street Wisdom tip.", 401)
    data = _payload()
    city, category, error = _validate_scope(data)
    if error:
        return _json_error(error)
    content, error = _normalise_text(data.get("content"), 160, "a tip")
    if error:
        return _json_error(error)
    if URL_PATTERN.search(content):
        return _json_error("Tips can't include links. Share the advice in your own words.")

    tip = StreetTip(city=city, category=category, content=content)
    community_db.session.add(tip)
    community_db.session.commit()
    return jsonify({"status": "success", "message": "Your anonymous tip is on The Floor.", "tip": _tip_json(tip)}), 201


@app.route("/floor/plug/ask", methods=["POST"])
def floor_plug_ask():
    if not get_current_user_id():
        return _json_error("Please sign in to ask the Sabi-Plug community.", 401)
    data = _payload()
    city, category, error = _validate_scope(data)
    if error:
        return _json_error(error)
    request_text, error = _normalise_text(data.get("request_text"), 140, "your request")
    if error:
        return _json_error(error)

    plug_request = SabiPlugRequest(city=city, category=category, request_text=request_text)
    community_db.session.add(plug_request)
    community_db.session.commit()
    return jsonify({
        "status": "success",
        "message": "Your request has been added to the board.",
        "request": {
            "id": plug_request.id,
            "city": plug_request.city,
            "category": plug_request.category,
            "request_text": plug_request.request_text,
            "recommendations_count": plug_request.recommendations_count,
            "created_at": _iso(plug_request.created_at),
            "recommendations": [],
        },
    }), 201


@app.route("/floor/plug/answer/<int:request_id>", methods=["POST"])
def floor_plug_answer(request_id):
    if not get_current_user_id():
        return _json_error("Please sign in to recommend a business plug.", 401)
    data = _payload()
    detail, error = _normalise_text(data.get("plug_detail"), 160, "a recommendation")
    if error:
        return _json_error(error)
    if not SabiPlugRequest.query.filter_by(id=request_id).first():
        return _json_error("That request is no longer on the board.", 404)

    recommendation = SabiPlugRecommendation(request_id=request_id, plug_detail=detail)
    community_db.session.add(recommendation)
    community_db.session.execute(
        update(SabiPlugRequest)
        .where(SabiPlugRequest.id == request_id)
        .values(recommendations_count=SabiPlugRequest.recommendations_count + 1)
    )
    community_db.session.commit()
    plug_request = SabiPlugRequest.query.filter_by(id=request_id).first()
    return jsonify({
        "status": "success",
        "message": "Your recommendation has been added.",
        "recommendation": _recommendation_json(recommendation),
        "recommendations_count": plug_request.recommendations_count,
    }), 201


@app.route("/floor/upvote/<string:target_type>/<int:target_id>", methods=["POST"])
def floor_upvote(target_type, target_id):
    if not get_current_user_id():
        return _json_error("Please sign in to upvote a community post.", 401)
    model = {"tip": StreetTip, "recommendation": SabiPlugRecommendation}.get(target_type)
    if not model or target_id < 1:
        return _json_error("That upvote target is not valid.")

    target = model.query.filter_by(id=target_id).first()
    if not target:
        return _json_error("That post is no longer available.", 404)
    vote = CommunityVote(
        user_hash=_user_hash(), target_type=target_type, target_id=target_id
    )
    try:
        community_db.session.add(vote)
        community_db.session.execute(
            update(model).where(model.id == target_id).values(upvotes=model.upvotes + 1)
        )
        community_db.session.commit()
    except IntegrityError:
        community_db.session.rollback()
        return _json_error("You have already upvoted this post.", 409)

    community_db.session.refresh(target)
    return jsonify({"status": "success", "upvotes": target.upvotes, "message": "Thanks for the upvote."})
