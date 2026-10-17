import com.khc.u2.Config.KhcProperties;
import com.khc.u2.Util.QbApiUtil;
import com.khc.u2.model.QbNode;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;

/** Protocol fixtures use only disposable credentials and loopback traffic. */
public class QbApiCompatibilityCheck {
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    private static void respond(HttpExchange exchange, int status, String body) throws java.io.IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, status == 204 ? -1 : bytes.length);
        if (status != 204) exchange.getResponseBody().write(bytes);
        exchange.close();
    }

    public static void main(String[] args) throws Exception {
        String scenario = args[0];
        if (scenario.equals("multi")) {
            main(new String[]{"legacy", args[1] + "/old"});
            main(new String[]{"modern", args[1] + "/new"});
            main(new String[]{"no-cookie", args[1] + "/missing"});
            return;
        }
        Path cache = Path.of(args[1]);
        Files.createDirectories(cache);
        KhcProperties config = new KhcProperties();
        KhcProperties.PathProperties paths = new KhcProperties.PathProperties();
        paths.setCookieFilePath(cache.toString());
        config.setPath(paths);
        KhcProperties.QbittorrentProperties qb = new KhcProperties.QbittorrentProperties();
        KhcProperties.QbittorrentProperties.QbGlobalProperties global =
                new KhcProperties.QbittorrentProperties.QbGlobalProperties();
        global.setCategory("U2");
        qb.setGlobal(global);
        config.setQbittorrent(qb);
        QbApiUtil api = new QbApiUtil(config);
        QbNode node = new QbNode();
        node.setName("fixture");
        node.setUsername("fixture-user");
        node.setPassword("fixture-password");
        node.setCategory("U2");
        node.setUploadLimit(51380224L);
        AtomicInteger logins = new AtomicInteger();
        AtomicInteger syncs = new AtomicInteger();
        AtomicInteger adds = new AtomicInteger();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        node.setHost("http://127.0.0.1:" + server.getAddress().getPort());
        // A reverse proxy can expose a different port; trust the response cookie name.
        String cookieName = scenario.equals("legacy") || scenario.equals("cached")
                ? "SID" : "QBT_SID_9090";
        String expectedCookie = cookieName + "=fixture-session";
        Path cookieFile = cache.resolve("fixture_127.0.0.1_cookie.txt");
        if (scenario.equals("cached")) Files.writeString(cookieFile, expectedCookie);
        if (scenario.equals("stale")) Files.writeString(cookieFile, "SID=expired-session");

        server.createContext("/api/v2/auth/login", exchange -> {
            logins.incrementAndGet();
            String form = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            if (!form.contains("username=fixture-user") || !form.contains("password=fixture-password")) {
                respond(exchange, 401, "Unauthorized");
                return;
            }
            if (scenario.equals("denied")) {
                respond(exchange, 401, "Unauthorized");
                return;
            }
            if (!scenario.equals("no-cookie")) {
                exchange.getResponseHeaders().add("Set-Cookie", "unrelated=ignored; Path=/");
                exchange.getResponseHeaders().add("Set-Cookie", expectedCookie + "; HttpOnly; Path=/");
            }
            boolean oldBody = scenario.equals("legacy");
            respond(exchange, oldBody || scenario.equals("modern200") ? 200 : 204, oldBody ? "Ok." : "");
        });
        server.createContext("/api/v2/sync/maindata", exchange -> {
            syncs.incrementAndGet();
            if (scenario.equals("invalid-session")
                    || !expectedCookie.equals(exchange.getRequestHeaders().getFirst("Cookie"))) {
                respond(exchange, 403, "Forbidden");
                return;
            }
            respond(exchange, 200, "{\"server_state\":{\"up_info_speed\":123,\"dl_info_speed\":456,"
                    + "\"free_space_on_disk\":107374182400},\"torrents\":{\"hash\":{\"category\":\"U2\"}}}");
        });
        server.createContext("/api/v2/torrents/add", exchange -> {
            adds.incrementAndGet();
            String form = URLDecoder.decode(new String(exchange.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8), StandardCharsets.UTF_8);
            String addCookie = scenario.equals("add-modern-cookie") ? "QBT_SID_9090=fixture-add" : "SID=fixture-add";
            if (!addCookie.equals(exchange.getRequestHeaders().getFirst("Cookie"))
                    || !form.contains("upLimit=51380224") || !form.contains("category=U2")
                    || !form.contains("urls=https://example.invalid/fixture.torrent")) {
                respond(exchange, 400, "Bad fixture request");
                return;
            }
            switch (scenario) {
                case "add-legacy" -> respond(exchange, 200, "Ok.");
                case "add-pending", "add-modern-cookie" -> respond(exchange, 202,
                        "{\"success_count\":0,\"pending_count\":1,\"failure_count\":0,\"added_torrent_ids\":[]}");
                case "add-success" -> respond(exchange, 200,
                        "{\"success_count\":1,\"pending_count\":0,\"failure_count\":0,\"added_torrent_ids\":[\"hash\"]}");
                case "add-json-failure" -> respond(exchange, 200,
                        "{\"success_count\":0,\"pending_count\":0,\"failure_count\":1,\"added_torrent_ids\":[]}");
                case "add-forbidden" -> respond(exchange, 403, "Ok.");
                case "add-html" -> respond(exchange, 200, "<html>Ok proxy login page</html>");
                default -> respond(exchange, 200, "");
            }
        });
        server.start();
        try {
            if (scenario.startsWith("add-")) {
                node.setCookie(scenario.equals("add-modern-cookie") ? "QBT_SID_9090=fixture-add" : "SID=fixture-add");
                boolean accepted = api.addTorrent(node, "https://example.invalid/fixture.torrent");
                boolean expected = scenario.equals("add-legacy") || scenario.equals("add-pending")
                        || scenario.equals("add-success") || scenario.equals("add-modern-cookie");
                check(accepted == expected, scenario + ": unexpected add result");
                check(adds.get() == 1, "Add request must not be silently repeated");
            } else {
                boolean expected = !scenario.equals("no-cookie") && !scenario.equals("denied")
                        && !scenario.equals("invalid-session");
                check(api.login(node) == expected, scenario + ": unexpected login result");
                check(node.getStatus() == (expected ? 1 : 0), "Node status must match verified session");
                if (expected) {
                    check(expectedCookie.equals(node.getCookie()), "Session cookie name/value was changed");
                    check(expectedCookie.equals(Files.readString(cookieFile)), "Cache did not retain session name/value");
                    check(node.getUpSpeed() == 123 && node.getDownSpeed() == 456, "Node information not populated");
                    check(node.getTorrentCategory().get("U2") == 1, "Category counts not populated");
                    check(logins.get() == (scenario.equals("cached") ? 0 : 1), "Unexpected login count");
                    int loginCount = logins.get();
                    QbNode second = new QbNode();
                    second.setName(node.getName());
                    second.setHost(node.getHost());
                    check(api.login(second), "Saved session must be reusable without credentials");
                    check(logins.get() == loginCount, "A valid cached session must not log in again");
                } else {
                    check(!Files.exists(cookieFile), "Invalid or missing session must not be cached");
                }
                check(syncs.get() <= 5 && logins.get() <= 1, "Authentication retries must be bounded");
            }
            System.out.println("PASS " + scenario);
        } finally {
            server.stop(0);
        }
    }
}
