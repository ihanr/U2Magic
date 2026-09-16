/*
 * Decompiled with CFR 0.152.
 *
 * Could not load the following classes:
 *  cn.hutool.core.bean.BeanUtil
 *  cn.hutool.core.collection.CollUtil
 *  cn.hutool.core.date.DateUtil
 *  cn.hutool.core.util.NumberUtil
 *  cn.hutool.core.util.ObjUtil
 *  cn.hutool.core.util.StrUtil
 *  cn.hutool.json.JSONUtil
 *  com.khc.u2.Config.KhcProperties
 *  com.khc.u2.Config.KhcProperties$BusinessProperties
 *  com.khc.u2.Config.KhcProperties$QbittorrentProperties
 *  com.khc.u2.Config.KhcProperties$QbittorrentProperties$QbNodeProperties
 *  com.khc.u2.Config.KhcProperties$QbittorrentProperties$QbNodeWeightConfig
 *  com.khc.u2.Service.ConfigService
 *  com.khc.u2.Service.QbScheduleService
 *  com.khc.u2.Service.U2Service
 *  com.khc.u2.Util.FileDatabase
 *  com.khc.u2.Util.QbApiUtil
 *  com.khc.u2.Util.QbNodeSelector
 *  com.khc.u2.Util.TorrentXmlUtil
 *  com.khc.u2.Util.domain.TorrentInfo
 *  com.khc.u2.Util.domain.TorrentSuccessRecords$TorrentSuccessRecord
 *  com.khc.u2.model.PromotionItem
 *  com.khc.u2.model.QbNode
 *  org.slf4j.Logger
 *  org.slf4j.LoggerFactory
 *  org.springframework.beans.BeanUtils
 *  org.springframework.scheduling.annotation.EnableScheduling
 *  org.springframework.scheduling.annotation.Scheduled
 *  org.springframework.stereotype.Service
 */
package com.khc.u2.task;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.date.DateUtil;
import cn.hutool.core.util.NumberUtil;
import cn.hutool.core.util.ObjUtil;
import cn.hutool.core.util.StrUtil;
import cn.hutool.json.JSONUtil;
import com.khc.u2.Config.KhcProperties;
import com.khc.u2.Service.ConfigService;
import com.khc.u2.Service.QbScheduleService;
import com.khc.u2.Service.U2Service;
import com.khc.u2.Util.FileDatabase;
import com.khc.u2.Util.QbApiUtil;
import com.khc.u2.Util.QbNodeSelector;
import com.khc.u2.Util.TorrentXmlUtil;
import com.khc.u2.Util.domain.TorrentInfo;
import com.khc.u2.Util.domain.TorrentSuccessRecords;
import com.khc.u2.model.PromotionItem;
import java.time.LocalDateTime;
import com.khc.u2.model.QbNode;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.BeanUtils;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

@Service
@EnableScheduling
public class AutoAddSchedule {
    private static final Logger log = LoggerFactory.getLogger(AutoAddSchedule.class);
    private final QbApiUtil qbApiUtil;
    private final QbScheduleService qbScheduleService;
    private final U2Service u2Service;
    private final FileDatabase fileDatabase;
    private final ConfigService configService;
    private final TorrentXmlUtil torrentXmlUtil;
    private static final String LAST_PROMOTION_ID_KEY = "LastPromotionId";
    private static final String LAST_EXECUTE_TIME_KEY = "LastExecuteTime";
    private static final String PENDING_PROMOTIONS_KEY = "PendingPromotions";
    public static final long FIVE_MINUTES_MS = 300000L;

