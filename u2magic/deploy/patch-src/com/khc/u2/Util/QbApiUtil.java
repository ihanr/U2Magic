package com.khc.u2.Util;

import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.io.FileUtil;
import cn.hutool.core.util.NumberUtil;
import cn.hutool.core.util.ObjUtil;
import cn.hutool.core.util.StrUtil;
import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import com.khc.u2.Config.KhcProperties;
import com.khc.u2.model.QbNode;
import java.net.HttpCookie;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** Source replacement for the upstream class, retaining its public entry points. */
@Component
public class QbApiUtil {
    private static final Logger log = LoggerFactory.getLogger(QbApiUtil.class);
    private final KhcProperties khcProperties;

    public QbApiUtil(KhcProperties khcProperties) {
        this.khcProperties = khcProperties;
    }

    private String getCookieFilePath(QbNode qbNode) {
        String directory = this.khcProperties.getPath().getCookieFilePath();
        FileUtil.mkdir(directory);
        return String.format("%s/%s_%s_cookie.txt", directory, qbNode.getName(),
                qbNode.getHost().replaceAll("http://", "").replaceAll(":.*", ""));
    }

    private String loadCookieFromFile(QbNode qbNode) {
        String path = this.getCookieFilePath(qbNode);
        if (FileUtil.exist(path)) {
            try {
                return FileUtil.readString(path, "UTF-8").trim();
            } catch (Exception exception) {
                log.error("加载【{}】Cookie文件失败", qbNode.getName(), exception);
            }
        }
        return null;
    }

    private void saveCookieToFile(QbNode qbNode, String cookie) {
        try {
            FileUtil.writeString(cookie, this.getCookieFilePath(qbNode), "UTF-8");
            log.info("【{}】Cookie已保存到文件", qbNode.getName());
        } catch (Exception exception) {
            log.error("保存【{}】Cookie文件失败", qbNode.getName(), exception);
        }
    }

    public boolean login(QbNode qbNode) {
        String cached = this.loadCookieFromFile(qbNode);
        if (StrUtil.isNotBlank(cached)) {
            qbNode.setCookie(cached);
            qbNode.setStatus(1);
            log.info("【{}】已加载缓存Cookie，先验证有效性", qbNode.getName());
            // The same request validates the session and supplies node statistics.
            this.initQbNodeInfo(qbNode);
            if (qbNode.getStatus() == 1) {
                log.info("【{}】Cookie有效, 直接使用Cookie操作", qbNode.getName());
                return true;
            }
            log.info("【{}】缓存Cookie失效，重新登录", qbNode.getName());
        }
        qbNode.setCookie(null);
        qbNode.setStatus(0);
        Map<String, Object> form = new HashMap<>();
        form.put("username", qbNode.getUsername());
        form.put("password", qbNode.getPassword());
        log.info("开始登录QB节点【{}】", qbNode.getName());
        // Explicit Cookie disables Hutool's global cookie store across same-host nodes.
        try (HttpResponse response = HttpRequest.post(qbNode.getHost() + "/api/v2/auth/login")
                .cookie("").form(form).timeout(10000).execute()) {
            int status = response.getStatus();
            String body = StrUtil.trim(response.body());
            log.info("【{}】登录响应：状态:{}", qbNode.getName(), status);
            boolean accepted = (status == 200 || status == 204)
                    && (StrUtil.isBlank(body) || "Ok.".equalsIgnoreCase(body) || "Ok".equalsIgnoreCase(body));
            String cookie = accepted ? sessionCookie(response) : null;
            if (StrUtil.isNotBlank(cookie)) {
                qbNode.setCookie(cookie);
                qbNode.setStatus(1);
                this.initQbNodeInfo(qbNode);
                if (qbNode.getStatus() == 1) {
                    this.saveCookieToFile(qbNode, cookie);
                    return true;
                }
            }
        } catch (Exception exception) {
            log.error("QB节点【{}】登录失败", qbNode.getName(), exception);
        }
        qbNode.setCookie(null);
        qbNode.setStatus(0);
        log.info("QB节点【{}】登录失败", qbNode.getName());
        return false;
    }

    private static String sessionCookie(HttpResponse response) {
        List<String> headers = response.headerList("Set-Cookie");
        if (headers == null) return null;
        String legacy = null;
        // Read only this response's headers; the global cookie jar may contain other nodes.
        for (String header : headers) {
            for (HttpCookie cookie : HttpCookie.parse(header)) {
                if (cookie.getValue().isEmpty() || cookie.hasExpired()) continue;
                String pair = cookie.getName() + "=" + cookie.getValue();
                if (cookie.getName().startsWith("QBT_SID_")) return pair;
                if (cookie.getName().equals("SID")) legacy = pair;
            }
        }
        return legacy;
    }

