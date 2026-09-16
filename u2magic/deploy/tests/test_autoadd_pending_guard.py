from pathlib import Path


SOURCE = Path(__file__).parents[1] / "patch-src/com/khc/u2/task/AutoAddSchedule.java"


def test_missing_seeders_is_deferred_without_blocking_later_promotions():
    source = SOURCE.read_text(encoding="utf-8")

    assert 'PENDING_PROMOTIONS_KEY = "PendingPromotions"' in source
    assert "torrentInfo.getTorrentSeeders() == null" in source
    assert "return null;" in source
    assert "if (handled == null)" in source
    assert "rememberPendingPromotion(promotionItem2);" in source
    assert "continue;" in source[source.index("rememberPendingPromotion(promotionItem2);"):]


def test_pending_promotions_are_persisted_and_expired_entries_are_not_added():
    source = SOURCE.read_text(encoding="utf-8")

    assert "JSONUtil.toList(JSONUtil.parseArray(json), PromotionItem.class)" in source
    assert "fileDatabase.put(PENDING_PROMOTIONS_KEY" in source
    assert "promotionItem.getExpirationTime().isBefore(LocalDateTime.now())" in source


def test_pending_queue_is_retried_even_when_there_are_no_new_promotions():
    source = SOURCE.read_text(encoding="utf-8")

    assert "private void retryPendingPromotions(KhcProperties khcProperties)" in source
    assert source.index("this.retryPendingPromotions(khcProperties);") < source.index("List<PromotionItem> list = this.u2Service.getPromotionItems();")
