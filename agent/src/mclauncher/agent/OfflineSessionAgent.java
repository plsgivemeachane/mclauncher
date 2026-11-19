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
 */
public final class OfflineSessionAgent {
    static final String SESSION_HOST = "https://sessionserver.mojang.com";
    static final String SERVICES_HOST = "https://api.minecraftservices.com";
    static final String AUTH_HOST = "https://authserver.mojang.com";
    static final String ACCOUNT_HOST = "https://api.mojang.com";
    static final String JOIN_PATH = "/session/minecraft/join";
    static final String LOOPBACK_HOST = "127.0.0.1";

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
        System.setProperty("minecraft.api.session.host", "http://" + LOOPBACK_HOST + ":" + port[0]);
        System.setProperty("minecraft.api.services.host", SERVICES_HOST);
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
            forward(exchange, method, uri, body);
        } catch (IOException error) {
            exchange.sendResponseHeaders(502, -1);
        } finally {
            exchange.close();
        }
    }

    private static void forward(HttpExchange exchange, String method, URI uri, byte[] body) throws IOException {
        String target = SESSION_HOST + uri.getRawPath() + (uri.getRawQuery() == null ? "" : "?" + uri.getRawQuery());
        HttpURLConnection connection = (HttpURLConnection) new URL(target).openConnection();
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(15000);
        connection.setRequestMethod(method);
        for (String header : new String[] {"Content-Type", "Accept", "User-Agent"}) {
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
        String contentType = connection.getContentType();
        if (contentType != null) {
            exchange.getResponseHeaders().set("Content-Type", contentType);
        }
        boolean empty = response.length == 0 || status == 204 || status == 304;
        exchange.sendResponseHeaders(status, empty ? -1 : response.length);
        if (!empty) {
            exchange.getResponseBody().write(response);
        }
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