    /*
     * WARNING - Removed try catching itself - possible behaviour change.
     */
    @Scheduled(cron="${khc.schedule.cron:0 * * * * ?}")
    public void executeTask() {
        KhcProperties khcProperties = this.configService.getCurrentConfig();
        if (khcProperties == null || !khcProperties.getSchedule().isEnable()) {
            return;
        }
        long l = System.currentTimeMillis();
        KhcProperties.BusinessProperties businessProperties = khcProperties.getBusiness();
        log.info("\n========== \u5f00\u59cb\u81ea\u52a8\u626b\u63cfU2\u9b54\u6cd5\u79cd\u5b50\u4fe1\u606f ===========");
        log.info("\u914d\u7f6e\u4fe1\u606f: \n \u79cd\u5b50\u4fe1\u606f: \u6700\u5c0f\u4e0a\u4f20\u500d\u7387:{}, \u6700\u5927\u4e0b\u8f7d\u500d\u7387:{}, \u79cd\u5b50\u5927\u5c0f\u533a\u95f4:[{}GB ~ {}GB], \u6700\u5927\u505a\u79cd\u4eba\u6570:{}, QB\u4efb\u52a1\u6570\u9650\u5236:{}, \u5168\u5c40\u5206\u7c7b\u6700\u5927\u4efb\u52a1\u6570:{}, \u914d\u7f6e\u7684qb\u8282\u70b9: \n{} ", new Object[]{businessProperties.getUpRate(), businessProperties.getDownRate(), NumberUtil.div((double)businessProperties.getTorrentMinSize().longValue(), (float)1.0737418E9f, (int)2), NumberUtil.div((double)businessProperties.getTorrentMaxSize().longValue(), (float)1.0737418E9f, (int)2), businessProperties.getSeeders(), khcProperties.getQbittorrent().getGlobal().getMaxTorrentSizeLimit(), khcProperties.getQbittorrent().getGlobal().getCategoryLimits(), khcProperties.getQbittorrent().getNodes().stream().filter(KhcProperties.QbittorrentProperties.QbNodeProperties::isEnabled).map(qbNodeProperties -> String.format("%s: %s", qbNodeProperties.getName(), qbNodeProperties.getHost())).collect(Collectors.joining("\n"))});
        try {
            this.retryPendingPromotions(khcProperties);
            List<PromotionItem> list = this.u2Service.getPromotionItems();
            if (CollUtil.isEmpty((Collection)list)) {
                log.info("\u83b7\u53d6\u7684\u9b54\u6cd5\u6e05\u5355\u4e3a\u7a7a\uff01");
                return;
            }
            Long l3 = (Long)this.fileDatabase.get(LAST_PROMOTION_ID_KEY, Long.class);
            if (ObjUtil.isNull((Object)l3)) {
                Long l5 = list.get(0).getPromotionId();
                this.fileDatabase.put(LAST_PROMOTION_ID_KEY, (Object)l5);
                this.fileDatabase.put(LAST_EXECUTE_TIME_KEY, (Object)l);
                log.info("\u67e5\u8be2\u4e0d\u5230\u5386\u53f2promotionId, \u8bb0\u5f55\u672c\u6b21promotionId==>{}\uff01 \u672c\u6b21\u6267\u884c\u8df3\u8fc7", (Object)l5);
                return;
            }
            Long l7 = list.get(0).getPromotionId();
            if (l7 <= l3) {
                log.info("\u672c\u6b21\u6267\u884c\u6700\u65b0\u7684PromotionId={}, \u4e0a\u6b21\u6700\u540e\u6267\u884c\u7684PromotionId={}, \u65e0\u65b0\u79cd\u5b50\uff0c\u672c\u6b21\u8df3\u8fc7\uff01", (Object)l7, (Object)l3);
                return;
            }
            List<PromotionItem> list2 = list.stream().filter(promotionItem -> promotionItem.getPromotionId() != null && promotionItem.getPromotionId() > l3).sorted(Comparator.comparing(PromotionItem::getPromotionId)).collect(Collectors.toList());
            Long l8 = l3;
            for (PromotionItem promotionItem2 : list2) {
                Boolean handled = this.handlePromotion(khcProperties, promotionItem2);
                if (handled == null) {
                    this.rememberPendingPromotion(promotionItem2);
                    l8 = promotionItem2.getPromotionId();
                    this.fileDatabase.put(LAST_PROMOTION_ID_KEY, l8);
                    this.fileDatabase.put(LAST_EXECUTE_TIME_KEY, l);
                    log.info("promotionId={}, torrentId={} 做种人数未就绪，已加入待重试队列，继续扫描后续新种", promotionItem2.getPromotionId(), promotionItem2.getTorrentId());
                    continue;
                }
                if (!handled) {
                    log.warn("promotionId={}, torrentId={} \u672c\u6b21\u5904\u7406\u672a\u5b8c\u6210\uff0c\u4fdd\u7559LastPromotionId={}\uff0c\u7b49\u5f85\u4e0b\u8f6e\u91cd\u8bd5", new Object[]{promotionItem2.getPromotionId(), promotionItem2.getTorrentId(), l8});
                    break;
                }
                l8 = promotionItem2.getPromotionId();
                this.fileDatabase.put(LAST_PROMOTION_ID_KEY, (Object)l8);
                this.fileDatabase.put(LAST_EXECUTE_TIME_KEY, (Object)l);
            }
        }
        catch (Exception exception) {
            log.error("\u4efb\u52a1\u6267\u884c\u5f02\u5e38", (Throwable)exception);
        }
        finally {
            log.info("========== \u5f00\u59cb\u81ea\u52a8\u626b\u63cfU2\u9b54\u6cd5\u79cd\u5b50\u4fe1\u606f\u7ed3\u675f ===========\n");
        }
    }

