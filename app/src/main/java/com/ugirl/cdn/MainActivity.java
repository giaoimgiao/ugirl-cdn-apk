package com.ugirl.cdn;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MainActivity extends Activity {
    private WebView webView;
    private ValueCallback<Uri[]> filePathCallback;
    private static final int FILE_CHOOSER = 1001;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private static final String API = "https://backend.ugirl.vip/api/v1";
    private static final String UA = "ugirl-cdn-android/2.0";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        webView = new WebView(this);
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setUserAgentString(UA);
        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView wv, ValueCallback<Uri[]> cb, FileChooserParams params) {
                if (filePathCallback != null) filePathCallback.onReceiveValue(null);
                filePathCallback = cb;
                try {
                    Intent i = params.createIntent();
                    i.addCategory(Intent.CATEGORY_OPENABLE);
                    startActivityForResult(Intent.createChooser(i, "选择文件"), FILE_CHOOSER);
                } catch (Exception e) {
                    filePathCallback = null;
                    return false;
                }
                return true;
            }
        });
        webView.addJavascriptInterface(new Bridge(), "nativeApi");
        webView.loadUrl("file:///android_asset/index.html");
        setContentView(webView);
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        if (req == FILE_CHOOSER) {
            if (filePathCallback == null) return;
            Uri[] results = null;
            if (res == Activity.RESULT_OK && data != null) {
                if (data.getDataString() != null) {
                    results = new Uri[]{Uri.parse(data.getDataString())};
                } else if (data.getClipData() != null) {
                    int n = data.getClipData().getItemCount();
                    results = new Uri[n];
                    for (int i = 0; i < n; i++) results[i] = data.getClipData().getItemAt(i).getUri();
                }
            }
            filePathCallback.onReceiveValue(results);
            filePathCallback = null;
        } else {
            super.onActivityResult(req, res, data);
        }
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    private String http(String urlStr, String method, String body, String token, boolean isApi) {
        HttpURLConnection c = null;
        try {
            URL url = new URL(urlStr);
            c = (HttpURLConnection) url.openConnection();
            c.setRequestMethod(method);
            c.setConnectTimeout(30000);
            c.setReadTimeout(120000);
            c.setRequestProperty("User-Agent", UA);
            if (isApi) {
                c.setRequestProperty("Content-Type", "application/json");
                if (token != null && !token.isEmpty()) c.setRequestProperty("Authorization", "Bearer " + token);
            }
            if (body != null && !body.isEmpty()) {
                c.setDoOutput(true);
                c.getOutputStream().write(body.getBytes("UTF-8"));
            }
            int code = c.getResponseCode();
            InputStream is = code >= 400 ? c.getErrorStream() : c.getInputStream();
            if (is == null) return "{\"status\":" + code + "}";
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = is.read(buf)) > 0) bos.write(buf, 0, n);
            String resp = bos.toString("UTF-8");
            if (code >= 400 && !resp.trim().startsWith("{")) {
                return "{\"status\":" + code + ",\"error\":\"" + esc(resp) + "\"}";
            }
            return resp;
        } catch (Exception e) {
            return "{\"error\":\"" + esc(e.getMessage()) + "\"}";
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private String esc(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r");
    }

    private void cb(final String callback, final String result) {
        handler.post(new Runnable() {
            @Override
            public void run() {
                webView.evaluateJavascript(callback + "('" + esc(result) + "')", null);
            }
        });
    }

    private class Bridge {
        @JavascriptInterface
        public void post(final String path, final String body, final String token, final String method, final String callback) {
            new Thread(new Runnable() {
                @Override
                public void run() {
                    String r = http(API + path, method == null || method.isEmpty() ? "POST" : method, body, token, true);
                    cb(callback, r);
                }
            }).start();
        }

        @JavascriptInterface
        public void parse(final String url, final String callback) {
            new Thread(new Runnable() {
                @Override
                public void run() {
                    String html = http(url, "GET", null, null, false);
                    if (html.startsWith("{")) { cb(callback, html); return; }
                    Set<String> out = new HashSet<>();
                    try {
                        Pattern p1 = Pattern.compile("(?:src|href|poster)\\s*=\\s*[\"']([^\"']+)[\"']", Pattern.CASE_INSENSITIVE);
                        Matcher m = p1.matcher(html);
                        while (m.find()) {
                            String u = m.group(1);
                            if (u.startsWith("data:") || u.startsWith("javascript:") || u.startsWith("#")) continue;
                            try {
                                String abs = new URL(new URL(url), u).toString();
                                if (abs.startsWith("http")) out.add(abs);
                            } catch (Exception ignored) {}
                        }
                        Pattern p2 = Pattern.compile("url\\(\\s*[\"']?([^\"')]+)[\"']?\\s*\\)", Pattern.CASE_INSENSITIVE);
                        m = p2.matcher(html);
                        while (m.find()) {
                            try {
                                String abs = new URL(new URL(url), m.group(1)).toString();
                                if (abs.startsWith("http")) out.add(abs);
                            } catch (Exception ignored) {}
                        }
                    } catch (Exception ignored) {}
                    List<String> list = new ArrayList<>(out);
                    if (list.size() > 40) list = list.subList(0, 40);
                    StringBuilder sb = new StringBuilder("{\"count\":").append(list.size()).append(",\"assets\":[");
                    for (int i = 0; i < list.size(); i++) {
                        if (i > 0) sb.append(',');
                        sb.append('"').append(esc(list.get(i))).append('"');
                    }
                    sb.append("]}");
                    cb(callback, sb.toString());
                }
            }).start();
        }

        @JavascriptInterface
        public void store(final String url, final String name, final String token, final String callback) {
            new Thread(new Runnable() {
                @Override
                public void run() {
                    try {
                        byte[] content = httpBytes(url);
                        String fname = (name == null || name.isEmpty()) ? "file.bin" : name;
                        String p = http(API + "/storage/presigned-url", "POST",
                                "{\"fileType\":\"s3\",\"fileName\":\"" + esc(fname) + "\",\"fileSize\":" + content.length
                                        + ",\"contentType\":\"application/octet-stream\",\"accessLevel\":\"PUBLIC\"}",
                                token, true);
                        String putUrl = jsonGet(p, "data.presignedUrl");
                        String fp = jsonGet(p, "data.filePath");
                        if (putUrl == null) { cb(callback, "{\"error\":\"presign failed\"}"); return; }
                        putBytes(putUrl, content);
                        String fu = http(API + "/storage/file-url", "POST", "{\"filePath\":\"" + fp + "\"}", token, true);
                        String cdnUrl = jsonGet(fu, "data.url");
                        cb(callback, "{\"filePath\":\"" + fp + "\",\"url\":\"" + esc(cdnUrl == null ? "" : cdnUrl)
                                + "\",\"size\":" + content.length + ",\"name\":\"" + esc(fname) + "\"}");
                    } catch (Exception e) {
                        cb(callback, "{\"error\":\"" + esc(e.getMessage()) + "\"}");
                    }
                }
            }).start();
        }

        @JavascriptInterface
        public void download(final String filePath, final String token, final String callback) {
            new Thread(new Runnable() {
                @Override
                public void run() {
                    try {
                        String fu = http(API + "/storage/file-url", "POST", "{\"filePath\":\"" + filePath + "\"}", token, true);
                        String cdnUrl = jsonGet(fu, "data.url");
                        if (cdnUrl == null) { cb(callback, "{\"error\":\"not found\"}"); return; }
                        byte[] data = httpBytes(cdnUrl);
                        String name = filePath.contains("/") ? filePath.substring(filePath.lastIndexOf('/') + 1) : filePath;
                        File dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
                        if (!dir.exists()) dir.mkdirs();
                        File f = new File(dir, name);
                        FileOutputStream fos = new FileOutputStream(f);
                        fos.write(data);
                        fos.close();
                        cb(callback, "{\"saved\":\"" + esc(f.getAbsolutePath()) + "\",\"size\":" + data.length + "}");
                    } catch (Exception e) {
                        cb(callback, "{\"error\":\"" + esc(e.getMessage()) + "\"}");
                    }
                }
            }).start();
        }

        @JavascriptInterface
        public void openBrowser(String url) {
            try {
                Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                startActivity(i);
            } catch (Exception ignored) {}
        }

        @JavascriptInterface
        public void toast(String msg) {
            Toast.makeText(MainActivity.this, msg, Toast.LENGTH_SHORT).show();
        }

        private byte[] httpBytes(String urlStr) throws Exception {
            HttpURLConnection c = (HttpURLConnection) new URL(urlStr).openConnection();
            c.setRequestMethod("GET");
            c.setConnectTimeout(30000);
            c.setReadTimeout(120000);
            c.setRequestProperty("User-Agent", UA);
            int code = c.getResponseCode();
            if (code >= 400) throw new Exception("HTTP " + code);
            InputStream is = c.getInputStream();
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = is.read(buf)) > 0) bos.write(buf, 0, n);
            is.close();
            c.disconnect();
            return bos.toByteArray();
        }

        private void putBytes(String urlStr, byte[] data) throws Exception {
            HttpURLConnection c = (HttpURLConnection) new URL(urlStr).openConnection();
            c.setRequestMethod("PUT");
            c.setConnectTimeout(30000);
            c.setReadTimeout(120000);
            c.setRequestProperty("Content-Length", String.valueOf(data.length));
            c.setRequestProperty("User-Agent", UA);
            c.setDoOutput(true);
            c.getOutputStream().write(data);
            int code = c.getResponseCode();
            c.disconnect();
            if (code >= 400) throw new Exception("PUT " + code);
        }

        private String jsonGet(String json, String dottedPath) {
            try {
                String[] parts = dottedPath.split("\\.");
                String cur = json;
                for (String p : parts) {
                    int idx = cur.indexOf("\"" + p + "\"");
                    if (idx < 0) return null;
                    cur = cur.substring(idx + p.length() + 2);
                    if (cur.startsWith(":")) cur = cur.substring(1).trim();
                    if (cur.startsWith("\"")) {
                        int end = cur.indexOf('"', 1);
                        return cur.substring(1, end).replace("\\/", "/");
                    }
                }
                return null;
            } catch (Exception e) {
                return null;
            }
        }
    }
}