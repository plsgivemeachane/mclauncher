package mclauncher.agent;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.instrument.Instrumentation;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URL;
import java.util.concurrent.Executors;

/**
 * Lets an offline session join servers that send a login encryption request.
 *
 * The game reports each server join to the session host before it answers the
 * encryption request. An offline session has no token, so Mojang rejects that
 * report and vanilla gives up with "Invalid session". This agent points the
 * session host at a loopback relay that accepts the join report and forwards
 * every other request (profiles, skins, blocked servers) to Mojang unchanged.
 * Whether the player gets in is still the server's decision.
 *
 * The services host goes through the same relay under {@link #SERVICES_PREFIX}.
 * authlib fetches the Services public keys once at startup and retries only a
 * day later, so a single failed lookup leaves the game unable to verify other
 * players' signed chat. The client then drops those messages from its
 * last-seen list and the server kicks it with "Chat message validation
 * failure" the next time it chats. When the live fetch fails the relay
 * answers with the key set bundled in this jar.
 */
public final class OfflineSessionAgent {
    static final String SESSION_HOST = "https://sessionserver.mojang.com";
    static final String SERVICES_HOST = "https://api.minecraftservices.com";
    static final String AUTH_HOST = "https://authserver.mojang.com";
    static final String ACCOUNT_HOST = "https://api.mojang.com";
    static final String JOIN_PATH = "/session/minecraft/join";
    static final String LOOPBACK_HOST = "127.0.0.1";
    static final String SERVICES_PREFIX = "/services";
    static final String PUBLIC_KEYS_PATH = "/publickeys";
    static final String BUNDLED_PUBLIC_KEYS = "publickeys.json";
    // authlib waits about 15 s for its own request, so give up upstream
    // sooner and still have time to answer with the bundled keys.
    static final int PUBLIC_KEYS_TIMEOUT_MS = 8000;
    static final int FORWARD_TIMEOUT_MS = 15000;
    static final String[] FORWARDED_HEADERS = {"Content-Type", "Accept", "User-Agent", "Authorization"};

    private OfflineSessionAgent() {
    }

    public static void premain(String args, Instrumentation instrumentation) {
        install();
    }

    public static void agentmain(String args, Instrumentation instrumentation) {
        install();
    }

    static void install() {
        // Respect hosts someone configured on purpose.
        if (System.getProperty("minecraft.api.session.host") != null) {
            return;
        }
        final int[] port = {-1};
        // Threads inherit daemon status, so starting the server from a daemon
        // thread keeps the relay from holding the game open after it quits.
        Thread starter = new Thread(() -> {
            try {
                port[0] = start();
            } catch (IOException error) {
                System.err.println("[mclauncher] offline session relay unavailable: " + error);
            }
        }, "mclauncher-session-relay-start");
        starter.setDaemon(true);
        starter.start();
        try {
            starter.join();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return;
        }
        if (port[0] < 0) {
            return;
        }
        // authlib only honours custom hosts when the whole set is present.
        String relay = "http://" + LOOPBACK_HOST + ":" + port[0];
        System.setProperty("minecraft.api.session.host", relay);
        System.setProperty("minecraft.api.services.host", relay + SERVICES_PREFIX);
        System.setProperty("minecraft.api.auth.host", AUTH_HOST);
        System.setProperty("minecraft.api.account.host", ACCOUNT_HOST);
    }