    private Boolean handlePromotion(KhcProperties khcProperties, PromotionItem promotionItem) {
        long l = promotionItem.getPromotionId();
        TorrentSuccessRecords.TorrentSuccessRecord torrentSuccessRecord = this.torrentXmlUtil.checkTorrentExists(promotionItem.getTorrentId(), null);
        if (Objects.nonNull(torrentSuccessRecord)) {
            if (torrentSuccessRecord.getRecordType() == 1) {
                log.warn("promotionId={}, torrentId={}, , \u5df2\u5b58\u5728\uff0c\u8df3\u8fc7~~", (Object)l, (Object)promotionItem.getTorrentId());
                return true;
            }
            if (torrentSuccessRecord.getRecordType() == 2 && Objects.equals(torrentSuccessRecord.getPromotionId(), l)) {
                log.warn("promotionId={}, torrentId={}, \u5df2\u5b58\u5728\uff0c\u4f46\u975e\u81ea\u52a8\u6dfb\u52a0\u7684\uff0c\u8df3\u8fc7~~", (Object)l, (Object)promotionItem.getTorrentId());
                return true;
            }
        }
        if (!StrUtil.equalsIgnoreCase((CharSequence)promotionItem.getPromotionType(), (CharSequence)"\u9b54\u6cd5")) {
            log.info("promotionId={}, promotionType={}, torrentName={}, \u5f53\u524d\u7c7b\u578b\u4e3a\u975e\u9b54\u6cd5, \u8df3\u8fc7~~", new Object[]{l, promotionItem.getTorrentName(), promotionItem.getPromotionType()});
            return true;
        }
        if (CollUtil.contains((Collection)khcProperties.getBusiness().getIgnoreUserNames(), (Object)promotionItem.getUserName())) {
            log.info("promotionId={}, userName={}, \u5f53\u524d\u7528\u6237\u4e3a\u9700\u5ffd\u7565\u53d1\u8d77\u9b54\u6cd5\u7684\u7528\u6237, \u8df3\u8fc7~~", (Object)l, (Object)promotionItem.getUserName());
            return true;
        }
        TorrentInfo torrentInfo = (TorrentInfo)ObjUtil.defaultIfNull((Object)this.u2Service.getTorrentDetailByApi(promotionItem.getTorrentId()), () -> this.u2Service.getTorrentDetail(promotionItem.getTorrentId()));
        log.debug("promotionId={},\u83b7\u53d6\u79cd\u5b50\u4fe1\u606f\u6210\u529f:  torrentInfo={}", (Object)l, (Object)JSONUtil.toJsonPrettyStr((Object)torrentInfo));
        if (ObjUtil.isNull((Object)torrentInfo)) {
            log.warn("promotionId={}, \u83b7\u53d6\u79cd\u5b50\u4fe1\u606f\u5931\u8d25, \u8df3\u8fc7~~", (Object)l);
            return false;
        }
        if (torrentInfo.getTorrentSeeders() == null) {
            log.info("promotionId={}, torrentId={}, torrentName={}, 做种人数未就绪，延后重试", l, promotionItem.getTorrentId(), promotionItem.getTorrentName());
            return null;
        }
        KhcProperties.BusinessProperties businessProperties = khcProperties.getBusiness();
        if (torrentInfo.getUpRate() < businessProperties.getUpRate() || torrentInfo.getDownRate() > businessProperties.getDownRate()) {
            log.info("promotionId={}, torrentId={}, torrentName={}, promotionType={}, \u4e0a\u4f20\u500d\u7387\u4e3a:{}(\u914d\u7f6e:{}), \u4e0b\u8f7d\u500d\u7387\u4e3a: {}(\u914d\u7f6e:{}), \u4e0d\u6ee1\u8db3\u6761\u4ef6, \u8df3\u8fc7\uff01", new Object[]{l, promotionItem.getTorrentId(), promotionItem.getTorrentName(), promotionItem.getPromotionType(), torrentInfo.getUpRate(), businessProperties.getUpRate(), torrentInfo.getDownRate(), businessProperties.getDownRate()});
            return true;
        }
        if (torrentInfo.getTorrentSize() <= businessProperties.getTorrentMinSize() || torrentInfo.getTorrentSize() >= businessProperties.getTorrentMaxSize()) {
            log.info("promotionId={}, torrentId={}, torrentName={}, torrentSize={} , \u914d\u7f6e\u8303\u56f4({} kb ~ {} kb), \u4e0d\u6ee1\u8db3\u6761\u4ef6\uff0c\u8df3\u8fc7\uff01", new Object[]{l, promotionItem.getTorrentId(), promotionItem.getTorrentName(), torrentInfo.getTorrentSizeShow(), businessProperties.getTorrentMinSize() / 1024L, businessProperties.getTorrentMaxSize() / 1024L});
            return true;
        }
        if (torrentInfo.getTorrentSeeders() >= businessProperties.getSeeders()) {
            log.info("promotionId={}, torrentId={}, torrentName={}, torrentSeeders={}, \u914d\u7f6e:{} \u4e0d\u6ee1\u8db3\u6761\u4ef6\uff0c\u8df3\u8fc7\uff01", new Object[]{l, promotionItem.getTorrentId(), promotionItem.getTorrentName(), torrentInfo.getTorrentSeeders(), businessProperties.getSeeders()});
            return true;
        }
        if (!StrUtil.containsIgnoreCase((CharSequence)promotionItem.getForUserName(), (CharSequence)"\u6240\u6709\u4eba")) {
            log.info("promotionId={}, torrentId={}, torrentName={}, forUserName={} \u4e0d\u6ee1\u8db3\u6761\u4ef6\uff0c\u8df3\u8fc7\uff01", new Object[]{l, promotionItem.getTorrentId(), promotionItem.getTorrentName(), promotionItem.getForUserName()});
            return true;
        }
        log.info("\n============================\u79cd\u5b50:{}\u5f00\u59cb=========================", (Object)promotionItem.getTorrentId());
        log.info("promotionId={}, \u9b54\u6cd5\u4fe1\u606f\u8be6\u60c5:{}, \u79cd\u5b50\u4fe1\u606f\u8be6\u60c5: {}, \u6ee1\u8db3\u6761\u4ef6\uff0c\u5f00\u59cb\u6dfb\u52a0\u4e0b\u8f7d\u4efb\u52a1\uff01", new Object[]{promotionItem.getPromotionId(), promotionItem, torrentInfo});
        log.info("\u5f00\u59cb\u67e5\u627e\u53ef\u7528\u7684QB\u8282\u70b9~~");
        String string = String.format("https://u2.dmhy.org/download.php?id=%s&passkey=%s&http=1", promotionItem.getTorrentId(), khcProperties.getSite().getPasskey());
        QbNode qbNode = this.addTorrentWithFailover(khcProperties, torrentInfo, string);
        if (qbNode == null) {
            log.error("\u6dfb\u52a0\u79cd\u5b50\u5931\u8d25\uff01\uff01\uff01");
            return false;
        }
        log.info("torrentId={}, torrentName={}, \u6dfb\u52a0\u79cd\u5b50\u5230QB\u3010{}\u3011\u6210\u529f\uff01\uff01\uff01", new Object[]{promotionItem.getTorrentId(), promotionItem.getTorrentName(), qbNode.getName()});
        TorrentSuccessRecords.TorrentSuccessRecord torrentSuccessRecord2 = new TorrentSuccessRecords.TorrentSuccessRecord();
        torrentSuccessRecord2.setAddTime(new Date());
        torrentSuccessRecord2.setNodeName(qbNode.getName());
        torrentSuccessRecord2.setPromotionId(promotionItem.getPromotionId());
        torrentSuccessRecord2.setTorrentId(promotionItem.getTorrentId());
        torrentSuccessRecord2.setRecordType(2);
        BeanUtils.copyProperties((Object)torrentInfo, (Object)torrentSuccessRecord2);
        torrentSuccessRecord2.setRemark(String.format("%s\u81ea\u52a8\u6dfb\u52a0\u79cd\u5b50:%s[%s], \u79cd\u5b50\u5927\u5c0f\u4e3a: %s, \u79cd\u5b50\u4f18\u60e0: \u4e0a\u4f20:%s \u4e0b\u8f7d:%s, \u6dfb\u52a0\u8282\u70b9: %s", DateUtil.now(), torrentInfo.getTorrentId(), torrentInfo.getTorrentTitle(), torrentInfo.getTorrentSizeShow(), torrentInfo.getUpRate(), torrentInfo.getDownRate(), qbNode.getName()));
        this.torrentXmlUtil.saveTorrentRecord(torrentSuccessRecord2);
        log.info("============================\u79cd\u5b50:{}\u7ed3\u675f=========================\n", (Object)promotionItem.getTorrentId());
        return true;
    }