    public void initQbNodeInfo(QbNode qbNode) {
        if (qbNode.getStatus() != 1) return;
        if (StrUtil.isBlank(qbNode.getCookie())) {
            qbNode.setStatus(0);
            return;
        }
        String url = String.format("%s/api/v2/sync/maindata?rid=%s", qbNode.getHost(), System.currentTimeMillis());
        try (HttpResponse response = HttpRequest.get(url).cookie(qbNode.getCookie()).timeout(5000).execute()) {
            log.info("验证【{}】Cookie: 状态:{}", qbNode.getName(), response.getStatus());
            if (response.getStatus() == 200) {
                JSONObject data = JSONUtil.parseObj(response.body());
                JSONObject server = data.getJSONObject("server_state");
                qbNode.setUpSpeed(server.getLong("up_info_speed", Long.MAX_VALUE));
                qbNode.setDownSpeed(server.getLong("dl_info_speed", Long.MAX_VALUE));
                qbNode.setFreeSpaceOnDisk(server.getLong("free_space_on_disk", 0L));
                JSONObject torrents = data.getJSONObject("torrents");
                qbNode.setTorrentSize(CollUtil.size(torrents));
                qbNode.setTorrentCategory(countByCategory(torrents));
                log.info("QB节点【{}】登录成功，种子总数:{}, 剩余磁盘空间{}G({}M)，上传速度:{}MB/s，下载速度:{}MB/s",
                        qbNode.getName(), qbNode.getTorrentSize(),
                        NumberUtil.div(qbNode.getFreeSpaceOnDisk().doubleValue(), 1073741824.0, 3),
                        NumberUtil.div(qbNode.getFreeSpaceOnDisk().doubleValue(), 1048576.0, 3),
                        NumberUtil.div(qbNode.getUpSpeed().doubleValue(), 1048576.0, 3),
                        NumberUtil.div(qbNode.getDownSpeed().doubleValue(), 1048576.0, 3));
                return;
            }
        } catch (Exception exception) {
            log.error("获取【{}】上传速度失败", qbNode.getName(), exception);
        }
        // login() owns the single refresh attempt; never recursively log in here.
        qbNode.setStatus(0);
    }

    public boolean addTorrent(QbNode qbNode, String url) {
        KhcProperties.QbittorrentProperties.QbGlobalProperties global = this.khcProperties.getQbittorrent().getGlobal();
        Map<String, Object> form = new HashMap<>();
        form.put("urls", url);
        form.put("category", ObjUtil.defaultIfNull(qbNode.getCategory(), global.getCategory()));
        form.put("tags", "幼儿园");
        form.put("upLimit", qbNode.getUploadLimit());
        form.put("dlLimit", qbNode.getDownLimit());
        form.put("firstLastPiecePrio", ObjUtil.defaultIfNull(qbNode.getFirstLastPiecePrio(), global.isFirstLastPiecePrio()));
        log.info("【{}】发送种子添加请求，分类:{}, 单种上传限速:{} B/s", qbNode.getName(), form.get("category"), qbNode.getUploadLimit());
        try (HttpResponse response = HttpRequest.post(qbNode.getHost() + "/api/v2/torrents/add")
                .cookie(qbNode.getCookie()).form(form).timeout(10000).execute()) {
            int status = response.getStatus();
            String body = StrUtil.trim(response.body());
            log.info("添加结果: 状态:{}, 响应结果:{}", status, body);
            if (status == 200 && ("Ok.".equalsIgnoreCase(body) || "Ok".equalsIgnoreCase(body))) return true;
            if ((status == 200 || status == 202) && JSONUtil.isTypeJSONObject(body)) {
                JSONObject result = JSONUtil.parseObj(body);
                long succeeded = result.getLong("success_count", 0L);
                long pending = result.getLong("pending_count", 0L);
                long failed = result.getLong("failure_count", -1L);
                if (failed == 0 && succeeded >= 0 && pending >= 0 && (succeeded > 0 || pending > 0)) {
                    if (pending > 0) log.info("【{}】QB已接收添加请求，等待下载种子文件", qbNode.getName());
                    return true;
                }
            }
        } catch (Exception exception) {
            log.error("【{}】添加任务失败", qbNode.getName(), exception);
        }
        return false;
    }

    public static Map<String, Long> countByCategory(JSONObject torrents) {
        if (torrents == null || torrents.isEmpty()) return Collections.emptyMap();
        return torrents.values().stream().map(value -> ((JSONObject)value).getStr("category", "无分类"))
                .collect(Collectors.groupingBy(Function.identity(), Collectors.counting()));
    }
}