    static int start() throws IOException {
        // Bind the literal IPv4 loopback the session host URL names. Forge
        // launches with -Djava.net.preferIPv6Addresses=system, which turns
        // getLoopbackAddress() into ::1 and leaves 127.0.0.1 refusing joins.
        InetAddress loopback = InetAddress.getByAddress(LOOPBACK_HOST, new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(new InetSocketAddress(loopback, 0), 0);
        server.setExecutor(Executors.newCachedThreadPool(task -> {
            Thread thread = new Thread(task, "mclauncher-session-relay");
            thread.setDaemon(true);
            return thread;
        }));
        server.createContext("/", OfflineSessionAgent::handle);
        server.start();
        return server.getAddress().getPort();
    }

    static void handle(HttpExchange exchange) throws IOException {
        try {
            byte[] body = readAll(exchange.getRequestBody());
            URI uri = exchange.getRequestURI();
            String method = exchange.getRequestMethod();
            if ("POST".equals(method) && JOIN_PATH.equals(uri.getRawPath())) {
                exchange.sendResponseHeaders(204, -1);
                return;
            }
            String path = uri.getRawPath();
            String query = uri.getRawQuery() == null ? "" : "?" + uri.getRawQuery();
            if (path.equals(SERVICES_PREFIX) || path.startsWith(SERVICES_PREFIX + "/")) {
                String servicesPath = path.substring(SERVICES_PREFIX.length());
                String upstream = servicesUpstream();
                if ("GET".equals(method) && PUBLIC_KEYS_PATH.equals(servicesPath)) {
                    servePublicKeys(exchange, upstream + servicesPath + query);
                    return;
                }
                send(exchange, forward(exchange, method, upstream + servicesPath + query, body, FORWARD_TIMEOUT_MS));
                return;
            }
            send(exchange, forward(exchange, method, SESSION_HOST + path + query, body, FORWARD_TIMEOUT_MS));
        } catch (IOException error) {
            exchange.sendResponseHeaders(502, -1);
        } finally {
            exchange.close();
        }
    }

    /** The real services host; tests point it somewhere unreachable. */
    static String servicesUpstream() {
        return System.getProperty("mclauncher.agent.servicesUpstream", SERVICES_HOST);
    }

    /** Prefer Mojang's live key set; fall back to the bundled one when it is unreachable. */
    private static void servePublicKeys(HttpExchange exchange, String target) throws IOException {
        Upstream live = null;
        try {
            live = forward(exchange, "GET", target, new byte[0], PUBLIC_KEYS_TIMEOUT_MS);
        } catch (IOException error) {
            System.err.println("[mclauncher] Services public keys unreachable (" + error + "); using bundled keys");
        }
        if (live != null && live.status == 200 && live.body.length > 0) {
            send(exchange, live);
            return;
        }
        if (live != null) {
            System.err.println("[mclauncher] Services public keys returned HTTP " + live.status + "; using bundled keys");
        }
        InputStream bundled = OfflineSessionAgent.class.getResourceAsStream(BUNDLED_PUBLIC_KEYS);
        if (bundled == null) {
            if (live != null) {
                send(exchange, live);
            } else {
                exchange.sendResponseHeaders(502, -1);
            }
            return;
        }
        send(exchange, new Upstream(200, "application/json", readAll(bundled)));
    }

    static final class Upstream {
        final int status;
        final String contentType;
        final byte[] body;

        Upstream(int status, String contentType, byte[] body) {
            this.status = status;
            this.contentType = contentType;
            this.body = body;
        }
    }

    private static void send(HttpExchange exchange, Upstream response) throws IOException {
        if (response.contentType != null) {
            exchange.getResponseHeaders().set("Content-Type", response.contentType);
        }
        boolean empty = response.body.length == 0 || response.status == 204 || response.status == 304;
        exchange.sendResponseHeaders(response.status, empty ? -1 : response.body.length);
        if (!empty) {
            exchange.getResponseBody().write(response.body);
        }
    }

    private static Upstream forward(HttpExchange exchange, String method, String target, byte[] body, int timeoutMs)
            throws IOException {
        HttpURLConnection connection = (HttpURLConnection) new URL(target).openConnection();
        connection.setConnectTimeout(timeoutMs);
        connection.setReadTimeout(timeoutMs);
        connection.setRequestMethod(method);
        for (String header : FORWARDED_HEADERS) {
            String value = exchange.getRequestHeaders().getFirst(header);
            if (value != null) {
                connection.setRequestProperty(header, value);
            }
        }
        if (body.length > 0) {
            connection.setDoOutput(true);
            try (OutputStream out = connection.getOutputStream()) {
                out.write(body);
            }
        }
        int status = connection.getResponseCode();
        InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
        byte[] response = stream == null ? new byte[0] : readAll(stream);
        return new Upstream(status, connection.getContentType(), response);
    }

    private static byte[] readAll(InputStream stream) throws IOException {
        try (InputStream in = stream) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buffer = new byte[8192];
            int read;
            while ((read = in.read(buffer)) != -1) {
                out.write(buffer, 0, read);
            }
            return out.toByteArray();
        }
    }
}