    private List<PromotionItem> loadPendingPromotions() {
        String json = this.fileDatabase.get(PENDING_PROMOTIONS_KEY, String.class);
        if (StrUtil.isBlank(json)) {
            return new ArrayList<PromotionItem>();
        }
        try {
            return new ArrayList<PromotionItem>(JSONUtil.toList(JSONUtil.parseArray(json), PromotionItem.class));
        }
        catch (Exception exception) {
            log.warn("待重试种子队列读取失败，本轮不处理历史待重试项", exception);
            return new ArrayList<PromotionItem>();
        }
    }

    private void retryPendingPromotions(KhcProperties khcProperties) {
        List<PromotionItem> pendingPromotions = this.loadPendingPromotions();
        List<PromotionItem> remainingPendingPromotions = new ArrayList<PromotionItem>();
        for (PromotionItem pendingPromotion : pendingPromotions) {
            if (this.isExpired(pendingPromotion)) {
                log.info("promotionId={}, torrentId={} 做种人数长期未就绪且魔法已过期，最终跳过", pendingPromotion.getPromotionId(), pendingPromotion.getTorrentId());
                continue;
            }
            Boolean pendingHandled = this.handlePromotion(khcProperties, pendingPromotion);
            if (pendingHandled == null || !pendingHandled) {
                remainingPendingPromotions.add(pendingPromotion);
                log.info("promotionId={}, torrentId={} 待重试种子本轮仍未完成，不阻塞新种扫描", pendingPromotion.getPromotionId(), pendingPromotion.getTorrentId());
            }
        }
        this.savePendingPromotions(remainingPendingPromotions);
    }

