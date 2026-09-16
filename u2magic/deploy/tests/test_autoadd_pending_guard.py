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


def test_idle_period_does_not_discard_the_first_new_promotion():
    source = SOURCE.read_text(encoding="utf-8")

    assert "l4 != null && l2 > 300000L" not in source
    assert "已重置执行标记，本次跳过" not in source


def test_per_torrent_upload_limit_is_not_used_to_reject_a_busy_node():
    source = SOURCE.read_text(encoding="utf-8")
    filter_node = source[
        source.index("private boolean filterNode"):
        source.index("public AutoAddSchedule")
    ]

    assert "qbNode.getUpSpeed()" not in filter_node
    assert "qbNode.getUploadLimit()" not in filter_node
    assert "qbNode.setUploadLimit" in source