    private void savePendingPromotions(List<PromotionItem> pendingPromotions) {
        if (CollUtil.isEmpty(pendingPromotions)) {
            this.fileDatabase.remove(PENDING_PROMOTIONS_KEY);
            return;
        }
        this.fileDatabase.put(PENDING_PROMOTIONS_KEY, JSONUtil.toJsonStr(pendingPromotions));
    }

    private void rememberPendingPromotion(PromotionItem promotionItem) {
        List<PromotionItem> pendingPromotions = this.loadPendingPromotions();
        boolean exists = pendingPromotions.stream().anyMatch(item -> Objects.equals(item.getPromotionId(), promotionItem.getPromotionId()));
        if (!exists) {
            pendingPromotions.add(promotionItem);
            this.savePendingPromotions(pendingPromotions);
        }
    }

    private boolean isExpired(PromotionItem promotionItem) {
        return promotionItem.getExpirationTime() != null && promotionItem.getExpirationTime().isBefore(LocalDateTime.now());
    }

    private QbNode addTorrentWithFailover(KhcProperties khcProperties, TorrentInfo torrentInfo, String string) {
        List<QbNode> list = this.buildCandidateNodes(khcProperties, torrentInfo);
        if (CollUtil.isEmpty(list)) {
            log.info("\u627e\u4e0d\u5230\u53ef\u7528\u7684QB\u8282\u70b9\uff01\uff01\uff01");
            return null;
        }
        while (CollUtil.isNotEmpty(list)) {
            QbNode qbNode = QbNodeSelector.selectOptimalNode(list, (KhcProperties.QbittorrentProperties.QbNodeWeightConfig)khcProperties.getQbittorrent().getQbNodeWeight(), (Long)torrentInfo.getTorrentSize());
            if (qbNode == null) {
                return null;
            }
            log.info("\u81ea\u52a8\u9009\u62e9\u7684\u6700\u4f18\u8282\u70b9\u4e3a: {}, \u8282\u70b9\u5269\u4f59\u7a7a\u95f4:{}G, \u8282\u70b9\u5e73\u5747\u4e0a\u4f20\u901f\u5ea6:{} MB/S", new Object[]{qbNode.getName(), NumberUtil.div((double)qbNode.getFreeSpaceOnDisk().longValue(), (float)1.0737418E9f), NumberUtil.div((double)qbNode.getUpSpeed().longValue(), (float)1048576.0f)});
            if (this.qbApiUtil.addTorrent(qbNode, string)) {
                return qbNode;
            }
            log.warn("\u8282\u70b9 {} \u6dfb\u52a0\u79cd\u5b50\u5931\u8d25\uff0c\u91cd\u65b0\u767b\u5f55\u540e\u91cd\u8bd5\u4e00\u6b21", (Object)qbNode.getName());
            this.qbApiUtil.login(qbNode);
            if (this.qbApiUtil.addTorrent(qbNode, string)) {
                return qbNode;
            }
            log.warn("\u8282\u70b9 {} \u91cd\u8bd5\u4ecd\u5931\u8d25\uff0c\u5207\u6362\u4e0b\u4e00\u4e2a\u5019\u9009QB\u8282\u70b9", (Object)qbNode.getName());
            list.remove(qbNode);
        }
        return null;
    }

    private List<QbNode> buildCandidateNodes(KhcProperties khcProperties, TorrentInfo torrentInfo) {
        if (ObjUtil.isNull((Object)torrentInfo)) {
            log.error("\u79cd\u5b50\u4fe1\u606f\u4e3a\u7a7a, \u67e5\u8be2\u8282\u70b9\u5931\u8d25~~");
            return new ArrayList<QbNode>();
        }
        KhcProperties.QbittorrentProperties qbittorrentProperties = khcProperties.getQbittorrent();
        List list = qbittorrentProperties.getNodes().stream().filter(KhcProperties.QbittorrentProperties.QbNodeProperties::isEnabled).map(qbNodeProperties -> {
            QbNode qbNode = new QbNode();
            BeanUtil.copyProperties((Object)qbNodeProperties, (Object)qbNode, (String[])new String[0]);
            qbNode.setCookiePath(khcProperties.getPath().getCookieFilePath());
            qbNode.setUploadLimit((Long)ObjUtil.defaultIfNull((Object)qbNodeProperties.getUploadLimit(), (Object)qbittorrentProperties.getGlobal().getUploadLimit()));
            qbNode.setMaxTorrentSizeLimit((Integer)ObjUtil.defaultIfNull((Object)qbNodeProperties.getMaxTorrentSizeLimit(), (Object)qbittorrentProperties.getGlobal().getMaxTorrentSizeLimit()));
            qbNode.setMaxTorrentSpeedLimit((Long)ObjUtil.defaultIfNull((Object)qbNodeProperties.getMaxTorrentSpeedLimit(), (Object)qbittorrentProperties.getGlobal().getMaxTorrentSpeedLimit()));
            this.qbApiUtil.login(qbNode);
            return qbNode;
        }).filter(qbNode -> this.filterNode((QbNode)qbNode, qbittorrentProperties)).collect(Collectors.toCollection(ArrayList::new));
        list.sort(Comparator.comparing(QbNode::getName));
        return list;
    }

    private boolean filterNode(QbNode qbNode, KhcProperties.QbittorrentProperties qbittorrentProperties) {
        if (qbNode.getStatus() != 1) {
            log.warn("\u8282\u70b9 {} \u72b6\u6001\u5f02\u5e38, \u8df3\u8fc7", (Object)qbNode.getName());
            return false;
        }
        Integer n = (Integer)ObjUtil.defaultIfNull((Object)qbNode.getMaxTorrentSizeLimit(), (Object)qbittorrentProperties.getGlobal().getMaxTorrentSizeLimit());
        if (qbNode.getTorrentSize() > n) {
            log.warn("\u8282\u70b9 {} \u5f53\u524d\u79cd\u5b50\u6570\u91cf:{} , \u8d85\u8fc7\u6700\u5927\u79cd\u5b50\u6570\u91cf[{}]\u9650\u5236, \u8df3\u8fc7", new Object[]{qbNode.getName(), qbNode.getTorrentSize(), n});
            return false;
        }
        Map<String, Long> categoryLimits = CollUtil.isEmpty((Map)qbNode.getCategoryLimits()) ? qbittorrentProperties.getGlobal().getCategoryLimits() : qbNode.getCategoryLimits();
        Map<String, Long> torrentCategory = qbNode.getTorrentCategory();
        log.info("\u8282\u70b9 {} \u5206\u7c7b\u9650\u5236:{}, \u5f53\u524d\u4efb\u52a1\u6570:{}", new Object[]{qbNode.getName(), categoryLimits, torrentCategory});
        if (CollUtil.isNotEmpty((Map)categoryLimits) && CollUtil.isNotEmpty((Map)torrentCategory)) {
            for (String category : torrentCategory.keySet()) {
                if (ObjUtil.isNull(categoryLimits.get(category))) continue;
                Long limit = categoryLimits.get(category);
                Long current = torrentCategory.getOrDefault(category, 0L);
                if (current < limit) continue;
                log.warn("\u8282\u70b9 {} \u5f53\u524d\u5206\u7c7b{}\u79cd\u5b50\u6570\u91cf:{} , \u8d85\u8fc7\u6700\u5927\u79cd\u5b50\u6570\u91cf[{}]\u9650\u5236, \u8df3\u8fc7", new Object[]{qbNode.getName(), category, current, limit});
                return false;
            }
        }
        Long maxTorrentSpeedLimit = (Long)ObjUtil.defaultIfNull((Object)qbNode.getMaxTorrentSpeedLimit(), (Object)qbittorrentProperties.getGlobal().getMaxTorrentSpeedLimit());
        if (qbNode.getDownSpeed() > maxTorrentSpeedLimit) {
            log.warn("\u8282\u70b9 {} \u5f53\u524d\u4e0b\u8f7d\u901f\u5ea6:{} MB/s, \u8d85\u8fc7\u6700\u5927\u4e0b\u8f7d\u901f\u5ea6[{}]\u9650\u5236, \u8df3\u8fc7", new Object[]{qbNode.getName(), qbNode.getDownSpeed() / 1024L / 1024L, maxTorrentSpeedLimit});
            return false;
        }
        return true;
    }

    public AutoAddSchedule(QbApiUtil qbApiUtil, QbScheduleService qbScheduleService, U2Service u2Service, FileDatabase fileDatabase, ConfigService configService, TorrentXmlUtil torrentXmlUtil) {
        this.qbApiUtil = qbApiUtil;
        this.qbScheduleService = qbScheduleService;
        this.u2Service = u2Service;
        this.fileDatabase = fileDatabase;
        this.configService = configService;
        this.torrentXmlUtil = torrentXmlUtil;
    }
}
